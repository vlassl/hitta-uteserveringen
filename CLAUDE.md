# Hitta uteserveringen

Victor bygger **Hitta uteserveringen**, en webbapp som svarar på "var kan jag sitta i solen just nu?" för Stockholms uteserveringar. Live: https://vlassl.github.io/hitta-uteserveringen/ (GitHub Pages från `main`).

Appen bygger på Lantmäteriets laserdata i stället för extruderade byggnadsfotavtryck: verkliga takformer och träd med både krontopp och kronbas, så att lågt stående sol kan passera under kronorna. Det är projektets kärna.

Projektet flyttades från Cowork till Claude Code 2026-11-12. `ARBETSSATT.md` och `PROJEKTINSTRUKTIONER.md` beskriver Cowork-tiden. Det som gäller nu står här, och fällorna och kontrollerna i `ARBETSSATT.md` gäller fortfarande.

## Systemet

- **Kedja:** `hamta_laser.py` / `hamta_orto.py` → `preprocess.py` → `tiles/` → `index.html`. `bygga_oversikt.py` gör `tiles/oversikt.png` (fjärrhorisonten). Python 3.14 (kör med `py`), vanilla JS, Three.js r128, Leaflet, Overpass, SMHI-prognos, GitHub Pages. SWEREF99 TM (EPSG:3006), höjder i RH2000.
- **Tileformat fmt 2:** huvudtile RG = hård yta `(h+100)*10`, B = krontopp i 0,5 m-steg. `_bas.png` R = kronbas, G = flagga (255 byggnad, 64 brodäck, 0 övrigt), B = hushöjd över mark. `tex_<key>.jpg` = ortofoto 0,5 m/px.
- **Laserklasser (LM):** 1 objekt, 2 mark, 7/18 brus, 9 vatten, 17 brodäck.

## Mappar

```
repo         C:\soldata\repo\hitta-uteserveringen   <- Claude Code-projektet
  tiles\     preprocess skriver hit via --out (bygg_om gör det)
  verktyg\   skripten i git
arbetsmapp   C:\soldata\arbetsmapp                  <- här körs skripten
laser        C:\soldata\laz      (Lantmäteriet, ~3,7 GB, inte i git)
orto         C:\soldata\orto     (ortofoto, ~24 GB, inte i git)
hdb          C:\soldata\hdb      (markhöjdmodell, inte i git)
```

`artefakter.json` läses från katalogen man står i, så skripten körs från arbetsmappen. Ändrade skript kopieras till `verktyg/` innan commit. Claude gör kopieringen själv och kontrollerar med `diff` att `verktyg/` och arbetsmappen stämmer.

Rådata (`laz`, `orto`, `hdb`) ligger utanför repot. På en ny dator hämtas de på nytt med `hamta_laser.py` / `hamta_orto.py` (Lantmäteriets öppna data).

## Så vill Victor jobba

- Svara på svenska, koncist och konkret. Inget beröm, inga sammanfattningar av vad som just sagts.
- Claude redigerar `preprocess.py` och övriga skript direkt och räknar upp versionsnumret i filhuvudet vid varje ändring. Appens version (`v0.NN` i `index.html`) räknas upp likadant.
- Verifiera ändringar mot riktiga tiles innan de redovisas, och ange förväntade siffror.
- Mät i datan och redovisa koordinater och utbredning innan kod skrivs. Visuell granskning av tiles är Victors föredragna felsökning.
- Konsolutskrifter i skript utan å, ä och ö.
- Kurering (`artefakter.json`, `friade.json`, `lagen.json`) ändras bara efter Victors beslut.
- En sak i taget. Victor säger till när nästa steg ska tas.
- Långa körningar (bygg_om, preprocess) körs i bakgrunden med utskriften till fil, t.ex. `korning.log`.

## Git, två datorer och publicering

Victor jobbar både på jobbdatorn och på den privata datorn (minidatorn). GitHub-repot `vlassl/hitta-uteserveringen` är den gemensamma versionen.

- Vid sessionsstart kör en hook i `.claude/settings.json` `git pull --ff-only`. Om pullen har misslyckats (ändringar på båda håll): reda ut det med Victor innan något annat görs.
- **En push publicerar live-appen.** Committa när en ändring är klar och verifierad. Pusha efter Victors klartecken, aldrig force-push. Innan sessionen avslutas: säg om det finns opushade commits.
- Tiles och kod i **separata commits**.
- Pusha aldrig genom att ladda upp filer på github.com, eftersom klonen då glider isär från origin.

## Kontrollera alltid

- `merge_into` tar `np.maximum`. **Radera berörda tiles före omkörning** (bygg_om gör det), annars vinner det gamla värdet.
- `tiles/index.json` efter varje körning: tile-antalet får aldrig minska (644 i dag, 2026-11-12), fmt 2, tileSize 512, nyckeln `oversikt` finns (annars är fjärrhorisonten av).
- I `git diff --cached --stat`: en `_bas.png` som tappat tiotals procent betyder raderad kronbas. Promille och växande filer är normalt.
- `Artefaktlista: N punkter läses in` ska stå överst i utskriften.
- En artefakt kan ligga i byggnadskanalen, vegetationskanalen eller båda. Kontrollera båda.
- Innan commit: verifiera i 3D och vrid ett varv (töm cache, tiles cachas hårt; djuplänk `#3d=E,N,lat,lon`). Söder Torn och Skrapan ska visa 86,5 m vid Medis.

Planerat men inte byggt står i `docs/framtida.md`. `ARBETSPLAN.md` är historik fram till 2026-09-06.
