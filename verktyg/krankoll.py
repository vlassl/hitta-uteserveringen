#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
krankoll.py - laser-detektiv for de hoga linjestrukturerna.

Svarar pa tre fragor som tilesen inte kan svara pa:
  1) Finns det takpunkter UNDER de hoga punkterna? (kran, inte byggnad)
  2) Kommer de hoga punkterna fran ett eller flera flygstrak? (GPS-tid)
  3) Har bommen olika azimut i olika strak? (vridning -> masten i skarningen)

Anvandning:
  py krankoll.py C:\\soldata\\laz\\m21c031-657_67.copc.laz ^
     --bbox 674780 6579000 674880 6579045
  py krankoll.py C:\\soldata\\laz\\m21c031-657_67.copc.laz ^
     --bbox 674840 6578895 674885 6579000

Meddelanden utan aao for att slippa teckenkrangel i konsolen.
"""
import argparse, sys
import numpy as np


def las_noder(path, bbox):
    """Nodval med bada voxelkonventionerna, som i preprocess.copc_query_robust,
    men behaller HELA punktobjektet sa gps_time och return_number foljer med."""
    from laspy.copc import CopcReader, HierarchyPage, OctreeNode
    with CopcReader.open(path) as r:
        h = r.header
        print(f'filens utbredning: E {h.mins[0]:.0f}-{h.maxs[0]:.0f}, '
              f'N {h.mins[1]:.0f}-{h.maxs[1]:.0f}, H {h.mins[2]:.0f}-{h.maxs[2]:.0f}')
        if (bbox[2] < h.mins[0] or bbox[0] > h.maxs[0] or
                bbox[3] < h.mins[1] or bbox[1] > h.maxs[1]):
            sys.exit('bbox ligger utanfor filen.')
        info = r.copc_info
        entries = dict(r.root_page.entries)
        loaded = set()
        while True:
            sidor = [(k, e) for k, e in entries.items()
                     if e.point_count == -1 and e.offset not in loaded]
            if not sidor:
                break
            for k, e in sidor:
                loaded.add(e.offset)
                r.source.seek(e.offset)
                entries.update(HierarchyPage.from_bytes(
                    r.source.read(e.byte_size)).entries)
        rootmin = np.asarray(info.center, float) - info.halfsize
        side = 2.0 * info.halfsize
        dmin = np.asarray(h.mins, float)
        dext = np.asarray(h.maxs, float) - dmin
        sel = []
        for k, e in entries.items():
            if e.point_count <= 0:
                continue
            f2 = 2 ** k.level
            sza = side / f2
            ax = rootmin[0] + k.x * sza; ay = rootmin[1] + k.y * sza
            hitA = not (ax + sza < bbox[0] or ax > bbox[2] or
                        ay + sza < bbox[1] or ay > bbox[3])
            sxb = dext[0] / f2; syb = dext[1] / f2
            bx = dmin[0] + k.x * sxb; by = dmin[1] + k.y * syb
            hitB = not (bx + sxb < bbox[0] or bx > bbox[2] or
                        by + syb < bbox[1] or by > bbox[3])
            if not (hitA or hitB):
                continue
            n = OctreeNode(); n.key = k; n.offset = e.offset
            n.byte_size = e.byte_size; n.point_count = e.point_count
            sel.append(n)
        print(f'hierarki: {len(entries)} noder, {len(sel)} valda')
        pts = r._fetch_and_decompress_points_of_nodes(sel)
    x = np.asarray(pts.x); y = np.asarray(pts.y); z = np.asarray(pts.z)
    m = (x >= bbox[0]) & (x < bbox[2]) & (y >= bbox[1]) & (y < bbox[3])
    d = {'x': x[m], 'y': y[m], 'z': z[m],
         'kl': np.asarray(pts.classification)[m]}
    for namn in ('gps_time', 'return_number', 'number_of_returns',
                 'scan_angle_rank', 'intensity'):
        try:
            d[namn] = np.asarray(getattr(pts, namn))[m]
        except Exception:
            d[namn] = None
    print(f'{len(d["x"]):,} punkter i bbox'.replace(',', ' '))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fil')
    ap.add_argument('--bbox', nargs=4, type=float, required=True,
                    metavar=('EMIN', 'NMIN', 'EMAX', 'NMAX'))
    ap.add_argument('--minh', type=float, default=35.0,
                    help='hojd over marknivan som raknas som "hog" (m)')
    ap.add_argument('--cell', type=float, default=1.0,
                    help='rutstorlek for kolumnanalysen (m)')
    a = ap.parse_args()
    d = las_noder(a.fil, a.bbox)
    x, y, z, kl = d['x'], d['y'], d['z'], d['kl']
    if len(x) == 0:
        sys.exit('inga punkter.')

    # --- marknivan ur klass 2, annars lag percentil -----------------------
    mark = z[kl == 2]
    mz = float(np.median(mark)) if mark.size > 50 else float(np.percentile(z, 5))
    print(f'\nmarkniva (median klass 2): {mz:.1f} m RH2000  '
          f'({mark.size} markpunkter)')
    hog = z - mz > a.minh
    print(f'hoga punkter (>{a.minh:.0f} m o mark): {int(hog.sum())}')
    if hog.sum() < 10:
        sys.exit('for fa hoga punkter - justera --bbox eller --minh.')
    print(f'  hojdspann: {z[hog].min()-mz:.1f} - {z[hog].max()-mz:.1f} m o mark')
    kls, cnt = np.unique(kl[hog], return_counts=True)
    print(f'  klasser: {dict(zip(kls.tolist(), cnt.tolist()))}')

    # --- FRAGA 1: finns det punkter UNDER de hoga? ------------------------
    C = a.cell
    def cellid(xx, yy):
        return (((xx - a.bbox[0]) // C).astype(np.int64) * 100000 +
                ((yy - a.bbox[1]) // C).astype(np.int64))
    hc = set(cellid(x[hog], y[hog]).tolist())
    lag = ~hog & (z - mz < a.minh - 10)
    lc = cellid(x[lag], y[lag])
    under = {}
    for c, zz in zip(lc.tolist(), (z[lag] - mz).tolist()):
        if c in hc:
            under.setdefault(c, []).append(zz)
    print(f'\nFRAGA 1 - vad finns under bommen?')
    print(f'  celler med hoga punkter: {len(hc)}')
    print(f'  darav med lagre punkter i samma cell: {len(under)} '
          f'({100*len(under)/max(1,len(hc)):.0f} %)')
    if under:
        alla = np.array([v for lst in under.values() for v in lst])
        print(f'  de lagre punkternas hojd o mark: '
              f'median {np.median(alla):.1f} m, '
              f'p10 {np.percentile(alla,10):.1f}, p90 {np.percentile(alla,90):.1f}')
        print('  => tak/mark under de hoga punkterna: TALAR FOR KRAN')
    else:
        print('  => inga punkter under alls: talar for massiv byggnad')

    # --- FRAGA 2: ett eller flera flygstrak? -----------------------------
    print(f'\nFRAGA 2 - flygstrak (GPS-tid)')
    t = d['gps_time']
    if t is None:
        print('  filen saknar gps_time - hoppar over fraga 2 och 3.')
        return
    th = t[hog]
    ordn = np.sort(th)
    glapp = np.diff(ordn)
    brytpunkter = ordn[:-1][glapp > max(1.0, 5 * np.median(glapp[glapp > 0]) if (glapp > 0).any() else 1.0)]
    granser = [ordn[0] - 1] + list(brytpunkter) + [ordn[-1] + 1]
    grupper = []
    for i in range(len(granser) - 1):
        g = (th > granser[i]) & (th <= granser[i + 1])
        if g.sum() >= 10:
            grupper.append(g)
    print(f'  {len(grupper)} tidsgrupp(er) bland de hoga punkterna')

    # --- FRAGA 3: azimut per grupp, och masten i skarningen ---------------
    xs, ys, zs = x[hog], y[hog], z[hog]
    linjer = []
    for i, g in enumerate(grupper, 1):
        gx, gy, gz = xs[g], ys[g], zs[g]
        X = np.stack([gx - gx.mean(), gy - gy.mean()])
        w, v = np.linalg.eigh(np.cov(X))
        dv = v[:, -1]
        az = np.degrees(np.arctan2(dv[0], dv[1])) % 180
        langd = 4 * np.sqrt(w[-1]); bredd = 4 * np.sqrt(max(w[0], 1e-9))
        print(f'  grupp {i}: {int(g.sum()):5d} pkt  t {gx.size and th[g].min():.1f}'
              f'-{th[g].max():.1f}  azimut {az:5.1f} grader  '
              f'ca {langd:.0f} x {bredd:.1f} m  '
              f'hojd {gz.min()-mz:.1f}-{gz.max()-mz:.1f} m')
        linjer.append((np.array([gx.mean(), gy.mean()]), dv))

    if len(linjer) >= 2:
        print('\nFRAGA 3 - skarningspunkter (kandidat for masten)')
        for i in range(len(linjer)):
            for j in range(i + 1, len(linjer)):
                p1, d1 = linjer[i]; p2, d2 = linjer[j]
                A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
                if abs(np.linalg.det(A)) < 1e-6:
                    print(f'  grupp {i+1} och {j+1}: parallella, ingen skarning')
                    continue
                s = np.linalg.solve(A, p2 - p1)
                pk = p1 + s[0] * d1
                inne = (a.bbox[0] <= pk[0] <= a.bbox[2] and
                        a.bbox[1] <= pk[1] <= a.bbox[3])
                print(f'  grupp {i+1} x {j+1}: E {pk[0]:.0f}, N {pk[1]:.0f}'
                      f'{"" if inne else "   (utanfor bbox - troligen inte masten)"}')
        print('  Ligger skarningen still mellan grupperna ar det EN kran som vridit sig.')
    else:
        print('\n  bara en tidsgrupp - ingen vridning att mata. Tva vinkelrata')
        print('  bommar i samma grupp betyder tva olika kranar.')


if __name__ == '__main__':
    main()
