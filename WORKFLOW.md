# Workflow — Daten sammeln, importieren, auswerten

Diese Datei beschreibt die komplette Pipeline: **welches Tool wann**, was es
voraussetzt und das genaue Kommando. Alle Werkzeuge lassen sich auch ohne
Kommandozeile über das **🔧 Tools**-Fenster im Viewer starten
(`python viewer.py` → Knopf „🔧 Tools"). Jeder Tab dort enthält dieselben
Erklärungen wie hier.

> Tipp: Tools mit Internet-/Browser-Zugriff (Crawler, Matricula, MyHeritage)
> können lange laufen. Sie sind **fortsetzbar** — der Fortschritt steht in den
> Datenbanken. Abbrechen mit „■ Stop" und später weitermachen ist unproblematisch.

---

## Überblick der Pipeline

```
A) Stammbaum     Webtrees-Crawl  →  Import Webtrees→DB
B) Kirchenbücher Katalog (1x)    →  Bücherverzeichnis  →  Seiten-Scan  →  Viewer
C) DNA           MyHeritage-Liste →  Shared Matches      →  Import CSV/TSV
D) Auswertung    Entity-Browser / xref-Review
```

Zentrale Datenbank: `ancestry/ancestry_dna.db` (Personen, Matches, Korrekturen).
Importe gleichen gegen das GEDCOM ab und **überschreiben nichts**.

---

## A) Stammbaum (Webtrees)

### 1. Crawlen
Lädt öffentliche Webtrees-Bäume (z. B. `stammbaum.anverwandte.info`) Person für
Person nach `ancestry/tools/webtrees_crawl.db`. Höflich: 4–6 s Pause,
max. 300 Seiten/Lauf, fortsetzbar.

```bash
python ancestry/tools/crawl_webtrees.py crawl --profile anverwandte --discover
```

- `--discover` — kompletten Baum aufdecken (neuen Personen folgen)
- `--reset-stale` — veraltete Seiten erneut abrufen
- Profile anzeigen: `python ancestry/tools/crawl_webtrees.py profiles`

### 2. In die DB importieren
```bash
python ancestry/tools/import_webtrees.py
```
- `--no-link` — ohne GEDCOM-Abgleich importieren

### 3. (optional) Als GEDCOM-Datei exportieren
Schreibt die gecrawlten Personen samt abgeleiteten Familien als `.ged`-Datei
(z. B. um sie mit GED Slim zu verkleinern oder in andere Programme zu laden).
Auch direkt im Viewer: Tab „Webtrees Crawler" › „💾 GEDCOM exportieren".
```bash
python ancestry/tools/crawl_webtrees.py export-gedcom --profile anverwandte --out anverwandte.ged
```
- `--db <pfad>` — bestimmte Crawl-DB statt Profil
- `--tree-source <name>` — nur Personen einer Quelle exportieren

---

## B) Kirchenbücher (Matricula-Online, Bistum Osnabrück)

### 0. Pfarrei-Katalog — **einmalig**
Baut die Liste aller Pfarreien auf (`matricula_parishes.db`). Erst danach ist
das Pfarrei-Auswahlfeld im Tools-Fenster gefüllt.
```bash
python ancestry/tools/scrape_matricula_osnabrueck.py
```
- `--visible` — Browser sichtbar, `--pause 2.0` — langsamer

### 1. Bücherverzeichnis holen
Welche Taufe-/Heirat-/Tod-Bücher (mit Jahresbereichen) hat eine Pfarrei?
```bash
python ancestry/tools/fetch_matricula_books.py --parish ostercappeln
```
Ohne `--parish` werden alle Pfarreien abgearbeitet.

### 2. Seiten scannen (Claude Vision)
Lädt die Seitenbilder und transkribiert die Kurrentschrift nach
`source_matrikula_entries`. **Voraussetzung:** Umgebungsvariable
`ANTHROPIC_API_KEY`.
```bash
python ancestry/tools/scan_matricula_kirchspiel.py --parish ostercappeln
```
- `--book-type Taufe|Heirat|Tod|Konfirmation` — auf einen Buchtyp begrenzen
- `--year-from 1780 --year-to 1850` — Jahresbereich
- `--retranscribe` — bereits geladene Bilder neu transkribieren (kein Web-Abruf)
- `--dry-run` — nur zeigen, was getan würde
- `--visible`, `--pause` — Debugging

### 3. Ansehen & korrigieren (Web-Viewer)
```bash
python ancestry/tools/matricula_viewer.py        # http://127.0.0.1:5000
```
Seitenbild + Transkript nebeneinander; manuelle Korrekturen werden als
`corrected_by='human'` gespeichert. Scans lassen sich auch direkt aus dem
Viewer starten.

---

## C) DNA (MyHeritage / GEDmatch)

### Voraussetzung für MyHeritage
Angemeldetes Chrome mit Remote-Debugging starten:
```
chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\chrome-cdp"
```

### 1. Matchliste herunterladen
```bash
python ancestry/tools/download_myheritage.py
```
- `--only-new` — nur neue Matches
- `--no-segments` — schneller, ohne Segmentdetails
- `--min-cm 15` — Schwelle (Standard 8)

### 2. Gemeinsame Matches (shared matches)
Pro Match die „Gemeinsame DNA-Matches" laden. Braucht eine Match-CSV
(z. B. Export aus dem Genealogy-Assistant).
```bash
python ancestry/tools/fetch_mh_shared_matches.py --csv pfad/zur/match_list.csv
```
- `--min-cm 50`, `--limit 100`, `--visible`, `--pause 2.0`

### 3. Importe in die DB
```bash
python ancestry/tools/import_mh_csv.py    pfad/zur/MyHeritage_Match_List.csv
python ancestry/tools/import_gedmatch.py  pfad/zur/gedmatch_export.txt
```
- `--kit <GUID>` — Kit-Zuordnung überschreiben

### WikiTree (optional)
```bash
python ancestry/tools/import_wikitree.py Kovermann-123 --depth 6
```

---

## D) Auswertung & Pflege

### Entity-Browser (Web-UI)
Alle Quellen (DNA, Baum, Matricula, Webtrees) zusammengeführt; Kandidaten
bestätigen/ablehnen.
```bash
python ancestry/tools/entity_browser.py          # http://127.0.0.1:5001
```

### Dubletten prüfen (CLI)
```bash
python ancestry/tools/xref_review.py -i          # interaktiv (j/n/q)
python ancestry/tools/xref_review.py --confirm <ID_A> <ID_B>
```

### Analysen & Exporte (GEDCOM-Analyzer)
```bash
python main.py --list-tasks
python main.py --batch --tasks cousins,export_excel --gedfile <pfad> --root-id <id>
```

---

## Tool-Übersicht (Kurzreferenz)

| Tool | Zweck | Im Tools-Fenster |
|------|-------|------------------|
| `crawl_webtrees.py` | Öffentliche Bäume crawlen | Webtrees Crawler |
| `import_webtrees.py` | Crawl → DB | Importe |
| `scrape_matricula_osnabrueck.py` | Pfarrei-Katalog (1x) | Matricula · Schritt 0 |
| `fetch_matricula_books.py` | Bücherverzeichnis | Matricula · Schritt 1 |
| `scan_matricula_kirchspiel.py` | Seiten-Scan (Claude Vision) | Matricula · Schritt 2 |
| `matricula_viewer.py` | Web-Viewer (5000) | Web-Viewer |
| `download_myheritage.py` | MH-Matchliste | MyHeritage · Schritt 1 |
| `fetch_mh_shared_matches.py` | MH shared matches | MyHeritage · Schritt 2 |
| `import_mh_csv.py` | MH-CSV → DB | Importe |
| `import_gedmatch.py` | GEDmatch-TSV → DB | Importe |
| `import_wikitree.py` | WikiTree → DB | Importe |
| `entity_browser.py` | Entity-Browser (5001) | Web-Viewer |
| `xref_review.py` | Dubletten bestätigen | (CLI) |
