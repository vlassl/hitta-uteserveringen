#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ortokoll.py - varfor skriver apply_orto inga texturer?
Laser metadata ur varje raster i C:\soldata\orto och provar en
fonsterlasning vid Katarina kyrka (tile 674816_6579200).
Kors fran arbetsmappen:   py ortokoll.py
Skriver ortokoll.txt (och ortokoll_prov.jpg om lasningen lyckas).
"""
import glob, os, sys, traceback
import numpy as np

UT = 'ortokoll.txt'
TE, TN, TILE = 674816, 6579200, 512      # Katarina-tilen

def main():
    rader = []
    def p(*a):
        s = ' '.join(str(x) for x in a)
        print(s); rader.append(s)
    try:
        import rasterio
        from rasterio.vrt import WarpedVRT
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds
        p('rasterio', rasterio.__version__, 'gdal', rasterio.__gdal_version__)
    except Exception as e:
        p('rasterio saknas eller trasig:', repr(e))
        open(UT, 'w', encoding='utf-8').write('\n'.join(rader)); return
    tifs = sorted(glob.glob(r'C:\soldata\orto\*.tif'))
    p(f'{len(tifs)} raster')
    traff = None
    for f in tifs:
        try:
            with rasterio.open(f) as s:
                b = s.bounds
                p(f'{os.path.basename(f):28s} crs={s.crs} epsg={s.crs.to_epsg() if s.crs else None} '
                  f'bounds=({b.left:.0f},{b.bottom:.0f},{b.right:.0f},{b.top:.0f}) '
                  f'{s.width}x{s.height} band={s.count} {s.dtypes[0]} res={s.res} nodata={s.nodata} '
                  f'driver={s.driver} ovr={s.overviews(1)[:3]}')
                with WarpedVRT(s, crs='EPSG:3006', resampling=Resampling.bilinear) as vrt:
                    vb = vrt.bounds
                    hit = not (TE+TILE <= vb.left or TE >= vb.right or
                               TN+TILE <= vb.bottom or TN >= vb.top)
                    if abs(vb.left-b.left) > 1 or abs(vb.top-b.top) > 1:
                        p(f'    VRT-bounds avviker: ({vb.left:.0f},{vb.bottom:.0f},{vb.right:.0f},{vb.top:.0f})')
                    if hit and traff is None:
                        traff = f
        except Exception as e:
            p(f'{os.path.basename(f)}: FEL {e!r}')
    p(f'raster som traffar tile {TE}_{TN}: {traff}')
    if traff:
        try:
            with rasterio.open(traff) as s, WarpedVRT(s, crs='EPSG:3006',
                    resampling=Resampling.bilinear) as vrt:
                w = from_bounds(TE, TN, TE+TILE, TN+TILE, vrt.transform)
                p('fonster:', w)
                nb = min(3, vrt.count)
                d = vrt.read(list(range(1, nb+1)), window=w, out_shape=(nb, 1024, 1024))
                p(f'last: shape={d.shape} dtype={d.dtype} min={d.min()} max={d.max()} '
                  f'medel={d.mean():.1f} andel noll={(d.max(axis=0)==0).mean():.3f}')
                from PIL import Image
                img = np.moveaxis(d, 0, -1)
                if img.dtype != np.uint8:
                    img = np.clip(img / max(1, img.max()) * 255, 0, 255).astype(np.uint8)
                Image.fromarray(img[..., :3] if nb == 3 else np.repeat(img[..., :1], 3, -1)).save('ortokoll_prov.jpg', quality=80)
                p('ortokoll_prov.jpg skriven')
        except Exception:
            p('lasning misslyckades:'); p(traceback.format_exc())
    open(UT, 'w', encoding='utf-8').write('\n'.join(rader))
    p(f'-> {UT}')

if __name__ == '__main__':
    main()
