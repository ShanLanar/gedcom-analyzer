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
from ancestry.gui.widgets.theme import COLORS, COLORS_DARK, TRANSLATIONS, apply_style, translate
from ancestry.gui.widgets.log_handler import install_gui_log_handler
from ancestry.gui.state import AppState
from ancestry.gui.tabs.stats import StatsTab
from ancestry.gui.tabs.login import LoginTab
from ancestry.gui.tabs.cluster import ClusterTab
from ancestry.gui.tabs.download import DownloadTab
from ancestry.gui.tabs.matches import MatchesTab
from ancestry.gui.tabs.matricula import MatriculaTab

log = logging.getLogger(__name__)


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
        self.configure(bg=self._active_colors()["bg"])

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
        apply_style(self, self._active_colors())

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
        vm.add_command(label=self._t("mn.recalc_cl"), command=lambda: self._cluster_tab.refresh())
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
                         (8,"mn.seg_triang"),
                         (10,"mn.reset_sh"),(11,"mn.reset_nm"),(13,"mn.refresh_lk"),
                         (14,"mn.chg_ged"),(16,"mn.surnames"),(17,"mn.places"),
                         (18,"mn.mrca"),(19,"mn.net_graph"),
                         (21,"mn.exp_ged"),(22,"mn.imp_mta"),
                         (24,"mn.ped_gaps"),(25,"mn.auto_sides"),(26,"mn.endo_score")]:
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

        # Login-Tab
        self._login_tab = LoginTab(
            self._nb, self._state,
            on_login_success=self._on_login_done,
            on_status=self._set_status,
            on_switch_tab=lambda idx: self._nb.select(idx),
        )
        self._nb.add(self._login_tab, text=self._t("tab_login"))
        self._lang_nb_tabs.append((self._login_tab, "tab_login"))
        # Aliase für Settings-Code der noch self._cookie_file_var / _manual_guid_var nutzt
        self._cookie_file_var = self._login_tab._cookie_file_var
        self._manual_guid_var = self._login_tab._manual_guid_var

        # Download-Tab als eigenständige Klasse
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

        # Matches-Tab als eigenständige Klasse
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
            on_goto_download     = lambda: self._nb.select(1),
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

        # Cluster-Tab als eigenständige Klasse
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

        # Stats-Tab als eigenständige Klasse
        self._stats_tab = StatsTab(
            self._nb, self._state,
            get_test_guid=lambda: self._state.current_test_guid or self._get_kit_guid(),
        )
        self._nb.add(self._stats_tab, text=self._t("tab_stats"))
        self._lang_nb_tabs.append((self._stats_tab, "tab_stats"))

        # Matricula-Tab: Kirchenbuch-Scans, läuft als Subprozess parallel zu DNA-Downloads
        self._matricula_tab = MatriculaTab(
            self._nb, self._state,
            set_status=self._set_status,
        )
        self._nb.add(self._matricula_tab, text=self._t("tab_matricula"))
        self._lang_nb_tabs.append((self._matricula_tab, "tab_matricula"))

        self._status_var = tk.StringVar(value="Bereit.")
        ttk.Label(self, textvariable=self._status_var,
                  relief="sunken", anchor="w", padding=(6, 2)).pack(fill="x", side="bottom")

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
        self._download_tab.update_kit_combo()
        self._save_settings()

    # ── Überlagerung: gemeinsame Vorfahren ─────────────────────────────────────

    def _current_guid(self):
        return self._download_tab.get_kit_guid() or self._state.current_test_guid

    # ── Namenskarte.com helper ────────────────────────────────────────────────

    def _open_namenskarte(self, surname: str):
        from ancestry.gui.analysis.names import open_namenskarte
        open_namenskarte(self, surname)

    # ── Nachname-Analyse ──────────────────────────────────────────────────────

    def _show_surname_analysis(self):
        from ancestry.gui.analysis.names import show_surname_analysis
        show_surname_analysis(self)

    # ── Geburtsort-Analyse ────────────────────────────────────────────────────

    def _show_place_analysis(self):
        from ancestry.gui.analysis.names import show_place_analysis
        show_place_analysis(self)

    # ── MRCA-Wahrscheinlichkeit ───────────────────────────────────────────────

    def _show_mrca_analysis(self, match=None):
        from ancestry.gui.analysis.mrca import show_mrca_analysis
        show_mrca_analysis(self, match)

    # ── Cluster-Netzwerkgraph (Canvas) ────────────────────────────────────────

    def _show_network_graph(self):
        from ancestry.gui.analysis.mrca import show_network_graph
        show_network_graph(self)

    def _show_ancestor_groups(self):
        from ancestry.gui.analysis.pedigree import show_ancestor_groups
        show_ancestor_groups(self)

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
        from ancestry.gui.analysis.pedigree import show_pedigree_overlay
        show_pedigree_overlay(self)

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

    def _show_triangulation(self):
        """Segment-Triangulation: TGs aus DNA-Segmenten + Shared-Match-Bestätigung."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Segment-Triangulation")
        win.geometry("1020x720")

        # Einstellungsleiste
        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(top, text="Min. Segment:", style="Bold.TLabel").pack(side="left")
        min_cm_var = tk.StringVar(value="7")
        ttk.Entry(top, textvariable=min_cm_var, width=5).pack(side="left", padx=4)
        ttk.Label(top, text="cM    Min. Überlappung:").pack(side="left")
        min_ov_var = tk.StringVar(value="5")
        ttk.Entry(top, textvariable=min_ov_var, width=5).pack(side="left", padx=4)
        ttk.Label(top, text="cM").pack(side="left")
        ttk.Button(top, text="↻", width=3, command=lambda: reload()).pack(side="left", padx=8)

        # Phasing-Hinweis
        ttk.Label(win,
            text="⚠  Ohne Phasing können IBD- und IBS-Segmente verwechselt werden. "
                 "GEDmatch-Segmente (Chromosome-Browser) empfohlen; MyHeritage ohne Phasing "
                 "ist weniger zuverlässig.",
            foreground="#a06000", wraplength=980, justify="left",
            font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 2))

        info = ttk.Label(win, text="", style="Bold.TLabel")
        info.pack(anchor="w", padx=10, pady=(2, 2))

        # Hauptpane: Tabelle oben | Chromosomenkarte Mitte | Mitglieder unten
        pane = ttk.PanedWindow(win, orient="vertical")
        pane.pack(fill="both", expand=True, padx=10, pady=4)

        tframe = ttk.Frame(pane); pane.add(tframe, weight=2)
        mapframe = ttk.Frame(pane); pane.add(mapframe, weight=3)
        bframe = ttk.Frame(pane); pane.add(bframe, weight=2)

        cols = ("chrom", "region", "members", "avg_cm")
        tv = ttk.Treeview(tframe, columns=cols, show="headings", selectmode="browse")
        for col, lbl, w, anchor in [
            ("chrom",   "Chr",           60,  "center"),
            ("region",  "Region (Mbp)",  220, "w"),
            ("members", "Mitglieder",     80, "center"),
            ("avg_cm",  "Ø cM",          80,  "center"),
        ]:
            tv.heading(col, text=lbl); tv.column(col, width=w, anchor=anchor)
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview); sb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=sb.set)

        # Chromosomenkarte
        MAP_CHROM_LENGTHS_MBP = {
            1:249,2:243,3:199,4:191,5:181,6:171,7:159,8:146,9:141,
            10:135,11:135,12:133,13:115,14:107,15:102,16:91,17:83,
            18:80,19:59,20:63,21:48,22:51,23:155
        }
        map_canvas = tk.Canvas(mapframe, bg="#f8f8f8", highlightthickness=1,
                               highlightbackground="#cccccc")
        map_canvas.pack(fill="both", expand=True, padx=4, pady=4)

        ttk.Label(bframe, text="Mitglieder der Triangulationsgruppe:",
                  style="Bold.TLabel").pack(anchor="w", pady=(4, 2))
        detail = tk.Text(bframe, height=8, wrap="word", font=("Segoe UI", 9))
        detail.pack(fill="both", expand=True)

        store = {}
        _palette = ["#1a73e8","#e8711a","#2da44e","#a832a8","#e81a4b",
                    "#1ab8e8","#8e8e00","#e8a81a","#666","#333"]

        def _draw_map(tgs):
            map_canvas.delete("all")
            if not tgs:
                return
            W = map_canvas.winfo_width() or 900
            H = map_canvas.winfo_height() or 300
            margin_l, margin_r = 36, 10
            margin_t, margin_b = 10, 10
            track_h = max(4, (H - margin_t - margin_b) // 23 - 2)
            y_step  = (H - margin_t - margin_b) // 23
            chroms = list(range(1, 24))
            max_len = max(MAP_CHROM_LENGTHS_MBP.values())
            draw_w = W - margin_l - margin_r

            for idx, chrom in enumerate(chroms):
                y = margin_t + idx * y_step
                lbl = "X" if chrom == 23 else str(chrom)
                map_canvas.create_text(margin_l - 4, y + track_h // 2, text=lbl,
                                       anchor="e", font=("Segoe UI", 7), fill="#666")
                chrom_len = MAP_CHROM_LENGTHS_MBP.get(chrom, 150)
                bar_w = int(draw_w * chrom_len / max_len)
                map_canvas.create_rectangle(
                    margin_l, y, margin_l + bar_w, y + track_h,
                    fill="#e0e0e0", outline="", tags="bg")

            for tg_idx, tg in enumerate(tgs):
                color = _palette[tg_idx % len(_palette)]
                chrom = tg["chromosome"]
                chrom_len_mbp = MAP_CHROM_LENGTHS_MBP.get(chrom, 150)
                idx = chrom - 1
                y = margin_t + idx * y_step
                bar_w = int(draw_w * chrom_len_mbp / max_len)
                for m in tg["members"]:
                    x0 = margin_l + int(bar_w * m["start"] / (chrom_len_mbp * 1e6))
                    x1 = margin_l + int(bar_w * m["end"]   / (chrom_len_mbp * 1e6))
                    x1 = max(x1, x0 + 2)
                    map_canvas.create_rectangle(x0, y, x1, y + track_h,
                                                fill=color, outline="", stipple="")
                # Konsensregion dicker hervorheben
                rx0 = margin_l + int(bar_w * tg["region_start"] / (chrom_len_mbp * 1e6))
                rx1 = margin_l + int(bar_w * tg["region_end"]   / (chrom_len_mbp * 1e6))
                rx1 = max(rx1, rx0 + 3)
                map_canvas.create_rectangle(rx0, y - 1, rx1, y + track_h + 1,
                                            fill="", outline=color, width=2)

        def reload(*_):
            try:
                min_cm = float(min_cm_var.get() or 7)
                min_ov = float(min_ov_var.get() or 5)
            except ValueError:
                min_cm, min_ov = 7.0, 5.0
            from ancestry.core.triangulation import build_triangulation_groups
            tgs = build_triangulation_groups(self._db, test_guid,
                                             min_cm=min_cm, min_overlap_cm=min_ov)
            tv.delete(*tv.get_children()); store.clear()
            for tg in tgs:
                chrom_lbl = tg["chromosome_label"]
                s_mbp = tg["region_start"] / 1_000_000
                e_mbp = tg["region_end"]   / 1_000_000
                n = len(tg["members"])
                avg_cm = sum(m["length_cm"] for m in tg["members"]) / n if n else 0
                iid = tv.insert("", "end", values=(
                    chrom_lbl, f"{s_mbp:.1f} – {e_mbp:.1f}", n, f"{avg_cm:.1f}"))
                store[iid] = tg
            if tgs:
                info.configure(text=(
                    f"{len(tgs)} Triangulationsgruppen "
                    f"(min. {min_cm:.0f} cM, Überlappung ≥ {min_ov:.0f} cM)"))
            else:
                info.configure(
                    text="Keine TGs – erst DNA-Segmente laden (import_segments.py) "
                         "und Shared Matches abrufen.")
            win.after(50, lambda: _draw_map(tgs))

        def on_sel(_event=None):
            detail.delete("1.0", "end")
            sel = tv.selection()
            if not sel:
                return
            tg = store.get(sel[0])
            if not tg:
                return
            chrom = tg["chromosome_label"]
            s_mbp = tg["region_start"] / 1_000_000
            e_mbp = tg["region_end"]   / 1_000_000
            detail.insert("end", f"Chr {chrom}  {s_mbp:.2f} – {e_mbp:.2f} Mbp\n\n")
            name_map: dict = {}
            try:
                name_map = {m.match_guid: m.display_name
                            for m in self._db.get_matches(test_guid)}
            except Exception:
                pass
            for m in sorted(tg["members"], key=lambda x: -x["length_cm"]):
                name = name_map.get(m["match_guid"], m["match_guid"][:12])
                detail.insert("end",
                    f"  {name[:42]:<44} {m['length_cm']:6.1f} cM  "
                    f"({m['start']/1e6:.1f}–{m['end']/1e6:.1f} Mbp)\n")

        tv.bind("<<TreeviewSelect>>", on_sel)
        # Karte erst nach Layout zeichnen, damit winfo_width korrekt ist
        win.after(100, reload)

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
        self._state.current_test_guid = guid
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
        import os
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
        return translate(key, self._lang)

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
            tg = self._state.current_test_guid or self._current_guid()
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

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3: MATCHES  →  siehe ancestry/gui/tabs/matches.py
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_match_table(self, *_):
        """Delegation stub — aktualisiert die Match-Tabelle im Matches-Tab."""
        self._matches_tab.refresh()

    def _update_matches_kit_combo(self):
        """Delegation stub — befüllt den Kit-Selektor im Matches-Tab."""
        self._matches_tab.update_kit_combo()

    def _load_gedcom_link_panel(self, match: "DnaMatch"):
        """Delegation stub — füllt den GEDCOM-Treffer-Tab im Matches-Tab."""
        self._matches_tab.load_gedcom_link_panel(match)

    @property
    def _selected_match(self) -> Optional[DnaMatch]:
        """Aktuell gewählter Match — lebt im Matches-Tab."""
        tab = getattr(self, "_matches_tab", None)
        return tab.selected_match if tab is not None else None

    def _run_gedcom_match_all(self):
        """Bulk-Abgleich aller Matches gegen den GEDCOM-Baum."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo("GEDCOM", self._t("md.ged_none"))
            return
        test_guid = self._state.current_test_guid or self._get_kit_guid()
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
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

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
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Endogamie-Transfer läuft …")

        def _worker():
            try:
                from core import bridge as _bridge
                import os as _os
                import importlib.util as _ilu
                # GEDCOM-Endogamie aus dem Haupt-Analyzer (tasks ist installiert)
                _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
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
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

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
        test_guid = self._state.current_test_guid or self._get_kit_guid()
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
                self.after(0, lambda exc=exc: messagebox.showwarning("ML-Herkunft", str(exc)))

        import threading
        threading.Thread(target=_worker, daemon=True, name="ml-origin").start()

    def _run_wikitree_extend(self):
        """Verlängert die Ahnenlinie des gewählten Matches über die WikiTree-API."""
        match = getattr(self, "_selected_match", None)
        if not match:
            messagebox.showinfo("WikiTree", "Bitte zuerst einen Match in der Tabelle auswählen.")
            return
        test_guid = self._state.current_test_guid or self._get_kit_guid()
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
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

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
        test_guid = self._state.current_test_guid or self._get_kit_guid()
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
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="origin-infer").start()


    # ─────────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────────────
    # TAB 5: STATISTIKEN
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_stats(self):
        self._stats_tab.refresh()

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
        test_guid = self._state.current_test_guid or self._get_kit_guid()
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
        test_guid = self._state.current_test_guid or self._get_kit_guid()
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

    def _on_progress(self, fetched, total, label):
        """Delegation stub — updates DownloadTab progress display."""
        self._download_tab.on_progress(fetched, total, label)

    def _get_kit_guid(self) -> Optional[str]:
        if hasattr(self, "_download_tab"):
            return self._download_tab.get_kit_guid()
        return None

    # ── Neue Analyse-Methoden ─────────────────────────────────────────────────

    def _show_pedigree_gaps(self):
        from ancestry.gui.analysis.pedigree import show_pedigree_gaps
        show_pedigree_gaps(self)

    def _show_endogamy_analysis(self):
        from ancestry.gui.analysis.mrca import show_endogamy_analysis
        show_endogamy_analysis(self)

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
        kit_combo.grid(row=2, column=0, columnspan=2, padx=28, pady=(0,4), sticky="w")
        kit_combo.bind("<Button-1>", lambda _: method_var.set("kit"))
        # Hinweis: ohne zweites Kit ist die Seiten-Zuweisung unzuverlässig
        ttk.Label(dlg,
            text="ℹ  Ohne ein Mutter- oder Vater-Kit basiert die Zuweisung nur auf\n"
                 "Cluster-Patterns und ist eine Schätzung — keine genealogische Gewissheit.",
            foreground="#a06000", font=("Segoe UI", 8), justify="left").grid(
            row=2, column=2, padx=(8,14), pady=(0,4), sticky="w")

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
                self._download_tab.update_kit_combo()
                self._state.current_test_guid = guid
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
        dl_running = self._download_tab.is_running()
        mat_running = self._matricula_tab.is_running()
        if dl_running or mat_running or (self._scraper and self._scraper.is_running()):
            what = "Matricula-Scan" if mat_running and not dl_running else "Download"
            if not messagebox.askyesno("Beenden?", f"{what} läuft noch. Wirklich beenden?"):
                return
            self._download_tab.stop_download()
            self._matricula_tab._stop_scan()
            if self._scraper:
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
