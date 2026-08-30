#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
linjedetektor.py v2 - sveper alla tiles efter avvikande hoga strukturer och
KLASSIFICERAR dem innan manniskan tar over. Foreslar bara - kapar ingenting.

  py verktyg\\linjedetektor.py --tiles tiles --csv kandidater.csv --karta kandidater.html

Kategorier (i prioritetsordning):
  KRAFTLEDNING  linje som ligger inom 40 m fran en OSM power=line/aerialway
  LEDNING?      kedja av kollinjara segment, sammanlagd strackning >= 180 m
                (eller ett ensamt segment >= 140 m) utan OSM-traff
  TRAD          veg-only linje med topp < 33 m - trad tar slut dar i Sverige
  KRAN?         ovriga linjer - smala, langa, kraftigt forhojd
  STUMP?        sma mycket hoga klumpar - kranrester eller akta master
  klump         kompakta kluster - stans hoga hus och trad, ingen atgard

OSM-ledningarna hamtas via Overpass (samma speglar och failover som
preprocess) och cachas i ledningscache.json. Faller alla speglar
klassificeras utan OSM-stod och en varning skrivs.

Meddelanden utan aao for att slippa teckenkrangel i konsolen.
"""
import argparse, json, math, os, ssl, sys, time, urllib.request
from collections import deque
import numpy as np
from PIL import Image

TILE = 512

# ---------------- SWEREF99 TM <-> WGS84 (Gauss-Kruger) ----------------
_a = 6378137.0; _f = 1 / 298.257222101
_e2 = _f * (2 - _f); _n = _f / (2 - _f)
_ah = _a / (1 + _n) * (1 + _n * _n / 4 + _n ** 4 / 64)
_k0 = 0.9996; _FE = 500000.0; _lon0 = math.radians(15.0)

def till_wgs84(E, N):
    """Numerisk invers av till_sweref - kan inte glida ifran framatriktningen."""
    lat, lon = 59.3, 18.0
    for _ in range(12):
        E2, N2 = till_sweref(lat, lon)
        lat += (N - N2) / 111320.0
        lon += (E - E2) / (111320.0 * math.cos(math.radians(lat)))
    return lat, lon

def till_sweref(lat, lon):
    A = _e2; B = (5*_e2**2 - _e2**3)/6
    C = (104*_e2**3 - 45*_e2**4)/120; D = 1237*_e2**4/1260
    b1 = _n/2 - 2*_n**2/3 + 5*_n**3/16 + 41*_n**4/180
    b2 = 13*_n**2/48 - 3*_n**3/5 + 557*_n**4/1440
    b3 = 61*_n**3/240 - 103*_n**4/140
    b4 = 49561*_n**4/161280
    phi = math.radians(lat); si = math.sin(phi)
    ps = phi - si*math.cos(phi)*(A + B*si*si + C*si**4 + D*si**6)
    dl = math.radians(lon) - _lon0
    xi = math.atan2(math.tan(ps), math.cos(dl))
    eta = math.atanh(math.cos(ps) * math.sin(dl))
    N = xi; E = eta
    for j, bj in enumerate((b1, b2, b3, b4), 1):
        N += bj * math.sin(2*j*xi) * math.cosh(2*j*eta)
        E += bj * math.cos(2*j*xi) * math.sinh(2*j*eta)
    return _k0*_ah*E + _FE, _k0*_ah*N

# ---------------- OSM-ledningar via Overpass --------------------------
SPEGLAR = ['https://overpass-api.de/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter',
           'https://overpass.private.coffee/api/interpreter']

def hamta_ledningar(bbox, cachefil='ledningscache.json'):
    """bbox i SWEREF (emin,nmin,emax,nmax) -> lista av polylinjer i SWEREF."""
    if os.path.exists(cachefil):
        try:
            d = json.load(open(cachefil, encoding='utf-8'))
            cb = d.get('bbox', [0, 0, 0, 0])
            if (cb[0] <= bbox[0] and cb[1] <= bbox[1] and
                    cb[2] >= bbox[2] and cb[3] >= bbox[3]):
                print(f'  ledningar ur cache: {len(d["linjer"])} st')
                return [np.array(l) for l in d['linjer']]
        except Exception:
            pass
    la0, lo0 = till_wgs84(bbox[0], bbox[1])
    la1, lo1 = till_wgs84(bbox[2], bbox[3])
    q = ('[out:json][timeout:120];('
         f'way["power"~"^(line|minor_line)$"]({la0:.5f},{lo0:.5f},{la1:.5f},{lo1:.5f});'
         f'way["aerialway"]({la0:.5f},{lo0:.5f},{la1:.5f},{lo1:.5f});'
         ');out geom;')
    ctx = ssl.create_default_context()
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT   # foretagsproxy saknar ofta AKI
    for runda in range(3):
        for url in SPEGLAR:
            try:
                req = urllib.request.Request(
                    url, data=('data=' + urllib.parse.quote(q)).encode(),
                    headers={'User-Agent': 'hitta-uteserveringen/linjedetektor'})
                with urllib.request.urlopen(req, timeout=150, context=ctx) as r:
                    d = json.loads(r.read())
                linjer = []
                for el in d.get('elements', []):
                    g = el.get('geometry') or []
                    if len(g) >= 2:
                        linjer.append([till_sweref(p['lat'], p['lon']) for p in g])
                json.dump({'bbox': list(bbox),
                           'linjer': [[list(p) for p in l] for l in linjer]},
                          open(cachefil, 'w', encoding='utf-8'))
                print(f'  {len(linjer)} kraftledningar/linbanor fran OSM '
                      f'({url.split("/")[2]})')
                return [np.array(l) for l in linjer]
            except Exception as e:
                print(f'  ({url.split("/")[2]}: {e})')
        time.sleep(10 * (runda + 1))
    print('  VARNING: ingen Overpass-spegel svarade - klassificerar utan OSM.')
    return []

def nara_ledning(E, N, ledningar, tol=40.0):
    p = np.array([E, N])
    for l in ledningar:
        # grov gallring pa bbox forst
        if (E < l[:, 0].min() - tol or E > l[:, 0].max() + tol or
                N < l[:, 1].min() - tol or N > l[:, 1].max() + tol):
            continue
        for i in range(len(l) - 1):
            a, b = l[i], l[i + 1]
            ab = b - a; t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-9), 0, 1)
            if np.linalg.norm(p - (a + t * ab)) <= tol:
                return True
    return False

# ---------------- tiles -----------------------------------------------
def las_tile(tdir, key):
    d = np.array(Image.open(os.path.join(tdir, key + '.png')).convert('RGB'))
    veg = d[..., 2].astype(np.float32) * 0.5
    bp = os.path.join(tdir, key + '_bas.png')
    if os.path.exists(bp):
        b = np.array(Image.open(bp).convert('RGB'))
        return veg, b[..., 1] > 127, b[..., 2].astype(np.float32) * 0.5
    return veg, np.zeros(veg.shape, bool), np.zeros_like(veg)

# ---------------- huvudflode ------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tiles', default='tiles')
    ap.add_argument('--minpx', type=int, default=8)
    ap.add_argument('--csv', help='skriv alla kandidater till CSV')
    ap.add_argument('--karta', help='skriv granskningskarta (HTML)')
    ap.add_argument('--visa-trad', action='store_true',
                    help='skriv aven TRAD-kategorin i konsolen')
    ap.add_argument('--friade', default='verktyg/friade.json',
                    help='JSON med granskade OK-objekt som ska tystas')
    ap.add_argument('--app', default='https://vlassl.github.io/hitta-uteserveringen/',
                    help='bas-URL till appen for 3D-lankarna i kartan')
    ap.add_argument('--utan-osm', action='store_true',
                    help='hoppa over Overpass-anropet')
    a = ap.parse_args()

    ip = os.path.join(a.tiles, 'index.json')
    if os.path.exists(ip):
        idx = json.load(open(ip, encoding='utf-8'))
        keys = [k if isinstance(k, str) else k.get('key') for k in idx['tiles']]
    else:
        keys = sorted(f[:-4] for f in os.listdir(a.tiles)
                      if f.endswith('.png') and '_bas' not in f and f[0].isdigit())
    print(f'{len(keys)} tiles att svepa i {a.tiles}/')

    punkter = {}
    KAN_B, KAN_V = 1, 2
    emin = nmin = 1e12; emax = nmax = -1e12
    for i, key in enumerate(keys, 1):
        try:
            e0, n0 = (int(v) for v in key.split('_'))
        except ValueError:
            continue
        emin = min(emin, e0); nmin = min(nmin, n0)
        emax = max(emax, e0 + TILE); nmax = max(nmax, n0 + TILE)
        ntop = n0 + TILE - 1
        try:
            veg, bflag, bh = las_tile(a.tiles, key)
        except FileNotFoundError:
            continue
        med = float(np.median(bh[bflag])) if bflag.sum() > 200 else 0.0
        mb = bflag & (bh > max(20.0, med + 15.0))
        mv = veg > max(25.0, med + 12.0)
        for mask, kan, vals in ((mb, KAN_B, bh), (mv, KAN_V, veg)):
            rs, cs = np.nonzero(mask)
            for r, c in zip(rs.tolist(), cs.tolist()):
                p = (e0 + c, ntop - r)
                g = punkter.get(p)
                v = float(vals[r, c])
                if g is None:
                    punkter[p] = [v, kan, med]
                else:
                    g[0] = max(g[0], v); g[1] |= kan
        if i % 100 == 0:
            print(f'  {i}/{len(keys)} tiles ...')
    print(f'{len(punkter)} pixlar over troskeln')

    # klustring over tilegranser
    kvar = set(punkter); kluster = []
    while kvar:
        s0 = kvar.pop(); ko = deque([s0]); px = [s0]
        while ko:
            E, N = ko.popleft()
            for dE in (-1, 0, 1):
                for dN in (-1, 0, 1):
                    q = (E + dE, N + dN)
                    if q in kvar:
                        kvar.remove(q); ko.append(q); px.append(q)
        if len(px) >= a.minpx:
            kluster.append(px)

    rader = []
    for px in kluster:
        E = np.array([p[0] for p in px], float)
        N = np.array([p[1] for p in px], float)
        cE, cN = E.mean(), N.mean()
        if len(px) > 2:
            w, v = np.linalg.eigh(np.cov(np.stack([E - cE, N - cN])))
            lang = 4 * np.sqrt(max(w[-1], 1e-9))
            bred = 4 * np.sqrt(max(w[0], 1e-9))
            rikt = v[:, -1]
            az = math.degrees(math.atan2(rikt[0], rikt[1])) % 180
            t = (E - cE) * rikt[0] + (N - cN) * rikt[1]
            p1 = (cE + t.min() * rikt[0], cN + t.min() * rikt[1])
            p2 = (cE + t.max() * rikt[0], cN + t.max() * rikt[1])
        else:
            lang = bred = 1.0; az = 0.0; p1 = p2 = (cE, cN)
        maxh = max(punkter[p][0] for p in px)
        kanaler = 0
        for p in px:
            kanaler |= punkter[p][1]
        med = float(np.median([punkter[p][2] for p in px]))
        rader.append(dict(
            n=len(px), cE=cE, cN=cN, p1=p1, p2=p2,
            E0=int(E.min()), E1=int(E.max()), N0=int(N.min()), N1=int(N.max()),
            lang=lang, bred=bred, az=az, maxh=maxh, takmed=med,
            kanal={1: 'bygg', 2: 'veg', 3: 'bygg+veg'}[kanaler],
            radie=float(np.sqrt(((E-cE)**2 + (N-cN)**2).max())),
            grans=(int(E.min()) // TILE != int(E.max()) // TILE or
                   int(N.min()) // TILE != int(N.max()) // TILE),
            linje=(lang >= 18 and bred <= 16 and lang / max(bred, .1) >= 3.5)))

    # --- stråkkedjning av linjer --------------------------------------
    lin = [r for r in rader if r['linje']]
    far = list(range(len(lin)))
    def hitta(x):
        while far[x] != x:
            far[x] = far[far[x]]; x = far[x]
        return x
    for i in range(len(lin)):
        for j in range(i + 1, len(lin)):
            da = abs(lin[i]['az'] - lin[j]['az']); da = min(da, 180 - da)
            if da > 20:
                continue
            gap = min(math.dist(lin[i][e1], lin[j][e2])
                      for e1 in ('p1', 'p2') for e2 in ('p1', 'p2'))
            if gap > 80:
                continue
            far[hitta(i)] = hitta(j)
    grupp = {}
    for i in range(len(lin)):
        grupp.setdefault(hitta(i), []).append(lin[i])
    for medl in grupp.values():
        pts = [m[e] for m in medl for e in ('p1', 'p2')]
        span = max(math.dist(pa, pb) for pa in pts for pb in pts) if len(pts) > 1 else 0
        korridor = (len(medl) >= 2 and span >= 180) or \
                   (len(medl) == 1 and medl[0]['lang'] >= 140)
        for m in medl:
            m['korridor'] = korridor; m['span'] = span

    # --- OSM-ledningar -------------------------------------------------
    ledningar = []
    if not a.utan_osm:
        print('Hamtar kraftledningar/linbanor fran OSM ...')
        ledningar = hamta_ledningar((emin, nmin, emax, nmax))

    # --- friade: granskade och godkanda objekt tystas -------------------
    friade = []
    if os.path.exists(a.friade):
        try:
            d = json.load(open(a.friade, encoding='utf-8'))
            friade = d.get('friade', d if isinstance(d, list) else [])
            print(f'{len(friade)} friade objekt lasta fran {a.friade}')
        except Exception as e:
            print(f'VARNING: kunde inte lasa {a.friade}: {e}')

    def friad(r):
        for f in friade:
            if math.dist((r['cE'], r['cN']),
                         (float(f['E']), float(f['N']))) <= float(f.get('r', 30)):
                return True
        return False

    # --- kategorisering ------------------------------------------------
    for r in rader:
        if friad(r):
            r['kat'] = 'FRIAD'
            continue
        if r['linje']:
            if ledningar and nara_ledning(r['cE'], r['cN'], ledningar):
                r['kat'] = 'KRAFTLEDNING'
            elif r.get('korridor'):
                r['kat'] = 'LEDNING?'
            elif r['kanal'] == 'veg' and r['maxh'] < 33:
                r['kat'] = 'TRAD'
            else:
                r['kat'] = 'KRAN?'
        elif r['n'] <= 40 and r['maxh'] >= max(35.0, r['takmed'] + 25):
            r['kat'] = 'STOLPE' if (ledningar and
                nara_ledning(r['cE'], r['cN'], ledningar)) else 'STUMP?'
        else:
            r['kat'] = 'klump'

    def skriv(kat, rubrik, forslag=True, maxrad=999):
        urval = sorted((r for r in rader if r['kat'] == kat),
                       key=lambda r: -r['maxh'])
        print(f'\n=== {len(urval)} {rubrik} ===')
        for r in urval[:maxrad]:
            print(f'  {r["n"]:4d} px  {r["lang"]:4.0f}x{r["bred"]:4.1f} m  '
                  f'az {r["az"]:5.1f}  topp {r["maxh"]:5.1f} m  '
                  f'takmed {r["takmed"]:4.1f}  [{r["kanal"]}]  '
                  f'E {r["E0"]}-{r["E1"]} N {r["N0"]}-{r["N1"]}')
            if forslag:
                print(f'        {{"namn": "GRANSKA MIG", "E": {r["cE"]:.0f}, '
                      f'"N": {r["cN"]:.0f}, "r": {int(r["radie"]) + 8}, '
                      f'"minh": {max(int(r["takmed"]) + 10, int(r["maxh"]) - 20)}}}')
        if len(urval) > maxrad:
            print(f'  ... och {len(urval) - maxrad} till (se CSV/karta)')
        return len(urval)

    skriv('KRAN?', 'KRANKANDIDATER - borja har')
    skriv('STUMP?', 'STUMP? - kranrester eller akta master, granska')
    skriv('LEDNING?', 'LEDNING? - kollinjara strak utan OSM-traff', maxrad=30)
    skriv('KRAFTLEDNING', 'KRAFTLEDNING (OSM-bekraftad) - kapas enligt policy',
          maxrad=15)
    skriv('STOLPE', 'STOLPE (kompakt vid OSM-ledning)', maxrad=10)
    if a.visa_trad:
        skriv('TRAD', 'TRAD - veg under 33 m, rors ej', forslag=False, maxrad=30)
    else:
        n = sum(1 for r in rader if r['kat'] == 'TRAD')
        print(f'\n({n} TRAD-linjer filtrerade - visa med --visa-trad)')
    n = sum(1 for r in rader if r['kat'] == 'FRIAD')
    if n:
        print(f'({n} FRIADE - granskade och godkanda, tystade)')
    n = sum(1 for r in rader if r['kat'] == 'klump')
    print(f'({n} kompakta klumpar - stans hoga hus och trad, se CSV)')

    if a.csv:
        import csv as cm
        with open(a.csv, 'w', newline='', encoding='utf-8') as f:
            w = cm.writer(f, delimiter=';')
            w.writerow(['kategori', 'px', 'langd_m', 'bredd_m', 'azimut',
                        'topp_m', 'takmedian_m', 'kanal', 'E_min', 'E_max',
                        'N_min', 'N_max', 'E_centrum', 'N_centrum'])
            for r in sorted(rader, key=lambda r: (r['kat'], -r['maxh'])):
                w.writerow([r['kat'], r['n'], round(r['lang'], 1),
                            round(r['bred'], 1), round(r['az'], 1), r['maxh'],
                            r['takmed'], r['kanal'], r['E0'], r['E1'],
                            r['N0'], r['N1'], round(r['cE']), round(r['cN'])])
        print(f'CSV skriven: {a.csv}')

    if a.karta:
        kand = []
        for r in rader:
            if r['kat'] == 'klump' and r['maxh'] < r['takmed'] + 30:
                continue                      # begransa klumparna pa kartan
            la, lo = till_wgs84(r['cE'], r['cN'])
            kand.append(dict(lat=round(la, 6), lon=round(lo, 6),
                             kat=r['kat'], n=r['n'], topp=r['maxh'],
                             lang=round(r['lang']), bred=round(r['bred'], 1),
                             az=round(r['az']), grans=int(r['grans']),
                             takmed=r['takmed'], kanal=r['kanal'],
                             E=round(r['cE']), N=round(r['cN']),
                             radie=int(r['radie']) + 8,
                             minh=max(int(r['takmed']) + 10,
                                      int(r['maxh']) - 20)))
        html = KARTMALL.replace('__DATA__', json.dumps(kand, ensure_ascii=False))
        html = html.replace('__APP__', a.app)
        open(a.karta, 'w', encoding='utf-8').write(html)
        print(f'Karta skriven: {a.karta} ({len(kand)} markorer)')

KARTMALL = """<!DOCTYPE html><html lang="sv"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Granskning av kandidater</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--ram:#d8d3c8;--bg:#f6f4ef;--ink:#2a2a26}
html,body{height:100%;margin:0;font:14px/1.4 system-ui,sans-serif;color:var(--ink);background:var(--bg)}
header{display:flex;gap:14px;align-items:center;padding:7px 12px;border-bottom:1px solid var(--ram);background:#fff;flex-wrap:wrap}
header b{font-size:15px}
#stat{color:#666}
#filt label{margin-right:9px;cursor:pointer;white-space:nowrap}
button{font:inherit;padding:5px 12px;border:1px solid var(--ram);border-radius:7px;background:#fff;cursor:pointer}
button:hover{background:#f0ede6}
#layout{display:grid;height:calc(100% - 46px);
  grid-template-columns:320px 1fr 1fr;grid-template-rows:1fr 1fr;gap:6px;padding:6px;box-sizing:border-box}
#lista{grid-row:1/3;overflow-y:auto;background:#fff;border:1px solid var(--ram);border-radius:8px}
.rad{padding:7px 10px;border-bottom:1px solid #eee;cursor:pointer;display:flex;gap:8px;align-items:baseline}
.rad:hover{background:#f4f1ea}
.rad.vald{background:#ece7db}
.rad.klar{opacity:.45}
.rad .kat{font-size:11px;font-weight:600;padding:1px 6px;border-radius:5px;color:#fff}
.rad .hojd{margin-left:auto;color:#666;font-variant-numeric:tabular-nums}
.rad .flagga{font-size:13px}
.panel{position:relative;background:#fff;border:1px solid var(--ram);border-radius:8px;overflow:hidden;min-height:0}
.panel .titel{position:absolute;top:6px;left:8px;z-index:800;background:rgba(255,255,255,.9);
  padding:2px 9px;border-radius:6px;font-size:12px;font-weight:600}
#map{height:100%}
iframe{width:100%;height:100%;border:0}
#pbeslut{padding:12px;overflow-y:auto}
#info{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;background:#f6f4ef;
  border-radius:7px;padding:9px;margin:8px 0}
#komm{width:100%;box-sizing:border-box;font:inherit;padding:7px;border:1px solid var(--ram);border-radius:7px;min-height:54px}
.knappar{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}
.knappar button{flex:1;padding:10px 6px;font-weight:600;border-width:2px}
#bKvar{border-color:#3f8a4f;color:#2c6238}
#bBort{border-color:#d43a2a;color:#a52a1d}
#bVanta{border-color:#e08a12;color:#a5650a}
.genv{color:#888;font-size:12px;margin-top:8px}
</style></head><body>
<header><b>Granskning</b><span id="stat"></span><span id="filt"></span>
<button id="bExport">Exportera beslut</button></header>
<div id="layout">
  <aside id="lista"></aside>
  <div class="panel" style="grid-column:2;grid-row:1"><div class="titel">Kandidatkarta</div><div id="map"></div></div>
  <div class="panel" style="grid-column:3;grid-row:1"><div class="titel">3D-vyn (appen)</div><iframe id="if3d"></iframe></div>
  <div class="panel" style="grid-column:2;grid-row:2"><div class="titel">Google flygfoto</div><iframe id="ifg" referrerpolicy="no-referrer-when-downgrade"></iframe></div>
  <div class="panel" id="pbeslut" style="grid-column:3;grid-row:2">
    <b id="rubrik">Välj en kandidat i listan eller på kartan</b>
    <div id="info"></div>
    <textarea id="komm" placeholder="Kommentar (sparas med beslutet; skriv gärna vad det är)"></textarea>
    <div class="knappar">
      <button id="bKvar">&#10003; Äkta &ndash; kvar</button>
      <button id="bBort">&#10007; Artefakt &ndash; bort</button>
      <button id="bVanta">&#9208; Avvakta</button>
    </div>
    <div class="genv">Kortkommandon: 1 kvar &middot; 2 bort &middot; 3 avvakta &middot; n nästa oavgjorda</div>
  </div>
</div>
<script>
"use strict";
const KAND=__DATA__;
const APP='__APP__';
const FARG={"KRAN?":"#d43a2a","STUMP?":"#e08a12","LEDNING?":"#7b4fd4",
 "KRAFTLEDNING":"#4f6bd4","STOLPE":"#4f9ad4","TRAD":"#3f8a4f","FRIAD":"#9bb59b","klump":"#8a8a8a"};
const ORDN=["KRAN?","STUMP?","LEDNING?","KRAFTLEDNING","STOLPE","TRAD","FRIAD","klump"];
KAND.forEach(k=>{k.id=k.E+'_'+k.N;});
KAND.sort((a,b)=>ORDN.indexOf(a.kat)-ORDN.indexOf(b.kat)||b.topp-a.topp);

let beslut={};
try{beslut=JSON.parse(localStorage.getItem('granskning_v1')||'{}');}catch(_){}
function spara(){try{localStorage.setItem('granskning_v1',JSON.stringify(beslut));}
  catch(e){alert('Kunde inte spara lokalt: '+e);}}

const visa=new Set(["KRAN?","STUMP?","LEDNING?"]);
let vald=null;

const map=L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(map);
const mark={};
function symbol(k){
  const b=beslut[k.id];
  return {radius:vald&&vald.id===k.id?11:7,weight:vald&&vald.id===k.id?4:2,
    color:FARG[k.kat]||'#888',fillOpacity:b?(b.beslut==='avvakta'?.5:.12):.55,
    dashArray:b&&b.beslut==='avvakta'?'3 3':null};
}
function ritaMark(){
  for(const id in mark){map.removeLayer(mark[id]);delete mark[id];}
  for(const k of KAND){
    if(!visa.has(k.kat))continue;
    const m=L.circleMarker([k.lat,k.lon],symbol(k)).addTo(map);
    m.on('click',()=>valj(k));
    mark[k.id]=m;
  }
}
function badge(k){
  const b=beslut[k.id];
  if(!b)return'';
  return {kvar:'&#10003;',bort:'&#10007;',avvakta:'&#9208;'}[b.beslut]||'';
}
function ritaLista(){
  const el=document.getElementById('lista');el.innerHTML='';
  for(const k of KAND){
    if(!visa.has(k.kat))continue;
    const b=beslut[k.id];
    const d=document.createElement('div');
    d.className='rad'+(vald&&vald.id===k.id?' vald':'')+(b&&b.beslut!=='avvakta'?' klar':'');
    d.innerHTML='<span class="flagga">'+badge(k)+'</span>'+
      '<span class="kat" style="background:'+(FARG[k.kat]||'#888')+'">'+k.kat+'</span>'+
      '<span>'+k.lang+'&times;'+k.bred+' m</span>'+
      '<span class="hojd">'+k.topp+' m</span>';
    d.onclick=()=>valj(k);
    el.appendChild(d);
  }
  stat();
}
function stat(){
  const syns=KAND.filter(k=>visa.has(k.kat));
  const n={kvar:0,bort:0,avvakta:0};
  for(const k of syns){const b=beslut[k.id];if(b)n[b.beslut]=(n[b.beslut]||0)+1;}
  document.getElementById('stat').textContent=
    syns.length+' kandidater &middot; '.replace('&middot;','·')+
    n.kvar+' kvar · '+n.bort+' bort · '+n.avvakta+' avvakta';
}
function filterUI(){
  const el=document.getElementById('filt');
  for(const kat of ORDN){
    if(!KAND.some(k=>k.kat===kat))continue;
    const l=document.createElement('label');
    const c=document.createElement('input');c.type='checkbox';c.checked=visa.has(kat);
    c.onchange=()=>{c.checked?visa.add(kat):visa.delete(kat);ritaMark();ritaLista();};
    l.appendChild(c);l.append(' '+kat);
    el.appendChild(l);
  }
}
function valj(k){
  vald=k;
  map.setView([k.lat,k.lon],18);
  document.getElementById('if3d').src=APP+'#3d='+k.E+','+k.N+','+k.lat+','+k.lon;
  document.getElementById('ifg').src='https://maps.google.com/maps?q='+k.lat+','+k.lon+
    '&t=k&z=18&output=embed&hl=sv';
  document.getElementById('rubrik').textContent=k.kat+'  ·  topp '+k.topp+' m över mark';
  document.getElementById('info').textContent=
    k.n+' px  ·  '+k.lang+'×'+k.bred+' m  ·  azimut '+k.az+'°  ·  ['+k.kanal+']\\n'+
    'takmedian '+k.takmed+' m'+(k.grans?'  ·  KORSAR TILEGRÄNS':'')+'\\n'+
    'E '+k.E+'   N '+k.N+'\\n'+
    'förslag: {"namn": "...", "E": '+k.E+', "N": '+k.N+', "r": '+k.radie+', "minh": '+k.minh+'}';
  const b=beslut[k.id];
  document.getElementById('komm').value=b?b.kommentar||'':'';
  ritaMark();ritaLista();
}
function narmsta(){
  let bast=null,bd=1e18;
  for(const k of KAND){
    if(!visa.has(k.kat)||beslut[k.id]||k===vald)continue;
    const d=(k.E-vald.E)**2+(k.N-vald.N)**2;
    if(d<bd){bd=d;bast=k;}
  }
  return bast;
}
function bestam(typ){
  if(!vald)return;
  beslut[vald.id]={beslut:typ,kommentar:document.getElementById('komm').value.trim(),
    tid:new Date().toISOString(),kat:vald.kat,E:vald.E,N:vald.N,
    r:vald.radie,minh:vald.minh,topp:vald.topp};
  spara();
  const n=narmsta();
  if(n)valj(n);else{ritaMark();ritaLista();
    document.getElementById('rubrik').textContent='Inga oavgjorda kvar i valda kategorier.';}
}
document.getElementById('bKvar').onclick=()=>bestam('kvar');
document.getElementById('bBort').onclick=()=>bestam('bort');
document.getElementById('bVanta').onclick=()=>bestam('avvakta');
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT')return;
  if(e.key==='1')bestam('kvar');
  else if(e.key==='2')bestam('bort');
  else if(e.key==='3')bestam('avvakta');
  else if(e.key==='n'&&vald){const x=narmsta();if(x)valj(x);}
});
document.getElementById('bExport').onclick=()=>{
  const ut={exporterad:new Date().toISOString(),
    kommentar:'Granskningsbeslut fran kandidatkartan. bort -> artefakter.json, kvar -> friade.json.',
    artefakter:[],friade:[],avvakta:[]};
  for(const id in beslut){
    const b=beslut[id];
    const namn=(b.kommentar||('granskad '+b.kat)).slice(0,80);
    if(b.beslut==='bort')ut.artefakter.push({namn:namn,E:b.E,N:b.N,r:b.r,minh:b.minh,
      notering:'Granskad '+b.tid.slice(0,10)+', topp '+b.topp+' m. '+(b.kommentar||'')});
    else if(b.beslut==='kvar')ut.friade.push({namn:namn,E:b.E,N:b.N,r:b.r});
    else ut.avvakta.push({namn:namn,E:b.E,N:b.N,kommentar:b.kommentar||'',kat:b.kat});
  }
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([JSON.stringify(ut,null,1)],{type:'application/json'}));
  a.download='granskning.json';a.click();
};
filterUI();ritaMark();ritaLista();
const start=KAND.filter(k=>visa.has(k.kat)&&!beslut[k.id]);
if(start.length)valj(start[0]);
else{const b=L.featureGroup(Object.values(mark)).getBounds();
  if(b.isValid())map.fitBounds(b.pad(.05));else map.setView([59.31,18.06],12);}
</script></body></html>"""

if __name__ == '__main__':
    main()
