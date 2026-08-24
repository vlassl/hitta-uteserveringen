# HITTA UTESERVERINGEN – ARBETSPLAN
*Uppdaterad 2026-08-23. Läget: v0.7 (app) / v1.4 (preprocess). Kedjan
Geotorget → COPC → tiles → solband/lista/3D verifierad mot Aspudden.*

## Att göra – förfiningar

1. **Brusfilter i preprocess**
   95:e percentil istället för max per pixel för hårda ytan och krontopp,
   plus 3×3-medianfilter. Tar bort spikar (antenner, fåglar, kranar) och
   markkonfetti (lågt ris som blir enstaka gröna kuber).

2. **Skarpa husväggar i 3D**
   Flagga byggnadspixlar i tile-formatet (ledig bit i kodningen alt. egen
   maskfil per tile, OSM-masken finns redan i preprocess). 3D-vyn reser då
   lodräta boxar för hus istället för smälta sluttningar.

3. **Kronbas via percentil**
   T.ex. 10:e percentilen av vegetationsreturer istället för minimum –
   robustare mot enstaka stampunkter och buskage under kronan.

4. **Större täckning**
   Kör pipelinen för hela innerstan (~10–15 laserrutor, några hundra MB
   tiles). Ren batchkörning; håll GitHub Pages-repot under 1 GB.

5. **Fixa COPC-frågan**
   laspy-queryn gav bara toppnivån av oktreet (15k av 5M punkter).
   Undersök resolution/level-parametrarna eller iterera noder manuellt.
   Viktigt först vid punkt 4 – chunkskanningen funkar men tar minuter/ruta.

6. **Lövsprickning per art**
   Stockholms träddatabas vet art och läge. Artvis transmissionskalender
   (ek löffälls sent, björk tidigt) istället för en global månadstabell.

7. **dtm-cog som markreferens**
   Lantmäteriets färdiga markmodell (finns i samma STAC-API) som facit och
   hålfyllnad om terrängen visar artefakter någonstans.

8. **Ortofoto-drapering i 3D** *(spår A – vald väg)*
   a) hamta_orto.py: hämta ortofoto (COG, 0 kr) via STAC-bild-API:t
   b) preprocess --orto: klipp till texturtiles tex_<key>.jpg (0,5 m/px)
   c) 3D-vyn: drapera texturen på terrängmeshen (UV-mappning)

9. **Intensitetstextur som fallback** *(spår B)*
   Medelintensitet per pixel ur LAZ (attribut som i dag slängs) →
   svartvit flygfotoliknande textur där ortofoto saknas.

## Anteckning: fotolika färger
Ortofoto-drapering är rätt väg: preprocess får ett steg som klipper
ortofotot till 512 m-texturtiles (t.ex. 0,5 m/px → 1024×1024 PNG), appen
UV-mappar dem på terrängmeshen. Vegetationvolymerna hålls halvtransparent
gröna ovanpå. Kostnad 0 kr, samma STAC-mönster som lasern
(hamta_laser.py kan återanvändas). Fallback utan nedladdning: intensitet.

13. **Takrendering i 3D – välj A, B eller C** *(beslut väntar)*
    Taken renderas i dag som per-pixel-boxar → "krenelering" på sadeltak.
    OBS: taken får INTE plattas till - nockhöjden styr skuggkastningen.
    - A) Acceptera trappstegen (sanningen i 1 m-upplösning; kostnad 0)
    - B) Tak som eget slätt displacement-mesh inom husflaggan, lodräta
      väggar upp till takfot → sadeltaksfall utan trappsteg (~40 rader)
    - C) Som B + försiktig 3x3-median endast inom takytan (dämpar
      skorstensspikar, rör inte nock/takfall)
    Endast rendering - solfysiken använder oförändrad hård yta.

14. **Datumväljare för listan**
    Listan räknar alltid på idag; öppettidsfiltret gjorde det synligt
    (Libertin stängd må-ti försvinner). Lägg datum + starttid i listkortet
    så "var är solen onsdag kväll?" går att svara på.

## Produktsteg (parallellt spår)
- Öppettidsfilter (parsa OSM opening_hours)
- Betyg/prisnivå via Google Places (frikvot räcker för hobbybruk)
- Publicera på GitHub Pages → mobil på stan
- Uteserteringens läge: outdoor_seating-taggens riktning/position (gårdar!)

## Parkerat
- SBK trädkronraster (bara topphöjd, lasern bättre efter kronbas-jobbet;
  licens kräver dessutom mejl till geodataservice@stockholm.se)
- Reflekterad sol från glasfasader (skippas)
- Fasaddetaljer/fönster (skippas – flyglaser ser inte fasader, glas ger
  inget eko; procedurella fönster bedömda som fel ambitionsnivå)
