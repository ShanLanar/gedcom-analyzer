# -*- coding: utf-8 -*-
"""
tasks/help_data.py — Strukturierte Hilfetexte pro Task.

Wird vom Hilfe-Fenster der GUI gelesen (main.py → _open_help).
Schema pro Eintrag:
    {
        "title":   Titel,
        "group":   Vorbereitung | Analysen | Extras | Export,
        "purpose": Zweck in 1-2 Sätzen,
        "input":   Welche GEDCOM-Felder/Vorgänger-Tasks gebraucht werden,
        "output":  Welche Excel-Sheets / Dateien erzeugt werden,
        "details": Ausführliche Beschreibung,
        "tips":    Optional: Tipps zur Nutzung,
    }
"""

HELP_ENTRIES: dict = {
    # ── Vorbereitung ───────────────────────────────────────────────────────────
    "load_gedcom": {
        "title":   "GEDCOM laden",
        "group":   "Vorbereitung",
        "purpose": "Liest die Stammbaumdatei (.ged oder .ftm) und bereitet alle Daten für die Analysen vor.",
        "input":   "Stammbaumdatei (GEDCOM 5.5 oder Family Tree Maker .ftm). Auto-Erkennung des Formats anhand SQLite-Header bei .ftm.",
        "output":  "Befüllt den State mit individuals + families. Erkennt Militär-Symbole ✠ ★ ⚔ ‡ und mig.-Marker im Namen. Liest EMIG/IMMI-Events.",
        "details": "Pflicht-Task. Ohne ihn können keine anderen Analysen laufen. Lädt auch die location_data.json für die Orts-Hierarchie-Parsung. Bei Familienarchiven > 100k Personen dauert das Einlesen 5–15 Sekunden.",
        "tips":    "Wird der Pfad in der UI geändert, wird er nach Klick auf 'Starten' persistiert (config_user.json). Beim nächsten Start ist er vorausgewählt.",
    },
    "load_cache": {
        "title":   "State-Cache laden (inkrementell)",
        "group":   "Vorbereitung",
        "purpose": "Lädt einen zuvor gespeicherten Analyse-State und überspringt alle Vor-Berechnungen, wenn die GEDCOM unverändert ist.",
        "input":   "~/.ahnen-cache.pkl (von 'State-Cache speichern' erzeugt). Vergleicht SHA-256 der aktuellen GEDCOM mit dem im Cache.",
        "output":  "Ersetzt den kompletten _state mit dem zwischengespeicherten Stand.",
        "details": "Workflow für Wiederholungs-Läufe: einmal komplett rechnen → 'State-Cache speichern' aktivieren → beim nächsten Run nur 'State-Cache laden' + gewünschte Export-Tasks aktivieren. Spart bei 130k Personen ~90 Sekunden.",
        "tips":    "Bei GEDCOM-Änderung wird der Cache automatisch verworfen und ein komplettes Re-Rechnen erforderlich.",
    },

    # ── Analysen ──────────────────────────────────────────────────────────────
    "cousins": {
        "title":   "Verwandtschafts-/Cousin-Analyse",
        "group":   "Analysen",
        "purpose": "Berechnet für jede mit der Root-Person verwandte Person die exakte Verwandtschaftsbezeichnung.",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "Sheet 'Cousin Beziehungen' — ein Eintrag pro Verwandtem. Bei 130k-Tree typisch 60–70k Einträge.",
        "details": "Nutzt BFS-Algorithmus, ermittelt für jeden Verwandten die Tiefe zum jüngsten gemeinsamen Ahnen mit Root und übersetzt das in deutsche Labels: Elternteil, Großelternteil, Cousin 1.–N. Grades, Urgroßonkel, etc.",
        "tips":    "Wichtige Grundlage für DNA-cM-Schätzung und MRCA-Finder — diese Tasks bauen auf den Cousin-Ergebnissen auf.",
    },
    "endogamy": {
        "title":   "Endogamie & Top-Ahnen",
        "group":   "Analysen",
        "purpose": "Identifiziert Orte mit hoher Endogamie und die wichtigsten Stamm-Ahnen.",
        "input":   "individuals + families + ROOT_ID + Ortsdaten.",
        "output":  "Sheets 'Endogamie Scores' (pro Ort), 'Top Ahnen' (wichtigste Stamm-Ahnen ohne weitere Vorfahren).",
        "details": "Endogamie-Score pro Ort = 1 - (distinkte Nachnamen / Personen). Top-Ahnen sind Vorfahren, deren eigene Eltern unbekannt sind — typische Startpunkte für Recherche.",
    },
    "migration": {
        "title":   "Migrationsrouten + Wellen + Korrelation",
        "group":   "Analysen",
        "purpose": "Vollständige Migrationsanalyse: einzelne Routen, komprimierte Familien-Routen, Wellen über Zeit, demografische Korrelationen.",
        "input":   "individuals (BIRT.PLAC, EMIG, IMMI, mig.-Marker) + families + Ortsdaten.",
        "output":  "Vier Sheets: 'Migrationsrouten Detail', 'Migrationsrouten Compressed' (Familien-Aggregate), 'Migrationswellen', 'Korrelation Migration-Demografie'.",
        "details": "Erkennt Migrationen über: (1) EMIG/IMMI-Events, (2) mig.-Marker im Namen, (3) Geburts- vs. Sterbeort in verschiedenen Ländern. Wellen werden über DBSCAN-ähnliches Zeit-Clustering identifiziert.",
    },
    "military": {
        "title":   "Militäranalyse",
        "group":   "Analysen",
        "purpose": "Detailanalyse aller militärischen Einträge: Streitkraft, Kriegszuordnung, Sterbealter-Klassen.",
        "input":   "individuals mit Militär-Symbolen ✠ (Deutsche), ★ (Andere), ⚔ (Gefallene).",
        "output":  "Sheet 'Militärdienst Details' und 'Symbol-Statistik' (Gesamt-Counts pro Symbol).",
        "details": "Klassifiziert Sterbealter (kurz ≤25 J. / mittel 26–35 / lang >35), ordnet Sterbedaten möglichen Kriegen zu (Dreißigjähriger Krieg, Napoleonische Kriege, Deutsch-Französisch, WWI, WWII).",
    },
    "demographics": {
        "title":   "Demografische Statistiken",
        "group":   "Analysen",
        "purpose": "Lebenserwartung, Heiratsalter, Kinderzahl, Kindersterblichkeit pro Epoche & Geschlecht.",
        "input":   "individuals mit Geburts-/Sterbedaten + families.",
        "output":  "Sheet 'Demografische Statistik' (Epoche × Geschlecht) und 'Umfassende Statistiken' (Gesamtkennzahlen).",
        "details": "Epochen: vor 1800, 1800–1850, 1850–1900, 1900–1950, nach 1950. Berechnet Median, Min, Max für Lebensspannen.",
    },
    "surnames": {
        "title":   "Familiennamen & Geburtsländer",
        "group":   "Analysen",
        "purpose": "Top-100 Familiennamen und Top-Geburtsländer mit Zeitspannen.",
        "input":   "individuals.",
        "output":  "Sheets 'Familiennamen Häufigkeit', 'Geburtsland Verteilung'.",
        "details": "Spaltet auch nach Geschlecht und gibt Geschlechterverteilung pro Nachname/Land aus.",
    },
    "genetics": {
        "title":   "Genetik (Inzucht + Pedigree Collapse)",
        "group":   "Analysen",
        "purpose": "Wright's F-Koeffizient pro Person, Pedigree-Collapse pro Generation, DNA-cM-Schätzung pro Verwandtem.",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "Sheets 'Inzuchtkoeffizient', 'Pedigree Collapse Generationen', 'Pedigree Collapse Mehrfach'.",
        "details": "F=0 bei nicht-konsanguinen Verbindungen, F=1/16 bei Cousin-Ehe, F=1/4 bei Geschwister-Ehe. Pedigree Collapse zeigt pro Generation: theoretische Slots (2^n) vs. tatsächliche eindeutige Vorfahren.",
        "tips":    "Die Kinship-Berechnung nutzt Henderson Tabular Method (rekursiv + memoisiert) — mathematisch korrekt auch bei tiefem Implex.",
    },
    "history": {
        "title":   "Historischer Kontext & Überlebenszeitanalyse",
        "group":   "Analysen",
        "purpose": "Ordnet Personen 19 historischen Ereignissen zu (1618–1973) und berechnet Survival-Kurven pro Geburts-Kohorte.",
        "input":   "individuals + families + Ortsdaten + ROOT_ID.",
        "output":  "Sheets 'Hist. Kontext Ereignisse', 'Hist. Kontext Personen', 'Überleben Kohorten', 'Überlebenskurven', 'Historische Trends'.",
        "details": "Kaplan-Meier-Kurven pro Jahrhundert-Kohorte. Generationenlängen werden bidirektional (Ahnen UND Nachfahren) berechnet.",
    },
    "names": {
        "title":   "Namensmorphologie (Kölner Phonetik)",
        "group":   "Analysen",
        "purpose": "Gruppiert Schreibvarianten desselben Namens automatisch via Kölner Phonetik + Levenshtein.",
        "input":   "individuals.",
        "output":  "Sheets 'Namensvarianten (Kölner Phonetik)', 'Namensvarianten Personen'.",
        "details": "Findet z.B. Müller/Mueller/Möller in einer Gruppe. Hilft bei der Erkennung von Schreibfehler-bedingten Doppeleinträgen.",
    },
    "data_quality": {
        "title":   "Datenvollständigkeits-Score",
        "group":   "Analysen",
        "purpose": "Bewertet pro Person die Datenqualität auf einer 0–100-Skala.",
        "input":   "individuals + families.",
        "output":  "Sheets 'Datenvollständigkeit Personen', '… Nachnamen', '… Epochen'.",
        "details": "Score pro Person basiert auf vorhandenen Feldern: Name (mit/ohne Surname), Geburtsjahr, Geburtsort, Sterbejahr, Sterbeort, Ehepartner, Eltern, Kinder. Aggregation auf Nachname- und Epoche-Ebene.",
    },
    "anomalies": {
        "title":   "Anomalien & Doubletten & Inseln",
        "group":   "Analysen",
        "purpose": "Findet implausible Datenkombinationen (Geburt nach Tod, zu junge Eltern, Zukunfts-Daten), potenzielle Duplikate und unverbundene Personen.",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "Drei Sheets: 'Daten-Anomalien' (KRITISCH/WARNUNG/HINWEIS), 'Potenzielle Doubletten' (mit Konfidenz-Score), 'Unerreichbare Personen'.",
        "details": "Anomalie-Schwellen: Mutter <12 J. oder >55 J., Vater <12 J. oder >80 J., Geschwisterabstand >25 J., Lebensalter >110, Heirat <14 oder >90 J. Doubletten-Detektor nutzt Levenshtein + 60-Einträge-Vornamen-Synonymtabelle (Hans↔Johannes, Fritz↔Friedrich, …).",
    },
    "dna_overview": {
        "title":   "DNA-Überblick (Ancestry-Datenbank)",
        "group":   "Analysen",
        "purpose": "Liest die Ancestry-DNA-SQLite-Datenbank und erstellt eine Übersicht über geladene Kits, Match-Zahlen, Top-Matches und Cluster.",
        "input":   "ancestry/ancestry_dna.db (wird vom Ancestry-DNA-Tool befüllt).",
        "output":  "Sheet 'DNA-Überblick (Ancestry)' mit Kit-Name, Match-Anzahl, Top-5, Leeds-Cluster, Endogamie-Markierungen.",
        "tips":    "Nur sinnvoll wenn das Ancestry-DNA-Tool bereits Matches heruntergeladen hat. Datenbankpfad: ancestry/ancestry_dna.db.",
    },
    "dna_cm": {
        "title":   "DNA-cM-Schätzung",
        "group":   "Analysen",
        "purpose": "Schätzt für jeden Verwandten die zu erwartenden gemeinsamen DNA-cM-Werte aus dem Stammbaum.",
        "input":   "individuals + families + ROOT_ID + Cousin-Ergebnisse.",
        "output":  "Sheet 'DNA-cM-Schätzung' (Kinship Φ, erwartete cM, DNA-Klasse).",
        "details": "Formel: erwartete cM ≈ Φ × 2 × 7000. Klassen orientiert an Ancestry/MyHeritage-Skala: Elternteil/Kind ~3500 cM, Vollgeschwister ~2600, Cousins 1°/2°/3° ~875/220/75.",
        "tips":    "Bei eigenem DNA-Test: Werte aus Ancestry hier abgleichen → wer in deinem Baum passt zu einem gemessenen Match-Wert?",
    },
    "sibling_namedrift": {
        "title":   "Geschwister-Statistiken & Namensdrift",
        "group":   "Analysen",
        "purpose": "Geburtsabstände in Familien + temporale Verbreitung jedes Vornamens.",
        "input":   "individuals + families.",
        "output":  "Sheets 'Geschwister-Statistiken' (pro Familie: Spanne, Min/Max-Abstand, Zwillinge), 'Namensdrift (Vornamen)' (pro Name: Peak-Dekade, Spanne).",
        "details": "Findet 'Zwillingsverdacht' bei Geschwistern mit gleichem Geburtsjahr und zeigt die zeitliche Drift von Vornamenstrends.",
    },
    "seasonality": {
        "title":   "Saisonalität (Monatsverteilung)",
        "group":   "Analysen",
        "purpose": "Verteilung von Geburten, Heiraten, Sterbefällen und geschätzten Empfängnissen über die 12 Monate pro Epoche.",
        "input":   "individuals + families (mit Monats-Information im DATE-String).",
        "output":  "Vier Sheets: 'Geburts-Monate', 'Heirats-Monate', 'Sterbe-Monate' (nach Altersklasse), 'Empfängnis-Monate' (Geburt − 9 Monate).",
        "details": "Zeigt traditionelle Heirats-Peaks (November/Mai bei Bauern), Säuglings-Sterbe-Sommerpeaks, Greisensterben im Winter.",
    },
    "snapshot": {
        "title":   "Stichjahr-Snapshot + Generationen-Overlap",
        "group":   "Analysen",
        "purpose": "Wer lebte zu bestimmten Stichjahren (1600, 1700, …, 2000)? Wie viele Generationen waren pro Jahrzehnt parallel am Leben?",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "Sheets 'Stichjahr-Snapshot' (Personen pro Stichjahr nach Geschlecht/Alter), 'Lebende Generationen' (pro Jahrzehnt).",
        "details": "Bei unbekanntem Sterbedatum wird die Person als lebend angenommen, wenn Geburtsjahr ≤ Stichjahr ≤ Geburtsjahr + 100.",
    },
    "spatial": {
        "title":   "Räumliche Lebensgeschichte",
        "group":   "Analysen",
        "purpose": "Heirats-Migration der Frauen, Lebens-Triangulation (Geburt→Heirat→Tod), Sesshaftigkeit pro Familie, Nachname×Region-Matrix.",
        "input":   "individuals + families + Ortsdaten + ROOT_ID.",
        "output":  "Vier Sheets: 'Heirats-Migration', 'Lebens-Triangulation', 'Sesshaftigkeit pro Familie', 'Nachname × Region'.",
        "details": "Klassifiziert Bewegungen als Lokal/Region/Land. Sesshaftigkeits-Score pro Familie = 1 / (distinkte Orte + 1).",
    },
    "family_structure": {
        "title":   "Erweiterte Familienstruktur",
        "group":   "Analysen",
        "purpose": "Mehrfachehen, Altersdifferenz Ehepaare, Reproduktive Spanne der Mütter, Kinderlosigkeit, Zwillinge.",
        "input":   "individuals + families.",
        "output":  "Fünf Sheets: 'Mehrfach-Ehen', 'Alters-Differenz Ehepaare', 'Reproduktive Spanne (Mütter)', 'Kinderlosigkeits-Rate', 'Zwillinge / Mehrfachgeburten'.",
        "details": "Mehrfachehen markiert Witwer/Witwen (Vor-Ehepartner gestorben). Altersdifferenz aggregiert pro Epoche mit Median/Min/Max.",
    },
    "lineage": {
        "title":   "Linien-Analysen (Y, Mt, Quartile, Aussterben)",
        "group":   "Analysen",
        "purpose": "Reine paternale Y-Linie, reine maternale Mt-Linie, 4-Quartile-Großeltern-Vergleich, Linien-Aussterben pro Nachname, Verzweigungs-Faktor.",
        "input":   "individuals + families + Ortsdaten + ROOT_ID.",
        "output":  "Fünf Sheets: 'Y-Linie (paternal)', 'Mt-Linie (maternal)', 'Großeltern-Quartile', 'Linien-Aussterben', 'Verzweigungs-Faktor'.",
        "details": "Y-Linie folgt nur Vater→Vater→… (DNA-Y-Vergleich). Mt-Linie folgt nur Mutter→Mutter→… (Mitochondrium-Vergleich). Quartile (PP/PM/MP/MM) zeigen Asymmetrien zwischen den 4 Großeltern-Linien.",
    },
    "naming_sociology": {
        "title":   "Namens-Soziologie (Patronyme, Junioren)",
        "group":   "Analysen",
        "purpose": "Patronyme (Mittlerer Vorname = Rufname des Vaters), Junioren (Erster Vorname = Vater-Vorname), Vornamen-Pool pro Familie.",
        "input":   "individuals + families.",
        "output":  "Drei Sheets: 'Patronyme', 'Junior-Detektor', 'Familien-Vornamen-Pool'.",
        "details": "Patronym-Tradition war im 17.–19. Jhd. weit verbreitet. Wiederverwendungs-Quote im Familien-Vornamen-Pool zeigt traditionsbewusste Familien.",
    },
    "imputation": {
        "title":   "Daten-Imputation (fehlende Daten)",
        "group":   "Analysen",
        "purpose": "Schätzt fehlende Geburtsjahre aus Familienkontext (Eltern, Kinder, Ehepartner, Geschwister).",
        "input":   "individuals + families.",
        "output":  "Sheet 'Geschätzte fehlende Daten' (mit Konfidenz-Klasse HOCH/MITTEL/NIEDRIG).",
        "details": "Kombiniert 4 Quellen: Eltern (+27), Kinder (Median − 27), Ehepartner (±3), Geschwister (±5). Konfidenz = HOCH wenn ≥2 Quellen mit Streuung ≤5 J.",
        "tips":    "Standardmäßig deaktiviert — wird nur bei explizitem Bedarf eingeschaltet.",
    },
    "cohort_extensions": {
        "title":   "Krisen-Kohorten & Eltern-Verlust",
        "group":   "Analysen",
        "purpose": "Vergleicht Lebensverläufe von Personen, die während historischer Krisen geboren wurden, mit Kontroll-Kohorten. Berechnet Alter beim Tod der Eltern pro Epoche.",
        "input":   "individuals + families.",
        "output":  "Sheets 'Krisen-Kohorten Folge', 'Eltern-Verlust-Alter'.",
        "details": "Pro historisches Ereignis: Kohorte = Geborene während des Ereignisses vs. Baseline = die 20 Jahre davor. Vergleicht Lebenserwartung, Heiratsalter, Kinderzahl.",
    },
    "research_helpers": {
        "title":   "Forschungs-Helfer (Brickwalls, Vorschläge, Quellen)",
        "group":   "Analysen",
        "purpose": "Brick-Wall-Detektor (gut belegte Personen ohne Eltern), Forschungs-Vorschläge nach Priorität, SOUR/OBJE-Inventar.",
        "input":   "individuals + families + GEDCOM-Datei (für SOUR-Parsing).",
        "output":  "Vier Sheets: 'Brick-Wall-Detektor' (Score ≥50), 'Forschungs-Vorschläge' (HOCH/MITTEL/NIEDRIG), 'Quellen-Inventar', 'Quellen-Qualität pro Person'.",
        "details": "Brick-Walls = die wichtigsten nächsten Recherche-Ziele. Forschungs-Vorschläge sind automatisch generierte Hinweise ('Suche Geburtseintrag in X um Jahr Y').",
        "tips":    "Die Brick-Wall-Liste ist die effizienteste 'next steps'-Liste für genealogische Recherche.",
    },
    "onomastics_endogamy": {
        "title":   "Onomastik & Endogamie-Bigraph",
        "group":   "Analysen",
        "purpose": "Religiöse/regionale Namensmuster (katholisch/protestantisch/germanisch) + Nachname × Nachname Heirats-Netz.",
        "input":   "individuals + families + Ortsdaten.",
        "output":  "Sheets 'Onomastik (Namensmuster)' und 'Endogamie-Netzwerk (Nachname×Nachname)'. Zusätzlich GraphML-Datei endogamy_network.graphml.",
        "details": "Onomastik klassifiziert Vornamen anhand 60+ Listen. Endogamie-Bigraph zeigt, welche Nachnamen-Paare am häufigsten miteinander heirateten.",
    },
    "sosa": {
        "title":   "Sosa-Stradonitz-Ahnentafel",
        "group":   "Analysen",
        "purpose": "Klassische internationale Ahnen-Nummerierung (Root=1, Vater=2, Mutter=3, …) inkl. Implex-Erkennung.",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "Sheet 'Sosa-Stradonitz-Ahnentafel' — eine Zeile pro Sosa-Nummer, sortiert.",
        "details": "Bei Pedigree-Collapse hat eine Person mehrere Sosa-Nummern (separate Spalte 'Implex'). Formel: Vater von N = 2N, Mutter von N = 2N+1.",
        "tips":    "Das ist der genealogische Welt-Standard. Jede Druck-Ahnentafel nutzt diese Nummerierung.",
    },
    "familysearch": {
        "title":   "FamilySearch-Vergleich (Suchlinks)",
        "group":   "Analysen",
        "purpose": "Generiert pro Ahn vorbereitete FamilySearch-Such-URLs (Quellen-Datenbank + Family Tree).",
        "input":   "individuals (vorzugsweise root_related_ids).",
        "output":  "Sheet 'FamilySearch-Vergleich' — zwei klickbare URLs pro Person, sortiert nach Such-Qualität.",
        "details": "Kein API-Key/OAuth nötig — der Browser handlet Auth. Such-Qualität (0–100) basiert auf vorhandenen Feldern: Name+Surname, Geburtsjahr, Geburtsort, Sterbedaten.",
        "tips":    "Klicke eine URL → siehst sofort, ob die Person in FamilySearch existiert.",
    },

    # ── Extras ────────────────────────────────────────────────────────────────
    "network": {
        "title":   "Familiennetzwerkanalyse",
        "group":   "Extras",
        "purpose": "Degree-Centrality, Betweenness, Brückenpersonen im Familien-Graph.",
        "input":   "individuals + families.",
        "output":  "Sheet 'Familiennetzwerk' (per Person mit Centrality-Werten).",
        "details": "Standardmäßig deaktiviert — rechenintensiv. Wählt automatisch zwischen Fast (≤5k Personen), Optimized (≤50k), Detailed (>50k).",
    },
    "osnabrueck": {
        "title":   "Osnabrück-Region Spezialanalyse",
        "group":   "Extras",
        "purpose": "Region-spezifische Analyse für Wallenhorst, GMH, Hagen a.T.W., Osnabrück, Bohmte.",
        "input":   "individuals mit Ortsdaten in der Osnabrück-Region.",
        "output":  "Sheet 'Osnabrück Übersicht' + ein Sheet pro Gemeinde.",
        "details": "Strikte Hierarchie-Prüfung: Personen werden nur zugeordnet, wenn Land + Kreis stimmen.",
    },

    # ── Export ────────────────────────────────────────────────────────────────
    "export_excel": {
        "title":   "Excel-Export",
        "group":   "Export",
        "purpose": "Schreibt alle aktiven Analyse-Sheets in eine Excel-Mappe.",
        "input":   "Alle Analyse-Ergebnisse im State.",
        "output":  "genealogy_analysis_complete.xlsx (typisch 15–25 MB bei 130k-Tree).",
        "details": "Nutzt openpyxl im write-only-Modus → streaming, RAM-flach, atomar geschrieben (.tmp → rename).",
    },
    "export_json": {
        "title":   "JSON-Export",
        "group":   "Export",
        "purpose": "Metadaten-Zusammenfassung als JSON.",
        "input":   "State (Statistiken, Top-Listen).",
        "output":  "genealogy_results.json.",
        "details": "Klein (<1 MB). Enthält Versionsinfo, Statistiken, Top-20-Nachnamen, Top-10-Länder.",
    },
    "export_html": {
        "title":   "HTML-Übersicht",
        "group":   "Export",
        "purpose": "Selbsterklärende HTML-Datei mit Kernkennzahlen.",
        "input":   "State.",
        "output":  "family_tree.html (Dark Theme, keine externen Dependencies).",
        "details": "Tabellen für Gesamtstatistik, Top-20-Nachnamen, Top-10-Länder, Demografie pro Epoche, Migrationswellen.",
    },
    "export_timeline": {
        "title":   "HTML-Timeline",
        "group":   "Export",
        "purpose": "Chronologische Ereignis-Zeitlinie mit Live-Filter im Browser.",
        "input":   "individuals + families + root_related_ids.",
        "output":  "timeline.html mit JavaScript-Such-Filter.",
        "details": "Alle Geburten, Tode, Auswanderungen, Einwanderungen sortiert nach Jahr. Filter im Eingabefeld nach Person oder Ort.",
    },
    "export_graphml": {
        "title":   "GraphML-Export",
        "group":   "Export",
        "purpose": "Familiennetzwerk als GraphML-Datei für Gephi/yEd.",
        "input":   "individuals + families + (optional) root_related_ids.",
        "output":  "family_network.graphml.",
        "details": "Knoten = Personen, Kanten = Eltern→Kind + Ehepartner.",
    },
    "export_fanchart": {
        "title":   "Fan-Chart SVG",
        "group":   "Export",
        "purpose": "Klassischer radialer Ahnenfächer (5-Generationen-Tafel) als SVG.",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "fan_chart.svg — direkt im Browser/Inkscape öffenbar.",
        "details": "Paternale Linie in Blau, maternale in Pink, unbekannte Ahnen in Grau. Druckfertig.",
    },
    "export_dashboard": {
        "title":   "HTML-Dashboard mit Charts",
        "group":   "Export",
        "purpose": "Interaktives Single-File-Dashboard mit Chart.js und Tab-Navigation.",
        "input":   "State.",
        "output":  "dashboard.html (Single-File, eine CDN-Referenz zu Chart.js).",
        "details": "6 Tabs: Übersicht, Demografie, Migration, Namen, Geografie, Genetik. Dark Theme.",
    },
    "export_heatmap": {
        "title":   "Geburts-Heatmap (Leaflet)",
        "group":   "Export",
        "purpose": "Welt-Karte der Geburtsorte nach Land + Jahrhundert.",
        "input":   "individuals + Ortsdaten.",
        "output":  "birth_heatmap.html (Leaflet, CARTO-Dark-Tiles).",
        "details": "Circle-Marker mit Radius proportional zu log(Anzahl), Farbe nach dominantem Jahrhundert.",
    },
    "export_descendants": {
        "title":   "Subtree: Nachfahren der Root als GEDCOM",
        "group":   "Export",
        "purpose": "Schreibt nur den Nachfahren-Teilbaum der Root als eigene .ged-Datei.",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "descendants.ged (GEDCOM 5.5).",
        "details": "Enthält Nachfahren bis max 10 Generationen + deren Ehepartner.",
    },
    "export_ancestors": {
        "title":   "Subtree: Vorfahren der Root als GEDCOM",
        "group":   "Export",
        "purpose": "Schreibt nur den Vorfahren-Teilbaum der Root als eigene .ged-Datei.",
        "input":   "individuals + families + ROOT_ID.",
        "output":  "ancestors.ged.",
        "details": "Enthält Vorfahren bis max 12 Generationen.",
    },
    "export_sankey": {
        "title":   "Migrations-Sankey (HTML)",
        "group":   "Export",
        "purpose": "Migrationsflüsse als interaktives SVG-Sankey-Diagramm.",
        "input":   "Migration-Ergebnisse.",
        "output":  "migration_sankey.html (Pure-SVG, keine externen Libs).",
        "details": "Linke Spalte = Geburtsländer, rechte = Sterbeländer. Bandbreite proportional zur Anzahl.",
    },
    "save_cache": {
        "title":   "State-Cache speichern",
        "group":   "Export",
        "purpose": "Persistiert den kompletten _state nach ~/.ahnen-cache.pkl für inkrementelle Folge-Läufe.",
        "input":   "Alle bisher berechneten Analyse-Ergebnisse.",
        "output":  "~/.ahnen-cache.pkl (typisch 50–200 MB) + SHA-256 der GEDCOM.",
        "details": "Beim nächsten Lauf: 'State-Cache laden' + nur Export-Tasks aktivieren → übergeht alle Re-Berechnungen.",
    },
    "online_research": {
        "title":   "Online-Sterbedaten (Wikidata + GND)",
        "group":   "Analysen",
        "purpose": "Ergänzt fehlende Sterbejahre aus Wikidata und der Deutschen Nationalbibliothek (GND) — rein lesend, kein GEDCOM-Schreiben.",
        "input":   "Personen im GEDCOM ohne Sterbejahr.",
        "output":  "Vorschlags-Liste mit Quellen-URL und Konfidenz; kein automatisches Einpflegen.",
        "details": "Benötigt aktive Internetverbindung. Bei großen Bäumen (>5 000 Personen) kann der Lauf mehrere Minuten dauern.",
    },
    "book_statistics": {
        "title":   "Buch-Statistiken (21 Analysen)",
        "group":   "Analysen",
        "purpose": "Implementiert alle 21 demografischen Analysen aus 'The Village in the Field': Sterbespitzen, Heiratsdistanz, Auswanderer vs. Stayer, Hofnamen, Berufsstand u.v.m.",
        "input":   "Vollständig geladenes GEDCOM.",
        "output":  "Ergebnis-Dicts im _state; werden von Excel-, HTML- und Dashboard-Export genutzt.",
        "details": "Aktivieren, bevor Export-Tasks gestartet werden — export_gravity_map und export_cousins_map benötigen diese Analyse.",
    },
    "export_gravity_map": {
        "title":   "Karte: Demografischer Schwerpunkt (Zeitraffer)",
        "group":   "Export",
        "purpose": "Erzeugt eine animierte Leaflet-Karte, die zeigt, wie sich der geografische Sterbepunkt-Schwerpunkt der Familie im Zeitverlauf verschiebt.",
        "input":   "Sterbeorte + Koordinaten aus 'Buch-Statistiken'.",
        "output":  "HTML-Datei mit Leaflet-Animation (ein Frame pro Dekade).",
        "details": "Benötigt 'Buch-Statistiken' als Vorgänger-Task. Eignet sich besonders für Auswanderer-Familien.",
    },
    "export_cousins_map": {
        "title":   "Karte: Lebende Cousins nach US-County",
        "group":   "Export",
        "purpose": "Leaflet-Karte mit Kreisen pro US-County — Kreisgröße entspricht der Anzahl lebender Verwandter in diesem County.",
        "input":   "Cousin-Analyse-Ergebnisse aus 'Buch-Statistiken'.",
        "output":  "HTML-Datei mit interaktiver Leaflet-Karte.",
        "details": "Benötigt 'Buch-Statistiken' aktiv. Sinnvoll für Familien mit starker US-Auswanderung.",
    },
}


# ── CLI-Subbefehle ────────────────────────────────────────────────────────────

CLI_HELP = {
    "--mrca": {
        "title":   "MRCA-Finder (CLI)",
        "syntax":  "python main.py --mrca @I100@ @I200@",
        "purpose": "Findet den jüngsten gemeinsamen Vorfahren (MRCA) zweier Personen — direkt aus der Konsole.",
        "details": "Lädt die GEDCOM, sucht beide Personen, gibt MRCA-ID, deren Tiefen, Verwandtschafts-Label und beide Pfade aus.",
        "example": "python main.py --mrca @I251@ @I2475@\n→ MRCA: @I42@ (Cousin 3. Grades, depth_a=4, depth_b=4)",
    },
    "--merge": {
        "title":   "Zwei GEDCOMs zusammenführen (CLI)",
        "syntax":  "python main.py --merge fileA.ged fileB.ged --merge-out merged.ged",
        "purpose": "Mergt zwei GEDCOMs mit Doubletten-Resolution (Name+Geburtsjahr ±2).",
        "details": "Schreibt ein Sidecar-Log .merge.log mit Liste der zusammengeführten Paare.",
    },
    "--predict-cm": {
        "title":   "DNA-cM → Verwandtschaft (CLI)",
        "syntax":  "python main.py --predict-cm 850",
        "purpose": "Wandelt einen gemessenen DNA-cM-Wert in Verwandtschafts-Wahrscheinlichkeiten um.",
        "details": "Gibt Top-5 Beziehungen mit Wahrscheinlichkeit (Gaussian-basiert) aus. 850 cM → 'Cousin 1. Grades' ~99%.",
    },
    "--batch": {
        "title":   "Batch-Modus (CLI ohne GUI)",
        "syntax":  "python main.py --batch [--tasks t1,t2,…] [--gedfile X] [--root-id Y]",
        "purpose": "Führt alle (oder ausgewählte) Tasks ohne GUI aus. Für Scheduled Tasks / Cron.",
        "details": "Exit-Codes: 0=OK, 1=Task-Fehler, 2=Unbekannte Task-ID, 130=User-Abbruch.",
    },
    "--list-tasks": {
        "title":   "Liste aller Tasks (CLI)",
        "syntax":  "python main.py --list-tasks",
        "purpose": "Zeigt alle verfügbaren Tasks mit ID, Gruppe, Default-Status.",
        "details": "* markiert Default-Tasks (laufen ohne --tasks).",
    },
}


# ── DNA-Tool / Viewer / Scraper ───────────────────────────────────────────────

DNA_TOOLS: dict = {
    "workflow_overview": {
        "title":   "Erste Schritte — Gesamtworkflow",
        "group":   "Workflow",
        "purpose": "Überblick über den empfohlenen Arbeitsablauf von GEDCOM-Import bis DNA-Auswertung.",
        "details": (
            "Schritt 1 — GEDCOM laden\n"
            "  Datei wählen (*.ged oder *.ftm), Root-ID setzen, 'Starten' klicken.\n"
            "  Nach dem ersten Lauf werden alle Stammbaumdaten automatisch in\n"
            "  ancestry/ancestry_dna.db gespeichert (Tabelle gedcom_persons).\n\n"
            "Schritt 2 — DNA-Matches importieren\n"
            "  Ancestry: DNA-Matches per CSV aus ancestry.com exportieren und über\n"
            "  '🧬 DNA-Matches' → Import-Tool laden.\n"
            "  MyHeritage: CSV aus MH exportieren und über ancestry/tools/import_mh_csv.py importieren.\n"
            "  GEDmatch: Über ancestry/tools/import_gedmatch.py.\n\n"
            "Schritt 3 — DNA-Viewer öffnen\n"
            "  '🧬 DNA-Matches'-Button → Ancestry-DNA-Tool öffnet sich als eigenes Fenster.\n"
            "  Dort: Match-Liste, GEDCOM-Overlap-Filter, Konfessions-Filter, Cluster-Färbung.\n\n"
            "Schritt 4 — Shared Matches laden (optional)\n"
            "  ancestry/tools/fetch_mh_shared_matches.py für MyHeritage.\n"
            "  Leeds-Clustering wird automatisch aus Shared-Matches berechnet.\n\n"
            "Schritt 5 — Kirchspiel-Daten ergänzen (optional)\n"
            "  ancestry/tools/scrape_matricula_osnabrueck.py einmalig starten.\n"
            "  Lädt alle 169 Pfarreien des Bistums Osnabrück inkl. Tochterkirchen.\n"
            "  Im Viewer erscheinen dann ✝K / ✝E Badges und blaue/grüne Markierungen."
        ),
        "tips": "GEDCOM jederzeit neu importieren — ersetzt nur die gedcom_persons-Daten, DNA-Matches bleiben erhalten.",
    },
    "dna_viewer": {
        "title":   "DNA-Viewer (Ancestry-DNA-Tool)",
        "group":   "DNA-Tools",
        "purpose": "Zeigt alle importierten DNA-Matches, ihre GEDCOM-Übereinstimmungen, Leeds-Cluster und Kirchspiel-Zuordnung.",
        "details": (
            "Geöffnet über '🧬 DNA-Matches' aus dem Hauptfenster oder direkt als\n"
            "  python ancestry/main.py\n\n"
            "Filter-Optionen:\n"
            "  • cM-Schwelle: nur Matches über X cM anzeigen\n"
            "  • GEDCOM-Filter: Alle / Im GEDCOM ✓ / Fuzzy-Match ~ / Nicht im GEDCOM\n"
            "  • Konfessions-Filter: Alle / Kath. / Ev. / Unbekannt\n"
            "  • Cluster-Filter: Nach Leeds-Cluster-Nummer filtern\n\n"
            "Farbmarkierungen:\n"
            "  Grüner Rand  = im GEDCOM bestätigt (xref-Eintrag)\n"
            "  Brauner Rand = Fuzzy-Match (gleicher Nachname + Geburtsjahr ±5)\n"
            "  Lila Rand    = Gleicher DNA-Cluster wie ein bestätigter GEDCOM-Match\n"
            "  Blau ✝K      = Pfarrei katolisch (Matricula-Daten)\n"
            "  Grün ✝E      = Pfarrei evangelisch"
        ),
        "tips": "Mit Doppelklick auf einen Match öffnet sich das Detail-Panel mit GEDCOM-Verknüpfung und Kirchspiel-Info.",
    },
    "gedcom_overlap": {
        "title":   "GEDCOM-Overlap-Erkennung",
        "group":   "DNA-Tools",
        "purpose": "Vergleicht DNA-Matches mit den GEDCOM-Personen und markiert, welche Matches bereits im Stammbaum sind.",
        "details": (
            "Drei Ebenen der Erkennung:\n\n"
            "1. Bestätigt (grün): Eintrag in gedcom_person_xref mit Übereinstimmung\n"
            "   zwischen einer Match-GUID und einer GEDCOM-Person-ID.\n\n"
            "2. Fuzzy-Match (braun): Kein xref-Eintrag, aber:\n"
            "   • Nachname stimmt überein (case-insensitiv) UND\n"
            "   • Geburtsjahr stimmt überein ±5 Jahre\n\n"
            "3. Cluster-Verbindung (lila): Match ist im selben Leeds-Cluster wie\n"
            "   ein bestätigter GEDCOM-Match.\n\n"
            "Neue Bestätigungen können im Viewer direkt gesetzt werden (xref_review.py)."
        ),
        "tips": "Filter 'Im GEDCOM ✓' zeigt nur Matches, die bereits sicher zugeordnet sind — ideal für Qualitätsprüfungen.",
    },
    "leeds_clustering": {
        "title":   "Leeds-Methode / Cluster-Analyse",
        "group":   "DNA-Tools",
        "purpose": "Gruppiert DNA-Matches in Familien-Cluster (Großeltern-Linien) per Union-Find-Algorithmus.",
        "details": (
            "Algorithmus (ähnlich Leeds-Methode):\n"
            "  1. Shared-Matches laden: Match A und Match B teilen beide DNA mit mir\n"
            "     UND teilen DNA miteinander → gehören einem Cluster an.\n"
            "  2. Union-Find (Disjoint Sets) verbindet alle solche Paare iterativ.\n"
            "  3. Ergebnis: cluster_id pro Match (1, 2, 3, …)\n\n"
            "Erwartetes Ergebnis bei nicht-endogamer Familie:\n"
            "  ~4 Hauptcluster = die 4 Großeltern-Linien (PP/PM/MP/MM)\n"
            "  Endogame Familien (wie Osnabrück-Region) haben oft weniger Cluster."
        ),
        "tips": "Shared Matches müssen zuerst geladen werden (fetch_mh_shared_matches.py oder äquivalent für Ancestry).",
    },
    "matricula_scraper": {
        "title":   "Matricula-Pfarrei-Scraper (Bistum Osnabrück)",
        "group":   "DNA-Tools",
        "purpose": "Lädt alle Pfarreien des Bistums Osnabrück von data.matricula-online.eu inkl. Gründungsdatum, Konfession und Mutterpfarreien.",
        "details": (
            "Start:\n"
            "  python ancestry/tools/scrape_matricula_osnabrueck.py\n\n"
            "Ergebnisse:\n"
            "  • ancestry/tools/matricula_parishes.db   — SQLite mit Hierarchie\n"
            "  • ancestry/tools/matricula_parishes.json — Ortsname → Pfarrei-Lookup\n\n"
            "Datenfelder pro Pfarrei:\n"
            "  parish_id, parish (Name), confession (kath/ev/unbekannt),\n"
            "  parent_id (Mutterpfarrei), founded (Gründungsjahr),\n"
            "  villages (zugehörige Orte)\n\n"
            "Abpfarrungen:\n"
            "  Manche Pfarreien sind aus größeren Pfarreien hervorgegangen.\n"
            "  Das Gründungsjahr der Abpfarrung ist genealogisch relevant:\n"
            "  vor diesem Jahr → Kirchenbücher in der Mutterpfarrei suchen."
        ),
        "tips": "Einmalig starten. Danach nutzt der Viewer die JSON-Datei lokal ohne Internet.",
    },
    "mh_shared_matches": {
        "title":   "MyHeritage Shared Matches (Playwright-Scraper)",
        "group":   "DNA-Tools",
        "purpose": "Lädt für alle MH-Matches ab einem cM-Schwellwert die Shared-Matches und importiert sie in die Datenbank.",
        "details": (
            "Start:\n"
            "  python ancestry/tools/fetch_mh_shared_matches.py \\\n"
            "    --csv \"pfad/zur/MH_Matches.csv\" --min-cm 50\n\n"
            "Voraussetzungen:\n"
            "  1. Playwright: pip install playwright && playwright install chromium\n"
            "  2. Beim ersten Start öffnet sich Chromium — manuell in MyHeritage einloggen.\n"
            "  3. Danach speichert --profile-dir den Login für Folgeläufe.\n\n"
            "Argumente:\n"
            "  --csv        Pfad zur MH Match-List-CSV (Pflicht)\n"
            "  --min-cm     Schwellwert (default: 50 cM)\n"
            "  --limit      Max. Anzahl Matches (default: alle)\n"
            "  --visible    Browser sichtbar anzeigen\n"
            "  --pause      Pause zwischen Seiten in Sekunden (default: 2.0)\n\n"
            "Status: Resumable — bereits gescrapte Matches werden übersprungen.\n"
            "Fortschritt wird in shared_matches_fetched gespeichert."
        ),
        "tips": "Falls MH die IP sperrt: VPN aktivieren oder einen Tag warten. Der Scraper setzt automatisch da fort, wo er aufgehört hat.",
    },
    "import_mh_csv": {
        "title":   "MyHeritage Match-List importieren",
        "group":   "DNA-Tools",
        "purpose": "Importiert die komplette Match-Liste aus einer MH-CSV-Datei in die ancestry_dna.db.",
        "details": (
            "Start:\n"
            "  python ancestry/tools/import_mh_csv.py \"pfad/zur/MH_Matches.csv\"\n\n"
            "CSV-Format (MH-Export):\n"
            "  Name, Match Name, Relationship, Shared DNA, Largest Segment,\n"
            "  Shared Segments, Ancestral surnames, Locations, Notes\n\n"
            "Importiert in Tabelle: dna_matches\n"
            "  kit_name, match_name, match_guid, cm_shared, relationship,\n"
            "  source='myheritage'\n\n"
            "Nach dem Import im Viewer über '🧬 DNA-Matches' sichtbar."
        ),
        "tips": "MH-CSV-Export: DNA → Matches → Download-Symbol → 'Als CSV herunterladen'.",
    },
    "webtrees_crawler": {
        "title":   "webtrees-Crawler (beliebige Instanz)",
        "group":   "DNA-Tools",
        "purpose": "Crawlt einen öffentlichen (oder login-geschützten) webtrees-Stammbaum und speichert alle Personen lokal für den GEDCOM-Overlap-Vergleich.",
        "details": (
            "Unterstützt jede webtrees-Instanz:\n\n"
            "Einfacher Start:\n"
            "  python ancestry/tools/crawl_webtrees.py crawl \\\n"
            "    \"https://mein-stammbaum.de/tree/family/individual/I1/\"\n\n"
            "Mit Login (HTTP Basic Auth):\n"
            "  python crawl_webtrees.py crawl <URL> --auth user:passwort\n\n"
            "Mit Cookie-Login (Cookie Editor JSON):\n"
            "  python crawl_webtrees.py crawl <URL> --cookies cookies.json\n\n"
            "Mit webtrees-Formular-Login:\n"
            "  python crawl_webtrees.py crawl <URL> \\\n"
            "    --login-url https://site.de/login \\\n"
            "    --login-user meins --login-pass geheim\n\n"
            "Profil speichern (für Wiederholungs-Läufe):\n"
            "  python crawl_webtrees.py crawl <URL> --save-profile meinbaum\n"
            "  python crawl_webtrees.py crawl --profile meinbaum\n\n"
            "Alle bekannten Sites auflisten:\n"
            "  python crawl_webtrees.py list-sites\n\n"
            "Datenbank: webtrees_{host}.db (pro Instanz getrennt)\n"
            "anverwandte.info → webtrees_crawl.db (Rückwärtskompatibel)"
        ),
        "tips": "Rate-Limit: Standard 4s + Jitter. Nie auf --delay < 4 setzen. Resumable: Einfach erneut starten.",
    },
    "xref_review": {
        "title":   "GEDCOM↔Match Verknüpfung verwalten (xref_review)",
        "group":   "DNA-Tools",
        "purpose": "Prüft und bestätigt/verwirft Fuzzy-Vorschläge für GEDCOM-Person ↔ DNA-Match-Zuordnungen.",
        "details": (
            "Start:\n"
            "  python ancestry/tools/xref_review.py\n\n"
            "Zeigt alle unbestätigten Fuzzy-Vorschläge mit:\n"
            "  • GEDCOM-Person (Name, Geburtsjahr, Geburtsort)\n"
            "  • DNA-Match (Name, cM, Quelle)\n"
            "  • Konfidenz-Score\n\n"
            "Aktionen:\n"
            "  [j] Bestätigen → schreibt in gedcom_person_xref (confirmed=1)\n"
            "  [n] Verwerfen  → schreibt in gedcom_person_xref (confirmed=0)\n"
            "  [s] Überspringen\n\n"
            "Bestätigte Verknüpfungen erscheinen im Viewer als grüner Rand."
        ),
    },
}


# ── Mathematische Konzepte (für die Hilfe) ────────────────────────────────────

CONCEPTS = {
    "Kinship-Koeffizient Φ": {
        "definition": "Wahrscheinlichkeit, dass ein zufällig gewähltes Allel von Person A IBD (identical by descent) ist mit einem zufällig gewählten Allel von B.",
        "formula":    "Henderson Tabular: Φ(A,A) = (1+F)/2; Φ(A,B) = ½·[Φ(P_jünger,B) + Φ(M_jünger,B)]",
        "examples":   "Φ(Eltern, Kind) = 0.25 · Φ(Vollgeschwister) = 0.25 · Φ(Großeltern, Enkel) = 0.125 · Φ(Cousin 1°) = 1/16",
    },
    "Wright's F (Inzuchtkoeffizient)": {
        "definition": "Wahrscheinlichkeit, dass eine Person an einem Genort zwei IBD-Allele trägt.",
        "formula":    "F(X) = Σ über gemeinsame Ahnen C der Eltern: (½)^(L_F + L_M + 1) × (1+F_C)",
        "examples":   "F=0 ohne Konsanguinität · F=1/16 bei Cousin-1°-Ehe-Kind · F=1/4 bei Geschwister-Ehe-Kind",
    },
    "Sosa-Stradonitz-Nummerierung": {
        "definition": "Internationaler Standard für Ahnen-Nummerierung: Proband = 1, Vater von N = 2N, Mutter von N = 2N+1.",
        "formula":    "Generation = bit_length(sosa) − 1.  Beispiel: Sosa 12 → bit_length(12)=4 → Gen 3 (Urgroßeltern).",
        "examples":   "Du=1, Vater=2, Mutter=3, paternaler Großvater=4, paternale Großmutter=5, …",
    },
    "DNA-cM (Centi-Morgan)": {
        "definition": "Einheit der DNA-Erbeinheit. Gesamtes menschliches Genom ≈ 7000 cM. Geteilte cM zwischen 2 Personen ≈ Φ × 2 × 7000.",
        "formula":    "Erwartete cM(A,B) = 2 × Φ(A,B) × 7000",
        "examples":   "Eltern/Kind ~3500 cM · Vollgeschwister ~2600 · Cousin 1° ~875 · Cousin 3° ~75",
    },
    "Pedigree Collapse (Implex)": {
        "definition": "Generationen-Effekt, dass eine Person mehrfach als Ahn auftritt (wenn Vorfahren miteinander verwandt sind).",
        "formula":    "Collapse-Rate Gen N = 1 − (eindeutige Ahnen / 2^N)",
        "examples":   "Gen 12: theoretisch 4096 Slots — bei 5% Collapse: ~3890 eindeutige Personen",
    },
}
