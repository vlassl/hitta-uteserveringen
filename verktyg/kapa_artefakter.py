def kapa_artefakter(hard, bh, bflag, e0, n_top, W, H, lista):
    """Kapar hårda ytan inom angivna radier ner till omgivningens takmedian.

    Ändringar mot v2.7:
      * cirkelmask i stället för bounding box (r är nu verkligen en radie)
      * referensmedianen tas ur en ÄKTA ring - artefaktrutan exkluderas
      * utskriften visar var pixlarna satt och hur högt de stack, så det
        syns direkt om kapningen tog något utanför den avsedda klumpen
    """
    for a in lista:
        E, N, r = float(a['E']), float(a['N']), float(a.get('r', 40))
        namn = a.get('namn', '?')
        minh = a.get('minh')          # absolut golv i m over mark, valfritt
        c0 = int(E - r - e0); c1 = int(E + r - e0)
        r0 = int(n_top - (N + r)); r1 = int(n_top - (N - r))
        if c1 < 0 or r1 < 0 or c0 >= W or r0 >= H:
            continue
        c0, c1 = max(0, c0), min(W, c1)
        r0, r1 = max(0, r0), min(H, r1)
        if c1 <= c0 or r1 <= r0:
            continue

        # --- referensnivå: median av byggnadshöjder i ringen r..2r ---------
        R = int(r * 2)
        rc0, rc1 = max(0, int(E - R - e0)), min(W, int(E + R - e0))
        rr0, rr1 = max(0, int(n_top - (N + R))), min(H, int(n_top - (N - R)))
        ringmask = bflag[rr0:rr1, rc0:rc1].copy()
        ringmask[r0 - rr0:r1 - rr0, c0 - rc0:c1 - rc0] = False   # bort med mitten
        ring = bh[rr0:rr1, rc0:rc1][ringmask]
        ref = float(np.median(ring)) if ring.size > 20 else 12.0
        if ring.size <= 20:
            print(f'    artefakt "{namn}": VARNING - bara {ring.size} '
                  f'byggnadspixlar i ringen, använder reservnivå {ref:.1f} m')

        # --- cirkelmask ----------------------------------------------------
        yy, xx = np.mgrid[r0:r1, c0:c1]
        pE = e0 + xx + 0.5                 # pixelcentrum i SWEREF
        pN = n_top - yy - 0.5
        inne = (pE - E) ** 2 + (pN - N) ** 2 <= r * r

        sub_h = hard[r0:r1, c0:c1]
        sub_b = bh[r0:r1, c0:c1]
        mark = sub_h - sub_b               # marknivå i rutan
        # Golvet for vad som raknas som artefakt. minh ur listan ar att
        # foredra: den satts efter vad man faktiskt sett i tilen och kan
        # laggas hogt over kvarterets verkliga tak, sa inget akta kapas.
        gran = float(minh) if minh is not None else ref + 6.0
        m = inne & ~np.isnan(sub_h) & (sub_b > gran)
        if not m.any():
            print(f'    artefakt "{namn}": inget att kapa (ref {ref:.1f} m, '
                  f'gräns {gran:.1f} m)')
            continue

        fore = float(np.nanmax(sub_b[m]))
        sub_h[m] = mark[m] + ref
        sub_b[m] = ref

        rs, cs = np.nonzero(m)
        Emin = e0 + c0 + int(cs.min()); Emax = e0 + c0 + int(cs.max())
        Nmax = n_top - (r0 + int(rs.min())); Nmin = n_top - (r0 + int(rs.max()))
        print(f'    artefakt "{namn}" (gräns {gran:.1f} m): {int(m.sum())} px kapade '
              f'{fore:.1f} -> {ref:.1f} m över mark  '
              f'[E {Emin:.0f}-{Emax:.0f}, N {Nmin:.0f}-{Nmax:.0f}, '
              f'{Emax-Emin+1}x{Nmax-Nmin+1} m]')
    return hard, bh
