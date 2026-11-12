#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bygga_oversikt.py - bygger tiles/oversikt.png: grov markhöjdkarta (50 m/px)
för fjärrhorisonten (solned-/uppgång mot åsar och hav).

Datakälla (avgiftsfri, manuell nedladdning):
  Geotorget -> "Markhöjdmodell Nedladdning, grid 50+ (HDB)" -> ruta över
  Stockholm -> ladda ner. Formatet är ASCII-tabell (E N H per rad).
  GeoTIFF (t.ex. dtm-cog) funkar också om rasterio är installerat.

Användning:
  py bygga_oversikt.py --in C:/soldata/hdb --tiles tiles --bbox 640000 6545000 712000 6615000
"""
import argparse, glob, json, os, sys
import numpy as np
from PIL import Image

RES = 50.0

def las_ascii(path, e0, n0, e1, n1, grid, W, H):
    n = 0
    with open(path, 'r', errors='ignore') as f:
        for line in f:
            p = line.replace(',', '.').split()   # svenskt decimalkomma
            if len(p) < 3:
                continue
            try:
                # både "E N H" och "N E H" förekommer - gissa på storleken
                a, b, h = float(p[0]), float(p[1]), float(p[2])
            except ValueError:
                continue
            E, N = (a, b) if a < b else (b, a)   # E ~6-700k, N ~6,5M
            if not (e0 <= E < e1 and n0 <= N < n1):
                continue
            c = int((E - e0) // RES)
            r = int((n1 - N) // RES) - 1
            if 0 <= r < H and 0 <= c < W:
                grid[r, c] = h
                n += 1
    return n

def las_tif(path, e0, n0, e1, n1, grid, W, H):
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    with rasterio.open(path) as srcf:
        with WarpedVRT(srcf, crs='EPSG:3006', resampling=Resampling.average) as v:
            b = v.bounds
            ee0, nn0 = max(e0, b.left), max(n0, b.bottom)
            ee1, nn1 = min(e1, b.right), min(n1, b.top)
            if ee0 >= ee1 or nn0 >= nn1:
                return 0
            w = from_bounds(ee0, nn0, ee1, nn1, v.transform)
            ww = int((ee1-ee0)//RES); hh = int((nn1-nn0)//RES)
            if ww < 1 or hh < 1:
                return 0
            d = v.read(1, window=w, out_shape=(hh, ww))
            c0 = int((ee0-e0)//RES); r0 = int((n1-nn1)//RES)
            sub = grid[r0:r0+hh, c0:c0+ww]
            m = (d > -1000) & (d < 3000)
            sub[m] = d[m]
            return int(m.sum())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='indir', required=True,
                    help='mapp med HDB ASCII-filer och/eller GeoTIFF')
    ap.add_argument('--tiles', default='tiles')
    ap.add_argument('--bbox', nargs=4, type=float, required=True,
                    metavar=('EMIN', 'NMIN', 'EMAX', 'NMAX'))
    a = ap.parse_args()
    e0, n0, e1, n1 = a.bbox
    W = int((e1-e0)//RES); H = int((n1-n0)//RES)
    print(f'Översikt {W}x{H} px @ {RES:.0f} m/px '
          f'({(e1-e0)/1000:.0f}x{(n1-n0)/1000:.0f} km)')
    grid = np.full((H, W), np.nan)
    filer = sorted(glob.glob(os.path.join(a.indir, '*')))
    tot = 0
    for p in filer:
        low = p.lower()
        if low.endswith(('.tif', '.tiff')):
            n = las_tif(p, e0, n0, e1, n1, grid, W, H)
        elif low.endswith(('.txt', '.asc', '.xyz', '.grid', '.dat')):
            n = las_ascii(p, e0, n0, e1, n1, grid, W, H)
        else:
            continue
        print(f'  {os.path.basename(p)}: {n:,} celler'.replace(',', ' '))
        tot += n
    if tot == 0:
        sys.exit('Inga höjdvärden hittades - kontrollera --in och --bbox.')
    tackning = 100*np.isfinite(grid).mean()
    print(f'Täckning: {tackning:.1f}% (hav/luckor = 0 m antas)')
    grid = np.nan_to_num(grid, nan=0.0)          # hav och luckor = havsytan
    v = np.clip(np.round((grid + 100) * 10), 1, 65535).astype(np.uint16)
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    rgb[..., 0] = v >> 8
    rgb[..., 1] = v & 255
    Image.fromarray(rgb).save(os.path.join(a.tiles, 'oversikt.png'), optimize=True)
    # meta in i index.json
    ip = os.path.join(a.tiles, 'index.json')
    idx = json.load(open(ip, encoding='utf-8'))
    idx['oversikt'] = {'e0': e0, 'n1': n1, 'res': RES, 'w': W, 'h': H}
    json.dump(idx, open(ip, 'w', encoding='utf-8'))
    print(f'Klart: {a.tiles}/oversikt.png + meta i index.json')

if __name__ == '__main__':
    main()
