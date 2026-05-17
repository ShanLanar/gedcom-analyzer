# gedcom-analyzer

Tkinter-GUI für umfassende Genealogie-Analyse einer GEDCOM-Datei.
Lädt einen Stammbaum, berechnet Verwandtschaften, Endogamie, Migration,
Demografie, Wright's F, Namensvarianten und einiges mehr, und exportiert
die Ergebnisse als Excel-Mappe mit ≈ 30 Sheets plus JSON-Zusammenfassung.

## Auf einen Blick

| | |
|---|---|
| **Eingabe** | `family.ged` (GEDCOM 5.5) |
| **Ausgaben** | `genealogy_analysis_complete.xlsx`, `genealogy_results.json` |
| **GUI** | Tkinter, Dark Theme |
| **Sprache** | Python ≥ 3.10 |
| **Dependencies** | nur `openpyxl` |
| **Plattform** | Windows (Launcher `.bat`); läuft aber überall, wo Tk verfügbar ist |

## Installation & Start (Windows)

```cmd
update-and-run.bat
```

Der Launcher klont (oder aktualisiert) das Repo nach `C:\gedcom-analyzer`,
installiert Abhängigkeiten und startet `main.py`. Beim Folgekontakt holt
er nur Updates per `git pull --ff-only`.

Manuell:

```cmd
git clone https://github.com/ShanLanar/gedcom-analyzer.git
cd gedcom-analyzer
pip install -r requirements.txt
python main.py
```

## Verzeichnislayout

```
gedcom-analyzer/
├── main.py             GUI + Task-Registry + Threading
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
