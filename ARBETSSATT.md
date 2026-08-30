# ARBETSSÄTT – Hitta uteserveringen
*Läs detta först. Uppdaterad 2026-08-29.*

## Rollfördelning
- **Victor redigerar aldrig `preprocess.py` själv.** Claude levererar
  kompletta ersättningsfiler att lägga in, med versionsnumret uppräknat
  i filhuvudet.
- Claude verifierar sina ändringar mot riktiga tiles innan de levereras,
  och anger förväntade siffror så Victor kan jämföra mot sin körning.
- Vid dataanalys: Claude mäter i tilesen och redovisar koordinater och
  utbredning innan någon kod skrivs.

## Mappar och flöde
```
arbetsmapp   OneDrive\Dropboxen\HittaUteserveringen   <- HÄR KÖRS ALLT
repo         C:\soldata\repo\hitta-uteserveringen
  tiles\     preprocess skriver hit via --out
  verktyg\   backup av skripten - INTE det som körs
laser        C:\soldata\laz
orto         C:\soldata\orto
```

**Arbetsgången:** jobba i arbetsmappen, kopiera till `verktyg/` på slutet,
committa. Filerna finns alltså på två ställen och det är arbetsmappens
kopior som körs — glöms kopieringen innehåller repot en gammal version.

**Claude ska påminna om `verktyg/`-kopieringen när en arbetssession
avslutas med commit.**

## Kommandon som behövs varje gång

PowerShell kör inte skriptfiler (Group Policy `AllSigned`) — klistra in
kommandon direkt i konsolen, eller kör `.py` via `py`.

Git saknas i PATH. Per session:
```powershell
$env:Path += ";C:\Users\vll\AppData\Local\GitHubDesktop\app-3.6.4\resources\app\git\cmd"
git config core.pager cat
```
Sökvägen innehåller versionsnumret och går sönder vid uppdatering av
GitHub Desktop. Lägg inte in den permanent.

## Fällor i preprocess

1. **`merge_into` tar `np.maximum`.** En kapning kan aldrig sänka ett
   värde som redan ligger på disk. **Radera alltid berörda tiles före
   omkörning.**
2. **Kör aldrig ett litet område utan att kontrollera `index.json`
   efteråt.** Ska vara 548 tiles, fmt 2, tileSize 512. (Buggen där
   `laddat_index` bara anropades i blockgrenen är rättad i v2.8.1, men
   kontrollen är billig.)
3. **Kontrollera `_bas.png`-storlekarna i `git diff --cached --stat`.**
   Ett fall på tiotals procent betyder raderad kronbas. Promille är
   normalt. (Rättad i v2.8.3.)
4. **`Artefaktlista: N punkter läses in`** ska stå överst i utskriften.
   Saknas raden hittades inte JSON-filen och kapningen uteblir tyst.
5. Overpass strular ibland. Failovern klarar det, men blocket hoppas
   över helt om alla tre speglar faller — då skrivs inga tiles.

## Innan commit
- Verifiera i 3D **och vrid ett varv** — artefakter göms bakom hus.
- Kontrollera att äkta höga hus står kvar: Söder Torn och Skrapan ska
  visa 86,5 m i tilekoll vid Medis.
- Tiles och kod i **separata commits**. Binärer ligger kvar i historiken
  för alltid.
- `tilekoll.html` är otrackad i repotroten — ta inte med den av misstag.

## Publicering
**Pusha bara från GitHub Desktop eller kommandoraden, aldrig genom att
ladda upp filer på github.com.** Uppladdningar via webben syns inte i den
lokala klonen förrän `git fetch`, och grenarna glider isär utan varning.
Det hände 2026-08-29: sju webbcommits låg före den lokala kopian.

## Att lägga till en ny artefakt i `artefakter.json`
1. Mät upp den i tilesen: utbredning, höjd i **båda** kanalerna
   (`bh` = byggnad, `veg` = vegetation), och högsta äkta tak och träd
   inom radien.
2. Sätt `r` så hela strukturen ryms, `minh` med marginal över det äkta.
3. Testa mot tilesen innan körning och notera förväntat pixelantal.
4. Skriv utbredningen i `notering` — den är enda dokumentationen av
   varför pixlarna ser ut som de gör.

En artefakt kan ligga i byggnadskanalen, vegetationskanalen eller båda.
Delar utanför OSM:s byggnadsmask hamnar i vegetationen. **Kontrollera
alltid båda** — en artefakt som bara syns i den ena missas annars.

## Kända artefakter är linjer, inte klumpar
Alla fyra hittills är raka, smala, kraftigt förhöjda linjer som skär
tvärs över byggnadsgränser — sannolikt byggkranar. Ett generellt
"högt och glest"-filter är förkastat, det kapar äkta södermalmstak.
Formbaserad detektor (smal + lång + högt över takmedian) står som
punkt 1 på arbetsplanen.
