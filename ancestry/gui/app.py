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
from importlib import import_module
from tkinter import messagebox, ttk
from typing import Optional
from urllib.parse import quote

from ancestry.core.api import AncestryApiClient
from ancestry.core.auth import AncestryAuth

# Export-Funktionen werden lazy geladen (nur im Menü-Callback)
# — spart ~4.5s Startup (openpyxl wird erst beim Export geladen)
from ancestry.core.cluster import build_clusters, suggest_grandparent_lines
from ancestry.core.database import Database
from ancestry.gui.state import AppState
from ancestry.gui.tabs.cluster import ClusterTab
from ancestry.gui._app_analysis_dialogs import AnalysisDialogsMixin
from ancestry.gui._app_enrichment_runs import EnrichmentRunsMixin
from ancestry.gui._app_export import ExportMixin
from ancestry.gui._app_gedcom_matching import GedcomMatchingMixin
from ancestry.gui._app_genealogy_export import GenealogyExportMixin
from ancestry.gui._app_kit_maintenance import KitMaintenanceMixin
from ancestry.gui._app_lifecycle import LifecycleMixin
from ancestry.gui._app_matches_bridge import MatchesBridgeMixin
from ancestry.gui._app_misc_dialogs import MiscDialogsMixin
from ancestry.gui._app_recent_files import RecentFilesMixin
from ancestry.gui._app_research_dialogs import ResearchDialogsMixin
from ancestry.gui._app_settings import SettingsMixin
from ancestry.gui._app_shortcuts import ShortcutsMixin
from ancestry.gui._app_stats_bridge import StatsBridgeMixin
from ancestry.gui._app_status import StatusMixin

# Eager loads (häufig genutzt)
from ancestry.gui.tabs.download import DownloadTab
from ancestry.gui.tabs.matches import MatchesTab
from ancestry.gui.widgets.log_handler import install_gui_log_handler
from ancestry.gui.widgets.status_bar import StatusBar
from ancestry.gui.widgets.theme import COLORS, COLORS_DARK, TRANSLATIONS, apply_style
from ancestry.models import DnaKit, DnaMatch, SharedMatch
from ancestry.paths import DB_PATH

# Lazy loads (gelegentlich genutzt) – werden via _lazy_import() beim Bedarf geladen

log = logging.getLogger(__name__)


def _lazy_import(module_path: str, class_name: str):
    """Lazy-import einer Tab-Klasse bei Bedarf."""
    module = import_module(module_path)
    return getattr(module, class_name)


class AncestryDnaApp(AnalysisDialogsMixin, EnrichmentRunsMixin, ExportMixin,
                     GedcomMatchingMixin, GenealogyExportMixin, KitMaintenanceMixin,
                     LifecycleMixin, MatchesBridgeMixin, MiscDialogsMixin,
                     RecentFilesMixin, ResearchDialogsMixin, SettingsMixin,
                     ShortcutsMixin, StatsBridgeMixin, StatusMixin, tk.Frame):
    # Wird schrittweise in Mixins aufgeteilt (Wartbarkeit, keine
    # Verhaltensänderung) — bisher ausgelagert: RecentFilesMixin
    # (ancestry/gui/_app_recent_files.py), ShortcutsMixin
    # (ancestry/gui/_app_shortcuts.py), AnalysisDialogsMixin
    # (ancestry/gui/_app_analysis_dialogs.py), ResearchDialogsMixin
    # (ancestry/gui/_app_research_dialogs.py), MiscDialogsMixin
    # (ancestry/gui/_app_misc_dialogs.py), MatchesBridgeMixin
    # (ancestry/gui/_app_matches_bridge.py), StatsBridgeMixin
    # (ancestry/gui/_app_stats_bridge.py), ExportMixin
    # (ancestry/gui/_app_export.py), SettingsMixin
    # (ancestry/gui/_app_settings.py), StatusMixin
    # (ancestry/gui/_app_status.py), LifecycleMixin
    # (ancestry/gui/_app_lifecycle.py), GenealogyExportMixin
    # (ancestry/gui/_app_genealogy_export.py), KitMaintenanceMixin
    # (ancestry/gui/_app_kit_maintenance.py), EnrichmentRunsMixin
    # (ancestry/gui/_app_enrichment_runs.py), GedcomMatchingMixin
    # (ancestry/gui/_app_gedcom_matching.py).

    # cM-Bereiche → wahrscheinliche Verwandtschaft (lo, hi, Label, Generation).
    # Einzige Quelle der Wahrheit auch für analysis/mrca.py.
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

        self._state = AppState(
            db=Database(str(DB_PATH)),
            startup_gedcom_path=gedcom_path,
        )

        # Aliase für bestehenden Code — zeigen auf state-Felder (kein Copy)
        self._db      = self._state.db
        self._auth    = None  # wird über _state.auth gesetzt wenn nötig
        self._client  = None
        self._scraper = None  # für nicht-Download-Scraper (refresh_links, cluster)
        self._kit_map               = self._state.kit_map
        self._lang_headings         = self._state.lang_headings
        self._lang_nb_tabs          = self._state.lang_nb_tabs
        self._lang_widgets          = self._state.lang_widgets
        self._lang_menus            = self._state.lang_menus
        self._lang_inner_nb_tabs    = self._state.lang_inner_nb_tabs
        self._pause_event           = self._state.pause_event
        self._dl_counters           = self._state.dl_counters

        self._startup_gedcom_path: str = gedcom_path
        self._lang: str    = "de"
        self._dark_mode:   bool  = False
        # Login-State (Cookie-Pfad + manuelle GUID). Der Login lebt jetzt im
        # Start-Tab; diese Vars werden vom dort eingehängten LoginTab geteilt und
        # hier weiterhin persistiert (settings.json).
        self._cookie_file_var = tk.StringVar()
        self._manual_guid_var = tk.StringVar()
        self.configure(bg=self._active_colors()["bg"])

        self._build_style()
        self._build_menu()
        self._build_main()
        self.after(200, self._bind_shortcuts)
        # ⚠️ _refresh_match_table() ist teuer (große DB) — asynchron laden
        # damit GUI schnell responsive ist (Startup <1s statt Minuten)
        self.after(50, self._refresh_match_table)

        if not self._embedded:
            self.winfo_toplevel().protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._load_settings)
        self.after(300, self._update_matches_kit_combo)
        self.after(400, self._load_lang_setting)
        self.after(600, self._maybe_show_checklist)
        self.after(1000, self._heartbeat)

    def _heartbeat(self):
        """Lebenszeichen für den Hang-Watchdog: solange die Tk-Hauptschleife
        läuft, wird dies im Sekundentakt aufgerufen. Bleibt es aus, weiß der
        Watchdog, dass der Main-Thread hängt, und schreibt einen Stack-Dump."""
        try:
            from ancestry.utils.watchdog import beat
            beat()
        except Exception:
            pass
        self.after(1000, self._heartbeat)

    def mainloop(self, *a, **k):
        """Standalone-Kompatibilität: leitet an das Toplevel weiter."""
        self.winfo_toplevel().mainloop(*a, **k)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _build_style(self):
        apply_style(self, self._active_colors())

    # ── Theme / Dark mode ─────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._build_style()
        self._save_ui_settings(dark_mode=self._dark_mode)

    def set_theme(self, dark: bool):
        """Setzt das Theme explizit (für den globalen Hell/Dunkel-Schalter)."""
        self._dark_mode = bool(dark)
        try:
            self._build_style()
            self.configure(bg=self._active_colors()["bg"])
        except Exception:
            pass

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
        # D1: "Zuletzt geöffnet" Untermenü
        self._recent_menu = tk.Menu(fm, tearoff=False)
        fm.add_cascade(label="Zuletzt geöffnet ▶", menu=self._recent_menu)
        fm.add_separator()
        fm.add_command(label=self._t("mn.quit"),       command=self._on_close)
        mb.add_cascade(label=self._t("mn.file"), menu=fm)
        for idx, key in [(0,"mn.exp_csv"),(1,"mn.exp_xlsx"),(2,"mn.exp_sh_csv"),
                         (3,"mn.exp_all"),(5,"mn.imp_names"),(9,"mn.quit")]:
            self._lang_menus.append((fm, idx, key))
        self._lang_menus.append((mb, 0, "mn.file"))
        # Populate recent files submenu after menu is built
        self.after(0, self._recent_menu_rebuild)

        vm = tk.Menu(mb, tearoff=False)
        vm.add_command(label=self._t("mn.refresh_t"), command=self._refresh_match_table)
        vm.add_command(label=self._t("mn.recalc_cl"),
                       command=lambda: self._cluster_tab and self._cluster_tab.refresh())
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
        am.add_command(label=self._t("mn.seg_triang"),  command=self._show_triangulation)
        am.add_separator()
        am.add_command(label=self._t("mn.reset_sh"),    command=self._reset_shared_matches)
        am.add_command(label=self._t("mn.reset_nm"),    command=self._reset_name_attempts)
        am.add_separator()
        am.add_command(label=self._t("mn.refresh_lk"),  command=self._refresh_links)
        am.add_separator()
        am.add_command(label=self._t("mn.surnames"),    command=self._show_surname_analysis)
        am.add_command(label=self._t("mn.places"),      command=self._show_place_analysis)
        am.add_command(label=self._t("mn.mrca"),        command=self._show_mrca_analysis)
        am.add_command(label=self._t("mn.net_graph"),   command=self._show_network_graph)
        am.add_separator()
        am.add_command(label=self._t("mn.exp_ged"),     command=self._export_gedcom)
        am.add_command(label=self._t("mn.exp_gramps"),  command=self._export_gramps)
        am.add_command(label=self._t("mn.imp_mta"),     command=self._import_mta)
        am.add_separator()
        am.add_command(label=self._t("mn.ped_gaps"),    command=self._show_pedigree_gaps)
        am.add_command(label=self._t("mn.ped_chart"),  command=self._show_pedigree_chart)
        am.add_command(label=self._t("mn.endo_score"),  command=self._show_endogamy_analysis)
        am.add_command(label=self._t("mn.pop_stats"),   command=self._show_population_stats)
        am.add_separator()
        am.add_command(label=self._t("mn.dashboard"),   command=self._show_research_dashboard)
        am.add_command(label=self._t("mn.copilot_cl"),  command=self._copilot_explain_cluster)
        am.add_separator()
        am.add_command(label=self._t("mn.sur_matrix"),  command=self._show_surname_matrix)
        am.add_command(label="🔗 Entity-Kandidaten prüfen",
                       command=self._show_entity_review)
        am.add_command(label="🔍 Kirchenbuch-Personensuche (NER)",
                       command=self._show_ner_search)
        mb.add_cascade(label=self._t("mn.analysis"), menu=am)
        for idx, key in [(0,"mn.anc_groups"),(1,"mn.exp_anc"),(3,"mn.pedigree"),
                         (4,"mn.ped_overlay"),(6,"mn.own_tree"),(7,"mn.sh_cluster"),
                         (8,"mn.seg_triang"),
                         (10,"mn.reset_sh"),(11,"mn.reset_nm"),(13,"mn.refresh_lk"),
                         (15,"mn.surnames"),(16,"mn.places"),
                         (17,"mn.mrca"),(18,"mn.net_graph"),
                         (20,"mn.exp_ged"),(21,"mn.imp_mta"),
                         (23,"mn.ped_gaps"),(24,"mn.ped_chart"),
                         (25,"mn.endo_score"),(26,"mn.pop_stats"),
                         (28,"mn.dashboard"),(29,"mn.copilot_cl"),
                         (31,"mn.sur_matrix")]:
            self._lang_menus.append((am, idx, key))
        self._lang_menus.append((mb, 2, "mn.analysis"))

        hm = tk.Menu(mb, tearoff=False)
        hm.add_command(label=self._t("mn.shortcuts"), command=self._show_shortcuts)
        hm.add_separator()
        hm.add_command(label=self._t("mn.about"), command=self._show_about)
        mb.add_cascade(label=self._t("mn.help"), menu=hm)
        self._lang_menus.append((hm, 0, "mn.shortcuts"))
        self._lang_menus.append((hm, 2, "mn.about"))
        self._lang_menus.append((mb, 3, "mn.help"))

    # ── Hauptlayout ───────────────────────────────────────────────────────────

    def _add_error_tab(self, key: str, exc: Exception):
        """Fügt einen Platzhalter-Reiter mit Fehlertext ein, statt die gesamte
        App-Init abzubrechen, wenn ein einzelner Reiter nicht aufgebaut werden
        kann. Die übrigen Reiter bleiben nutzbar."""
        log.exception("Reiter '%s' konnte nicht aufgebaut werden", key)
        try:
            ph = ttk.Frame(self._nb)
            ttk.Label(
                ph,
                text=("⚠ Dieser Reiter konnte nicht geladen werden.\n\n"
                      f"{type(exc).__name__}: {exc}\n\n"
                      "Die übrigen Reiter funktionieren normal.\n"
                      "Details stehen im Log."),
                foreground="#b00020", justify="left", padding=24,
            ).pack(anchor="nw")
            self._nb.add(ph, text=self._t(key))
            self._lang_nb_tabs.append((ph, key))
        except Exception:
            log.exception("Konnte Platzhalter-Reiter '%s' nicht anlegen", key)

    def _build_main(self):
        hf = tk.Frame(self, bg=COLORS["primary"])
        hf.pack(fill="x")
        ttk.Label(hf, text="🧬  Ancestry DNA Tool",
                  style="Header.TLabel").pack(side="left", fill="x", expand=True)
        # Sprachauswahl liegt jetzt global oben rechts (unified.py); die
        # DNA-App wird darüber via set_language() umgeschaltet.

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=8, pady=8)
        # Statistik wird erst beim Öffnen des Reiters berechnet (nicht beim
        # Start) — siehe StatsTab.on_show().
        self._nb.bind("<<NotebookTabChanged>>", self._on_nb_tab_changed, add=True)
        self._nb.bind("<<NotebookTabChanged>>", lambda _: self._save_ui_settings(
            active_tab=self._nb.index("current")), add=True)

        # Jeder Reiter wird einzeln abgesichert: schlägt der Aufbau eines
        # Reiters fehl (z. B. wegen Datenlage), kommt ein Platzhalter statt
        # eines Komplettabsturzes der App. Tab-Attribute werden vorab auf None
        # gesetzt, damit Querverweise getattr-sicher sind.
        (self._login_tab, self._download_tab, self._matches_tab,
         self._cluster_tab, self._stats_tab, self._matricula_tab,
         self._persons_tab, self._tools_tab) = (None,) * 8

        # Login lebt jetzt im Start-Tab (siehe make_login_widget); der DNA-App-
        # Notebook beginnt direkt mit „Herunterladen".

        # Download-Tab als eigenständige Klasse
        try:
            self._download_tab = DownloadTab(
                self._nb, self._state,
                on_refresh_matches    = self._refresh_match_table,
                on_refresh_stats      = self._refresh_stats,
                on_refresh_kit_combos = self._update_matches_kit_combo,
                set_status            = self._set_status,
            )
            self._nb.add(self._download_tab, text=self._t("tab_download"))
            self._lang_nb_tabs.append((self._download_tab, "tab_download"))
            # Aliase für Code der noch self._kit_var / self._names_stop_btn direkt nutzt
            self._kit_var        = self._download_tab._kit_var
            self._names_stop_btn = self._download_tab._names_stop_btn
        except Exception as _exc:
            self._add_error_tab("tab_download", _exc)

        # Matches-Tab als eigenständige Klasse
        try:
            self._matches_tab = MatchesTab(
                self._nb, self._state,
                get_test_guid    = lambda: self._state.current_test_guid or self._get_kit_guid(),
                get_gedcom       = lambda: getattr(self, "_gedcom", None),
                load_ui_settings = self._load_ui_settings,
                save_ui_settings = self._save_ui_settings,
                set_status       = self._set_status,
                cm_ranges        = self._CM_RANGES,
                on_auto_assign_sides = self._auto_assign_sides,
                on_gedmatch_bridge   = self._run_gedmatch_bridge,
                on_goto_download     = lambda: (self._download_tab is not None
                                                 and self._nb.select(self._download_tab)),
                on_choose_gedcom     = lambda: self._ensure_gedcom_loaded(
                    self._on_gedcom_loaded_update_header, force_ask=True),
                on_gedcom_match_all  = self._run_gedcom_match_all,
                on_endogamy_transfer = self._run_endogamy_transfer,
                on_xref_review       = self._open_xref_review,
                on_ml_origin         = self._run_ml_origin,
                on_wikitree_extend   = self._run_wikitree_extend,
                on_origin_inference  = self._run_origin_inference,
                on_gedcom_header_update = self._on_gedcom_loaded_update_header,
            )
            self._nb.add(self._matches_tab, text=self._t("tab_matches"))
            self._lang_nb_tabs.append((self._matches_tab, "tab_matches"))
            # Aliase für Code der die Matches-Tab-Widgets noch direkt nutzt
            self._matches_kit_var   = self._matches_tab._matches_kit_var
            self._matches_kit_combo = self._matches_tab._matches_kit_combo
            self._ged_link_status   = self._matches_tab._ged_link_status
            self._ged_file_var      = self._matches_tab._ged_file_var
        except Exception as _exc:
            self._add_error_tab("tab_matches", _exc)

        # Cluster-Tab als eigenständige Klasse
        try:
            self._cluster_tab = ClusterTab(
                self._nb, self._state,
                get_test_guid    = lambda: self._state.current_test_guid or self._get_kit_guid(),
                get_current_guid = self._current_guid,
                load_ui_settings = self._load_ui_settings,
                save_ui_settings = self._save_ui_settings,
                set_status       = self._set_status,
                on_show_timeline = self._show_cluster_timeline,
                on_assign_side   = self._assign_cluster_side,
            )
            self._nb.add(self._cluster_tab, text=self._t("tab_cluster"))
            self._lang_nb_tabs.append((self._cluster_tab, "tab_cluster"))
        except Exception as _exc:
            self._add_error_tab("tab_cluster", _exc)

        # Heavy Tabs → asynchrone Initialisierung nach GUI-Rendering
        # Das spart erheblich Startup-Zeit, da diese Tabs komplex sind
        self.after(100, self._init_heavy_tabs)

        self._status_bar = StatusBar(self, bg=self._active_colors()["bg"])
        self._status_bar.pack(fill="x", side="bottom")
        # Kompatibilitäts-Alias: älterer Code der _status_var.set() nutzt
        self._status_var = self._status_bar._var

        # A2: Live-Zähler-Statuszeile
        self._live_bar = ttk.Frame(self)
        self._live_bar.pack(fill="x", side="bottom")
        self._live_bar_var = tk.StringVar(value="Matches: – | Personen: – | DB: –")
        ttk.Label(self._live_bar, textvariable=self._live_bar_var,
                  anchor="w", padding=(6, 1)).pack(fill="x")
        self.after(0, self._update_statusbar)

    def _init_heavy_tabs(self):
        """Initialisiert schwere Tabs asynchron nach GUI-Rendering.
        Das spart Startup-Zeit erheblich."""
        StatsTab = _lazy_import('ancestry.gui.tabs.stats', 'StatsTab')
        MatriculaTab = _lazy_import('ancestry.gui.tabs.matricula', 'MatriculaTab')
        PersonsTab = _lazy_import('ancestry.gui.tabs.persons', 'PersonsTab')
        ToolsTab = _lazy_import('ancestry.gui.tabs.tools', 'ToolsTab')

        # Stats-Tab
        try:
            self._stats_tab = StatsTab(
                self._nb, self._state,
                get_test_guid=lambda: self._state.current_test_guid or self._get_kit_guid(),
            )
            self._nb.add(self._stats_tab, text=self._t("tab_stats"))
            self._lang_nb_tabs.append((self._stats_tab, "tab_stats"))
            # Cache-Invalidierung: nach Download oder GEDCOM-Import dirty markieren
            # und ggf. sofort neuberechnen (wenn Reiter sichtbar).
            self._state.register_data_change(
                lambda src: self._invalidate_stats()
            )
        except Exception as _exc:
            self._add_error_tab("tab_stats", _exc)

        # Matricula-Tab
        try:
            self._matricula_tab = MatriculaTab(
                self._nb, self._state,
                set_status=self._set_status,
            )
            self._nb.add(self._matricula_tab, text=self._t("tab_matricula"))
            self._lang_nb_tabs.append((self._matricula_tab, "tab_matricula"))
        except Exception as _exc:
            self._add_error_tab("tab_matricula", _exc)

        # Personen-Tab
        try:
            self._persons_tab = PersonsTab(self._nb, self._state)
            self._nb.add(self._persons_tab, text=self._t("tab_persons"))
            self._lang_nb_tabs.append((self._persons_tab, "tab_persons"))
            if hasattr(self._persons_tab, "set_on_goto_matches"):
                self._persons_tab.set_on_goto_matches(self._goto_matches_for_wikitree)
        except Exception as _exc:
            self._add_error_tab("tab_persons", _exc)

        # Werkzeuge-Tab
        try:
            self._tools_tab = ToolsTab(self._nb, self._state)
            self._nb.add(self._tools_tab, text=self._t("tab_tools"))
            self._lang_nb_tabs.append((self._tools_tab, "tab_tools"))
        except Exception as _exc:
            self._add_error_tab("tab_tools", _exc)

    def _goto_matches_for_wikitree(self, name: str):
        """Wechselt zum Matches-Tab und setzt die Suche auf den WikiTree-Namen."""
        try:
            for i in range(self._nb.index("end")):
                tab_id = self._nb.tabs()[i]
                w = self._nb.nametowidget(tab_id)
                if hasattr(w, "_search_var"):   # MatchesTab hat _search_var
                    self._nb.select(i)
                    w._search_var.set(name)
                    self.after(50, w.refresh)
                    break
        except Exception as e:
            log.debug("goto_matches_for_wikitree: %s", e)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1: LOGIN  →  siehe ancestry/gui/tabs/login.py
    # ─────────────────────────────────────────────────────────────────────────

    def _on_login_done(self, auth, client, kits):
        """Callback von LoginTab nach erfolgreichem Login."""
        if auth:
            self._auth   = auth
            self._client = client
            self._state.auth   = auth
            self._state.client = client
        for kit in (kits or []):
            self._kit_map[kit.name] = kit.guid
            self._db.upsert_kit(kit)
        if self._download_tab is not None:
            self._download_tab.update_kit_combo()
        self._save_settings()

    def make_login_widget(self, parent):
        """Erzeugt das Login-Widget (Cookie-Datei + manuelle Kit-GUID) für die
        Einbettung im Start-Tab. Teilt die Cookie-/GUID-Vars dieser App, damit
        der Login-State weiterhin über settings.json persistiert wird."""
        from ancestry.gui.tabs.login import LoginTab
        return LoginTab(
            parent, self._state,
            on_login_success=self._on_login_done,
            on_status=self._set_status,
            on_switch_tab=lambda idx: None,
            cookie_var=self._cookie_file_var,
            guid_var=self._manual_guid_var,
        )

if __name__ == "__main__":
    # Komfort: `python -m ancestry.gui.app` startet die GUI über den
    # kanonischen Einstiegspunkt (inkl. Logging- und tkinter-Check).
    from ancestry.main import main
    main()
