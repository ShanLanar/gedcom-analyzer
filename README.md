# gedcom-analyzer / Genealogie-Suite

Zwei Welten unter einem Dach (gemeinsamer Start: `python unified.py`):

1. **GEDCOM-Analyse** (`main.py`, `tasks/`, `lib/`) — Tkinter-GUI für
   umfassende Auswertung einer GEDCOM-Datei: Verwandtschaften, Endogamie,
   Migration, Demografie, Wright's F, Namensvarianten u. v. m.; Export als
   Excel-Mappe mit ≈ 30 Sheets plus JSON-Zusammenfassung.
2. **DNA & Quellen** (`ancestry/`) — Ancestry-/MyHeritage-/GEDmatch-Matches,
   Webtrees-/Anverwandte-Crawler, Matricula-Kirchenbuch-Erschließung
   (Claude-Vision-Transkription) und eine Entity-Resolution-Schicht, die
   DNA-Matches, Baum-Personen und Kirchenbucheinträge verknüpft. Dazu zwei
   Flask-Viewer: Matricula-Viewer (Port 5000) und Entity-Browser (Port 5001).

Architektur, Schichtenregeln und Refactoring-Fahrplan: **ARCHITEKTUR-KONZEPT.md**.

## Auf einen Blick

| | |
|---|---|
| **Eingabe** | `family.ged` (GEDCOM 5.5), DNA-Match-Exporte, Matricula-Scans |
| **Ausgaben** | `genealogy_analysis_complete.xlsx`, JSON, SQLite (`ancestry_dna.db`) |
| **GUI** | Tkinter (Suite + Analyzer + DNA-Tool), Flask (2 Viewer) |
| **Sprache** | Python ≥ 3.10 |
| **Dependencies** | `pyproject.toml`; Extras: `[viewer]` `[scraping]` `[vision]` `[dev]` |
| **Plattform** | Windows (Launcher `.bat`); läuft aber überall, wo Tk verfügbar ist |

## Installation & Start

```cmd
git clone https://github.com/ShanLanar/gedcom-analyzer.git
cd gedcom-analyzer
pip install -e .[viewer,scraping,vision,dev]
python unified.py          :: Suite (Start + Stammbaum + DNA)
python main.py             :: nur GEDCOM-Analyzer
```

Der Editable-Install (`-e`) macht die Pakete `ancestry`, `tasks` und `lib`
überall importierbar — alle Werkzeuge unter `ancestry/tools/` laufen damit
ohne Pfad-Tricks aus jedem Arbeitsverzeichnis. Wer nur den GEDCOM-Analyzer
braucht: `pip install -e .` (ohne Extras) genügt.

Windows-Launcher wie gehabt:

```cmd
update-and-run.bat
```

## Laufzeitdaten (`data/`)

Alles Generierte liegt unter `data/` (gitignored, Pfade zentral in
`ancestry/paths.py`, per Umgebungsvariablen übersteuerbar):

```
data/snapshots/   manuelle Roh-Exporte (z. B. MyHeritage-JSON)
data/exports/     erzeugte Berichte/GEDCOMs
data/logs/        Werkzeug-Logs
data/cache/       Zwischenstände
```

Die SQLite-Hauptdatenbank `ancestry_dna.db` bleibt im Repo-Root
(`ANCESTRY_DB` zum Übersteuern); Kirchenbuch-Scans liegen unter
`~/matricula_images` (`MATRICULA_ARCHIVE`).

## Quellen-Pipeline (Reihenfolge)

```
Matricula : scrape_matricula_osnabrueck → fetch_matricula_books → scan_matricula_kirchspiel
Bäume     : crawl_webtrees → import_webtrees   ·   GEDCOM-Import
DNA       : Ancestry-Download (GUI) · import_mh_matches · import_gedmatch_matches
Verknüpfen: python -m ancestry.core.entity_resolution --mode candidates
Review    : python ancestry/tools/entity_browser.py   (+ matricula_viewer.py)
```

## Verzeichnislayout

```
gedcom-analyzer/
├── main.py             GUI + Task-Registry + Threading
├── unified.py          Suite-Fenster (Start + Stammbaum + DNA)
├── pyproject.toml      Paket-Definition + Extras
├── ancestry/           DNA-Tool, Quellen-Adapter, Entity-Resolution, Viewer
│   ├── core/           Domänenlogik (database, bridge, entity_resolution …)
│   ├── gui/            DNA-Tkinter-App
│   ├── models/         DnaKit / DnaMatch / SharedMatch
│   ├── tools/          CLI-Werkzeuge (Importer, Crawler, Viewer)
│   └── paths.py        zentrale Pfade (DATA_DIR, DB_PATH, Archiv)
├── data/               Laufzeitdaten (gitignored)
├── config.py           Pfade, Symbole, GUI-Farben, Overrides
├── lib/
│   ├── gedcom.py       Parser, Symbol-Erkennung, Datums-Helfer
│   ├── places.py       Ortsdaten laden + parsen (location_data.json)
│   ├── helpers.py      Verwandtschaft, Familienname, Migrationsstatus
│   ├── cache.py        LRU-Cache für Ahnenpfade
│   └── logger.py       Thread-sicherer Logger
├── tasks/
│   ├── _runner.py      Dispatcher + Shared-State
│   ├── cousins.py      Verwandtschafts-/Cousin-Analyse
│   ├── endogamy.py     Endogamie-Score + Top-Ahnen
│   ├── migration.py    Migrationsrouten, Wellen, Korrelationen
│   ├── military.py     Militärdienst (Symbol-basiert)
│   ├── demographics.py Lebenserwartung, Heiratsalter, Kinder
│   ├── genetics.py     Inzuchtkoeffizient + Pedigree Collapse
│   ├── history.py      Historischer Kontext, Überlebenszeit, Trends
│   ├── names.py        Kölner Phonetik + Levenshtein
│   ├── data_quality.py Datenvollständigkeits-Score
│   ├── network.py      Familiennetzwerk-Centrality
│   ├── osnabrueck.py   Region-Spezialanalyse
│   └── export.py       Excel- und JSON-Export
├── tests/              pytest-Suite
└── update-and-run.bat  Windows-Launcher
```

## GEDCOM-Konventionen

Im `NAME`-Tag erkannte Marker:

| Symbol | Bedeutung                  |
|--------|----------------------------|
| ✠      | Deutscher Soldat           |
| ★      | Anderer Soldat             |
| ⚔      | Gefallen                   |
| ‡      | Linie endet                |
| `mig.` | Migration markiert         |
| `mig.‼1882` o.ä. | Migrationsjahr   |

Zusätzlich werden GEDCOM-`EMIG`- und `IMMI`-Events ausgewertet (mit
`DATE` und `PLAC`), und Standorte werden über `location_data.json`
(Länder, Bundesländer, Aliase, Bezirks-/Provinz-Indikatoren) normalisiert.

## Konfiguration

Default-Werte stehen in `config.py`. Lokale Overrides können per
`config_user.json` (im `BASE_DIR`, default `C:\ahnen\`) gesetzt werden —
die Datei steht in `.gitignore`. Beispiel:

```json
{
  "gedfile": "D:/genealogie/familie.ged",
  "root_id": "@I42@",
  "output_xlsx": "D:/genealogie/output.xlsx"
}
```

Sowohl flache Keys (`"gedfile"`) als auch Top-Level-Dicts (`"FILES": {...}`)
werden akzeptiert; Overrides propagieren konsistent nach `cfg.FILES`,
`cfg.ROOT_ID` usw.

## Tasks

Über die linke Spalte der GUI an-/abwählbar; pflichtig ist nur **GEDCOM
laden**. Reihenfolge wird automatisch nach Gruppe sortiert
(`Vorbereitung → Analysen → Extras → Export`).

Der **Abbrechen**-Button setzt ein `threading.Event`, das die teuren
Loops (Cousins, Inzucht, Migration) kooperativ pollen — Tasks können
also mitten in der Berechnung abgebrochen werden.

## CLI-Modus

Für Batch-Läufe ohne GUI (z.B. Scheduled Task / Cron):

```cmd
python main.py --list-tasks                       :: alle Task-IDs anzeigen
python main.py --batch                            :: alle Default-Tasks ausführen
python main.py --batch --tasks=load_gedcom,migration,export_excel
python main.py --batch --gedfile=D:\ahn\family.ged --root-id=@I42@
```

Exit-Code: `0` = OK, `1` = Tasks meldeten Fehler, `2` = unbekannte Task-ID,
`130` = User-Abbruch.

## HTML-Übersicht

Optionaler Task „HTML-Übersicht" (in der GUI standardmäßig **aus**, im
CLI per `--tasks=export_html` aktivierbar) erzeugt eine selbst­erklärende
HTML-Datei mit Gesamtstatistik, Top-20 Familiennamen, Top-10 Geburtsländern,
Demografie pro Epoche und Migrationswellen. Pfad steuerbar über
`FILES["interactive_html"]` in `config.py`.

## Tests

```bash
python -m pytest tests/
```

Deckt aktuell ab: Datums-Parser, Kölner Phonetik (inkl. B1-Regression),
LRU-Cache, Verwandtschafts-Labels, Migrationsstatus-Memoization,
Wright's F (Lehrbuchfälle), Slot-Deduplizierung in Demografie (B2),
Sheet-Namen-Eindeutigkeit im Excel-Export.

## Status der Reviews

Bekannte Vereinfachungs-/Refactoring-Kandidaten sind im Branch-Verlauf
dokumentiert (Commits `Fix four critical bugs from code review` ff.).
Offene größere Punkte: Auflösung des modul-globalen `_state` in
`tasks/_runner.py` zugunsten eines expliziten `AnalysisContext`, und ein
Architektur-Update der GUI-Tabellen für volldynamische Sheet-Headers.
