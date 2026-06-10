# Architektur-Konzept — Designschwächen & Wartbarkeit

Stand: Juni 2026 · Ergänzt BACKLOG.md (insb. EPIC 5 „Technische Schulden & Tests")

Dieses Dokument beschreibt, **wie** die bekannten Designschwächen technisch
behoben werden — ohne Big-Bang-Rewrite, in kleinen, jederzeit lauffähigen
Schritten (Strangler-Fig-Prinzip). Die SQLite-Datenbanken sind der stabile
Kern; der Code organisiert sich um sie herum neu.

---

## 1. Leitprinzipien

1. **Kein Rewrite.** Jede Etappe endet mit laufender Software (Tests grün,
   GUI startet, Viewer erreichbar). Umbau und Funktionsänderung nie im
   selben Commit.
2. **Daten vor Code.** Schema-Änderungen sind teurer als Code-Änderungen;
   das Schema (v21) bleibt unangetastet, nur der Zugriff darauf wird
   reorganisiert.
3. **Read-only als technische Garantie**, nicht nur als Konvention:
   Quelldaten-Tabellen werden auf Verbindungsebene schreibgeschützt
   (SQLite-Authorizer), nicht nur per Disziplin.
4. **Proportionalität.** Ein-Entwickler-Projekt, Single-User, Windows-
   Primärumgebung. Bewusst **kein** ORM, kein asyncio-Umbau, kein
   Web-Rewrite der Tk-GUI, kein Docker-Zwang, kein Microservice-Schnitt.
5. **Boy-Scout-Regel statt Refactoring-Sprint:** Der GUI-Monolith wird
   nicht „am Stück" zerlegt, sondern tab-weise — immer dann, wenn an einem
   Tab ohnehin gearbeitet wird. Neues Verhalten entsteht **nie** in
   `app.py`.

---

## 2. Ist-Befunde (messbar)

| # | Befund | Beleg |
|---|--------|-------|
| B1 | GUI-Monolith | `ancestry/gui/app.py`: 6 003 Zeilen, **1 Klasse, 211 Methoden**, 5 Tabs |
| B2 | Config-Namenskollision | Zwei Module heißen `config` (Root + `ancestry/`); `unified.py` behebt das per `sys.modules.pop("config")`-Tanz (dokumentierter Hack in dessen Docstring) |
| B3 | DB-Gott-Klasse | `ancestry/core/database.py`: 1 871 Zeilen; Schema, 10 Inline-Migrationen (`_migrate_v1_v2` …) und ~60 Query-Methoden in einer Klasse; Migrationsmethoden ungeordnet in der Datei verteilt |
| B4 | Keine Paketinstallation | 27 `sys.path`-Manipulationen allein in `ancestry/tools/`; kein `pyproject.toml`; Cross-Paket-Import `ancestry → tasks.names` nur via Pfad-Hack |
| B5 | requirements.txt unvollständig | Deklariert: `openpyxl`, `curl_cffi`. Tatsächlich genutzt: zusätzlich **Flask** (2 Viewer), **Playwright** (6 Dateien), **anthropic** (Vision-Transkription) |
| B6 | Laufzeitdaten im Repo | `mh_all_matches.json` (989 KB) + `mh_indexeddb_matches.json` (819 KB) in `ancestry/tools/` |
| B7 | Pipeline implizit | 23 CLI-Tools; Reihenfolge (scrape → fetch_books → scan → resolution) existiert nur im Kopf; keine Status-Übersicht „welche Quelle ist wie aktuell?" |
| B8 | Entity-Workflow ohne UI-Anbindung | `entity_resolution.py` nur per CLI startbar; der Loop „berechnen → reviewen → erneut berechnen" erfordert Terminal |
| B9 | Keine CI | Kein `.github/workflows/`; 24 Testdateien laufen nur manuell |
| B10 | Pfad-Logik dupliziert | `Path(__file__).resolve().parent.parent.parent` u. ä. in nahezu jedem Tool; Archiv-/DB-Pfade mehrfach unabhängig definiert |

---

## 3. Zielarchitektur

### 3.1 Schichten und Importregeln

```
┌────────────────────────────────────────────────────────────┐
│  UI                                                         │
│   ui/desktop  (Tkinter: unified, AhnenApp, DNA-Tabs)        │
│   ui/web      (Flask: matricula_viewer, entity_browser)     │
├────────────────────────────────────────────────────────────┤
│  Pipeline     (Orchestrierung: Steps, Status, Läufe)        │
├────────────────────────────────────────────────────────────┤
│  Sources      (Adapter je Quelle — schreiben NUR in ihre    │
│                eigenen source_*/match-Tabellen)             │
│   ancestry · myheritage · gedmatch · webtrees · matricula   │
├────────────────────────────────────────────────────────────┤
│  Core         (Domänenlogik, keine UI-Imports)              │
│   db (connection, migrations, repos) · names (Phonetik)     │
│   entity (Resolution) · gedcom · analysis                   │
└────────────────────────────────────────────────────────────┘
```

**Regeln** (per Test erzwungen, s. M8):

- `core` importiert nie aus `ui`, `pipeline` oder `sources`.
- `ui` enthält keine SQL-Strings für Quelldaten-Schreibzugriffe — Viewer
  öffnen die DB grundsätzlich mit Schreib-Scope „entity-layer-only".
- Adapter (`sources/*`) erhalten Schreibrechte ausschließlich auf ihre
  eigenen Tabellen.

### 3.2 Schreib-Scopes technisch erzwingen (Kernidee)

SQLite bietet mit `Connection.set_authorizer()` eine eingebaute Möglichkeit,
Schreiboperationen pro Verbindung auf eine Tabellen-Whitelist zu begrenzen.
Ein kleines Modul `ancestry/core/db/connection.py` stellt Fabriken bereit:

```python
open_ro(path)                      # mode=ro — Analyse, Statistik
open_entity(path)                  # schreibt: entities, entity_assignments,
                                   #   entity_candidates, name_index,
                                   #   source_matrikula_entries (OCR-Korrektur)
open_source(path, source="mh")     # schreibt: nur Tabellen dieser Quelle
open_admin(path)                   # Migrationen, Imports — bewusst explizit
```

Verstößt Code gegen den Scope, wirft SQLite sofort `DatabaseError` — das
Read-only-Prinzip („Rohdaten sind read-only auf Tool-Ebene") wird damit vom
Kommentar zur Laufzeitgarantie. Die Viewer (`matricula_viewer`,
`entity_browser`) steigen auf `open_entity()` um; ein Test belegt, dass eine
Viewer-Verbindung `matches`/`source_webtrees` nicht schreiben **kann**.

### 3.3 Verzeichnis-Zielbild (evolutionär, keine Umbenennungs-Orgie)

Bestehende Pakete (`ancestry`, `tasks`, `lib`) bleiben; sie werden über
`pyproject.toml` installierbar gemacht. Innerhalb von `ancestry` entsteht
Struktur durch **Aufteilen**, nicht Verschieben:

```
ancestry/
  core/
    db/                  ← NEU: aus database.py herausgelöst
      connection.py        (Fabriken + Authorizer-Scopes)
      migrations/          (0001_initial.sql … 0021_*.sql + runner.py)
      repos/               (matches.py, pedigree.py, clusters.py, entities.py)
    entity_resolution.py   (bleibt; nutzt db/)
    analysis/            ← NEU: reine Funktionen aus GUI-Fenstern (M7)
  sources/               ← NEU: dünne Adapter-Fassaden um bestehende Tools
  pipeline/              ← NEU: Step-Registry, Runner, Status (M5)
  gui/
    app.py                 (schrumpft auf Kompositions-Root)
    tabs/                ← NEU: login.py, download.py, matches.py,
                            cluster.py, stats.py
    widgets/             ← NEU: Tabelle, Tooltip, Theme, i18n
  tools/                   (CLI-Einstiege bleiben; Logik wandert nach
                            sources/ bzw. core/)
```

`tasks/names.py` (Kölner Phonetik + Levenshtein) wird nach
`ancestry/core/names.py` **verschoben** und in `tasks/names.py` als
Re-Export belassen — damit entfällt der fragile Root-Import in drei
Matricula-Modulen, ohne die GEDCOM-Analyzer-Seite anzufassen.

---

## 4. Maßnahmenpakete

Aufwand: S ≈ ½ Sitzung · M ≈ 1–2 Sitzungen · L ≈ mehrere Sitzungen, teilbar.

### M1 — Paketierung & Abhängigkeiten ehrlich machen (S) 🔴

- `pyproject.toml` (PEP 621, setuptools): Pakete `ancestry`, `tasks`, `lib`;
  Python ≥ 3.10.
- Abhängigkeiten als Extras gruppiert, damit der Kern schlank bleibt:
  - Basis: `openpyxl`, `curl_cffi`
  - `[viewer]`: `flask`
  - `[scraping]`: `playwright`
  - `[vision]`: `anthropic`
  - `[dev]`: `pytest`, `pytest-cov`, `ruff`
- `pip install -e .[viewer,scraping,vision,dev]` einmalig; danach **alle 27
  `sys.path`-Hacks löschen**.
- Akzeptanz: `python -c "from ancestry.core import database"` aus beliebigem
  Arbeitsverzeichnis; `grep -r "sys.path.insert" ancestry/` → 0 Treffer.
- *Befund aus der Umsetzung (W0):* Zwei Tools (`download_mother_kit.py`,
  `discover_endpoint.py`) hängen an der `import config`-Kette von
  `core/auth|api|scraper` und behalten ihren Hack mit `TODO(M2)`-Marker —
  sie fallen erst mit der Config-Umbenennung in M2. Zusätzlich nötig war
  `ancestry/__init__.py` (war bisher Namespace-Paket) und ein **lazy**
  `ancestry/core/__init__.py` (PEP 562), da die bisherigen Eager-Re-Exports
  auth/api/scraper — und damit config — bei jedem Core-Import mitzogen.

### M2 — Config-Kollision auflösen (S/M) 🔴

Befund B2 ist die fragilste Stelle des Gesamtsystems (Import-Reihenfolge
entscheidet über Verhalten). Aufwand ist klein: nur 3 Dateien importieren
das Root-`config`, 6 das `ancestry/config`.

- `ancestry/config.py` → aufteilen in `ancestry/endpoints.py` (API-URLs,
  der Hauptinhalt) und `ancestry/settings.py` (Laufzeit-Optionen);
  Importe in den 6 Nutzdateien anpassen.
- Root-`config.py` behält seinen Namen (GEDCOM-Analyzer-Seite bleibt
  unberührt).
- `unified.py`: Eager-Import-/`sys.modules.pop()`-Mechanik ersatzlos
  streichen; Docstring-Abschnitt „Technische Besonderheit" entfällt.
- Akzeptanz: `grep -rn 'sys.modules.pop("config")'` → 0; Suite startet mit
  beiden Tabs.

### M3 — Repo-Hygiene & zentrale Pfade (S) 🔴

- Konvention `data/`-Verzeichnis (gitignored) für alles Generierte:
  `data/db/`, `data/cache/`, `data/exports/`, `data/snapshots/`.
- `mh_all_matches.json` / `mh_indexeddb_matches.json`: `git rm --cached`,
  nach `data/snapshots/` verschieben, `.gitignore` ergänzen.
  *History-Rewrite (filter-repo) bewusst optional — nur mit Backup, bringt
  lediglich ~1,8 MB.*
- Neues Modul `ancestry/paths.py`: `ROOT`, `DATA_DIR`, `DB_PATH`,
  `MATRICULA_ARCHIVE` (env-überschreibbar) — ersetzt die ~10 unabhängigen
  `parent.parent.parent`-Konstruktionen schrittweise.
- Akzeptanz: frisches Clone + `pip install -e .` + Start ohne manuelles
  Anlegen von Verzeichnissen.

### M4 — DB-Schicht entkoppeln (M) 🔴

Strangler-Schnitt, die GUI merkt nichts davon:

1. **Migrationen extrahieren:** `ancestry/core/db/migrations/` mit
   nummerierten Dateien (`0001_initial.sql` … `0021_entity_layer.sql`) und
   einem ~50-Zeilen-Runner (liest `schema_version`, wendet fehlende an,
   transaktional). Die Methoden `_migrate_v1_v2` … `_migrate_v10_v11`
   werden 1:1 überführt; `_init_db()` ruft nur noch den Runner.
2. **Verbindungs-Fabriken + Authorizer-Scopes** (s. 3.2) in
   `db/connection.py`.
3. **Repositories:** Query-Methoden thematisch nach `db/repos/` umziehen
   (matches, pedigree, shared/cluster, entities). Die bestehende
   `Database`-Klasse bleibt als **Fassade** erhalten und delegiert — kein
   einziger Aufrufer in `app.py` muss angefasst werden.
- Akzeptanz: Migrationstest „leere DB → v21" grün (Backlog EPIC 5 🔴);
  Authorizer-Test grün; `database.py` < 400 Zeilen (nur Fassade).

### M5 — Pipeline-Orchestrierung (M) 🔴

Adressiert B7 und den ausdrücklichen Wunsch „Crawlen prominenter im Tool
selbst ansteuern, ohne Kommandozeilengefummel".

- `ancestry/pipeline/steps.py`: deklarative Step-Registry —

  ```python
  Step(id="matricula.scan", needs=["matricula.books"],
       produces=["source_matrikula_entries"],
       run=scan_matricula_kirchspiel.main, freshness_days=None)
  ```

  Steps für: Ancestry-Download(s), MH-Import, GEDmatch-Import,
  Webtrees-Crawl, Matricula (scrape/books/scan), GEDCOM-Import,
  `entity.resolve`.
- Tabelle `pipeline_runs` (step_id, started_at, finished_at, status,
  items_processed, log_path) — schreibender Zugriff nur via
  `open_admin`-Scope des Runners.
- CLI: `python -m ancestry.pipeline status` (Tabellen-Counts + letzter
  Lauf je Step, Ampel) · `run <step>` · `run --all --only-stale`.
- Lange Läufe starten als **Subprozess** (nicht Thread): GUI und Flask
  bleiben reaktionsfähig, Logs landen in `data/logs/<step>-<ts>.log`,
  Status wird über `pipeline_runs` gepollt. Abbruch = Prozess-Terminierung,
  Wiederaufnahme dank idempotenter Steps (bereits vorhandenes
  Skip-Verhalten der Scanner/Crawler wird so zum Vertragsbestandteil).
- Akzeptanz: `status` zeigt alle Quellen mit Datenstand; Webtrees-Crawl
  über den Runner gestartet überlebt GUI-Schließen.

### M6 — GUI-Monolith zerlegen (L, tab-weise) 🟡

Reihenfolge nach Änderungshäufigkeit (zuerst, woran ohnehin gearbeitet
wird):

1. `gui/widgets/` extrahieren: Theme/`_build_style`, Tooltip, sortierbare
   Tabelle, Log-Handler — die von allen Tabs genutzten ~400 Zeilen.
2. `gui/state.py`: ein `AppState`-Objekt (db, session, aktueller Kit,
   GEDCOM-Pfad, Settings, i18n-Funktion) ersetzt die impliziten
   `self._*`-Querbezüge zwischen Tabs.
3. Pro Sitzung **ein** Tab nach `gui/tabs/<name>.py` (Klasse
   `XyTab(ttk.Frame)`, Konstruktor erhält `state`). `_build_main()` in
   `app.py` instanziiert nur noch.
4. Analyse-Popups (`_show_surname_analysis`, `_show_place_analysis`,
   `_show_network_graph`, Cluster-Fenster …) wandern zusammen mit M7.
- Harte Regel ab sofort: **kein neuer Code in `app.py`** — neue Features
  entstehen als Modul und werden nur eingehängt.
- Zielmetrik: `app.py` < 800 Zeilen (Komposition, Menü, Shutdown).

### M7 — Geschäftslogik aus der GUI ziehen (M, parallel zu M6) 🟡

Die Analyse-Fenster mischen Query + Berechnung + Tk-Anzeige. Berechnungen
werden reine Funktionen in `ancestry/core/analysis/` (Eingabe: Rows/dicts,
Ausgabe: dicts/lists — kein Tk-Import):

- `surnames.py`, `places.py`, `mrca.py`, `clusters.py`, `network.py`
- Damit werden sie testbar (EPIC 5) und vom Entity-Layer wiederverwendbar
  (z. B. Cluster-Information als Evidenz in `entity_candidates` —
  Backlog-EPIC 3 profitiert direkt).

### M8 — Tests & CI (S→M) 🔴

- `.github/workflows/ci.yml`: `ruff check` + `pytest` (Linux; Tk-Tests
  unter `xvfb-run`, sonst Marker `@pytest.mark.gui` zum Skippen).
- Neue Pflichttests:
  - Migrations-Kette v1→v21 inkl. Beispieldaten (Backlog 🔴),
  - Authorizer-Scopes (Viewer kann Quelltabellen nicht schreiben),
  - Architektur-Test: `core/*` importiert kein `tkinter`/`flask`
    (einfacher AST-/Import-Check, kein Zusatztool nötig),
  - Flask-Viewer-Smoke via `app.test_client()` gegen Fixture-DB.
- Coverage-Messung aktivieren (`--cov=ancestry`), Ziel laut Backlog > 80 %
  für Kernmodule — als Trend, nicht als Gate.

### M9 — Entity-Workflow in die Oberfläche (M) 🔴

- Entity-Browser: Kopfzeilen-Button **„Kandidaten neu berechnen"** →
  startet `entity.resolve` über den Pipeline-Runner (M5), zeigt Fortschritt
  aus `pipeline_runs`, lädt Kandidatenliste nach Abschluss neu.
- Start-Tab der Suite: **Pipeline-Kachel** — je Quelle Datenstand + Knopf
  (Webtrees-Crawl, MH-Import, Matricula-Scan, Resolution). Damit ist das
  „Kommandozeilengefummel" für den Alltagsbetrieb beendet; die CLI bleibt
  für Automatisierung erhalten.

### M10 — Dokumentation & Entscheidungsnotizen (S, fortlaufend) 🟢

- README: Architekturdiagramm (aus 3.1), Datenfluss-Skizze, Pipeline-
  Reihenfolge, Quickstart für frisches Clone.
- `docs/adr/`-Kurznotizen (je ~10 Zeilen): „SQLite-Authorizer statt
  Konvention", „kein ORM", „Subprozess statt Thread für lange Läufe",
  „GEDCOM-Export erzeugt SOUR-Zitate je Entity-Assignment" (Vorgriff auf
  den Export-Epic — genealogisch sauber nach GPS).

---

## 5. Etappenplan

| Welle | Inhalt | Abhängigkeit | Ergebnis |
|-------|--------|--------------|----------|
| **0** (sofort) | M1 + M3 + M10-Start | — | Installierbares Paket, ehrliche Dependencies, sauberes Repo; rein mechanisch, Risiko ≈ 0 |
| **1** | M2 + M4 + M8 | W0 | Config-Hack weg, DB-Schicht entkoppelt, Read-only erzwungen, CI wacht |
| **2** | M5 + M9 | W1 (Scopes, Paket) | Pipeline-Status & Start aus der Oberfläche; Entity-Loop rund |
| **3** (fortlaufend) | M6 + M7, tab-weise | W1 | `app.py` schrumpft pro Sitzung; Logik wird testbar |

Jede Welle endet mit: Tests grün, `unified.py` startet mit beiden Tabs,
beide Flask-Viewer liefern HTTP 200 auf `/`, ein Commit pro logischem
Schritt.

---

## 6. Risiken & Leitplanken

| Risiko | Gegenmaßnahme |
|--------|---------------|
| Ancestry-/MH-Downloads sind nur gegen Live-Systeme voll testbar | Echte API-Antworten (anonymisiert) als Fixtures aufzeichnen; Mock-HTTP-Tests (Backlog EPIC 5 🟡); Download-Pfade in W1–W3 nicht umbauen, nur umziehen |
| Windows-Primärumgebung (FTM-Workflow!) | Keine Unix-only-Annahmen: `pathlib` durchgängig, `xvfb` nur in CI, Subprozess-Start via `sys.executable` |
| Config-Umbau (M2) bricht versteckte Importe | Umbau rein mechanisch in einem Commit; Suite-Start + beide Viewer als Smoke direkt danach |
| Authorizer blockiert legitime Schreiber | Scopes zuerst im „Log-only"-Modus ausrollen (Verstöße loggen statt werfen), nach einer Woche scharf schalten |
| Tab-Extraktion (M6) reißt implizite `self`-Kopplungen | Erst `AppState` (M6.2), dann Tabs; pro Tab ein Commit; GUI-Smoke-Test headless |
| Laufender Webtrees-Crawl (24 299 Personen, ~15 k offen) | W0/W1 fassen weder Crawler noch dessen Tabellen an; Pipeline-Integration (M5) übernimmt den Crawler erst nach Abschluss des Laufs |

---

## 7. Bewusst ausgeschlossen (Anti-Scope)

- **Kein ORM** — das SQL ist hier Asset (Window-Functions, präzise
  Indizes), nicht Schuld.
- **Kein Wechsel weg von SQLite** — Single-User, lokale Datei, WAL reicht.
- **Kein Web-Rewrite der Desktop-GUI** — Tkinter bleibt; Flask nur für die
  beiden Viewer, wo Browser-UI echten Mehrwert hat (Bilder, Verlinkung).
- **Kein asyncio** — Nebenläufigkeit über Subprozesse + DB-Status ist
  robuster und debugbarer.
- **Keine History-Bereinigung als Pflicht** — 1,8 MB rechtfertigen kein
  riskantes Rewrite der Git-Historie.

---

## 8. Messbare Ziele (vorher → nachher)

| Metrik | Ist | Ziel |
|--------|-----|------|
| `ancestry/gui/app.py` | 6 003 Zeilen / 211 Methoden | < 800 Zeilen (Komposition) |
| `ancestry/core/database.py` | 1 871 Zeilen | < 400 (Fassade) + `db/`-Module |
| `sys.path`-Hacks | 27 | 0 |
| Module namens `config` | 2 (kollidierend) | 1 |
| requirements vs. Realität | 2 von ~6 Paketen deklariert | vollständig, als Extras gruppiert |
| Read-only-Garantie Quelldaten | Konvention | Laufzeit-erzwungen (Authorizer) + Test |
| CI | keine | ruff + pytest + Migrations-/Scope-Tests bei jedem Push |
| Pipeline-Transparenz | implizit | `pipeline status` + Start-Tab-Kachel |
| Laufzeitdaten im Repo | 1,8 MB JSON | 0 (unter `data/`, gitignored) |

---

## 9. Nächster konkreter Schritt

**Welle 0** ist ohne Risiko für den laufenden Webtrees-Crawl umsetzbar
(reine Build-/Repo-Mechanik, kein Eingriff in Crawler oder DB) und schafft
die Voraussetzung für alles Weitere: `pyproject.toml` + Extras,
`pip install -e .`, 27 Pfad-Hacks entfernen, `paths.py`, JSON-Snapshots
nach `data/`, README-Quickstart.
