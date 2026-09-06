#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brokoll.py - inventerar klass 17 (brodack) i laserdatan.
Laser alla .copc.laz i C:\soldata\laz i bitar, plockar ut klass 17 inom
tileomradet och rastrerar till 2 m-rutor: antal, zmax, zmin.
Kors fran arbetsmappen:   py brokoll.py
Skriver bro17.npz (grid), bro17.png (oversikt) och brokoll.txt (statistik).
Tar nagra minuter per laserfil.
"""
import glob, os, sys, time
from collections import Counter
import numpy as np
from PIL import Image

LAZ = r'C:\soldata\laz'
BBOX = (666112, 6574592, 679424, 6585856)     # tileomradet + kant
RES = 2
KLASS = 17

def main():
    import laspy
    e0, n0, e1, n1 = BBOX
    W = (e1 - e0) // RES; H = (n1 - n0) // RES
    cnt = np.zeros(H * W, np.int32)
    zmax = np.full(H * W, -np.inf); zmin = np.full(H * W, np.inf)
    klasser = Counter()
    tot17 = 0
    rader = []
    for f in sorted(glob.glob(os.path.join(LAZ, '*.la[sz]'))):
        t = time.time()
        with laspy.open(f) as fh:
            tot = fh.header.point_count; done = 0
            for ch in fh.chunk_iterator(10_000_000):
                c = np.asarray(ch.classification)
                klasser.update(Counter(c.tolist()))
                m = c == KLASS
                done += len(c)
                if m.any():
                    x = np.asarray(ch.x)[m]; y = np.asarray(ch.y)[m]; z = np.asarray(ch.z)[m]
                    inne = (x >= e0) & (x < e1) & (y >= n0) & (y < n1)
                    x, y, z = x[inne], y[inne], z[inne]
                    tot17 += len(x)
                    col = ((x - e0) // RES).astype(np.int64)
                    row = ((n1 - 1 - y) // RES).astype(np.int64)
                    flat = row * W + col
                    np.add.at(cnt, flat, 1)
                    np.maximum.at(zmax, flat, z)
                    np.minimum.at(zmin, flat, z)
                print(f'\r  {os.path.basename(f)}: {done/1e6:.0f}/{tot/1e6:.0f} M punkter, '
                      f'klass {KLASS} hittills {tot17}', end='', flush=True)
        s = f'{os.path.basename(f)}: {tot/1e6:.1f} M punkter, {time.time()-t:.0f} s'
        print('\n' + s); rader.append(s)
    zmax[np.isinf(zmax)] = np.nan; zmin[np.isinf(zmin)] = np.nan
    cnt = cnt.reshape(H, W); zmax = zmax.reshape(H, W); zmin = zmin.reshape(H, W)
    np.savez_compressed('bro17.npz', cnt=cnt, zmax=zmax, zmin=zmin,
                        bbox=np.array(BBOX), res=RES)
    rader.append('klasser totalt: ' + str(dict(sorted(klasser.items()))))
    rader.append(f'klass {KLASS} i tileomradet: {tot17} punkter, {int((cnt > 0).sum())} rutor a {RES} m')
    # sammanhangande klumpar (4-grannar) - grov lista utan scipy
    lab = np.zeros((H, W), np.int32); n = 0
    occ = cnt > 0
    rs, cs = np.nonzero(occ)
    for r, c in zip(rs, cs):
        if lab[r, c]:
            continue
        n += 1; stack = [(r, c)]; lab[r, c] = n
        while stack:
            rr, cc = stack.pop()
            for dr, dc in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                r2, c2 = rr+dr, cc+dc
                if 0 <= r2 < H and 0 <= c2 < W and occ[r2, c2] and not lab[r2, c2]:
                    lab[r2, c2] = n; stack.append((r2, c2))
    klumpar = []
    for i in range(1, n + 1):
        m = lab == i
        k = int(m.sum())
        if k < 25:
            continue
        rr, cc = np.nonzero(m)
        klumpar.append((k, e0 + cc.min()*RES, e0 + (cc.max()+1)*RES,
                        n1 - (rr.max()+1)*RES, n1 - rr.min()*RES,
                        float(np.nanmin(zmin[m])), float(np.nanmax(zmax[m])),
                        float(np.nanmedian(zmax[m] - zmin[m]))))
    klumpar.sort(reverse=True)
    rader.append(f'{len(klumpar)} klumpar >= 25 rutor (storsta forst):')
    for k, ea, eb, na, nb, zlo, zhi, tj in klumpar:
        rader.append(f'  {k*RES*RES:7d} m2  E {ea:.0f}-{eb:.0f}  N {na:.0f}-{nb:.0f}  '
                     f'z {zlo:.1f}-{zhi:.1f}  median zmax-zmin per ruta {tj:.1f} m')
    open('brokoll.txt', 'w', encoding='utf-8').write('\n'.join(rader))
    # oversiktsbild: 10 m/px, vit = klass 17
    f = 10 // RES
    Hc, Wc = H // f, W // f
    ov = occ[:Hc*f, :Wc*f].reshape(Hc, f, Wc, f).any(axis=(1, 3))
    Image.fromarray((ov * 255).astype(np.uint8)).save('bro17.png')
    print('\n'.join(rader[-min(len(rader), 40):]))
    print('-> brokoll.txt, bro17.npz, bro17.png')

if __name__ == '__main__':
    main()
