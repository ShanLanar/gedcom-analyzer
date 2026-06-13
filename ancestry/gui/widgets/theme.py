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
    # New analysis windows
    "mn.surnames":  {"de": "Nachname-Analyse (Namenskarte) …",     "en": "Surname analysis (name map) …"},
    "mn.places":    {"de": "Geburtsort-Analyse …",                 "en": "Birth place analysis …"},
    "mn.mrca":      {"de": "MRCA-Wahrscheinlichkeit …",            "en": "MRCA probability …"},
    "mn.net_graph": {"de": "Cluster-Netzwerkgraph …",              "en": "Cluster network graph …"},
    # Dark mode
    "mn.darkmode":  {"de": "🌙 Dunkelmodus",                       "en": "🌙 Dark mode"},
    # New export/analysis menu items
    "mn.exp_ged":   {"de": "Vorfahren als GEDCOM exportieren …",   "en": "Export ancestors as GEDCOM …"},
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
