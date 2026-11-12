# Framtida att göra

Det som är planerat men inte byggt i Hitta uteserveringen, uppbyggt ur `ARBETSPLAN.md` (2026-09-06) och git-historiken fram till v0.58. Det som byggs stryks härifrån och står i git-historiken. Redan gjort sedan arbetsplanen: full omkörning med preprocess v2.9.1 (644 tiles), SMHI-väder i appen (v0.52) och kurering av `lagen.json` (v0.56–0.58).

## Tiles och preprocess

- **Bro-kanten vid landfästen** (Victor 2026-09-06): träd och utrustning intill däck under 6 m över mark rörs inte (BRO_FRI). Återstår att granska i 3D vid Skanstull och Liljeholmen om gröna pelare står kvar. *Väntar på Victor* (granskningen).
- **bygg_om: 32 m marginal i bbox** (Victor 2026-09-06): omkörda tiles skiljer sig 0,6–3 m i de yttersta 15 raderna mot grannens strip-merge, eftersom markmodellen saknar grannblockets punkter. Kosmetiskt.
- **Kantremsor** (Victor 2026-09-06): W/H överskattas en tile när punkter ligger under 1 m från bbox-kanten, vilket ger 15 px-slivers i nästa tilekolumn. Harmlöst med symmetrisk merge.
- **Brodäckets undersida ur lasern** (Victor 2026-09-06): i dag schablon 3,0 m (`--brotjocklek`). Klass 1 under däcken ger kantbalk, inte lådans botten (histogram i `brokoll2.txt`). Parkerat.

## Sol och skugga

- **Lövsprickning per art** (Victor 2026-09-06): Stockholms träddatabas → artvis transmission genom kronorna. Broar räknas redan som art med 0 transmission (G=64). *Öppna frågor*: datakälla och hur arterna kopplas till kronorna i tilesen.

## Appen

- **Föreslå korrekt läge** (Victor 2026-09-06): användaren föreslår rätt läge för en uteservering. Inte påbörjat.
- **Fler stadsdelar** (Victor 2026-09-06): fler tiles utöver dagens ~150 km². Kräver mer laser och orto (`hamta_laser.py`, `hamta_orto.py`).
- **Google Places** (Victor 2026-09-06): parkerat.

## Parkerat med flit

- **Takrendering B/C, fasader och fönster, reflekterad sol, intensitetstexturer, SBK:s trädkronraster** (Victor 2026-09-06): parkerat.
- **Generellt "högt och glest"-filter** (Victor 2026-09-06): parkerat, eftersom det kapar äkta tak.

## Verktyg

- **Tre skript bara i arbetsmappen** (2026-11-12): `bygga_oversikt.py`, `kapa_artefakter.py` och `orto_kolla.py` finns i `C:\soldata\arbetsmapp` men inte i `verktyg/`. *Väntar på Victor*: ska de in i git?
