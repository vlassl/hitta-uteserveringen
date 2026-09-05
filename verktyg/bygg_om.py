#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bygg_om.py - lasar artefakter.json, raknar ut vilka tiles som berors,
raderar dem och kor preprocess per omrade. Kors fran ARBETSMAPPEN
(dar preprocess.py och artefakter.json ligger):

  py bygg_om.py                     visa planen utan att gora nagot
  py bygg_om.py --kor               radera och kor allt

Grupperar berorda tiles i sammanhangande omraden och kor en bbox per
omrade, sa laserlasningen halls liten. Kraver preprocess >= v2.8.5:
tidigare versioner raderade kronbasen i tiles som forst skrevs som
marginalremsa av en grannkorning och sedan byggdes fullt. Overpass-cachen i osm_cache/
gor att byggnadshamtningen mest gar pa disk.
"""
import argparse, json, os, subprocess, sys

T = 512

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--artefakter', default='artefakter.json')
    ap.add_argument('--preprocess', default='preprocess.py')
    ap.add_argument('--laz', default=r'C:\soldata\laz')
    ap.add_argument('--out', default=r'C:\soldata\repo\hitta-uteserveringen\tiles')
    ap.add_argument('--kor', action='store_true',
                    help='utan denna flagga visas bara planen')
    a = ap.parse_args()

    d = json.load(open(a.artefakter, encoding='utf-8'))
    arte = d.get('artefakter', [])
    print(f'{len(arte)} artefakter i {a.artefakter}')

    tiles = set()
    for x in arte:
        r = float(x.get('r', 40)) + 2
        for te in range(int((x['E']-r)//T)*T, int((x['E']+r)//T)*T + 1, T):
            for tn in range(int((x['N']-r)//T)*T, int((x['N']+r)//T)*T + 1, T):
                tiles.add((te, tn))

    finns = [(te, tn) for te, tn in sorted(tiles)
             if os.path.exists(os.path.join(a.out, f'{te}_{tn}.png'))]
    print(f'{len(tiles)} berorda tiles, varav {len(finns)} finns i {a.out}')

    # gruppera till sammanhangande omraden (grannar inkl diagonal)
    far = list(range(len(finns)))
    def hitta(x):
        while far[x] != x:
            far[x] = far[far[x]]; x = far[x]
        return x
    for i in range(len(finns)):
        for j in range(i + 1, len(finns)):
            if (abs(finns[i][0]-finns[j][0]) <= T and
                    abs(finns[i][1]-finns[j][1]) <= T):
                far[hitta(i)] = hitta(j)
    grupper = {}
    for i, t in enumerate(finns):
        grupper.setdefault(hitta(i), []).append(t)
    boxar = sorted(
        (min(t[0] for t in g), min(t[1] for t in g),
         max(t[0] for t in g) + T, max(t[1] for t in g) + T, len(g))
        for g in grupper.values())
    print(f'{len(boxar)} preprocess-korningar planerade:\n')
    for i, b in enumerate(boxar, 1):
        print(f'  {i:2d}. bbox {b[0]} {b[1]} {b[2]} {b[3]}   ({b[4]} tiles)')

    if not a.kor:
        print('\nTorrkorning - kor igen med --kor for att radera och bygga om.')
        return

    print('\nRaderar tiles ...')
    for te, tn in finns:
        for f in (f'{te}_{tn}.png', f'{te}_{tn}_bas.png'):
            p = os.path.join(a.out, f)
            if os.path.exists(p):
                os.remove(p)
    print(f'{len(finns)} tiles raderade (bas dar den fanns).')

    fel = []
    for i, b in enumerate(boxar, 1):
        print(f'\n=== korning {i}/{len(boxar)}: bbox {b[0]} {b[1]} {b[2]} {b[3]} ===')
        p = subprocess.Popen([sys.executable, a.preprocess,
                              '--laz', a.laz, '--out', a.out,
                              '--bbox', str(b[0]), str(b[1]), str(b[2]), str(b[3])],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace')
        hoppat = False
        for rad in p.stdout:
            print(rad, end='')
            if 'BLOCKET HOPPAS' in rad.upper():
                hoppat = True
        p.wait()
        if p.returncode != 0 or hoppat:
            fel.append(i)
            print(f'  VARNING: korning {i} {"hoppade over ett block" if hoppat else "slutade med kod "+str(p.returncode)}')

    print('\n================= KLART =================')
    if fel:
        print(f'{len(fel)} korningar felade: {fel} - kor om dem manuellt.')
    else:
        print('Alla korningar gick igenom.')
    print('Kontrollera nu: index.json (548 tiles), stickprov i tilekoll/3D,')
    print('git diff --stat innan commit (inga _bas som tappat tiotals procent).')

if __name__ == '__main__':
    main()
