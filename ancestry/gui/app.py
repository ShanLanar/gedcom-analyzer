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

import config as cfg
from core.auth import AncestryAuth
from core.api import AncestryApiClient
from core.database import Database
from core.scraper import Scraper, DownloadResult
from core.export import export_csv, export_shared_csv, export_xlsx
from core.cluster import build_clusters, suggest_grandparent_lines
from models import DnaKit, DnaMatch, SharedMatch

log = logging.getLogger(__name__)

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
    "primary" : "#2E75B6",
    "accent"  : "#4A9FD4",
    "light"   : "#2A3A4A",
    "bg"      : "#1A2130",
    "text"    : "#E8EDF2",
    "success" : "#4CAF50",
    "warning" : "#FF9800",
    "white"   : "#FFFFFF",
    "cluster" : ["#4A2020","#1E4A2A","#1A2E4A","#3A3010","#2E1A4A","#0A2A3A"],
}

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


class AncestryDnaApp(tk.Frame):

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
        self._db      : Database                    = Database(cfg.DB_FILE)
        self._kit_map : dict[str, str]              = {}
        self._matches_kit_guid_map: dict[str, str]  = {}
        self._matches : list[DnaMatch]              = []
        self._current_test_guid : Optional[str]     = None
        self._startup_gedcom_path: str              = gedcom_path

        self._lang: str = "de"
        self._lang_headings:       list = []   # (tv, col, key) tuples
        self._lang_nb_tabs:        list = []   # (frame, key) tuples
        self._lang_widgets:        list = []   # (widget_or_sv, key[, suffix]) tuples
        self._lang_menus:          list = []   # (menu, index, key) tuples
        self._lang_inner_nb_tabs:  list = []   # (notebook, frame, key) tuples
        self._dark_mode:           bool = False
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
        self._save_ui_settings(dark_mode=self._dark_mode)

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
        hf = tk.Frame(self, bg=COLORS["primary"])
        hf.pack(fill="x")
        ttk.Label(hf, text="🧬  Ancestry DNA Tool",
                  style="Header.TLabel").pack(side="left", fill="x", expand=True)
        self._lang_btn = tk.Button(
            hf, text="🌐 → EN", font=("Segoe UI", 10, "bold"),
            bg="#2E75B6", fg="white", activebackground="#1F4E79", activeforeground="white",
            relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
            command=self._toggle_lang)
        self._lang_btn.pack(side="right", padx=10, pady=4)

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
    # TAB 1: LOGIN
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_login(self):
        f = self._tab_login
        p = {"padx": 16, "pady": 8}

        _sv = tk.StringVar(value=self._t("lg.meth1"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.meth1"))

        _sv = tk.StringVar(value=self._t("lg.email"))
        ttk.Label(f, textvariable=_sv).grid(row=1, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.email"))
        self._email_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._email_var, width=36).grid(row=1, column=1, sticky="w", **p)

        _sv = tk.StringVar(value=self._t("lg.password"))
        ttk.Label(f, textvariable=_sv).grid(row=2, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.password"))
        self._pw_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw_var, show="•", width=36).grid(row=2, column=1, sticky="w", **p)

        _sv = tk.StringVar(value=self._t("lg.login_btn"))
        ttk.Button(f, textvariable=_sv, command=self._do_login).grid(row=3, column=1, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.login_btn"))

        ttk.Separator(f, orient="horizontal").grid(row=4, column=0, columnspan=3,
                                                    sticky="ew", padx=16, pady=12)

        _sv = tk.StringVar(value=self._t("lg.meth2"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=5, column=0, columnspan=3, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.meth2"))
        ttk.Label(f, text=(
            "1. Chrome/Firefox-Extension »Cookie-Editor« installieren\n"
            "2. Auf ancestry.com einloggen\n"
            "3. Cookie-Editor → Export → JSON → speichern\n"
            "4. Datei hier auswählen"
        ), foreground="#555555").grid(row=6, column=0, columnspan=3, sticky="w", padx=16)
        self._cookie_file_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._cookie_file_var, width=36,
                  state="readonly").grid(row=7, column=1, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("lg.choose"))
        ttk.Button(f, textvariable=_sv,
                   command=self._choose_cookie_file).grid(row=7, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.choose"))
        _sv = tk.StringVar(value=self._t("lg.login_ck"))
        ttk.Button(f, textvariable=_sv,
                   command=self._do_login_cookies).grid(row=8, column=1, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.login_ck"))

        ttk.Separator(f, orient="horizontal").grid(row=9, column=0, columnspan=3,
                                                    sticky="ew", padx=16, pady=12)
        _sv = tk.StringVar(value=self._t("lg.manual"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=10, column=0, columnspan=3, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.manual"))
        ttk.Label(f, text="URL: ancestry.com/dna/tests/<GUID>/matches",
                  foreground="#555555").grid(row=11, column=0, columnspan=3, sticky="w", padx=16)
        self._manual_guid_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._manual_guid_var, width=44).grid(
            row=12, column=1, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("lg.use_guid"))
        ttk.Button(f, textvariable=_sv,
                   command=self._use_manual_guid).grid(row=12, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.use_guid"))

        self._login_status_var = tk.StringVar(value="Nicht eingeloggt.")
        self._login_status_lbl = ttk.Label(f, textvariable=self._login_status_var,
                                           style="Warning.TLabel")
        self._login_status_lbl.grid(row=13, column=0, columnspan=3, **p)
        f.columnconfigure(1, weight=1)

    def _do_login(self):
        e, pw = self._email_var.get().strip(), self._pw_var.get()
        if not e or not pw:
            messagebox.showwarning("Eingabe fehlt", "E-Mail und Passwort eingeben.")
            return
        threading.Thread(target=self._login_thread, args=(e, pw, "password"),
                         daemon=True).start()

    def _do_login_cookies(self):
        path = self._cookie_file_var.get().strip()
        if not path:
            messagebox.showwarning("Keine Datei", "Bitte Cookie-Datei auswählen.")
            return
        threading.Thread(target=self._login_thread, args=(path, None, "cookie"),
                         daemon=True).start()

    def _login_thread(self, arg1, arg2, method):
        auth = AncestryAuth()
        ok = auth.login_password(arg1, arg2) if method == "password" else auth.login_cookies(arg1)
        if ok:
            self._auth = auth
            self._client = AncestryApiClient(auth.get_session())
            self._after_login()
        else:
            self.after(0, lambda: self._set_login_status(
                "❌ Login fehlgeschlagen.", success=False))

    def _after_login(self):
        uid  = self._auth.uid or "?"
        kits = []
        if self._auth.uid:
            kits = self._client.get_dna_kits(self._auth.uid)
            if not kits:
                guid = self._client.detect_kit_from_uid(self._auth.uid)
                if guid:
                    kits = [DnaKit(guid=guid, name="Mein DNA-Test")]
        for kit in kits:
            self._kit_map[kit.name] = kit.guid
            self._db.upsert_kit(kit)

        def _upd():
            self._set_login_status(
                f"✅ Eingeloggt (UID: {uid[:16]}…) | {len(kits)} Kit(s)", success=True)
            self._set_status("Login erfolgreich.")
            self._update_kit_combo()
            self._nb.select(1)
            self._save_settings()
        self.after(0, _upd)

    def _choose_cookie_file(self):
        p = filedialog.askopenfilename(title="Cookie-JSON wählen",
                                        filetypes=[("JSON", "*.json"), ("Alle", "*.*")])
        if p:
            self._cookie_file_var.set(p)

    def _use_manual_guid(self):
        guid = self._manual_guid_var.get().strip()
        if not guid:
            messagebox.showwarning("Keine GUID", "Bitte eine Kit-GUID eingeben.")
            return
        name = f"Manuell ({guid[:8]}…)"
        self._kit_map[name] = guid
        self._update_kit_combo()
        self._current_test_guid = guid
        self._save_settings()
        self._set_status(f"Kit-GUID gespeichert.")

    def _set_login_status(self, msg, success=True):
        self._login_status_var.set(msg)
        self._login_status_lbl.configure(
            style="Success.TLabel" if success else "Warning.TLabel")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2: HERUNTERLADEN
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_download(self):
        f = self._tab_download
        p = {"padx": 14, "pady": 6}

        # Kit-Auswahl
        _sv = tk.StringVar(value=self._t("dl.kit"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(row=0, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.kit"))
        self._kit_var = tk.StringVar()
        self._kit_combo = ttk.Combobox(f, textvariable=self._kit_var, width=46, state="readonly")
        self._kit_combo.grid(row=0, column=1, columnspan=2, sticky="w", **p)
        self._update_kit_combo()

        # ── Bereich A: Matches ────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=1, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=self._t("dl.sec_a"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", **p)
        self._lang_widgets.append((_sv, "dl.sec_a"))

        _sv = tk.StringVar(value=self._t("dl.filter"))
        ttk.Label(f, textvariable=_sv).grid(row=3, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.filter"))
        self._filter_var = tk.StringVar(value="ALL")
        ff = ttk.Frame(f); ff.grid(row=3, column=1, sticky="w", **p)
        for val, key in [("ALL","dl.f_all"),("STARRED","dl.f_star"),
                         ("CLOSE","dl.f_close"),("DISTANT","dl.f_distant")]:
            _sv = tk.StringVar(value=self._t(key))
            ttk.Radiobutton(ff, textvariable=_sv, variable=self._filter_var, value=val).pack(
                side="left", padx=5)
            self._lang_widgets.append((_sv, key))

        _sv = tk.StringVar(value=self._t("dl.sort"))
        ttk.Label(f, textvariable=_sv).grid(row=4, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.sort"))
        self._sort_var = tk.StringVar(value="RELATIONSHIP")
        sf = ttk.Frame(f); sf.grid(row=4, column=1, sticky="w", **p)
        for val, key in [("RELATIONSHIP","dl.s_rel"),("SHARED_CM","dl.s_cm")]:
            _sv = tk.StringVar(value=self._t(key))
            ttk.Radiobutton(sf, textvariable=_sv, variable=self._sort_var, value=val).pack(
                side="left", padx=5)
            self._lang_widgets.append((_sv, key))

        bf = ttk.Frame(f); bf.grid(row=5, column=0, columnspan=4, sticky="w", **p)
        _sv_start_m = tk.StringVar(value=self._t("dl.start_m"))
        self._start_btn = ttk.Button(bf, textvariable=_sv_start_m, command=self._start_matches)
        self._start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_start_m, "dl.start_m"))
        _sv_stop1 = tk.StringVar(value=self._t("dl.stop"))
        self._stop_btn = ttk.Button(bf, textvariable=_sv_stop1,
                                    command=self._stop_download, state="disabled")
        self._stop_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_stop1, "dl.stop"))
        self._only_new_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=self._t("dl.only_new"))
        ttk.Checkbutton(bf, textvariable=_sv, variable=self._only_new_var).pack(side="left", padx=14)
        self._lang_widgets.append((_sv, "dl.only_new"))
        self._fetch_names_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=self._t("dl.full_names"))
        ttk.Checkbutton(bf, textvariable=_sv, variable=self._fetch_names_var).pack(side="left", padx=14)
        self._lang_widgets.append((_sv, "dl.full_names"))

        # ── Bereich A2: Namen nachladen ───────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=6, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=self._t("dl.sec_a2"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=7, column=0, columnspan=4, sticky="w", **p)
        self._lang_widgets.append((_sv, "dl.sec_a2"))
        ttk.Label(f, text=(
            "Lädt Namen, Geschlecht, Stammbaum-Status/-Größe und ob ein\n"
            "gemeinsamer Vorfahre existiert (20 Matches pro Anfrage).\n"
            "Danach: 'Vorfahren & Orte' + 'Ahnentafeln' laden für ALLE Matches\n"
            "mit Baum (nicht nur Ancestrys erkannte) – dann Auswertung/GEDCOM-Abgleich."
        ), foreground="#555555").grid(row=8, column=0, columnspan=4, sticky="w", padx=14)

        sf_names = ttk.Frame(f); sf_names.grid(row=9, column=0, columnspan=4, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("dl.min_cm"))
        ttk.Label(sf_names, textvariable=_sv).pack(side="left")
        self._lang_widgets.append((_sv, "dl.min_cm"))
        self._names_min_cm_var = tk.StringVar(value="0")
        ttk.Entry(sf_names, textvariable=self._names_min_cm_var, width=6).pack(side="left", padx=6)
        _sv = tk.StringVar(value=self._t("dl.depth"))
        ttk.Label(sf_names, textvariable=_sv).pack(side="left", padx=(18, 0))
        self._lang_widgets.append((_sv, "dl.depth"))
        self._ped_gens_var = tk.StringVar(value="5")
        ttk.Combobox(sf_names, textvariable=self._ped_gens_var,
                     values=["5", "6", "7", "8", "10"], width=4,
                     state="readonly").pack(side="left", padx=4)
        self._ped_force_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=self._t("dl.reload_all"))
        ttk.Checkbutton(sf_names, textvariable=_sv,
                        variable=self._ped_force_var).pack(side="left", padx=(12, 4))
        self._lang_widgets.append((_sv, "dl.reload_all"))
        ttk.Label(sf_names, text="(>5 Gen. = langsamer, mehr Extra-Calls)",
                  foreground="#888888").pack(side="left")

        bf_names = ttk.Frame(f); bf_names.grid(row=10, column=0, columnspan=4, sticky="w", **p)
        _sv_nm = tk.StringVar(value=self._t("dl.start_nm"))
        self._names_start_btn = ttk.Button(bf_names, textvariable=_sv_nm,
                                            command=self._start_fetch_names)
        self._names_start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_nm, "dl.start_nm"))
        _sv_stop2 = tk.StringVar(value=self._t("dl.stop"))
        self._names_stop_btn = ttk.Button(bf_names, textvariable=_sv_stop2,
                                           command=self._stop_download, state="disabled")
        self._names_stop_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_stop2, "dl.stop"))
        _sv_anc = tk.StringVar(value=self._t("dl.start_anc"))
        self._anc_start_btn = ttk.Button(bf_names, textvariable=_sv_anc,
                                         command=self._start_fetch_ancestors)
        self._anc_start_btn.pack(side="left", padx=(16,4))
        self._lang_widgets.append((_sv_anc, "dl.start_anc"))
        _sv_ped = tk.StringVar(value=self._t("dl.start_ped"))
        self._ped_start_btn = ttk.Button(bf_names, textvariable=_sv_ped,
                                         command=self._start_fetch_pedigrees)
        self._ped_start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_ped, "dl.start_ped"))

        # ── Bereich B: Shared Matches ─────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=11, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        _sv = tk.StringVar(value=self._t("dl.sec_b"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=12, column=0, columnspan=4, sticky="w", **p)
        self._lang_widgets.append((_sv, "dl.sec_b"))
        ttk.Label(f, text=(
            "Lädt für jeden gespeicherten Match dessen gemeinsame Matches mit cM-Werten.\n"
            "Empfehlung: erst Matches (A) herunterladen, dann Shared Matches (B).\n"
            "Ab 20 cM sinnvoll – erfasst auch entferntere Verwandte.\n"
            "Tipp: Höherer cM-Wert = deutlich weniger primäre Matches = viel schneller (kann sonst Stunden dauern)."
        ), foreground="#555555").grid(row=13, column=0, columnspan=4, sticky="w", padx=14)

        sf2 = ttk.Frame(f); sf2.grid(row=14, column=0, columnspan=4, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("dl.prim_min"))
        ttk.Label(sf2, textvariable=_sv).pack(side="left")
        self._lang_widgets.append((_sv, "dl.prim_min"))
        self._shared_min_cm_var = tk.StringVar(value="20")
        ttk.Entry(sf2, textvariable=self._shared_min_cm_var, width=6).pack(side="left", padx=6)
        self._skip_existing_var = tk.BooleanVar(value=True)
        _sv = tk.StringVar(value=self._t("dl.skip_ex"))
        ttk.Checkbutton(sf2, textvariable=_sv,
                         variable=self._skip_existing_var).pack(side="left", padx=12)
        self._lang_widgets.append((_sv, "dl.skip_ex"))

        bf2 = ttk.Frame(f); bf2.grid(row=15, column=0, columnspan=4, sticky="w", **p)
        _sv_sh = tk.StringVar(value=self._t("dl.start_sh"))
        self._shared_start_btn = ttk.Button(bf2, textvariable=_sv_sh, command=self._start_shared)
        self._shared_start_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_sh, "dl.start_sh"))
        _sv_stop3 = tk.StringVar(value=self._t("dl.stop"))
        self._shared_stop_btn = ttk.Button(bf2, textvariable=_sv_stop3,
                                            command=self._stop_download, state="disabled")
        self._shared_stop_btn.pack(side="left", padx=4)
        self._lang_widgets.append((_sv_stop3, "dl.stop"))

        # ── Fortschritt ───────────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=16, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        _sv = tk.StringVar(value=self._t("dl.progress"))
        ttk.Label(f, textvariable=_sv).grid(row=17, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "dl.progress"))
        self._progress_var = tk.DoubleVar()
        ttk.Progressbar(f, variable=self._progress_var, maximum=100, length=380).grid(
            row=17, column=1, sticky="w", **p)
        self._progress_lbl = tk.StringVar(value="—")
        ttk.Label(f, textvariable=self._progress_lbl).grid(row=17, column=2, sticky="w", **p)

        # Pause-Button
        self._pause_sv = tk.StringVar(value=self._t("dl.pause"))
        self._pause_btn = ttk.Button(f, textvariable=self._pause_sv,
                                      command=self._toggle_pause, state="disabled")
        self._pause_btn.grid(row=17, column=3, sticky="w", **p)
        self._lang_widgets.append((self._pause_sv, "dl.pause"))

        # ETA-Label
        self._eta_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self._eta_var, foreground="#777777").grid(
            row=17, column=4, sticky="w", **p)

        # Dashboard: 4 Live-Zähler
        dash = ttk.Frame(f); dash.grid(row=17, column=5, sticky="w", padx=8)
        self._dash_vars: dict[str, tk.StringVar] = {}
        for i, (key, icon) in enumerate([("dl.dash_mat","🧬"),("dl.dash_tree","🌳"),
                                          ("dl.dash_sh","👥"),("dl.dash_err","❌")]):
            col_frame = ttk.Frame(dash); col_frame.grid(row=0, column=i, padx=6)
            _sv_d = tk.StringVar(value=self._t(key))
            ttk.Label(col_frame, textvariable=_sv_d, foreground="#777777",
                      font=("Segoe UI", 8)).pack()
            self._lang_widgets.append((_sv_d, key))
            val_sv = tk.StringVar(value="0")
            ttk.Label(col_frame, textvariable=val_sv, font=("Segoe UI", 11, "bold"),
                      foreground=COLORS["primary"]).pack()
            dk = key.replace("dl.dash_","")
            self._dash_vars[dk] = val_sv

        # ── Log ───────────────────────────────────────────────────────────────
        _sv = tk.StringVar(value=self._t("dl.log"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(
            row=18, column=0, sticky="ne", padx=14, pady=(10, 4))
        self._lang_widgets.append((_sv, "dl.log"))
        lf = ttk.Frame(f); lf.grid(row=18, column=1, columnspan=3, sticky="nsew",
                                     padx=14, pady=4)
        self._log_text = tk.Text(lf, height=12, width=72, font=("Consolas", 9),
                                  bg="#1E1E2E", fg="#A0D0FF", state="disabled", relief="flat")
        sc = ttk.Scrollbar(lf, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sc.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        f.columnconfigure(1, weight=1)
        f.rowconfigure(13, weight=1)
        self._install_gui_log_handler()

    def _install_gui_log_handler(self):
        widget = self._log_text

        class GUIHandler(logging.Handler):
            def __init__(self, w):
                super().__init__()
                self._w = w
            def emit(self, record):
                msg   = self.format(record) + "\n"
                color = {"DEBUG":"#888888","INFO":"#A0D0FF",
                         "WARNING":"#FFD080","ERROR":"#FF8080"}.get(record.levelname,"#A0D0FF")
                try:
                    def _ins():
                        self._w.configure(state="normal")
                        self._w.insert("end", msg, record.levelname)
                        self._w.tag_config(record.levelname, foreground=color)
                        self._w.see("end")
                        self._w.configure(state="disabled")
                    self._w.after(0, _ins)
                except Exception:
                    pass

        h = GUIHandler(widget)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(h)

    def _update_kit_combo(self):
        names = list(self._kit_map.keys())
        self._kit_combo["values"] = names
        if names and not self._kit_var.get():
            self._kit_combo.current(0)
        self._update_matches_kit_combo()

    _ALL_SOURCES_LABEL = "— Alle Plattformen —"

    def _update_matches_kit_combo(self):
        """Befüllt den Kit-Selektor im Matches-Tab aus DB + _kit_map."""
        if not hasattr(self, "_matches_kit_combo"):
            return
        try:
            db_kits = self._db.get_kits()
        except Exception:
            db_kits = []
        combined: dict[str, str] = {}
        # Sentinel für plattformübergreifende Ansicht
        combined[self._ALL_SOURCES_LABEL] = ""
        for k in db_kits:
            name = k.name or f"Kit {k.guid[:8]}"
            combined[name] = k.guid
        for name, guid in self._kit_map.items():
            combined.setdefault(name, guid)
        self._matches_kit_guid_map = combined
        names = list(combined.keys())
        self._matches_kit_combo["values"] = names
        if names and self._matches_kit_var.get() not in names:
            self._matches_kit_combo.current(0)

    def _get_kit_guid(self) -> Optional[str]:
        return self._kit_map.get(self._kit_var.get())

    def _start_matches(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._pause_btn.configure(state="normal")
        self._dl_t0 = 0.0
        self._pause_event.set()
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                 on_progress=self._on_progress,
                                 on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                 on_done=self._on_done)
        if self._fetch_names_var.get():
            self._set_status("Hinweis: 'Volle Namen' lädt jeden Match einzeln – "
                             "das kann bei vielen Matches sehr lange dauern.")
        self._scraper.start_matches(guid, self._filter_var.get(), self._sort_var.get(),
                                     only_new=self._only_new_var.get(),
                                     fetch_names=self._fetch_names_var.get())

    def _start_shared(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        total_matches = self._db.get_match_count(guid)
        if total_matches == 0:
            messagebox.showwarning("Keine Matches",
                                   "Erst Matches herunterladen (Schritt A).")
            return
        try:
            min_cm = float(self._shared_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 90.0

        self._current_test_guid = guid
        self._shared_start_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                 on_progress=self._on_progress,
                                 on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                 on_done=self._on_shared_done)
        self._scraper.start_shared(guid, min_cm, self._skip_existing_var.get())

    def _start_fetch_names(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        try:
            min_cm = float(self._names_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 0.0
        self._current_test_guid = guid
        self._names_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_names_done(r)))
        self._scraper.start_fetch_names(guid, min_cm)

    def _on_names_done(self, result: "DownloadResult"):
        self._names_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Namen", result.message)

    def _start_fetch_ancestors(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._anc_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_ancestors_done(r)))
        self._scraper.start_fetch_ancestors(guid, self._a2_min_cm())

    def _on_ancestors_done(self, result: "DownloadResult"):
        self._anc_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Vorfahren", result.message)

    def _start_fetch_pedigrees(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._ped_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        try:
            max_gen = int(self._ped_gens_var.get())
        except (ValueError, AttributeError):
            max_gen = 5
        force = bool(getattr(self, "_ped_force_var", None) and self._ped_force_var.get())
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_pedigrees_done(r)))
        self._scraper.start_fetch_pedigrees(guid, self._a2_min_cm(), max_gen, force)

    def _a2_min_cm(self) -> float:
        """cM-Schwelle aus dem A2-Feld 'Nur ab (cM)'."""
        try:
            return float(self._names_min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            return 0.0

    def _on_pedigrees_done(self, result: "DownloadResult"):
        self._ped_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Ahnentafeln", result.message)

    # ── Überlagerung: gemeinsame Vorfahren ─────────────────────────────────────

    def _current_guid(self):
        return self._get_kit_guid() or getattr(self, "_current_test_guid", None)

    # ── Namenskarte.com helper ────────────────────────────────────────────────

    def _open_namenskarte(self, surname: str):
        """Opens namenskarte.com for the given surname in the default browser."""
        url = f"https://www.namenskarte.com/nachname/{quote(surname)}"
        webbrowser.open(url)

    # ── Nachname-Analyse ──────────────────────────────────────────────────────

    def _show_surname_analysis(self):
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Nachname-Analyse – Häufigste Nachnamen in Match-Ahnentafeln")
        win.geometry("960x640")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="Min. Matches:", style="Bold.TLabel").pack(side="left")
        min_var = tk.StringVar(value="2")
        ttk.Spinbox(top, from_=1, to=99, width=4, textvariable=min_var).pack(side="left", padx=4)
        ttk.Label(top, text="  Suche:").pack(side="left", padx=(12,0))
        search_var = tk.StringVar()
        ttk.Entry(top, textvariable=search_var, width=18).pack(side="left", padx=4)

        info = ttk.Label(win, text="", style="Bold.TLabel")
        info.pack(anchor="w", padx=10, pady=(2,2))

        # Toolbar
        tb = ttk.Frame(win); tb.pack(fill="x", padx=10, pady=(0,4))

        pane = ttk.PanedWindow(win, orient="vertical")
        pane.pack(fill="both", expand=True, padx=10, pady=(0,6))

        tframe = ttk.Frame(pane); pane.add(tframe, weight=4)
        bframe = ttk.Frame(pane); pane.add(bframe, weight=2)

        cols = ("surname","count","avg_cm","max_cm","gen_range")
        tv = ttk.Treeview(tframe, columns=cols, show="headings", selectmode="browse")
        for c,(lbl,w,anch) in {
            "surname":   ("Nachname",       260, "w"),
            "count":     ("Matches",         80, "center"),
            "avg_cm":    ("Ø cM",            80, "e"),
            "max_cm":    ("Max cM",          80, "e"),
            "gen_range": ("Generationen",   100, "center"),
        }.items():
            tv.heading(c, text=lbl, command=lambda c=c: _sort(c))
            tv.column(c, width=w, anchor=anch)
        sy = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sy.set)
        tv.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")

        ttk.Label(bframe, text="Matches mit diesem Nachnamen:",
                  style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bframe, height=6, wrap="word", font=("Segoe UI", 9))
        ds = ttk.Scrollbar(bframe, orient="vertical", command=detail.yview)
        detail.configure(yscrollcommand=ds.set)
        detail.pack(side="left", fill="both", expand=True)
        ds.pack(side="right", fill="y")

        store = {}
        _sort_col = ["count"]; _sort_asc = [False]

        def _get_selected_surname():
            sel = tv.selection()
            if not sel: return None
            g = store.get(sel[0])
            return g["label"] if g else None

        def _namenskarte():
            s = _get_selected_surname()
            if s:
                self._open_namenskarte(s)
            else:
                messagebox.showinfo("Kein Name", "Bitte zuerst einen Nachnamen auswählen.")

        ttk.Button(tb, text="🗺 Namenskarte.com öffnen",
                   command=_namenskarte).pack(side="left", padx=4)
        ttk.Button(tb, text="↻ Aktualisieren",
                   command=lambda: reload()).pack(side="left", padx=4)

        def _sort(col):
            if _sort_col[0] == col:
                _sort_asc[0] = not _sort_asc[0]
            else:
                _sort_col[0] = col; _sort_asc[0] = col not in ("count","avg_cm","max_cm")
            reload()

        def reload(*_):
            try:
                mm = max(1, int(min_var.get() or 1))
            except ValueError:
                mm = 1
            q = search_var.get().strip().lower()
            groups = self._db.get_pedigree_groups(test_guid, min_matches=mm, mode="surname")
            if q:
                groups = [g for g in groups if q in g["label"].lower()]
            tv.delete(*tv.get_children()); store.clear()
            def _key(g):
                cms = [cm for _, _, _, _, cm in g["matches"] if cm]
                avg = sum(cms)/len(cms) if cms else 0
                mx  = max(cms) if cms else 0
                gens = [gen for _, _, _, gen, _ in g["matches"] if gen]
                return g["label"], g["count"], avg, mx, gens
            enriched = [(_key(g), g) for g in groups]
            col = _sort_col[0]
            ci  = {"surname":0,"count":1,"avg_cm":2,"max_cm":3,"gen_range":4}.get(col,1)
            enriched.sort(key=lambda x: x[0][ci], reverse=not _sort_asc[0])
            for (lbl, cnt, avg, mx, gens), g in enriched:
                gen_range = (f"{min(gens)}–{max(gens)}" if gens else "?")
                iid = tv.insert("", "end", values=(
                    lbl, cnt,
                    f"{avg:.0f}" if avg else "—",
                    f"{mx:.0f}"  if mx  else "—",
                    gen_range,
                ))
                store[iid] = g
            info.configure(text=(
                f"{len(groups)} Nachnamen in ≥{mm} Match-Ahnentafeln." if groups
                else "Keine Daten – erst '▶ Ahnentafeln laden' ausführen."))

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            g = store.get(sel[0])
            if not g: return
            detail.delete("1.0","end")
            for guid, name, path, gen, cm in sorted(g["matches"], key=lambda x:-(x[4] or 0)):
                detail.insert("end", f"  • {name or guid[:8]}   {(cm or 0):.0f} cM"
                              f"   Gen {gen}"
                              f"   Linie {path or '?'}\n")

        tv.bind("<<TreeviewSelect>>", on_sel)
        tv.bind("<Double-1>", lambda _: _namenskarte())
        min_var.trace_add("write", reload)
        search_var.trace_add("write", reload)
        reload()

    # ── Geburtsort-Analyse ────────────────────────────────────────────────────

    def _show_place_analysis(self):
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Geburtsort-Analyse – Häufigste Orte in Match-Ahnentafeln")
        win.geometry("960x600")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="Min. Matches:", style="Bold.TLabel").pack(side="left")
        min_var = tk.StringVar(value="2")
        ttk.Spinbox(top, from_=1, to=99, width=4, textvariable=min_var).pack(side="left", padx=4)
        ttk.Label(top, text="  Suche:").pack(side="left", padx=(12,0))
        search_var = tk.StringVar()
        ttk.Entry(top, textvariable=search_var, width=22).pack(side="left", padx=4)

        info = ttk.Label(win, text="", style="Bold.TLabel")
        info.pack(anchor="w", padx=10, pady=(2,2))

        tb = ttk.Frame(win); tb.pack(fill="x", padx=10, pady=(0,4))

        pane = ttk.PanedWindow(win, orient="vertical")
        pane.pack(fill="both", expand=True, padx=10, pady=(0,6))
        tframe = ttk.Frame(pane); pane.add(tframe, weight=4)
        bframe = ttk.Frame(pane); pane.add(bframe, weight=2)

        cols = ("place","count","avg_cm","gen_range")
        tv = ttk.Treeview(tframe, columns=cols, show="headings", selectmode="browse")
        for c,(lbl,w,anch) in {
            "place":     ("Geburtsort",     350, "w"),
            "count":     ("Matches",         80, "center"),
            "avg_cm":    ("Ø cM",            80, "e"),
            "gen_range": ("Generationen",   100, "center"),
        }.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=anch)
        sy = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sy.set)
        tv.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")

        ttk.Label(bframe, text="Matches mit diesem Ort:",
                  style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bframe, height=6, wrap="word", font=("Segoe UI", 9))
        ds = ttk.Scrollbar(bframe, orient="vertical", command=detail.yview)
        detail.configure(yscrollcommand=ds.set)
        detail.pack(side="left", fill="both", expand=True)
        ds.pack(side="right", fill="y")

        store = {}

        def _search_maps():
            sel = tv.selection()
            if not sel: return
            g = store.get(sel[0])
            if not g: return
            q = quote(g["label"])
            webbrowser.open(f"https://www.google.com/maps/search/{q}")

        ttk.Button(tb, text="🗺 Google Maps öffnen",
                   command=_search_maps).pack(side="left", padx=4)
        ttk.Button(tb, text="🔍 Meyers Gazetteer",
                   command=lambda: (lambda sel: webbrowser.open(
                       f"https://gov.genealogy.net/search/index#q={quote(store[sel[0]]['label'])}"
                       ) if (sel := tv.selection()) else None)(tv.selection())).pack(
                   side="left", padx=4)

        def reload(*_):
            try:
                mm = max(1, int(min_var.get() or 1))
            except ValueError:
                mm = 1
            q = search_var.get().strip().lower()
            groups = self._db.get_pedigree_groups(test_guid, min_matches=mm, mode="place")
            if q:
                groups = [g for g in groups if q in g["label"].lower()]
            tv.delete(*tv.get_children()); store.clear()
            for g in groups:
                cms  = [cm for _, _, _, _, cm in g["matches"] if cm]
                avg  = sum(cms)/len(cms) if cms else 0
                gens = [gen for _, _, _, gen, _ in g["matches"] if gen]
                gen_range = (f"{min(gens)}–{max(gens)}" if gens else "?")
                iid = tv.insert("", "end", values=(
                    g["label"], g["count"],
                    f"{avg:.0f}" if avg else "—",
                    gen_range,
                ))
                store[iid] = g
            info.configure(text=(
                f"{len(groups)} Orte in ≥{mm} Match-Ahnentafeln." if groups
                else "Keine Daten – erst '▶ Ahnentafeln laden' ausführen."))

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            g = store.get(sel[0])
            if not g: return
            detail.delete("1.0","end")
            for guid, name, path, gen, cm in sorted(g["matches"], key=lambda x:-(x[4] or 0)):
                detail.insert("end", f"  • {name or guid[:8]}   {(cm or 0):.0f} cM"
                              f"   Gen {gen}\n")

        tv.bind("<<TreeviewSelect>>", on_sel)
        min_var.trace_add("write", reload)
        search_var.trace_add("write", reload)
        reload()

    # ── MRCA-Wahrscheinlichkeit ───────────────────────────────────────────────

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

    def _show_mrca_analysis(self, match=None):
        """Zeigt cM-basierte MRCA-Wahrscheinlichkeiten für den gewählten Match
        oder – ohne Argument – für den aktuell selektierten Match."""
        if match is None:
            match = getattr(self, "_selected_match", None)
        if match is None:
            messagebox.showinfo("Kein Match", "Bitte zuerst einen Match in der Tabelle auswählen.")
            return

        try:
            from core.treematch import cm_to_mrca
        except ImportError:
            cm_to_mrca = None

        cm = getattr(match, "shared_cm", 0) or 0
        segs = getattr(match, "shared_segments", 0) or 0
        longest = getattr(match, "longest_segment", 0) or 0

        win = tk.Toplevel(self)
        win.title(f"MRCA-Analyse: {match.display_name}")
        win.geometry("580x460")
        win.resizable(True, True)

        ttk.Label(win, text=f"{match.display_name}",
                  style="Bold.TLabel", font=("Segoe UI",12,"bold")).pack(anchor="w", padx=14, pady=(12,2))
        ttk.Label(win, text=f"{cm:.1f} cM  ·  {segs} Segmente  ·  längstes {longest:.1f} cM"
                            f"  ·  {match.predicted_relationship or '?'}",
                  foreground="#555").pack(anchor="w", padx=14, pady=(0,6))

        # cM lookup
        rel_frame = ttk.LabelFrame(win, text="Beziehungsbereich (Shared cM Project 2020)", padding=8)
        rel_frame.pack(fill="x", padx=14, pady=4)

        match_row = None
        for lo, hi, label, gen in self._CM_RANGES:
            if lo <= cm <= hi:
                match_row = (lo, hi, label, gen)
                break
        # best fit even outside exact ranges
        if match_row is None:
            dists = [(abs(cm - (lo+hi)/2), lo, hi, label, gen) for lo,hi,label,gen in self._CM_RANGES]
            dists.sort()
            _, lo, hi, label, gen = dists[0]
            match_row = (lo, hi, label, gen)

        cols2 = ttk.Treeview(rel_frame, columns=("rel","range","gen","match"),
                             show="headings", height=len(self._CM_RANGES))
        cols2.heading("rel",   text="Beziehung")
        cols2.heading("range", text="cM-Bereich")
        cols2.heading("gen",   text="Gen.")
        cols2.heading("match", text="Trifft zu")
        cols2.column("rel",   width=260, anchor="w")
        cols2.column("range", width=110, anchor="center")
        cols2.column("gen",   width=45,  anchor="center")
        cols2.column("match", width=70,  anchor="center")
        cols2.tag_configure("hit", background="#d8f0d8", font=("Segoe UI",9,"bold"))
        for lo, hi, label, gen in self._CM_RANGES:
            tag = ("hit",) if (lo, hi) == (match_row[0], match_row[1]) else ()
            cols2.insert("", "end", tags=tag, values=(
                label, f"{lo}–{hi}", gen,
                "✓" if (lo, hi) == (match_row[0], match_row[1]) else ""))
        cols2.pack(fill="x")

        # MRCA generation estimate
        if cm_to_mrca:
            try:
                lbl_mrca, gen_mrca = cm_to_mrca(cm)
            except Exception:
                lbl_mrca, gen_mrca = match_row[2], match_row[3]
        else:
            lbl_mrca, gen_mrca = match_row[2], match_row[3]

        inf_frame = ttk.LabelFrame(win, text="Schätzung gemeinsamer Vorfahr (MRCA)", padding=8)
        inf_frame.pack(fill="x", padx=14, pady=4)
        ttk.Label(inf_frame,
                  text=f"Geschätzte Beziehung: {lbl_mrca}",
                  style="Bold.TLabel").pack(anchor="w")
        ttk.Label(inf_frame,
                  text=f"Gemeinsamer Vorfahr ca. Generation {gen_mrca} zurück",
                  foreground="#333").pack(anchor="w")
        if longest > 0:
            ttk.Label(inf_frame,
                      text=f"Längstes Segment {longest:.1f} cM → "
                           f"{'identisches Segment wahrscheinlich' if longest > 30 else 'entfernter Verwandter, IBD möglich'}",
                      foreground="#555").pack(anchor="w")
        if segs > 0 and cm > 0:
            avg_seg = cm / segs
            ttk.Label(inf_frame,
                      text=f"Ø Segment {avg_seg:.1f} cM · "
                           f"{'viele kurze Segmente → mögliche Endogamie' if segs > 12 and avg_seg < 15 else 'normal'}",
                      foreground="#555").pack(anchor="w")

    # ── Cluster-Netzwerkgraph (Canvas) ────────────────────────────────────────

    def _show_network_graph(self):
        """Canvas-basierter Netzwerkgraph der Cluster-Mitglieder mit shared-cM als Kantengewicht."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Cluster-Netzwerkgraph")
        win.geometry("1000x700")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="Primäre Matches ab (cM):", style="Bold.TLabel").pack(side="left")
        lo_var = tk.StringVar(value="80")
        ttk.Entry(top, textvariable=lo_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="bis:").pack(side="left")
        hi_var = tk.StringVar(value="900")
        ttk.Entry(top, textvariable=hi_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="  Min. shared cM:").pack(side="left", padx=(12,0))
        edge_var = tk.StringVar(value="15")
        ttk.Entry(top, textvariable=edge_var, width=5).pack(side="left", padx=4)

        info = ttk.Label(win, text="", foreground="#555")
        info.pack(anchor="w", padx=10)

        canvas = tk.Canvas(win, bg="#1a1a2e", cursor="crosshair")
        canvas.pack(fill="both", expand=True, padx=6, pady=4)

        legend = ttk.Frame(win); legend.pack(fill="x", padx=10, pady=(0,6))
        ttk.Label(legend, text="● Knotengröße ∝ cM  ·  Liniendicke ∝ shared cM zwischen Matches  "
                               "·  Farbe = Cluster").pack(side="left")

        _node_data = {}  # tag → (name, cm)

        def _draw(*_):
            canvas.delete("all")
            _node_data.clear()
            try:
                lo = float(lo_var.get() or 0)
                hi = float(hi_var.get() or 9999)
                min_edge = float(edge_var.get() or 0)
            except ValueError:
                return

            clusters = self._db.get_shared_clusters(test_guid, lo, hi)
            if not clusters:
                canvas.create_text(500, 300, text="Keine Cluster – erst Shared Matches laden (Schritt B).",
                                   fill="white", font=("Segoe UI",12))
                return

            # Collect all members (deduplicated) and their cluster assignments
            import math, random
            random.seed(42)
            W = canvas.winfo_width() or 980
            H = canvas.winfo_height() or 650
            all_members: dict = {}  # guid → {name, cm, cluster_idx, cluster_color}
            cl_colors = COLORS["cluster"]
            for ci, cl in enumerate(clusters[:20]):
                col = cl_colors[ci % len(cl_colors)]
                for guid, name, cm in cl["members"]:
                    if guid not in all_members:
                        all_members[guid] = {"name": name, "cm": cm or 0,
                                             "ci": ci, "color": col}

            if not all_members:
                return

            # Simple force-directed layout (spring model, 30 iterations)
            guids = list(all_members.keys())
            n = len(guids)
            angle_step = 2 * math.pi / max(n, 1)
            r0 = min(W, H) * 0.38
            # Initial positions: circle
            pos = {g: (W/2 + r0 * math.cos(i * angle_step),
                       H/2 + r0 * math.sin(i * angle_step))
                   for i, g in enumerate(guids)}

            # Collect edges from shared_matches
            edges: list = []
            for ci, cl in enumerate(clusters[:20]):
                cl_guids = [g for g, _, _ in cl["members"]]
                pairs = self._db.get_pairwise_shared(test_guid, cl_guids)
                for (ga, gb, cm_ab) in pairs:
                    if cm_ab and cm_ab >= min_edge and ga in pos and gb in pos:
                        edges.append((ga, gb, cm_ab))

            # Spring layout iterations
            k = math.sqrt(W * H / max(n, 1)) * 0.6
            for _ in range(40):
                disp = {g: [0.0, 0.0] for g in guids}
                # Repulsion
                for i in range(n):
                    for j in range(i+1, n):
                        gi, gj = guids[i], guids[j]
                        dx = pos[gi][0] - pos[gj][0]
                        dy = pos[gi][1] - pos[gj][1]
                        d  = max(math.hypot(dx, dy), 1)
                        f  = k*k / d
                        disp[gi][0] += dx/d*f; disp[gi][1] += dy/d*f
                        disp[gj][0] -= dx/d*f; disp[gj][1] -= dy/d*f
                # Attraction along edges
                for ga, gb, cm_ab in edges:
                    if ga not in pos or gb not in pos: continue
                    dx = pos[ga][0] - pos[gb][0]
                    dy = pos[ga][1] - pos[gb][1]
                    d  = max(math.hypot(dx, dy), 1)
                    f  = d*d / k
                    disp[ga][0] -= dx/d*f; disp[ga][1] -= dy/d*f
                    disp[gb][0] += dx/d*f; disp[gb][1] += dy/d*f
                # Apply displacement (damped)
                temp = 20
                for g in guids:
                    dm = math.hypot(*disp[g])
                    if dm > 0:
                        scale = min(dm, temp) / dm
                        x = max(40, min(W-40, pos[g][0] + disp[g][0]*scale))
                        y = max(40, min(H-40, pos[g][1] + disp[g][1]*scale))
                        pos[g] = (x, y)

            # Draw edges
            max_cm_edge = max((cm for _, _, cm in edges), default=1)
            for ga, gb, cm_ab in edges:
                if ga not in pos or gb not in pos: continue
                w = max(1, int(cm_ab / max_cm_edge * 5))
                alpha_hex = f"#{int(cm_ab/max_cm_edge*180):02x}{int(cm_ab/max_cm_edge*180):02x}ff"
                try:
                    canvas.create_line(pos[ga][0], pos[ga][1], pos[gb][0], pos[gb][1],
                                       width=w, fill="#4488cc", smooth=True)
                except Exception:
                    pass

            # Draw nodes
            max_cm_node = max((d["cm"] for d in all_members.values()), default=1)
            for guid, d in all_members.items():
                if guid not in pos: continue
                x, y = pos[guid]
                r = max(8, min(28, int(d["cm"] / max_cm_node * 26) + 8))
                tag = f"node_{guid}"
                canvas.create_oval(x-r, y-r, x+r, y+r,
                                   fill=d["color"], outline="white", width=1, tags=tag)
                short = (d["name"] or guid[:8])[:14]
                canvas.create_text(x, y+r+7, text=short, fill="white",
                                   font=("Segoe UI",7), tags=tag)
                _node_data[tag] = (d["name"], d["cm"])

            info.configure(text=(f"{len(all_members)} Matches · {len(edges)} Verbindungen ≥{min_edge} cM  "
                                 f"(Cluster 1–{min(len(clusters),20)} von {len(clusters)} gezeigt)"))

        def _on_node_hover(event):
            items = canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
            for item in items:
                tags = canvas.gettags(item)
                for t in tags:
                    if t.startswith("node_") and t in _node_data:
                        name, cm = _node_data[t]
                        canvas.itemconfig(item, outline="yellow", width=2)
                        info.configure(text=f"  {name}  ·  {cm:.0f} cM")
                        return

        canvas.bind("<Configure>", _draw)
        canvas.bind("<Motion>", _on_node_hover)
        ttk.Button(top, text="↻ Zeichnen", command=_draw).pack(side="left", padx=8)
        win.after(200, _draw)

    def _show_ancestor_groups(self):
        guid = self._current_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        groups = self._db.get_ancestor_groups(guid, min_matches=2)
        if not groups:
            messagebox.showinfo("Keine Daten",
                "Noch keine geteilten Vorfahren gefunden.\n"
                "Erst 'Vorfahren & Orte laden' ausführen.")
            return

        win = tk.Toplevel(self)
        win.title("Gemeinsame Vorfahren – Überlagerung")
        win.geometry("820x560")

        ttk.Label(win, text=(f"{len(groups)} Vorfahren werden von mehreren Matches "
                             f"geteilt – Klick zeigt die Matches:"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

        pane = ttk.PanedWindow(win, orient="vertical"); pane.pack(fill="both", expand=True, padx=10, pady=6)
        top = ttk.Frame(pane); pane.add(top, weight=3)
        bot = ttk.Frame(pane); pane.add(bot, weight=2)

        cols = ("anc","year","count")
        tv = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse")
        for c,(lbl,w) in {"anc":("Gemeinsamer Vorfahr",420),"year":("*Jahr",90),
                          "count":("# Matches",90)}.items():
            tv.heading(c, text=lbl); tv.column(c, width=w,
                       anchor=("center" if c!="anc" else "w"))
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(top, orient="vertical", command=tv.yview); sb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=sb.set)

        self._anc_groups = {}
        for g in groups:
            iid = tv.insert("", "end", values=(g["ancestor_name"], g["birth_year"], g["count"]))
            self._anc_groups[iid] = g

        ttk.Label(bot, text="Matches dieses Vorfahren:",
                  style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bot, height=8, wrap="word", font=("Segoe UI", 9))
        detail.pack(fill="both", expand=True)

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            g = self._anc_groups.get(sel[0])
            detail.delete("1.0","end")
            if not g: return
            detail.insert("end", f"{g['ancestor_name']}  (*{g['birth_year'] or '?'})  "
                                 f"– {g['count']} Matches:\n\n")
            for guid_m, name, path, cm in sorted(g["matches"], key=lambda x:-(x[3] or 0)):
                detail.insert("end", f"  • {name or guid_m[:8]}   "
                                     f"{cm:.0f} cM   Pfad: {path or '?'}\n")
        tv.bind("<<TreeviewSelect>>", on_sel)

    def _export_ancestor_groups(self):
        guid = self._current_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        groups = self._db.get_ancestor_groups(guid, min_matches=2)
        if not groups:
            messagebox.showinfo("Keine Daten", "Noch keine geteilten Vorfahren gefunden.")
            return
        path = filedialog.asksaveasfilename(
            title="Vorfahren-Gruppen speichern", defaultextension=".csv",
            filetypes=[("CSV","*.csv")])
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow(["Gemeinsamer Vorfahr","*Jahr","Anzahl Matches","Match","cM","Pfad"])
            for g in groups:
                for guid_m, name, pth, cm in sorted(g["matches"], key=lambda x:-(x[3] or 0)):
                    w.writerow([g["ancestor_name"], g["birth_year"], g["count"],
                                name or guid_m, f"{cm:.0f}" if cm else "", pth or ""])
        messagebox.showinfo("Export", f"{len(groups)} Vorfahren-Gruppen gespeichert.")
        self._set_status(f"Vorfahren-Gruppen exportiert: {len(groups)}")

    # ── Ahnentafel eines Matches ────────────────────────────────────────────────

    def _show_match_pedigree(self):
        if not self._selected_match:
            messagebox.showinfo("Kein Match", "Bitte zuerst einen Match in der Tabelle wählen.")
            return
        guid = self._selected_match.match_guid
        test_guid = self._current_guid()
        rows = self._db.get_pedigree_for_match(test_guid, guid)
        if not rows:
            messagebox.showinfo("Keine Ahnentafel",
                "Für diesen Match ist noch keine Ahnentafel geladen.\n"
                "Erst '▶ Ahnentafeln laden' ausführen (Match braucht einen Baum).")
            return

        # Gemeinsame Vorfahren (= wo der Match in DEINEM Baum hängt)
        common = self._db.get_ancestors_for_match(guid)

        win = tk.Toplevel(self)
        win.title(f"Ahnentafel – {self._selected_match.display_name}")
        win.geometry("800x600")
        ttk.Label(win, text=(f"{len(rows)} Vorfahren von "
                             f"{self._selected_match.display_name}:"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

        # ── Anknüpfungspunkt zu deinem Baum ─────────────────────────────────────
        if common:
            box = ttk.LabelFrame(win, text="🔗 Verbindung zu deinem Baum")
            box.pack(fill="x", padx=10, pady=(0,6))
            for a in common:
                yr = a.get("birth_year") or "?"
                mine = a.get("kinship_path_sample") or "?"
                rel = a.get("relationship_to_sample") or ""
                ttk.Label(box, text=(f"  • {a.get('ancestor_name','?')} (*{yr}) – "
                                     f"deine Linie: {mine}"
                                     + (f"  ({rel})" if rel else ""))).pack(anchor="w")
        else:
            ttk.Label(win, text="(Kein gemeinsamer Vorfahr geladen – ggf. "
                                "'▶ Vorfahren & Orte laden' ausführen.)",
                      foreground="#888888").pack(anchor="w", padx=12)

        # Namen+Jahr der gemeinsamen Vorfahren zum Markieren in der Tafel
        common_keys = set()
        for a in common:
            nm = (a.get("ancestor_name") or "").lower()
            common_keys.add((nm, (a.get("birth_year") or "")))

        cols = ("gen", "rel", "name", "birth", "death")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c,(lbl,w) in {"gen":("Gen.",45), "rel":("Linie",90),
                          "name":("Name",300), "birth":("* Geburt",150),
                          "death":("† Tod",150)}.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=("w" if c in ("name","birth","death") else "center"))
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=6)
        sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y", pady=6); tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("common", background="#fff3b0")  # gemeinsamer Vorfahr

        def _rel(path):
            if path == "":
                return "Match"
            return path  # z.B. FMF

        def _is_common(name, year):
            nl = name.lower()
            for cn, cy in common_keys:
                if not cn:
                    continue
                # Treffer wenn Nachname enthalten und Jahr passt (oder Jahr fehlt)
                if (nl in cn or cn in nl) and (not year or not cy or year == cy):
                    return True
            return False

        for r in rows:
            name = (f"{r['given_name']} {r['surname']}".strip()) or "(lebend/privat)"
            b = " ".join(x for x in (r["birth_date"] or r["birth_year"],
                                     r["birth_place"]) if x).strip()
            d = " ".join(x for x in (r["death_date"] or r["death_year"],
                                     r["death_place"]) if x).strip()
            tags = ("common",) if _is_common(name, r["birth_year"] or "") else ()
            tv.insert("", "end", values=(r["generation"], _rel(r["ahnen_path"]),
                                         name, b, d), tags=tags)

    def _show_pedigree_overlay(self):
        """Cluster: Vorfahren, die in mehreren Match-Ahnentafeln vorkommen."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Pedigree-Überlagerung – Cluster über alle Ahnentafeln")
        win.geometry("860x600")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="Gruppieren nach:", style="Bold.TLabel").pack(side="left")
        mode_var = tk.StringVar(value="person")
        for val, lbl in (("person","Person (Name+Jahr)"),
                         ("surname","Nachname (Sippe)"),
                         ("place","Geburtsort")):
            ttk.Radiobutton(top, text=lbl, value=val, variable=mode_var).pack(side="left", padx=6)
        ttk.Label(top, text="  ab").pack(side="left")
        minm_var = tk.StringVar(value="2")
        ttk.Spinbox(top, from_=2, to=99, width=4, textvariable=minm_var).pack(side="left", padx=4)
        ttk.Label(top, text="Matches").pack(side="left")

        info = ttk.Label(win, text="", style="Bold.TLabel")
        info.pack(anchor="w", padx=10, pady=(4,2))

        # Toolbar with namenskarte button (only active in surname mode)
        tb = ttk.Frame(win); tb.pack(fill="x", padx=10, pady=(0,2))

        pane = ttk.PanedWindow(win, orient="vertical"); pane.pack(fill="both", expand=True, padx=10, pady=4)
        tframe = ttk.Frame(pane); pane.add(tframe, weight=3)
        bframe = ttk.Frame(pane); pane.add(bframe, weight=2)

        cols = ("label","detail","count")
        tv = ttk.Treeview(tframe, columns=cols, show="headings", selectmode="browse")
        for c,(lbl,w) in {"label":("Vorfahr / Cluster",470),"detail":("Info",150),
                          "count":("# Matches",90)}.items():
            tv.heading(c, text=lbl); tv.column(c, width=w,
                       anchor=("center" if c=="count" else "w"))
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview); sb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=sb.set)

        ttk.Label(bframe, text="Matches dieses Clusters:",
                  style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bframe, height=8, wrap="word", font=("Segoe UI", 9))
        detail.pack(fill="both", expand=True)

        store = {}

        def _namenskarte_from_overlay():
            sel = tv.selection()
            if not sel:
                return
            g = store.get(sel[0])
            if not g:
                return
            if mode_var.get() == "surname":
                self._open_namenskarte(g["label"])
            else:
                # extract surname token from person name
                parts = g["label"].split()
                if parts:
                    self._open_namenskarte(parts[-1])

        ttk.Button(tb, text="🗺 Namenskarte.com",
                   command=_namenskarte_from_overlay).pack(side="left", padx=4)

        def reload(*_):
            try:
                mm = max(2, int(minm_var.get() or 2))
            except ValueError:
                mm = 2
            groups = self._db.get_pedigree_groups(test_guid, min_matches=mm,
                                                  mode=mode_var.get())
            tv.delete(*tv.get_children()); store.clear()
            for g in groups:
                iid = tv.insert("", "end", values=(g["label"], g["detail"], g["count"]))
                store[iid] = g
            info.configure(text=(f"{len(groups)} Cluster werden von ≥{mm} Matches geteilt."
                                 if groups else
                                 "Keine Überlagerung gefunden – erst '▶ Ahnentafeln laden' ausführen."))
        mode_var.trace_add("write", reload)
        minm_var.trace_add("write", reload)

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            g = store.get(sel[0]); detail.delete("1.0","end")
            if not g: return
            detail.insert("end", f"{g['label']} {g['detail']} – {g['count']} Matches:\n\n")
            for guid_m, name, path, gen, cm in sorted(g["matches"], key=lambda x:-(x[4] or 0)):
                detail.insert("end", f"  • {name or guid_m[:8]}   "
                                     f"{(cm or 0):.0f} cM   (Gen {gen}, Linie {path or '?'})\n")
        tv.bind("<<TreeviewSelect>>", on_sel)
        tv.bind("<Double-1>", lambda _: _namenskarte_from_overlay())
        reload()

    def _show_shared_clusters(self):
        """Triangulations-Cluster aus den Shared Matches (Connected Components)."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Shared-Cluster – Triangulationsgruppen")
        win.geometry("820x600")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="cM-Fenster:", style="Bold.TLabel").pack(side="left")
        lo_var = tk.StringVar(value="20"); hi_var = tk.StringVar(value="400")
        ttk.Entry(top, textvariable=lo_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="bis").pack(side="left")
        ttk.Entry(top, textvariable=hi_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="cM   (sehr enge/weite Matches verbinden alles)").pack(side="left")

        info = ttk.Label(win, text="", style="Bold.TLabel")
        info.pack(anchor="w", padx=10, pady=(4,2))

        pane = ttk.PanedWindow(win, orient="vertical"); pane.pack(fill="both", expand=True, padx=10, pady=6)
        tframe = ttk.Frame(pane); pane.add(tframe, weight=2)
        bframe = ttk.Frame(pane); pane.add(bframe, weight=3)

        tv = ttk.Treeview(tframe, columns=("cluster","size","dens","conf"),
                          show="headings", selectmode="browse")
        for col,(lbl,w) in {"cluster":("Cluster",100),"size":("Mitglieder",80),
                            "dens":("Dichte",70),"conf":("Echt-Güte",110)}.items():
            tv.heading(col, text=lbl); tv.column(col, width=w, anchor="center")
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview); sb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=sb.set)

        ttk.Label(bframe, text="Mitglieder des Clusters:", style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bframe, height=10, wrap="word", font=("Segoe UI", 9))
        detail.pack(fill="both", expand=True)

        store = {}
        def reload(*_):
            try:
                lo = float(lo_var.get() or 0); hi = float(hi_var.get() or 9999)
            except ValueError:
                lo, hi = 20.0, 400.0
            from core.treematch import cluster_confidence
            clusters = self._db.get_shared_clusters(test_guid, lo, hi)
            tv.delete(*tv.get_children()); store.clear()
            for i, c in enumerate(clusters, 1):
                conf = cluster_confidence(c["size"], c.get("density", 0),
                                          c.get("median_cm", 0),
                                          endogamy_score=c.get("endogamy", 0),
                                          n_confirmed=c.get("n_thrulines", 0)
                                                      + c.get("n_linked", 0))
                c["_conf"] = conf
                iid = tv.insert("", "end", values=(
                    f"Cluster {i}", c["size"], f"{c.get('density',0):.2f}",
                    f"{conf['realness']*100:.0f}% ({conf['label']})"))
                store[iid] = c
            info.configure(text=(f"{len(clusters)} Cluster gefunden "
                                 f"({lo:.0f}–{hi:.0f} cM)." if clusters else
                                 "Keine Cluster – erst Shared Matches laden (Schritt B)."))
        ttk.Button(top, text="↻", width=3, command=reload).pack(side="left", padx=8)

        def dock_in_tree():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo("Kein Cluster", "Bitte einen Cluster wählen.")
                return
            c = store.get(sel[0])
            if not c:
                return
            guids = [g for g, _n, _cm in c["members"]]

            def _after_load(ged):
                import threading
                from core.treematch import Person
                index, amap = ged["index"], ged["amap"]

                def _worker():
                    # Jedes Cluster-Mitglied einzeln gegen den eigenen Baum matchen.
                    # Aggregiert nach Person in DEINEM Baum: wie viele Mitglieder
                    # treffen sie? (Schreibvarianten egal – dein Baum ist Referenz.)
                    agg = {}      # own.ref -> {"own","members":set,"best":score}
                    n_with_ped = 0
                    for guid in guids:
                        rows = self._db.get_pedigree_for_match(test_guid, guid)
                        rows = [r for r in rows if (r["generation"] or 0) >= 2]
                        if rows:
                            n_with_ped += 1
                        seen = set()
                        for r in rows:
                            q = Person(r["given_name"], r["surname"],
                                       r["birth_year"], r["birth_place"])
                            if not q.stoks:
                                continue
                            own, score = index.best_match(q, min_score=0.6)
                            if not own or own.ref in seen:
                                continue
                            seen.add(own.ref)
                            e = agg.setdefault(own.ref,
                                {"own": own, "members": set(), "best": 0.0})
                            e["members"].add(guid)
                            e["best"] = max(e["best"], score)
                    hits = []
                    for ref, e in agg.items():
                        path = amap.get(ref)
                        hits.append((len(e["members"]), e["best"],
                                     e["own"].display, e["own"], path))
                    # Direktlinie + von meisten Mitgliedern geteilt + jüngster zuerst
                    hits.sort(key=lambda h: (h[4] is None,
                                             len(h[4]) if h[4] else 99,
                                             -h[0], -h[1]))
                    self.after(0, lambda: self._show_cluster_dock(c, hits, n_with_ped))

                threading.Thread(target=_worker, daemon=True,
                                 name="cluster-dock").start()

            self._set_status("Suche Cluster-Linie in deinem Baum …")
            self._ensure_gedcom_loaded(_after_load)

        ttk.Button(top, text="🔗 Cluster-Linie in meinem Baum suchen",
                   command=dock_in_tree).pack(side="left", padx=8)

        def deepen_cluster():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo("Kein Cluster", "Bitte einen Cluster wählen.")
                return
            c = store.get(sel[0])
            if not c:
                return
            guids = [g for g, _n, _cm in c["members"]]
            if not messagebox.askyesno(
                    "Cluster tiefer laden",
                    f"Für {len(guids)} Cluster-Matches tiefere Ahnentafeln "
                    f"(bis 8 Generationen) laden?\n\n"
                    "Nötig für entfernte Cousins (gemeinsamer Vorfahr >5 Gen.).\n"
                    "Dauert etwas (mehrere Calls pro Match)."):
                return
            if not self._client:
                messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
                return
            self._scraper = Scraper(self._client, self._db,
                                    on_progress=self._on_progress,
                                    on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                    on_done=lambda r: self.after(0, lambda: messagebox.showinfo(
                                        "Tiefe Ahnentafeln", r.message + "\n\nJetzt erneut "
                                        "'Cluster-Linie suchen'.")))
            self._scraper.start_deepen_pedigrees(test_guid, guids)

        ttk.Button(top, text="⤓ Cluster tiefer laden (8 Gen.)",
                   command=deepen_cluster).pack(side="left", padx=4)

        def combined_tree():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo("Kein Cluster", "Bitte einen Cluster wählen.")
                return
            c = store.get(sel[0])
            if not c:
                return
            self._build_cluster_tree(test_guid, c)

        ttk.Button(top, text="🌳 Cluster-Stammbaum kombinieren",
                   command=combined_tree).pack(side="left", padx=4)

        def internal_rels():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo("Kein Cluster", "Bitte einen Cluster wählen.")
                return
            c = store.get(sel[0])
            if not c:
                return
            self._show_cluster_relationships(test_guid, c)

        ttk.Button(top, text="👥 Beziehungen im Cluster",
                   command=internal_rels).pack(side="left", padx=4)

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            c = store.get(sel[0]); detail.delete("1.0","end")
            if not c: return
            guids = [g for g, _n, _cm in c["members"]]
            conf = c.get("_conf", {})
            detail.insert("end",
                f"Echt-Güte: {conf.get('realness',0)*100:.0f}% "
                f"({conf.get('label','?')}) · Dichte {c.get('density',0):.2f} "
                f"({c.get('edges',0)} Verbindungen) · Median {c.get('median_cm',0):.0f} cM, "
                f"{c.get('median_segments',0)} Segm., längstes {c.get('median_longest',0):.0f} cM\n")
            nt, nl = c.get("n_thrulines", 0), c.get("n_linked", 0)
            if nt or nl:
                detail.insert("end",
                    f"✓ Bestätigt: {nt} mit ThruLine, {nl} in deinem Baum verknüpft "
                    f"→ Linie zu dir belegt\n")
            if conf.get("note"):
                detail.insert("end", f"⚠ {conf['note']}\n")
            detail.insert("end", f"\n{c['size']} Matches in dieser Gruppe "
                                 f"(wahrscheinlich gemeinsame Ahnenlinie):\n")
            seg = c.get("seg_by_member", {})
            for guid, name, cm in c["members"]:
                s, lg = seg.get(guid, (0, 0))
                detail.insert("end", f"  • {name or guid[:8]}   {(cm or 0):.0f} cM"
                                     f"  ({s} Segm., längstes {lg:.0f})\n")

            # Gemeinsame Vorfahren-Linien INNERHALB des Clusters – das ist die
            # belastbare Linie, die bei dir andocken muss.
            detail.insert("end", "\n── Gemeinsame Vorfahren im Cluster "
                                 "(von ≥2 Mitgliedern geteilt) ──\n")
            found = False
            for mode, titel in (("person", "Personen"), ("surname", "Nachnamen"),
                                ("place", "Orte")):
                groups = self._db.get_pedigree_groups(
                    test_guid, min_matches=2, mode=mode, only_guids=guids)
                if not groups:
                    continue
                found = True
                detail.insert("end", f"\n{titel}:\n")
                for g in groups[:12]:
                    detail.insert("end", f"  • {g['label']} {g['detail']}"
                                         f"  ({g['count']}/{c['size']} Matches)\n")
            if not found:
                detail.insert("end", "  (keine geteilten Vorfahren – ggf. erst "
                                     "Ahnentafeln für diese Matches laden)\n")
        tv.bind("<<TreeviewSelect>>", on_sel)
        reload()

    def _build_cluster_tree(self, test_guid, cluster):
        """Verschmilzt die Ahnentafeln aller Cluster-Mitglieder zu einem
        kombinierten Cluster-Stammbaum und zeigt Konvergenz + Andockpunkt."""
        import threading
        from core.treematch import Person, merge_person_list, render_kinship
        guids = [g for g, _n, _cm in cluster["members"]]
        cm_by_member = {g: cm for g, _n, cm in cluster["members"]}
        name_by_member = {g: n for g, n, _cm in cluster["members"]}
        ged = getattr(self, "_gedcom", None)
        self._set_status("Kombiniere Cluster-Stammbaum …")

        def _worker():
            persons = []
            member_rows = {}   # guid -> {ahnen_path: row}  (für Eltern-Lookup)
            n_with_ped = 0
            for guid in guids:
                rows = [r for r in self._db.get_pedigree_for_match(test_guid, guid)
                        if (r["generation"] or 0) >= 2]
                if rows:
                    n_with_ped += 1
                member_rows[guid] = {r["ahnen_path"]: r for r in rows}
                for r in rows:
                    p = Person(r["given_name"], r["surname"],
                               r["birth_year"], r["birth_place"],
                               ref=(guid, r["generation"], r["ahnen_path"]),
                               bdate=r["birth_date"])
                    if p.stoks:
                        persons.append(p)
            groups = merge_person_list(persons)

            def _parents_of(group):
                """Verschmolzene Vater/Mutter eines Vorfahren-Clusters (über alle
                Mitglieder, in denen er vorkommt)."""
                fa, mo = [], []
                for it in group["items"]:
                    g, _gen, path = it.ref
                    rowmap = member_rows.get(g, {})
                    fr = rowmap.get((path or "") + "F")
                    mr = rowmap.get((path or "") + "M")
                    if fr:
                        fa.append(Person(fr["given_name"], fr["surname"],
                                  fr["birth_year"], fr["birth_place"], bdate=fr["birth_date"]))
                    if mr:
                        mo.append(Person(mr["given_name"], mr["surname"],
                                  mr["birth_year"], mr["birth_place"], bdate=mr["birth_date"]))
                def _rep(lst):
                    if not lst:
                        return None
                    grp = merge_person_list(lst)
                    grp.sort(key=lambda x: -len(x["items"]))
                    return grp[0]["rep"]
                return _rep(fa), _rep(mo)

            index = ged["index"] if ged else None
            amap = ged["amap"] if ged else {}
            rows_out = []
            for grp in groups:
                members = {it.ref[0] for it in grp["items"]}
                gen = min(it.ref[1] for it in grp["items"])
                rep = grp["rep"]
                own = path = None
                via = False
                score = 0.0
                if index:
                    own, score = index.best_match(rep, min_score=0.6)
                    if own:
                        path = amap.get(own.ref)
                        if path is None:   # Seitenverwandter → zur direkten Linie hoch
                            from core.treematch import mrca_on_direct_line
                            _mid, mpath = mrca_on_direct_line(
                                own.ref, ged.get("individuals", {}),
                                ged.get("families", {}), amap)
                            if mpath is not None:
                                path, via = mpath, True
                father, mother = _parents_of(grp)
                rows_out.append({
                    "rep": rep, "members": members, "gen": gen,
                    "own": own, "path": path, "via": via, "score": score,
                    "father": father, "mother": mother,
                    "cms": sorted((cm_by_member.get(m, 0) for m in members),
                                  reverse=True),
                })
            # Konvergenz zuerst: von vielen geteilt, dann jüngste Generation
            rows_out.sort(key=lambda r: (-len(r["members"]), r["gen"]))
            self.after(0, lambda: self._show_cluster_tree_win(
                cluster, rows_out, n_with_ped, bool(ged), name_by_member))

        threading.Thread(target=_worker, daemon=True, name="cluster-tree").start()

    def _show_cluster_tree_win(self, cluster, rows, n_with_ped, has_ged, name_by_member):
        from core.treematch import render_kinship, cm_to_mrca
        win = tk.Toplevel(self)
        win.title("Kombinierter Cluster-Stammbaum")
        win.geometry("960x640")
        size = cluster["size"]
        shared = [r for r in rows if len(r["members"]) >= 2]
        ttk.Label(win, text=(f"Cluster: {size} Matches ({n_with_ped} mit Ahnentafel) · "
                             f"{len(rows)} Personen verschmolzen · "
                             f"{len(shared)} von ≥2 Mitgliedern geteilt"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,2))

        # cM-basierte Erwartung, wie tief der gemeinsame Vorfahr liegt
        cms = sorted((cm for _g, _n, cm in cluster["members"] if cm), reverse=True)
        if cms:
            lbl_close, gen_close = cm_to_mrca(cms[0])     # nächstes Mitglied
            lbl_far,   gen_far   = cm_to_mrca(cms[-1])    # entferntestes
            ttk.Label(win, text=(
                f"cM-Schätzung: gem. Vorfahr ~Gen {gen_close}"
                + (f"–{gen_far}" if gen_far != gen_close else "")
                + f"  (nächstes Mitglied {cms[0]:.0f} cM = {lbl_close}; "
                f"entferntestes {cms[-1]:.0f} cM = {lbl_far}).  "
                "⚠ Endogamie → cM überhöht, echter Vorfahr eher tiefer."),
                foreground="#555").pack(anchor="w", padx=10, pady=(0,2))

        # ── Confidence (Echtheit × Konvergenz) ─────────────────────────────────
        from core.treematch import cluster_confidence
        conv_frac = (max((len(r["members"]) for r in rows), default=0)
                     / n_with_ped) if n_with_ped else 0.0
        conf = cluster_confidence(size, cluster.get("density", 0),
                                  cluster.get("median_cm", 0), conv_frac,
                                  endogamy_score=cluster.get("endogamy", 0),
                                  n_confirmed=cluster.get("n_thrulines", 0)
                                              + cluster.get("n_linked", 0))
        ttk.Label(win, text=(
            f"Bewertung: Cluster echt ~{conf['realness']*100:.0f}% ({conf['label']}, "
            f"Dichte {cluster.get('density',0):.2f}) · "
            f"Pedigree-Konvergenz {conv_frac*100:.0f}% "
            f"(max. {max((len(r['members']) for r in rows), default=0)}/{n_with_ped} "
            f"auf einen Vorfahren)"
            + (f"  ⚠ {conf['note']}" if conf['note'] else "")),
            foreground="#333", style="Bold.TLabel").pack(anchor="w", padx=10, pady=(0,4))

        def _birth(rep):
            d = rep.bdate or (str(rep.year) if rep.year else "")
            return " · ".join(x for x in (d, rep.place) if x)

        # ── Vorhersage: gemeinsamer Vorfahr des Clusters (MRCA) ─────────────────
        box = ttk.LabelFrame(win, text="🔮 Vorhergesagter gemeinsamer Vorfahr des Clusters")
        box.pack(fill="x", padx=10, pady=(2,6))
        # bevorzugt Treffer auf deiner direkten Linie (jüngster, meist geteilt);
        # sonst der am häufigsten geteilte verschmolzene Vorfahr.
        direct = sorted([r for r in shared if r["path"] is not None],
                        key=lambda r: (len(r["path"]), -len(r["members"])))
        pred = direct[0] if direct else (shared[0] if shared else (rows[0] if rows else None))
        if not pred:
            ttk.Label(box, text="Zu wenig Daten – Ahnentafeln der Mitglieder laden.",
                      foreground="#a05a00").pack(anchor="w", padx=8, pady=4)
        else:
            rep = pred["rep"]
            ttk.Label(box, text=f"{rep.display}   ({_birth(rep) or 'kein Datum/Ort'})",
                      style="Bold.TLabel").pack(anchor="w", padx=8, pady=(4,0))
            ttk.Label(box, text=f"geteilt von {len(pred['members'])}/{size} "
                      f"Mitgliedern · Generation {pred['gen']}").pack(anchor="w", padx=8)
            if pred["path"] is not None:
                via_txt = (f"über Seitenlinie {pred['own'].display} → "
                           if pred.get("via") else "")
                ttk.Label(box, text=(f"✓ Andockpunkt in deinem Baum: {via_txt}"
                          f"deine Linie: {render_kinship(pred['path'])}"),
                          foreground=COLORS.get("primary","#1b5e20"),
                          style="Bold.TLabel").pack(anchor="w", padx=8, pady=(0,4))
            elif pred["own"] is not None:
                ttk.Label(box, text=(f"In deinem Baum als Seitenlinie: "
                          f"{pred['own'].display} (nicht direkte Ahnenlinie)"),
                          foreground="#a05a00").pack(anchor="w", padx=8, pady=(0,4))
            else:
                ttk.Label(box, text=("❗ NICHT in deinem Baum → Forschungsziel: "
                          "diese Person suchen/eintragen, dann liefert Ancestry "
                          "ThruLines-Hints für den ganzen Cluster."),
                          foreground="#b00020", style="Bold.TLabel"
                          ).pack(anchor="w", padx=8, pady=(0,4))
            # Eltern des vorhergesagten Vorfahren (zum Verifizieren/Verlängern)
            fa, mo = pred.get("father"), pred.get("mother")
            if fa or mo:
                ft = f"Vater: {fa.display} ({_birth(fa) or '?'})" if fa else "Vater: ?"
                mt = f"Mutter: {mo.display} ({_birth(mo) or '?'})" if mo else "Mutter: ?"
                ttk.Label(box, text=f"   └ {ft}   |   {mt}",
                          foreground="#444").pack(anchor="w", padx=8, pady=(0,4))
            # Namenskarte buttons for predicted ancestor's surnames
            if pred:
                rep = pred["rep"]
                btn_frame = ttk.Frame(box); btn_frame.pack(anchor="w", padx=8, pady=(0,4))
                surnames = {s for s in [
                    getattr(rep, "surname", None),
                    getattr(fa, "surname", None) if pred.get("father") else None,
                    getattr(mo, "surname", None) if pred.get("mother") else None,
                ] if s}
                for sur in list(surnames)[:4]:
                    ttk.Button(btn_frame, text=f"🗺 {sur}",
                               command=lambda s=sur: self._open_namenskarte(s)
                               ).pack(side="left", padx=2)
        if not has_ged:
            ttk.Label(win, text="(GEDCOM nicht geladen → ohne Andock-Spalte. "
                      "Über 'Cluster-Linie in meinem Baum suchen' wird der Baum geladen.)",
                      foreground="#888").pack(anchor="w", padx=10)

        cols = ("person","shared","gen","cms","dock")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c,(lbl,w) in {"person":("Vorfahr (verschmolzen)",300),
                          "shared":("geteilt von",90),"gen":("Gen",50),
                          "cms":("cM der Mitglieder",150),
                          "dock":("= in deinem Baum (Sosa)",260)}.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=("center" if c in ("shared","gen") else "w"))
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=6)
        sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y", pady=6); tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("shared", background="#fff3b0")   # Konvergenz
        tv.tag_configure("dock", background="#d8f0d8")      # dockt direkt an

        row_reps = {}
        for r in rows:
            rep = r["rep"]
            indent = "  " * max(0, r["gen"] - 2)
            bd = rep.bdate or (str(rep.year) if rep.year else "")
            binfo = " · ".join(x for x in (bd, rep.place) if x)
            disp = f"{indent}{rep.display}" + (f"  (*{binfo})" if binfo else "")
            nshare = len(r["members"])
            dock = ""
            if r["path"] is not None:
                dock = f"{r['own'].display} – {render_kinship(r['path'])}"
            elif r["own"] is not None:
                dock = f"{r['own'].display} (Seitenlinie)"
            cms = ", ".join(f"{c:.0f}" for c in r["cms"][:6])
            tag = ("dock",) if r["path"] is not None else \
                  (("shared",) if nshare >= 2 else ())
            iid = tv.insert("", "end", tags=tag, values=(
                disp, f"{nshare}/{size}", r["gen"], cms, dock))
            row_reps[iid] = rep

        # Namenskarte button below treeview
        nk_frame = ttk.Frame(win); nk_frame.pack(anchor="w", padx=10, pady=(0,4), side="bottom")
        nk_lbl = ttk.Label(nk_frame, text="Ausgewählter Vorfahr → Namenskarte:",
                           foreground="#555")
        nk_lbl.pack(side="left")
        nk_btn = ttk.Button(nk_frame, text="🗺 Namenskarte.com",
                            state="disabled",
                            command=lambda: None)
        nk_btn.pack(side="left", padx=6)

        def _on_tree_sel(_):
            sel = tv.selection()
            if not sel: return
            rep = row_reps.get(sel[0])
            if not rep: return
            sur = getattr(rep, "surname", None) or rep.display.split()[-1]
            nk_btn.configure(state="normal",
                             command=lambda s=sur: self._open_namenskarte(s))

        tv.bind("<<TreeviewSelect>>", _on_tree_sel)

    def _show_cluster_relationships(self, test_guid, cluster):
        """Interne Beziehungs-Struktur: paarweise cM zwischen Cluster-Mitgliedern
        → wer ist mit wem wie verwandt (Eltern/Kind, Geschwister, Cousin …)."""
        from core.treematch import pair_relationship
        guids = [g for g, _n, _cm in cluster["members"]]
        name = {g: n for g, n, _cm in cluster["members"]}
        pairs = self._db.get_pairwise_shared(test_guid, guids)

        win = tk.Toplevel(self)
        win.title("Beziehungen im Cluster (interne Struktur)")
        win.geometry("760x540")
        ttk.Label(win, text=(f"{cluster['size']} Mitglieder · {len(pairs)} bekannte "
                             f"Paar-Beziehungen (aus geteilten cM untereinander):"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,2))
        ttk.Label(win, text="Hohe cM = nah (Eltern/Kind, Geschwister) → engere "
                  "Teil-Familien im Cluster. Hilft, die Struktur zu rekonstruieren.",
                  foreground="#555").pack(anchor="w", padx=10, pady=(0,4))

        if not pairs:
            ttk.Label(win, text="Keine paarweisen cM gespeichert. Dafür müssen die "
                      "Shared Matches der Mitglieder geladen sein (Schritt B).",
                      foreground="#a05a00").pack(anchor="w", padx=10, pady=8)
            return

        cols = ("a","b","cm","rel")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c,(lbl,w) in {"a":("Match A",200),"b":("Match B",200),
                          "cm":("cM A↔B",80),"rel":("Beziehung",230)}.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=("center" if c=="cm" else "w"))
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=6)
        sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y", pady=6); tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("close", background="#d8f0d8")

        for a, b, cm in pairs:
            tag = ("close",) if cm >= 200 else ()
            tv.insert("", "end", tags=tag, values=(
                name.get(a, a[:8]), name.get(b, b[:8]),
                f"{cm:.0f}", pair_relationship(cm)))

    def _show_cluster_dock(self, cluster, hits, n_with_ped):
        """Zeigt, wo die Cluster-Mitglieder in deinem Baum andocken.
        hits: [(member_count, best_score, own_display, own_person, self_path)]."""
        from core.treematch import render_kinship
        win = tk.Toplevel(self)
        win.title("Cluster-Linie → Andockpunkt in deinem Baum")
        win.geometry("840x540")
        ttk.Label(win, text=(f"Cluster mit {cluster['size']} Matches "
                             f"({n_with_ped} mit Ahnentafel) – Treffer in deinem Baum:"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

        direct = [h for h in hits if h[4] is not None]
        if direct:
            best = direct[0]
            ttk.Label(win, text=(f"➡  Wahrscheinlicher Andockpunkt: {best[2]}  "
                                 f"({render_kinship(best[4])}) – von {best[0]} "
                                 f"Mitglied(ern) getroffen"),
                      style="Bold.TLabel", foreground=COLORS.get("primary","#1b5e20")
                      ).pack(anchor="w", padx=10, pady=(0,6))
        elif hits:
            ttk.Label(win, text=("Kein Treffer auf deiner direkten Ahnenlinie – "
                                 "untenstehende sind Seitenlinien/Vorschläge."),
                      foreground="#a05a00").pack(anchor="w", padx=10, pady=(0,6))
        else:
            ttk.Label(win, text=("Keine Treffer im Baum. Mögliche Gründe: Cluster-"
                                 "Mitglieder haben (noch) keine Ahnentafel geladen, "
                                 "oder die Linie liegt tiefer → ‚Cluster tiefer laden'."),
                      foreground="#a05a00").pack(anchor="w", padx=10, pady=(0,6))

        cols = ("count","line","anchor","score")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c,(lbl,w) in {"count":("getroffen von",110),
                          "line":("Deine Linie",230),
                          "anchor":("Person in deinem Baum",230),
                          "score":("Sicherheit",80)}.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=("center" if c in ("count","score") else "w"))
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=6)
        sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y", pady=6); tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("direct", background="#d8f0d8")

        for count, score, owndisp, own, path in hits:
            kin = render_kinship(path) if path is not None else "— (Seitenlinie)"
            tag = ("direct",) if path is not None else ()
            tv.insert("", "end", tags=tag, values=(
                f"{count}/{cluster['size']}", kin, owndisp, f"{score:.2f}"))

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
        import json, os
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_ui_settings(self, **kw):
        import json
        s = self._load_ui_settings(); s.update(kw)
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
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
                self.after(0, lambda: messagebox.showerror(
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

        tv.tag_configure("strong",  background="#d8f0d8")
        tv.tag_configure("newlead", background="#fde9c8")
        clr = COLORS["cluster"]
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
                    tag = (f"cl{cid}",)
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

    def _stop_download(self):
        if self._scraper:
            self._scraper.stop()
        self._stop_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="disabled")

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._pause_sv.set(self._t("dl.resume"))
            self._set_status("⏸ Download pausiert.")
        else:
            self._pause_event.set()
            self._pause_sv.set(self._t("dl.pause"))
            self._set_status("▶ Download fortgesetzt.")

    def _on_progress(self, fetched, total, label):
        import time
        pct = min(100.0, (fetched / max(total, 1)) * 100)
        if self._dl_t0 == 0.0:
            self._dl_t0 = time.monotonic()
        elapsed = time.monotonic() - self._dl_t0
        remaining = fetched and elapsed and (elapsed / fetched * max(total - fetched, 0))
        if remaining and remaining < 3600 * 5:
            mins, secs = divmod(int(remaining), 60)
            eta_txt = f"~{mins}m {secs:02d}s"
        else:
            eta_txt = ""
        # Update tree counter from DB
        try:
            tg = self._current_test_guid or self._get_kit_guid()
            if tg:
                self._dl_counters["matches"] = self._db.get_match_count(tg)
                with self._db._cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM matches WHERE test_guid=? AND has_tree=1", (tg,))
                    self._dl_counters["trees"] = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM shared_matches WHERE test_guid=?", (tg,))
                    self._dl_counters["shared"] = cur.fetchone()[0]
        except Exception:
            pass
        def _u():
            self._progress_var.set(pct)
            self._progress_lbl.set(f"{fetched} / ~{total}  –  {label[:45]}")
            self._eta_var.set(eta_txt)
            if hasattr(self, "_dash_vars"):
                self._dash_vars.get("mat_") or None
                for k, sv in [
                    ("mat",  str(self._dl_counters["matches"])),
                    ("tree", str(self._dl_counters["trees"])),
                    ("sh",   str(self._dl_counters["shared"])),
                    ("err",  str(self._dl_counters["errors"])),
                ]:
                    if k in self._dash_vars:
                        self._dash_vars[k].set(sv)
        self.after(0, _u)

    def _on_done(self, result: DownloadResult):
        def _u():
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._pause_btn.configure(state="disabled")
            self._pause_sv.set(self._t("dl.pause"))
            self._eta_var.set("")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._refresh_match_table()
            self._refresh_stats()
            if result.success:
                messagebox.showinfo("Fertig", result.message)
        self.after(0, _u)

    def _on_shared_done(self, result: DownloadResult):
        def _u():
            self._shared_start_btn.configure(state="normal")
            self._shared_stop_btn.configure(state="disabled")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._refresh_stats()
            if result.success:
                messagebox.showinfo("Shared Matches fertig", result.message)
        self.after(0, _u)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3: MATCHES
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_matches(self):
        f = self._tab_matches

        # Kit-Leiste
        kl = ttk.Frame(f); kl.pack(fill="x", padx=10, pady=(6, 0))
        _sv_kit = tk.StringVar(value=self._t("mf.kit"))
        ttk.Label(kl, textvariable=_sv_kit, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self._lang_widgets.append((_sv_kit, "mf.kit"))
        self._matches_kit_var = tk.StringVar()
        self._matches_kit_combo = ttk.Combobox(
            kl, textvariable=self._matches_kit_var, width=38, state="readonly")
        self._matches_kit_combo.pack(side="left")
        self._matches_kit_combo.bind(
            "<<ComboboxSelected>>", lambda _: self._refresh_match_table())
        _sv_sides = tk.StringVar(value=self._t("mf.sides"))
        ttk.Button(kl, textvariable=_sv_sides,
                   command=self._auto_assign_sides).pack(side="left", padx=(12, 0))
        self._lang_widgets.append((_sv_sides, "mf.sides"))
        ttk.Button(kl, text="⚡ GEDmatch-Brücke",
                   command=self._run_gedmatch_bridge).pack(side="left", padx=(8, 0))

        # Filter-Leiste
        fl = ttk.Frame(f); fl.pack(fill="x", padx=10, pady=6)
        _sv_s = tk.StringVar(value=self._t("mf.search"))
        ttk.Label(fl, textvariable=_sv_s).pack(side="left", padx=(0,4))
        self._lang_widgets.append((_sv_s, "mf.search"))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_match_table())
        ttk.Entry(fl, textvariable=self._search_var, width=20).pack(side="left")

        _sv_r = tk.StringVar(value=self._t("mf.rel"))
        ttk.Label(fl, textvariable=_sv_r).pack(side="left", padx=(10,4))
        self._lang_widgets.append((_sv_r, "mf.rel"))
        self._rel_var = tk.StringVar(value="(alle)")
        self._rel_combo = ttk.Combobox(fl, textvariable=self._rel_var, width=22, state="readonly")
        self._rel_combo.pack(side="left")
        self._rel_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_match_table())

        _sv_c = tk.StringVar(value=self._t("mf.mincm"))
        ttk.Label(fl, textvariable=_sv_c).pack(side="left", padx=(10,4))
        self._lang_widgets.append((_sv_c, "mf.mincm"))
        self._min_cm_var = tk.StringVar(value="0")
        ttk.Entry(fl, textvariable=self._min_cm_var, width=6).pack(side="left")
        ttk.Button(fl, text="↩", width=3, command=self._refresh_match_table).pack(side="left", padx=2)

        self._starred_var = tk.BooleanVar()
        _sv_starred = tk.StringVar(value=self._t("mf.starred"))
        ttk.Checkbutton(fl, textvariable=_sv_starred, variable=self._starred_var,
                        command=self._refresh_match_table).pack(side="left", padx=(10,0))
        self._lang_widgets.append((_sv_starred, "mf.starred"))
        self._tree_var = tk.BooleanVar()
        _sv_tree = tk.StringVar(value=self._t("mf.tree"))
        ttk.Checkbutton(fl, textvariable=_sv_tree, variable=self._tree_var,
                        command=self._refresh_match_table).pack(side="left", padx=6)
        self._lang_widgets.append((_sv_tree, "mf.tree"))
        self._hide_endo_var = tk.BooleanVar()
        _sv_endo = tk.StringVar(value=self._t("mf.endo"))
        ttk.Checkbutton(fl, textvariable=_sv_endo, variable=self._hide_endo_var,
                        command=self._refresh_match_table).pack(side="left", padx=6)
        self._lang_widgets.append((_sv_endo, "mf.endo"))

        self._match_count_var = tk.StringVar(value="")
        ttk.Label(fl, textvariable=self._match_count_var,
                  foreground=COLORS["primary"]).pack(side="right", padx=8)
        ttk.Button(fl, text="↻", command=self._refresh_match_table).pack(side="right", padx=4)

        # Schnellfilter-Chips
        cf = ttk.Frame(f); cf.pack(fill="x", padx=10, pady=(0, 4))
        self._chip_vars: dict[str, tk.BooleanVar] = {}
        chip_defs = [
            ("star",  "mf.chip_star",  self._chip_starred),
            ("tree",  "mf.chip_tree",  self._chip_tree),
            ("cm200", "mf.chip_200",   self._chip_cm200),
            ("pat",   "mf.chip_pat",   self._chip_pat),
            ("mat",   "mf.chip_mat",   self._chip_mat),
        ]
        self._chip_btns: dict[str, tk.Button] = {}
        self._chip_t_keys: dict[str, str] = {}
        for key, t_key, cmd in chip_defs:
            var = tk.BooleanVar(value=False)
            self._chip_vars[key] = var
            btn = tk.Button(
                cf, text=self._t(t_key),
                font=("Segoe UI", 9), relief="flat", bd=1,
                bg=COLORS["light"], fg=COLORS["text"],
                activebackground=COLORS["primary"], activeforeground=COLORS["white"],
                cursor="hand2", padx=10, pady=3,
                command=lambda k=key, c=cmd: self._toggle_chip(k, c),
            )
            btn.pack(side="left", padx=3)
            self._chip_btns[key] = btn
            self._chip_t_keys[key] = t_key
            self._lang_widgets.append((btn, t_key))

        # Haupt-Pane
        pane = ttk.PanedWindow(f, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=4)

        left = ttk.Frame(pane); pane.add(left, weight=3)
        right = ttk.Frame(pane); pane.add(right, weight=2)

        self._build_match_tree(left)
        self._build_detail_panel(right)

    def _chip_starred(self):
        self._starred_var.set(self._chip_vars["star"].get())
        self._refresh_match_table()

    def _chip_tree(self):
        self._tree_var.set(self._chip_vars["tree"].get())
        self._refresh_match_table()

    def _chip_cm200(self):
        self._min_cm_var.set("200" if self._chip_vars["cm200"].get() else "0")
        self._refresh_match_table()

    def _chip_pat(self):
        if self._chip_vars["pat"].get():
            self._chip_vars["mat"].set(False)
            self._chip_btns["mat"].configure(bg=COLORS["light"], fg=COLORS["text"])
        self._refresh_match_table()

    def _chip_mat(self):
        if self._chip_vars["mat"].get():
            self._chip_vars["pat"].set(False)
            self._chip_btns["pat"].configure(bg=COLORS["light"], fg=COLORS["text"])
        self._refresh_match_table()

    def _toggle_chip(self, key: str, cmd):
        new_val = not self._chip_vars[key].get()
        self._chip_vars[key].set(new_val)
        btn = self._chip_btns[key]
        if new_val:
            btn.configure(bg=COLORS["primary"], fg=COLORS["white"])
        else:
            btn.configure(bg=COLORS["light"], fg=COLORS["text"])
        cmd()

    def _build_match_tree(self, parent):
        cols = ("name","guid","note","cm","seg","rel","tree","ged","ca","starred")
        self._tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        for col, (key, width, anchor) in {
            "name"   : ("m.name",    190, "w"),
            "guid"   : ("m.src",      68, "center"),  # Quell-Badge (🧬/🔵/⚪)
            "note"   : ("m.note",    150, "w"),
            "cm"     : ("m.cm",       65, "e"),
            "seg"    : ("m.seg",      45, "e"),
            "rel"    : ("m.rel",     150, "w"),
            "tree"   : ("m.tree",    140, "w"),
            "ged"    : ("m.ged",      40, "center"),
            "ca"     : ("m.ca",       70, "center"),
            "starred": ("m.starred",  40, "center"),
        }.items():
            self._tree.heading(col, text=self._t(key), command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))
            self._lang_headings.append((self._tree, col, key))

        self._tree.tag_configure("paternal",  background="#DDF0FF")
        self._tree.tag_configure("maternal",  background="#FFE0E0")
        self._tree.tag_configure("close",    background="#D6F5E3")
        self._tree.tag_configure("starred",  background="#FFF3CD")
        self._tree.tag_configure("no_tree",  foreground="#999999")
        self._tree.tag_configure("endogamy", background="#E0E0E0", foreground="#666666")

        sy = ttk.Scrollbar(parent, orient="vertical",   command=self._tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1); parent.columnconfigure(0, weight=1)
        self._tree.bind("<<TreeviewSelect>>", self._on_match_select)
        self._tree.bind("<Button-3>", self._on_match_rightclick)
        self._sort_col = "cm"; self._sort_asc = False

        # Keyboard navigation
        self._tree.bind("<Return>", lambda _: self._on_match_select(None))
        self._tree.bind("<Escape>", lambda _: self._search_var.set("") or self._refresh_match_table())
        self.bind_all("<F5>", lambda _: self._refresh_match_table())

        # Empty state overlay
        self._empty_frame = ttk.Frame(parent)
        _ev = tk.StringVar(value=self._t("mf.empty"))
        ttk.Label(self._empty_frame, textvariable=_ev,
                  font=("Segoe UI", 14), foreground="#888888").pack(pady=(60, 8))
        self._lang_widgets.append((_ev, "mf.empty"))
        _eh = tk.StringVar(value=self._t("mf.empty_hint"))
        ttk.Label(self._empty_frame, textvariable=_eh,
                  font=("Segoe UI", 10), foreground="#AAAAAA").pack()
        self._lang_widgets.append((_eh, "mf.empty_hint"))
        ttk.Button(self._empty_frame, text="→ Download",
                   command=lambda: self._nb.select(1)).pack(pady=12)

    def _build_detail_panel(self, parent):
        # Oberer Teil: Matchdetails
        self._detail_nb = ttk.Notebook(parent)
        self._detail_nb.pack(fill="both", expand=True)

        # Sub-Tab 1: Info + Notiz
        info_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(info_frame, text=self._t("md.tab_info"))
        self._lang_inner_nb_tabs.append((self._detail_nb, info_frame, "md.tab_info"))

        self._detail_name_var = tk.StringVar(value="—")
        ttk.Label(info_frame, textvariable=self._detail_name_var,
                  font=("Segoe UI", 11, "bold"), wraplength=260).pack(anchor="w", padx=8, pady=(6,2))

        inf = ttk.Frame(info_frame); inf.pack(fill="x", padx=8)
        self._detail_fields: dict[str, tk.StringVar] = {}
        for de_lbl, key in [("cM","md.cm"),("Segmente","md.seg"),
                             ("Längstes Seg.","md.longseg"),("Beziehung","md.rel"),
                             ("Beziehung (cM)","md.rel_cm"),
                             ("Konfidenz","md.conf"),("Stammbaum","md.tree_lbl"),
                             ("Gem. Vorfahre","md.anc"),("Geschlecht","md.sex"),
                             ("Letzter Login","md.last"),
                             ("Ahnentafel","md.pedigree"),
                             ("Herkunft","md.origin"),
                             ("Herkunft (ML)","md.ml_origin")]:
            row = ttk.Frame(inf); row.pack(fill="x", pady=1)
            sv_lbl = tk.StringVar(value=self._t(key))
            ttk.Label(row, textvariable=sv_lbl, width=15, anchor="e",
                      foreground="#555555").pack(side="left")
            self._lang_widgets.append((sv_lbl, key))
            var = tk.StringVar(value="—")
            ttk.Label(row, textvariable=var, anchor="w").pack(side="left", padx=4)
            self._detail_fields[de_lbl] = var

        # Relationship probability bars
        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=4)
        _sv_rp = tk.StringVar(value=self._t("md.rel_prob"))
        ttk.Label(info_frame, textvariable=_sv_rp,
                  style="Bold.TLabel").pack(anchor="w", padx=8)
        self._lang_widgets.append((_sv_rp, "md.rel_prob"))
        self._rel_prob_canvas = tk.Canvas(info_frame, height=52, bg=COLORS["bg"],
                                          highlightthickness=0)
        self._rel_prob_canvas.pack(fill="x", padx=8, pady=(2, 4))

        # Research checklist
        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=2)
        _sv_cl = tk.StringVar(value=self._t("md.checklist"))
        ttk.Label(info_frame, textvariable=_sv_cl,
                  style="Bold.TLabel").pack(anchor="w", padx=8)
        self._lang_widgets.append((_sv_cl, "md.checklist"))
        self._checklist_vars: list[tk.BooleanVar] = []
        chk_frame = ttk.Frame(info_frame); chk_frame.pack(fill="x", padx=8)
        for i, key in enumerate(["md.chk0","md.chk1","md.chk2","md.chk3","md.chk4"]):
            var = tk.BooleanVar()
            self._checklist_vars.append(var)
            _sv_c = tk.StringVar(value=self._t(key))
            cb = ttk.Checkbutton(chk_frame, textvariable=_sv_c, variable=var,
                                  command=lambda i=i: self._save_checklist(i))
            cb.pack(anchor="w")
            self._lang_widgets.append((_sv_c, key))

        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=4)
        _sv = tk.StringVar(value=self._t("md.note"))
        ttk.Label(info_frame, textvariable=_sv, style="Bold.TLabel").pack(anchor="w", padx=8)
        self._lang_widgets.append((_sv, "md.note"))
        self._note_text = tk.Text(info_frame, height=4, font=("Segoe UI", 9),
                                   wrap="word", relief="solid", borderwidth=1)
        self._note_text.pack(fill="x", padx=8, pady=4)
        btn_row = ttk.Frame(info_frame); btn_row.pack(fill="x", padx=8, pady=2)
        _sv = tk.StringVar(value=self._t("md.save_note"))
        ttk.Button(btn_row, textvariable=_sv, command=self._save_note).pack(side="left", padx=(0,4))
        self._lang_widgets.append((_sv, "md.save_note"))
        _sv = tk.StringVar(value=self._t("md.open_anc"))
        ttk.Button(btn_row, textvariable=_sv, command=self._open_in_ancestry).pack(side="left", padx=4)
        self._lang_widgets.append((_sv, "md.open_anc"))
        _sv_fs = tk.StringVar(value=self._t("md.fs_link"))
        ttk.Button(btn_row, textvariable=_sv_fs, command=self._open_familysearch).pack(side="left", padx=4)
        self._lang_widgets.append((_sv_fs, "md.fs_link"))

        # Sub-Tab 2: Shared Matches
        sm_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(sm_frame, text=self._t("md.tab_shared"))
        self._lang_inner_nb_tabs.append((self._detail_nb, sm_frame, "md.tab_shared"))
        self._build_shared_panel(sm_frame)

        # Sub-Tab 3: GEDCOM-Bridge
        ged_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(ged_frame, text=self._t("md.tab_gedcom"))
        self._lang_inner_nb_tabs.append((self._detail_nb, ged_frame, "md.tab_gedcom"))
        self._build_gedcom_link_panel(ged_frame)

        # Sub-Tab 4: Gemeinsame Vorfahren (Ancestry match_ancestors)
        anc_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(anc_frame, text=self._t("md.tab_ancestors"))
        self._lang_inner_nb_tabs.append((self._detail_nb, anc_frame, "md.tab_ancestors"))
        self._build_ancestors_panel(anc_frame)

        self._selected_match: Optional[DnaMatch] = None

    def _build_shared_panel(self, parent):
        """Panel für Shared Matches des ausgewählten primären Matches."""
        # Toolbar
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._sm_count_var = tk.StringVar(value="Kein Match ausgewählt.")
        ttk.Label(tb, textvariable=self._sm_count_var,
                  foreground=COLORS["primary"]).pack(side="left")

        # Tabelle
        cols = ("name","cm","cmab","rel")
        self._sm_tree = ttk.Treeview(parent, columns=cols, show="headings",
                                      selectmode="browse", height=14)
        for col, (lbl, w, anchor) in {
            "name": ("Shared Match",     170, "w"),
            "cm"  : ("cM mit dir",        75, "e"),
            "cmab": ("cM mit Match",      80, "e"),
            "rel" : ("Beziehung zu dir", 130, "w"),
        }.items():
            self._sm_tree.heading(col, text=lbl)
            self._sm_tree.column(col, width=w, anchor=anchor, stretch=(col=="name"))

        sy = ttk.Scrollbar(parent, orient="vertical", command=self._sm_tree.yview)
        self._sm_tree.configure(yscrollcommand=sy.set)
        self._sm_tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=4)
        sy.pack(side="right", fill="y", pady=4)

    def _build_gedcom_link_panel(self, parent):
        """Sub-Tab 3: GEDCOM-Treffer — zeigt Verbindungen zwischen Match-Vorfahren
        und Personen im eigenen GEDCOM-Baum."""
        # Zeile 1: GEDCOM-Datei-Info + Wählen-Button
        hdr = ttk.Frame(parent); hdr.pack(fill="x", padx=6, pady=(4, 0))
        self._ged_file_var = tk.StringVar(value="—")
        ttk.Label(hdr, text="🌳", font=("Segoe UI", 10)).pack(side="left")
        ttk.Label(hdr, textvariable=self._ged_file_var,
                  foreground="#555555", font=("Segoe UI", 8)).pack(side="left", padx=4)
        ttk.Button(hdr, text="📂", width=3,
                   command=lambda: self._ensure_gedcom_loaded(
                       self._on_gedcom_loaded_update_header, force_ask=True)
                   ).pack(side="left")
        _sv_orig = tk.StringVar(value=self._t("md.ged_origin"))
        ttk.Button(hdr, textvariable=_sv_orig,
                   command=self._run_origin_inference).pack(side="right", padx=4)
        self._lang_widgets.append((_sv_orig, "md.ged_origin"))
        ttk.Button(hdr, text="🔗 WikiTree",
                   command=self._run_wikitree_extend).pack(side="right", padx=4)
        ttk.Button(hdr, text="🤖 ML-Herkunft",
                   command=self._run_ml_origin).pack(side="right", padx=4)
        ttk.Button(hdr, text="👥 Duplikate prüfen",
                   command=self._open_xref_review).pack(side="right", padx=4)
        _sv_endo_btn = tk.StringVar(value=self._t("md.ged_endogamy"))
        ttk.Button(hdr, textvariable=_sv_endo_btn,
                   command=self._run_endogamy_transfer).pack(side="right", padx=4)
        self._lang_widgets.append((_sv_endo_btn, "md.ged_endogamy"))

        # Zeile 2: Status + Bulk-Abgleich-Button
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=(2, 4))
        self._ged_link_status = tk.StringVar(value=self._t("md.ged_none"))
        ttk.Label(tb, textvariable=self._ged_link_status,
                  foreground=COLORS["primary"]).pack(side="left")
        _sv_all = tk.StringVar(value=self._t("md.ged_run_all"))
        ttk.Button(tb, textvariable=_sv_all,
                   command=self._run_gedcom_match_all).pack(side="right")
        self._lang_widgets.append((_sv_all, "md.ged_run_all"))

        cols = ("gen", "sosa", "path", "ped_name", "ped_year", "icon",
                "ged_name", "ged_year", "score", "method")
        self._ged_link_tree = ttk.Treeview(parent, columns=cols,
                                            show="headings", selectmode="browse")
        widths = {"gen": 30, "sosa": 45, "path": 50, "ped_name": 150, "ped_year": 48,
                  "icon": 28, "ged_name": 150, "ged_year": 48,
                  "score": 48, "method": 68}
        labels = {"gen": "Gen", "sosa": "Sosa", "path": "Pfad",
                  "ped_name": "Vorfahre (Match)", "ped_year": "Jahr",
                  "icon": "", "ged_name": "GEDCOM-Person",
                  "ged_year": "Jahr", "score": "Score", "method": "Methode"}
        for col in cols:
            self._ged_link_tree.heading(col, text=labels[col])
            self._ged_link_tree.column(col, width=widths[col],
                                        anchor="center" if col in ("gen","sosa","icon","score","ped_year","ged_year") else "w",
                                        stretch=(col in ("ped_name","ged_name")))
        self._ged_link_tree.tag_configure("strong", foreground=COLORS["success"])
        self._ged_link_tree.tag_configure("weak",   foreground="#888888")
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._ged_link_tree.yview)
        self._ged_link_tree.configure(yscrollcommand=sy.set)
        self._ged_link_tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=2)
        sy.pack(side="right", fill="y", pady=2)

        # Doppelklick → GEDCOM-Person im Browser öffnen (FamilySearch-Suche)
        self._ged_link_tree.bind("<Double-1>", self._on_ged_link_dblclick)

    def _load_gedcom_link_panel(self, match: "DnaMatch"):
        """Füllt den GEDCOM-Treffer-Tab für den ausgewählten Match."""
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        ged = getattr(self, "_gedcom", None)
        if not ged:
            self._ged_link_status.set(self._t("md.ged_none"))
            return

        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set(self._t("md.ged_searching"))

        self.after(0, lambda: self._on_gedcom_loaded_update_header(ged))

        def _worker():
            try:
                from core import bridge
                bridge.ensure_tables(self._db)
                # GEDCOM-Personen importieren, falls leer
                if bridge.get_gedcom_person_count(self._db) == 0:
                    n = bridge.import_gedcom_persons(
                        self._db, ged["individuals"], ged.get("path", ""))
                    log.info("bridge: %d Personen importiert", n)
                rows = bridge.run_match_for_match(self._db, test_guid, match.match_guid)
                self.after(0, lambda: self._fill_ged_link_tree(rows, match))
            except Exception as exc:
                log.warning("bridge: %s", exc)
                self.after(0, lambda: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="bridge").start()

    def _fill_ged_link_tree(self, rows: list, match: "DnaMatch"):
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        if not rows:
            self._ged_link_status.set(self._t("md.ged_no_ped"))
            return
        hits = sum(1 for r in rows if r["icon"])
        self._ged_link_status.set(
            f"{hits} Treffer von {len(rows)} Vorfahren  ·  {match.display_name}")
        try:
            from core.bridge import path_to_sosa
        except Exception:
            path_to_sosa = lambda p: ""  # noqa: E731
        for r in rows:
            tag = "strong" if r["icon"] == "✓" else ("weak" if not r["icon"] else "")
            ap = r["ahnen_path"] or ""
            sosa = path_to_sosa(ap) if ap else ""
            self._ged_link_tree.insert("", "end", values=(
                r["generation"], sosa, ap,
                r["ped_name"],   r["ped_year"],
                r["icon"],
                r["ged_name"],   r["ged_year"],
                r["score"],      r["method"],
            ), tags=(tag,) if tag else ())

    def _on_ged_link_dblclick(self, _event):
        """Doppelklick auf eine GEDCOM-Treffer-Zeile → FamilySearch-Suche nach Name."""
        sel = self._ged_link_tree.selection()
        if not sel:
            return
        vals = self._ged_link_tree.item(sel[0], "values")
        # cols: gen(0) sosa(1) path(2) ped_name(3) ped_year(4) icon(5) ged_name(6) ged_year(7)
        if not vals or len(vals) < 8 or vals[6] == "—" or not vals[6]:
            return
        ged_name = vals[6]
        ged_year = vals[7] or ""
        from urllib.parse import quote
        parts = ged_name.split()
        if parts:
            q = quote(parts[-1])
            url = (f"https://www.familysearch.org/search/record/results"
                   f"?q.surname={q}" + (f"&q.birthLikeDate.from={ged_year}&q.birthLikeDate.to={ged_year}"
                                        if ged_year else ""))
            import webbrowser
            webbrowser.open(url)

    def _build_ancestors_panel(self, parent):
        """Sub-Tab 4: Gemeinsame Vorfahren (aus Ancestry match_ancestors-Tabelle)."""
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._anc_status_var = tk.StringVar(value="")
        ttk.Label(tb, textvariable=self._anc_status_var,
                  foreground=COLORS["primary"]).pack(side="left")

        cols = ("name", "birth", "death", "rel_sample", "rel_match", "path_sample")
        self._anc_tree = ttk.Treeview(parent, columns=cols,
                                       show="headings", selectmode="browse")
        widths   = {"name": 200, "birth": 45, "death": 45,
                    "rel_sample": 140, "rel_match": 140, "path_sample": 90}
        labels   = {"name": "Vorfahre", "birth": "Geb.", "death": "Gest.",
                    "rel_sample": "Verwandtschaft (Proband)",
                    "rel_match":  "Verwandtschaft (Match)",
                    "path_sample": "Ahnen-Pfad"}
        anchors  = {"birth": "center", "death": "center", "path_sample": "center"}
        for col in cols:
            self._anc_tree.heading(col, text=labels[col])
            self._anc_tree.column(col, width=widths[col],
                                   anchor=anchors.get(col, "w"),
                                   stretch=(col in ("name", "rel_sample", "rel_match")))
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._anc_tree.yview)
        self._anc_tree.configure(yscrollcommand=sy.set)
        self._anc_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=2)
        sy.pack(side="right", fill="y", pady=2)

    def _load_ancestors_panel(self, match: "DnaMatch"):
        """Füllt den Gemeinsame-Vorfahren-Tab für den ausgewählten Match."""
        self._anc_tree.delete(*self._anc_tree.get_children())
        try:
            rows = self._db.get_ancestors_for_match(match.match_guid)
        except Exception:
            rows = []
        if not rows:
            self._anc_status_var.set(self._t("md.anc_none"))
            return
        self._anc_status_var.set(
            f"{len(rows)} gemeinsame Vorfahren  ·  {match.display_name}")
        for r in rows:
            self._anc_tree.insert("", "end", values=(
                r.get("ancestor_name", ""),
                r.get("birth_year") or "—",
                r.get("death_year") or "—",
                r.get("relationship_to_sample", ""),
                r.get("relationship_to_match", ""),
                r.get("kinship_path_sample", ""),
            ))

    def _run_gedcom_match_all(self):
        """Bulk-Abgleich aller Matches gegen den GEDCOM-Baum."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo("GEDCOM", self._t("md.ged_none"))
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Bulk-Abgleich läuft …")

        def _worker():
            try:
                from core import bridge
                bridge.ensure_tables(self._db)
                if bridge.get_gedcom_person_count(self._db) == 0:
                    bridge.import_gedcom_persons(
                        self._db, ged["individuals"], ged.get("path", ""))
                total = bridge.run_match_all(self._db, test_guid)
                self.after(0, lambda: self._ged_link_status.set(
                    f"Bulk-Abgleich fertig: {total} Treffer gesamt"))
                # Match-Tabelle aktualisieren (🌳N-Spalte) + aktuelle Detail-Ansicht
                self.after(0, self._refresh_match_table)
                if self._selected_match:
                    self.after(0, lambda: self._load_gedcom_link_panel(self._selected_match))
            except Exception as exc:
                log.warning("bridge bulk: %s", exc)
                self.after(0, lambda: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="bridge-bulk").start()

    def _on_gedcom_loaded_update_header(self, ged: dict):
        """Callback nach _ensure_gedcom_loaded: GEDCOM-Dateiname in Header zeigen."""
        import os
        path = ged.get("path", "")
        name = os.path.basename(path) if path else "—"
        n = len(ged.get("people", {}))
        if hasattr(self, "_ged_file_var"):
            self._ged_file_var.set(f"{name}  ({n} Personen)")

    def _run_endogamy_transfer(self):
        """Überträgt GEDCOM-Endogamie-Scores via Geburtsort-Abgleich auf Matches."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo("GEDCOM", self._t("md.ged_none"))
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Endogamie-Transfer läuft …")

        def _worker():
            try:
                from core import bridge as _bridge
                import sys as _sys, os as _os, importlib.util as _ilu
                # GEDCOM-Endogamie aus dem Haupt-Analyzer laden (tasks/endogamy.py)
                _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                if _root not in _sys.path:
                    _sys.path.insert(0, _root)
                from tasks.endogamy import compute_endogamy_with_detailed_places
                from lib.places import load_location_data
                # Root-config direkt laden (nicht über sys.modules["config"],
                # der auf ancestry/config.py zeigt)
                _cfg_spec = _ilu.spec_from_file_location(
                    "_root_config", _os.path.join(_root, "config.py"))
                _cfg_root = _ilu.module_from_spec(_cfg_spec)
                _cfg_spec.loader.exec_module(_cfg_root)
                loc = load_location_data(
                    _cfg_root.DEFAULT_CONFIG.get("location_data_json", ""))
                endo_results = compute_endogamy_with_detailed_places(
                    ged["individuals"], ged["families"],
                    root_id="", location_data=loc)
                n = _bridge.apply_gedcom_endogamy_to_matches(
                    self._db, test_guid, endo_results,
                    progress_cb=lambda m, **kw: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)))
                self.after(0, lambda: self._ged_link_status.set(
                    f"Endogamie-Transfer fertig: {n} Matches markiert"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("endogamy-transfer: %s", exc)
                self.after(0, lambda: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="endo-transfer").start()

    def _open_xref_review(self):
        """Fenster zum Prüfen grenzwertiger Duplikat-Verknüpfungen (gedcom_person_xref)."""
        try:
            from core import bridge
        except Exception as e:
            messagebox.showerror("Duplikate", f"bridge nicht ladbar: {e}"); return

        win = tk.Toplevel(self)
        win.title("Duplikate prüfen – Querbezüge")
        win.geometry("900x460")

        bar = ttk.Frame(win); bar.pack(fill="x", padx=8, pady=6)
        ttk.Label(bar, text="Score von").pack(side="left")
        lo_var = tk.StringVar(value="0.72"); hi_var = tk.StringVar(value="0.85")
        ttk.Entry(bar, textvariable=lo_var, width=5).pack(side="left", padx=2)
        ttk.Label(bar, text="bis").pack(side="left")
        ttk.Entry(bar, textvariable=hi_var, width=5).pack(side="left", padx=2)
        only_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="nur ungeprüfte", variable=only_auto).pack(side="left", padx=8)

        cols = ("score", "status", "a", "b")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=15)
        for c, t, w in [("score","Score",60),("status","Status",80),
                        ("a","A (dein GEDCOM)",360),("b","B (andere Quelle)",360)]:
            tree.heading(c, text=t); tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=8)
        rowmap = {}

        def _fmt(r, pre):
            return (f"{r[pre+'_given'] or ''} {r[pre+'_surname'] or ''} "
                    f"*{r[pre+'_by'] or '?'} †{r[pre+'_dy'] or '?'} "
                    f"[{r[pre+'_bp'] or ''}]").strip()

        def reload():
            tree.delete(*tree.get_children()); rowmap.clear()
            try:
                lo, hi = float(lo_var.get()), float(hi_var.get())
            except ValueError:
                lo, hi = 0.0, 1.0
            pairs = bridge.get_xref_pairs(self._db, lo=lo, hi=hi)
            for r in pairs:
                if only_auto.get() and r["status"] != "auto":
                    continue
                iid = tree.insert("", "end", values=(
                    f"{r['score']:.3f}", r["status"], _fmt(r,"a"), _fmt(r,"b")))
                rowmap[iid] = r
            win.title(f"Duplikate prüfen – {len(rowmap)} Paare")

        def _decide(status):
            for iid in tree.selection():
                r = rowmap.get(iid)
                if not r: continue
                bridge.set_xref_status(self._db, r["ged_id_primary"],
                                       r["ged_id_other"], status)
                tree.set(iid, "status", status)

        btns = ttk.Frame(win); btns.pack(fill="x", padx=8, pady=6)
        ttk.Button(btns, text="🔄 Laden", command=reload).pack(side="left")
        ttk.Button(btns, text="✓ Dieselbe Person (bestätigen)",
                   command=lambda: _decide("confirmed")).pack(side="left", padx=4)
        ttk.Button(btns, text="✗ Verschiedene (ablehnen)",
                   command=lambda: _decide("rejected")).pack(side="left", padx=4)
        ttk.Label(btns, text="Mehrfachauswahl möglich (Strg/Shift)",
                  foreground="#777").pack(side="right")
        reload()

    def _run_ml_origin(self):
        """Trainiert (falls nötig) das ML-Herkunftsmodell auf dem GEDCOM und
        wendet es als 'zweite Meinung' auf alle Matches an (ml_origin-Spalte)."""
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return
        self._ged_link_status.set("ML-Herkunft: starte …")

        def _worker():
            try:
                from core import ml_origin as _ml
                cb = lambda m: self.after(0, lambda mm=m: self._ged_link_status.set(mm))
                if not _ml.load():
                    cb("ML: trainiere Modell auf GEDCOM …")
                    metrics = _ml.train(self._db, progress_cb=cb)
                    cb(f"ML: trainiert ({metrics['n_train']} Personen, "
                       f"{metrics['n_regions']} Regionen, "
                       f"{metrics['train_acc']:.0%})")
                n = _ml.apply_to_matches(self._db, test_guid, progress_cb=cb)
                self.after(0, lambda: self._ged_link_status.set(
                    f"ML-Herkunft fertig: {n} Matches gelabelt"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("ml-origin: %s", exc)
                msg = str(exc).split("\n")[0]
                self.after(0, lambda: self._ged_link_status.set(f"ML-Fehler: {msg}"))
                self.after(0, lambda: messagebox.showwarning("ML-Herkunft", str(exc)))

        import threading
        threading.Thread(target=_worker, daemon=True, name="ml-origin").start()

    def _run_wikitree_extend(self):
        """Verlängert die Ahnenlinie des gewählten Matches über die WikiTree-API."""
        match = getattr(self, "_selected_match", None)
        if not match:
            messagebox.showinfo("WikiTree", "Bitte zuerst einen Match in der Tabelle auswählen.")
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("WikiTree-Abgleich läuft …")

        def _worker(mguid=match.match_guid, mname=match.display_name):
            try:
                from core import bridge as _bridge
                results = _bridge.wikitree_extend_match(
                    self._db, test_guid, mguid,
                    progress_cb=lambda m: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)),
                )
                found = sum(1 for r in results if r.get("best"))
                self.after(0, lambda: self._ged_link_status.set(
                    f"WikiTree: {found} Linie(n) gefunden"))
                self.after(0, lambda: self._show_wikitree_results(mname, results))
            except Exception as exc:
                log.warning("wikitree-extend: %s", exc)
                self.after(0, lambda: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="wikitree").start()

    def _show_wikitree_results(self, match_name: str, results: list):
        """Zeigt die WikiTree-Treffer und gefundenen Ahnenlinien in einem Fenster."""
        win = tk.Toplevel(self)
        win.title(f"WikiTree-Linien: {match_name}")
        win.geometry("640x520")
        txt = tk.Text(win, wrap="word", font=("Segoe UI", 9))
        sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); txt.pack(fill="both", expand=True)

        if not results:
            txt.insert("end", "Keine Ahnen mit Nachnamen in der Ahnentafel dieses Matches.\n")
        for r in results:
            q = r.get("query", {})
            txt.insert("end", f"▶ {q.get('first_name','')} {q.get('surname','')}"
                              f"  ({q.get('birth_place','')} {q.get('birth_year','')})\n")
            if r.get("error"):
                txt.insert("end", f"   Fehler: {r['error']}\n\n"); continue
            best = r.get("best")
            if not best:
                txt.insert("end", f"   kein WikiTree-Treffer ({len(r.get('candidates',[]))} Kandidaten)\n\n")
                continue
            txt.insert("end", f"   ✓ {best.get('Name','?')}: {best.get('FirstName','')} "
                              f"{best.get('LastNameAtBirth','')}  "
                              f"* {best.get('BirthDate','?')} {best.get('BirthLocation','')}\n")
            lin = r.get("lineage", [])
            if lin:
                txt.insert("end", f"   Ahnenlinie ({len(lin)}):\n")
                for a in lin[:12]:
                    txt.insert("end", f"      • {a.get('FirstName','')} "
                                      f"{a.get('LastNameAtBirth','')}  "
                                      f"* {a.get('BirthDate','?')} {a.get('BirthLocation','')}\n")
            txt.insert("end", "\n")
        txt.configure(state="disabled")

    def _run_origin_inference(self):
        """Leitet wahrscheinliche Herkunftsregionen aus Pedigree-Nachnamen × GEDCOM-Orten ab."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo("GEDCOM", self._t("md.ged_none"))
            return
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Herkunfts-Analyse läuft …")

        def _worker():
            try:
                from core import bridge as _bridge
                results = _bridge.infer_match_origins(
                    self._db, test_guid,
                    progress_cb=lambda m, **kw: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)),
                )
                n = len(results)
                self.after(0, lambda: self._ged_link_status.set(
                    f"Herkunfts-Analyse fertig: {n} Matches zugeordnet"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("origin-inference: %s", exc)
                self.after(0, lambda: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="origin-infer").start()

    def _refresh_match_table(self, *_):
        try:
            self._refresh_match_table_inner()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("_refresh_match_table fehlgeschlagen")
            try:
                if hasattr(self, "_match_count_var"):
                    self._match_count_var.set(f"⚠ Fehler: {exc}")
            except Exception:
                pass

    def _refresh_match_table_inner(self, *_):
        try:
            min_cm = float(self._min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            min_cm = 0.0

        try:
            rels = self._db.get_distinct_relationships()
        except Exception:
            rels = []
        if hasattr(self, "_rel_combo"):
            self._rel_combo["values"] = ["(alle)"] + rels

        col_map = {"name":"display_name","guid":"match_guid","note":"tag_surname",
                   "cm":"shared_cm","seg":"shared_segments",
                   "rel":"predicted_relationship","tree":"tree_size",
                   "ged":"match_guid","ca":"has_common_ancestor","starred":"starred"}
        sort_col = col_map.get(self._sort_col, "shared_cm")

        # Kit-GUID aus Matches-Tab-Selektor
        active_kit: Optional[str] = None
        selected_kit_name = ""
        if hasattr(self, "_matches_kit_var") and self._matches_kit_var.get():
            selected_kit_name = self._matches_kit_var.get()
            active_kit = self._matches_kit_guid_map.get(selected_kit_name)
        all_sources_mode = (selected_kit_name == self._ALL_SOURCES_LABEL)
        if not all_sources_mode and not active_kit:
            active_kit = self._current_test_guid or self._get_kit_guid()

        self._matches = self._db.get_matches(
            test_guid      = active_kit,
            all_sources    = all_sources_mode,
            search         = self._search_var.get().strip() or None,
            relationship   = self._rel_var.get() if hasattr(self,"_rel_var") else None,
            starred_only   = self._starred_var.get() if hasattr(self,"_starred_var") else False,
            has_tree_only  = self._tree_var.get() if hasattr(self,"_tree_var") else False,
            min_cm         = min_cm,
            hide_endogamy  = getattr(self, "_hide_endo_var", tk.BooleanVar()).get(),
            sort_col       = sort_col,
            sort_asc       = self._sort_asc,
        )

        # Overlap-Set: welche GUIDs kommen noch in anderen Kits vor?
        overlap_guids: set = set()
        if active_kit:
            try:
                all_kits = [k.guid for k in self._db.get_kits() if k.guid != active_kit]
                if all_kits:
                    with self._db._cursor() as _cur:
                        rows = _cur.execute(
                            "SELECT match_guid FROM match_kit_membership WHERE test_guid IN ({})".format(
                                ",".join("?" * len(all_kits))),
                            all_kits,
                        ).fetchall()
                    overlap_guids = {r[0] for r in rows}
            except Exception:
                pass
        self._match_count_var.set(f"{len(self._matches)} Match(es)")
        self._tree.delete(*self._tree.get_children())
        # Apply pat/mat chip filter
        if hasattr(self, "_chip_vars"):
            if self._chip_vars.get("pat", tk.BooleanVar()).get():
                self._matches = [m for m in self._matches
                                 if getattr(m, "paternal_maternal", "") == "paternal"]
            elif self._chip_vars.get("mat", tk.BooleanVar()).get():
                self._matches = [m for m in self._matches
                                 if getattr(m, "paternal_maternal", "") == "maternal"]
        # Bridge-Treffer-Zähler laden (leer wenn kein GEDCOM / keine Tabelle)
        bridge_hits: dict = {}
        if getattr(self, "_gedcom", None):
            try:
                tg = self._current_test_guid or self._get_kit_guid()
                if tg:
                    bridge_hits = self._db.get_bridge_hit_counts(tg)
            except Exception:
                pass
        for m in self._matches:
            endo = getattr(m, "endogamy_cluster", "") or ""
            tags = []
            pm = m.paternal_maternal or ""
            if pm == "paternal":
                tags.append("paternal")
            elif pm == "maternal":
                tags.append("maternal")
            if endo:
                tags.append("endogamy")
            elif m.starred:
                tags.append("starred")
            elif m.predicted_relationship.lower() in (
                "parent","child","sibling","aunt/uncle","first cousin",
                "1st cousin","half sibling","close"):
                tags.append("close")
            if not m.has_tree and not endo:
                tags.append("no_tree")

            # Stammbaum-Spalte: Status (+ Personenzahl falls vorhanden)
            status = getattr(m, "tree_status", "") or ""
            if status and m.tree_size:
                tree_txt = f"{status} ({m.tree_size})"
            elif status:
                tree_txt = status
            elif m.has_tree:
                tree_txt = f"✓ ({m.tree_size})" if m.tree_size else "✓"
            else:
                tree_txt = "—"

            # Quell-Badge (Plattform)
            src = getattr(m, "source", "ancestry") or "ancestry"
            gm_kit = getattr(m, "gedmatch_kit_id", "") or ""
            if src == "myheritage":
                src_badge = "🔵MH"
            elif src == "gedmatch":
                src_badge = "⚪GED"
            else:
                src_badge = "🧬ANC"
            if gm_kit:
                src_badge += "⚡"   # GEDmatch-Brücke bekannt

            # Bemerkungsspalte: Overlap → Endogamie → tag_surname
            in_other_kit = m.match_guid in overlap_guids
            if endo:
                note_txt = f"🔇 {endo}"
            elif in_other_kit:
                note_txt = f"👥 {m.tag_surname or ''}".strip()
            else:
                note_txt = m.tag_surname or ""

            n_hits = bridge_hits.get(m.match_guid, 0)
            ged_txt = f"🌳{n_hits}" if n_hits else ""
            self._tree.insert("", "end", iid=m.match_guid, tags=tags, values=(
                m.display_name,
                src_badge,
                note_txt,
                f"{m.shared_cm:.1f}" if m.shared_cm else "—",
                m.shared_segments or "—",
                m.predicted_relationship or "—",
                tree_txt,
                ged_txt,
                "👪" if getattr(m, "has_common_ancestor", False) else "—",
                "⭐" if m.starred else "",
            ))
        # Show/hide empty state
        if hasattr(self, "_empty_frame"):
            if self._matches:
                self._empty_frame.place_forget()
            else:
                self._empty_frame.place(relx=0.5, rely=0.5, anchor="center")

    def _on_match_rightclick(self, event):
        """Kontextmenü bei Rechtsklick auf einen Match."""
        item = self._tree.identify_row(event.y)
        if not item:
            return
        self._tree.selection_set(item)
        match = next((m for m in self._matches if m.match_guid == item), None)
        if not match:
            return

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="🔗 In Ancestry öffnen",
            command=self._open_in_ancestry)
        menu.add_command(
            label="📋 Match-GUID kopieren",
            command=lambda: (self.clipboard_clear(),
                             self.clipboard_append(match.match_guid)))
        menu.add_separator()
        menu.add_command(
            label="⭐ Als Mutterseite markieren",
            command=lambda: self._set_custom_rel(match, "maternal"))
        menu.add_command(
            label="⭐ Als Vaterseite markieren",
            command=lambda: self._set_custom_rel(match, "paternal"))
        menu.add_command(
            label="✏️  Name eintragen …",
            command=lambda: self._prompt_name(match))
        menu.add_separator()
        endo = getattr(match, "endogamy_cluster", "") or ""
        endo_label = (f"🔇 Endogamie-Cluster: {endo}" if endo
                      else "🔇 Als Hintergrundrauschen markieren …")
        menu.add_command(label=endo_label,
                         command=lambda: self._set_endogamy_cluster(match))
        if endo:
            menu.add_command(label="✖ Endogamie-Markierung entfernen",
                             command=lambda: self._clear_endogamy_cluster(match))
        menu.tk_popup(event.x_root, event.y_root)

    def _set_endogamy_cluster(self, match):
        """Dialog: Endogamie-Cluster-Namen eingeben oder aus bekannten wählen."""
        known = self._load_ui_settings().get("endogamy_clusters", [])
        current = getattr(match, "endogamy_cluster", "") or ""

        dlg = tk.Toplevel(self)
        dlg.title("Endogamie-Cluster zuweisen")
        dlg.geometry("420x180")
        dlg.grab_set()
        dlg.resizable(False, False)

        ttk.Label(dlg, text=f"Match: {match.display_name}",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(12,2))
        ttk.Label(dlg,
                  text="Cluster-Name (z. B. 'Ostercappeln/Seymour') — "
                       "leer lassen zum Entfernen:").pack(anchor="w", padx=14)

        var = tk.StringVar(value=current)
        cb = ttk.Combobox(dlg, textvariable=var, values=known, width=38)
        cb.pack(padx=14, pady=8, fill="x")
        cb.focus()

        def _save():
            name = var.get().strip()
            self._db.set_endogamy_cluster(match.match_guid, name)
            match.endogamy_cluster = name
            if name and name not in known:
                known.append(name)
                self._save_ui_settings(endogamy_clusters=known)
            self._refresh_match_table()
            dlg.destroy()

        bf = ttk.Frame(dlg); bf.pack(anchor="e", padx=14, pady=4)
        ttk.Button(bf, text="Abbrechen", command=dlg.destroy).pack(side="left", padx=4)
        ttk.Button(bf, text="Speichern", command=_save).pack(side="left")
        dlg.bind("<Return>", lambda _: _save())

    def _clear_endogamy_cluster(self, match):
        self._db.set_endogamy_cluster(match.match_guid, "")
        match.endogamy_cluster = ""
        self._refresh_match_table()

    def _set_custom_rel(self, match, rel: str):
        self._db.update_note(match.match_guid,
                             match.note or "")
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET custom_relationship=? WHERE match_guid=?",
                        (rel, match.match_guid))
        self._set_status(f"{match.display_name} → {rel}")
        self._refresh_match_table()

    def _prompt_name(self, match):
        """Einfacher Dialog um einen Namen manuell einzutragen."""
        import tkinter.simpledialog as sd
        name = sd.askstring(
            "Name eintragen",
            "Name eintragen (cM: " + str(round(match.shared_cm)) + ")",
            initialvalue=match.display_name if match.display_name != "Anonym" else "",
            parent=self,
        )
        if name is not None and name.strip():
            with self._db._cursor() as cur:
                cur.execute("UPDATE matches SET display_name=? WHERE match_guid=?",
                            (name.strip(), match.match_guid))
            self._set_status(f"Name gespeichert: {name.strip()}")
            self._refresh_match_table()

    def _save_cluster_desc(self):
        """Save cluster description to ui_settings."""
        sel = self._cluster_list.selection()
        if not sel:
            return
        cid = int(sel[0])
        desc = self._cluster_desc_var.get().strip()
        descs = self._load_ui_settings().get("cluster_descs", {})
        descs[str(cid)] = desc
        self._save_ui_settings(cluster_descs=descs)
        self._set_status(f"Cluster #{cid} Beschreibung gespeichert.")

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col in ("name","rel")
        # Update column header to show sort direction
        for c in ("name","guid","note","cm","seg","rel","tree","ca","starred"):
            base = self._t({
                "name":"m.name","guid":"m.guid","note":"m.note","cm":"m.cm",
                "seg":"m.seg","rel":"m.rel","tree":"m.tree","ca":"m.ca","starred":"m.starred",
            }[c])
            if c == self._sort_col:
                self._tree.heading(c, text=base + (" ▲" if self._sort_asc else " ▼"))
            else:
                self._tree.heading(c, text=base)
        self._refresh_match_table()

    @staticmethod
    def _tree_detail_text(match) -> str:
        status = getattr(match, "tree_status", "") or ""
        if status and match.tree_size:
            return f"{status} ({match.tree_size} Personen)"
        if status:
            return status
        if match.has_tree:
            return f"Ja ({match.tree_size})" if match.tree_size else "Ja"
        return "Nein"

    def _on_match_select(self, _):
        sel = self._tree.selection()
        if not sel: return
        match = next((m for m in self._matches if m.match_guid == sel[0]), None)
        if not match: return
        self._selected_match = match

        # Detail-Felder befüllen
        self._detail_name_var.set(match.display_name)
        for lbl, val in [
            ("cM",             f"{match.shared_cm:.2f}"),
            ("Segmente",       str(match.shared_segments)),
            ("Längstes Seg.",  f"{match.longest_segment:.2f} cM"),
            ("Beziehung",      match.predicted_relationship or "—"),
            ("Beziehung (cM)", self._rel_cm_summary(match.shared_cm or 0)),
            ("Konfidenz",      match.confidence or "—"),
            ("Stammbaum",      self._tree_detail_text(match)),
            ("Gem. Vorfahre",  "Ja 👪" if getattr(match, "has_common_ancestor", False) else "Nein"),
            ("Geschlecht",     {"M":"♂ männlich","F":"♀ weiblich"}.get(
                                   getattr(match, "gender", ""), "—")),
            ("Letzter Login",  match.last_login[:10] if match.last_login else "—"),
        ]:
            self._detail_fields[lbl].set(val)

        # Ahnentafel-Vollständigkeit asynchron nachladen
        test_guid_af = self._current_test_guid or self._get_kit_guid()
        self._detail_fields["Ahnentafel"].set("…")
        def _load_ped(guid=match.match_guid, tg=test_guid_af):
            try:
                summary = self._db.get_pedigree_summary_for_match(tg, guid)
                self.after(0, lambda s=summary: self._detail_fields["Ahnentafel"].set(
                    s if s else "—"))
            except Exception:
                self.after(0, lambda: self._detail_fields["Ahnentafel"].set("—"))
        import threading as _thr
        _thr.Thread(target=_load_ped, daemon=True, name="ped-summary").start()

        # Herkunfts-Schätzung aus probable_origin-Spalte laden
        self._detail_fields["Herkunft"].set("…")
        def _load_origin(guid=match.match_guid):
            try:
                import json as _json
                with self._db._cursor() as _cur:
                    row = _cur.execute(
                        "SELECT probable_origin FROM matches WHERE match_guid=?", (guid,)
                    ).fetchone()
                raw = row["probable_origin"] if row else ""
                if raw:
                    data = _json.loads(raw)
                    region = data.get("region", "")
                    score  = data.get("score", 0)
                    sn     = ", ".join(data.get("surnames", [])[:3])
                    label  = f"{region} ({score:.2f})" + (f"  [{sn}]" if sn else "")
                else:
                    label = "—"
                self.after(0, lambda lb=label: self._detail_fields["Herkunft"].set(lb))
            except Exception:
                self.after(0, lambda: self._detail_fields["Herkunft"].set("—"))
        _thr.Thread(target=_load_origin, daemon=True, name="origin-load").start()

        # ML-Herkunft (zweite Meinung) aus ml_origin-Spalte laden
        self._detail_fields["Herkunft (ML)"].set("…")
        def _load_ml_origin(guid=match.match_guid):
            try:
                import json as _json
                with self._db._cursor() as _cur:
                    row = _cur.execute(
                        "SELECT ml_origin FROM matches WHERE match_guid=?", (guid,)
                    ).fetchone()
                raw = row["ml_origin"] if row and "ml_origin" in row.keys() else ""
                if raw:
                    data = _json.loads(raw)
                    region = data.get("region", "")
                    prob   = data.get("prob", 0)
                    alts   = data.get("alts", [])
                    label  = f"{region} ({prob*100:.0f}%)"
                    if alts:
                        label += "  · " + ", ".join(
                            f"{a['region']} {a['prob']*100:.0f}%" for a in alts[:2])
                else:
                    label = "—"
                self.after(0, lambda lb=label: self._detail_fields["Herkunft (ML)"].set(lb))
            except Exception:
                self.after(0, lambda: self._detail_fields["Herkunft (ML)"].set("—"))
        _thr.Thread(target=_load_ml_origin, daemon=True, name="ml-origin-load").start()

        self._note_text.delete("1.0","end")
        self._note_text.insert("1.0", match.note or "")

        # MRCA-Schätzung im Status (einzeilig, nicht invasiv)
        cm = match.shared_cm or 0
        mrca_hint = ""
        for lo, hi, label, gen in self._CM_RANGES:
            if lo <= cm <= hi:
                mrca_hint = f"  →  ~{label} (Gen {gen})"
                break
        self._set_status(f"{match.display_name}  ·  {cm:.0f} cM{mrca_hint}")

        # Update relationship probability bars
        self.after(10, lambda: self._update_rel_prob(cm))

        # Load research checklist
        flags = getattr(match, "research_flags", 0) or 0
        for i, var in enumerate(self._checklist_vars):
            var.set(bool(flags & (1 << i)))

        # Shared Matches + GEDCOM-Bridge + Gemeinsame Vorfahren laden
        self._load_shared_panel(match)
        self._load_gedcom_link_panel(match)
        self._load_ancestors_panel(match)

    def _load_shared_panel(self, match: DnaMatch):
        """Lädt Shared Matches für den ausgewählten primären Match."""
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        shared = self._db.get_shared_matches(test_guid, match.match_guid)
        self._sm_tree.delete(*self._sm_tree.get_children())

        if not shared:
            fetched = self._db.is_shared_fetched(test_guid, match.match_guid)
            self._sm_count_var.set(
                "Shared Matches wurden abgefragt, aber keine gefunden."
                if fetched else
                "Noch nicht heruntergeladen. → Tab »Herunterladen« → Schritt B"
            )
            return

        self._sm_count_var.set(f"{len(shared)} Shared Match(es) mit {match.display_name}")
        for sm in shared:
            self._sm_tree.insert("", "end", values=(
                sm.display_name_b or "(unbekannt)",
                f"{sm.shared_cm_b:.0f}" if sm.shared_cm_b else "—",
                f"{sm.shared_cm_ab:.0f}" if sm.shared_cm_ab else "—",
                sm.relationship_b or "—",
            ))

    def _open_in_ancestry(self):
        """Öffnet den aktuellen Match in Ancestry im Browser."""
        if not self._selected_match:
            return
        test_guid  = self._current_test_guid or self._get_kit_guid()
        match_guid = self._selected_match.match_guid
        if not test_guid or not match_guid:
            return
        import webbrowser
        url = (f"https://www.ancestry.com/discoveryui-matches/compare"
               f"/{test_guid}/with/{match_guid}")
        webbrowser.open(url)
        self._set_status(f"Ancestry geöffnet: {self._selected_match.display_name}")

    def _save_note(self):
        if not self._selected_match: return
        note = self._note_text.get("1.0","end").strip()
        self._db.update_note(self._selected_match.match_guid, note)
        self._selected_match.note = note
        self._set_status(f"Notiz gespeichert: {self._selected_match.display_name}")

    def _save_checklist(self, changed_index: int):
        """Save research checklist state as bitmask to DB."""
        if not self._selected_match:
            return
        flags = sum(1 << i for i, v in enumerate(self._checklist_vars) if v.get())
        try:
            self._db.update_research_flags(self._selected_match.match_guid, flags)
        except Exception as e:
            log.debug("Checklist speichern: %s", e)

    def _open_familysearch(self):
        """Search FamilySearch for the selected match's name."""
        if not self._selected_match:
            return
        name = self._selected_match.display_name or ""
        if not name or name in ("Anonym", "?"):
            messagebox.showinfo("Kein Name", "Für diesen Match ist kein Name bekannt.")
            return
        url = f"https://www.familysearch.org/search/record/results?q.surname={quote(name.split()[-1])}"
        webbrowser.open(url)

    @staticmethod
    def _rel_cm_summary(cm: float) -> str:
        """Shared-cM-Project-Verteilung als Einzeiler, z.B.
        '70% 2. Cousin · 19% Halb-1C · 11% …'."""
        try:
            from core.shared_cm import summary_line
            return summary_line(cm, top=3) if cm and cm > 0 else "—"
        except Exception:
            return "—"

    def _update_rel_prob(self, cm: float):
        """Draw top-3 relationship probability bars on the canvas
        (Shared cM Project 4.0 distribution)."""
        c = self._rel_prob_canvas
        c.delete("all")
        if cm <= 0:
            return
        w = c.winfo_width() or 260
        h = c.winfo_height() or 52
        try:
            from core.shared_cm import relationship_probabilities
            probs = relationship_probabilities(cm, top=3)
            scored = [(p["probability"], p["labels"][0]) for p in probs]
        except Exception:
            scored = []
        if not scored:
            return
        total = sum(s for s, _ in scored) or 1.0
        colors = [COLORS["primary"], COLORS["accent"], COLORS["light"]]
        bar_h = (h - 6) // 3
        for i, (score, label) in enumerate(scored):
            pct = score / total
            y0 = 3 + i * (bar_h + 2)
            bar_w = max(4, int((w - 130) * pct))
            c.create_rectangle(2, y0, bar_w + 2, y0 + bar_h,
                                fill=colors[i], outline="")
            c.create_text(bar_w + 6, y0 + bar_h // 2,
                          text=f"{label}  {pct*100:.0f}%",
                          anchor="w", font=("Segoe UI", 8),
                          fill=COLORS["text"])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4: CLUSTER
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_cluster(self):
        f = self._tab_cluster

        # Einstellungen
        cf = ttk.Frame(f); cf.pack(fill="x", padx=14, pady=8)
        _sv_pf = tk.StringVar(value=self._t("cl.prim_from"))
        ttk.Label(cf, textvariable=_sv_pf).pack(side="left")
        self._lang_widgets.append((_sv_pf, "cl.prim_from"))
        self._cluster_min_cm_var = tk.StringVar(value="20")
        ttk.Entry(cf, textvariable=self._cluster_min_cm_var, width=6).pack(side="left", padx=6)
        _sv_pt = tk.StringVar(value=self._t("cl.prim_to"))
        ttk.Label(cf, textvariable=_sv_pt).pack(side="left", padx=(4,4))
        self._lang_widgets.append((_sv_pt, "cl.prim_to"))
        self._cluster_max_cm_var = tk.StringVar(value="400")
        ttk.Entry(cf, textvariable=self._cluster_max_cm_var, width=6).pack(side="left")
        _sv_sm = tk.StringVar(value=self._t("cl.shared_min"))
        ttk.Label(cf, textvariable=_sv_sm).pack(side="left", padx=(14,4))
        self._lang_widgets.append((_sv_sm, "cl.shared_min"))
        self._cluster_shared_cm_var = tk.StringVar(value="20")
        ttk.Entry(cf, textvariable=self._cluster_shared_cm_var, width=6).pack(side="left")
        _sv_calc = tk.StringVar(value=self._t("cl.calc_btn"))
        ttk.Button(cf, textvariable=_sv_calc, command=self._refresh_cluster).pack(side="left", padx=14)
        self._lang_widgets.append((_sv_calc, "cl.calc_btn"))
        self._cluster_count_var = tk.StringVar(value="")
        ttk.Label(cf, textvariable=self._cluster_count_var,
                  foreground=COLORS["primary"]).pack(side="left")
        _sv_tree_btn = tk.StringVar(value=self._t("cl.tree_btn"))
        ttk.Button(cf, textvariable=_sv_tree_btn, command=self._show_cluster_tree).pack(side="left", padx=14)
        self._lang_widgets.append((_sv_tree_btn, "cl.tree_btn"))
        _sv_tl = tk.StringVar(value=self._t("cl.timeline"))
        ttk.Button(cf, textvariable=_sv_tl, command=self._show_cluster_timeline).pack(side="left", padx=4)
        self._lang_widgets.append((_sv_tl, "cl.timeline"))
        _sv_as = tk.StringVar(value=self._t("cl.assign_side"))
        ttk.Button(cf, textvariable=_sv_as, command=self._assign_cluster_side).pack(side="left", padx=4)
        self._lang_widgets.append((_sv_as, "cl.assign_side"))

        # Cluster description field
        df = ttk.Frame(f); df.pack(fill="x", padx=14, pady=(0,4))
        _sv_desc = tk.StringVar(value=self._t("cl.desc"))
        ttk.Label(df, textvariable=_sv_desc).pack(side="left")
        self._lang_widgets.append((_sv_desc, "cl.desc"))
        self._cluster_desc_var = tk.StringVar()
        ttk.Entry(df, textvariable=self._cluster_desc_var, width=50).pack(side="left", padx=6)
        ttk.Button(df, text="💾", command=self._save_cluster_desc, width=3).pack(side="left")

        # Interpretation
        self._cluster_text_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self._cluster_text_var,
                  foreground="#444466", font=("Segoe UI", 9),
                  wraplength=900, justify="left").pack(anchor="w", padx=14, pady=(0,6))

        # Pane: Cluster-Liste | Mitglieder | Gegenseitige cM
        pane = ttk.PanedWindow(f, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=14, pady=4)

        # Linke Seite: Cluster-Liste
        left = ttk.LabelFrame(pane, text=self._t("cl.frm_left"), padding=6)
        self._lang_widgets.append((left, "cl.frm_left"))
        pane.add(left, weight=1)
        self._cluster_list = ttk.Treeview(left, columns=("cid","count","max_cm","top","quality"),
                                           show="headings", selectmode="browse")
        for col, (key, w) in {
            "cid"     : ("cl.cid",     50),
            "count"   : ("cl.count",   55),
            "max_cm"  : ("cl.maxcm",   65),
            "top"     : ("cl.top",    175),
            "quality" : ("cl.quality", 80),
        }.items():
            self._cluster_list.heading(col, text=self._t(key))
            self._cluster_list.column(col, width=w, stretch=(col=="top"),
                                       anchor="center" if col in ("quality","count") else "w")
            self._lang_headings.append((self._cluster_list, col, key))
        sy1 = ttk.Scrollbar(left, orient="vertical", command=self._cluster_list.yview)
        self._cluster_list.configure(yscrollcommand=sy1.set)
        self._cluster_list.pack(side="left", fill="both", expand=True)
        sy1.pack(side="right", fill="y")
        self._cluster_list.bind("<<TreeviewSelect>>", self._on_cluster_select)

        # Mittlere Seite: Mitglieder
        mid = ttk.LabelFrame(pane, text=self._t("cl.frm_mid"), padding=6)
        self._lang_widgets.append((mid, "cl.frm_mid"))
        pane.add(mid, weight=2)
        self._member_tree = ttk.Treeview(mid, columns=("name","cm","rel","baum"),
                                          show="headings", selectmode="browse")
        for col, (key, w, anchor) in {
            "name": ("mb.name", 190, "w"),
            "cm"  : ("mb.cm",    60, "e"),
            "rel" : ("mb.rel",  150, "w"),
            "baum": ("mb.baum",  55, "center"),
        }.items():
            self._member_tree.heading(col, text=self._t(key))
            self._member_tree.column(col, width=w, anchor=anchor, stretch=(col=="name"))
            self._lang_headings.append((self._member_tree, col, key))
        sy2 = ttk.Scrollbar(mid, orient="vertical", command=self._member_tree.yview)
        self._member_tree.configure(yscrollcommand=sy2.set)
        self._member_tree.pack(side="left", fill="both", expand=True)
        sy2.pack(side="right", fill="y")

        # Rechte Seite: Paarweise cM zwischen Mitgliedern
        right = ttk.LabelFrame(pane, text=self._t("cl.frm_right"), padding=6)
        self._lang_widgets.append((right, "cl.frm_right"))
        pane.add(right, weight=2)
        self._pairwise_tree = ttk.Treeview(right, columns=("a","b","cm"),
                                            show="headings", selectmode="none")
        for col, (key, w, anch) in {
            "a":  ("pw.a",  190, "w"),
            "b":  ("pw.b",  190, "w"),
            "cm": ("pw.cm",  90, "e"),
        }.items():
            self._pairwise_tree.heading(col, text=self._t(key))
            self._pairwise_tree.column(col, width=w, anchor=anch, stretch=(col in ("a","b")))
            self._lang_headings.append((self._pairwise_tree, col, key))
        sy3 = ttk.Scrollbar(right, orient="vertical", command=self._pairwise_tree.yview)
        self._pairwise_tree.configure(yscrollcommand=sy3.set)
        self._pairwise_tree.pack(side="left", fill="both", expand=True)
        sy3.pack(side="right", fill="y")

        self._clusters: dict = {}

    def _refresh_cluster(self):
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return
        try:
            min_prim   = float(self._cluster_min_cm_var.get() or 20)
            max_prim   = float(self._cluster_max_cm_var.get() or 400)
            min_shared = float(self._cluster_shared_cm_var.get() or 20)
        except ValueError:
            min_prim, max_prim, min_shared = 20.0, 400.0, 20.0

        shared_data = self._db.get_all_shared_for_cluster(
            test_guid, min_prim, min_shared,
            max_cm_primary=max_prim, max_cm_shared=max_prim)
        if not shared_data:
            messagebox.showinfo("Keine Daten",
                                "Keine Shared Matches im gewählten cM-Bereich.\n\n"
                                "Mögliche Ursachen:\n"
                                "• Noch keine Shared Matches heruntergeladen "
                                "(Tab Herunterladen → B)\n"
                                f"• Keine primären Matches zwischen {min_prim:.0f} "
                                f"und {max_prim:.0f} cM — Bereich anpassen.")
            return

        self._clusters = build_clusters(shared_data, min_prim, min_shared,
                                        max_cm_primary=max_prim)
        self._cluster_count_var.set(f"{len(self._clusters)} Cluster")
        self._cluster_text_var.set(suggest_grandparent_lines(self._clusters))

        # Seiten-Map für alle Cluster-Mitglieder vorladen
        all_guids = [m["guid"] for mlist in self._clusters.values() for m in mlist]
        side_map: dict[str, str] = {}
        if all_guids:
            try:
                with self._db._cursor() as _cur:
                    _rows = _cur.execute(
                        "SELECT match_guid, paternal_maternal FROM matches "
                        "WHERE match_guid IN ({})".format(",".join("?" * len(all_guids))),
                        all_guids,
                    ).fetchall()
                side_map = {r["match_guid"]: (r["paternal_maternal"] or "") for r in _rows}
            except Exception:
                pass
        self._cluster_side_colors: dict[int, str] = {}

        # Dichte pro Cluster aus shared_data berechnen (undirected unique pairs)
        _cluster_member_sets: dict[int, set] = {
            cid: {m["guid"] for m in mlist}
            for cid, mlist in self._clusters.items()
        }
        _guid_to_cid: dict[str, int] = {}
        for cid, guids in _cluster_member_sets.items():
            for g in guids:
                _guid_to_cid[g] = cid
        _edge_counts: dict[int, int] = {}
        _seen_pairs: set = set()
        for row in shared_data:
            ga, gb = row["match_guid_a"], row["match_guid_b"]
            ca, cb = _guid_to_cid.get(ga), _guid_to_cid.get(gb)
            if ca is not None and ca == cb:
                pair = (ga, gb) if ga < gb else (gb, ga)
                if pair not in _seen_pairs:
                    _seen_pairs.add(pair)
                    _edge_counts[ca] = _edge_counts.get(ca, 0) + 1

        # Cluster-Liste füllen
        self._cluster_list.delete(*self._cluster_list.get_children())
        cluster_colors = COLORS["cluster"]
        for cid, members in self._clusters.items():
            cms   = [m["cm"] for m in members]
            sides = [side_map.get(m["guid"], "") for m in members]
            n_pat = sides.count("paternal")
            n_mat = sides.count("maternal")
            n_known = n_pat + n_mat
            if n_known >= max(3, len(members) // 2):
                if n_pat / n_known >= 0.7:
                    color = "#DDF0FF"
                    side_icon = "🔵 "
                elif n_mat / n_known >= 0.7:
                    color = "#FFE0E0"
                    side_icon = "🔴 "
                else:
                    color = cluster_colors[(cid - 1) % len(cluster_colors)]
                    side_icon = ""
            else:
                color = cluster_colors[(cid - 1) % len(cluster_colors)]
                side_icon = ""
            self._cluster_side_colors[cid] = color
            n = len(members)
            possible = n * (n - 1) / 2
            density = (_edge_counts.get(cid, 0) / possible) if possible > 0 else 0.0
            try:
                from core.treematch import cluster_confidence
                med_cm = sum(m["cm"] for m in members) / n if n else 0.0
                conf_result = cluster_confidence(n, density, median_cm=med_cm)
                realness = conf_result.get("realness", 0)
                quality_icon = "🟢" if realness >= 0.85 else ("🟡" if realness >= 0.5 else "🔴")
            except Exception:
                quality_icon = "—"
            quality_icon = f"{quality_icon} {density:.0%}"
            top_name = side_icon + (members[0]["name"] if members else "")
            self._cluster_list.insert("", "end", iid=str(cid),
                                       tags=(f"c{cid}",),
                                       values=(f"#{cid}", len(members),
                                               f"{max(cms):.0f}",
                                               top_name,
                                               quality_icon))
            self._cluster_list.tag_configure(f"c{cid}", background=color)

        self._member_tree.delete(*self._member_tree.get_children())

    def _on_cluster_select(self, _):
        sel = self._cluster_list.selection()
        if not sel: return
        cid = int(sel[0])
        members = self._clusters.get(cid, [])
        # Load saved description
        descs = self._load_ui_settings().get("cluster_descs", {})
        if hasattr(self, "_cluster_desc_var"):
            self._cluster_desc_var.set(descs.get(str(cid), ""))
        color = getattr(self, "_cluster_side_colors", {}).get(
            cid, COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])])

        # Build guid → match lookup for tree-link indicators
        test_guid = self._current_guid()
        guid_match: dict = {}
        if test_guid:
            try:
                guid_match = {m.match_guid: m for m in self._db.get_matches(test_guid)}
            except Exception:
                pass

        self._member_tree.delete(*self._member_tree.get_children())
        self._member_tree.tag_configure("row", background=color)
        for m in members:
            match = guid_match.get(m["guid"])
            if match and getattr(match, "linked_in_tree", False):
                baum_val = "🔗 Baum"
            elif match and getattr(match, "has_tree", False):
                baum_val = "🌳"
            else:
                baum_val = "—"
            self._member_tree.insert("", "end", tags=("row",),
                                      values=(m["name"], f"{m['cm']:.1f}",
                                              m.get("rel",""), baum_val))

        # Paarweise cM zwischen den Cluster-Mitgliedern
        self._pairwise_tree.delete(*self._pairwise_tree.get_children())
        test_guid = self._current_guid()
        if test_guid and len(members) >= 2:
            guids = [m["guid"] for m in members]
            guid_name = {m["guid"]: m["name"] for m in members}
            pairs = self._db.get_pairwise_shared(test_guid, guids)
            self._pairwise_tree.tag_configure("row", background=color)
            for a, b, cm in pairs:
                if cm > 0:
                    self._pairwise_tree.insert("", "end", tags=("row",), values=(
                        guid_name.get(a, a[:12]),
                        guid_name.get(b, b[:12]),
                        f"{cm:.0f}"))

    def _show_cluster_tree(self):
        """Stammbaum-Analyse: Ahnentafeln aller Cluster-Mitglieder zusammenführen.

        Zeigt welche Vorfahren über mehrere Mitglieder hinweg gemeinsam auftauchen –
        das sind die wahrscheinlichen gemeinsamen Vorfahren des Clusters.
        """
        sel = self._cluster_list.selection()
        if not sel:
            messagebox.showinfo("Kein Cluster",
                                "Bitte zuerst einen Cluster in der Liste auswählen.")
            return
        cid = int(sel[0])
        members = self._clusters.get(cid, [])
        if not members:
            return

        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return

        guids   = {m["guid"] for m in members}
        id_name = {m["guid"]: m["name"] for m in members}
        id_cm   = {m["guid"]: m["cm"]   for m in members}

        all_peds = self._db.get_all_pedigrees(test_guid)

        # ── Vorfahren zusammenführen ─────────────────────────────────────────
        # Schlüssel: (Nachname normiert, Geburtsjahrzehnt) → Aggregat-Dict
        merged: dict = {}
        for guid in guids:
            if guid not in all_peds:
                continue
            for row in all_peds[guid]["rows"]:
                sn  = (row.get("surname")    or "").strip()
                gn  = (row.get("given_name") or "").strip()
                by  = row.get("birth_year")
                gen = row.get("generation") or 0
                bp  = (row.get("birth_place") or "").strip()
                sn_norm = sn.lower()
                by_key  = round(int(by) / 5) * 5 if by else 0
                key = (sn_norm, by_key)
                if key not in merged:
                    merged[key] = {
                        "surname": sn, "given": gn,
                        "birth_year": str(by) if by else "",
                        "birth_place": bp,
                        "generations": set(),   # alle Gen.-Werte (auch Mehrfachauftreten)
                        "guid_gens":   {},       # guid → {gen, ...} für Annotationen
                        "guids": set(),
                        "names": set(),
                    }
                ent = merged[key]
                ent["guids"].add(guid)
                ent["names"].add(id_name.get(guid, guid[:10]))
                if gen:
                    ent["generations"].add(gen)
                    ent["guid_gens"].setdefault(guid, set()).add(gen)
                if bp and not ent["birth_place"]:
                    ent["birth_place"] = bp

        persons = sorted(merged.values(),
                         key=lambda p: (-len(p["guids"]),
                                        min(p["generations"]) if p["generations"] else 99))

        # ── Fenster ──────────────────────────────────────────────────────────
        color = COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])]
        win = tk.Toplevel(self)
        win.title(f"Cluster #{cid} – Stammbaum-Analyse ({len(members)} Matches)")
        win.geometry("1150x680")
        win.configure(bg=color)

        n_total = len(members)
        ttk.Label(win,
                  text=f"Cluster #{cid} · {n_total} Mitglieder · "
                       f"{len(persons)} einzigartige Vorfahren in den Ahnentafeln",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10,0))
        ttk.Label(win,
                  text="Grün = alle Mitglieder teilen diese Person  |  "
                       "Gelb = ≥3 Mitglieder  |  Orange = 2 Mitglieder  |  "
                       "Weiß = nur 1 Mitglied  →  mehr Übereinstimmungen = wahrscheinlicherer Vorfahre",
                  foreground="#333333").pack(anchor="w", padx=12, pady=(2,6))

        cols  = ("count","person","birth","place","gen","matches")
        heads = {
            "count":   ("ct.count",   45),
            "person":  ("ct.person", 220),
            "birth":   ("ct.birth",   65),
            "place":   ("ct.place",  180),
            "gen":     ("ct.gen",     55),
            "matches": ("ct.matches", 500),
        }
        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=4)
        tv = ttk.Treeview(frame, columns=cols, show="headings")
        for c, (key, w) in heads.items():
            tv.heading(c, text=self._t(key), command=lambda c=c: _sort(c))
            tv.column(c, width=w,
                      anchor=("center" if c in ("count","birth","gen") else "w"),
                      stretch=(c == "matches"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tv.tag_configure("all",   background="#D6F5E3")   # alle Mitglieder
        tv.tag_configure("many",  background="#FFD6D6")   # ≥3
        tv.tag_configure("two",   background="#FFF3CD")   # 2
        tv.tag_configure("one",   background="#FFFFFF")   # 1

        st = {"col": "count", "desc": True}

        def _fill():
            col, desc = st["col"], st["desc"]
            sort_key = {
                "count":  lambda p: -len(p["guids"]),
                "person": lambda p: (p["surname"] + " " + p["given"]).lower(),
                "birth":  lambda p: p["birth_year"] or "9999",
                "place":  lambda p: p["birth_place"].lower(),
                "gen":    lambda p: min(p["generations"]) if p["generations"] else 99,
                "matches":lambda p: ", ".join(sorted(p["names"])),
            }
            data = sorted(persons, key=sort_key.get(col, sort_key["count"]),
                          reverse=(desc and col == "count"))
            tv.delete(*tv.get_children())
            for p in data:
                n = len(p["guids"])
                nm = f"{p['given']} {p['surname']}".strip() or "?"
                all_gens = sorted(p["generations"])
                gen_str = "/".join(str(g) for g in all_gens)
                show_gen_ann = len(all_gens) > 1
                match_parts = []
                for guid in sorted(p["guids"], key=lambda g: id_name.get(g, g)):
                    mname = id_name.get(guid, guid[:10])
                    if show_gen_ann:
                        gg = sorted(p["guid_gens"].get(guid, set()))
                        if gg:
                            mname += f" ({', '.join(str(g) for g in gg)})"
                    match_parts.append(mname)
                ms = ", ".join(match_parts)
                tag = ("all" if n >= n_total and n_total > 1
                       else "many" if n >= 3
                       else "two" if n >= 2
                       else "one")
                tv.insert("", "end", tags=(tag,), values=(
                    n, nm, p["birth_year"], p["birth_place"],
                    gen_str, ms))

        def _sort(col):
            st["desc"] = not st["desc"] if st["col"] == col else True
            st["col"] = col
            _fill()

        _fill()

        n_shared = sum(1 for p in persons if len(p["guids"]) >= 2)
        n_all    = sum(1 for p in persons if len(p["guids"]) >= n_total and n_total > 1)
        ttk.Label(win,
                  text=(f"Personen in ≥2 Bäumen: {n_shared}  |  "
                        f"In allen {n_total} Bäumen: {n_all}  "
                        f"(Klick auf Spaltenköpfe = sortieren)"),
                  foreground="#444444").pack(anchor="w", padx=12, pady=(0,6))

        # Mitglieder-Übersicht
        mf = ttk.LabelFrame(win, text="Cluster-Mitglieder", padding=4)
        mf.pack(fill="x", padx=12, pady=(0,8))
        for i, m in enumerate(sorted(members, key=lambda x: -(x["cm"] or 0))):
            ttk.Label(mf, text=f"#{i+1} {m['name']}  ({m['cm']:.0f} cM)",
                      foreground=COLORS["primary"]).grid(
                row=0, column=i, padx=10, pady=2, sticky="w")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 5: STATISTIKEN
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_stats(self):
        f = self._tab_stats
        _sv = tk.StringVar(value=self._t("st.refresh"))
        ttk.Button(f, textvariable=_sv,
                   command=self._refresh_stats).pack(anchor="ne", padx=14, pady=8)
        self._lang_widgets.append((_sv, "st.refresh"))

        kz = ttk.LabelFrame(f, text=self._t("st.kz"), padding=10)
        kz.pack(fill="x", padx=14, pady=4)
        self._lang_widgets.append((kz, "st.kz"))

        self._stat_vars: dict[str, tk.StringVar] = {}
        stat_label_keys = [
            ("total",               "st.total"),
            ("max_cm",              "st.max_cm"),
            ("avg_cm",              "st.avg_cm"),
            ("starred_count",       "st.starred"),
            ("with_tree",           "st.with_tree"),
            ("with_note",           "st.with_note"),
            ("shared_total",        "st.shared_tot"),
            ("shared_primary_count","st.shared_pri"),
        ]
        for i, (stat_key, t_key) in enumerate(stat_label_keys):
            sv_lbl = tk.StringVar(value=self._t(t_key))
            ttk.Label(kz, textvariable=sv_lbl, foreground="#555555").grid(
                row=i // 4, column=(i % 4) * 2, sticky="e", padx=(14,4), pady=3)
            self._lang_widgets.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(kz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(
                row=i // 4, column=(i % 4) * 2 + 1, sticky="w")
            self._stat_vars[stat_key] = var

        # Pedigree completeness section
        pz = ttk.LabelFrame(f, text=self._t("st.ped_kz"), padding=10)
        pz.pack(fill="x", padx=14, pady=4)
        self._lang_widgets.append((pz, "st.ped_kz"))
        ped_label_keys = [
            ("ped_loaded", "st.ped_loaded"),
            ("ped_avg_depth", "st.ped_depth"),
            ("ped_surnames", "st.ped_surn"),
        ]
        for i, (stat_key, t_key) in enumerate(ped_label_keys):
            sv_lbl = tk.StringVar(value=self._t(t_key))
            ttk.Label(pz, textvariable=sv_lbl, foreground="#555555").grid(
                row=0, column=i*2, sticky="e", padx=(14,4), pady=3)
            self._lang_widgets.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(pz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(row=0, column=i*2+1, sticky="w")
            self._stat_vars[stat_key] = var

        # GEDCOM bridge section
        gz = ttk.LabelFrame(f, text=self._t("st.ged_kz"), padding=10)
        gz.pack(fill="x", padx=14, pady=4)
        self._lang_widgets.append((gz, "st.ged_kz"))
        ged_label_keys = [
            ("gedcom_persons", "st.ged_pers"),
            ("gedcom_linked",  "st.ged_linked"),
        ]
        for i, (stat_key, t_key) in enumerate(ged_label_keys):
            sv_lbl = tk.StringVar(value=self._t(t_key))
            ttk.Label(gz, textvariable=sv_lbl, foreground="#555555").grid(
                row=0, column=i*2, sticky="e", padx=(14,4), pady=3)
            self._lang_widgets.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(gz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(row=0, column=i*2+1, sticky="w")
            self._stat_vars[stat_key] = var

        # Seitenzuweisung section
        sz = ttk.LabelFrame(f, text=self._t("st.side_kz"), padding=10)
        sz.pack(fill="x", padx=14, pady=4)
        self._lang_widgets.append((sz, "st.side_kz"))
        side_label_keys = [
            ("side_paternal", "st.side_pat"),
            ("side_maternal", "st.side_mat"),
            ("side_unset",    "st.side_open"),
        ]
        for i, (stat_key, t_key) in enumerate(side_label_keys):
            sv_lbl = tk.StringVar(value=self._t(t_key))
            ttk.Label(sz, textvariable=sv_lbl, foreground="#555555").grid(
                row=0, column=i*2, sticky="e", padx=(14,4), pady=3)
            self._lang_widgets.append((sv_lbl, t_key))
            var = tk.StringVar(value="—")
            ttk.Label(sz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(row=0, column=i*2+1, sticky="w")
            self._stat_vars[stat_key] = var

        # Kits & Matches section
        kf = ttk.LabelFrame(f, text=self._t("st.kit_kz"), padding=10)
        kf.pack(fill="x", padx=14, pady=4)
        self._lang_widgets.append((kf, "st.kit_kz"))
        self._kit_stat_tree = ttk.Treeview(kf, columns=("kit", "count"),
                                            show="headings", height=4)
        self._kit_stat_tree.heading("kit",   text="Kit")
        self._kit_stat_tree.heading("count", text="Matches")
        self._kit_stat_tree.column("kit",   width=280)
        self._kit_stat_tree.column("count", width=80, anchor="e")
        self._kit_stat_tree.pack(fill="x")

        # Progress ring section
        ring_frame = ttk.Frame(f); ring_frame.pack(fill="x", padx=14, pady=4)
        self._ring_canvas = tk.Canvas(ring_frame, height=90, bg=COLORS["bg"],
                                       highlightthickness=0)
        self._ring_canvas.pack(fill="x")
        self._stat_ring_data: dict = {}

        rf = ttk.LabelFrame(f, text=self._t("st.rel_dist"), padding=10)
        rf.pack(fill="both", expand=True, padx=14, pady=4)
        self._lang_widgets.append((rf, "st.rel_dist"))
        self._rel_tree = ttk.Treeview(rf, columns=("rel","count"), show="headings", height=10)
        self._rel_tree.heading("rel",   text=self._t("st.rel"))
        self._rel_tree.heading("count", text=self._t("st.count"))
        self._rel_tree.column("rel",    width=300)
        self._rel_tree.column("count",  width=80, anchor="e")
        self._rel_tree.pack(fill="both", expand=True)
        self._lang_headings.append((self._rel_tree, "rel",   "st.rel"))
        self._lang_headings.append((self._rel_tree, "count", "st.count"))
        self._refresh_stats()

    def _refresh_stats(self):
        stats = self._db.get_statistics()
        for key, var in self._stat_vars.items():
            v = stats.get(key)
            var.set(f"{v:.1f}" if isinstance(v, float) else str(v) if v is not None else "—")
        self._rel_tree.delete(*self._rel_tree.get_children())
        for rel, cnt in stats.get("relationship_breakdown", []):
            self._rel_tree.insert("", "end", values=(rel, cnt))
        self._kit_stat_tree.delete(*self._kit_stat_tree.get_children())
        for kit_name, cnt in stats.get("kit_breakdown", []):
            self._kit_stat_tree.insert("", "end", values=(kit_name, cnt))
        self._draw_stat_rings(stats)

    def _draw_stat_rings(self, stats: dict):
        """Draw three progress-ring indicators on the statistics canvas."""
        c = self._ring_canvas
        c.delete("all")
        total = stats.get("total") or 0
        if total == 0:
            c.create_text(20, 45, text="—", anchor="w", fill="#888888",
                          font=("Segoe UI", 10))
            return
        with_tree   = stats.get("with_tree", 0) or 0
        ped_loaded  = stats.get("ped_loaded", 0) or 0
        # Attempt to get side-known count from DB
        try:
            tg = self._current_test_guid or self._get_kit_guid()
            if tg:
                with self._db._cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                        "AND paternal_maternal != '' AND paternal_maternal IS NOT NULL", (tg,))
                    side_known = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                        "AND endogamy_cluster != '' AND endogamy_cluster IS NOT NULL", (tg,))
                    endo_known = cur.fetchone()[0]
            else:
                side_known = endo_known = 0
        except Exception:
            side_known = endo_known = 0

        gedcom_linked = stats.get("gedcom_linked", 0) or 0
        rings = [
            (with_tree / total,    f"{with_tree}/{total}",      "Mit Baum",      COLORS["accent"]),
            (ped_loaded / max(with_tree, 1), f"{ped_loaded}/{with_tree}", "Ahnentafel", COLORS["success"]),
            (side_known / total,   f"{side_known}/{total}",     "Seite bekannt", "#8B4513"),
            (gedcom_linked / total, f"{gedcom_linked}/{total}", "GEDCOM-Treffer", COLORS["primary"]),
        ]
        R = 35; cx_start = 55
        for i, (pct, label_cnt, title, color) in enumerate(rings):
            cx = cx_start + i * 160
            cy = 45
            # Background arc
            c.create_arc(cx-R, cy-R, cx+R, cy+R, start=90, extent=360,
                          style="arc", outline=COLORS["light"], width=8)
            # Progress arc
            extent = max(1, min(360, int(pct * 360)))
            c.create_arc(cx-R, cy-R, cx+R, cy+R, start=90, extent=-extent,
                          style="arc", outline=color, width=8)
            # Center text
            c.create_text(cx, cy - 6, text=f"{pct*100:.0f}%",
                          font=("Segoe UI", 10, "bold"), fill=COLORS["text"])
            c.create_text(cx, cy + 8, text=label_cnt,
                          font=("Segoe UI", 7), fill="#777777")
            c.create_text(cx, cy + R + 12, text=title,
                          font=("Segoe UI", 8), fill=COLORS["text"])

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

        import json, csv, re

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

    def _get_kit_guid(self) -> Optional[str]:
        return self._kit_map.get(self._kit_var.get()) if hasattr(self,"_kit_var") else None

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
                self.after(0, lambda: (
                    messagebox.showinfo(
                        "GEDmatch-Brücke",
                        f"{n} GEDmatch-Match/es mit Ancestry/MH-Matches verknüpft.\n"
                        "⚡-Badge erscheint in der Match-Liste wenn Brücke bekannt."
                    ),
                    self._refresh_match_table(),
                ))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
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
            text=f"Ancestry-Schätzung importieren (Tag 8 / Cluster-Code):",
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
        color = COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])]
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
                                             fill=COLORS["text"]))
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

        c = tk.Canvas(win, height=160, bg=COLORS["bg"], highlightthickness=0)
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
                              font=("Segoe UI", 7), fill=COLORS["text"], angle=45 if bw < 60 else 0)
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
            "Datenbank: " + cfg.DB_FILE)

    # ── Persistente Einstellungen ──────────────────────────────────────────────

    def _load_settings(self):
        """Lädt gespeicherte Einstellungen (Cookie-Pfad, Kit-GUID)."""
        import json, os
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
        import json, os
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
