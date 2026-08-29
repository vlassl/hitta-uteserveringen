#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hamta_orto.py – laddar ner Ortofoto (COG GeoTIFF)
från Lantmäteriets STAC-API för ett valt område.

Användning (Aspudden är förifyllt som standard):
  pip install requests
  python hamta_orto.py --user DITT_SYSTEMKONTO --password DITT_LOSENORD

Annat område (bbox i WGS84: lon_min lat_min lon_max lat_max):
  python hamta_orto.py --user X --password Y --bbox 17.98 59.29 18.02 59.32

Om API-adressen skiljer sig från standarden, ange den:
  python hamta_orto.py --user X --password Y --api https://api.lantmateriet.se/stac-bild/v1
(Rätt adress står på produktens sida "Åtkomst och leverans" i Geotorget.)
"""
import argparse, getpass, os, re, sys, time
try:
    import requests
except ImportError:
    sys.exit("Kör först: pip install requests")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True, help='användarnamn för systemkontot (Geotorget)')
    ap.add_argument('--password', help='lösenord (utelämna så frågar skriptet dolt)')
    ap.add_argument('--api', default='https://api.lantmateriet.se/stac-bild/v1',
                    help='STAC-API:ets basadress (se Åtkomst och leverans i Geotorget)')
    ap.add_argument('--bbox', nargs=4, type=float,
                    default=[17.985, 59.298, 18.017, 59.315],   # Aspudden/Vapengatan 2 + marginal
                    help='lon_min lat_min lon_max lat_max (WGS84)')
    ap.add_argument('--out', default='orto', help='mapp för nedladdade filer')
    ap.add_argument('--coll', help='exakt kollektion, t.ex. orto-a2-2024 '
                    '(annars väljs nyaste för Stockholms län automatiskt)')
    ap.add_argument('--lan', default='a', help='länsbokstav, a=Stockholm (standard)')
    a = ap.parse_args()

    losen = a.password or getpass.getpass('Lösenord (syns inte): ')
    s = requests.Session()
    s.auth = (a.user, losen)
    os.makedirs(a.out, exist_ok=True)

    # 1) Lista kataloger (collections) och hitta laserdata skog
    r = s.get(a.api + '/collections', timeout=60)
    if r.status_code == 401:
        sys.exit('401: fel användarnamn/lösenord, eller behörighet till produkten saknas i Geotorget.')
    if r.status_code == 403:
        sys.exit('403: kontot saknar behörighet till produkten – beställ Laserdata Nedladdning, skog i Geotorget först.')
    r.raise_for_status()
    colls = [c['id'] for c in r.json().get('collections', [])]
    print('Kataloger i API:et:', ', '.join(colls) or '(inga)')
    # Kollektionerna heter orto-<län><variant>-<år>, t.ex. orto-a2-2024.
    # A = Stockholms län. Vi tar de NYASTE åren för valt län - att söka i
    # alla ~650 kollektioner ger 429 (Too Many Requests).
    if a.coll:
        lasercolls = [a.coll]
    else:
        pat = re.compile(r'^orto-' + re.escape(a.lan.lower()) + r'\d*-(\d{4})$')
        tr = []
        for c in colls:
            m = pat.match(c.lower())
            if m:
                tr.append((int(m.group(1)), c))
        tr.sort(reverse=True)
        lasercolls = [c for _, c in tr[:4]]       # fyra nyaste årgångarna
        if not lasercolls:
            sys.exit('Hittade ingen kollektion för län "%s". Ange --coll manuellt '
                     '(se listan ovan).' % a.lan)
    print('Söker i:', ', '.join(lasercolls))

    # 2) Sök items inom bbox
    hittade = []
    for coll in lasercolls:
        url = f'{a.api}/search'
        body = {'collections': [coll], 'bbox': a.bbox, 'limit': 100}
        r = None
        for forsok in range(4):
            r = s.post(url, json=body, timeout=90)
            if r.status_code != 429:
                break
            paus = 20 * (forsok + 1)
            print(f'  (429 Too Many Requests - väntar {paus} s)')
            time.sleep(paus)
        time.sleep(2)
        if r.status_code == 404:   # vissa STAC-API:er saknar POST /search
            r = s.get(f'{a.api}/collections/{coll}/items',
                      params={'bbox': ','.join(map(str, a.bbox)), 'limit': 100}, timeout=60)
        r.raise_for_status()
        hittade += r.json().get('features', [])
    if not hittade:
        sys.exit('Inga ortofoton hittades i angiven bbox – kontrollera bbox och att området är skannat (Planer och utfall).')
    print(f'{len(hittade)} ruta/rutor täcker området.')

    # 3) Ladda ner LAZ-assets
    for item in hittade:
        for namn, asset in item.get('assets', {}).items():
            href = asset.get('href', '')
            if not href.lower().endswith(('.tif', '.tiff')):
                continue
            fil = os.path.join(a.out, os.path.basename(href.split('?')[0]))
            if os.path.exists(fil):
                print('Finns redan:', fil); continue
            print('Laddar ner', href.split('/')[-1], '…', flush=True)
            with s.get(href, stream=True, timeout=600) as dl:
                dl.raise_for_status()
                tot = 0
                with open(fil, 'wb') as f:
                    for chunk in dl.iter_content(1 << 20):
                        f.write(chunk); tot += len(chunk)
                        print(f'\r  {tot/1e6:.0f} MB', end='')
            print('  klart.')
    print(f'Klart! Filerna ligger i ./{a.out}/ – kör sedan preprocess.py med --orto mot den mappen.')

if __name__ == '__main__':
    main()
