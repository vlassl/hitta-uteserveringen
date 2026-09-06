# ARBETSSÄTT – Hitta uteserveringen
*Läs detta först. Uppdaterad 2026-09-06.*

## Rollfördelning
- **Victor redigerar aldrig `preprocess.py` själv.** Claude levererar
  kompletta ersättningsfiler att lägga in, med versionsnumret uppräknat
  i filhuvudet.
- Claude verifierar sina ändringar mot riktiga tiles innan de levereras,
  och anger förväntade siffror så Victor kan jämföra mot sin körning.
- Vid dataanalys: Claude mäter i tilesen och redovisar koordinater och
  utbredning innan någon kod skrivs.
- Kurering (artefakter.json, friade.json) ändras bara efter Victors
  beslut. Git push bara efter klartecken.

## Mappar och flöde
```
arbetsmapp   C:\soldata\arbetsmapp                 <- HÄR KÖRS ALLT
repo         C:\soldata\repo\hitta-uteserveringen
  tiles\     preprocess skriver hit via --out (bygg_om gör det)
  verktyg\   backup av skripten - INTE det som körs
laser        C:\soldata\laz
orto         C:\soldata\orto
```
`artefakter.json` läses från katalogen man står i. **Stå i arbetsmappen.**

**Arbetsgången:** jobba i arbetsmappen, kopiera till `verktyg/` på slutet,
committa. Claude påminner om `verktyg/`-kopieringen vid commit.

## I Cowork
- Claude har inget skal på datorn: läser och skriver filer, kör analyser
  i molnet. Körningar på datorn = en rad att klistra in. Skriv alltid
  utskriften till fil så Claude läser den själv:
  `py bygg_om.py ... 2>&1 | Tee-Object -FilePath korning.log`
- Efter varje filskrivning från Claude: verifiera mot disk (storlek/mtime)
  – skrivningar har rapporterats lyckade utan att landa.
- Datorstyrning ger bara klick i terminaler – oanvändbart här.

## Kommandon som behövs varje gång
PowerShell kör inte skriptfiler (Group Policy `AllSigned`) — klistra in
kommandon direkt, eller kör `.py` via `py`.

Git saknas i PATH. Per session (versionsnumret slås upp, hårdkodas ej):
```powershell
cd C:\soldata\repo\hitta-uteserveringen
$env:Path += ";" + (Get-ChildItem "$env:LOCALAPPDATA\GitHubDesktop\app-*\resources\app\git\cmd" | Sort-Object Name -Descending | Select-Object -First 1).FullName
git config core.pager cat
```

## Omkörning av tiles
`bygg_om.py --artefakter <urval>.json --kor [--orto C:\soldata\orto]`
raderar berörda tiles (även sådana som saknas på disk men står i
index.json) och kör preprocess per sammanhängande område. Urvalsfiler:
`kupol_globen.json`, `broar_test.json`, `alla_tiles.json` (allt).

## Fällor i preprocess
1. **`merge_into` tar `np.maximum`.** Radera alltid berörda tiles före
   omkörning (bygg_om gör det). Flaggkanalen G tas också som max.
2. **Kontrollera `index.json` efteråt:** tile-antalet får aldrig minska
   (550 i dag), fmt 2, tileSize 512, och nyckeln `oversikt` ska finnas —
   utan den är fjärrhorisonten av i appen.
3. **`_bas.png`-storlekar:** ett fall på tiotals procent betyder raderad
   kronbas. Växande filer är normalt (fyllda tak, broar).
4. **`Artefaktlista: N punkter läses in`** ska stå överst i utskriften.
5. Overpass strular ibland; blocket hoppas över om alla speglar faller.
6. Utskriften bryts inte längre av konsolkodningen (bygg_om sätter UTF-8
   för barnprocessen), men skriv utskrifter i skript utan å/ä/ö.

## Innan commit
- Verifiera i 3D **och vrid ett varv**. Töm cache/privat fönster — tiles
  och iframes cachas aggressivt. Djuplänk: `#3d=E,N,lat,lon`.
- Äkta höga hus står kvar: Söder Torn och Skrapan 86,5 m vid Medis.
- Tiles och kod i **separata commits**.
- Otrackat med flit: kandidater.*, efterkontroll.html, ledningscache.json,
  tilekoll.html, korning.log, bro17*.

## Publicering
Pusha från kommandoraden eller GitHub Desktop, aldrig via uppladdning på
github.com (klonen glider isär, hände 2026-08-29).

## Att lägga till en ny artefakt i `artefakter.json`
1. Mät i tilesen: utbredning, höjd i **båda** kanalerna, högsta äkta tak
   och träd inom radien.
2. Sätt `r` så hela strukturen ryms, `minh` med marginal över det äkta.
3. Testa mot tilesen, notera förväntat pixelantal.
4. Skriv utbredningen i `notering`.
