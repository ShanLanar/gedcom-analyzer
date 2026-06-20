# Ancestry DNA Tool — Priorisiertes Backlog

Legende: 🔴 Hoch · 🟡 Mittel · 🟢 Niedrig | Aufwand: S=klein M=mittel L=groß XL=sehr groß

---

## EPIC 1 — Bedienbarkeit & UX (Quick Wins)

| Prio | Titel | Aufwand | Beschreibung |
|------|-------|---------|--------------|
| 🔴 | **Keyboard-Navigation im Match-Tab** | S | Tab/Enter zwischen Suche, Tabelle, Detail-Panel; Esc leert Suche |
| 🔴 | **Status-Bar Fortschrittsring** | S | Kleiner animierter Kreis statt Text-"Bereit." während Download läuft |
| 🔴 | **Download-Tab: Zeitschätzung** | S | Nach Start: "~4 Min verbleibend" basierend auf matches/sec-Rate |
| 🔴 | **Drag-and-Drop Cookie-Datei** | S | Cookie-JSON-Datei direkt in Login-Tab fallen lassen |
| 🟡 | **Rechtsklick-Kontextmenü Match-Tabelle** | M | Öffne in Ancestry, Namenskarte, Kopiere GUID, Markiere/Entmarkiere |
| 🟡 | **Spaltenbreite anpassbar und gespeichert** | M | Match-Tabelle: Spaltenbreite via Drag, persistent in settings |
| 🟡 | **Schnellfilter-Chips** | M | Oberhalb der Tabelle: klickbare Chips "Markierte", ">200 cM", "Mit Baum" |
| 🟡 | **Dunkelmodus** | M | Dark-Theme-Option; Farben aus COLORS-Dict tauschen |
| 🟢 | **Tooltips auf allen Buttons** | S | `tooltip(widget, text)` Helfer; alle Buttons mit Hover-Hinweis |
| 🟢 | **Tastenkürzel-Übersicht** | S | Hilfe-Menü → "Tastenkürzel" Dialog |

---

## EPIC 2 — Download & Daten-Qualität

| Prio | Titel | Aufwand | Beschreibung |
|------|-------|---------|--------------|
| 🔴 | **Download-Fortschritts-Dashboard** | M | Neuer Tab-Bereich zeigt: X Matches, Y mit Pedigree, Z mit Shared, fehlende |
| 🔴 | **Inkrementeller Pedigree-Update** | M | Nur Matches aktualisieren deren `pedigree_fetched` > 30 Tage alt ist |
| 🔴 | **Cookie-Ablauf-Erkennung** | S | HTTP-403/401 → automatische Warnung "Cookies abgelaufen, neu einloggen" |
| 🟡 | **Parallele Shared-Match-Downloads** | L | Concurrent fetches mit konfigurierbarem Thread-Pool (aktuell sequenziell) |
| 🟡 | **Download-Queue mit Pause/Fortsetzen** | L | Stop speichert Position; nächster Start macht weiter |
| 🟡 | **Automatischer Retry bei Ratelimit** | M | 429-Responses → exponentielles Backoff statt Abbruch |
| 🟢 | **Download-Protokoll exportieren** | S | Log-Text als .txt speichern via Kontextmenü im Log-Widget |

---

## EPIC 3 — Analyse

| Prio | Titel | Aufwand | Beschreibung |
|------|-------|---------|--------------|
| 🔴 | **Mütterliche/väterliche Seiten-Zuweisung** | L | Wenn Mutter-Kit vorhanden: automatisch matches als "maternal" / "paternal" / "beide" klassifizieren |
| 🔴 | **Phasing-Dashboard** | L | Visualisierung: welcher Cluster ist welcher Großelternteil (4-Quadranten) |
| 🔴 | **MyTrueAncestry-Import** | M | CSV/JSON-Import der paläogenetischen Scores; Triangulation mit DNA-Matches |
| 🔴 | **cM-Zeitreihe** | M | Wenn mehrere Kits vorhanden: Änderung der Match-cM über Zeit (Vergleich Downloads) |
| 🟡 | **Endogamie-Score-Berechnung** | M | Automatische Kennzeichnung von Matches mit Endogamie-Verdacht (hohe Segmentzahl + kurze Segs) |
| 🟡 | **MRCA-Karte** | M | Aus Cluster-Vorfahren-Orten: Leaflet-Karte aller MRCA-Kandidaten |
| 🟡 | **Pedigree-Lücken-Analyse** | M | Für jeden Match: welche Generationen fehlen noch (Gen 3 vorhanden, Gen 4 nicht) |
| 🟡 | **Triangulations-Bericht PDF** | L | Export eines Forschungsberichts pro Cluster als druckbares PDF |
| 🟢 | **Ähnlichkeits-Matrix** | M | Treeview-Heatmap: wie ähnlich sind zwei Matches' Vorfahren (Nachnamen-Overlap) |
| 🟢 | **Zeitachsen-Ansicht** | M | Geburtsjahre der Vorfahren als horizontale Timeline pro Match |

---

## EPIC 4 — Export & Integration

| Prio | Titel | Aufwand | Beschreibung |
|------|-------|---------|--------------|
| 🔴 | **GEDCOM-Export** | L | Gemeinsame Vorfahren als GEDCOM exportieren (für andere Tools) |
| ✅ | **FamilySearch-Link** | S | Erledigt: `tasks/familysearch.py` + `tasks/externe_quellen.py` |
| ✅ | **Archion/Matricula-Link** | S | Erledigt: `tasks/externe_quellen.py` + `tasks/gov_lookup.py` |
| ✅ | **GenWiki-GOV-Integration** | S | Erledigt: `tasks/gov_lookup.py` (Nominatim + Wikidata GOV-ID + Archiv-Links) |
| 🟡 | **MyTrueAncestry API-Login** | XL | Automatischer Login + Datenabruf (erfordert Reverse-Engineering der API) |
| 🟢 | **GedMatch-Export** | M | Cluster-Ergebnisse als GedMatch-kompatibles Format |
| 🟢 | **Gramps XML Export** | M | Gemeinsame Vorfahren als Gramps-XML für direkten Import |

---

## EPIC 5 — Technische Schulden & Tests

| Prio | Titel | Aufwand | Beschreibung |
|------|-------|---------|--------------|
| 🔴 | **GUI-Smoke-Tests (ohne Display)** | M | pytest + headless Tkinter (`Tk.__init__` mocken) für alle Tab-Builder |
| 🔴 | **Settings-Persistenz testen** | S | test_settings.py: save/load UI-Settings, lang-Setting |
| 🔴 | **Datenbankmigrationen testen** | M | Jede Migration einzeln testen (v1→v2 ... vN) |
| 🟡 | **Scraper-Tests mit Mock-HTTP** | L | Vollständige Mock-Responses für alle API-Endpunkte |
| 🟡 | **Performance-Benchmarks** | M | pytest-benchmark: get_matches(1000), get_shared_clusters(5000) |
| 🟡 | **Codeabdeckung messen** | S | `pytest --cov=ancestry --cov-report=html` einrichten; Ziel >80% |
| 🟢 | **Type-Checking (mypy)** | M | mypy für alle Kernmodule; schrittweise strict-Modus |
| 🟢 | **Logging-Konfiguration** | S | Strukturiertes JSON-Logging optional aktivieren |

---

## EPIC 6 — MyTrueAncestry-Integration (längerfristig)

| Prio | Titel | Aufwand | Beschreibung |
|------|-------|---------|--------------|
| 🟡 | **MTA-Daten-Import (CSV)** | M | Manuell exportierte Scores einlesen; Benutzer wählt "Base 1" und "Base 2" |
| 🟡 | **Triangulation Basis 1 vs. Basis 2** | L | Für jede paläogenetische Komponente: Anteil von Mutter (Base 2) vs. Vater |
| 🟡 | **Korrelation MTA ↔ Cluster** | L | Welche Ancestry-Cluster korrelieren mit welchen MTA-Populationen? |
| 🟢 | **Populationsübersicht-Tab** | M | Neuer Tab "Paläogenetik": Donut-Chart der MTA-Komponenten, Differenz Mutter/Kind |

---

## Bestandsaufnahme 2026-06 (Code-verifiziert)

Eine Scrum-Bestandsaufnahme hat das Backlog gegen den realen Code geprüft.
Viele „offene" Punkte waren längst implementiert. Bereits **fertig** (aus dem
Backlog zu streichen):

- EPIC 1: Dark-Mode, Schnellfilter-Chips, Rechtsklick-Kontextmenü, Download-ETA
- EPIC 2: Cookie-Ablauf-Erkennung (401/403), 429-Retry mit Backoff
- EPIC 3/6: Maternal/Paternal-Seitenzuweisung, MyTrueAncestry-CSV-Import,
  Zeitachsen-Ansicht
- EPIC 4: GEDCOM-Export, FamilySearch-Links

### Sprint erledigt (diese Sitzung)

1. ✅ Coverage in CI aktiviert (`--cov`) + `[tool.coverage]`-Konfiguration
2. ✅ Inkrementeller Pedigree-Refresh: Zeitstempel (Migration 0023) +
   `max_age_days` (30-Tage-Logik)
3. ✅ Core-API-Tests mit Mock-HTTP (`_session`/`_matches`/`_pedigree`):
   0 % → 42 % Coverage im Download-Kern
4. ✅ Headless GUI-Smoke-Tests für alle 8 Tab-Builder (Fake-tkinter)
5. ✅ Phasing-Dashboard: 4-Quadranten-Visualisierung der Großelternlinien

### Sprint 2 erledigt (gleiche Sitzung)

1. ✅ MRCA-Karte: Leaflet-HTML der Vorfahren-Geburtsorte (Cluster-Tab-Button)
2. ✅ Pedigree-Lücken-Analyse: getestete Kernlogik (`analyze_pedigree_gaps`)
   in die **bestehende** Analyse-Menü-View integriert (Frontier-Spalten);
   versehentliche Dublette wieder zurückgebaut
3. ✅ Inkrementeller Pedigree-Refresh als Checkbox im Download-Tab verdrahtet
4. ✅ Einzelne DB-Migrationen getestet (v_n→v_{n+1}, parametrisiert)
5. ✅ GEDmatch-Export (One-to-Many-TSV, round-trip zum Import; Download-Tab-Button)
6. ✅ MTA Eltern-Vergleich Basis 1 vs. Basis 2 (`classify_parental_origin`,
   Button im MTA-Fenster)
7. ✅ UX: `tooltip(widget, text)`-Helfer + Tastenkürzel-Hilfe (Hilfe-Menü);
   Tooltips an Cluster-/Download-Buttons

> Hinweis MTA↔Cluster-Korrelation: mit den vorhandenen Daten (ein
> Eigenprofil, keine Per-Match-Populationen) **nicht sauber fundierbar** —
> aus dem Sprint genommen. Stattdessen der tragfähige Eltern-Vergleich (6).

8. ✅ Tooltips auf die primären Buttons aller Tabs ausgerollt (Login, Matches,
   Cluster, Stats, Persons, Matricula, Download)

### Sprint 3 erledigt (gleiche Sitzung) — Punkte 1–6

1. ✅ Live-Sprachwechsel für statische Tab-Labels (`register_lang`, 29 Widgets)
2. ✅ Triangulations-Bericht als druckbares HTML/PDF (`triangulation_report`)
3. ✅ Endogamie-Verdacht automatisch kennzeichnen (`auto_flag_endogamy`)
4. ✅ `test_viewer_smoke` mit `importorskip("flask")` — Suite überall grün
5. ✅ mypy schrittweise (7 Kernmodule, CI-Job `typecheck`)
6. ✅ Tooltips auf alle „…"-Dateiwähler-Buttons

### Sprint 4 erledigt (2026-06-20) — Schlecht erschlossene Online-Daten

Expertengremium (Archivar, DNA-Genetikerin, Data Engineer, Historiker,
Datenschutzjurist) → folgende Tasks realisiert:

1. ✅ **GOV-Orte-Lookup** (`tasks/gov_lookup.py`)
   - Nominatim (OpenStreetMap) → Koordinaten für jeden GEDCOM-Ort
   - Wikidata SPARQL → GOV-ID (P3519), Diözese, Kirchspiel
   - Archiv-Links: Matricula, Archion, ArcInSys NI, Archivportal-D, GOV
   - Sheet „GOV-Orte & Archiv-Links"

2. ✅ **Grabstein-Suche** (`tasks/grabstein.py`)
   - BillionGraves, FindAGrave, Grabstein-Projekt, Volksbund VDK,
     Steinheim-Institut (jüdische Friedhöfe)
   - Konfidenz-Klasse HOCH/MITTEL/NIEDRIG
   - Sheet „Grabstein-Suche"

3. ✅ **Externe Recherche-Links** (`tasks/externe_quellen.py`)
   - 27 plattform-spezifische Links pro Person
   - Zeitraum-basiert: Kirchenbücher (<1874) / Standesamt (≥1874)
   - Auswanderer-, Militär-, Presse-, Adressbuch-, Linked-Data-Links
   - Sheet „Externe Recherche-Links"

4. ✅ **DFD-Namenforschung** (`tasks/dfd_lookup.py`)
   - Digitales Familiennamenwörterbuch Deutschlands (namenforschung.net)
   - URL-Modus (immer) + optionaler 2-Stufen-HTML-Scraper
   - Häufigkeit, Rang, Namentyp, Etymologie, Schreibvarianten
   - Varianten → `_state["dfd_variants"]` für Phonetik-Matching
   - K/C/V/W-Phonetik-Äquivalenz in `_similar_enough()`
   - Sheet „DFD-Familiennamen"

### Sprint 5 erledigt (2026-06-20) — Expertengremium Sprint 2

Gremium: Archivar, DNA-Genetikerin, Data Engineer, Historiker, Datenschutzjurist

1. ✅ **WikiTree-Profil-Suche** (`tasks/wikitree_lookup.py`)
   - Öffentliche API (https://api.wikitree.com/api.php, kein API-Key)
   - Für jeden Ahnen: Such-URL (immer) + optionaler API-Abruf
   - Konfidenz HOCH/MITTEL/NIEDRIG (Name + Geburtsjahr ± 2 J.)
   - Sheet „WikiTree-Profile" im Excel-Export (13 Spalten)

2. ✅ **cM-Zeitreihe im Stats-Tab**
   - Query auf `fetched_at` in `matches`-Tabelle → Neuzugänge + Ø cM pro Tag
   - Canvas-Linien-/Balken-Chart (blaue Balken = Match-Anzahl, orangene Linie = Ø cM)
   - Automatisch nach jedem Stats-Refresh neu gezeichnet

3. ✅ **Download-Protokoll exportieren** (Rechtsklick-Kontextmenü auf Log)
   - „Alles kopieren" / „Als .txt speichern …" / „Log leeren"

4. ✅ **Drag-and-Drop Cookie-Datei** (`login.py`)
   - Drop-Zone für `.json`-Dateien (wenn tkinterdnd2 installiert; sonst Fallback)
   - Pfad wird gesetzt → direkter Login möglich

5. ✅ **DFD-Varianten in `bridge.py`/`treematch.py` einbinden** (Sprint 4b)
   - `expand_surname_variants()` in `_text.py`
   - Varianten-Schritt in `matching.py` Kandidaten-Aufbau
   - JSON-Persistenz in `tasks/dfd_lookup.py`

6. ✅ **Unit-Tests für alle 5 Online-Module** (95 → 112 Tests)
   - gov_lookup, grabstein, externe_quellen, dfd_lookup, wikitree_lookup

## Sofort-Sprint (nächste Sitzung)

1. 🟢 Live-Switch auf restliche on-demand-Dialog-Labels ausweiten
2. 🟢 mypy-Abdeckung erweitern (weitere Kernmodule aufnehmen, sobald sauber)
3. 🟢 i18n-Audit-Tool auf AST umstellen (fängt auch messagebox-Nachrichten)
4. 🟡 cM-Zeitreihe: „Neu seit letztem Download"-Kennzeichnung in Match-Tab
5. 🟡 WikiTree-Profile direkt im Matches-Detailpanel verlinken (Bridge-Tab)
6. 🟡 Gramps XML Export (EPIC 4 🟢 M) — Gramps 5.1 XML für direkten Import

> ✅ Erledigt (diese Sitzung): GESAMTE GUI zweisprachig (179 → 0 hartkodierte
> Strings) + Live-Sprachwechsel, Guard-Test + Audit-Tool, Tooltip-Helfer +
> vollständige Ausrollung, Tastenkürzel-Hilfe, Triangulations-PDF, Endogamie-
> Auto-Flag, mypy-Gate. Davor: Phasing-Dashboard, MRCA-Karte, Pedigree-Lücken,
> GEDmatch-Export, MTA-Eltern-Vergleich, inkrementeller Pedigree-Refresh,
> Core-API-Tests, GUI-Smoke-Tests, einzelne Migrations-Tests, Coverage-CI.
