#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
copcdiff.py – jämför robust COPC-nodval mot helskanning (facit) och
lokaliserar VAR punkterna skiljer sig: per oktree-nivå och per 100 m-cell.

Användning:
  py copcdiff.py C:\\soldata\\laz\\m21c031-657_67.copc.laz --bbox 670100 6577300 671600 6578750
"""
import argparse, sys
import numpy as np
import laspy
from laspy.copc import CopcReader, HierarchyPage, OctreeNode

def robust(path, bbox):
    with CopcReader.open(path) as r:
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
        print(f'copc_info: center={list(info.center)}, halfsize={info.halfsize}, '
              f'spacing={info.spacing}')
        print(f'hierarki: {len(entries)} poster, {len(loaded)} undersidor')
        lvl_all = {}
        for k, e in entries.items():
            if e.point_count > 0:
                lvl_all.setdefault(k.level, [0, 0])
                lvl_all[k.level][0] += 1
                lvl_all[k.level][1] += e.point_count
        print('hela filen per nivå {nivå: (noder, punkter)}:',
              {k: tuple(v) for k, v in sorted(lvl_all.items())})
        rootmin = np.asarray(info.center, float) - info.halfsize
        side = 2.0 * info.halfsize
        sel, lvl_sel = [], {}
        for k, e in entries.items():
            if e.point_count <= 0:
                continue
            sz = side / (2 ** k.level)
            mnx = rootmin[0] + k.x * sz
            mny = rootmin[1] + k.y * sz
            if (mnx + sz < bbox[0] or mnx > bbox[2] or
                    mny + sz < bbox[1] or mny > bbox[3]):
                continue
            n = OctreeNode(); n.key = k; n.offset = e.offset
            n.byte_size = e.byte_size; n.point_count = e.point_count
            sel.append(n)
            lvl_sel.setdefault(k.level, [0, 0])
            lvl_sel[k.level][0] += 1
            lvl_sel[k.level][1] += e.point_count
        print('valda noder per nivå:', {k: tuple(v) for k, v in sorted(lvl_sel.items())})
        pts = r._fetch_and_decompress_points_of_nodes(sel)
    x = np.asarray(pts.x); y = np.asarray(pts.y)
    m = (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
    print(f'robust: {int(m.sum())} punkter i bbox '
          f'({len(x)} dekomprimerade fran valda noder)')
    return x[m], y[m]

def facit(path, bbox):
    xs, ys = [], []
    with laspy.open(path) as fh:
        tot = fh.header.point_count; done = 0
        for ch in fh.chunk_iterator(10_000_000):
            x = np.asarray(ch.x); y = np.asarray(ch.y)
            m = (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
            if m.any():
                xs.append(x[m]); ys.append(y[m])
            done += len(x)
            print(f'\rfacit-skanning {done/1e6:.0f}/{tot/1e6:.0f} M ...',
                  end='', flush=True)
    print()
    return np.concatenate(xs), np.concatenate(ys)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fil')
    ap.add_argument('--bbox', nargs=4, type=float, required=True,
                    metavar=('EMIN', 'NMIN', 'EMAX', 'NMAX'))
    a = ap.parse_args()
    b = a.bbox
    rx, ry = robust(a.fil, b)
    fx, fy = facit(a.fil, b)
    print(f'\nTOTALT  robust: {len(rx):,}   facit: {len(fx):,}   '
          f'diff: {len(fx)-len(rx):,} ({(len(fx)-len(rx))/max(1,len(fx))*100:.1f}%)'
          .replace(',', ' '))
    # per 100 m-cell
    C = 100.0
    def cells(x, y):
        i = ((x - b[0]) // C).astype(int)
        j = ((y - b[1]) // C).astype(int)
        W = int((b[2]-b[0]) // C) + 1
        cnt = {}
        for k in (j * W + i):
            cnt[k] = cnt.get(k, 0) + 1
        return cnt, W
    rc, W = cells(rx, ry)
    fc, _ = cells(fx, fy)
    diffs = []
    for k, fv in fc.items():
        rv = rc.get(k, 0)
        if fv - rv > 0:
            diffs.append((fv - rv, fv, k))
    diffs.sort(reverse=True)
    print('\nStörsta underskotten per 100 m-cell (saknas/facit @ E,N för cellens SV-hörn):')
    for d, fv, k in diffs[:12]:
        i, j = k % W, k // W
        print(f'  saknas {d:>7,} av {fv:>7,}  @  E {b[0]+i*C:.0f}, N {b[1]+j*C:.0f}'
              .replace(',', ' '))
    if not diffs:
        print('  inga underskott - metoderna matchar!')

if __name__ == '__main__':
    main()
