# HITTA UTESERVERINGEN – ARBETSPLAN
*Uppdaterad 2026-08-29. Läge: app v0.46, preprocess v2.8.
Live: https://vlassl.github.io/hitta-uteserveringen/ (548 tiles, ~150 km²)*

## Systemet i korthet
- **Data:** Lantmäteriet Laserdata Skog (COPC/LAZ, 1–2 pkt/m²) + Ortofoto
  `orto-o2-2025` (0,16 m, flugen 2025-05-31) + Markhöjdmodell grid 50+ (HDB)
  för fjärrhorisonten. Allt avgiftsfritt via Geotorget/STAC.
- **Kedja:** `hamta_laser.py` / `hamta_orto.py` → `preprocess.py` → `tiles/`
  → `index.html`. `bygga_oversikt.py` gör `tiles/oversikt.png` (50 m/px).
- **Mappar:** laser `C:\soldata\laz`, orto `C:\soldata\orto` (37 raster,
  25 GB), repo `C:\soldata\repo\hitta-uteserveringen`, arbetsmapp
  OneDrive\Dropboxen\HittaUteserveringen.
- **Tileformat fmt 2:** huvudtile RG = hård yta ((h+100)*10), B = krontopp
  (0,5 m-steg). `_bas.png` RGB = kronbas / byggnadsflagga / hushöjd över
  mark. `tex_<key>.jpg` = ortofoto 0,5 m/px.
- **Etapper (bbox SWEREF99 TM):**
  E1 667700 6576300 672200 6579600 · E2 666400 6579600 678000 6585000 ·
  E3 666400 6572800 678500 6576300 · E4 672200 6576300 678500 6579600

## LÖST 2026-08-29 – falska höga strukturer
Fyra artefakter, alla **raka, smala, kraftigt förhöjda linjer** som skär
tvärs över byggnadsgränser. Sannolikt byggkranar.

| namn | utbredning | höjd ö mark | r / minh |
|---|---|---|---|
| Medborgarplatsen, linje NO-SV | E 674787–674864, N 6579015–6579030 | 62–71 m | 50 / 45 |
| Medborgarplatsen, linje N-S | E 674855–674868, N 6578911–6578989 | 47–58 m | 50 / 35 |
| Östra Medis, kort stump | E 675086–675089, N 6579019–6579023 | 41–56,5 m | 20 / 36 |
| Midsommarkransen, linje NV-SO | E 671039–671094, N 6577623–6577697 | 40–51 m | 50 / 30 |

De två Medis-linjerna är vinkelräta mot varandra och möts nära korsningen.
Antingen två kranar eller en som vridit sig mellan flygstråken —
`verktyg/krankoll.py` avgör saken via GPS-tid i punktmolnet, ej kört än.

**Viktig korrigering:** de högsta klustren i tilekoll vid Medis är *äkta
hus*. 25×26 m @ 86,5 m = Söder Torn (86 m, oktogonal plan, Bofills båge
syns intill). 30×44 m @ 86,5 m + 15×19 m @ 81,5 m = Skrapan, Götgatan 78.
De ska aldrig kapas. Tilekoll sorterar på maxhöjd, så Södermalms två
skyskrapor hamnar överst i tabellen.

### Fyra buggar hittade på vägen
1. `kapa_artefakter` rörde bara hårda ytan. Delar av en artefakt utanför
   OSM:s byggnadsmask hamnar i **vegetationskanalen** och överlevde som
   gröna pelare i 3D. (v2.8.2)
2. `laddat_index` anropades bara i blockgrenen, så en körning med bbox
   under 2048 m skrev **index.json med bara sina egna tiles** — 548 blev
   6. (v2.8.1)
3. `merge_into` tog `base = np.minimum(base, b0)`. En körning utan data i
   en grannruta levererar nollor, och `min(0, gammalt) = 0` **raderade
   kronbasen** i sju tiles. Syns inte i 3D förrän solen står lågt.
   (v2.8.3)
4. En artefakt helt utan byggnadsdel hoppades över med `continue` innan
   vegetationskoden nåddes. (v2.8.4)

**OBS vid omkörning:** `merge_into` kombinerar med befintlig tile via
`np.maximum`. En kapning kan aldrig sänka ett värde som redan ligger på
disk — berörda tiles måste raderas först.

## Att göra – i prioritetsordning

### 1. Linjedetektor för artefakter *(gör först – skyddar allt annat)*
Fyra artefakter hittades för hand, i fyra omgångar: varje gång en kapades
dök nästa upp bredvid när vyn vreds. Det finns sannolikt fler i de 548
tilesen, och fler tillkommer vid varje utbyggnad. Detektorn ska bara
*föreslå*, aldrig kapa.
  a) Skript som läser tiles/ och per tile kör sammanhängande kluster på
     `bh > lokal takmedian + 15` OCH `veg > lokal takmedian + 12` —
     båda kanalerna, annars missas hälften
  b) Filtrera på form: bredd ≤ 8 m, längd ≥ 20 m, längd/bredd ≥ 3
  c) Skriv ut E, N, utbredning, maxhöjd, lokal takmedian per kandidat
  d) Manuell granskning → nya rader i `artefakter.json` med `minh`
  e) Kontrollera om fler kandidater korsar tilegränser (båda kända gör
     det – E 674816 respektive N 6577664; troligen slump, men värt att se)

### 2. Väderdata från SMHI *(störst effekt på upplevd träffsäkerhet)*
En app som säger "här är solen 17:30" utan att veta att det är mulet
svarar på fel fråga.
  a) SMHI Öppna data, punktprognos (`api.smhi.se`, ingen nyckel, gratis)
  b) Hämta molnighet + temperatur för stadens mittpunkt, cacha ~1 h
  c) Visa i listkortet: soltimme + molnighet, inte bara geometrisk sol
  d) Överväg att vikta rankningen – full sol i moln är sämre än
     halvskugga i klarväder
  e) Faller anropet: visa geometrin som i dag, ingen hård koppling

### 3. Lövsprickning per art
Stockholms träddatabas (art + position) → artvis transmissionskalender
i stället för global månadstabell. Ek lövfäller sent, björk tidigt.

### 4. Kurering av `lagen.json`
Victors manuella parasollägen bakas in så alla användare får dem.
Export: tryck 5× på versionsnumret i headern.

### 5. "Föreslå korrekt läge"
Låt användare skicka in lägen för godkännande.

### 6. dtm-cog som markreferens vid behov
Samma STAC-API. Aktuell först om terrängen visar artefakter.

### 7. Fler stadsdelar
Pipeline och Pages-utrymme räcker gott (278 MB av 1 GB). Kör punkt 1
först, så artefakter fångas i samma svep.

### 8. Google Places-betyg *(parkerat)*
Kräver betalkort; betyg ligger i Enterprise-nivån (1000 fria anrop/mån).
Måste cachas i `betyg.json`, aldrig live-anrop. Yelp uteslutet.

## Solcellsspåret *(nytt produktbeslut, inte nästa steg)*
Modellen är stark där kommersiella verktyg är svaga: trädskuggning med
kronbas, och fjärrhorisont – båda avgörande för årsutbyte på denna
breddgrad, och båda dåligt hanterade av Google Solar API och Sunroof.

Men en full solcellskalkyl vore att göra om ett löst problem sämre.
PVGIS och PVsyst finns och är validerade. Det som saknas hos dem är
just skuggan.

**Rätt ambitionsnivå:** ett skuggindex per takyta – en siffra för
skuggförlust med trädkronor och fjärrhorisont inräknade – som matas in
i en etablerad kalkyl.

Saknas i dag: strålningsmodell (kWh/m²·år, direkt + diffus + albedo),
sky view factor för diffus strålning, 8760 timsteg över normalår,
taksegmentering i plan med lutning och azimut, hinderdetektering
(`despike` kapar i dag just skorstenar och ventilationshuvar).

**Börja med validering, inte kod:** jämför skuggindex mot uppmätt
produktion på ett fåtal befintliga anläggningar. Så fort någon fattar
investeringsbeslut på siffrorna byter projektet karaktär, och det är ett
annat åtagande än att gissa var solen står vid ett bord.

## Parkerat med flit
- Takrendering B/C (slätt takmesh) – testrendering visade nocktapp och
  verkliga tak är för komplexa; A (per-pixel-boxar) behålls.
- Fasader/fönster – flyglaser ser inte fasader, glas ger inget eko.
- Reflekterad sol från glasfasader.
- Intensitetstexturer – ersatta av ortofoto; grå mark är standard i 3D
  eftersom fotots egna skuggor annars konkurrerar med de beräknade.
- SBK trädkronraster – lasern är bättre efter kronbas-arbetet.
- Generellt "högt och glest"-filter – kapar äkta södermalmstak. Ersatt
  av formbaserad detektor (punkt 1) + kurerad lista.

## Lösta milstolpar
COPC-voxelbuggen (LM numrerar mot dataextent, inte spec-kuben – fixad med
dubbel konvention, verifierad 5 135 049 = facit) · kronbas som vinkel-
intervall (låg sol passerar under kronor) · fasadsnappning + manuell
parasollplacering · öppettidsparser med enhetstester · Overpass-failover
och diskcache · fjärrhorisont 72×70 km · tårtdiagram som kartmarkörer ·
fyra linjeartefakter kapade i båda kanalerna (v2.8.4) ·
arbetssätt och projektinstruktioner nedskrivna.
