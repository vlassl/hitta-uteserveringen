#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
copcdiff2.py – steg 2 i COPC-detektivarbetet.
Dekomprimerar nod för nod i en E-korridor och tar reda på vilka noder som
FAKTISKT innehåller punkterna i det saknade N-bandet, samt jämför varje
nods verkliga utbredning med den voxel som nyckeln (level,x,y,z) pekar ut.

Användning:
  py copcdiff2.py C:\\soldata\\laz\\m21c031-657_67.copc.laz ^
     --bbox 670100 6577300 671600 6578750 --strip 6578400 6578700
"""
import argparse
import numpy as np
from laspy.copc import CopcReader, HierarchyPage, OctreeNode

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fil')
    ap.add_argument('--bbox', nargs=4, type=float, required=True,
                    metavar=('EMIN', 'NMIN', 'EMAX', 'NMAX'))
    ap.add_argument('--strip', nargs=2, type=float, required=True,
                    metavar=('NMIN', 'NMAX'),
                    help='N-bandet där punkter saknas')
    a = ap.parse_args()
    b = a.bbox; s0, s1 = a.strip

    with CopcReader.open(a.fil) as r:
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

        rootmin = np.asarray(info.center, float) - info.halfsize
        side = 2.0 * info.halfsize
        print(f'kubens hörn: E {rootmin[0]:.2f}, N {rootmin[1]:.2f}, '
              f'H {rootmin[2]:.2f}, sida {side:.2f}')

        # Kandidater: alla noder vars voxel överlappar E-intervallet,
        # OAVSETT N och H - så hittar vi punkterna var nycklarna än pekar.
        cands = []
        for k, e in entries.items():
            if e.point_count <= 0:
                continue
            sz = side / (2 ** k.level)
            mnx = rootmin[0] + k.x * sz
            if mnx + sz < b[0] or mnx > b[2]:
                continue
            n = OctreeNode(); n.key = k; n.offset = e.offset
            n.byte_size = e.byte_size; n.point_count = e.point_count
            cands.append((k, n, sz))
        print(f'{len(cands)} kandidatnoder i E-korridoren, dekomprimerar ...')

        traffar = []
        tot_strip = 0
        for i, (k, n, sz) in enumerate(cands):
            pts = r._fetch_and_decompress_points_of_nodes([n])
            x = np.asarray(pts.x); y = np.asarray(pts.y)
            m = (x >= b[0]) & (x < b[2]) & (y >= s0) & (y < s1)
            cnt = int(m.sum())
            if cnt > 0:
                # nyckelns voxel enligt vår formel
                vx = rootmin[0] + k.x * sz
                vy = rootmin[1] + k.y * sz
                vz = rootmin[2] + k.z * sz
                inne = (vy <= s1) and (vy + sz >= s0)
                traffar.append((cnt, k, (vx, vy, vz, sz),
                                (float(x.min()), float(x.max()),
                                 float(y.min()), float(y.max()))))
                tot_strip += cnt
            if (i + 1) % 50 == 0:
                print(f'\r  {i+1}/{len(cands)} noder klara, '
                      f'{tot_strip:,} strippunkter funna'.replace(',', ' '),
                      end='', flush=True)
        print()

    traffar.sort(reverse=True, key=lambda t: t[0])
    print(f'\n{tot_strip:,} punkter i bandet N {s0:.0f}-{s1:.0f} '
          f'fördelade på {len(traffar)} noder.'.replace(',', ' '))
    print('\nTopp 15 noder (punkter i bandet | nyckel | voxel enligt formel | '
          'verklig punktutbredning):')
    for cnt, k, (vx, vy, vz, sz), (xmn, xmx, ymn, ymx) in traffar[:15]:
        stamm = 'OK ' if (vy <= ymx and vy + sz >= ymn) else 'FEL'
        print(f'  {cnt:>7,} | L{k.level} x{k.x} y{k.y} z{k.z} | '
              f'voxel N {vy:.0f}-{vy+sz:.0f} E {vx:.0f}-{vx+sz:.0f} | '
              f'punkter N {ymn:.0f}-{ymx:.0f} E {xmn:.0f}-{xmx:.0f}  [{stamm}]'
              .replace(',', ' '))
    fel = [t for t in traffar if not (t[2][1] <= t[3][3] and t[2][1]+t[2][3] >= t[3][2])]
    print(f'\nNoder där formelns voxel INTE stämmer med punkternas läge: '
          f'{len(fel)} av {len(traffar)}')
    if fel:
        print('=> nyckel-mappningen är fel för dessa; jämför kolumnerna ovan '
              'för att se mönstret (spegling/förskjutning/axelbyte).')
    else:
        print('=> mappningen stämmer överallt; felet sitter då i urvalslogiken, '
              'inte i geometrin.')

if __name__ == '__main__':
    main()
