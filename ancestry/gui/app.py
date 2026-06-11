"""
Ancestry DNA Tool – Hauptfenster (Tkinter).

Tabs:
  1. Login         – Einloggen per Passwort oder Cookie-Datei
  2. Herunterladen – Matches + Shared Matches
  3. Matches       – Tabellenansicht; Shared-Match-Panel pro Match
  4. Cluster       – Leeds-Clustering-Ansicht
  5. Statistiken   – Kennzahlen
"""

import logging
import os
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Optional
from urllib.parse import quote

from ancestry.paths import DB_PATH
from ancestry.core.auth import AncestryAuth
from ancestry.core.api import AncestryApiClient
from ancestry.core.database import Database
from ancestry.core.scraper import Scraper, DownloadResult
from ancestry.core.export import export_csv, export_shared_csv, export_xlsx
from ancestry.core.cluster import build_clusters, suggest_grandparent_lines
from ancestry.models import DnaKit, DnaMatch, SharedMatch
from ancestry.gui._colors import COLORS, _COLORS_DARK as COLORS_DARK, _is_dark_theme
from ancestry.gui.tabs.login_tab import LoginTabMixin
from ancestry.gui.tabs.cluster_tab import ClusterTabMixin
from ancestry.gui.tabs.stats_tab import StatsTabMixin
from ancestry.gui.tabs.download_tab import DownloadTabMixin
from ancestry.gui.tabs.analysis_tab import AnalysisTabMixin
from ancestry.gui.tabs.matches_tab import MatchesTabMixin

log = logging.getLogger(__name__)

TRANSLATIONS: dict[str, dict[str, str]] = {
    # Tabs
    "tab_login":    {"de": "  🔑 Login  ",        "en": "  🔑 Login  "},
    "tab_download": {"de": "  ⬇ Herunterladen  ", "en": "  ⬇ Download  "},
    "tab_matches":  {"de": "  🧬 Matches  ",       "en": "  🧬 Matches  "},
    "tab_cluster":  {"de": "  🌳 Cluster  ",       "en": "  🌳 Cluster  "},
    "tab_stats":    {"de": "  📊 Statistiken  ",   "en": "  📊 Statistics  "},
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
    "mb.src":  {"de": "Quelle",    "en": "Source"},
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
    "lg.meth2":     {"de": "Methode 2: Cookie-Datei (empfohlen)",  "en": "Method 2: Cookie File (recommended)"},
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
    "mn.auto_sides":{"de": "Seiten automatisch zuweisen (Mutter-Kit)…",
                     "en": "Auto-assign sides (mother kit)…"},
    "mn.endo_score":{"de": "Endogamie-Score-Analyse …",            "en": "Endogamy score analysis …"},
    "mn.cl_timeline":{"de": "Cluster-Zeitachse …",                 "en": "Cluster timeline …"},
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
    "md.anc_none":  {"de": "Keine gemeinsamen Vorfahren von Ancestry heruntergeladen.",
                     "en": "No common ancestors downloaded from Ancestry."},
    "md.ged_none":  {"de": "Kein GEDCOM geladen – Analyse → Eigenen Baum abgleichen", "en": "No GEDCOM loaded – Analysis → Match own tree"},
    "md.ged_no_ped":{"de": "Keine Ahnentafel-Daten für diesen Match.", "en": "No pedigree data for this match."},
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
    # Matches tab — kit bar
    "mf.kit":           {"de": "Kit:",              "en": "Kit:"},
    "mf.sides":         {"de": "⚡ Seiten ableiten","en": "⚡ Assign sides"},
    # GEDCOM link panel buttons
    "md.ged_origin":    {"de": "🗺 Herkunft ableiten",        "en": "🗺 Infer origins"},
    "md.ged_endogamy":  {"de": "🧬 Endogamie übertragen",     "en": "🧬 Transfer endogamy"},
}



class AncestryDnaApp(
        LoginTabMixin, ClusterTabMixin, StatsTabMixin,
        DownloadTabMixin, AnalysisTabMixin, MatchesTabMixin,
        tk.Frame):

    # cM → relationship probability table (Shared cM Project 2020 + DNAPainter)
    _CM_RANGES = [
        (2600, 3900, "Elternteil / Kind",               1),
        (1700, 2600, "Halbgeschwister / Großelternteil", 2),
        (1200, 1700, "Halbgeschwister / Großelternteil", 2),
        ( 550, 1200, "Onkel/Tante · 1. Cousin",         2),
        ( 330,  550, "1. Cousin",                        3),
        ( 200,  330, "1. Cousin 1× entf. · 2. Cousin",  3),
        ( 100,  200, "2. Cousin",                        4),
        (  55,  100, "2. Cousin 1× entf. · 3. Cousin",  4),
        (  20,   55, "3. Cousin · 4. Cousin",            5),
        (   7,   20, "4. Cousin · 5. Cousin",            6),
        (   3,    7, "5. Cousin und weiter",              7),
    ]

    def __init__(self, master=None, gedcom_path: str = ""):
        # Dual-Modus: master=None -> eigenes Fenster (Standalone, abwärtskompatibel),
        # master=<Frame/Notebook-Tab> -> eingebettet in die vereinte App.
        self._embedded = master is not None
        if master is None:
            master = tk.Tk()
        super().__init__(master)
        _root = self.winfo_toplevel()
        if not self._embedded:
            _root.title("Ancestry DNA Tool")
            _root.geometry("1200x760")
            _root.minsize(960, 620)
        self.pack(fill="both", expand=True)

        self._auth    : Optional[AncestryAuth]      = None
        self._client  : Optional[AncestryApiClient] = None
        self._scraper : Optional[Scraper]           = None
        self._db      : Database                    = Database(str(DB_PATH))
        self._kit_map : dict[str, str]              = {}
        self._matches_kit_guid_map: dict[str, str]  = {}
        self._matches : list[DnaMatch]              = []
        self._selected_match : Optional[DnaMatch]   = None
        self._current_test_guid : Optional[str]     = None
        self._startup_gedcom_path: str              = gedcom_path

        self._lang: str = "de"
        self._lang_headings:       list = []   # (tv, col, key) tuples
        self._lang_nb_tabs:        list = []   # (frame, key) tuples
        self._lang_widgets:        list = []   # (widget_or_sv, key[, suffix]) tuples
        self._lang_menus:          list = []   # (menu, index, key) tuples
        self._theme_widgets:       list = []   # (widget, attr, color_key) tuples
        self._lang_inner_nb_tabs:  list = []   # (notebook, frame, key) tuples
        _saved_dark = self._load_ui_settings().get("dark_mode")
        self._dark_mode: bool = bool(_saved_dark) if _saved_dark is not None else _is_dark_theme()
        self.configure(bg=self._active_colors()["bg"])
        self._pause_event:         threading.Event = threading.Event()
        self._pause_event.set()  # not paused initially
        self._dl_counters = {"matches": 0, "trees": 0, "shared": 0, "errors": 0}
        self._dl_t0: float = 0.0
        self._dl_total: int = 1

        self._build_style()
        self._build_menu()
        self._build_main()
        self._refresh_match_table()

        if not self._embedded:
            self.winfo_toplevel().protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._load_settings)
        self.after(300, self._update_matches_kit_combo)
        self.after(400, self._load_lang_setting)

    def mainloop(self, *a, **k):
        """Standalone-Kompatibilität: leitet an das Toplevel weiter."""
        self.winfo_toplevel().mainloop(*a, **k)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _build_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        C = self._active_colors()
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

    # ── Theme / Dark mode ─────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._build_style()
        self._apply_theme()
        self._save_ui_settings(dark_mode=self._dark_mode)

    def _apply_theme(self):
        """Update all registered non-ttk widgets to the current theme palette."""
        C = self._active_colors()
        for widget, attr, key in self._theme_widgets:
            try:
                widget.configure(**{attr: C[key]})
            except Exception:
                pass
        # Canvases: redraw with new background
        if hasattr(self, "_ring_canvas"):
            self._ring_canvas.configure(bg=C["bg"])
            if hasattr(self, "_last_stats"):
                self._draw_stat_rings(self._last_stats)
        if hasattr(self, "_rel_prob_canvas"):
            self._rel_prob_canvas.configure(bg=C["bg"])
        # Chip buttons: reset to idle state colors
        if hasattr(self, "_chip_btns") and hasattr(self, "_chip_vars"):
            for key_btn, btn in self._chip_btns.items():
                if self._chip_vars.get(key_btn, None) and self._chip_vars[key_btn].get():
                    btn.configure(bg=C["primary"], fg=C["white"])
                else:
                    btn.configure(bg=C["light"], fg=C["text"])

    def _active_colors(self):
        return COLORS_DARK if self._dark_mode else COLORS

    # ── Menü ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self)
        self.winfo_toplevel().configure(menu=mb)

        fm = tk.Menu(mb, tearoff=False)
        fm.add_command(label=self._t("mn.exp_csv"),    command=self._export_csv)
        fm.add_command(label=self._t("mn.exp_xlsx"),   command=self._export_xlsx)
        fm.add_command(label=self._t("mn.exp_sh_csv"), command=self._export_shared_csv)
        fm.add_command(label=self._t("mn.exp_all"),    command=self._export_all_xlsx)
        fm.add_separator()
        fm.add_command(label=self._t("mn.imp_names"),  command=self._import_names)
        fm.add_separator()
        fm.add_command(label=self._t("mn.quit"),       command=self._on_close)
        mb.add_cascade(label=self._t("mn.file"), menu=fm)
        for idx, key in [(0,"mn.exp_csv"),(1,"mn.exp_xlsx"),(2,"mn.exp_sh_csv"),
                         (3,"mn.exp_all"),(5,"mn.imp_names"),(7,"mn.quit")]:
            self._lang_menus.append((fm, idx, key))
        self._lang_menus.append((mb, 0, "mn.file"))

        vm = tk.Menu(mb, tearoff=False)
        vm.add_command(label=self._t("mn.refresh_t"), command=self._refresh_match_table)
        vm.add_command(label=self._t("mn.recalc_cl"), command=self._refresh_cluster)
        vm.add_separator()
        vm.add_command(label=self._t("mn.language"),  command=self._toggle_lang)
        vm.add_command(label=self._t("mn.darkmode"),  command=self._toggle_theme)
        mb.add_cascade(label=self._t("mn.view"), menu=vm)
        for idx, key in [(0,"mn.refresh_t"),(1,"mn.recalc_cl"),(3,"mn.language"),
                         (4,"mn.darkmode")]:
            self._lang_menus.append((vm, idx, key))
        self._lang_menus.append((mb, 1, "mn.view"))

        am = tk.Menu(mb, tearoff=False)
        am.add_command(label=self._t("mn.anc_groups"),  command=self._show_ancestor_groups)
        am.add_command(label=self._t("mn.exp_anc"),     command=self._export_ancestor_groups)
        am.add_separator()
        am.add_command(label=self._t("mn.pedigree"),    command=self._show_match_pedigree)
        am.add_command(label=self._t("mn.ped_overlay"), command=self._show_pedigree_overlay)
        am.add_separator()
        am.add_command(label=self._t("mn.own_tree"),    command=self._match_own_tree)
        am.add_command(label=self._t("mn.sh_cluster"),  command=self._show_shared_clusters)
        am.add_separator()
        am.add_command(label=self._t("mn.reset_sh"),    command=self._reset_shared_matches)
        am.add_command(label=self._t("mn.reset_nm"),    command=self._reset_name_attempts)
        am.add_separator()
        am.add_command(label=self._t("mn.refresh_lk"),  command=self._refresh_links)
        am.add_command(label=self._t("mn.chg_ged"),     command=self._change_gedcom_settings)
        am.add_separator()
        am.add_command(label=self._t("mn.surnames"),    command=self._show_surname_analysis)
        am.add_command(label=self._t("mn.places"),      command=self._show_place_analysis)
        am.add_command(label=self._t("mn.mrca"),        command=self._show_mrca_analysis)
        am.add_command(label=self._t("mn.net_graph"),   command=self._show_network_graph)
        am.add_separator()
        am.add_command(label=self._t("mn.exp_ged"),     command=self._export_gedcom)
        am.add_command(label=self._t("mn.imp_mta"),     command=self._import_mta)
        am.add_separator()
        am.add_command(label=self._t("mn.ped_gaps"),    command=self._show_pedigree_gaps)
        am.add_command(label=self._t("mn.auto_sides"),  command=self._auto_assign_sides)
        am.add_command(label=self._t("mn.endo_score"),  command=self._show_endogamy_analysis)
        mb.add_cascade(label=self._t("mn.analysis"), menu=am)
        for idx, key in [(0,"mn.anc_groups"),(1,"mn.exp_anc"),(3,"mn.pedigree"),
                         (4,"mn.ped_overlay"),(6,"mn.own_tree"),(7,"mn.sh_cluster"),
                         (9,"mn.reset_sh"),(10,"mn.reset_nm"),(12,"mn.refresh_lk"),
                         (13,"mn.chg_ged"),(15,"mn.surnames"),(16,"mn.places"),
                         (17,"mn.mrca"),(18,"mn.net_graph"),
                         (20,"mn.exp_ged"),(21,"mn.imp_mta"),
                         (23,"mn.ped_gaps"),(24,"mn.auto_sides"),(25,"mn.endo_score")]:
            self._lang_menus.append((am, idx, key))
        self._lang_menus.append((mb, 2, "mn.analysis"))

        hm = tk.Menu(mb, tearoff=False)
        hm.add_command(label=self._t("mn.about"), command=self._show_about)
        mb.add_cascade(label=self._t("mn.help"), menu=hm)
        self._lang_menus.append((hm, 0, "mn.about"))
        self._lang_menus.append((mb, 3, "mn.help"))

    # ── Hauptlayout ───────────────────────────────────────────────────────────

    def _build_main(self):
        hf = tk.Frame(self, bg=self._active_colors()["primary"])
        self._theme_widgets.append((hf, "bg", "primary"))
        hf.pack(fill="x")
        ttk.Label(hf, text="🧬  Ancestry DNA Tool",
                  style="Header.TLabel").pack(side="left", fill="x", expand=True)
        _C = self._active_colors()
        self._lang_btn = tk.Button(
            hf, text="🌐 → EN", font=("Segoe UI", 10, "bold"),
            bg=_C["accent"], fg=_C["white"],
            activebackground=_C["primary"], activeforeground=_C["white"],
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=self._toggle_lang)
        self._lang_btn.pack(side="right", padx=10, pady=4)
        self._theme_widgets.append((self._lang_btn, "bg", "accent"))
        self._theme_widgets.append((self._lang_btn, "fg", "white"))
        self._theme_widgets.append((self._lang_btn, "activebackground", "primary"))
        self._theme_widgets.append((self._lang_btn, "activeforeground", "white"))

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=8, pady=8)

        tabs = [
            ("_tab_login",    "tab_login"),
            ("_tab_download", "tab_download"),
            ("_tab_matches",  "tab_matches"),
            ("_tab_cluster",  "tab_cluster"),
            ("_tab_stats",    "tab_stats"),
        ]
        for attr, key in tabs:
            frame = ttk.Frame(self._nb)
            setattr(self, attr, frame)
            self._nb.add(frame, text=self._t(key))
            self._lang_nb_tabs.append((frame, key))

        self._build_tab_login()
        self._build_tab_download()
        self._build_tab_matches()
        self._build_tab_cluster()
        self._build_tab_stats()

        self._status_var = tk.StringVar(value="Bereit.")
        ttk.Label(self, textvariable=self._status_var,
                  relief="sunken", anchor="w", padding=(6, 2)).pack(fill="x", side="bottom")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1: LOGIN  →  login_tab.LoginTabMixin
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2: HERUNTERLADEN
    # ─────────────────────────────────────────────────────────────────────────

    # ── Nachname-Analyse ──────────────────────────────────────────────────────

    def _change_gedcom_settings(self):
        """GEDCOM-Datei + Wurzelperson neu wählen (überschreibt die gemerkten)."""
        self._gedcom = None   # Cache verwerfen → Neuladen
        self._ensure_gedcom_loaded(
            lambda ged: self._set_status(
                f"GEDCOM/Wurzelperson gesetzt: {len(ged['people'])} Personen, "
                f"{len(ged['amap'])} Vorfahren auf deiner Linie."),
            force_ask=True)

    def _refresh_links(self):
        """Zieht 'View in tree' + gemeinsamer Vorfahr für ALLE Matches nach."""
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._names_stop_btn.configure(state="normal")
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: (
                                    self._names_stop_btn.configure(state="disabled"),
                                    self._refresh_match_table(),
                                    messagebox.showinfo("Verknüpfungen", r.message))))
        self._scraper.start_refresh_links(guid)

    def _reset_name_attempts(self):
        """Setzt die Fehlversuch-Zähler zurück, damit übersprungene Profile beim
        nächsten 'Namen laden' erneut versucht werden."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        n = self._db.reset_name_attempts(test_guid)
        self._set_status(f"Namens-Versuche zurückgesetzt: {n} Matches.")
        messagebox.showinfo("Zurückgesetzt",
            f"{n} Matches werden beim nächsten 'Namen & Stammbaum laden' "
            "erneut versucht.")

    def _reset_shared_matches(self):
        """Leert die Shared-Matches-Tabelle (alte, mit falschem Endpunkt geladene
        Daten) – danach Schritt B neu ausführen."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        if not messagebox.askyesno(
                "Shared Matches zurücksetzen",
                "Alle gespeicherten Shared Matches dieses Kits löschen?\n\n"
                "Nötig, um die fehlerhaften Alt-Daten (ganze Liste) zu entfernen.\n"
                "Danach Tab »Herunterladen« → Schritt B erneut ausführen."):
            return
        n = self._db.reset_shared_matches(test_guid)
        self._set_status(f"Shared Matches zurückgesetzt: {n} Zeilen gelöscht.")
        messagebox.showinfo("Zurückgesetzt",
            f"{n} Shared-Match-Zeilen gelöscht.\n"
            "Jetzt Schritt B (Shared Matches herunterladen) neu starten.")

    def _match_own_tree(self):
        """Gleicht alle geladenen Match-Ahnentafeln gegen den eigenen GEDCOM ab
        und zeigt, wo jeder Match in DEINEM Baum hängt."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        peds = self._db.get_all_pedigrees(test_guid)
        if not peds:
            messagebox.showinfo("Keine Ahnentafeln",
                "Noch keine Ahnentafeln geladen. Erst '▶ Ahnentafeln laden' ausführen.")
            return
        def _after_load(ged):
            import threading
            from core.treematch import Person, render_kinship, mrca_on_direct_line
            index, amap = ged["index"], ged["amap"]
            indi, fams = ged.get("individuals", {}), ged.get("families", {})

            # Cluster-Lookup einmalig vor dem Thread aufbauen (kein Threading-Problem)
            cluster_lookup: dict[str, int] = {}
            for cid, members in getattr(self, "_clusters", {}).items():
                for m in members:
                    cluster_lookup[m["guid"]] = cid

            def _worker():
                results = []
                items = list(peds.items())
                for i, (guid, info) in enumerate(items, 1):
                    cands = []  # (score, ped_row, own_person, self_path)
                    for r in info["rows"]:
                        q = Person(r["given_name"], r["surname"],
                                   r["birth_year"], r["birth_place"])
                        if not q.stoks:
                            continue
                        own, score = index.best_match(q, min_score=0.6)
                        if own:
                            cands.append((score, r, own, amap.get(own.ref)))
                    if cands:
                        # MRCA: Direktlinie bevorzugen, davon der jüngste; sonst Score.
                        direct = [c for c in cands if c[3] is not None]
                        if direct:
                            best = min(direct, key=lambda c: (len(c[3]), -c[0]))
                        else:
                            best = max(cands, key=lambda c: (c[0], -c[1]["generation"]))
                        if best[3] is not None:
                            kin = render_kinship(best[3])
                        else:
                            # Seitenverwandter → im Baum hochklettern zur direkten Linie
                            _mid, mpath = mrca_on_direct_line(
                                best[2].ref, indi, fams, amap)
                            kin = (render_kinship(mpath) + " (über Seitenlinie)"
                                   if mpath is not None else "")
                        results.append((info["name"], info["cm"], best, kin,
                                        info.get("linked", False), guid))
                    if i % 20 == 0 or i == len(items):
                        self.after(0, lambda i=i: self._set_status(
                            f"GEDCOM-Abgleich: {i}/{len(items)} Matches geprüft …"))
                results.sort(key=lambda x: (-(x[2][0]), -(x[1] or 0)))
                self.after(0, lambda: self._show_gedcom_results(
                    results, len(ged["people"]), len(peds), cluster_lookup))

            threading.Thread(target=_worker, daemon=True, name="gedcom-match").start()

        self._ensure_gedcom_loaded(_after_load)

    def _settings_path(self):
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(base, "data")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "ui_settings.json")

    def _load_ui_settings(self) -> dict:
        import json
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._ui_settings_cache = data
                    return dict(data)
        except Exception:
            pass
        return dict(getattr(self, "_ui_settings_cache", {}))

    def _save_ui_settings(self, **kw):
        import json
        s = dict(getattr(self, "_ui_settings_cache", {}))
        s.update(kw)
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
            self._ui_settings_cache = s
        except Exception as e:
            log.debug("Settings speichern fehlgeschlagen: %s", e)

    # ── Sprache / Localisation ────────────────────────────────────────────────

    def _t(self, key: str) -> str:
        entry = TRANSLATIONS.get(key, {})
        return entry.get(self._lang, entry.get("de", key))

    def _update_lang_btn(self):
        if hasattr(self, "_lang_btn"):
            self._lang_btn.configure(
                text="🌐 → EN" if self._lang == "de" else "🌐 → DE")

    def _toggle_lang(self):
        self._lang = "en" if self._lang == "de" else "de"
        self._apply_lang()
        self._save_ui_settings(lang=self._lang)

    def _apply_lang(self):
        self._update_lang_btn()
        for frame, key in self._lang_nb_tabs:
            try:
                self._nb.tab(frame, text=self._t(key))
            except Exception:
                pass
        for tv, col, key in self._lang_headings:
            try:
                tv.heading(col, text=self._t(key))
            except Exception:
                pass
        for item in self._lang_widgets:
            widget, key = item[0], item[1]
            suffix = item[2] if len(item) > 2 else ""
            try:
                text = self._t(key) + suffix
                if isinstance(widget, tk.StringVar):
                    widget.set(text)
                else:
                    widget.configure(text=text)
            except Exception:
                pass
        for menu, index, key in self._lang_menus:
            try:
                menu.entryconfigure(index, label=self._t(key))
            except Exception:
                pass
        for nb, frame, key in self._lang_inner_nb_tabs:
            try:
                nb.tab(frame, text=self._t(key))
            except Exception:
                pass

    def _load_lang_setting(self):
        lang = self._load_ui_settings().get("lang", "de")
        if lang in ("de", "en"):
            self._lang = lang
            self._apply_lang()

    def _ensure_gedcom_loaded(self, on_ready, force_ask=False):
        """Lädt den eigenen GEDCOM (mit Cache) + baut Index/Ahnen-Map, dann
        ruft on_ready(ged_dict) auf dem Main-Thread. GEDCOM-Pfad und Wurzelperson
        werden persistent gemerkt (data/ui_settings.json) – kein erneutes Fragen."""
        import os
        cached = getattr(self, "_gedcom", None)
        if cached and not force_ask:
            on_ready(cached)
            return

        st = self._load_ui_settings()
        path = st.get("gedcom_path") if not force_ask else None
        root_name = st.get("gedcom_root", "") or ""

        # GEDCOM-Pfad: gemerkten nutzen, wenn er noch existiert – sonst fragen.
        if not path or not os.path.exists(path):
            path = filedialog.askopenfilename(
                title="Eigenen Stammbaum wählen (GEDCOM)",
                filetypes=[("GEDCOM", "*.ged *.gedcom"), ("Alle", "*.*")])
            if not path:
                return

        # Wurzelperson: gemerkte nutzen; nur fragen, wenn keine bekannt (oder force).
        if force_ask or not root_name:
            import tkinter.simpledialog as sd
            root_name = (sd.askstring(
                "Deine Wurzelperson",
                "Wie heißt DU (bzw. die Wurzelperson) im Baum?\n"
                "Vorname Nachname – wird dauerhaft gemerkt (leer = ohne).",
                initialvalue=root_name) or "").strip()

        self._gedcom_root_name = root_name
        self._save_ui_settings(gedcom_path=path, gedcom_root=root_name)

        import threading
        self._set_status("GEDCOM wird geladen … (läuft im Hintergrund)")

        def _worker():
            try:
                from core.treematch import (load_gedcom_full, TreeIndex,
                                            build_ancestor_map, find_root_candidate)
                people, individuals, families = load_gedcom_full(path)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror(
                    "GEDCOM-Fehler", f"Konnte GEDCOM nicht laden:\n{e}"))
                return
            if not people:
                self.after(0, lambda: messagebox.showwarning(
                    "Leer", "Kein verwertbarer Inhalt im GEDCOM."))
                return
            index = TreeIndex(people)
            amap = {}
            if root_name:
                rid, rscore = find_root_candidate(people, root_name)
                if rid and rscore >= 0.6:
                    amap = build_ancestor_map(rid, individuals, families)
                    log.info("Wurzelperson erkannt (score %.2f), %d Vorfahren",
                             rscore, len(amap))
            ged = dict(path=path, people=people, index=index,
                       individuals=individuals, families=families, amap=amap)
            self._gedcom = ged
            self.after(0, lambda: self._set_status(
                f"Eigener Baum geladen & gecacht: {len(people)} Personen."))
            self.after(0, lambda: on_ready(ged))

        threading.Thread(target=_worker, daemon=True, name="gedcom-load").start()

    def _show_gedcom_results(self, results, n_people, n_peds, cluster_lookup=None):
        win = tk.Toplevel(self)
        win.title("GEDCOM-Abgleich – wo hängt jeder Match in deinem Baum?")
        win.geometry("1100x640")

        cl = cluster_lookup or {}
        cluster_ids = sorted({cid for cid in cl.values()}) if cl else []

        # Flache Datenzeilen (für Filter/Sortierung)
        data = []
        for name, cm, (score, r, own, _p), kin, linked, guid in results:
            ab = " ".join(x for x in (str(own.year or ""), own.place) if x).strip()
            cid = cl.get(guid)
            data.append({
                "linked": linked,
                "link": self._t("gc.linked") if linked else self._t("gc.new"),
                "match": name or "?", "cm": float(cm or 0),
                "anchor": own.display, "abirth": ab,
                "kin": kin or "—", "line": r["ahnen_path"] or "?",
                "score": float(score or 0),
                "cluster": cid,
                "cluster_str": f"#{cid}" if cid else "—",
            })
        n_new = sum(1 for d in data if not d["linked"])

        # ── Filterleiste ────────────────────────────────────────────────────────
        bar = ttk.Frame(win); bar.pack(fill="x", padx=10, pady=(10,2))
        ttk.Label(bar, text=self._t("gc.f.search")).pack(side="left")
        f_search = tk.StringVar()
        ttk.Entry(bar, textvariable=f_search, width=20).pack(side="left", padx=4)
        f_new = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=self._t("gc.f.new"),
                        variable=f_new).pack(side="left", padx=6)
        f_direct = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=self._t("gc.f.direct"),
                        variable=f_direct).pack(side="left", padx=6)
        ttk.Label(bar, text=self._t("gc.f.mincm")).pack(side="left")
        f_cm = tk.StringVar(value="0")
        ttk.Entry(bar, textvariable=f_cm, width=5).pack(side="left", padx=4)
        ttk.Label(bar, text=self._t("gc.f.cluster")).pack(side="left", padx=(10,0))
        f_cluster = tk.StringVar(value="")
        cluster_opts = [""] + [str(c) for c in cluster_ids]
        cb_cluster = ttk.Combobox(bar, textvariable=f_cluster,
                                  values=cluster_opts, width=5, state="readonly")
        cb_cluster.pack(side="left", padx=4)

        hdr = ttk.Label(win, text="", style="Bold.TLabel")
        hdr.pack(anchor="w", padx=10, pady=(0,2))

        # Cluster-Stammbaum-Button – vor frame packen (side=bottom), damit
        # frame mit expand=True den verbleibenden Mittelbereich füllt
        btn_bar = ttk.Frame(win)
        _cluster_btn = ttk.Button(btn_bar,
                                  text=self._t("gc.tree_btn"),
                                  state="disabled")
        _cluster_btn.pack(side="left", padx=4)
        btn_bar.pack(fill="x", padx=10, pady=(0, 4), side="bottom")
        _sel_cid: list = [None]

        cols = ("cluster","link","match","cm","anchor","abirth","kin","line","score")
        heads = {
            "cluster": ("gc.cluster", 58),
            "link":    ("gc.link",    72),
            "match":   ("gc.match",  165),
            "cm":      ("gc.cm",      52),
            "anchor":  ("gc.anchor", 185),
            "abirth":  ("gc.abirth", 115),
            "kin":     ("gc.kin",    165),
            "line":    ("gc.line",    72),
            "score":   ("gc.score",   65),
        }
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=(10,0), pady=6)
        tv = ttk.Treeview(frame, columns=cols, show="headings")
        for c, (key, w) in heads.items():
            tv.column(c, width=w,
                      anchor=("center" if c in ("cluster","cm","line","score","link") else "w"))
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y"); tv.configure(yscrollcommand=sb.set)

        clr = self._active_colors()["cluster"]
        tv.tag_configure("strong",  background=clr[1])
        tv.tag_configure("newlead", background=clr[3])

        for i in range(1, len(clr) + 1):
            tv.tag_configure(f"cl{i}", background=clr[(i - 1) % len(clr)])

        def _on_tv_select(_):
            sel = tv.selection()
            _sel_cid[0] = None
            if not sel:
                _cluster_btn.configure(state="disabled")
                return
            vals = tv.item(sel[0], "values")
            cstr = vals[0] if vals else ""
            if cstr and cstr != "—":
                try:
                    cid = int(cstr.lstrip("#"))
                    if cid in getattr(self, "_clusters", {}):
                        _sel_cid[0] = cid
                        _cluster_btn.configure(state="normal")
                        return
                except (ValueError, AttributeError):
                    pass
            _cluster_btn.configure(state="disabled")

        def _open_cluster_tree():
            cid = _sel_cid[0]
            clusters = getattr(self, "_clusters", {})
            if cid is None or cid not in clusters:
                messagebox.showinfo(
                    "Cluster nicht berechnet",
                    "Bitte zuerst im Cluster-Tab Clustering durchführen.")
                return
            members = clusters[cid]
            cluster_obj = {"members": [(m["guid"], m["name"], m["cm"])
                                       for m in members]}
            tg = self._current_test_guid or self._current_guid()
            if tg:
                self._build_cluster_tree(tg, cluster_obj)

        _cluster_btn.configure(command=_open_cluster_tree)
        tv.bind("<<TreeviewSelect>>", _on_tv_select)

        state = {"col": "cm", "desc": True}

        def populate(*_):
            q = f_search.get().strip().lower()
            try:
                mincm = float(f_cm.get() or 0)
            except ValueError:
                mincm = 0
            fc = f_cluster.get().strip()
            rows = [d for d in data
                    if d["cm"] >= mincm
                    and (not f_new.get() or not d["linked"])
                    and (not f_direct.get() or ("Seitenlinie" not in d["kin"]
                                                and d["kin"] != "—"))
                    and (not fc or str(d.get("cluster","")) == fc)
                    and (not q or q in d["match"].lower()
                         or q in d["anchor"].lower() or q in d["kin"].lower())]
            col, desc = state["col"], state["desc"]
            rows.sort(key=lambda d: (d[col] is None, d[col] or 0), reverse=desc)
            tv.delete(*tv.get_children())
            for d in rows:
                cid = d.get("cluster")
                if not d["linked"]:
                    tag = ("newlead",)
                elif d["score"] >= 0.8:
                    tag = ("strong",)
                elif cid:
                    tag = (f"cl{(cid - 1) % len(clr) + 1}",)
                else:
                    tag = ()
                tv.insert("", "end", tags=tag, values=(
                    d["cluster_str"], d["link"], d["match"],
                    f"{d['cm']:.0f}", d["anchor"], d["abirth"],
                    d["kin"], d["line"], f"{d['score']:.2f}"))
            hdr.configure(text=(f"Eigener Baum: {n_people} Pers. · "
                f"{len(data)} verankert ({n_new} neu) · angezeigt: {len(rows)} · "
                f"Sort: {self._t(heads[col][0])} {'▼' if desc else '▲'}"))

        def sort_by(col):
            state["desc"] = not state["desc"] if state["col"] == col else True
            state["col"] = col
            populate()

        for c, (key, w) in heads.items():
            tv.heading(c, text=self._t(key), command=lambda c=c: sort_by(c))

        for var in (f_search, f_new, f_direct, f_cm, f_cluster):
            var.trace_add("write", populate)
        populate()
        self._set_status(f"GEDCOM-Abgleich: {len(data)}/{n_peds} Matches verankert.")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3: MATCHES
    # ─────────────────────────────────────────────────────────────────────────

    # TAB 4: CLUSTER  →  cluster_tab.ClusterTabMixin
    # ─────────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    # TAB 5: STATISTIKEN  →  stats_tab.StatsTabMixin
    # ─────────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    # Export
    # ─────────────────────────────────────────────────────────────────────────

    def _export_csv(self):
        matches = self._db.get_matches()
        if not matches:
            messagebox.showinfo("Keine Daten", "Keine Matches vorhanden.")
            return
        p = filedialog.asksaveasfilename(title="Matches als CSV",
            defaultextension=".csv", filetypes=[("CSV","*.csv"),("Alle","*.*")],
            initialfile="ancestry_dna_matches.csv")
        if p:
            export_csv(matches, p)
            messagebox.showinfo("Fertig", f"{len(matches)} Matches → {p}")

    def _export_shared_csv(self):
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return
        with self._db._cursor() as cur:
            cur.execute("SELECT * FROM shared_matches WHERE test_guid=? ORDER BY shared_cm_b DESC",
                        (test_guid,))
            rows = cur.fetchall()
        if not rows:
            messagebox.showinfo("Keine Daten", "Keine Shared Matches in der Datenbank.")
            return
        from models import SharedMatch
        shared = [SharedMatch.from_db_row(dict(r)) for r in rows]
        matches = {m.match_guid: m.display_name for m in self._db.get_matches(test_guid=test_guid)}

        p = filedialog.asksaveasfilename(title="Shared Matches als CSV",
            defaultextension=".csv", filetypes=[("CSV","*.csv"),("Alle","*.*")],
            initialfile="ancestry_shared_matches.csv")
        if p:
            export_shared_csv(shared, p, matches)
            messagebox.showinfo("Fertig", f"{len(shared)} Shared Matches → {p}")

    def _export_xlsx(self):
        matches = self._db.get_matches()
        if not matches:
            messagebox.showinfo("Keine Daten", "Keine Matches vorhanden.")
            return
        p = filedialog.asksaveasfilename(title="Matches als XLSX",
            defaultextension=".xlsx", filetypes=[("XLSX","*.xlsx"),("Alle","*.*")],
            initialfile="ancestry_dna_matches.xlsx")
        if p:
            export_xlsx(matches, p)
            messagebox.showinfo("Fertig", f"{len(matches)} Matches → {p}")

    def _export_all_xlsx(self):
        test_guid = self._current_test_guid or self._get_kit_guid()
        matches = self._db.get_matches(test_guid=test_guid)
        if not matches:
            messagebox.showinfo("Keine Daten", "Keine Matches vorhanden.")
            return
        shared, name_map = [], {}
        if test_guid:
            with self._db._cursor() as cur:
                cur.execute("SELECT * FROM shared_matches WHERE test_guid=? ORDER BY shared_cm_b DESC",
                            (test_guid,))
                from models import SharedMatch
                shared = [SharedMatch.from_db_row(dict(r)) for r in cur.fetchall()]
            name_map = {m.match_guid: m.display_name for m in matches}

        # Statistik-Kennzahlen
        try:
            stats = self._db.get_statistics(test_guid)
        except Exception:
            stats = None

        # Analyse-Blatt: Herkunft (Regel + ML) und Seite je Match
        import json as _json
        analysis = []
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    "SELECT display_name, shared_cm, paternal_maternal, "
                    "probable_origin, ml_origin FROM matches WHERE test_guid=? "
                    "ORDER BY shared_cm DESC", (test_guid,)).fetchall()
            def _reg(j):
                try:
                    d = _json.loads(j) if j else {}
                    r = d.get("region", "")
                    pr = d.get("score", d.get("prob"))
                    return f"{r} ({pr})" if r and pr is not None else r
                except Exception:
                    return ""
            for r in rows:
                analysis.append({
                    "name":   r["display_name"],
                    "cm":     r["shared_cm"],
                    "side":   {"paternal":"väterlich","maternal":"mütterlich",
                               "both":"beidseitig"}.get(r["paternal_maternal"] or "", ""),
                    "origin_rule": _reg(r["probable_origin"]),
                    "origin_ml":   _reg(r["ml_origin"]),
                })
        except Exception:
            analysis = []

        p = filedialog.asksaveasfilename(title="Alles als XLSX exportieren",
            defaultextension=".xlsx", filetypes=[("XLSX","*.xlsx"),("Alle","*.*")],
            initialfile="ancestry_dna_komplett.xlsx")
        if p:
            export_xlsx(matches, p, shared if shared else None, name_map,
                        stats=stats, analysis=analysis)
            messagebox.showinfo("Fertig",
                                f"{len(matches)} Matches + {len(shared)} Shared Matches\n"
                                f"+ Statistik + Herkunft/Seiten → {p}")

    # ─────────────────────────────────────────────────────────────────────────
    # Hilfsmethoden
    # ─────────────────────────────────────────────────────────────────────────

    def _import_names(self):
        """
        Importiert Namen aus JSON (Browser-DOM-Export).
        Filtert Rausch-Eintraege wie "This match is connected..." heraus.
        Dedupliziert pro sampleId: bester Name gewinnt.
        """
        path = filedialog.askopenfilename(
            title="Namen-Datei importieren",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv"), ("Alle", "*.*")],
        )
        if not path:
            return

        import json
        import csv
        import re

        # Muster die KEIN echter Name sind
        NOISE_PATTERNS = [
            "this match is connected",
            "public linked tree",
            "unlinked tree",
            "private tree",
            "no tree",
        ]

        def is_noise(name: str) -> bool:
            n = name.lower().strip()
            return any(n.startswith(p) for p in NOISE_PATTERNS)

        def name_quality(name: str) -> int:
            """Hoehere Zahl = besserer Name. Echter Name > Benutzername > Initialen."""
            if is_noise(name):
                return -1
            # Initialen wie "J. M." = niedrige Qualitaet
            if re.match(r'^[A-Z]\.\s+[A-Z]\.$', name.strip()):
                return 1
            # Echter Name (Vor- + Nachname) = hohe Qualitaet
            if ' ' in name and not name.startswith('@'):
                return 3
            return 2  # Benutzername

        # Einlesen
        raw: list[tuple[str, str]] = []
        try:
            if path.lower().endswith(".json"):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # Listen-Format: [{"sampleId": "...", "name": "..."}, ...]
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        sid  = (item.get("sampleId") or item.get("sample_id")
                                or item.get("guid", "")).strip()
                        name = (item.get("name") or item.get("displayName")
                                or item.get("matchName") or item.get("managedName")
                                or "").strip()
                        if sid and name:
                            raw.append((sid, name))
                elif isinstance(data, dict):
                    # Dict-Format (profileData-Antwort):
                    #   {"<sid>": {"matchName": "...", "managedName": "..."}, ...}
                    #   oder {"<sid>": "Name", ...}
                    for sid, info in data.items():
                        sid = (sid or "").strip()
                        if isinstance(info, dict):
                            name = (info.get("matchName") or info.get("managedName")
                                    or info.get("name") or info.get("displayName")
                                    or "").strip()
                        else:
                            name = str(info or "").strip()
                        if sid and name:
                            raw.append((sid, name))
            else:
                with open(path, encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        sid  = (row.get("sampleId") or row.get("match_guid", "")).strip()
                        name = (row.get("name") or row.get("display_name", "")).strip()
                        if sid and name:
                            raw.append((sid, name))
        except Exception as e:
            messagebox.showerror("Import-Fehler", str(e))
            return

        # Deduplizieren: bester Name pro sampleId
        best: dict[str, tuple[str, int]] = {}
        for sid, name in raw:
            q = name_quality(name)
            if q < 0:
                continue
            if sid not in best or q > best[sid][1]:
                best[sid] = (name, q)

        if not best:
            messagebox.showinfo("Kein Ergebnis",
                                "Keine gueltigen Namen gefunden.")
            return

        # In DB schreiben. Ueberschrieben werden nur Platzhalter:
        # leer/Anonym/NULL, Gender-Suffixe und das 8-stellige GUID-Kuerzel
        # (z.B. "BEC4AE66"), das matchList ohne echten Namen speichert.
        # Manuell eingetragene echte Namen bleiben unangetastet.
        HEX8 = "[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]" \
               "[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]"
        updated = skipped = 0
        with self._db._cursor() as cur:
            for sid, (name, _) in best.items():
                cur.execute(
                    "UPDATE matches SET display_name=? "
                    "WHERE match_guid=? "
                    "AND (display_name='' OR display_name='Anonym' "
                    "     OR display_name IS NULL "
                    "     OR display_name LIKE '% (m.)' "
                    "     OR display_name LIKE '% (w.)' "
                    f"     OR display_name GLOB '{HEX8}')",
                    (name, sid)
                )
                if cur.rowcount:
                    updated += 1
                else:
                    skipped += 1

        self._refresh_match_table()
        msg = (str(len(raw)) + " Roheintraege, "
               + str(len(best)) + " eindeutige Matches, "
               + str(updated) + " aktualisiert"
               + (" (" + str(skipped) + " uebersprungen)" if skipped else ""))
        messagebox.showinfo("Import abgeschlossen", msg)
        self._set_status("Namen: " + str(updated) + " importiert")

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    # ── Neue Analyse-Methoden ─────────────────────────────────────────────────

    def _show_pedigree_gaps(self):
        """Zeigt welche Generationen in Match-Ahnentafeln noch fehlen."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Ahnentafel-Lücken-Analyse")
        win.geometry("900x600")

        ttk.Label(win, text="Matches mit unvollständigen Ahnentafeln (nach Generation):",
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

        cols = ("name","cm","gen2","gen3","gen4","gen5","gen6")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for col, (lbl, w) in {
            "name": ("Match",     200),
            "cm":   ("cM",         65),
            "gen2": ("Gen 2",      60),
            "gen3": ("Gen 3",      60),
            "gen4": ("Gen 4",      60),
            "gen5": ("Gen 5",      60),
            "gen6": ("Gen 6+",     60),
        }.items():
            tv.heading(col, text=lbl)
            tv.column(col, width=w, anchor=("e" if col=="cm" else "center" if col!="name" else "w"))

        tv.tag_configure("gap3", background="#FFF3CD")
        tv.tag_configure("gap2", background="#FFD6D6")

        sy = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sy.set)
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=4)
        sy.pack(side="right", fill="y", pady=4)

        try:
            data = self._db.get_pedigree_completeness_per_match(test_guid)
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            return

        max_gen = {2: 4, 3: 8, 4: 16, 5: 32, 6: 64}
        for entry in data[:200]:
            gens = entry.get("generations", {})
            def fmt(g):
                got = gens.get(g, 0)
                exp = max_gen.get(g, 0)
                return f"{got}/{exp}" if exp else f"{got}"
            g3 = gens.get(3, 0); g4 = gens.get(4, 0)
            tags = ("gap2",) if g3 < 4 else (("gap3",) if g4 < 8 else ())
            tv.insert("", "end", tags=tags, values=(
                entry.get("display_name","?")[:30],
                f"{entry.get('shared_cm',0):.0f}",
                fmt(2), fmt(3), fmt(4), fmt(5), fmt(6),
            ))
        if not data:
            tv.insert("", "end", values=("—",) * 7)

    def _show_endogamy_analysis(self):
        """Listet Matches mit erhöhtem Endogamie-Score."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Endogamie-Score-Analyse")
        win.geometry("800x500")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="Min. Score:", style="Bold.TLabel").pack(side="left")
        thr_var = tk.StringVar(value="0.15")
        ttk.Entry(top, textvariable=thr_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="  (Score = Segmente / (cM+1)  –  Verdacht > 0.15)",
                  foreground="#777777").pack(side="left")

        info_lbl = ttk.Label(win, text="", style="Bold.TLabel")
        info_lbl.pack(anchor="w", padx=10)

        cols = ("name","cm","seg","score")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for col, (lbl, w, a) in {
            "name":  ("Match",  280, "w"),
            "cm":    ("cM",      80, "e"),
            "seg":   ("Seg.",    60, "e"),
            "score": ("Score",   80, "e"),
        }.items():
            tv.heading(col, text=lbl); tv.column(col, width=w, anchor=a)
        sy = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sy.set)
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=4)
        sy.pack(side="right", fill="y", pady=4)

        def reload(*_):
            try:
                thr = float(thr_var.get() or 0.15)
            except ValueError:
                thr = 0.15
            tv.delete(*tv.get_children())
            try:
                rows = self._db.get_endogamy_candidates(test_guid, thr)
            except Exception as e:
                messagebox.showerror("Fehler", str(e)); return
            for r in rows:
                tv.insert("", "end", values=(
                    r.get("display_name","?")[:40],
                    f"{r.get('shared_cm',0):.0f}",
                    r.get("shared_segments","?"),
                    f"{r.get('endo_score',0):.3f}",
                ))
            info_lbl.configure(text=f"{len(rows)} Matches mit Endogamie-Verdacht (Score > {thr:.2f})")

        thr_var.trace_add("write", reload)
        reload()

    def _run_gedmatch_bridge(self):
        """Verknüpft GEDmatch-Matches mit Ancestry/MH-Matches (Name+cM-Ähnlichkeit)."""
        import threading
        def _do():
            try:
                n = self._db.link_gedmatch_bridges()
                msg = (f"{n} GEDmatch-Match/es mit Ancestry/MH-Matches verknüpft.\n"
                       "⚡-Badge erscheint in der Match-Liste wenn Brücke bekannt.")
                self.after(0, lambda m=msg: messagebox.showinfo("GEDmatch-Brücke", m))
                self.after(50, self._refresh_match_table)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror("Fehler", str(e)))
        threading.Thread(target=_do, daemon=True).start()

    def _auto_assign_sides(self):
        """Weist Seiten (väterlich/mütterlich) zu — via Mutter-Kit oder GEDCOM-Baum."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit wählen.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Seiten automatisch zuweisen")
        dlg.resizable(False, False)
        dlg.grab_set()
        ttk.Label(dlg, text="Methode:", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12,4))

        method_var = tk.StringVar(value="kit")

        # ── Methode A: via Mutter-Kit ─────────────────────────────────────────
        kits = self._db.get_kits()
        other_kits = [k for k in kits if k.guid != test_guid]
        rb_kit = ttk.Radiobutton(dlg, text="Via zweites Ancestry-Kit (Mutter/Vater):",
                                 variable=method_var, value="kit")
        rb_kit.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(4,2))
        kit_names = [f"{k.name or k.guid[:16]}…" for k in other_kits]
        kit_combo = ttk.Combobox(dlg, values=kit_names, state="readonly", width=34)
        if kit_names:
            kit_combo.current(0)
        else:
            kit_combo.set("(kein zweites Kit vorhanden)")
            kit_combo.configure(state="disabled")
        kit_combo.grid(row=2, column=0, columnspan=2, padx=28, pady=(0,8), sticky="w")
        kit_combo.bind("<Button-1>", lambda _: method_var.set("kit"))

        # ── Methode B: via GEDCOM-Baum ────────────────────────────────────────
        has_gedcom = bool(getattr(self, "_gedcom", None))
        amap = (self._gedcom.get("amap") or {}) if has_gedcom else {}
        has_amap = bool(amap)
        ged_state = "normal" if (has_gedcom and has_amap) else "disabled"
        rb_ged = ttk.Radiobutton(dlg, text="Via GEDCOM-Baum (Ahnen-Map):",
                                 variable=method_var, value="ged", state=ged_state)
        rb_ged.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(4,2))
        # Show which person is at path 'M' (= the mother) from the amap
        if has_amap:
            mother_gid = next((gid for gid, p in amap.items() if p == "M"), None)
            if mother_gid:
                inds = self._gedcom.get("individuals", {})
                mo_ind = inds.get(mother_gid, {})
                mo_name = (mo_ind.get("NAME") or mother_gid).replace("/","").strip()
                ged_hint = f"Mutter im Baum: {mo_name}"
            else:
                ged_hint = "Keine Mutter im Ahnen-Map gefunden (Wurzelperson prüfen)"
        else:
            ged_hint = "GEDCOM laden + Wurzelperson setzen, um Ahnen-Map zu erstellen"
        ttk.Label(dlg, text=ged_hint, foreground="#555555",
                  font=("Segoe UI", 8)).grid(
            row=4, column=0, columnspan=2, padx=28, pady=(0,12), sticky="w")

        # ── Methode C: Ancestry-Schätzung (Tag 8 / matchClusterCode) ─────────────
        # Vorhandene Daten: tags_json Tag "8" = "M"/"P" und match_cluster_code
        try:
            with self._db._cursor() as _cur:
                _cur.execute(
                    "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                    "AND (tags_json LIKE '%\"8\": \"M\"%' OR tags_json LIKE '%\"8\":\"M\"%' "
                    "OR tags_json LIKE '%\"8\": \"P\"%' OR tags_json LIKE '%\"8\":\"P\"%' "
                    "OR match_cluster_code IN ('maternal','paternal'))",
                    (test_guid,))
                n_ancestry = _cur.fetchone()[0]
        except Exception:
            n_ancestry = 0

        rb_anc = ttk.Radiobutton(dlg,
            text="Ancestry-Schätzung importieren (Tag 8 / Cluster-Code):",
            variable=method_var, value="ancestry")
        rb_anc.grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(4,2))
        ttk.Label(dlg, text=f"{n_ancestry} Matches mit Ancestry-Seitenzuweisung gefunden",
                  foreground="#555555", font=("Segoe UI", 8)).grid(
            row=6, column=0, columnspan=2, padx=28, pady=(0,12), sticky="w")
        if n_ancestry == 0:
            rb_anc.configure(state="disabled")

        # ── Buttons ────────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(dlg); btn_frame.grid(row=7, column=0, columnspan=2,
                                                    padx=14, pady=(4,12))
        result = {"ok": False}

        def _ok():
            result["ok"] = True
            # Auswahl JETZT auslesen – nach dlg.destroy() sind die Widgets weg
            result["method"] = method_var.get()
            try:
                result["kit_index"] = kit_combo.current()
            except Exception:
                result["kit_index"] = -1
            dlg.destroy()

        ttk.Button(btn_frame, text="Abbrechen", command=dlg.destroy).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✓ Zuweisen", command=_ok).pack(side="left", padx=4)
        self.wait_window(dlg)
        if not result["ok"]:
            return

        method = result.get("method", "")
        kit_index = result.get("kit_index", -1)
        if method == "kit":
            # Via Mutter-Kit
            if not other_kits or kit_index < 0:
                messagebox.showinfo("Kein Kit", "Kein zweites Kit verfügbar.")
                return
            parent_kit = other_kits[kit_index]
            overlap = self._db.get_paternal_maternal_overlap(test_guid, parent_kit.guid)
            mat = overlap["shared"]
            pat = overlap["only_a"]
            n_mat = self._db.bulk_set_side(list(mat), "maternal")
            n_pat = self._db.bulk_set_side(list(pat), "paternal")
            self._refresh_match_table()
            messagebox.showinfo("Ergebnis",
                                f"✅ {n_mat} Matches als mütterlich markiert\n"
                                f"✅ {n_pat} Matches als väterlich markiert\n\n"
                                f"Mutter-Kit: {parent_kit.name or parent_kit.guid[:16]}")
        elif method == "ged":
            # Via GEDCOM-Baum
            if not has_amap:
                messagebox.showwarning("Kein Ahnen-Map",
                                       "Bitte GEDCOM laden und Wurzelperson angeben.")
                return
            try:
                from core.bridge import infer_side_from_links
            except ImportError:
                messagebox.showerror("Fehler", "bridge.py nicht ladbar.")
                return

            with self._db._cursor() as cur:
                match_guids = [r[0] for r in cur.execute(
                    "SELECT DISTINCT match_guid FROM gedcom_links WHERE test_guid=?",
                    (test_guid,)
                ).fetchall()]

            pat_guids, mat_guids, both_guids = [], [], []
            for mguid in match_guids:
                side = infer_side_from_links(self._db, test_guid, mguid, amap)
                if side == "paternal":
                    pat_guids.append(mguid)
                elif side == "maternal":
                    mat_guids.append(mguid)
                elif side == "both":
                    both_guids.append(mguid)

            n_pat = self._db.bulk_set_side(pat_guids, "paternal")
            n_mat = self._db.bulk_set_side(mat_guids, "maternal")
            self._refresh_match_table()
            messagebox.showinfo("GEDCOM-Seitenableitung",
                                f"✅ {n_pat} Matches als väterlich markiert\n"
                                f"✅ {n_mat} Matches als mütterlich markiert\n"
                                f"   {len(both_guids)} Matches beidseitig (unverändert)\n\n"
                                f"Basis: {len(amap)} Vorfahren im Ahnen-Map")

        elif method == "ancestry":
            # Via Ancestry-Schätzung (Tag 8 / matchClusterCode)
            try:
                with self._db._cursor() as cur:
                    mat_guids = [r[0] for r in cur.execute(
                        "SELECT match_guid FROM matches WHERE test_guid=? "
                        "AND (tags_json LIKE '%\"8\": \"M\"%' OR tags_json LIKE '%\"8\":\"M\"%' "
                        "OR match_cluster_code = 'maternal')",
                        (test_guid,)).fetchall()]
                    pat_guids = [r[0] for r in cur.execute(
                        "SELECT match_guid FROM matches WHERE test_guid=? "
                        "AND (tags_json LIKE '%\"8\": \"P\"%' OR tags_json LIKE '%\"8\":\"P\"%' "
                        "OR tags_json LIKE '%\"8\": \"F\"%' OR tags_json LIKE '%\"8\":\"F\"%' "
                        "OR match_cluster_code = 'paternal')",
                        (test_guid,)).fetchall()]
            except Exception as e:
                messagebox.showerror("Fehler", str(e))
                return
            n_mat = self._db.bulk_set_side(mat_guids, "maternal")
            n_pat = self._db.bulk_set_side(pat_guids, "paternal")
            self._refresh_match_table()
            messagebox.showinfo("Ancestry-Schätzung",
                                f"✅ {n_mat} Matches als mütterlich markiert\n"
                                f"✅ {n_pat} Matches als väterlich markiert\n\n"
                                f"Quelle: Ancestry Tag 8 / Cluster-Code")

    def _assign_cluster_side(self):
        """Weist allen Mitgliedern des gewählten Clusters eine Seite zu."""
        sel = self._cluster_list.selection()
        if not sel:
            messagebox.showinfo("Kein Cluster", "Bitte Cluster auswählen.")
            return
        cid = int(sel[0])
        members = self._clusters.get(cid, [])
        if not members:
            return
        test_guid = self._current_guid()
        if not test_guid:
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Cluster #{cid} – Seite zuweisen")
        dlg.resizable(False, False)
        dlg.grab_set()
        ttk.Label(dlg, text=f"Seite für alle {len(members)} Mitglieder von Cluster #{cid}:",
                  font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(14, 8), sticky="w")

        side_var = tk.StringVar(value="paternal")
        ttk.Radiobutton(dlg, text="🔵 Väterlich (paternal)",
                        variable=side_var, value="paternal").grid(
            row=1, column=0, columnspan=2, padx=24, pady=2, sticky="w")
        ttk.Radiobutton(dlg, text="🔴 Mütterlich (maternal)",
                        variable=side_var, value="maternal").grid(
            row=2, column=0, columnspan=2, padx=24, pady=2, sticky="w")
        ttk.Radiobutton(dlg, text="✖ Zuweisung entfernen",
                        variable=side_var, value="").grid(
            row=3, column=0, columnspan=2, padx=24, pady=(2, 10), sticky="w")

        result = {"ok": False}
        def _ok():
            result["ok"] = True
            dlg.destroy()

        bf = ttk.Frame(dlg); bf.grid(row=4, column=0, columnspan=2, padx=14, pady=(0, 12))
        ttk.Button(bf, text="OK", command=_ok, width=10).pack(side="left", padx=4)
        ttk.Button(bf, text="Abbrechen", command=dlg.destroy, width=10).pack(side="left", padx=4)
        dlg.wait_window()

        if not result["ok"]:
            return

        guids = [m["guid"] for m in members]
        side = side_var.get()
        n = self._db.bulk_set_side(guids, side)
        self._refresh_match_table()

        if side:
            side_label = "väterlich" if side == "paternal" else "mütterlich"
            messagebox.showinfo("Seite zugewiesen",
                                f"✅ {n} Matches als {side_label} markiert\n"
                                f"Cluster #{cid} ({len(members)} Mitglieder)")
        else:
            messagebox.showinfo("Zuweisung entfernt",
                                f"✅ Seitenzuweisung für {n} Matches entfernt\n"
                                f"Cluster #{cid} ({len(members)} Mitglieder)")

    def _show_cluster_timeline(self):
        """Zeigt Geburtsjahre der Cluster-Vorfahren als Zeitachse."""
        sel = self._cluster_list.selection()
        if not sel:
            messagebox.showinfo("Kein Cluster", "Bitte Cluster auswählen.")
            return
        cid = int(sel[0])
        members = self._clusters.get(cid, [])
        if not members:
            return
        test_guid = self._current_guid()
        if not test_guid:
            return

        try:
            guids = [m["guid"] for m in members]
            rows = self._db.get_cluster_ancestor_years(test_guid, guids)
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            return

        if not rows:
            messagebox.showinfo("Keine Daten",
                                "Keine Ahnentafel-Daten für diesen Cluster vorhanden.\n"
                                "→ Erst 'Ahnentafeln laden' ausführen.")
            return

        win = tk.Toplevel(self)
        _cc = self._active_colors()["cluster"]
        color = getattr(self, "_cluster_side_colors", {}).get(cid, _cc[(cid - 1) % len(_cc)])
        win.title(f"Cluster #{cid} – Zeitachse der Vorfahren")
        win.geometry("900x400")

        years = [int(r.get("birth_year", 0)) for r in rows if r.get("birth_year")]
        if not years:
            return
        y_min, y_max = min(years), max(years)
        y_range = max(y_max - y_min, 50)

        c = tk.Canvas(win, bg="#FAFAFA", highlightthickness=0)
        c.pack(fill="both", expand=True, padx=10, pady=10)

        def draw(_event=None):
            c.delete("all")
            W = c.winfo_width() or 860
            H = c.winfo_height() or 340
            pad_x = 60; pad_y = 40

            # Draw axis
            c.create_line(pad_x, H - pad_y, W - 20, H - pad_y, fill="#AAAAAA", width=1)
            # Draw decade ticks
            decade_start = (y_min // 10) * 10
            decade_end   = ((y_max // 10) + 1) * 10
            for yr in range(decade_start, decade_end + 1, 10):
                x = pad_x + (yr - y_min) / y_range * (W - pad_x - 20)
                c.create_line(x, H - pad_y - 4, x, H - pad_y + 4, fill="#888888")
                c.create_text(x, H - pad_y + 16, text=str(yr),
                              font=("Segoe UI", 7), fill="#888888")

            # Draw people as colored dots
            import random
            random.seed(cid)
            for r in rows:
                yr = int(r.get("birth_year", 0))
                if not yr: continue
                x = pad_x + (yr - y_min) / y_range * (W - pad_x - 20)
                gen = r.get("generation", 3)
                y = pad_y + (gen - 1) * 18
                y = min(y, H - pad_y - 20)
                tag = f"d{id(r)}"
                c.create_oval(x-5, y-5, x+5, y+5, fill=color, outline="white",
                              width=1, tags=tag)
                name = f"{r.get('given_name','')} {r.get('surname','')}"
                c.tag_bind(tag, "<Enter>",
                           lambda e, n=name, yr=yr, gen=gen:
                               c.create_text(e.x+10, e.y-10, text=f"{n} ({yr}) Gen{gen}",
                                             font=("Segoe UI", 8), tags="tooltip",
                                             fill=self._active_colors()["text"]))
                c.tag_bind(tag, "<Leave>", lambda _: c.delete("tooltip"))

        c.bind("<Configure>", draw)
        win.after(100, draw)

    def _export_gedcom(self):
        """Exportiert Vorfahren-Gruppen als GEDCOM 5.5.1."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit wählen.")
            return
        try:
            groups = self._db.get_pedigree_groups(test_guid, min_matches=2, mode="person")
        except Exception as e:
            messagebox.showerror("Datenbankfehler", str(e))
            return
        if not groups:
            messagebox.showinfo("Keine Daten",
                                "Keine Vorfahren-Gruppen vorhanden.\n"
                                "→ Erst 'Ahnentafeln laden' ausführen.")
            return
        p = filedialog.asksaveasfilename(
            title="GEDCOM exportieren",
            defaultextension=".ged",
            filetypes=[("GEDCOM", "*.ged"), ("Alle", "*.*")],
            initialfile="ancestry_dna_ancestors.ged")
        if not p:
            return
        try:
            from core.gedcom_export import export_gedcom
            # Enrich groups with ancestor data
            enriched = []
            for g in groups:
                ancestors = []
                for guid, name, path, gen, cm in g.get("matches", []):
                    rows = self._db.get_pedigree_for_match(test_guid, guid)
                    for r in rows:
                        ancestors.append(r)
                enriched.append({**g, "ancestors": ancestors})
            n = export_gedcom(enriched, p)
            messagebox.showinfo("Fertig", f"{n} Personen als GEDCOM exportiert → {p}")
        except ImportError:
            messagebox.showerror("Fehler", "gedcom_export-Modul nicht gefunden.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def _import_mta(self):
        """Importiert MyTrueAncestry CSV-Export."""
        p = filedialog.askopenfilename(
            title="MyTrueAncestry CSV importieren",
            filetypes=[("CSV", "*.csv"), ("Alle", "*.*")])
        if not p:
            return
        try:
            from core.mta_import import parse_mta_csv
            rows = parse_mta_csv(p)
        except Exception as e:
            messagebox.showerror("Import-Fehler", str(e))
            return
        if not rows:
            messagebox.showwarning("Keine Daten", "Keine Zeilen im CSV gefunden.")
            return

        win = tk.Toplevel(self)
        win.title("MyTrueAncestry – Populationsverteilung")
        win.geometry("820x560")
        ttk.Label(win, text=f"MyTrueAncestry: {len(rows)} Populationen importiert",
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,2))

        # Group by era and draw bar chart
        from collections import defaultdict
        era_scores: dict = defaultdict(float)
        for r in rows:
            era_scores[r["era"]] += r["score"]

        era_colors = {
            "Neolithic": "#4CAF50", "Bronze Age": "#FF9800",
            "Iron Age / Historical": "#9C27B0", "Medieval": "#2196F3",
            "Modern": "#F44336", "Ancient / Other": "#795548",
        }

        c = tk.Canvas(win, height=160, bg=self._active_colors()["bg"], highlightthickness=0)
        c.pack(fill="x", padx=10, pady=6)

        def draw_era_bars(_=None):
            c.delete("all")
            W = c.winfo_width() or 780; H = 140
            total = sum(era_scores.values()) or 1
            sorted_eras = sorted(era_scores.items(), key=lambda x: -x[1])
            x = 10
            for era, score in sorted_eras:
                bw = max(5, int((W - 20) * score / total))
                col = era_colors.get(era, "#999999")
                c.create_rectangle(x, 20, x + bw, 80, fill=col, outline="white", width=1)
                if bw > 40:
                    c.create_text(x + bw // 2, 50, text=f"{score:.1f}%",
                                  font=("Segoe UI", 8, "bold"), fill="white")
                c.create_text(x + bw // 2, 95, text=era[:15],
                              font=("Segoe UI", 7), fill=self._active_colors()["text"], angle=45 if bw < 60 else 0)
                x += bw + 2

        c.bind("<Configure>", draw_era_bars)
        win.after(100, draw_era_bars)

        # Detail table
        cols = ("pop","score","dist","era")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for col, (lbl, w, a) in {
            "pop":   ("Population", 300, "w"),
            "score": ("Score %",     80, "e"),
            "dist":  ("Distance",    80, "e"),
            "era":   ("Ära",        200, "w"),
        }.items():
            tv.heading(col, text=lbl); tv.column(col, width=w, anchor=a)
        sy = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sy.set)
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=4)
        sy.pack(side="right", fill="y", pady=4)
        for r in sorted(rows, key=lambda x: -x["score"])[:50]:
            tv.insert("", "end", values=(
                r["population"][:45], f"{r['score']:.2f}",
                f"{r['distance']:.4f}", r["era"]))

    def _show_about(self):
        messagebox.showinfo("Über",
            "Ancestry DNA Tool v2\n\n"
            "Features: Matches + Shared Matches + Leeds-Clustering\n"
            "Datenbank: " + str(DB_PATH))

    # ── Persistente Einstellungen ──────────────────────────────────────────────

    def _load_settings(self):
        """Lädt gespeicherte Einstellungen (Cookie-Pfad, Kit-GUID)."""
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'settings.json')
        try:
            with open(path, encoding='utf-8') as f:
                s = json.load(f)
            if s.get('cookie_file'):
                self._cookie_file_var.set(s['cookie_file'])
            if s.get('manual_guid'):
                self._manual_guid_var.set(s['manual_guid'])
                # Automatisch als Kit registrieren
                guid = s['manual_guid']
                name = 'Gespeichertes Kit (' + guid[:8] + '...)'
                self._kit_map[name] = guid
                self._update_kit_combo()
                self._current_test_guid = guid
            if s.get('last_kit_name') and s['last_kit_name'] in self._kit_map:
                self._kit_var.set(s['last_kit_name'])
            self._set_status('Einstellungen geladen.')
        except (FileNotFoundError, Exception):
            pass

        # GEDCOM-Pfad aus Kommandozeile vorbelegen (überschreibt ui_settings nur wenn nötig)
        if self._startup_gedcom_path:
            import os as _os
            if _os.path.exists(self._startup_gedcom_path):
                st = self._load_ui_settings()
                if not st.get("gedcom_path"):
                    self._save_ui_settings(gedcom_path=self._startup_gedcom_path)
                    self._set_status(
                        f"GEDCOM vorbelegt: {_os.path.basename(self._startup_gedcom_path)}")

    def _save_settings(self):
        """Speichert aktuelle Einstellungen."""
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'settings.json')
        s = {
            'cookie_file' : self._cookie_file_var.get(),
            'manual_guid' : self._manual_guid_var.get(),
            'last_kit_name': self._kit_var.get(),
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning('Einstellungen konnten nicht gespeichert werden: %s', e)

    def _on_close(self):
        if self._scraper and self._scraper.is_running():
            if not messagebox.askyesno("Beenden?", "Download läuft noch. Wirklich beenden?"):
                return
            self._scraper.stop()
        self.shutdown()
        self.winfo_toplevel().destroy()

    def shutdown(self):
        """Aufräumen ohne Fenster zu zerstören – für die eingebettete Nutzung."""
        try: self._save_settings()
        except Exception: pass
        try: self._db.close()
        except Exception: pass

    def _set_gedcom(self, path: str):
        """Setzt den GEDCOM-Pfad von außen (z.B. aus dem Start-Tab)."""
        try:
            import os as _os
            if path and _os.path.exists(path):
                self._save_ui_settings(gedcom_path=path)
                self._set_status(f"GEDCOM-Pfad aktualisiert: {_os.path.basename(path)}")
        except Exception:
            pass
