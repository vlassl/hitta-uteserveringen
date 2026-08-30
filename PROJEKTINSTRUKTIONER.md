# Projektinstruktioner – Hitta uteserveringen

Kopiera innehållet nedan till projektets instruktioner i Claude.
Håll det kort — det läses vid varje prompt. Detaljerna hör hemma i
`ARBETSPLAN.md` (vad som ska göras) och `ARBETSSATT.md` (hur vi jobbar).

---

Victor är byggnadsingenjör på Tyréns och bygger **Hitta uteserveringen**,
en webbapp som svarar på frågan "var kan jag sitta i solen just nu?" för
Stockholms uteserveringar. Live på vlassl.github.io/hitta-uteserveringen.

Appen bygger på Lantmäteriets laserdata i stället för extruderade
byggnadsfotavtryck. Det ger verkliga takformer och — viktigast — träd
med både krontopp och kronbas, så att lågt stående sol kan passera under
kronorna. Det är projektets kärna och det ingen kommersiell tjänst gör.

**Kedja:** `hamta_laser.py` / `hamta_orto.py` → `preprocess.py` → `tiles/`
→ `index.html`. Python 3.14, vanilla JS, Three.js r128, Leaflet, Overpass,
GitHub Pages. SWEREF99 TM (EPSG:3006), höjder i RH2000.

**Tileformat fmt 2:** huvudtile RG = hård yta `(h+100)*10`, B = krontopp
i 0,5 m-steg. `_bas.png` RGB = kronbas / byggnadsflagga / hushöjd över mark.
`tex_<key>.jpg` = ortofoto 0,5 m/px.

**Mappar:** arbetsmapp `OneDrive\Dropboxen\HittaUteserveringen` (här körs
allt), repo `C:\soldata\repo\hitta-uteserveringen` med `tiles\` och
`verktyg\`, laser `C:\soldata\laz`, orto `C:\soldata\orto`.

## Så vill Victor jobba

- Svara på svenska. Var koncis och konkret. Hoppa över beröm och
  sammanfattningar av vad som just sagts.
- **Victor redigerar aldrig `preprocess.py` själv.** Leverera kompletta
  ersättningsfiler med uppräknat versionsnummer i filhuvudet.
- Verifiera ändringar mot riktiga tiles innan de levereras, och ange
  förväntade siffror så han kan jämföra mot sin egen körning.
- Mät i datan och redovisa koordinater och utbredning innan kod skrivs.
  Visuell granskning av tiles är hans föredragna felsökningsmetod.
- Skriv konsolutskrifter i skript utan å, ä och ö — konsolen mojibake:ar.
- PowerShell kör inte skriptfiler (Group Policy `AllSigned`). Ge kommandon
  att klistra in direkt, eller `.py` som körs med `py`.
- En sak i taget. Han säger till när nästa steg ska tas.

## Kontrollera alltid

- `merge_into` tar `np.maximum` — **radera berörda tiles före omkörning**,
  annars vinner det gamla värdet och kapningar får ingen effekt.
- `index.json` ska ha 548 tiles, fmt 2, tileSize 512 efter varje körning.
- I `git diff --cached --stat`: en `_bas.png` som tappat tiotals procent
  betyder raderad kronbas. Promille är normalt.
- `Artefaktlista: N punkter läses in` ska stå överst i utskriften.
- En artefakt kan ligga i byggnadskanalen, vegetationskanalen eller båda.
  Kontrollera alltid båda.
- Innan commit: verifiera i 3D och vrid ett varv. Kolla att äkta höga hus
  står kvar — Söder Torn och Skrapan ska visa 86,5 m vid Medis.
- Påminn om att kopiera ändrade skript till `verktyg/` när en session
  avslutas med commit.
- Pusha aldrig genom att ladda upp filer på github.com; det får den lokala
  klonen att glida isär från origin utan varning.
