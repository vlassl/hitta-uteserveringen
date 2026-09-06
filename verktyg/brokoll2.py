#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brokoll2.py - vad finns UNDER brodacken i lasern?
Laser bro17.npz (fran brokoll.py) och gar igenom laserfilerna igen.
For varje 2 m-ruta med klass 17 samlas klass 1-punkter som ligger under
dackets ovansida (zmax17 - 0.5 m): djup under dack i 0,5 m-steg, samt
klass 2/9 (mark/vatten) i samma rutor. Per klump (>= 25 rutor) skrivs
histogram av djupen -> syns balkundersidan som en topp?
Kors fran arbetsmappen:   py brokoll2.py
Skriver brokoll2.txt och bro17_under.npz.
"""
import glob, os, time
import numpy as np

LAZ = r'C:\soldata\laz'
DMAX = 40.0        # storsta djup under dack som registreras, m
STEG = 0.5

def klumpa(occ):
    H, W = occ.shape
    lab = np.zeros((H, W), np.int32); n = 0
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
    return lab, n

def main():
    import laspy
    d = np.load('bro17.npz')
    cnt, zmax = d['cnt'], d['zmax']; e0, n0, e1, n1 = d['bbox']; R = int(d['res'])
    H, W = cnt.shape
    occ = cnt > 0
    print('klumpar ...', flush=True)
    lab, nk = klumpa(occ)
    storlek = np.bincount(lab.ravel())
    NB = int(DMAX / STEG)
    # histogram per klump: djup under dack for klass 1
    hist = np.zeros((nk + 1, NB), np.int64)
    under_min = np.full(nk + 1, np.inf)          # minsta djup (narmast dacket)
    mark_sum = np.zeros(nk + 1); mark_n = np.zeros(nk + 1)   # dack - mark
    zmaxf = zmax.ravel(); labf = lab.ravel()
    for f in sorted(glob.glob(os.path.join(LAZ, '*.la[sz]'))):
        t = time.time()
        with laspy.open(f) as fh:
            tot = fh.header.point_count; done = 0
            for ch in fh.chunk_iterator(10_000_000):
                x = np.asarray(ch.x); y = np.asarray(ch.y)
                inne = (x >= e0) & (x < e1) & (y >= n0) & (y < n1)
                done += len(x)
                if not inne.any():
                    continue
                c = np.asarray(ch.classification)[inne]
                z = np.asarray(ch.z)[inne]; x = x[inne]; y = y[inne]
                col = ((x - e0) // R).astype(np.int64)
                row = ((n1 - 1 - y) // R).astype(np.int64)
                flat = row * W + col
                k = labf[flat]
                m = k > 0
                if not m.any():
                    continue
                flat, k, c, z = flat[m], k[m], c[m], z[m]
                djup = zmaxf[flat] - z
                # klass 1 under dacket
                m1 = (c == 1) & (djup > 0.5) & (djup < DMAX)
                if m1.any():
                    b = (djup[m1] / STEG).astype(np.int64)
                    np.add.at(hist, (k[m1], b), 1)
                    np.minimum.at(under_min, k[m1], djup[m1])
                # mark/vatten i rutan
                m2 = np.isin(c, (2, 9)) & (djup > 0)
                if m2.any():
                    np.add.at(mark_sum, k[m2], djup[m2]); np.add.at(mark_n, k[m2], 1)
                print(f'\r  {os.path.basename(f)}: {done/1e6:.0f}/{tot/1e6:.0f} M', end='', flush=True)
        print(f'  {time.time()-t:.0f} s')
    np.savez_compressed('bro17_under.npz', lab=lab, hist=hist, under_min=under_min,
                        mark_sum=mark_sum, mark_n=mark_n)
    rader = [f'{nk} klumpar; histogram = klass 1-punkter under dackets ovansida, '
             f'{STEG} m-steg fran 0,5 m']
    ordning = np.argsort(-storlek[1:]) + 1
    for i in ordning[:60]:
        if storlek[i] < 25:
            break
        rr, cc = np.nonzero(lab == i)
        h = hist[i]; n = int(h.sum())
        mark = mark_sum[i] / mark_n[i] if mark_n[i] else float('nan')
        rad = (f'klump {i:4d}  {storlek[i]*R*R:7d} m2  E {e0+cc.min()*R:.0f}-{e0+(cc.max()+1)*R:.0f}  '
               f'N {n1-(rr.max()+1)*R:.0f}-{n1-rr.min()*R:.0f}  '
               f'dack-mark medel {mark:.1f} m ({int(mark_n[i])} markpkt)  '
               f'punkter under dack: {n}')
        if n:
            kum = np.cumsum(h) / n
            p10 = (np.searchsorted(kum, 0.10) + 1) * STEG
            p50 = (np.searchsorted(kum, 0.50) + 1) * STEG
            rad += f'  narmast {under_min[i]:.1f} m, p10 {p10:.1f} m, p50 {p50:.1f} m'
            # kompakt histogram 0,5-10 m
            rad += '\n            djup 0.5-10 m: ' + ' '.join(f'{int(v)}' for v in h[:20])
        rader.append(rad)
    open('brokoll2.txt', 'w', encoding='utf-8').write('\n'.join(rader))
    print('\n'.join(rader[:25])); print('-> brokoll2.txt, bro17_under.npz')

if __name__ == '__main__':
    main()
