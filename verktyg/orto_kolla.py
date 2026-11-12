#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
orto_kolla.py - sonderar Lantmäteriets bild-STAC: vilka kollektioner täcker
Stockholm, och vilket frågeformat funkar? Gör få anrop (rate-limit-vänligt).

  py orto_kolla.py --user MEJL --password X
  py orto_kolla.py --user MEJL --password X --coll orto-a2-2024
"""
import argparse, json, sys, time
import requests

API = 'https://api.lantmateriet.se/stac-bild/v1'
# Testpunkt: Vapengatan 2, Aspudden (WGS84)
LAT, LON = 59.3064, 18.0009
BBOX = [17.99, 59.30, 18.01, 59.31]

def global_sok(s, bbox, sida=100):
    """Söker i HELA arkivet på bbox - ett anrop, visar vilka kollektioner
    som täcker punkten och vilket år de är från."""
    print('=== Global sökning på bbox (alla kollektioner) ===')
    r = s.post(f'{API}/search', json={'bbox': bbox, 'limit': sida}, timeout=120)
    print('POST /search ->', r.status_code)
    if r.status_code != 200:
        r = s.get(f'{API}/search',
                  params={'bbox': ','.join(map(str, bbox)), 'limit': sida}, timeout=120)
        print('GET /search ->', r.status_code)
    if r.status_code != 200:
        print(r.text[:300]); return
    feats = r.json().get('features', [])
    print(f'{len(feats)} träffar\n')
    per = {}
    for f in feats:
        coll = f.get('collection', '?')
        dt = (f.get('properties', {}) or {}).get('datetime', '')[:10]
        per.setdefault(coll, {'n': 0, 'dt': dt, 'ex': f})
        per[coll]['n'] += 1
    for coll, info in sorted(per.items(), key=lambda kv: kv[1]['dt'], reverse=True):
        print(f'  {coll:32s} {info["n"]:3d} rutor   {info["dt"]}')
        for namn, asset in list(info['ex'].get('assets', {}).items())[:2]:
            print(f'      "{namn}": {asset.get("href","")[:100]}')
    print()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True)
    ap.add_argument('--password', required=True)
    ap.add_argument('--coll', nargs='*', help='kollektioner att sondera')
    a = ap.parse_args()

    s = requests.Session()
    s.auth = (a.user, a.password)

    global_sok(s, BBOX)
    if a.coll is None:
        return                      # global sökning räcker som sondering
    kandidater = a.coll or ['orto-a2-2024', 'orto-a4-2023', 'orto-a6-2022',
                            'orto-a2-2022', 'orto-storstockholm-2009']

    for coll in kandidater:
        print(f'\n=== {coll} ===')
        # 1) Kollektionens egen metadata: utbredning och tidsintervall
        r = s.get(f'{API}/collections/{coll}', timeout=60)
        if r.status_code != 200:
            print(f'  metadata: HTTP {r.status_code}')
            time.sleep(3)
            continue
        d = r.json()
        ext = d.get('extent', {}).get('spatial', {}).get('bbox', [[]])
        tid = d.get('extent', {}).get('temporal', {}).get('interval', [[]])
        print(f'  titel: {d.get("title","-")}')
        print(f'  utbredning: {ext}')
        print(f'  tid: {tid}')
        print(f'  träffar Stockholm: '
              f'{"JA" if ext and ext[0] and ext[0][0] <= LON <= ext[0][2] and ext[0][1] <= LAT <= ext[0][3] else "nej"}')
        time.sleep(2)

        # 2) items med bbox (GET - enklaste vägen)
        r = s.get(f'{API}/collections/{coll}/items',
                  params={'bbox': ','.join(map(str, BBOX)), 'limit': 3}, timeout=90)
        print(f'  GET items?bbox -> HTTP {r.status_code}', end='')
        if r.status_code == 200:
            f = r.json().get('features', [])
            print(f', {len(f)} träffar')
            for it in f[:3]:
                assets = it.get('assets', {})
                print(f'    id: {it.get("id")}')
                for namn, asset in list(assets.items())[:6]:
                    print(f'      asset "{namn}": {asset.get("type","?")} '
                          f'{asset.get("href","")[:95]}')
        else:
            print()
        time.sleep(3)

        # 3) items UTAN bbox - visar hur en post ser ut om bbox-filtret strular
        r = s.get(f'{API}/collections/{coll}/items', params={'limit': 1}, timeout=90)
        if r.status_code == 200:
            f = r.json().get('features', [])
            if f:
                print(f'  exempelpost utan filter: id={f[0].get("id")} '
                      f'bbox={f[0].get("bbox")}')
        time.sleep(3)

if __name__ == '__main__':
    main()
