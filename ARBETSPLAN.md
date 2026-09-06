# HITTA UTESERVERINGEN – ARBETSPLAN
*Uppdaterad 2026-09-06. Läge: app v0.51, preprocess v2.9.1.
Live: https://vlassl.github.io/hitta-uteserveringen/ (550 tiles, ~150 km²)*

## Systemet i korthet
- **Data:** Lantmäteriet Laserdata Skog (COPC/LAZ, 1–2 pkt/m²) + Ortofoto
  (`C:\soldata\orto`, 37 raster 2,5×2,5 km, 0,16 m, EPSG:3006, 4 band) +
  Markhöjdmodell grid 50+ (HDB) för fjärrhorisonten.
- **Kedja:** `hamta_laser.py` / `hamta_orto.py` → `preprocess.py` → `tiles/`
  → `index.html`. `bygga_oversikt.py` gör `tiles/oversikt.png` (50 m/px) och
  skriver nyckeln `oversikt` i index.json (preprocess ≥ v2.9.0 bevarar den).
- **Mappar:** laser `C:\soldata\laz`, orto `C:\soldata\orto`, repo
  `C:\soldata\repo\hitta-uteserveringen`, arbetsmapp `C:\soldata\arbetsmapp`.
- **Tileformat fmt 2:** huvudtile RG = hård yta ((h+100)*10), B = krontopp
  (0,5 m-steg). `_bas.png` R = kronbas, **G = flagga (255 byggnad, 64 brodäck,
  0 övrigt)**, B = hushöjd över mark. `tex_<key>.jpg` = ortofoto 0,5 m/px.
- **Laserklasser (LM):** 1 objekt, 2 mark, 7/18 brus, 9 vatten, **17 brodäck**.

## LÖST 2026-09-06
1. **Nodata-hål under stora tak** (Katarina-kupolen, Globen, gallerior).
   `fill_nan(dtm, 15)` fyllde markmodellen bara 15 m in under tak; sedan
   `hard[isnan(dtm)] = nan`. v2.8.6: pyramidfyllning (8×/64×) där
   laserpunkter finns inom 2 m. Katarina + Globen-rutan omkörda; övriga
   tiles rättas vid full omkörning.
2. **Ortofoto:** `tex_*.jpg` i repot var laserintensitet (gråskala, 203
   helsvarta kantremsor). Färgtexturerna låg i `arbetsmapp\tiles` sedan
   28/8 (`--out tiles` skrev dit). Kopierade till repot. Två kanttiles
   (678912_6579712, 679424_6579200) saknar textur tills körning med `--orto`.
3. **Fjärrhorisonten var av:** preprocess skrev om index.json utan
   `oversikt`-nyckeln → `OV.ok=false` i appen. Nyckeln återställd
   (e0 640000, n1 6615000, res 50, 1440×1400) och bevaras från v2.9.0.
4. **Broar** (v2.9.0/2.9.1): klass 17 → däck i veg-kanalen, ovansida ur
   lasern (+ bilar/räcken ≤ 2 m), undersida = ovansida − 3,0 m
   (`--brotjocklek`, schablon – lasern ser inte undersidan), `_bas` G = 64.
   Däck < 2,5 m över mark → hård yta. Broutrustning inom 3 m från fritt
   däck (≥ 6 m över mark) går in i däcket eller slopas. Appen v0.51 räknar
   G=64 som **skugga året runt** (inte "silad sol") och ritar däcken grå
   med tomrum under. Testat på Årstabroarna + Liljeholmsbron (5 tiles).
5. **Parasoll på tak** (v0.51): klick på hus i 3D sätter parasollet på
   taket; horisonten räknas från takhöjd; OSM `location=roof/rooftop`
   snappas inte ut från huset; "tak"-etikett i listan.
6. Basfilsfynd: fyra tiles (Globen-rutan, Årsta N, 673280_6578176) hade
   **0 px kronbas** sedan gamla min-merge-buggen – återställda vid omkörning.

## Att göra – i prioritetsordning

### 1. Full omkörning med v2.9.1 *(krävs för broar och nodata-hål överallt)*
`py bygg_om.py --artefakter alla_tiles.json --kor --orto C:\soldata\orto`
raderar alla 550 tiles och bygger om (Overpass-cachen gör byggnaderna
gratis; timmar). Går det snett: `git checkout -- tiles` återställer.
Kontroll efteråt: 550 tiles, basfiler (ingen −20 %), `oversikt` kvar,
stickprov Söder Torn/Skrapan 86,5 m, Västerbron, Skanstull, Centralbron.

### 2. Bro-kanten vid landfästen
Träd/utrustning intill däck < 6 m över mark rörs inte (BRO_FRI). Granska
i 3D vid Skanstull och Liljeholmen om gröna pelare står kvar.

### 3. Väderdata från SMHI
Punktprognos (`api.smhi.se`), molnighet + temperatur, cache ~1 h, visa i
listkortet, vikta rankningen. Faller anropet: geometrin som i dag.

### 4. Lövsprickning per art
Stockholms träddatabas → artvis transmission. Broar = art med 0
transmission (redan implementerat via G=64).

### 5. Kurering av `lagen.json`
Export: 5× på versionsnumret i headern.

### 6. bygg_om: 32 m marginal i bbox
Omkörda tiles skiljer sig 0,6–3 m i yttersta 15 raderna mot grannens
strip-merge (markmodellen saknar grannblockets punkter). Kosmetiskt.

### 7. Kantremsor (W/H överskattas en tile när punkter ligger < 1 m från
bbox-kanten) – ger 15 px-slivers i nästa tilekolumn. Harmlöst med
symmetrisk merge, men källan till de svarta intensitetstexturerna.

### 8. "Föreslå korrekt läge" · 9. Fler stadsdelar · 10. Google Places (parkerat)

## Verktyg i `verktyg\`
preprocess (v2.9.1) · bygg_om (`--artefakter <urval>.json --kor [--orto]`,
tar med tiles som saknas på disk men står i index.json) · brokoll/brokoll2
(klass 17-inventering, under-däck-histogram) · ortokoll · linjedetektor ·
efterkontroll · krankoll · urval: kupol_globen.json, broar_test.json,
alla_tiles.json.

## Parkerat med flit
- Takrendering B/C, fasader/fönster, reflekterad sol, intensitetstexturer,
  SBK trädkronraster, generellt "högt och glest"-filter (kapar äkta tak).
- Brodäckets undersida ur lasern: klass 1 under däcken ger kantbalk
  (1–1,5 m) där den syns, inte lådans botten; platt fördelning i övrigt.
  Schablon 3,0 m tills vidare (brokoll2.txt har histogrammen).

## Lösta milstolpar
COPC-voxelbuggen · kronbas som vinkelintervall · fasadsnappning + manuell
parasollplacering · öppettidsparser · Overpass-failover och diskcache ·
fjärrhorisont 72×70 km · tårtdiagram som kartmarkörer · 162 artefakter
kapade, 194 friade, linjedetektor 0 kandidater · nodata under stora tak ·
ortofoto i färg · broar ur klass 17 · parasoll på tak.
