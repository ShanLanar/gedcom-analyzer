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
| 🟡 | **FamilySearch-Link** | S | Match-Detail: "🔍 FamilySearch" Button öffnet Namenssuche |
| 🟡 | **Archion/Matricula-Link** | S | Geburtsort-Analyse: direkter Link zu Archion/Matricula für deutschen Ort |
| 🟡 | **GenWiki-GOV-Integration** | S | Schon in Orte-Analyse: ausbauen auf automatische Koordinaten-Abfrage |
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

## Sofort-Sprint (nächste Sitzung)

1. 🔴 Rechtsklick-Kontextmenü Match-Tabelle
2. 🔴 Download-Fortschritts-Dashboard  
3. 🔴 Cookie-Ablauf-Erkennung
4. 🔴 Mütterliche/väterliche Seiten-Zuweisung (wenn Mutter-Kit da)
5. 🔴 MyTrueAncestry CSV-Import (manuelle Variante)
