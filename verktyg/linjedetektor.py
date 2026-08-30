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

    # --- kategorisering ------------------------------------------------
    for r in rader:
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
<title>Kandidatkoll</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>html,body,#map{height:100%;margin:0}
.pop{font-family:ui-monospace,monospace;font-size:12px;white-space:pre}</style>
</head><body><div id="map"></div><script>
const KAND=__DATA__;
const APP='__APP__';
const FARG={"KRAN?":"#d43a2a","STUMP?":"#e08a12","LEDNING?":"#7b4fd4",
"KRAFTLEDNING":"#4f6bd4","STOLPE":"#4f9ad4","TRAD":"#3f8a4f","klump":"#8a8a8a"};
const map=L.map('map');
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,
  attribution:'&copy; OpenStreetMap'}).addTo(map);
const grupper={},synlig={"KRAN?":1,"STUMP?":1,"LEDNING?":1};
for(const k of KAND){
  const g=grupper[k.kat]??(grupper[k.kat]=L.featureGroup());
  const m=L.circleMarker([k.lat,k.lon],{radius:7,color:FARG[k.kat]||'#888',
    weight:2,fillOpacity:.5});
  m.bindPopup('<div class="pop"><b>'+k.kat+'</b>  topp '+k.topp+' m\\n'+
    k.n+' px  '+k.lang+'x'+k.bred+' m  ['+k.kanal+']  takmed '+k.takmed+
    '\\nE '+k.E+'  N '+k.N+'\\n\\n{"namn": "GRANSKA MIG", "E": '+k.E+
    ', "N": '+k.N+', "r": '+k.radie+', "minh": '+k.minh+'}\\n\\n'+
    '<a href="'+APP+'#3d='+k.E+','+k.N+','+k.lat+','+k.lon+
    '" target="_blank">3D-vyn har</a>   '+
    '<a href="https://maps.google.com/?q='+k.lat+','+k.lon+
    '&t=k" target="_blank">Google flygfoto</a></div>');
  m.addTo(g);
}
const alla=[];
for(const[kat,g]of Object.entries(grupper)){
  if(synlig[kat])g.addTo(map);
  alla.push(g);
}
L.control.layers(null,Object.fromEntries(Object.entries(grupper).map(
  ([k,g])=>[k+' ('+g.getLayers().length+')',g])),{collapsed:false}).addTo(map);
const b=L.featureGroup(alla).getBounds();
if(b.isValid())map.fitBounds(b.pad(.05)); else map.setView([59.31,18.06],12);
</script></body></html>"""

if __name__ == '__main__':
    main()
