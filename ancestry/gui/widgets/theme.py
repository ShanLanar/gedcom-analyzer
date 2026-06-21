"""Farben, Übersetzungen und ttk-Style für das Ancestry-DNA-Tool."""

from tkinter import ttk

COLORS = {
    "primary" : "#1F4E79",
    "accent"  : "#2E75B6",
    "light"   : "#D6E4F0",
    "bg"      : "#F0F4F8",
    "text"    : "#1A1A2E",
    "success" : "#217A3C",
    "warning" : "#C85000",
    "white"   : "#FFFFFF",
    "cluster" : ["#FFD6D6","#D6F5E3","#D6E4FF","#FFF3CD","#F0D6FF","#D6F0FF"],
}

COLORS_DARK = {
    "primary" : "#7c7cf8",
    "accent"  : "#a5a5ff",
    "light"   : "#2a2a3e",
    "bg"      : "#1e1e2e",
    "text"    : "#cdd6f4",
    "success" : "#50fa7b",
    "warning" : "#ffb86c",
    "white"   : "#ffffff",
    "cluster" : ["#3a2020","#1a3a2a","#1e1e3a","#2e2a10","#2a1a3a","#0a2230"],
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    # Tabs
    "tab_login":    {"de": "  🔑 Login  ",        "en": "  🔑 Login  "},
    "tab_download": {"de": "  ⬇ Herunterladen  ", "en": "  ⬇ Download  "},
    "tab_matches":  {"de": "  🧬 Matches  ",       "en": "  🧬 Matches  "},
    "tab_cluster":  {"de": "  🌳 Cluster  ",       "en": "  🌳 Cluster  "},
    "tab_stats":    {"de": "  📊 Statistiken  ",   "en": "  📊 Statistics  "},
    "tab_persons":  {"de": "  👪 Personen  ",       "en": "  👪 Persons  "},
    "tab_matricula":{"de": "  ⛪ Matricula  ",      "en": "  ⛪ Matricula  "},
    "tab_tools":    {"de": "  🔧 Werkzeuge  ",      "en": "  🔧 Tools  "},
    # Matricula-Tab
    "mat.next":     {"de": "Nächste Pfarrei:",      "en": "Next parish:"},
    "mat.booktype": {"de": "Buchtyp:",              "en": "Book type:"},
    "mat.autonext": {"de": "automatisch mit nächster Pfarrei fortfahren",
                     "en": "continue with next parish automatically"},
    "mat.start":    {"de": "▶ Scan starten",        "en": "▶ Start scan"},
    "mat.stop":     {"de": "⏹ Stopp",               "en": "⏹ Stop"},
    "mat.refresh":  {"de": "↻ Status",              "en": "↻ Status"},
    "mat.overview": {"de": "Pfarreien-Übersicht (✓ = fertig, ausgegraut):",
                     "en": "Parish overview (✓ = done, greyed out):"},
    "mat.no_db":    {"de": "Keine Pfarrei-DB gefunden. Zuerst ausführen:\n"
                           "  python ancestry/tools/scrape_matricula_osnabrueck.py\n"
                           "  python ancestry/tools/fetch_matricula_books.py",
                     "en": "No parish DB found. Run first:\n"
                           "  python ancestry/tools/scrape_matricula_osnabrueck.py\n"
                           "  python ancestry/tools/fetch_matricula_books.py"},
    # Main match table
    "m.name":    {"de": "Name / ID",   "en": "Name / ID"},
    "m.guid":    {"de": "GUID",        "en": "GUID"},
    "m.src":     {"de": "Quelle",      "en": "Source"},
    "m.note":    {"de": "Bemerkung",   "en": "Note"},
    "m.cm":      {"de": "cM",          "en": "cM"},
    "m.seg":     {"de": "Seg.",        "en": "Seg."},
    "m.rel":     {"de": "Beziehung",   "en": "Relationship"},
    "m.tree":    {"de": "Stammbaum",   "en": "Tree"},
    "m.ca":      {"de": "Vorfahre",    "en": "Ancestor"},
    "m.ged":     {"de": "🌳",           "en": "🌳"},
    "m.starred": {"de": "⭐",           "en": "⭐"},
    # Cluster list
    "cl.cid":   {"de": "Cluster",   "en": "Cluster"},
    "cl.count": {"de": "Matches",   "en": "Matches"},
    "cl.maxcm": {"de": "Max cM",    "en": "Max cM"},
    "cl.top":   {"de": "Top-Match", "en": "Top Match"},
    # Cluster members
    "mb.name": {"de": "Name",      "en": "Name"},
    "mb.cm":   {"de": "cM",        "en": "cM"},
    "mb.rel":  {"de": "Beziehung", "en": "Relationship"},
    "mb.baum": {"de": "Baum",      "en": "Tree"},
    # Pairwise
    "pw.a":  {"de": "Match A",      "en": "Match A"},
    "pw.b":  {"de": "Match B",      "en": "Match B"},
    "pw.cm": {"de": "Gemeinsam cM", "en": "Shared cM"},
    # GEDCOM comparison window
    "gc.cluster": {"de": "Cluster",   "en": "Cluster"},
    "gc.link":    {"de": "Verknüpft", "en": "Linked"},
    "gc.match":   {"de": "Match",     "en": "Match"},
    "gc.cm":      {"de": "cM",        "en": "cM"},
    "gc.anchor":  {"de": "Anknüpfung in deinem Baum", "en": "Anchor in your tree"},
    "gc.abirth":  {"de": "* Anknüpfung", "en": "* Anchor"},
    "gc.kin":     {"de": "Deine Linie",  "en": "Your line"},
    "gc.line":    {"de": "Match-Linie",  "en": "Match line"},
    "gc.score":   {"de": "Sicherheit",   "en": "Confidence"},
    # Cluster tree analysis window
    "ct.count":   {"de": "Anz.",       "en": "Count"},
    "ct.person":  {"de": "Person",     "en": "Person"},
    "ct.birth":   {"de": "* Jahr",     "en": "* Year"},
    "ct.place":   {"de": "Geburtsort", "en": "Birth place"},
    "ct.gen":     {"de": "Gen.",       "en": "Gen."},
    "ct.matches": {"de": "In welchen Matches", "en": "In which matches"},
    # Match-Tab Filterleiste
    "mf.search":  {"de": "Suche:",                  "en": "Search:"},
    "mf.rel":     {"de": "  Beziehung:",            "en": "  Relationship:"},
    "mf.mincm":   {"de": "  min cM:",               "en": "  min cM:"},
    "mf.starred": {"de": "Markierte",               "en": "Starred"},
    "mf.tree":    {"de": "Mit Stammbaum",           "en": "With tree"},
    "mf.endo":    {"de": "🔇 Rauschen ausblenden",  "en": "🔇 Hide noise"},
    # Cluster-Tab Steuerung
    "cl.prim_from":  {"de": "Primäre cM von:",  "en": "Primary cM from:"},
    "cl.prim_to":    {"de": "bis:",             "en": "to:"},
    "cl.shared_min": {"de": "Min. cM Shared:",  "en": "Min. cM shared:"},
    "cl.calc_btn":   {"de": "🔄 Cluster berechnen",  "en": "🔄 Calculate clusters"},
    "cl.tree_btn":   {"de": "🌳 Stammbaum-Analyse",  "en": "🌳 Tree analysis"},
    "cl.frm_left":   {"de": "Cluster",               "en": "Cluster"},
    "cl.frm_mid":    {"de": "Cluster-Mitglieder",    "en": "Cluster members"},
    "cl.frm_right":  {"de": "Gegenseitige cM (Mitglieder untereinander)",
                      "en": "Pairwise cM (members)"},
    # GEDCOM-Abgleich Filterleiste
    "gc.f.search":  {"de": "Suche:",            "en": "Search:"},
    "gc.f.new":     {"de": "nur neue Leads",    "en": "new leads only"},
    "gc.f.direct":  {"de": "nur direkte Linie", "en": "direct line only"},
    "gc.f.mincm":   {"de": "ab cM:",            "en": "from cM:"},
    "gc.f.cluster": {"de": "Cluster:",          "en": "Cluster:"},
    "gc.linked":    {"de": "✓ im Baum",         "en": "✓ in tree"},
    "gc.new":       {"de": "neu?",              "en": "new?"},
    "gc.tree_btn":  {"de": "🌳 Stammbaum-Analyse für diesen Cluster",
                     "en": "🌳 Cluster tree analysis"},
    # Login tab
    "lg.meth1":     {"de": "Methode 1: Automatischer Login",       "en": "Method 1: Automatic Login"},
    "lg.email":     {"de": "E-Mail:",                              "en": "E-Mail:"},
    "lg.password":  {"de": "Passwort:",                            "en": "Password:"},
    "lg.login_btn": {"de": "Einloggen",                            "en": "Log in"},
    "lg.meth2":     {"de": "Cookie-Datei Login",                   "en": "Cookie File Login"},
    "lg.choose":    {"de": "Datei wählen …",                       "en": "Choose file …"},
    "lg.login_ck":  {"de": "Mit Cookies einloggen",                "en": "Log in with cookies"},
    "lg.manual":    {"de": "Manuelle Kit-GUID",                    "en": "Manual Kit GUID"},
    "lg.use_guid":  {"de": "GUID übernehmen",                      "en": "Use GUID"},
    # Download tab
    "dl.kit":       {"de": "DNA-Kit:",                             "en": "DNA Kit:"},
    "dl.sec_a":     {"de": "A: Matches herunterladen",             "en": "A: Download Matches"},
    "dl.filter":    {"de": "Filter:",                              "en": "Filter:"},
    "dl.f_all":     {"de": "Alle",                                 "en": "All"},
    "dl.f_star":    {"de": "Markierte",                            "en": "Starred"},
    "dl.f_close":   {"de": "Nahe",                                 "en": "Close"},
    "dl.f_distant": {"de": "Entfernte",                            "en": "Distant"},
    "dl.sort":      {"de": "Sortierung:",                          "en": "Sort:"},
    "dl.s_rel":     {"de": "Nach Beziehung",                       "en": "By relationship"},
    "dl.s_cm":      {"de": "Nach cM",                              "en": "By cM"},
    "dl.start_m":   {"de": "▶ Matches starten",                    "en": "▶ Start matches"},
    "dl.stop":      {"de": "⏹ Stoppen",                            "en": "⏹ Stop"},
    "dl.only_new":  {"de": "✨ Nur neue (inkrementell)",            "en": "✨ New only (incremental)"},
    "dl.full_names":{"de": "👤 Volle Namen versuchen (oft von Ancestry blockiert)",
                     "en": "👤 Try full names (often blocked by Ancestry)"},
    "dl.sec_a2":    {"de": "A2: Namen & Stammbaum nachladen",      "en": "A2: Reload Names & Tree"},
    "dl.min_cm":    {"de": "Nur ab (cM):",                         "en": "Only from (cM):"},
    "dl.depth":     {"de": "Tiefe (Generationen):",                "en": "Depth (generations):"},
    "dl.reload_all":{"de": "🔄 Alle neu laden",                    "en": "🔄 Reload all"},
    "dl.refresh_stale":{"de": "♻ nur veraltete (>30 T.)",          "en": "♻ stale only (>30 d)"},
    "dl.start_nm":  {"de": "▶ Namen & Stammbaum laden",            "en": "▶ Load names & tree"},
    "dl.start_anc": {"de": "▶ Vorfahren & Orte laden",             "en": "▶ Load ancestors & places"},
    "dl.start_ped": {"de": "▶ Ahnentafeln laden",                  "en": "▶ Load pedigrees"},
    "dl.sec_b":     {"de": "B: Shared Matches herunterladen",      "en": "B: Download Shared Matches"},
    "dl.prim_min":  {"de": "Nur primäre Matches ab (cM):",         "en": "Only primary matches from (cM):"},
    "dl.skip_ex":   {"de": "Bereits geholte überspringen",         "en": "Skip already fetched"},
    "dl.start_sh":  {"de": "▶ Shared Matches starten",             "en": "▶ Start shared matches"},
    "dl.progress":  {"de": "Fortschritt:",                         "en": "Progress:"},
    "dl.log":       {"de": "Protokoll:",                           "en": "Log:"},
    # Match detail panel inner tabs
    "md.tab_info":  {"de": "Info & Notiz",                         "en": "Info & Note"},
    "md.tab_shared":{"de": "Shared Matches",                       "en": "Shared Matches"},
    # Match detail field labels (colon included)
    "md.cm":        {"de": "cM:",                                  "en": "cM:"},
    "md.seg":       {"de": "Segmente:",                            "en": "Segments:"},
    "md.longseg":   {"de": "Längstes Seg.:",                       "en": "Longest seg.:"},
    "md.rel":       {"de": "Beziehung:",                           "en": "Relationship:"},
    "md.conf":      {"de": "Konfidenz:",                           "en": "Confidence:"},
    "md.tree_lbl":  {"de": "Stammbaum:",                           "en": "Tree:"},
    "md.anc":       {"de": "Gem. Vorfahre:",                       "en": "Com. Ancestor:"},
    "md.sex":       {"de": "Geschlecht:",                          "en": "Gender:"},
    "md.last":      {"de": "Letzter Login:",                       "en": "Last Login:"},
    "md.pedigree":  {"de": "Ahnentafel:",                          "en": "Pedigree:"},
    "md.origin":    {"de": "Herkunft:",                            "en": "Origin:"},
    "md.rel_cm":    {"de": "Beziehung (cM):",                      "en": "Relationship (cM):"},
    "md.ml_origin": {"de": "Herkunft (ML):",                       "en": "Origin (ML):"},
    "md.note":      {"de": "Notiz:",                               "en": "Note:"},
    "md.save_note": {"de": "💾 Notiz speichern",                   "en": "💾 Save note"},
    "md.open_anc":  {"de": "🔗 In Ancestry öffnen",                "en": "🔗 Open in Ancestry"},
    "dlg.no_matches_t": {"de": "Keine Matches", "en": "No matches"},
    "dl.m_no_matches_kit": {"de": "Für dieses Kit sind keine Matches vorhanden.", "en": "No matches available for this kit."},
    "dl.m_choose_kit_or_guid": {"de": "Bitte DNA-Kit auswählen oder GUID eingeben.", "en": "Please select a DNA kit or enter a GUID."},
    "dl.m_choose_ftdna": {"de": "Bitte zuerst eine FTDNA matches.csv wählen.", "en": "Please choose an FTDNA matches.csv first."},
    "dl.m_login_ancestry": {"de": "Bitte zuerst bei Ancestry einloggen (Login-Tab).", "en": "Please log in to Ancestry first (Login tab)."},
    "dl.m_choose_csv": {"de": "Bitte zuerst eine CSV-Datei wählen.", "en": "Please choose a CSV file first."},
    "dl.b_cancel": {"de": "⏹ Abbrechen", "en": "⏹ Cancel"},
    "dl.b_gmx_export": {"de": "⬇ Matches als GEDmatch-TSV exportieren", "en": "⬇ Export matches as GEDmatch TSV"},
    "dl.b_ethnicity": {"de": "▶ Herkunft & Traits laden", "en": "▶ Load origin & traits"},
    "dl.t_seg_csv": {"de": "Segment-CSV wählen", "en": "Choose segment CSV"},
    "dl.t_save_gmx": {"de": "GEDmatch-TSV speichern", "en": "Save GEDmatch TSV"},
    "dl.t_ftdna": {"de": "FTDNA matches.csv wählen", "en": "Choose FTDNA matches.csv"},
    "dl.sec_c": {"de": "C · DNA-Segmente (für Triangulation)", "en": "C · DNA segments (for triangulation)"},
    "dl.seg_hint": {"de": "(GEDmatch Segment Search, MyHeritage Shared-Segments oder FTDNA)", "en": "(GEDmatch Segment Search, MyHeritage shared segments or FTDNA)"},
    "dl.b_seg_import": {"de": "⬆ Segmente importieren", "en": "⬆ Import segments"},
    "dl.b_ftdna_import": {"de": "⬆ FTDNA Matches importieren", "en": "⬆ Import FTDNA matches"},
    "dl.sec_d": {"de": "D · Herkunft / Ethnizität & Traits", "en": "D · Origin / ethnicity & traits"},
    "dl.help_names": {"de": "Lädt Namen, Geschlecht, Stammbaum-Status/-Größe und ob ein\ngemeinsamer Vorfahre existiert (20 Matches pro Anfrage).\nDanach: 'Vorfahren & Orte' + 'Ahnentafeln' laden für ALLE Matches\nmit Baum (nicht nur Ancestrys erkannte) – dann Auswertung/GEDCOM-Abgleich.", "en": "Loads names, sex, tree status/size and whether a\ncommon ancestor exists (20 matches per request).\nThen: load 'Ancestors & places' + 'Pedigrees' for ALL matches\nwith a tree (not only the ones Ancestry detected) — then analysis/GEDCOM matching."},
    "dl.help_shared": {"de": "Lädt für jeden gespeicherten Match dessen gemeinsame Matches mit cM-Werten.\nEmpfehlung: erst Matches (A) herunterladen, dann Shared Matches (B).\nAb 20 cM sinnvoll – erfasst auch entferntere Verwandte.\nTipp: Höherer cM-Wert = deutlich weniger primäre Matches = viel schneller (kann sonst Stunden dauern).", "en": "Loads the shared matches (with cM values) for every stored match.\nRecommendation: download matches (A) first, then shared matches (B).\nUseful from 20 cM — also captures more distant relatives.\nTip: a higher cM value = far fewer primary matches = much faster (can otherwise take hours)."},
    "dl.help_all": {"de": "Führt A+A2+Vorfahren+B nacheinander aus: Matches → Namen → Vorfahren → Shared Matches.\nKann über Nacht laufen. Einzelne Phasen können trotzdem separat (oben) gestartet werden.", "en": "Runs A+A2+ancestors+B in sequence: matches → names → ancestors → shared matches.\nCan run overnight. Individual phases can still be started separately (above)."},
    "dl.help_ethnicity": {"de": "Lädt die Ethnizitäts-Auswertung (Ancestry + MyHeritage) und die Ancestry DNA-Traits einmalig.\nErgebnis wird im Statistik-Tab dauerhaft angezeigt.", "en": "Loads the ethnicity analysis (Ancestry + MyHeritage) and the Ancestry DNA traits once.\nThe result is shown permanently in the Statistics tab."},
    "dl.m_session_expired_full": {"de": "Die Ancestry-Sitzung ist abgelaufen (HTTP 401/403).\n\nBitte:\n1. ancestry.com im Browser öffnen und einloggen\n2. Cookies neu exportieren (cookies.txt)\n3. Download erneut starten", "en": "The Ancestry session has expired (HTTP 401/403).\n\nPlease:\n1. open ancestry.com in the browser and log in\n2. re-export cookies (cookies.txt)\n3. start the download again"},
    "dl.m_session_expired_short": {"de": "Die Ancestry-Sitzung ist abgelaufen (HTTP 401/403).\n\nBitte Cookies neu exportieren und erneut starten.", "en": "The Ancestry session has expired (HTTP 401/403).\n\nPlease re-export cookies and start again."},
    "tl.b_guide": {"de": "📖 Anleitung öffnen", "en": "📖 Open guide"},
    "tl.guide_frame": {"de": "📋 Anleitung – empfohlener Ablauf", "en": "📋 Guide – recommended workflow"},
    "tl.b_dbdel": {"de": "🗑 DB löschen", "en": "🗑 Delete DB"},
    "tl.b_impmatch": {"de": "🔗 Anverwandte-Matches importieren", "en": "🔗 Import relative matches"},
    "tl.dbdel_t": {"de": "DB löschen", "en": "Delete DB"},
    "tl.t_save_gedcom": {"de": "GEDCOM speichern unter", "en": "Save GEDCOM as"},
    "tl.b_open": {"de": "▶ Öffnen", "en": "▶ Open"},
    "tl.m_no_crawl_db": {"de": "Keine Crawl-Datenbank gefunden.", "en": "No crawl database found."},
    "tl.m_choose_parish": {"de": "Bitte mindestens eine Pfarrei auswählen.", "en": "Please select at least one parish."},
    "tl.header": {"de": "🔧 Werkzeuge & Import", "en": "🔧 Tools & import"},
    "tl.note": {"de": "Hinweis: Viele Tools brauchen vorher einen Login im Browser (Ancestry/MyHeritage) bzw. eine gewählte Datei. Vollständige Schritt-für-Schritt-Anleitung: „📖 Anleitung öffnen\".", "en": "Note: many tools require a prior browser login (Ancestry/MyHeritage) or a selected file. Full step-by-step guide: \"📖 Open guide\"."},
    "tl.c_dryrun": {"de": "nur Bilder laden, kein OCR (--dry-run)", "en": "only load images, no OCR (--dry-run)"},
    "tl.c_incomplete": {"de": "unvollständige (<10) nachholen", "en": "catch up incomplete (<10)"},
    "tl.places_hint": {"de": "Rohorte anzeigen, automatische Normalisierung prüfen und manuelle Überschreibungen setzen.", "en": "Show raw places, check automatic normalization and set manual overrides."},
    "tl.mapping_file": {"de": "Mapping-Datei:", "en": "Mapping file:"},
    "cl.no_coords_t": {"de": "Keine Orte mit Koordinaten", "en": "No places with coordinates"},
    "cl.m_no_coords": {"de": "Keine Geburtsorte mit Koordinaten gefunden.\n→ Erst 'Vorfahren & Orte' laden (liefert Koordinaten).", "en": "No birthplaces with coordinates found.\n→ Load 'Ancestors & places' first (provides coordinates)."},
    "cl.tree_legend": {"de": "Grün = alle Mitglieder teilen diese Person  |  Gelb = ≥3 Mitglieder  |  Orange = 2 Mitglieder  |  Weiß = nur 1 Mitglied  →  mehr = wahrscheinlicherer Vorfahre", "en": "Green = all members share this person  |  Yellow = ≥3 members  |  Orange = 2 members  |  White = only 1 member  →  more = more likely ancestor"},
    "pe.b_back": {"de": "◀ Zurück", "en": "◀ Back"},
    "pe.not_found": {"de": "Person nicht gefunden.", "en": "Person not found."},
    "pe.founded": {"de": "Gegründet", "en": "Founded"},
    "lg.t_cookie": {"de": "Cookie-JSON wählen", "en": "Choose cookie JSON"},
    "lg.no_file_t": {"de": "Keine Datei", "en": "No file"},
    "lg.m_choose_cookie": {"de": "Bitte Cookie-Datei auswählen.", "en": "Please select a cookie file."},
    "lg.no_guid_t": {"de": "Keine GUID", "en": "No GUID"},
    "lg.m_enter_guid": {"de": "Bitte eine Kit-GUID eingeben.", "en": "Please enter a kit GUID."},
    "lg.cookie_steps": {"de": "1. Chrome/Firefox-Extension »Cookie-Editor« installieren\n2. Auf ancestry.com einloggen\n3. Cookie-Editor → Export → JSON → speichern\n4. Datei hier auswählen", "en": "1. Install the Chrome/Firefox extension \"Cookie-Editor\"\n2. Log in on ancestry.com\n3. Cookie-Editor → Export → JSON → save\n4. Choose the file here"},
    "mf.b_bridge": {"de": "⚡ GEDmatch-Brücke", "en": "⚡ GEDmatch bridge"},
    "mf.b_dups": {"de": "👥 Duplikate prüfen", "en": "👥 Check duplicates"},
    "mf.b_open_anc": {"de": "🔗 In Ancestry öffnen", "en": "🔗 Open in Ancestry"},
    "mf.no_name_t": {"de": "Kein Name", "en": "No name"},
    "mf.m_no_name": {"de": "Für diesen Match ist kein Name bekannt.", "en": "No name is known for this match."},
    "dlg.save": {"de": "Speichern", "en": "Save"},
    "av.m_no_ped_cluster": {"de": "Keine Ahnentafel-Daten für diesen Cluster vorhanden.\n→ Erst 'Ahnentafeln laden' ausführen.", "en": "No pedigree data available for this cluster.\n→ Run 'Load pedigrees' first."},
    "av.no_clusters_t": {"de": "Keine Cluster", "en": "No clusters"},
    "av.sel_anc_namemap": {"de": "Ausgewählter Vorfahr → Namenskarte:", "en": "Selected ancestor → name map:"},
    "av.phasing_head": {"de": "Phasing-Dashboard · 4 Großelternlinien (Leeds)", "en": "Phasing dashboard · 4 grandparent lines (Leeds)"},
    "av.too_little_data": {"de": "Zu wenig Daten – Ahnentafeln der Mitglieder laden.", "en": "Too little data – load the members’ pedigrees."},
    "av.no_gedcom_note": {"de": "(GEDCOM nicht geladen → ohne Andock-Spalte. Über 'Cluster-Linie in meinem Baum suchen' wird der Baum geladen.)", "en": "(GEDCOM not loaded → without anchor column. The tree is loaded via 'Find cluster line in my tree'.)"},
    "av.no_pairwise_cm": {"de": "Keine paarweisen cM gespeichert. Dafür müssen die Shared Matches der Mitglieder geladen sein (Schritt B).", "en": "No pairwise cM stored. This requires the members’ shared matches to be loaded (step B)."},
    "av.no_direct_hit": {"de": "Kein Treffer auf deiner direkten Ahnenlinie – untenstehende sind Seitenlinien/Vorschläge.", "en": "No hit on your direct ancestral line – those below are side lines/suggestions."},
    "av.no_tree_hits": {"de": "Keine Treffer im Baum. Mögliche Gründe: Cluster-Mitglieder haben (noch) keine Ahnentafel geladen, oder die Linie liegt tiefer → ‚Cluster tiefer laden'.", "en": "No hits in the tree. Possible reasons: cluster members have no pedigree loaded (yet), or the line is deeper → 'Load cluster deeper'."},
    "av.empty_slot": {"de": "(leer – kein Cluster)", "en": "(empty – no cluster)"},
    "av.not_in_tree": {"de": "❗ NICHT in deinem Baum → Forschungsziel: diese Person suchen/eintragen, dann liefert Ancestry ThruLines-Hints für den ganzen Cluster.", "en": "❗ NOT in your tree → research goal: find/add this person, then Ancestry provides ThruLines hints for the whole cluster."},
    "av.mrca_title": {"de": "Schätzung gemeinsamer Vorfahr (MRCA)", "en": "Estimated common ancestor (MRCA)"},
    "av.primary_from_cm": {"de": "Primäre Matches ab (cM):", "en": "Primary matches from (cM):"},
    "av.net_legend": {"de": "● Knotengröße ∝ cM  ·  Liniendicke ∝ shared cM zwischen Matches  ·  Farbe = Cluster", "en": "● Node size ∝ cM  ·  line width ∝ shared cM between matches  ·  color = cluster"},
    "av.no_clusters_load_b": {"de": "Keine Cluster – erst Shared Matches laden (Schritt B).", "en": "No clusters – load shared matches first (step B)."},
    "av.m_no_shared_anc2": {"de": "Noch keine geteilten Vorfahren gefunden.\nErst 'Vorfahren & Orte laden' ausführen.", "en": "No shared ancestors found yet.\nRun 'Load ancestors & places' first."},
    "av.incomplete_peds": {"de": "Matches mit unvollständigen Ahnentafeln (nach Generation):", "en": "Matches with incomplete pedigrees (by generation):"},
    "av.min_overlap": {"de": "cM    Min. Überlappung:", "en": "cM    Min. overlap:"},
    "av.phasing_warn": {"de": "⚠  Ohne Phasing können IBD- und IBS-Segmente verwechselt werden. GEDmatch-Segmente (Chromosome-Browser) empfohlen; MyHeritage ohne Phasing ist weniger zuverlässig.", "en": "⚠  Without phasing, IBD and IBS segments can be confused. GEDmatch segments (chromosome browser) recommended; MyHeritage without phasing is less reliable."},
    "av.no_tgs": {"de": "Keine TGs – erst DNA-Segmente laden (import_segments.py) und Shared Matches abrufen.", "en": "No TGs – load DNA segments first (import_segments.py) and fetch shared matches."},
    "av.m_choose_surname": {"de": "Bitte zuerst einen Nachnamen auswählen.", "en": "Please select a surname first."},
    "av.b_namenskarte": {"de": "🗺 Namenskarte.com öffnen", "en": "🗺 Open Namenskarte.com"},
    "av.b_gmaps": {"de": "🗺 Google Maps öffnen", "en": "🗺 Open Google Maps"},
    "av.loading": {"de": "Lädt …", "en": "Loading …"},
    "av.surname_entropy": {"de": "Nachnamen-Entropie", "en": "Surname entropy"},
    "av.no_data_load_ged": {"de": "Keine Daten – GEDCOM oder Match-Ahnentafeln laden.", "en": "No data – load GEDCOM or match pedigrees."},
    "av.no_migration": {"de": "Keine Migrations-Daten – Ahnentafeln und GEDCOM laden.", "en": "No migration data – load pedigrees and GEDCOM."},
    "av.cm_hist_hint": {"de": "Häufigkeit der geteilten cM über alle Matches — Spitze links = viele entfernte Cousins, Ausreißer rechts = nahe Verwandte.", "en": "Frequency of shared cM across all matches — peak on the left = many distant cousins, outliers on the right = close relatives."},
    "av.no_matches_found": {"de": "Keine Matches gefunden.", "en": "No matches found."},
    "av.entropy_hint": {"de": "Shannon-Entropie der Nachnamen pro Jahrzehnt — Einbrüche = Gründereffekt / Datenlücke, Anstieg = Zuzug / bessere Quellenabdeckung.", "en": "Shannon entropy of surnames per decade — dips = founder effect / data gap, rises = immigration / better source coverage."},
    "av.entropy_axis": {"de": "Nachnamen-Entropie pro Jahrzehnt (Shannon H, bits)", "en": "Surname entropy per decade (Shannon H, bits)"},
    "av.parent_child_region": {"de": "Elternregion → Kindregion: wo sind die Kinder im Vergleich zu den Eltern geboren?", "en": "Parent region → child region: where were the children born compared to the parents?"},
    "av.matches_surname": {"de": "Matches mit diesem Nachnamen:", "en": "Matches with this surname:"},
    "av.matches_place": {"de": "Matches mit diesem Ort:", "en": "Matches with this place:"},
    "av.next_steps": {"de": "Nächste Schritte (regelbasiert)", "en": "Next steps (rule-based)"},
    "av.reload": {"de": "↻ Neu laden", "en": "↻ Reload"},
    "av.close": {"de": "Schließen", "en": "Close"},
    "av.tg_members": {"de": "Mitglieder der Triangulationsgruppe:", "en": "Members of the triangulation group:"},
    "st.cm_hist": {"de": "cM-Histogramm der Matches:", "en": "cM histogram of the matches:"},
    "mat.m_choose_parish": {"de": "Bitte eine Pfarrei wählen.", "en": "Please select a parish."},
    "mat.api_missing_t": {"de": "API-Key fehlt", "en": "API key missing"},
    "mat.m_no_api_key": {"de": "ANTHROPIC_API_KEY ist nicht gesetzt.\n\nOhne diesen Schlüssel kann Claude Vision die Kirchenbuch-Seiten nicht transkribieren — der Scan wird nach dem ersten Bild fehlschlagen.\n\nTrotzdem starten? (Sinnvoll nur bei --dry-run oder Re-Transkription von bereits vorhandenen Bildern.)", "en": "ANTHROPIC_API_KEY is not set.\n\nWithout this key Claude Vision cannot transcribe the parish-register pages — the scan will fail after the first image.\n\nStart anyway? (Only sensible for --dry-run or re-transcription of existing images.)"},
    "gr.no_cluster_calc": {"de": "Cluster nicht berechnet", "en": "Clusters not calculated"},
    "av.tg_export": {"de": "🖨 Bericht (HTML/PDF)", "en": "🖨 Report (HTML/PDF)"},
    "mf.endo_auto": {"de": "🔇 Endogamie auto-markieren", "en": "🔇 Auto-flag endogamy"},
    "mf.endo_auto_done": {"de": "{n} Matches als Endogamie-Verdacht markiert.", "en": "{n} matches flagged as endogamy suspects."},
    "tt.mf_endo_auto": {"de": "Matches mit vielen kurzen Segmenten automatisch als Endogamie-Verdacht kennzeichnen", "en": "Automatically flag matches with many short segments as endogamy suspects"},
    "tt.pick_file": {"de": "Datei wählen …", "en": "Choose file …"},
    # Statistics tab
    "st.refresh":   {"de": "↻ Aktualisieren",                     "en": "↻ Refresh"},
    "st.kz":        {"de": "Kennzahlen",                           "en": "Key Figures"},
    "st.total":     {"de": "Gesamtzahl Matches:",                  "en": "Total matches:"},
    "st.max_cm":    {"de": "Höchste cM:",                          "en": "Highest cM:"},
    "st.avg_cm":    {"de": "Ø cM:",                                "en": "Avg. cM:"},
    "st.starred":   {"de": "Markierte:",                           "en": "Starred:"},
    "st.with_tree": {"de": "Mit Stammbaum:",                       "en": "With tree:"},
    "st.with_note": {"de": "Mit Notiz:",                           "en": "With note:"},
    "st.shared_tot":{"de": "Shared-Match-Einträge:",               "en": "Shared match entries:"},
    "st.shared_pri":{"de": "Primäre m. Shared:",                   "en": "Primary w. shared:"},
    "st.rel_dist":  {"de": "Beziehungsverteilung (Top 10)",        "en": "Relationship distribution (top 10)"},
    "st.rel":       {"de": "Beziehung",                            "en": "Relationship"},
    "st.count":     {"de": "Anzahl",                               "en": "Count"},
    "st.ped_kz":    {"de": "Ahnentafel-Vollständigkeit",           "en": "Pedigree completeness"},
    "st.ped_loaded":{"de": "Ahnentafeln geladen:",                 "en": "Pedigrees loaded:"},
    "st.ped_depth": {"de": "Ø Generationstiefe:",                  "en": "Avg. generation depth:"},
    "st.ped_surn":  {"de": "Unterschiedliche Nachnamen:",          "en": "Distinct surnames:"},
    "st.gen_length":{"de": "Ø Generationsabstand:",               "en": "Avg. generation span:"},
    "st.ged_kz":    {"de": "GEDCOM-Brücke",                        "en": "GEDCOM Bridge"},
    "st.ged_pers":  {"de": "GEDCOM-Personen:",                     "en": "GEDCOM persons:"},
    "st.ged_linked":{"de": "Matches mit Treffer:",                  "en": "Matches with hits:"},
    "st.side_kz":   {"de": "Seitenzuweisung",                      "en": "Side Assignment"},
    "st.side_pat":  {"de": "🔵 Väterlich:",                        "en": "🔵 Paternal:"},
    "st.side_mat":  {"de": "🔴 Mütterlich:",                       "en": "🔴 Maternal:"},
    "st.side_open": {"de": "❓ Nicht zugewiesen:",                  "en": "❓ Unassigned:"},
    "st.kit_kz":    {"de": "Kits & Matches",                       "en": "Kits & Matches"},
    # Menu bar — cascade labels
    "mn.file":      {"de": "Datei",                                "en": "File"},
    "mn.view":      {"de": "Ansicht",                              "en": "View"},
    "mn.analysis":  {"de": "Auswertung",                           "en": "Analysis"},
    "mn.help":      {"de": "Hilfe",                                "en": "Help"},
    # File menu items
    "mn.exp_csv":   {"de": "Matches als CSV …",                    "en": "Matches as CSV …"},
    "mn.exp_xlsx":  {"de": "Matches als XLSX …",                   "en": "Matches as XLSX …"},
    "mn.exp_sh_csv":{"de": "Shared Matches als CSV …",             "en": "Shared matches as CSV …"},
    "mn.exp_all":   {"de": "Alles als XLSX (2 Blätter)…",          "en": "All as XLSX (2 sheets)…"},
    "mn.imp_names": {"de": "Namen importieren (JSON/CSV) …",       "en": "Import names (JSON/CSV) …"},
    "mn.quit":      {"de": "Beenden",                              "en": "Quit"},
    # View menu items
    "mn.refresh_t": {"de": "Tabelle aktualisieren",                "en": "Refresh table"},
    "mn.recalc_cl": {"de": "Cluster neu berechnen",                "en": "Recalculate clusters"},
    "mn.language":  {"de": "🌐 Sprache: Deutsch / English",        "en": "🌐 Language: Deutsch / English"},
    # Analysis menu items
    "mn.anc_groups":{"de": "Gemeinsame Vorfahren (Überlagerung) …","en": "Common ancestors (overlay) …"},
    "mn.exp_anc":   {"de": "Vorfahren-Gruppen als CSV …",          "en": "Ancestor groups as CSV …"},
    "mn.pedigree":  {"de": "Ahnentafel des Matches anzeigen …",    "en": "Show match pedigree …"},
    "mn.ped_overlay":{"de": "Pedigree-Überlagerung (Cluster) …",   "en": "Pedigree overlay (cluster) …"},
    "mn.own_tree":  {"de": "Eigenen Baum (GEDCOM) abgleichen …",   "en": "Match own tree (GEDCOM) …"},
    "mn.sh_cluster":{"de": "Shared-Cluster (Triangulation) …",     "en": "Shared cluster (triangulation) …"},
    "mn.seg_triang":{"de": "Segment-Triangulation …",               "en": "Segment triangulation …"},
    "mn.reset_sh":  {"de": "Shared Matches zurücksetzen (neu laden) …",
                     "en": "Reset shared matches (reload) …"},
    "mn.reset_nm":  {"de": "Namens-Versuche zurücksetzen (alle erneut) …",
                     "en": "Reset name attempts (all again) …"},
    "mn.refresh_lk":{"de": "Verknüpfungen aktualisieren (View in tree) …",
                     "en": "Update links (view in tree) …"},
    "mn.chg_ged":   {"de": "GEDCOM / Wurzelperson ändern …",       "en": "Change GEDCOM / root person …"},
    # Help menu items
    "mn.about":     {"de": "Über …",                               "en": "About …"},
    "mn.shortcuts": {"de": "Tastenkürzel …",                       "en": "Keyboard shortcuts …"},
    # New analysis windows
    "mn.surnames":  {"de": "Nachname-Analyse (Namenskarte) …",     "en": "Surname analysis (name map) …"},
    "mn.places":    {"de": "Geburtsort-Analyse …",                 "en": "Birth place analysis …"},
    "mn.mrca":      {"de": "MRCA-Wahrscheinlichkeit …",            "en": "MRCA probability …"},
    "mn.net_graph": {"de": "Cluster-Netzwerkgraph …",              "en": "Cluster network graph …"},
    # Dark mode
    "mn.darkmode":  {"de": "🌙 Dunkelmodus",                       "en": "🌙 Dark mode"},
    # New export/analysis menu items
    "mn.exp_ged":   {"de": "Vorfahren als GEDCOM exportieren …",   "en": "Export ancestors as GEDCOM …"},
    "mn.exp_gramps":{"de": "Vorfahren als Gramps XML exportieren …","en": "Export ancestors as Gramps XML …"},
    "mn.imp_mta":   {"de": "MyTrueAncestry CSV importieren …",     "en": "Import MyTrueAncestry CSV …"},
    "mn.ped_gaps":  {"de": "Ahnentafel-Lücken analysieren …",      "en": "Pedigree gap analysis …"},
    "mn.ped_chart": {"de": "🌳 Ahnentafel-Diagramm …",            "en": "🌳 Pedigree chart …"},
    "mn.auto_sides":{"de": "Seiten automatisch zuweisen (Mutter-Kit)…",
                     "en": "Auto-assign sides (mother kit)…"},
    "mn.endo_score":{"de": "Endogamie-Score-Analyse …",            "en": "Endogamy score analysis …"},
    "mn.cl_timeline":{"de": "Cluster-Zeitachse …",                 "en": "Cluster timeline …"},
    "mn.pop_stats":  {"de": "Bevölkerungsstatistiken …",           "en": "Population statistics …"},
    "mn.dashboard":  {"de": "🏅 Forschungs-Dashboard …",          "en": "🏅 Research dashboard …"},
    "mn.copilot_cl": {"de": "🤖 Cluster erklären (Copilot) …",    "en": "🤖 Explain cluster (copilot) …"},
    # Quick-filter chips
    "mf.chip_star": {"de": "★ Markierte",    "en": "★ Starred"},
    "mf.chip_tree": {"de": "🌳 Mit Baum",    "en": "🌳 With tree"},
    "mf.chip_200":  {"de": ">200 cM",        "en": ">200 cM"},
    "mf.chip_pat":  {"de": "🔵 Väterlich",   "en": "🔵 Paternal"},
    "mf.chip_mat":  {"de": "🔴 Mütterlich",  "en": "🔴 Maternal"},
    "mf.chip_new":  {"de": "🆕 Neu (7 Tage)", "en": "🆕 New (7 days)"},
    # Empty state
    "mf.empty":     {"de": "📭  Noch keine Matches geladen",       "en": "📭  No matches loaded yet"},
    "mf.empty_hint":{"de": "→ Tab »Herunterladen« öffnen",         "en": "→ Open »Download« tab"},
    # Download dashboard
    "dl.pause":     {"de": "⏸ Pause",        "en": "⏸ Pause"},
    "dl.resume":    {"de": "▶ Fortsetzen",   "en": "▶ Resume"},
    "dl.eta":       {"de": "Verbleibend:",   "en": "Remaining:"},
    "dl.dash_mat":  {"de": "🧬 Matches",     "en": "🧬 Matches"},
    "dl.dash_tree": {"de": "🌳 Mit Baum",    "en": "🌳 With tree"},
    "dl.dash_sh":   {"de": "👥 Shared",      "en": "👥 Shared"},
    "dl.dash_err":  {"de": "❌ Fehler",      "en": "❌ Errors"},
    # Detail panel
    "md.rel_prob":  {"de": "Beziehungswahrscheinlichkeit",         "en": "Relationship probability"},
    "md.checklist": {"de": "Forschungs-Checkliste",                "en": "Research checklist"},
    "md.chk0":      {"de": "Baum angeschaut",                      "en": "Tree reviewed"},
    "md.chk1":      {"de": "Nachricht gesendet",                   "en": "Message sent"},
    "md.chk2":      {"de": "Gemeinsame Vorfahren geprüft",         "en": "Common ancestors checked"},
    "md.chk3":      {"de": "In Cluster eingeordnet",               "en": "Assigned to cluster"},
    "md.chk4":      {"de": "Seite zugewiesen (v/m)",               "en": "Side assigned (p/m)"},
    "md.fs_link":   {"de": "🔍 FamilySearch …",                    "en": "🔍 FamilySearch …"},
    "md.tab_gedcom":{"de": "🌳 GEDCOM-Treffer",                   "en": "🌳 GEDCOM Hits"},
    "md.tab_ancestors":{"de": "👨‍👩‍👧 Gemeinsame Vorfahren",           "en": "👨‍👩‍👧 Common Ancestors"},
    "md.tab_kirchenbuch":{"de": "⛪ Kirchenbücher",                 "en": "⛪ Church Records"},
    "md.tab_wikitree":  {"de": "🌐 WikiTree",                      "en": "🌐 WikiTree"},
    "md.wt_no_match":   {"de": "Kein Match ausgewählt.",            "en": "No match selected."},
    "md.wt_search":     {"de": "🔍 WikiTree-Suche öffnen",         "en": "🔍 Open WikiTree search"},
    "md.wt_profile":    {"de": "Profil öffnen",                    "en": "Open profile"},
    "md.wt_no_data":    {"de": "Keine WikiTree-Daten vorhanden.\nEinmalig »🔗 WikiTree« (GEDCOM-Tab) ausführen.",
                         "en": "No WikiTree data available.\nRun »🔗 WikiTree« (GEDCOM tab) once."},
    "md.kb_min_gen": {"de": "ab Generation:",                       "en": "from generation:"},
    "md.kb_reload":  {"de": "↻ Suchen",                             "en": "↻ Search"},
    "md.kb_no_ped":  {"de": "Keine Ahnentafel für diesen Match.\n"
                            "Erst Schritt C (Ahnentafeln laden) ausführen.",
                      "en": "No pedigree for this match.\n"
                            "Run step C (load pedigrees) first."},
    "md.kb_no_db":   {"de": "Keine Kirchenbuch-Daten in der Datenbank.\n"
                            "Zuerst Matricula-Scan starten (⛪ Matricula-Tab).",
                      "en": "No church record data in database.\n"
                            "Start a Matricula scan first (⛪ Matricula tab)."},
    "md.kb_no_hits": {"de": "Keine Treffer für die Nachnamen aus der Ahnentafel.",
                      "en": "No matches for surnames from the pedigree."},
    "md.kb_surnames":{"de": "Gesuchte Nachnamen:",                  "en": "Surnames searched:"},
    "md.anc_none":  {"de": "Keine gemeinsamen Vorfahren von Ancestry heruntergeladen.",
                     "en": "No common ancestors downloaded from Ancestry."},
    "md.ged_none":  {"de": "Kein GEDCOM geladen – Analyse → Eigenen Baum abgleichen",
                     "en": "No GEDCOM loaded – Analysis → Match own tree"},
    "md.ged_no_ped":{"de": "Keine Ahnentafel-Daten für diesen Match.",
                     "en": "No pedigree data for this match."},
    "md.ged_searching": {"de": "Suche …", "en": "Searching …"},
    "md.ged_run_all":   {"de": "🔄 Alle Matches abgleichen", "en": "🔄 Match all"},
    # Cluster tab
    "cl.quality":   {"de": "Güte",           "en": "Quality"},
    "cl.desc":      {"de": "Cluster-Beschreibung:",                "en": "Cluster description:"},
    "cl.timeline":  {"de": "📅 Zeitachse",   "en": "📅 Timeline"},
    "cl.assign_side": {"de": "⚡ Seite zuweisen", "en": "⚡ Assign side"},
    "cl.phasing":   {"de": "🧭 Phasing-Dashboard", "en": "🧭 Phasing dashboard"},
    "cl.mrca_map":  {"de": "🗺 MRCA-Karte", "en": "🗺 MRCA map"},

    # ── Tooltips (Hover-Hinweise) ──────────────────────────────────────────
    "tt.lg_choose": {"de": "Exportierte Cookie-JSON-Datei auswählen",
                     "en": "Choose the exported cookie JSON file"},
    "tt.lg_login":  {"de": "Mit den geladenen Cookies bei Ancestry anmelden",
                     "en": "Sign in to Ancestry with the loaded cookies"},
    "tt.lg_guid":   {"de": "Test-GUID manuell übernehmen (ohne Cookie-Login)",
                     "en": "Use the test GUID manually (without cookie login)"},
    "tt.mf_sides":  {"de": "Matches automatisch väterlich/mütterlich zuordnen "
                           "(braucht Eltern-Kit oder GEDCOM/Ancestry-Seite)",
                     "en": "Auto-assign matches paternal/maternal "
                           "(needs a parent kit or GEDCOM/Ancestry side)"},
    "tt.mf_bridge": {"de": "GEDmatch-Kits mit Ancestry-Matches verknüpfen",
                     "en": "Link GEDmatch kits with Ancestry matches"},
    "tt.md_note":   {"de": "Notiz zu diesem Match speichern",
                     "en": "Save a note for this match"},
    "tt.md_anc":    {"de": "Dieses Match auf ancestry.com im Browser öffnen",
                     "en": "Open this match on ancestry.com in the browser"},
    "tt.md_fs":     {"de": "Namen dieses Matches auf FamilySearch suchen",
                     "en": "Search this match's names on FamilySearch"},
    "tt.md_chrom":  {"de": "Chromosomen-Browser: geteilte Segmente dieses Matches, "
                           "eingefärbt nach Seite",
                     "en": "Chromosome browser: this match's shared segments, "
                           "coloured by side"},
    "tt.md_tasks":  {"de": "Forschungsaufgaben (To-Dos) für dieses Match",
                     "en": "Research tasks (to-dos) for this match"},
    "tt.md_choose": {"de": "GEDCOM-Datei wählen (für den Stammbaum-Abgleich)",
                     "en": "Choose a GEDCOM file (for tree matching)"},
    "tt.md_origin": {"de": "Wahrscheinliche Herkunft der Matches aus den Ahnen-Orten ableiten",
                     "en": "Infer likely match origins from ancestral places"},
    "tt.md_wikitree": {"de": "Ahnentafel über WikiTree erweitern",
                       "en": "Extend the pedigree via WikiTree"},
    "tt.md_ml":     {"de": "Herkunft per ML-Modell schätzen",
                     "en": "Estimate origin via the ML model"},
    "tt.md_dup":    {"de": "Querverweise/Duplikate zwischen Matches und Baum prüfen",
                     "en": "Review cross-references/duplicates between matches and tree"},
    "tt.md_endo":   {"de": "Endogamie-Erkenntnisse auf die Matches übertragen",
                     "en": "Transfer endogamy findings onto the matches"},
    "tt.md_runall": {"de": "Alle Matches gegen die GEDCOM-Datei abgleichen",
                     "en": "Match all matches against the GEDCOM file"},
    "tt.cl_calc":   {"de": "Cluster aus den Shared Matches neu berechnen (Leeds-Methode)",
                     "en": "Recompute clusters from shared matches (Leeds method)"},
    "tt.cl_modularity": {"de": "Modularitäts-Clustering (Louvain) statt Leeds/Union-Find — "
                               "robuster gegen über-geteilte Brücken-Matches",
                         "en": "Modularity clustering (Louvain) instead of Leeds/union-find — "
                               "more robust against over-shared bridge matches"},
    "tt.cl_tree":   {"de": "Kombinierten Stammbaum des gewählten Clusters anzeigen",
                     "en": "Show the combined tree of the selected cluster"},
    "tt.cl_timeline": {"de": "Geburtsjahre der Cluster-Vorfahren als Zeitachse",
                       "en": "Birth years of the cluster ancestors as a timeline"},
    "tt.cl_assign": {"de": "Allen Matches des Clusters eine Elternseite zuweisen",
                     "en": "Assign a parental side to all matches in the cluster"},
    "tt.cl_phasing": {"de": "Ordnet die 4 größten Cluster den Großelternlinien zu (Leeds)",
                      "en": "Maps the 4 largest clusters to the grandparent lines (Leeds)"},
    "tt.cl_mrca":   {"de": "Geburtsorte der gemeinsamen Vorfahren als Leaflet-Karte (Browser)",
                     "en": "Birthplaces of common ancestors as a Leaflet map (browser)"},
    "tt.st_refresh": {"de": "Statistik neu berechnen (kann bei großen Beständen dauern)",
                      "en": "Recompute statistics (may be slow for large datasets)"},
    "tt.pe_dedup":  {"de": "Mögliche doppelte Personen im Baum finden und zusammenführen",
                     "en": "Find and merge possible duplicate persons in the tree"},
    "tt.pe_back":   {"de": "Zur zuvor betrachteten Person zurück",
                     "en": "Back to the previously viewed person"},
    "tt.mat_start": {"de": "Kirchenbuch-Scan/Transkription für das gewählte Kirchspiel starten",
                     "en": "Start parish-register scan/transcription for the selected parish"},
    "tt.mat_stop":  {"de": "Laufenden Scan abbrechen",
                     "en": "Cancel the running scan"},
    "tt.mat_refresh": {"de": "Kirchspiel-Liste neu laden",
                       "en": "Reload the parish list"},
    "tt.dl_refresh": {"de": "Auch bereits geladene Ahnentafeln erneuern, deren "
                            "Abruf älter als 30 Tage ist",
                      "en": "Also refresh already-loaded pedigrees older than 30 days"},
    "tt.dl_gmx":    {"de": "Exportiert die Matches des gewählten Kits im "
                           "GEDmatch-One-to-Many-Format (wieder importierbar)",
                     "en": "Export the selected kit's matches as GEDmatch "
                           "One-to-Many format (re-importable)"},
    "tt.tl_guide":  {"de": "Anleitung / empfohlenen Ablauf im Browser öffnen",
                     "en": "Open the guide / recommended workflow in the browser"},
    "tt.tl_logclear": {"de": "Das Log-Fenster leeren",
                       "en": "Clear the log window"},
    "tt.tl_dbdel":  {"de": "Die Webtrees-Crawl-Datenbank löschen (Neustart des Crawls)",
                     "en": "Delete the webtrees crawl database (restart the crawl)"},
    "tt.tl_impmatch": {"de": "Anverwandte-Matches aus CSV in die Datenbank importieren",
                       "en": "Import relative matches from CSV into the database"},
    "tt.tl_places": {"de": "Roh-Orte ansehen, Normalisierung prüfen und Überschreibungen setzen",
                     "en": "Review raw places, check normalization and set overrides"},
    "tt.tl_open":   {"de": "Dieses Werkzeug öffnen",
                     "en": "Open this tool"},
    "tt.tl_start":  {"de": "Dieses Werkzeug im Hintergrund starten",
                     "en": "Start this tool in the background"},
    "tt.tl_stop":   {"de": "Laufenden Prozess abbrechen",
                     "en": "Cancel the running process"},
    "tt.tl_tutorial": {"de": "Schritt-für-Schritt-Tutorial durch alle Tabs starten",
                       "en": "Start the step-by-step tutorial through all tabs"},
    # ── Personen-Tab ────────────────────────────────────────────────────────
    "tt.pe_search": {"de": "Vor- oder Nachname suchen (Teilsuche möglich)",
                     "en": "Search by first or last name (partial match supported)"},
    "tt.pe_src":    {"de": "Personen nach Datenquelle filtern: GEDCOM = eigene Forschung, "
                           "Webtrees = Anverwandte-Crawl, WikiTree = WikiTree-Import",
                     "en": "Filter persons by data source: GEDCOM = own research, "
                           "Webtrees = Anverwandte crawl, WikiTree = WikiTree import"},
    "tt.pe_conf":   {"de": "Personen nach Konfession filtern — abgeleitet aus dem Geburtsort "
                           "via Matricula-Pfarreikatalog (kath./ev./unbekannt)",
                     "en": "Filter persons by religion — derived from birthplace "
                           "via Matricula parish catalogue (cath./prot./unknown)"},
    "tt.pe_depth":  {"de": "Anzahl der Vorfahren-Generationen im Stammbaum-Canvas (1–5)",
                     "en": "Number of ancestor generations shown in the tree canvas (1–5)"},
    # ── Matricula-Tab ────────────────────────────────────────────────────────
    "tt.mat_ner":   {"de": "Namen und Rollen aus transkribierten Einträgen extrahieren "
                           "(Taufpaten, Eltern, Zeugen …) — befüllt die Personen-NER-Tabelle",
                     "en": "Extract names and roles from transcribed entries "
                           "(godparents, parents, witnesses …) — populates the persons NER table"},
    "tt.mat_ocr":   {"de": "Aktive OCR-Engine (Umgebungsvariable MATRICULA_OCR_BACKEND). "
                           "claude = Claude Vision API (kostenpflichtig, strukturiert); "
                           "tesseract = lokal/gratis, gut für gedruckte Register; "
                           "kraken = lokal/gratis, für Handschriften (HTR). "
                           "Ändern: MATRICULA_OCR_BACKEND=tesseract in der Umgebung setzen.",
                     "en": "Active OCR engine (env var MATRICULA_OCR_BACKEND). "
                           "claude = Claude Vision API (paid, structured output); "
                           "tesseract = local/free, good for printed registers; "
                           "kraken = local/free, for handwritten records (HTR). "
                           "Change: set MATRICULA_OCR_BACKEND=tesseract in your environment."},
    "dlg.no_kit": {"de": "Kein Kit", "en": "No kit"},
    "dlg.no_data": {"de": "Keine Daten", "en": "No data"},
    "dlg.m_choose_kit": {"de": "Bitte zuerst ein DNA-Kit wählen.", "en": "Please select a DNA kit first."},
    "dlg.done": {"de": "Fertig", "en": "Done"},
    "dlg.no_cluster": {"de": "Kein Cluster", "en": "No cluster"},
    "dlg.error": {"de": "Fehler", "en": "Error"},
    "dlg.m_choose_cluster": {"de": "Bitte einen Cluster wählen.", "en": "Please select a cluster."},
    "dlg.gedcom": {"de": "GEDCOM", "en": "GEDCOM"},
    "dlg.m_no_matches": {"de": "Keine Matches vorhanden.", "en": "No matches available."},
    "dlg.import_error": {"de": "Import-Fehler", "en": "Import error"},
    "dlg.reset_done": {"de": "Zurückgesetzt", "en": "Reset"},
    "dlg.not_logged": {"de": "Nicht eingeloggt", "en": "Not logged in"},
    "dlg.m_login_first": {"de": "Bitte zuerst einloggen.", "en": "Please log in first."},
    "dlg.m_no_csv": {"de": "Keine Zeilen im CSV gefunden.", "en": "No rows found in the CSV."},
    "dlg.export": {"de": "Export", "en": "Export"},
    "dlg.import_done": {"de": "Import abgeschlossen", "en": "Import complete"},
    "dlg.m_no_shared_anc": {"de": "Noch keine geteilten Vorfahren gefunden.", "en": "No shared ancestors found yet."},
    "dlg.no_match": {"de": "Kein Match", "en": "No match"},
    "dlg.m_choose_match": {"de": "Bitte zuerst einen Match in der Tabelle wählen.", "en": "Please select a match in the table first."},
    "dlg.no_pedigree": {"de": "Keine Ahnentafel", "en": "No pedigree"},
    "dlg.m_no_pedigree": {"de": "Für diesen Match ist noch keine Ahnentafel geladen.\nErst '▶ Ahnentafeln laden' ausführen (Match braucht einen Baum).", "en": "No pedigree loaded for this match yet.\nRun '▶ Load pedigrees' first (the match needs a tree)."},
    "dlg.reset_shared": {"de": "Shared Matches zurücksetzen", "en": "Reset shared matches"},
    "dlg.m_reset_shared": {"de": "Alle gespeicherten Shared Matches dieses Kits löschen?\n\nNötig, um die fehlerhaften Alt-Daten (ganze Liste) zu entfernen.\nDanach Tab »Herunterladen« → Schritt B erneut ausführen.", "en": "Delete all stored shared matches for this kit?\n\nNeeded to remove the faulty legacy data (whole list).\nThen run tab \"Download\" → step B again."},
    "dlg.no_pedigrees": {"de": "Keine Ahnentafeln", "en": "No pedigrees"},
    "dlg.m_no_pedigrees": {"de": "Noch keine Ahnentafeln geladen. Erst '▶ Ahnentafeln laden' ausführen.", "en": "No pedigrees loaded yet. Run '▶ Load pedigrees' first."},
    "dlg.wikitree": {"de": "WikiTree", "en": "WikiTree"},
    "dlg.m_no_shared_db": {"de": "Keine Shared Matches in der Datenbank.", "en": "No shared matches in the database."},
    "dlg.no_result": {"de": "Kein Ergebnis", "en": "No result"},
    "dlg.m_no_valid_names": {"de": "Keine gueltigen Namen gefunden.", "en": "No valid names found."},
    "dlg.explain_cluster": {"de": "Cluster erklären", "en": "Explain cluster"},
    "dlg.m_do_clustering": {"de": "Bitte zuerst im Cluster-Tab Clustering durchführen.", "en": "Please run clustering in the Cluster tab first."},
    "dlg.result": {"de": "Ergebnis", "en": "Result"},
    "dlg.side_assigned": {"de": "Seite zugewiesen", "en": "Side assigned"},
    "dlg.side_removed": {"de": "Zuweisung entfernt", "en": "Assignment removed"},
    "dlg.m_no_anc_groups": {"de": "Keine Vorfahren-Gruppen vorhanden.\n→ Erst 'Ahnentafeln laden' ausführen.", "en": "No ancestor groups available.\n→ Run 'Load pedigrees' first."},
    "dlg.deepen_cluster": {"de": "Cluster tiefer laden", "en": "Load cluster deeper"},
    "dlg.duplicates": {"de": "Duplikate", "en": "Duplicates"},
    "dlg.m_no_second_kit": {"de": "Kein zweites Kit verfügbar.", "en": "No second kit available."},
    "dlg.ged_side": {"de": "GEDCOM-Seitenableitung", "en": "GEDCOM side inference"},
    "dlg.db_error": {"de": "Datenbankfehler", "en": "Database error"},
    "dlg.m_gedexport_missing": {"de": "gedcom_export-Modul nicht gefunden.", "en": "gedcom_export module not found."},
    "dlg.quit_q": {"de": "Beenden?", "en": "Quit?"},
    "dlg.no_anc_map": {"de": "Kein Ahnen-Map", "en": "No ancestor map"},
    "dlg.m_load_gedcom": {"de": "Bitte GEDCOM laden und Wurzelperson angeben.", "en": "Please load a GEDCOM and set the root person."},
    "dlg.anc_estimate": {"de": "Ancestry-Schätzung", "en": "Ancestry estimate"},
    "dlg.empty": {"de": "Leer", "en": "Empty"},
    "dlg.m_ged_empty": {"de": "Kein verwertbarer Inhalt im GEDCOM.", "en": "No usable content in the GEDCOM."},
    "dlg.gedmatch_bridge": {"de": "GEDmatch-Brücke", "en": "GEDmatch bridge"},
    "dlg.m_bridge_unloadable": {"de": "bridge.py nicht ladbar.", "en": "bridge.py could not be loaded."},
    "dlg.ged_error": {"de": "GEDCOM-Fehler", "en": "GEDCOM error"},
    "dlg.ml_origin": {"de": "ML-Herkunft", "en": "ML origin"},
    "dlg.deep_pedigrees": {"de": "Tiefe Ahnentafeln", "en": "Deep pedigrees"},
    "dlg.links": {"de": "Verknüpfungen", "en": "Links"},
    "dlg.t_save_anc_groups": {"de": "Vorfahren-Gruppen speichern", "en": "Save ancestor groups"},
    "dlg.l_cm_window": {"de": "cM-Fenster:", "en": "cM window:"},
    "dlg.b_deepen_cluster": {"de": "⤓ Cluster tiefer laden (8 Gen.)", "en": "⤓ Load cluster deeper (8 gen.)"},
    "dlg.t_choose_own_tree": {"de": "Eigenen Stammbaum wählen (GEDCOM)", "en": "Choose your own tree (GEDCOM)"},
    "dlg.c_unreviewed_only": {"de": "nur ungeprüfte", "en": "unreviewed only"},
    "dlg.b_load": {"de": "🔄 Laden", "en": "🔄 Load"},
    "dlg.b_same_person": {"de": "✓ Dieselbe Person (bestätigen)", "en": "✓ Same person (confirm)"},
    "dlg.l_multiselect": {"de": "Mehrfachauswahl möglich (Strg/Shift)", "en": "Multi-select possible (Ctrl/Shift)"},
    "dlg.b_export_xlsx": {"de": "Alles als XLSX exportieren", "en": "Export all as XLSX"},
    "dlg.t_import_names": {"de": "Namen-Datei importieren", "en": "Import names file"},
    "dlg.l_import_anc_est": {"de": "Ancestry-Schätzung importieren (Tag 8 / Cluster-Code):", "en": "Import Ancestry estimate (tag 8 / cluster code):"},
    "dlg.cancel": {"de": "Abbrechen", "en": "Cancel"},
    "dlg.r_paternal": {"de": "🔵 Väterlich (paternal)", "en": "🔵 Paternal"},
    "dlg.r_maternal": {"de": "🔴 Mütterlich (maternal)", "en": "🔴 Maternal"},
    "dlg.r_remove_side": {"de": "✖ Zuweisung entfernen", "en": "✖ Remove assignment"},
    "dlg.t_export_gedcom": {"de": "GEDCOM exportieren", "en": "Export GEDCOM"},
    "dlg.t_export_gramps": {"de": "Gramps XML exportieren", "en": "Export Gramps XML"},
    "dlg.t_import_mta": {"de": "MyTrueAncestry CSV importieren", "en": "Import MyTrueAncestry CSV"},
    "tt.tl_stop":   {"de": "Das laufende Werkzeug stoppen",
                     "en": "Stop the running tool"},
    "dlg.l_no_common_anc": {
        "de": "(Kein gemeinsamer Vorfahr geladen – ggf. "
              "'▶ Vorfahren & Orte laden' ausführen.)",
        "en": "(No common ancestor loaded – run "
              "'▶ Load ancestors & places' if needed.)"},
    "dlg.l_side_estimate_note": {
        "de": "ℹ  Ohne ein Mutter- oder Vater-Kit basiert die Zuweisung nur auf\n"
              "Cluster-Patterns und ist eine Schätzung — keine genealogische Gewissheit.",
        "en": "ℹ  Without a mother or father kit, the assignment is based only on\n"
              "cluster patterns and is an estimate — not genealogical certainty."},
    "pe2.b_save":   {"de": "💾 Speichern", "en": "💾 Save"},
    "pe2.b_reload": {"de": "🔁 Neu laden", "en": "🔁 Reload"},
    "pe2.hint":     {"de": "  Doppelklick → Überschreibung bearbeiten",
                     "en": "  Double-click → edit override"},
    "pe2.col_override": {"de": "Überschreibung", "en": "Override"},
    "pe2.l_override":   {"de": "Überschreibung:", "en": "Override:"},
    "pe2.b_apply":  {"de": "✓ Übernehmen", "en": "✓ Apply"},
    "pe2.b_delete": {"de": "✕ Löschen", "en": "✕ Delete"},
    "pc.no_anc":    {"de": "Keine Vorfahren gefunden.\nBitte zuerst GEDCOM laden und\nWurzelperson setzen.",
                     "en": "No ancestors found.\nPlease load a GEDCOM and\nset the root person first."},
    "pc.no_match_person": {"de": "Kein Anverwandte-Treffer\nfür diese Person.",
                           "en": "No relative match\nfor this person."},
    "pc.max_cm_hint": {"de": "(Maximaler cM-Wert eines Matches, der auf diesen Vorfahren verlinkt)",
                       "en": "(Maximum cM value of a match linking to this ancestor)"},
    "pc.no_db":     {"de": "Kein Datenbankzugang", "en": "No database access"},
    "pc.click_hint": {"de": "  |  Klick auf Kästchen → Details rechts",
                      "en": "  |  Click a box → details on the right"},
    "dr.not_dup":   {"de": "✗ Keine Dublette", "en": "✗ Not a duplicate"},
    "os.no_index":  {"de": "Kein Index — erst 'Index neu bauen' klicken.",
                     "en": "No index — click 'Rebuild index' first."},
    "dlg.about_title": {"de": "Über", "en": "About"},
    "dlg.about_body":  {"de": "Ancestry DNA Tool v2\n\nFunktionen: Matches + "
                              "Shared Matches + Leeds-Clustering\nDatenbank: ",
                        "en": "Ancestry DNA Tool v2\n\nFeatures: matches + "
                              "shared matches + Leeds clustering\nDatabase: "},
    "dlg.shortcuts_body": {
        "de": "Tastenkürzel & Bedienung\n\n"
              "Matches-Tab:\n"
              "  Enter          Detail des ausgewählten Matches öffnen\n"
              "  Esc            Suche leeren / Tabelle zurücksetzen\n"
              "  Rechtsklick    Kontextmenü (in Ancestry öffnen, GUID kopieren,\n"
              "                 Namenskarte, Seite zuweisen …)\n\n"
              "Dialoge / Eingabefelder:\n"
              "  Enter          Eingabe bestätigen (z. B. Notiz speichern,\n"
              "                 Suche starten, Ort-Override anwenden)\n\n"
              "Allgemein:\n"
              "  Mausrad        Scrollen in Listen, Tabellen und im Download-Tab",
        "en": "Keyboard shortcuts & usage\n\n"
              "Matches tab:\n"
              "  Enter          Open the selected match's detail\n"
              "  Esc            Clear search / reset the table\n"
              "  Right-click    Context menu (open in Ancestry, copy GUID,\n"
              "                 name map, assign side …)\n\n"
              "Dialogs / input fields:\n"
              "  Enter          Confirm input (e.g. save note,\n"
              "                 start search, apply place override)\n\n"
              "General:\n"
              "  Mouse wheel    Scroll lists, tables and the Download tab"},
    # Statistics tab
    "st.with_tree_pct": {"de": "Mit Baum %:", "en": "With tree %:"},
    "st.side_pct":      {"de": "Seite bekannt %:", "en": "Side known %:"},
    "st.endo_pct":      {"de": "Cluster bekannt %:", "en": "Cluster known %:"},
    "st.ethnicity":     {"de": "Ethnizität / Herkunft", "en": "Ethnicity / Origins"},
    "st.traits":        {"de": "DNA-Traits (phänotypische Merkmale)", "en": "DNA Traits"},
    # Matches tab — kit bar
    "mf.kit":           {"de": "Kit:",              "en": "Kit:"},
    "mf.sides":         {"de": "⚡ Seiten ableiten","en": "⚡ Assign sides"},
    # GEDCOM link panel buttons
    "md.ged_origin":    {"de": "🗺 Herkunft ableiten",        "en": "🗺 Infer origins"},
    "md.ged_endogamy":  {"de": "🧬 Endogamie übertragen",     "en": "🧬 Transfer endogamy"},
    "md.ged_rerun":     {"de": "↺ Nochmals abgleichen",       "en": "↺ Re-run match"},
    # cluster_views – interne Strukturansicht
    "cv.cm_hint":       {"de": "Hohe cM = nah (Eltern/Kind, Geschwister) → engere Teil-Familien im Cluster. Hilft, die Struktur zu rekonstruieren.",
                         "en": "High cM = close relation (parent/child, siblings) → tighter sub-families in cluster. Helps reconstruct structure."},
    # dedup_review – Hinweistext
    "dr.model_hint":    {"de": "Entscheidungen werden\nals Labels gespeichert\nund trainieren das Modell.",
                         "en": "Decisions are saved\nas labels and train\nthe model."},
    # Ähnlichkeits-Matrix
    "mn.sur_matrix": {"de": "Ähnlichkeits-Matrix (Nachnamen) …", "en": "Similarity matrix (surnames) …"},
    "sm.title":      {"de": "Nachnamen-Ähnlichkeits-Matrix",      "en": "Surname Similarity Matrix"},
    "sm.min_cm":     {"de": "Mindest-cM:",                        "en": "Min cM:"},
    "sm.min_score":  {"de": "Mindest-Jaccard:",                   "en": "Min Jaccard:"},
    "sm.calc":       {"de": "Berechnen",                          "en": "Calculate"},
    "sm.match_a":    {"de": "Match A",                            "en": "Match A"},
    "sm.match_b":    {"de": "Match B",                            "en": "Match B"},
    "sm.count":      {"de": "Anzahl",                             "en": "Count"},
    "sm.score":      {"de": "Jaccard",                            "en": "Jaccard"},
    "sm.common":     {"de": "Gemeinsame Nachnamen",               "en": "Common Surnames"},
    "sm.no_data":    {"de": "Keine Stammbaumdaten vorhanden.",    "en": "No pedigree data available."},
    "sm.computing":  {"de": "Berechne …",                        "en": "Computing …"},
    "sm.pairs":      {"de": "{n} Paare gefunden ({m} Matches)",   "en": "{n} pairs found ({m} matches)"},
}


def apply_style(parent, colors: dict) -> None:
    """Wendet ttk-Style mit den übergebenen Farben auf das Widget an."""
    C = colors
    s = ttk.Style(parent)
    s.theme_use("clam")
    s.configure("TNotebook",         background=C["bg"])
    s.configure("TNotebook.Tab",     padding=[14, 6],
                background=C["light"], foreground=C["text"],
                font=("Segoe UI", 10))
    s.map("TNotebook.Tab",
          background=[("selected", C["primary"])],
          foreground=[("selected", C["white"])])
    s.configure("TFrame",            background=C["bg"])
    s.configure("TLabel",            background=C["bg"],
                foreground=C["text"], font=("Segoe UI", 10))
    s.configure("Header.TLabel",     background=C["primary"],
                foreground=C["white"], font=("Segoe UI", 13, "bold"), padding=10)
    s.configure("Bold.TLabel",       background=C["bg"],
                font=("Segoe UI", 10, "bold"))
    s.configure("Success.TLabel",    background=C["bg"],
                foreground=C["success"], font=("Segoe UI", 10, "bold"))
    s.configure("Warning.TLabel",    background=C["bg"],
                foreground=C["warning"], font=("Segoe UI", 10, "bold"))
    s.configure("TButton",           font=("Segoe UI", 10), padding=6)
    s.configure("TProgressbar",      troughcolor=C["light"],
                background=C["accent"])
    s.configure("Treeview",          rowheight=24, font=("Segoe UI", 9))
    s.configure("Treeview.Heading",  font=("Segoe UI", 9, "bold"),
                background=C["primary"], foreground=C["white"])


def translate(key: str, lang: str) -> str:
    """Gibt die Übersetzung für *key* in *lang* zurück; Fallback: Deutsch, dann key."""
    entry = TRANSLATIONS.get(key, {})
    return entry.get(lang, entry.get("de", key))


def resolve_t(widget):
    """Findet die Übersetzungsfunktion eines Widgets.

    Läuft die master-Kette hoch, bis ein Objekt mit aufrufbarem ``_state.t``
    gefunden wird (Tab/Hauptfenster). Fällt sonst auf Deutsch zurück – so
    übersetzen auch klassenbasierte Dialoge ohne expliziten app-Parameter.
    """
    w = widget
    for _ in range(8):
        if w is None:
            break
        t = getattr(getattr(w, "_state", None), "t", None)
        if callable(t):
            return t
        w = getattr(w, "master", None)
    return lambda key: translate(key, "de")


def register_lang(state, widget, key):
    """Registriert *widget* für Live-Sprachwechsel und gibt es zurück
    (so kettet ein anschließendes .pack()/.grid()). _apply_lang ruft später
    widget.configure(text=translate(key, lang))."""
    try:
        state.lang_widgets.append((widget, key))
    except AttributeError:
        pass
    return widget
