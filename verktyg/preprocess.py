#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================ SOLDYRKAREN PREPROCESS v1.9 ============================
Bygger höjdtiles (PNG) för Soldyrkaren från:
  1. Lantmäteriets laserdata (LAZ, SWEREF99 TM / EPSG:3006, RH2000)
  2. (valfritt) SBK Trädkronehöjd - absolut höjd (GeoTIFF, 50 cm, RH2000)
  3. OSM-byggnadsfotavtryck via Overpass (för att skilja hus från vegetation i lasern)

Utdata: <out>/index.json + <out>/<E>_<N>.png  (512x512 px, 1 m/px, SWEREF99 TM)
  Kodning per pixel: v = (höjd_m + 100) * 10  →  R = v >> 8, G = v & 255   (hård yta:
  mark + byggnader, absolut RH2000; v = 0 betyder "ingen data")
  B = trädkronans TOPP över hårda ytan i 0,5 m-steg (0 = inget träd)
  Dessutom <key>_bas.png (RGB, formatversion 2):
    R = kronans UNDERKANT över hårda ytan i 0,5 m-steg (0 = ner till marken)
    G = byggnadsflagga (255 = pixeln är byggnad enligt OSM-mask + höjd)
    B = byggnadens höjd över marken i 0,5 m-steg (ground = hård - B*0,5)
  Valfritt: tex_<key>.jpg - ortofototextur 0,5 m/px (via --orto)

Användning:
  python preprocess.py --laz ./laz --out ./tiles --bbox 670100 6577300 671600 6578750
  (--bbox EMIN NMIN EMAX NMAX i SWEREF99 TM begränsar området; för stora
   10 km COPC-rutor läses då bara det utsnittet ur filen - snabbt och RAM-snålt)
Beroenden:
  pip install numpy pillow "laspy[lazrs]"
  pip install rasterio           # endast om --sbk används
=====================================================================================
"""
import argparse, glob, json, math, os, ssl, sys, urllib.request, urllib.parse

import numpy as np
from PIL import Image, ImageDraw

TILE = 512          # tilestorlek i px = meter
H0, HSCALE = -100.0, 10.0   # höjdkodning
GROUND_CLS = (2, 9)         # mark + vatten
OBJECT_CLS = (1,)           # "övrigt" i Lantmäteriets klassning (hus, träd, m.m.)
VEG_MIN = 1.5               # lägsta objekthöjd som räknas som vegetation, m

# ---------------- SWEREF99 TM (EPSG:3006) <-> WGS84, Gauss-Krügerserier ----------------
_a, _f = 6378137.0, 1.0/298.257222101
_e2 = _f*(2-_f); _n = _f/(2-_f)
_ah = _a/(1+_n)*(1+_n**2/4+_n**4/64)
_k0, _FN, _FE, _lon0 = 0.9996, 0.0, 500000.0, math.radians(15.0)

def latlon_to_en(lat, lon):
    phi, lam = math.radians(lat), math.radians(lon)
    A = _e2; B = (5*_e2**2-_e2**3)/6; C = (104*_e2**3-45*_e2**4)/120; D = 1237*_e2**4/1260
    s = math.sin(phi)
    ps = phi - s*math.cos(phi)*(A + B*s*s + C*s**4 + D*s**6)
    dl = lam - _lon0
    xi = math.atan2(math.tan(ps), math.cos(dl))
    eta = math.atanh(math.cos(ps)*math.sin(dl))
    b1 = _n/2-2*_n**2/3+5*_n**3/16+41*_n**4/180
    b2 = 13*_n**2/48-3*_n**3/5+557*_n**4/1440
    b3 = 61*_n**3/240-103*_n**4/140
    b4 = 49561*_n**4/161280
    N = _k0*_ah*(xi + b1*math.sin(2*xi)*math.cosh(2*eta) + b2*math.sin(4*xi)*math.cosh(4*eta)
                 + b3*math.sin(6*xi)*math.cosh(6*eta) + b4*math.sin(8*xi)*math.cosh(8*eta)) + _FN
    E = _k0*_ah*(eta + b1*math.cos(2*xi)*math.sinh(2*eta) + b2*math.cos(4*xi)*math.sinh(4*eta)
                 + b3*math.cos(6*xi)*math.sinh(6*eta) + b4*math.cos(8*xi)*math.sinh(8*eta)) + _FE
    return E, N

def en_to_latlon(E, N):
    d1 = _n/2-2*_n**2/3+37*_n**3/96-_n**4/360
    d2 = _n**2/48+_n**3/15-437*_n**4/1440
    d3 = 17*_n**3/480-37*_n**4/840
    d4 = 4397*_n**4/161280
    xi, eta = (N-_FN)/(_k0*_ah), (E-_FE)/(_k0*_ah)
    xip = xi - (d1*math.sin(2*xi)*math.cosh(2*eta) + d2*math.sin(4*xi)*math.cosh(4*eta)
                + d3*math.sin(6*xi)*math.cosh(6*eta) + d4*math.sin(8*xi)*math.cosh(8*eta))
    etp = eta - (d1*math.cos(2*xi)*math.sinh(2*eta) + d2*math.cos(4*xi)*math.sinh(4*eta)
                 + d3*math.cos(6*xi)*math.sinh(6*eta) + d4*math.cos(8*xi)*math.sinh(8*eta))
    ps = math.asin(math.sin(xip)/math.cosh(etp))
    dl = math.atan2(math.sinh(etp), math.cos(xip))
    As = _e2 + _e2**2 + _e2**3 + _e2**4
    Bs = -(7*_e2**2 + 17*_e2**3 + 30*_e2**4)/6
    Cs = (224*_e2**3 + 889*_e2**4)/120
    Ds = -4279*_e2**4/1260
    s = math.sin(ps)
    phi = ps + s*math.cos(ps)*(As + Bs*s*s + Cs*s**4 + Ds*s**6)
    return math.degrees(phi), math.degrees(_lon0 + dl)

# ---------------- Overpass: byggnadsfotavtryck ----------------
def fetch_buildings(e0, n0, e1, n1, pad=30):
    """Hämtar byggnadspolygoner (listor av (E,N)) inom SWEREF-bbox."""
    lat0, lon0 = en_to_latlon(e0-pad, n0-pad)
    lat1, lon1 = en_to_latlon(e1+pad, n1+pad)
    q = (f'[out:json][timeout:60];('
         f'way["building"]({lat0},{lon0},{lat1},{lon1});'
         f'relation["building"]["type"="multipolygon"]({lat0},{lon0},{lat1},{lon1});'
         f');out geom;')
    req = urllib.request.Request('https://overpass-api.de/api/interpreter',
                                 data=('data='+urllib.parse.quote(q)).encode(),
                                 headers={'User-Agent': 'Soldyrkaren-preprocess/1.0'})
    # Python 3.14 kör strikt certvalidering; företagsproxyers certifikat
    # saknar ofta Authority Key Identifier -> stäng av ENDAST striktheten
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        data = json.load(r)
    polys = []
    for el in data.get('elements', []):
        geoms = []
        if el.get('type') == 'way' and 'geometry' in el:
            geoms = [el['geometry']]
        elif el.get('type') == 'relation':
            geoms = [m['geometry'] for m in el.get('members', [])
                     if m.get('role') == 'outer' and 'geometry' in m]
        for g in geoms:
            polys.append([latlon_to_en(p['lat'], p['lon']) for p in g])
    return polys

def rasterize_mask(polys, e0, n_top, W, H):
    """Byggnadsmask, row 0 = norr. 1 px dilatation för takutsprång."""
    img = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(img)
    for poly in polys:
        pts = [(E - e0, n_top - N) for E, N in poly]
        if len(pts) >= 3:
            d.polygon(pts, fill=1)
    m = np.array(img, dtype=bool)
    dil = m.copy()
    dil[1:, :] |= m[:-1, :]; dil[:-1, :] |= m[1:, :]
    dil[:, 1:] |= m[:, :-1]; dil[:, :-1] |= m[:, 1:]
    return dil

# ---------------- Rasterhjälpare ----------------
def fill_nan(a, iters=15):
    """Fyller hål med medel av grannar, iterativt (täcker ~iters meter)."""
    for _ in range(iters):
        m = np.isnan(a)
        if not m.any():
            break
        p = np.pad(a, 1, constant_values=np.nan)
        with np.errstate(all='ignore'):
            nb = np.nanmean(np.stack([p[1:-1, :-2], p[1:-1, 2:],
                                      p[:-2, 1:-1], p[2:, 1:-1]]), axis=0)
        a[m] = nb[m]
    return a

def despike(a, thr, iters=2):
    """Kapar enstaka pixlar som sticker upp mer än thr över grannarnas max."""
    for _ in range(iters):
        p = np.pad(a, 1, mode='edge')
        with np.errstate(all='ignore'):
            nb = np.nanmax(np.stack([p[1:-1, :-2], p[1:-1, 2:],
                                     p[:-2, 1:-1], p[2:, 1:-1]]), axis=0)
        m = ~np.isnan(a) & ~np.isnan(nb) & (a > nb + thr)
        a[m] = nb[m]
    return a

def median3(a):
    """3x3-nanmedian."""
    p = np.pad(a, 1, mode='edge')
    st = np.stack([p[i:i+a.shape[0], j:j+a.shape[1]]
                   for i in range(3) for j in range(3)])
    with np.errstate(all='ignore'):
        return np.nanmedian(st, axis=0)

def encode_tile(hard, veg_extra):
    """hard: float m (nan=nodata). veg_extra: float m över hård yta."""
    v = np.where(np.isnan(hard), 0,
                 np.clip(np.round((hard - H0) * HSCALE), 1, 65535)).astype(np.uint32)
    rgb = np.zeros((TILE, TILE, 3), dtype=np.uint8)
    rgb[..., 0] = v >> 8
    rgb[..., 1] = v & 255
    rgb[..., 2] = np.clip(np.round(np.nan_to_num(veg_extra) / 0.5), 0, 255).astype(np.uint8)
    return rgb

def decode_tile(rgb):
    v = rgb[..., 0].astype(np.float64) * 256 + rgb[..., 1]
    hard = np.where(v == 0, np.nan, v / HSCALE + H0)
    veg = rgb[..., 2].astype(np.float64) * 0.5
    return hard, veg

def merge_into(path, hard, veg, base=None, bflag=None, bh=None):
    bpath = path.replace('.png', '_bas.png')
    if base is None: base = np.zeros_like(veg)
    if bflag is None: bflag = np.zeros(veg.shape, dtype=bool)
    if bh is None: bh = np.zeros_like(veg)
    if os.path.exists(path):
        h0, v0 = decode_tile(np.array(Image.open(path)))
        if os.path.exists(bpath):
            old = np.array(Image.open(bpath).convert('RGB'), dtype=np.float64)
            b0, f0, bh0 = old[..., 0]*0.5, old[..., 1] > 127, old[..., 2]*0.5
        else:
            b0 = np.zeros_like(veg); f0 = np.zeros(veg.shape, bool); bh0 = np.zeros_like(veg)
        hard = np.where(np.isnan(hard), h0, np.where(np.isnan(h0), hard, np.maximum(hard, h0)))
        veg = np.maximum(veg, v0)
        base = np.minimum(base, b0)   # konservativt: lägsta basen vinner
        bflag = bflag | f0
        bh = np.maximum(bh, bh0)
    Image.fromarray(encode_tile(hard, veg)).save(path, optimize=True)
    out = np.zeros((TILE, TILE, 3), dtype=np.uint8)
    out[..., 0] = np.clip(np.round(np.nan_to_num(base) / 0.5), 0, 255)
    out[..., 1] = np.where(bflag, 255, 0)
    out[..., 2] = np.clip(np.round(np.nan_to_num(bh) / 0.5), 0, 255)
    if out.any():
        Image.fromarray(out, mode='RGB').save(bpath, optimize=True)

# ---------------- Steg 1: LAZ → hård yta + laser-vegetation ----------------
def copc_query_robust(path, bbox):
    """Eget nodval: ladda ALLA hierarkisidor, välj varje nod vars voxel
    överlappar bbox - oberoende av trädkopplingar (laspys egen query
    missade delträd i Lantmäteriets filer)."""
    from laspy.copc import CopcReader, HierarchyPage, OctreeNode
    with CopcReader.open(path) as r:
        h = r.header
        print(f'    filens utbredning: E {h.mins[0]:.0f}-{h.maxs[0]:.0f}, '
              f'N {h.mins[1]:.0f}-{h.maxs[1]:.0f}, H {h.mins[2]:.0f}-{h.maxs[2]:.0f}')
        if (bbox[2] < h.mins[0] or bbox[0] > h.maxs[0] or
            bbox[3] < h.mins[1] or bbox[1] > h.maxs[1]):
            return None
        info = r.copc_info
        entries = dict(r.root_page.entries)
        loaded = set()
        while True:
            pages = [(k, e) for k, e in entries.items()
                     if e.point_count == -1 and e.offset not in loaded]
            if not pages:
                break
            for k, e in pages:
                loaded.add(e.offset)
                r.source.seek(e.offset)
                entries.update(HierarchyPage.from_bytes(
                    r.source.read(e.byte_size)).entries)
        # Två voxelkonventioner förekommer:
        #  A) COPC-spec: kubisk rot = center +/- halfsize
        #  B) LM/PDAL-observerad: rot = filens datautbredning PER AXEL
        # Vi väljer noden om NÅGON av dem överlappar bbox (överurval är
        # billigt - slutfiltret på punktnivå rensar ändå).
        rootmin = np.asarray(info.center, float) - info.halfsize
        side = 2.0 * info.halfsize
        dmin = np.asarray(h.mins, float)
        dext = np.asarray(h.maxs, float) - dmin
        sel = []
        for k, e in entries.items():
            if e.point_count <= 0:
                continue
            f2 = 2 ** k.level
            # A: kub
            sza = side / f2
            ax = rootmin[0] + k.x * sza; ay = rootmin[1] + k.y * sza
            hitA = not (ax + sza < bbox[0] or ax > bbox[2] or
                        ay + sza < bbox[1] or ay > bbox[3])
            # B: datautbredning per axel
            sxb = dext[0] / f2; syb = dext[1] / f2
            bx = dmin[0] + k.x * sxb; by = dmin[1] + k.y * syb
            hitB = not (bx + sxb < bbox[0] or bx > bbox[2] or
                        by + syb < bbox[1] or by > bbox[3])
            if not (hitA or hitB):
                continue
            n = OctreeNode(); n.key = k; n.offset = e.offset
            n.byte_size = e.byte_size; n.point_count = e.point_count
            sel.append(n)
        print(f'    hierarki: {len(entries)} noder ({len(loaded)} undersidor), '
              f'{len(sel)} valda för utsnittet')
        pts = r._fetch_and_decompress_points_of_nodes(sel)
    x = np.asarray(pts.x); y = np.asarray(pts.y)
    m = (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
    return (x[m], y[m], np.asarray(pts.z)[m],
            np.asarray(pts.classification)[m],
            np.asarray(pts.intensity)[m].astype(np.float64))

SNABB = True    # --helskanning tvingar chunkskanning (facit-metoden).
                # Voxelbuggen i LM:s filer är löst (dubbel konvention,
                # se copcdiff2) men rimlighetskollen nedan vakar ändå.

def load_points(path, bbox):
    import laspy
    if bbox and path.lower().endswith('.copc.laz'):
        if SNABB:
            res = copc_query_robust(path, bbox)
            if res is None:
                return None
            expected = (bbox[2]-bbox[0]) * (bbox[3]-bbox[1]) * 0.2
            if len(res[0]) >= expected:
                return res
            print(f'    nodvalet gav bara {len(res[0])} punkter '
                  f'(förväntat >{expected:.0f}) - chunkskanning istället ...')
        return chunk_scan(path, bbox)
    las = laspy.read(path)
    x = np.asarray(las.x); y = np.asarray(las.y); z = np.asarray(las.z)
    c = np.asarray(las.classification)
    ii = np.asarray(las.intensity).astype(np.float64)
    if bbox:
        m = (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
        x, y, z, c, ii = x[m], y[m], z[m], c[m], ii[m]
    return x, y, z, c, ii

def chunk_scan(path, bbox):
    """Läser hela LAZ-filen i bitar och filtrerar mot bbox - långsammare men pålitligt."""
    import laspy
    xs, ys, zs, cs = [], [], [], []
    with laspy.open(path) as fh:
        tot = fh.header.point_count
        done = 0
        for ch in fh.chunk_iterator(10_000_000):
            x = np.asarray(ch.x); y = np.asarray(ch.y)
            m = (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
            if m.any():
                xs.append(x[m]); ys.append(y[m])
                zs.append(np.asarray(ch.z)[m])
                cs.append(np.asarray(ch.classification)[m])
                if not hasattr(chunk_scan, "_is"): chunk_scan._is=[]
                chunk_scan._is.append(np.asarray(ch.intensity)[m].astype(np.float64))
            done += len(x)
            hits = sum(map(len, xs))
            print(f'\r    skannar {done/1e6:.0f}/{tot/1e6:.0f} M punkter, '
                  f'traffar hittills: {hits/1e6:.2f} M', end='', flush=True)
    print()
    if not xs:
        return None
    ii = np.concatenate(chunk_scan._is); chunk_scan._is=[]
    return (np.concatenate(xs), np.concatenate(ys),
            np.concatenate(zs), np.concatenate(cs), ii)

def process_laz(path, outdir, use_osm, keys, bbox=None):
    print(f'  läser {os.path.basename(path)} ...', flush=True)
    pts = load_points(path, bbox)
    if pts is None or len(pts[0]) == 0:
        print('    (utanför bbox, hoppar över)'); return
    x, y, z, cls, inten = pts
    print(f'    {len(x):,} punkter i utsnittet'.replace(',',' '))
    if len(x) < 50000:
        print('    VARNING: misstänkt få punkter - kontrollera bbox mot filens utbredning ovan')
    from collections import Counter
    cc = Counter(cls.tolist()[:200000])
    print('    klasser (urval):', dict(sorted(cc.items())))

    e0 = math.floor(x.min() / TILE) * TILE
    n0 = math.floor(y.min() / TILE) * TILE
    n_top = math.ceil((y.max() + 1) / TILE) * TILE
    W = math.ceil((x.max() + 1 - e0) / TILE) * TILE
    H = n_top - n0
    col = np.clip((x - e0).astype(np.int64), 0, W - 1)
    row = np.clip((n_top - 1 - np.floor(y)).astype(np.int64), 0, H - 1)
    flat = row * W + col

    gsum = np.zeros(W * H); gcnt = np.zeros(W * H)
    gm = np.isin(cls, GROUND_CLS)
    np.add.at(gsum, flat[gm], z[gm]); np.add.at(gcnt, flat[gm], 1)
    dtm = np.full(W * H, np.nan)
    dtm[gcnt > 0] = gsum[gcnt > 0] / gcnt[gcnt > 0]
    dtm = fill_nan(dtm.reshape(H, W))

    om = np.isin(cls, OBJECT_CLS)
    objmax = np.full(W * H, -np.inf)
    np.maximum.at(objmax, flat[om], z[om])
    objmax = objmax.reshape(H, W)
    objmax[np.isinf(objmax)] = np.nan
    objmin = np.full(W * H, np.inf)
    np.minimum.at(objmin, flat[om], z[om])
    objmin = objmin.reshape(H, W)
    objmin[np.isinf(objmin)] = np.nan

    if use_osm:
        print('    hämtar byggnadsfotavtryck (Overpass) ...', flush=True)
        bmask = rasterize_mask(fetch_buildings(e0, n0, e0 + W, n_top), e0, n_top, W, H)
    else:
        bmask = np.zeros((H, W), dtype=bool)

    hard = dtm.copy()
    bm = bmask & ~np.isnan(objmax)
    hard[bm] = np.maximum(hard[bm], objmax[bm])

    veg = np.zeros((H, W))
    vm = ~bmask & ~np.isnan(objmax) & (objmax - dtm >= VEG_MIN)
    veg[vm] = objmax[vm] - hard[vm]

    # Punkt 1: brusfilter - kapa spikar (antenner, fåglar) i hård yta och kronor
    hard = despike(hard, 3.0)
    veg = despike(veg, 4.0)
    # Konfetti: isolerade låga vegetationspixlar (ris/buskage-brus) tas bort
    vp = np.pad((veg > 0).astype(np.int8), 1)
    nbc = vp[1:-1, :-2] + vp[1:-1, 2:] + vp[:-2, 1:-1] + vp[2:, 1:-1]
    veg[(nbc == 0) & (veg < 5)] = 0.0

    # Kronbas: lägsta vegetationsretur, robustgjord med 3x3-median (punkt 3)
    base = np.zeros((H, W))
    bm2 = (veg > 0) & vm & ~np.isnan(objmin)
    base[bm2] = np.clip(objmin[bm2] - hard[bm2], 0, None)
    bmed = median3(np.where(veg > 0, base, np.nan))
    base = np.where(veg > 0, np.nan_to_num(np.fmin(bmed, veg * 0.9)), 0.0)

    # Punkt 2: byggnadskanal - flagga + höjd över mark (för skarpa 3D-väggar)
    bflag = bmask & ~np.isnan(hard) & ~np.isnan(dtm) & (hard - dtm >= 2.0)
    bh = np.where(bflag, np.clip(hard - dtm, 0, 127), 0.0)

    hard[np.isnan(dtm)] = np.nan  # utanför laserdata = nodata

    # Punkt 12: intensitetstextur (svartvit "flygfoto"-fallback tills orto finns)
    isum = np.zeros(W * H); icnt = np.zeros(W * H)
    np.add.at(isum, flat, inten); np.add.at(icnt, flat, 1)
    imean = np.full(W * H, np.nan)
    imean[icnt > 0] = isum[icnt > 0] / icnt[icnt > 0]
    imean = imean.reshape(H, W)
    ok = ~np.isnan(imean)
    if ok.any():
        lo, hi = np.percentile(imean[ok], [2, 98])
        itex = np.clip((imean - lo) / max(1e-9, hi - lo) * 255, 0, 255)
        itex = np.nan_to_num(itex).astype(np.uint8)
    else:
        itex = np.zeros((H, W), np.uint8)

    for tn in range(n0, n_top, TILE):
        for te in range(e0, e0 + W, TILE):
            r0 = n_top - (tn + TILE); c0 = te - e0
            th = hard[r0:r0+TILE, c0:c0+TILE]
            tv = veg[r0:r0+TILE, c0:c0+TILE]
            tb = base[r0:r0+TILE, c0:c0+TILE]
            tf = bflag[r0:r0+TILE, c0:c0+TILE]
            tbh = bh[r0:r0+TILE, c0:c0+TILE]
            if np.all(np.isnan(th)):
                continue
            key = f'{te}_{tn}'
            merge_into(os.path.join(outdir, key + '.png'), th, tv, tb, tf, tbh)
            tx = os.path.join(outdir, f'tex_{key}.jpg')
            if not os.path.exists(tx):   # skriv inte över ev. ortotextur
                Image.fromarray(itex[r0:r0+TILE, c0:c0+TILE]).convert('RGB').resize(
                    (TILE*2, TILE*2), Image.BILINEAR).save(tx, quality=80)
            keys.add(key)

# ---------------- Steg 2: SBK trädkronsraster ersätter laser-vegetation ----------------
def apply_sbk(sbk_dir, outdir, keys):
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    tifs = sorted(glob.glob(os.path.join(sbk_dir, '*.tif')) +
                  glob.glob(os.path.join(sbk_dir, '*.tiff')))
    if not tifs:
        print('VARNING: inga GeoTIFF hittades i', sbk_dir); return
    print(f'Steg 2: SBK trädkronor, {len(tifs)} raster ...')
    srcs = [(rasterio.open(p),) for p in tifs]
    vrts = [WarpedVRT(s[0], crs='EPSG:3006', resampling=Resampling.max) for s in srcs]
    for key in sorted(keys):
        te, tn = map(int, key.split('_'))
        crown = np.zeros((TILE, TILE))
        found = False
        for vrt in vrts:
            b = vrt.bounds
            if te + TILE < b.left or te > b.right or tn + TILE < b.bottom or tn > b.top:
                continue
            w = from_bounds(te, tn, te + TILE, tn + TILE, vrt.transform)
            d = vrt.read(1, window=w, out_shape=(TILE, TILE),
                         boundless=True, fill_value=0,
                         resampling=Resampling.max).astype(np.float64)
            nod = vrt.nodata
            if nod is not None:
                d[d == nod] = 0
            crown = np.maximum(crown, d)
            found = True
        if not found:
            continue
        path = os.path.join(outdir, key + '.png')
        hard, _lasveg = decode_tile(np.array(Image.open(path)))
        veg = np.where((crown > 0) & ~np.isnan(hard),
                       np.clip(crown - hard, 0, None), 0.0)
        veg[veg < VEG_MIN] = 0.0
        Image.fromarray(encode_tile(hard, veg)).save(path, optimize=True)
        # OBS: SBK-rastret saknar kronbas - basfilen från laserpassagen behålls
    for v in vrts: v.close()
    for s in srcs: s[0].close()

# ---------------- main ----------------
def apply_orto(orto_dir, outdir, keys):
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    tifs = sorted(glob.glob(os.path.join(orto_dir, '*.tif')) +
                  glob.glob(os.path.join(orto_dir, '*.tiff')))
    if not tifs:
        print('VARNING: inga ortofoto-GeoTIFF i', orto_dir); return
    print(f'Ortofoto: {len(tifs)} raster -> texturtiles (0,5 m/px) ...')
    P2 = TILE * 2
    srcs = [rasterio.open(p) for p in tifs]
    vrts = [WarpedVRT(s0, crs='EPSG:3006', resampling=Resampling.bilinear) for s0 in srcs]
    for key in sorted(keys):
        te, tn = map(int, key.split('_'))
        img = np.zeros((P2, P2, 3), dtype=np.uint8)
        found = False
        for vrt in vrts:
            b = vrt.bounds
            if te+TILE < b.left or te > b.right or tn+TILE < b.bottom or tn > b.top:
                continue
            w = from_bounds(te, tn, te+TILE, tn+TILE, vrt.transform)
            nb = min(3, vrt.count)
            d = vrt.read(list(range(1, nb+1)), window=w, out_shape=(nb, P2, P2),
                         boundless=True, fill_value=0)
            d = np.moveaxis(d, 0, -1)
            if nb == 1: d = np.repeat(d, 3, axis=-1)
            m = d.any(axis=-1)
            img[m] = d[m][..., :3]
            found = True
        if found:
            Image.fromarray(img).save(os.path.join(outdir, f'tex_{key}.jpg'), quality=82)
    for v in vrts: v.close()
    for s0 in srcs: s0.close()

def main():
    ap = argparse.ArgumentParser(description='Soldyrkaren: LAZ (+SBK) -> höjdtiles')
    ap.add_argument('--laz', required=True, help='mapp med .laz/.las-filer (EPSG:3006)')
    ap.add_argument('--sbk', help='mapp med SBK Trädkronehöjd GeoTIFF (valfritt)')
    ap.add_argument('--orto', help='mapp med ortofoto-GeoTIFF -> texturtiles (valfritt)')
    ap.add_argument('--out', default='tiles', help='utdatamapp (default: tiles)')
    ap.add_argument('--bbox', nargs=4, type=float, metavar=('EMIN','NMIN','EMAX','NMAX'),
                    help='begränsa till område i SWEREF99 TM (rekommenderas för 10 km COPC-rutor)')
    ap.add_argument('--helskanning', action='store_true',
                    help='tvinga långsam helskanning istället för COPC-nodval (felsökning)')
    ap.add_argument('--no-osm', action='store_true',
                    help='hoppa över byggnadsmask från OSM (allt högt blir vegetation!)')
    a = ap.parse_args()

    global SNABB
    SNABB = not a.helskanning
    files = sorted(glob.glob(os.path.join(a.laz, '*.la[sz]')))
    if not files:
        sys.exit('Inga .laz/.las-filer i ' + a.laz)
    os.makedirs(a.out, exist_ok=True)

    keys = set()
    print(f'Steg 1: {len(files)} laserfiler ...')
    for f in files:
        process_laz(f, a.out, not a.no_osm, keys, a.bbox)

    if a.sbk:
        apply_sbk(a.sbk, a.out, keys)
    else:
        print('Steg 2 hoppas över (ingen --sbk angiven) – laser-vegetation används.')

    if a.orto:
        apply_orto(a.orto, a.out, keys)

    idx = {'tileSize': TILE, 'res': 1, 'h0': H0, 'scale': HSCALE, 'fmt': 2,
           'vegStep': 0.5, 'crs': 'EPSG:3006',
           'vegSource': 'SBK Trädkronehöjd 2022' if a.sbk else 'Lantmäteriet laserdata',
           'tiles': sorted(keys)}
    with open(os.path.join(a.out, 'index.json'), 'w') as f:
        json.dump(idx, f)
    print(f'Klart: {len(keys)} tiles i {a.out}/ + index.json')

if __name__ == '__main__':
    main()
