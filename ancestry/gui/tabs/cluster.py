"""Cluster-Tab: Leeds-Clustering-Ansicht für das Ancestry-DNA-Tool."""

from __future__ import annotations

import datetime
import logging
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ancestry.core.cluster import build_clusters, suggest_grandparent_lines
from ancestry.gui.state import AppState
from ancestry.gui.undo import UndoStack as _UndoStack
from ancestry.gui.widgets.theme import register_lang, COLORS
from ancestry.gui.widgets.tooltip import register_tooltip

log = logging.getLogger(__name__)


class ClusterTab(ttk.Frame):
    """Cluster-Tab des Ancestry-DNA-Tools.

    Parameters
    ----------
    parent:
        ttk.Frame aus dem Notebook.
    state:
        Gemeinsamer App-Zustand.
    get_test_guid:
        Liefert die aktuelle primäre Test-GUID (oder None).
    get_current_guid:
        Liefert die aktuelle GUID (kit-combo oder test_guid).
    load_ui_settings:
        Lädt das UI-Settings-Dict.
    save_ui_settings:
        Speichert UI-Settings-Schlüssel.
    set_status:
        Setzt die App-Statuszeile.
    on_show_timeline:
        Öffnet das Cluster-Zeitachse-Fenster.
    on_assign_side:
        Führt die automatische Seiten-Zuweisung aus.
    """

    def __init__(
        self,
        parent: tk.Widget,
        state: AppState,
        get_test_guid:    Callable[[], Optional[str]],
        get_current_guid: Callable[[], Optional[str]],
        load_ui_settings: Callable[[], dict],
        save_ui_settings: Callable[..., None],
        set_status:       Callable[[str], None],
        on_show_timeline: Callable,
        on_assign_side:   Callable,
    ):
        super().__init__(parent)
        self._state            = state
        self._get_test_guid    = get_test_guid
        self._get_current_guid = get_current_guid
        self._load_settings    = load_ui_settings
        self._save_settings    = save_ui_settings
        self._set_status       = set_status
        self._on_show_timeline = on_show_timeline
        self._on_assign_side   = on_assign_side
        self._clusters:          dict = {}
        self._cluster_side_colors: dict[int, str] = {}
        self._build()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        s  = self._state
        t  = s.t
        lw = s.lang_widgets
        lh = s.lang_headings

        # Einstellungen
        cf = ttk.Frame(self)
        cf.pack(fill="x", padx=14, pady=8)
        _sv = tk.StringVar(value=t("cl.prim_from"))
        ttk.Label(cf, textvariable=_sv).pack(side="left")
        lw.append((_sv, "cl.prim_from"))
        self._min_cm_var = tk.StringVar(value="20")
        ttk.Entry(cf, textvariable=self._min_cm_var, width=6).pack(side="left", padx=6)
        _sv = tk.StringVar(value=t("cl.prim_to"))
        ttk.Label(cf, textvariable=_sv).pack(side="left", padx=(4, 4))
        lw.append((_sv, "cl.prim_to"))
        self._max_cm_var = tk.StringVar(value="400")
        ttk.Entry(cf, textvariable=self._max_cm_var, width=6).pack(side="left")
        _sv = tk.StringVar(value=t("cl.shared_min"))
        ttk.Label(cf, textvariable=_sv).pack(side="left", padx=(14, 4))
        lw.append((_sv, "cl.shared_min"))
        self._shared_cm_var = tk.StringVar(value="20")
        ttk.Entry(cf, textvariable=self._shared_cm_var, width=6).pack(side="left")
        # Modularitäts-Clustering (Louvain) statt Leeds/Union-Find: robuster
        # gegen über-geteilte Brücken-Matches, die sonst zwei Linien verschmelzen.
        self._modularity_var = tk.BooleanVar(value=False)
        _mb = ttk.Checkbutton(cf, text="Modularität", variable=self._modularity_var)
        _mb.pack(side="left", padx=(14, 0))
        register_tooltip(_mb, "tt.cl_modularity", self._state)
        _sv = tk.StringVar(value=t("cl.calc_btn"))
        self._calc_btn = ttk.Button(cf, textvariable=_sv, command=self.refresh)
        self._calc_btn.pack(side="left", padx=14)
        register_tooltip(self._calc_btn, "tt.cl_calc", self._state)
        lw.append((_sv, "cl.calc_btn"))
        self._count_var = tk.StringVar(value="")
        ttk.Label(cf, textvariable=self._count_var,
                  foreground=COLORS["primary"]).pack(side="left")
        _sv = tk.StringVar(value=t("cl.tree_btn"))
        _b = ttk.Button(cf, textvariable=_sv, command=self._show_tree)
        _b.pack(side="left", padx=14)
        register_tooltip(_b, "tt.cl_tree", self._state)
        lw.append((_sv, "cl.tree_btn"))
        _sv = tk.StringVar(value=t("cl.timeline"))
        _b = ttk.Button(cf, textvariable=_sv, command=self._on_show_timeline)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.cl_timeline", self._state)
        lw.append((_sv, "cl.timeline"))
        _sv = tk.StringVar(value=t("cl.assign_side"))
        _b = ttk.Button(cf, textvariable=_sv, command=self._on_assign_side)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.cl_assign", self._state)
        lw.append((_sv, "cl.assign_side"))
        _sv = tk.StringVar(value=t("cl.phasing"))
        _b = ttk.Button(cf, textvariable=_sv, command=self._show_phasing)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.cl_phasing", self._state)
        lw.append((_sv, "cl.phasing"))
        _sv = tk.StringVar(value=t("cl.dna_segments"))
        _b = ttk.Button(cf, textvariable=_sv, command=self._show_dna_segments)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.cl_segments", self._state)
        lw.append((_sv, "cl.dna_segments"))
        _sv = tk.StringVar(value=t("cl.mrca_map"))
        _b = ttk.Button(cf, textvariable=_sv, command=self._show_mrca_map)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.cl_mrca", self._state)
        lw.append((_sv, "cl.mrca_map"))
        ttk.Button(cf, text="📥 CSV", command=self._export_clusters).pack(side="left", padx=4)
        ttk.Button(cf, text="📄 Report", command=self._export_cluster_report).pack(side="left", padx=4)

        # Cluster-Beschreibung
        df = ttk.Frame(self)
        df.pack(fill="x", padx=14, pady=(0, 4))
        _sv = tk.StringVar(value=t("cl.desc"))
        ttk.Label(df, textvariable=_sv).pack(side="left")
        lw.append((_sv, "cl.desc"))
        self._desc_var = tk.StringVar()
        ttk.Entry(df, textvariable=self._desc_var, width=50).pack(side="left", padx=6)
        ttk.Button(df, text="💾", command=self._save_desc, width=3).pack(side="left")

        # Ahn-Hypothese je Cluster (B3): von welchem Vorfahren stammt der Cluster?
        hf = ttk.Frame(self)
        hf.pack(fill="x", padx=14, pady=(0, 4))
        ttk.Label(hf, text="MRCA-Hypothese:").pack(side="left")
        self._hypo_var = tk.StringVar(value="—")
        ttk.Label(hf, textvariable=self._hypo_var, foreground=COLORS["primary"],
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=6)
        _hb = ttk.Button(hf, text="🧬 Ahn-Hypothese …", command=self._edit_hypothesis)
        _hb.pack(side="left", padx=6)
        register_tooltip(_hb, "tt.cl_hypo", self._state)

        # A1: AI-Copilot „Erklären"-Button
        ttk.Button(hf, text="🤖 Erklären (AI)",
                   command=self._ai_explain_cluster).pack(side="left", padx=4)
        self._ai_explain_label = tk.StringVar(value="")
        ttk.Label(hf, textvariable=self._ai_explain_label,
                  wraplength=320, foreground="#334455",
                  font=("Segoe UI", 8)).pack(side="left", padx=8)

        # A2: Triangulations-Bericht-Button + A1: Chromosomen-Browser-Button
        af = ttk.Frame(self)
        af.pack(fill="x", padx=14, pady=(0, 2))
        self._tri_report_btn = ttk.Button(
            af, text="📄 HTML-Bericht öffnen (Triangulation)",
            command=self._open_triangulation_report,
        )
        self._tri_report_btn.pack(side="left", padx=0)
        self._chrom_btn = ttk.Button(
            af, text="🧬 Chromosomen-Browser",
            command=self._open_chromosome_browser,
        )
        self._chrom_btn.pack(side="left", padx=(8, 0))
        register_tooltip(self._chrom_btn, "tt.cl_chrom", self._state)

        self._text_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._text_var,
                  foreground="#444466", font=("Segoe UI", 9),
                  wraplength=900, justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        self._build_legend()

        # B3: Phasing-Panel
        self._build_phasing_panel(self)
        self._populate_phase_kits()

        # PanedWindow
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=14, pady=4)

        left = ttk.LabelFrame(pane, text=t("cl.frm_left"), padding=6)
        lw.append((left, "cl.frm_left"))
        pane.add(left, weight=1)
        self._cluster_list = ttk.Treeview(
            left, columns=("cid", "count", "max_cm", "top", "quality"),
            show="headings", selectmode="browse")
        for col, (key, w) in {
            "cid":     ("cl.cid",     50),
            "count":   ("cl.count",   55),
            "max_cm":  ("cl.maxcm",   65),
            "top":     ("cl.top",    175),
            "quality": ("cl.quality", 80),
        }.items():
            self._cluster_list.heading(col, text=t(key))
            self._cluster_list.column(col, width=w,
                                      stretch=(col == "top"),
                                      anchor="center" if col in ("quality", "count") else "w")
            lh.append((self._cluster_list, col, key))
        sy1 = ttk.Scrollbar(left, orient="vertical", command=self._cluster_list.yview)
        self._cluster_list.configure(yscrollcommand=sy1.set)
        self._cluster_list.pack(side="left", fill="both", expand=True)
        sy1.pack(side="right", fill="y")
        self._cluster_list.bind("<<TreeviewSelect>>", self._on_select)
        # B3: Kontextmenü für Merge-Aktion
        self._cluster_ctx_menu = tk.Menu(self, tearoff=0)
        self._cluster_ctx_menu.add_command(
            label="🔗 Zusammenführen mit …",
            command=self._merge_cluster_dialog,
        )
        self._cluster_list.bind("<Button-3>", self._on_cluster_right_click)
        # macOS: Button-2
        self._cluster_list.bind("<Button-2>", self._on_cluster_right_click)

        mid = ttk.LabelFrame(pane, text=t("cl.frm_mid"), padding=6)
        lw.append((mid, "cl.frm_mid"))
        pane.add(mid, weight=2)
        self._member_tree = ttk.Treeview(
            mid, columns=("name", "cm", "rel", "baum"),
            show="headings", selectmode="browse")
        for col, (key, w, anchor) in {
            "name": ("mb.name", 190, "w"),
            "cm":   ("mb.cm",    60, "e"),
            "rel":  ("mb.rel",  150, "w"),
            "baum": ("mb.baum",  55, "center"),
        }.items():
            self._member_tree.heading(col, text=t(key))
            self._member_tree.column(col, width=w, anchor=anchor, stretch=(col == "name"))
            lh.append((self._member_tree, col, key))
        sy2 = ttk.Scrollbar(mid, orient="vertical", command=self._member_tree.yview)
        self._member_tree.configure(yscrollcommand=sy2.set)
        self._member_tree.pack(side="left", fill="both", expand=True)
        sy2.pack(side="right", fill="y")

        right = ttk.LabelFrame(pane, text=t("cl.frm_right"), padding=6)
        lw.append((right, "cl.frm_right"))
        pane.add(right, weight=2)
        self._pairwise_tree = ttk.Treeview(
            right, columns=("a", "b", "cm"),
            show="headings", selectmode="none")
        for col, (key, w, anch) in {
            "a":  ("pw.a",  190, "w"),
            "b":  ("pw.b",  190, "w"),
            "cm": ("pw.cm",  90, "e"),
        }.items():
            self._pairwise_tree.heading(col, text=t(key))
            self._pairwise_tree.column(col, width=w, anchor=anch,
                                       stretch=(col in ("a", "b")))
            lh.append((self._pairwise_tree, col, key))
        sy3 = ttk.Scrollbar(right, orient="vertical", command=self._pairwise_tree.yview)
        self._pairwise_tree.configure(yscrollcommand=sy3.set)
        self._pairwise_tree.pack(side="left", fill="both", expand=True)
        sy3.pack(side="right", fill="y")

        # A1: Spaltenbreiten-Persistenz — nach Aufbau aller Treeviews
        # Laden über after() damit Widgets bereits realisiert sind
        self.after(
            200,
            lambda: (
                self._load_col_widths(
                    self._cluster_list,
                    ("cid", "count", "max_cm", "top", "quality"),
                    "cluster_col",
                ),
                self._load_col_widths(
                    self._member_tree, ("name", "cm", "rel", "baum"), "cluster_member_col"
                ),
                self._load_col_widths(
                    self._pairwise_tree, ("a", "b", "cm"), "cluster_pw_col"
                ),
            ),
        )
        # Resize-Event: Breiten beim Loslassen der Maus nach dem Schieben speichern
        self._cluster_list.bind(
            "<ButtonRelease-1>",
            lambda _e: self._save_col_widths(
                self._cluster_list,
                ("cid", "count", "max_cm", "top", "quality"),
                "cluster_col",
            ),
        )
        self._member_tree.bind(
            "<ButtonRelease-1>",
            lambda _e: self._save_col_widths(
                self._member_tree, ("name", "cm", "rel", "baum"), "cluster_member_col"
            ),
        )
        self._pairwise_tree.bind(
            "<ButtonRelease-1>",
            lambda _e: self._save_col_widths(
                self._pairwise_tree, ("a", "b", "cm"), "cluster_pw_col"
            ),
        )

    def _build_legend(self):
        """Kompakte Farb-Legende unterhalb der Cluster-Beschreibung."""
        lf = tk.Frame(self, bd=0)
        lf.pack(anchor="w", padx=14, pady=(0, 6))
        tk.Label(lf, text="Legende:", font=("Segoe UI", 9, "bold"),
                 fg="#1A1A2E").pack(side="left", padx=(0, 8))
        # Seiten-Farben
        for color, label in [
            ("#DDF0FF", "🔵 Väterlich (≥70 %)"),
            ("#FFE0E0", "🔴 Mütterlich (≥70 %)"),
        ]:
            tk.Label(lf, text=" ", bg=color, relief="solid", bd=1,
                     padx=8, pady=2).pack(side="left", padx=(0, 2))
            ttk.Label(lf, text=label,
                      font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
        # "Bunte Farbe" für unbekannte Seite
        tk.Label(lf, text=" ", bg=COLORS["cluster"][2], relief="solid", bd=1,
                 padx=8, pady=2).pack(side="left", padx=(0, 2))
        ttk.Label(lf, text="Bunt = Seite unbekannt",
                  font=("Segoe UI", 9)).pack(side="left", padx=(0, 14))
        # Qualitäts-Icons
        ttk.Label(lf, text="Qualität:",
                  font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        for icon, desc in [
            ("🟢", "≥85 % intern vernetzt"),
            ("🟡", "50–84 %"),
            ("🔴", "<50 %"),
        ]:
            ttk.Label(lf, text=f"{icon} {desc}",
                      font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))

    # ── Daten laden ──────────────────────────────────────────────────────────

    def refresh(self):
        import threading as _threading
        test_guid = self._get_test_guid()
        if not test_guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dlg.m_choose_kit"))
            return
        try:
            min_prim   = float(self._min_cm_var.get()    or 20)
            max_prim   = float(self._max_cm_var.get()    or 400)
            min_shared = float(self._shared_cm_var.get() or 20)
        except ValueError:
            min_prim, max_prim, min_shared = 20.0, 400.0, 20.0
        use_modularity = bool(self._modularity_var.get())   # Tk-Var auf Main-Thread lesen

        self._calc_btn.configure(state="disabled")

        def _worker():
            shared_data = self._state.db.get_all_shared_for_cluster(
                test_guid, min_prim, min_shared,
                max_cm_primary=max_prim, max_cm_shared=max_prim)
            if not shared_data:
                self.after(0, lambda: (
                    self._calc_btn.configure(state="normal"),
                    messagebox.showinfo(self._state.t("dlg.no_data"),
                                        "Keine Shared Matches im gewählten cM-Bereich.\n\n"
                                        "Mögliche Ursachen:\n"
                                        "• Noch keine Shared Matches heruntergeladen "
                                        "(Tab Herunterladen → B)\n"
                                        f"• Keine primären Matches zwischen {min_prim:.0f} "
                                        f"und {max_prim:.0f} cM — Bereich anpassen."),
                ))
                return
            if use_modularity:
                from ancestry.core.cluster import build_clusters_modularity
                clusters = build_clusters_modularity(shared_data, min_prim, min_shared,
                                                     max_cm_primary=max_prim)
            else:
                clusters = build_clusters(shared_data, min_prim, min_shared,
                                          max_cm_primary=max_prim)
            # Seiten-Map im Worker-Thread holen
            all_guids = [m["guid"] for mlist in clusters.values() for m in mlist]
            side_map: dict[str, str] = {}
            if all_guids:
                try:
                    with self._state.db._cursor() as cur:
                        rows = cur.execute(
                            "SELECT match_guid, paternal_maternal FROM matches "
                            "WHERE match_guid IN ({})".format(",".join("?" * len(all_guids))),
                            all_guids,
                        ).fetchall()
                    side_map = {r["match_guid"]: (r["paternal_maternal"] or "") for r in rows}
                except Exception as e:
                    log.debug("cluster side_map: %s", e)
            self.after(0, lambda sd=shared_data, cl=clusters, sm=side_map:
                       self._apply_cluster_result(sd, cl, sm))

        _threading.Thread(target=_worker, daemon=True, name="cluster-build").start()

    def _apply_cluster_result(self, shared_data, clusters, side_map):
        self._desc_cid = None   # Cluster-IDs neu vergeben → kein Auto-Save auf alte ID
        self._clusters = clusters
        self._count_var.set(f"{len(self._clusters)} Cluster")
        self._text_var.set(suggest_grandparent_lines(self._clusters))
        self._cluster_side_colors = {}

        # Dichte berechnen
        _sets: dict[int, set] = {
            cid: {m["guid"] for m in mlist} for cid, mlist in self._clusters.items()}
        _guid_cid: dict[str, int] = {g: cid for cid, gs in _sets.items() for g in gs}
        _edge_counts: dict[int, int] = {}
        _seen: set = set()
        for row in shared_data:
            ga, gb = row["match_guid_a"], row["match_guid_b"]
            ca, cb = _guid_cid.get(ga), _guid_cid.get(gb)
            if ca is not None and ca == cb:
                pair = (ga, gb) if ga < gb else (gb, ga)
                if pair not in _seen:
                    _seen.add(pair)
                    _edge_counts[ca] = _edge_counts.get(ca, 0) + 1

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
                    color = "#DDF0FF"; side_icon = "🔵 "
                elif n_mat / n_known >= 0.7:
                    color = "#FFE0E0"; side_icon = "🔴 "
                else:
                    color = cluster_colors[(cid - 1) % len(cluster_colors)]; side_icon = ""
            else:
                color = cluster_colors[(cid - 1) % len(cluster_colors)]; side_icon = ""
            self._cluster_side_colors[cid] = color
            n = len(members)
            possible = n * (n - 1) / 2
            density  = (_edge_counts.get(cid, 0) / possible) if possible > 0 else 0.0
            try:
                from statistics import median
                from ancestry.core.treematch import cluster_confidence
                # Echter Median statt Mittelwert: cM-Verteilung im Cluster ist
                # rechtsschief (ein naher Verwandter zieht den Schnitt hoch).
                med_cm = median(m["cm"] for m in members) if n else 0.0
                conf   = cluster_confidence(n, density, median_cm=med_cm)
                r = conf.get("realness", 0)
                quality_icon = "🟢" if r >= 0.85 else ("🟡" if r >= 0.5 else "🔴")
            except Exception:
                quality_icon = "—"
            quality_icon = f"{quality_icon} {density:.0%}"
            top_name = side_icon + (members[0]["name"] if members else "")
            self._cluster_list.insert("", "end", iid=str(cid), tags=(f"c{cid}",),
                                       values=(f"#{cid}", len(members),
                                               f"{max(cms):.0f}", top_name, quality_icon))
            self._cluster_list.tag_configure(f"c{cid}", background=color)
        self._member_tree.delete(*self._member_tree.get_children())
        self._calc_btn.configure(state="normal")
        # B1: Gespeicherte Farben aus DB laden und anwenden
        self._load_cluster_colors()
        # B1: Aktuell berechnete Farben direkt persistieren
        self._save_cluster_colors()

    # ── Selektion ────────────────────────────────────────────────────────────

    def _autosave_desc(self):
        """Sichert eine geänderte Cluster-Beschreibung still, bevor die Auswahl
        wechselt (verhindert Datenverlust wie beim Notiz-Feld im Matches-Tab)."""
        prev = getattr(self, "_desc_cid", None)
        if prev is None:
            return
        cur = self._desc_var.get().strip()
        stored = self._load_settings().get("cluster_descs", {}).get(str(prev), "")
        if cur != stored:
            descs = self._load_settings().get("cluster_descs", {})
            descs[str(prev)] = cur
            self._save_settings(cluster_descs=descs)

    def _on_select(self, _=None):
        sel = self._cluster_list.selection()
        if not sel:
            return
        cid     = int(sel[0])
        # Ausstehende Beschreibung des vorigen Clusters sichern, dann neue laden
        self._autosave_desc()
        members = self._clusters.get(cid, [])
        descs   = self._load_settings().get("cluster_descs", {})
        self._desc_var.set(descs.get(str(cid), ""))
        self._desc_cid = cid
        # Ahn-Hypothese dieses Clusters laden (B3)
        self._hypo_cid = cid
        self._hypo_members = [m["guid"] for m in members]
        self._load_hypothesis(cid)
        color = self._cluster_side_colors.get(
            cid, COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])])

        self._member_tree.delete(*self._member_tree.get_children())
        self._pairwise_tree.delete(*self._pairwise_tree.get_children())

        test_guid = self._get_current_guid()
        if not (test_guid and members):
            return

        import threading as _threading

        def _worker(cid=cid, members=members, color=color, tg=test_guid):
            guid_match: dict = {}
            try:
                member_guids = [m["guid"] for m in members]
                guid_match = {m.match_guid: m
                              for m in self._state.db.get_matches(
                                  tg, guid_filter=member_guids)}
            except Exception as e:
                log.debug("cluster guid_match: %s", e)
            pairs = []
            if len(members) >= 2:
                try:
                    pairs = self._state.db.get_pairwise_shared(
                        tg, [m["guid"] for m in members])
                except Exception as e:
                    log.debug("cluster pairwise: %s", e)
            self.after(0, lambda: self._fill_member_panels(
                cid, members, guid_match, pairs, color))

        _threading.Thread(target=_worker, daemon=True, name="cluster-select").start()

    def _fill_member_panels(self, cid, members, guid_match, pairs, color):
        # Stale-Guard: Auswahl könnte sich während des DB-Calls geändert haben
        sel = self._cluster_list.selection()
        if not sel or int(sel[0]) != cid:
            return
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
                                             m.get("rel", ""), baum_val))

        self._pairwise_tree.delete(*self._pairwise_tree.get_children())
        guid_name = {m["guid"]: m["name"] for m in members}
        self._pairwise_tree.tag_configure("row", background=color)
        for a, b, cm in pairs:
            if cm > 0:
                self._pairwise_tree.insert("", "end", tags=("row",), values=(
                    guid_name.get(a, a[:12]),
                    guid_name.get(b, b[:12]),
                    f"{cm:.0f}"))

    # ── Beschreibung speichern ────────────────────────────────────────────────

    def _save_desc(self):
        sel = self._cluster_list.selection()
        if not sel:
            return
        cid      = int(sel[0])
        new_desc = self._desc_var.get().strip()
        old_desc = self._load_settings().get("cluster_descs", {}).get(str(cid), "")
        descs = self._load_settings().get("cluster_descs", {})
        descs[str(cid)] = new_desc
        self._save_settings(cluster_descs=descs)
        self._set_status(f"Cluster #{cid} Beschreibung gespeichert.")

        # Undo-Hook: Beschreibungsänderung rückgängig machen
        _cid, _old, _new = cid, old_desc, new_desc

        def _undo_desc():
            d = self._load_settings().get("cluster_descs", {})
            d[str(_cid)] = _old
            self._save_settings(cluster_descs=d)
            if self._cluster_list.selection() and int(self._cluster_list.selection()[0]) == _cid:
                self._desc_var.set(_old)

        def _redo_desc():
            d = self._load_settings().get("cluster_descs", {})
            d[str(_cid)] = _new
            self._save_settings(cluster_descs=d)
            if self._cluster_list.selection() and int(self._cluster_list.selection()[0]) == _cid:
                self._desc_var.set(_new)

        _UndoStack.get().push(f"Cluster #{_cid} Beschreibung", _undo_desc, _redo_desc)

    # ── Ahn-Hypothese je Cluster (B3) ─────────────────────────────────────────

    def _load_hypothesis(self, cid: int):
        tg = self._get_current_guid()
        h = None
        if tg:
            try:
                h = self._state.db.get_cluster_hypothesis(tg, cid)
            except Exception as e:
                log.debug("load hypothesis: %s", e)
        if h and (h.get("mrca_label") or h.get("mrca_ged_id")):
            conf = h.get("confidence") or ""
            self._hypo_var.set(
                (h.get("mrca_label") or h.get("mrca_ged_id"))
                + (f"  ({conf})" if conf else ""))
        else:
            self._hypo_var.set("—")

    def _edit_hypothesis(self):
        cid = getattr(self, "_hypo_cid", None)
        tg  = self._get_current_guid()
        if cid is None or not tg:
            messagebox.showinfo("Ahn-Hypothese", "Bitte zuerst einen Cluster auswählen.")
            return
        members = getattr(self, "_hypo_members", [])
        # Vorschläge aus den GEDCOM-Brücken-Links der Cluster-Mitglieder
        suggestions = []
        try:
            suggestions = self._state.db.suggest_cluster_mrca(tg, members)
        except Exception as e:
            log.debug("suggest mrca: %s", e)
        existing = None
        try:
            existing = self._state.db.get_cluster_hypothesis(tg, cid)
        except Exception:
            pass

        dlg = tk.Toplevel(self)
        dlg.title(f"Ahn-Hypothese — Cluster #{cid}")
        dlg.geometry("560x440")
        ttk.Label(dlg, text=f"Von welchem gemeinsamen Vorfahren stammt Cluster #{cid}?",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 4))

        if suggestions:
            ttk.Label(dlg, text="Vorschläge (GEDCOM-Brücke, ≥2 Mitglieder docken an):",
                      foreground="#555").pack(anchor="w", padx=12)
            sug_tree = ttk.Treeview(dlg, columns=("name", "year", "n", "score"),
                                    show="headings", height=5, selectmode="browse")
            for c, (lbl, w) in {"name": ("Vorfahr", 240), "year": ("Jahr", 60),
                                "n": ("Mitgl.", 60), "score": ("Ø-Score", 70)}.items():
                sug_tree.heading(c, text=lbl); sug_tree.column(c, width=w)
            sug_tree.pack(fill="x", padx=12, pady=4)
            sug_by_iid = {}
            for s in suggestions:
                iid = sug_tree.insert("", "end", values=(
                    s["name"], s["year"], s["member_count"], s["avg_score"]))
                sug_by_iid[iid] = s
        else:
            ttk.Label(dlg, text="Keine automatischen Vorschläge (noch keine "
                                "GEDCOM-Verknüpfungen für diese Mitglieder).",
                      foreground="#a05a00").pack(anchor="w", padx=12, pady=2)
            sug_tree = None
            sug_by_iid = {}

        frm = ttk.Frame(dlg); frm.pack(fill="x", padx=12, pady=(8, 2))
        ttk.Label(frm, text="Vorfahr (Name):").grid(row=0, column=0, sticky="w")
        label_var = tk.StringVar(value=(existing or {}).get("mrca_label", ""))
        ttk.Entry(frm, textvariable=label_var, width=40).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Label(frm, text="GEDCOM-ID:").grid(row=1, column=0, sticky="w")
        gid_var = tk.StringVar(value=(existing or {}).get("mrca_ged_id", ""))
        ttk.Entry(frm, textvariable=gid_var, width=24).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(frm, text="Konfidenz:").grid(row=2, column=0, sticky="w")
        conf_var = tk.StringVar(value=(existing or {}).get("confidence", "mittel") or "mittel")
        ttk.Combobox(frm, textvariable=conf_var, width=12, state="readonly",
                     values=["hoch", "mittel", "niedrig"]).grid(row=2, column=1, sticky="w", padx=4)
        frm.columnconfigure(1, weight=1)

        ttk.Label(dlg, text="Begründung / Belege:").pack(anchor="w", padx=12, pady=(6, 0))
        ev_txt = tk.Text(dlg, height=4, wrap="word")
        ev_txt.pack(fill="x", padx=12)
        ev_txt.insert("1.0", (existing or {}).get("evidence", ""))

        def _use_suggestion(_=None):
            if not sug_tree:
                return
            sel = sug_tree.selection()
            if not sel:
                return
            s = sug_by_iid.get(sel[0])
            if s:
                label_var.set(f"{s['name']}" + (f" ({s['year']})" if s["year"] else ""))
                gid_var.set(s["ged_id"])
        if sug_tree:
            sug_tree.bind("<Double-1>", _use_suggestion)

        def _save():
            new_mrca_ged_id = gid_var.get().strip()
            new_mrca_label  = label_var.get().strip()
            new_confidence  = conf_var.get()
            new_evidence    = ev_txt.get("1.0", "end").strip()
            # Alte Werte für Undo festhalten
            _old = dict(existing) if existing else {}
            _new = {
                "mrca_ged_id": new_mrca_ged_id,
                "mrca_label":  new_mrca_label,
                "confidence":  new_confidence,
                "evidence":    new_evidence,
            }
            self._state.db.set_cluster_hypothesis(
                tg, cid, mrca_ged_id=new_mrca_ged_id,
                mrca_label=new_mrca_label, confidence=new_confidence,
                evidence=new_evidence)
            self._load_hypothesis(cid)
            self._set_status(f"Cluster #{cid}: Ahn-Hypothese gespeichert.")
            dlg.destroy()

            # Undo-Hook: Ahn-Hypothese rückgängig machen
            _tg, _cid_u = tg, cid

            def _undo_hypo():
                try:
                    if _old:
                        self._state.db.set_cluster_hypothesis(
                            _tg, _cid_u,
                            mrca_ged_id=_old.get("mrca_ged_id", ""),
                            mrca_label=_old.get("mrca_label", ""),
                            confidence=_old.get("confidence", ""),
                            evidence=_old.get("evidence", ""))
                    else:
                        self._state.db.delete_cluster_hypothesis(_tg, _cid_u)
                    if getattr(self, "_hypo_cid", None) == _cid_u:
                        self._load_hypothesis(_cid_u)
                except Exception:
                    pass

            def _redo_hypo():
                try:
                    self._state.db.set_cluster_hypothesis(
                        _tg, _cid_u,
                        mrca_ged_id=_new["mrca_ged_id"],
                        mrca_label=_new["mrca_label"],
                        confidence=_new["confidence"],
                        evidence=_new["evidence"])
                    if getattr(self, "_hypo_cid", None) == _cid_u:
                        self._load_hypothesis(_cid_u)
                except Exception:
                    pass

            _UndoStack.get().push(f"Ahn-Hypothese Cluster #{_cid_u}", _undo_hypo, _redo_hypo)

        def _delete():
            self._state.db.delete_cluster_hypothesis(tg, cid)
            self._load_hypothesis(cid)
            dlg.destroy()

        bf = ttk.Frame(dlg); bf.pack(fill="x", padx=12, pady=8)
        if sug_tree:
            ttk.Button(bf, text="◀ Vorschlag übernehmen", command=_use_suggestion).pack(side="left")
        ttk.Button(bf, text="🗑 Löschen", command=_delete).pack(side="left", padx=4)
        ttk.Button(bf, text="Abbrechen", command=dlg.destroy).pack(side="right")
        ttk.Button(bf, text="💾 Speichern", command=_save).pack(side="right", padx=4)

    # ── A1: AI-Copilot ───────────────────────────────────────────────────────

    def _ai_explain_cluster(self):
        """Ruft ai_copilot.py auf und zeigt die Erklärung im Cluster-Detail an."""
        try:
            from ancestry.core.ai_copilot import cluster_prompt, explain_async
        except ImportError:
            messagebox.showinfo("AI-Copilot", "ai_copilot nicht verfügbar.")
            return

        sel = self._cluster_list.selection()
        if not sel:
            messagebox.showinfo("AI-Copilot", "Bitte zuerst einen Cluster auswählen.")
            return
        cluster_id = int(sel[0])

        self._ai_explain_label.set("⏳ Lade AI-Erklärung …")

        members = self._clusters.get(cluster_id, [])
        # Baue die Mitgliederliste mit allen verfügbaren Feldern
        match_list = [
            {"name": m.get("name", ""), "cm": m.get("cm", 0),
             "rel_type": m.get("rel", ""), "probable_origin": m.get("origin", "")}
            for m in members
        ]

        prompt = cluster_prompt(cluster_id, match_list)
        if not prompt:
            self._ai_explain_label.set("Keine Daten für AI-Erklärung.")
            return

        accumulated: list[str] = []

        def _on_chunk(chunk: str):
            accumulated.append(chunk)
            text = "".join(accumulated)[:500]
            self.after(0, lambda t=text: self._ai_explain_label.set(t))

        def _on_done(text: str):
            self.after(0, lambda t=text: self._ai_explain_label.set(t[:500]))

        explain_async(prompt, on_chunk=_on_chunk, on_done=_on_done)

    # ── A2: Triangulations-Bericht ────────────────────────────────────────────

    def _open_triangulation_report(self):
        import webbrowser
        try:
            from ancestry.paths import EXPORT_DIR
            import os
            path = str(EXPORT_DIR / "triangulation_report.html")
            if os.path.exists(path):
                webbrowser.open(f"file://{path}")
            else:
                messagebox.showinfo(
                    "Bericht",
                    f"Kein Bericht unter:\n{path}\n\n"
                    "Bitte zuerst Triangulation ausführen\n"
                    "(Menü → Analyse → Segment-Triangulation).")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    # ── A1: Chromosomen-Browser ───────────────────────────────────────────────

    def _open_chromosome_browser(self):
        """Öffnet den Chromosomen-Browser für den aktuell selektierten Match."""
        from ancestry.gui.analysis.chromosome_browser import show_chromosome_browser

        test_guid = self._get_current_guid()
        if not test_guid:
            messagebox.showwarning(
                self._state.t("dlg.no_kit"),
                self._state.t("dlg.m_choose_kit"),
            )
            return

        # Selektierten Match aus dem Mitglieder-Treeview holen
        sel_member = self._member_tree.selection()
        sel_cluster = self._cluster_list.selection()

        match_guid: str | None = None
        match_name: str = ""

        if sel_member:
            # Zeile im Member-Tree: Name in Spalte 0
            vals = self._member_tree.item(sel_member[0], "values")
            if vals:
                match_name = vals[0]
                # GUID über aktiven Cluster suchen
                if sel_cluster:
                    cid = int(sel_cluster[0])
                    for m in self._clusters.get(cid, []):
                        if m["name"] == match_name:
                            match_guid = m["guid"]
                            break
        elif sel_cluster:
            # Kein Match ausgewählt: Top-Match des Clusters nehmen
            cid = int(sel_cluster[0])
            members = self._clusters.get(cid, [])
            if members:
                match_guid = members[0]["guid"]
                match_name = members[0]["name"]

        if not match_guid:
            messagebox.showinfo(
                "Chromosomen-Browser",
                "Bitte zuerst einen Match im Cluster-Mitglieder-Panel auswählen.",
            )
            return

        try:
            show_chromosome_browser(
                self, self._state, test_guid, match_guid, match_name
            )
        except Exception as exc:
            log.exception("chromosome_browser: %s", exc)
            messagebox.showerror(
                "Chromosomen-Browser",
                f"Fehler beim Öffnen:\n{exc}\n\n"
                "Möglicherweise sind keine Segmentdaten vorhanden.",
            )

    # ── B3: Phasing-Panel ────────────────────────────────────────────────────

    def _build_phasing_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="🧬 Phasing – Elternlinie", padding=6)
        frame.pack(fill="x", padx=14, pady=(0, 4))

        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="Mutter-Kit:").pack(side="left")
        self._phase_mother_var = tk.StringVar(value="")
        self._phase_mother_cb = ttk.Combobox(
            row, textvariable=self._phase_mother_var, width=24, state="readonly")
        self._phase_mother_cb.pack(side="left", padx=4)
        ttk.Button(row, text="📊 Phasing berechnen",
                   command=self._run_phasing).pack(side="left", padx=4)

        # 4-Quadrant Canvas
        self._phase_canvas = tk.Canvas(
            frame, height=160, bg="#f8f8f8",
            highlightthickness=1, highlightbackground="#cccccc")
        self._phase_canvas.pack(fill="x", pady=(4, 0))
        # B4: <Configure> bereits vorhanden; zusätzlich Scroll/Drag-Events
        # damit der Lazy-Canvas bei Viewport-Änderungen neu zeichnet.
        self._phase_canvas.bind("<Configure>", self._draw_phasing_quadrants)
        self._phase_canvas.bind("<MouseWheel>", self._draw_phasing_quadrants)
        self._phase_canvas.bind("<Button-4>", self._draw_phasing_quadrants)   # Linux scroll up
        self._phase_canvas.bind("<Button-5>", self._draw_phasing_quadrants)   # Linux scroll down
        self._phase_canvas.bind("<B1-Motion>", self._draw_phasing_quadrants)

    def _populate_phase_kits(self):
        """Befüllt Mutter-Kit-Combobox aus dna_kits."""
        try:
            with self._state.db._cursor() as cur:
                rows = cur.execute(
                    "SELECT guid, name FROM dna_kits ORDER BY name"
                ).fetchall()
            values = [f"{r[1] or r[0]}" for r in rows]
            if hasattr(self, "_phase_mother_cb"):
                self._phase_mother_cb["values"] = values
        except Exception:
            pass

    def _draw_phasing_quadrants(self, event=None):
        """Zeichnet den Phasing-Canvas.

        B4: Lazy Loading — bei mehr als 100 Clustern werden nur die Segmente
        gezeichnet, die im aktuell sichtbaren Viewport liegen.  Bei ≤ 100
        Clustern bleibt das Verhalten unverändert (alle 4 Quadranten).
        """
        if not hasattr(self, "_phase_canvas"):
            return
        c = self._phase_canvas
        c.delete("all")
        w = c.winfo_width() or 300
        h = c.winfo_height() or 160

        n_clusters = len(self._clusters)

        if n_clusters <= 100:
            # Ursprüngliches Verhalten: 4 statische Quadranten
            colors = ["#DDF0FF", "#FFE0E0", "#DDF0FF", "#FFE0E0"]
            labels = [
                "Väterl.-Väterl.", "Väterl.-Mütterl.",
                "Mütterl.-Väterl.", "Mütterl.-Mütterl.",
            ]
            for i, (col, lbl) in enumerate(zip(colors, labels)):
                x0 = (i % 2) * w // 2
                y0 = (i // 2) * h // 2
                x1 = x0 + w // 2
                y1 = y0 + h // 2
                c.create_rectangle(x0, y0, x1, y1, fill=col, outline="#aaaaaa")
                c.create_text(
                    (x0 + x1) // 2, (y0 + y1) // 2, text=lbl,
                    font=("Segoe UI", 8), fill="#444444",
                )
        else:
            # B4: Lazy-Loading — Cluster als kleine farbige Kacheln rendern,
            # nur sichtbare Kacheln (innerhalb des Viewports) werden gezeichnet.
            TILE_W = 28
            TILE_H = 22
            PADDING = 2

            # Scroll-Offset des Canvas ermitteln
            try:
                scroll_y = c.yview()
                total_rows = -(-n_clusters // max(w // (TILE_W + PADDING), 1))
                total_h = total_rows * (TILE_H + PADDING)
                vy0 = int(scroll_y[0] * total_h)
                vy1 = int(scroll_y[1] * total_h)
            except Exception:
                vy0 = 0
                vy1 = h

            cols_per_row = max(w // (TILE_W + PADDING), 1)
            cluster_ids = sorted(self._clusters.keys())
            cluster_colors = COLORS["cluster"]

            # Hintergrund
            c.create_rectangle(0, 0, w, h, fill="#f8f8f8", outline="")
            c.create_text(
                4, 4, text=f"Cluster-Kacheln ({n_clusters} gesamt) — Lazy View",
                anchor="nw", font=("Segoe UI", 7), fill="#888888",
            )

            for idx, cid in enumerate(cluster_ids):
                row_idx = idx // cols_per_row
                col_idx = idx % cols_per_row
                tile_y0 = row_idx * (TILE_H + PADDING)
                tile_y1 = tile_y0 + TILE_H

                # Nur Kacheln im sichtbaren Viewport zeichnen (Lazy Loading)
                if tile_y1 < vy0 or tile_y0 > vy1:
                    continue

                tile_x0 = col_idx * (TILE_W + PADDING)
                tile_x1 = tile_x0 + TILE_W
                color = self._cluster_side_colors.get(
                    cid, cluster_colors[(cid - 1) % len(cluster_colors)]
                )
                c.create_rectangle(
                    tile_x0, tile_y0, tile_x1, tile_y1,
                    fill=color, outline="#aaaaaa",
                )
                n_members = len(self._clusters.get(cid, []))
                c.create_text(
                    (tile_x0 + tile_x1) // 2, (tile_y0 + tile_y1) // 2,
                    text=str(n_members), font=("Segoe UI", 7), fill="#333333",
                )

    def _run_phasing(self):
        """Auto-Phasing via Mutter-Kit: ordnet Cluster maternal/paternal zu."""
        self._draw_phasing_quadrants()

        # --- Mutter-Kit ermitteln ---
        mother_name = self._phase_mother_var.get().strip()
        if not mother_name:
            messagebox.showwarning(
                "Phasing",
                "Bitte zuerst ein Mutter-Kit in der Combobox auswählen.",
            )
            return

        test_guid = self._get_current_guid()
        if not test_guid:
            messagebox.showwarning(
                self._state.t("dlg.no_kit"),
                self._state.t("dlg.m_choose_kit"),
            )
            return

        if not self._clusters:
            messagebox.showinfo("Phasing", "Zuerst Cluster berechnen.")
            return

        # --- Mutter-Kit-GUID aus dna_kits holen ---
        try:
            with self._state.db._cursor() as cur:
                row = cur.execute(
                    "SELECT guid FROM dna_kits WHERE name = ? OR guid = ? LIMIT 1",
                    (mother_name, mother_name),
                ).fetchone()
        except Exception as exc:
            messagebox.showerror("Phasing – DB-Fehler", str(exc))
            return

        if not row:
            messagebox.showerror(
                "Phasing",
                f"Mutter-Kit '{mother_name}' nicht in dna_kits gefunden.",
            )
            return
        mother_guid = row[0]

        # --- Shared-Match-GUIDs des Mutter-Kits laden ---
        try:
            with self._state.db._cursor() as cur:
                sm_rows = cur.execute(
                    """SELECT match_guid_b FROM shared_matches
                       WHERE test_guid = ?
                       UNION
                       SELECT match_guid_a FROM shared_matches
                       WHERE test_guid = ? AND match_guid_b = ?""",
                    (mother_guid, test_guid, mother_guid),
                ).fetchall()
        except Exception as exc:
            messagebox.showerror("Phasing – DB-Fehler", str(exc))
            return

        mother_match_set: set[str] = {r[0] for r in sm_rows if r[0]}

        if not mother_match_set:
            messagebox.showwarning(
                "Phasing",
                f"Keine Shared Matches für Mutter-Kit '{mother_name}' gefunden.\n"
                "Bitte zunächst Shared Matches herunterladen.",
            )
            return

        # --- Je Cluster: Anteil mütterlicher Matches zählen ---
        cluster_result: list[tuple[int, str, int, int]] = []
        # (cid, side, n_maternal, n_total)
        for cid, members in self._clusters.items():
            guids = [m["guid"] for m in members]
            n_maternal = sum(1 for g in guids if g in mother_match_set)
            n_total = len(guids)
            ratio = n_maternal / n_total if n_total else 0.0
            side = "maternal" if ratio >= 0.5 else "paternal"
            cluster_result.append((cid, side, n_maternal, n_total))

        # --- matches.phase_status updaten + paternal_maternal setzen ---
        updated = 0
        errors: list[str] = []
        for cid, side, _, _ in cluster_result:
            guids = [m["guid"] for m in self._clusters.get(cid, [])]
            if not guids:
                continue
            try:
                with self._state.db._cursor() as cur:
                    cur.execute(
                        "UPDATE matches SET paternal_maternal = ? "
                        "WHERE match_guid IN ({})".format(",".join("?" * len(guids))),
                        [side, *guids],
                    )
                updated += len(guids)
            except Exception as exc:
                errors.append(f"Cluster #{cid}: {exc}")

        # --- Cluster-Farben aktualisieren (maternal=rot, paternal=blau) ---
        for cid, side, _, _ in cluster_result:
            if side == "maternal":
                color = "#FFE0E0"
                side_icon = "🔴 "
            else:
                color = "#DDF0FF"
                side_icon = "🔵 "
            self._cluster_side_colors[cid] = color
            self._cluster_list.tag_configure(f"c{cid}", background=color)
            # Top-Match-Text im Treeview aktualisieren
            if self._cluster_list.exists(str(cid)):
                vals = list(self._cluster_list.item(str(cid), "values"))
                if vals and len(vals) >= 4:
                    # Seiten-Icon in Spalte "top" (Index 3) setzen
                    raw_name = vals[3].lstrip("🔵🔴 ")
                    vals[3] = side_icon + raw_name
                    self._cluster_list.item(str(cid), values=vals)
        # B1: Neue Farben persistieren
        self._save_cluster_colors()

        # --- Phasing-Canvas neu zeichnen ---
        self._draw_phasing_quadrants()

        # --- Statusmeldung ---
        n_mat = sum(1 for _, s, _, _ in cluster_result if s == "maternal")
        n_pat = sum(1 for _, s, _, _ in cluster_result if s == "paternal")
        mat_matches = sum(n for _, s, n, _ in cluster_result if s == "maternal")
        pat_matches = sum(n - n_m for _, s, n, n_m in
                         [(c, si, nt, nm) for c, si, nm, nt in cluster_result]
                         if s == "paternal")
        msg = (
            f"Phasing abgeschlossen: {n_mat} Cluster maternal "
            f"({mat_matches} Matches), {n_pat} Cluster paternal. "
            f"{updated} Match-Datensätze aktualisiert."
        )
        if errors:
            msg += f"\nFehler: {'; '.join(errors[:3])}"
        self._set_status(msg)
        messagebox.showinfo("Phasing", msg)

    # ── A1: user_prefs Hilfsmethoden ─────────────────────────────────────────

    def _pref_get(self, key: str, default: str = "") -> str:
        """Liest einen Wert aus user_prefs. Gibt default zurück bei Fehler."""
        try:
            with self._state.db._cursor() as cur:
                row = cur.execute(
                    "SELECT value FROM user_prefs WHERE key = ?", (key,)
                ).fetchone()
            return row[0] if row else default
        except Exception as exc:
            log.debug("_pref_get(%s): %s", key, exc)
            return default

    def _pref_set(self, key: str, value: str) -> None:
        """Schreibt einen Wert in user_prefs (INSERT OR REPLACE)."""
        try:
            with self._state.db._cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO user_prefs (key, value) VALUES (?, ?)",
                    (key, value),
                )
        except Exception as exc:
            log.debug("_pref_set(%s): %s", key, exc)

    def _save_col_widths(self, tree: ttk.Treeview, cols: tuple, prefix: str) -> None:
        """Speichert Spaltenbreiten des gegebenen Treeview in user_prefs."""
        for col in cols:
            try:
                w = tree.column(col, "width")
                self._pref_set(f"{prefix}_{col}", str(w))
            except Exception:
                pass

    def _load_col_widths(self, tree: ttk.Treeview, cols: tuple, prefix: str) -> None:
        """Lädt und wendet gespeicherte Spaltenbreiten aus user_prefs an."""
        for col in cols:
            raw = self._pref_get(f"{prefix}_{col}", "")
            if raw:
                try:
                    w = int(raw)
                    if w >= 20:
                        tree.column(col, width=w)
                except (ValueError, tk.TclError) as exc:
                    log.debug("_load_col_widths(%s/%s): %s", prefix, col, exc)

    # ── B1: Cluster-Farb-Persistierung ───────────────────────────────────────

    def _save_cluster_colors(self):
        """Schreibt aktuelle Cluster-Farben (side + color) in cluster_colors-Tabelle."""
        kit_id = self._get_current_guid()
        if not kit_id or not self._cluster_side_colors:
            return
        try:
            with self._state.db._cursor() as cur:
                for cid, color in self._cluster_side_colors.items():
                    if color == "#DDF0FF":
                        side = "paternal"
                    elif color == "#FFE0E0":
                        side = "maternal"
                    else:
                        side = ""
                    cur.execute(
                        """INSERT OR REPLACE INTO cluster_colors
                           (kit_id, cluster_id, side, color)
                           VALUES (?, ?, ?, ?)""",
                        (kit_id, str(cid), side, color),
                    )
        except Exception as exc:
            log.debug("_save_cluster_colors: %s", exc)

    def _load_cluster_colors(self):
        """Lädt Cluster-Farben aus DB und wendet sie auf den Treeview an."""
        kit_id = self._get_current_guid()
        if not kit_id:
            return
        try:
            with self._state.db._cursor() as cur:
                rows = cur.execute(
                    "SELECT cluster_id, color FROM cluster_colors WHERE kit_id = ?",
                    (kit_id,),
                ).fetchall()
        except Exception as exc:
            log.debug("_load_cluster_colors: %s", exc)
            return
        for row in rows:
            try:
                cid = int(row[0])
            except (ValueError, TypeError):
                continue
            color = row[1] or ""
            if not color:
                continue
            # Nur anwenden wenn der Cluster im Treeview vorhanden ist
            if str(cid) in self._cluster_list.get_children():
                self._cluster_side_colors[cid] = color
                self._cluster_list.tag_configure(f"c{cid}", background=color)

    # ── Phasing-Dashboard ─────────────────────────────────────────────────────

    def _show_phasing(self):
        from ancestry.gui.analysis.cluster_views import show_phasing_dashboard
        show_phasing_dashboard(self, self._clusters, set_status=self._set_status)

    def _show_dna_segments(self):
        from ancestry.gui.analysis.segment_views import show_dna_segments
        show_dna_segments(self, self._state.db, self._get_test_guid(),
                          set_status=self._set_status)

    # ── MRCA-Karte (Leaflet-HTML) ─────────────────────────────────────────────

    def _show_mrca_map(self):
        import webbrowser

        from ancestry.core.mrca_map import aggregate_mrca_places, build_mrca_map_html
        from ancestry.paths import EXPORT_DIR

        test_guid = self._get_current_guid()
        if not test_guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dlg.m_choose_kit"))
            return
        # nur Matches aus den berechneten Clustern (falls vorhanden), sonst alle
        guids = [m["guid"] for mlist in self._clusters.values() for m in mlist] or None
        try:
            rows = self._state.db.get_match_birthplaces(test_guid, guids)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(self._state.t("dlg.error"), str(e))
            return
        places = aggregate_mrca_places(rows)
        if not places:
            messagebox.showinfo(
                self._state.t("cl.no_coords_t"),
                self._state.t("cl.m_no_coords"))
            return
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = EXPORT_DIR / "mrca_map.html"
        out.write_text(build_mrca_map_html(places, "MRCA-Karte"), encoding="utf-8")
        webbrowser.open(out.as_uri())
        self._set_status(f"MRCA-Karte: {len(places)} Orte → {out}")

    def _export_clusters(self):
        if not self._clusters:
            messagebox.showinfo("Export", "Zuerst Cluster berechnen.")
            return
        import csv
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(
            title="Cluster als CSV exportieren",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Alle", "*.*")],
            initialfile="cluster_export.csv")
        if not p:
            return
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Cluster", "Mitglieder", "Top-Match", "Max-cM",
                         "Ø-cM", "Seite", "Beschreibung"])
            descs = self._state.ui_settings.get("cluster_descs", {})
            test_guid = self._get_current_guid() or ""
            try:
                rows_side = self._state.db._get_conn().execute(
                    "SELECT match_guid, paternal_maternal FROM matches WHERE test_guid=?",
                    (test_guid,)).fetchall()
                side_map = {r["match_guid"]: (r["paternal_maternal"] or "") for r in rows_side}
            except Exception:
                side_map = {}
            for cid, members in sorted(self._clusters.items()):
                cms = [m["cm"] for m in members]
                top = members[0]["name"] if members else ""
                sides = {side_map.get(m["guid"], "") for m in members} - {""}
                w.writerow([
                    f"#{cid}", len(members), top,
                    f"{max(cms):.1f}" if cms else "",
                    f"{sum(cms)/len(cms):.1f}" if cms else "",
                    "/".join(sorted(sides)),
                    descs.get(str(cid), ""),
                ])
        messagebox.showinfo("Export", f"{len(self._clusters)} Cluster → {p}")

    # ── C3: Cluster-Report als HTML ──────────────────────────────────────────

    def _export_cluster_report(self):
        """Exportiert alle Cluster als HTML-Bericht und öffnet ihn im Browser."""
        if not self._clusters:
            messagebox.showinfo("Report", "Zuerst Cluster berechnen.")
            return

        kit_id = self._get_current_guid() or "—"
        path = filedialog.asksaveasfilename(
            title="Cluster-Report speichern",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("Alle", "*.*")],
            initialfile="cluster_report.html",
        )
        if not path:
            return

        today = datetime.date.today().strftime("%d.%m.%Y")
        descs = self._load_settings().get("cluster_descs", {})
        cluster_colors_html = COLORS["cluster"]

        rows_html = []
        for cid, members in sorted(self._clusters.items()):
            color = self._cluster_side_colors.get(
                cid, cluster_colors_html[(cid - 1) % len(cluster_colors_html)]
            )
            # Seite ermitteln
            if color == "#DDF0FF":
                side = "paternal"
            elif color == "#FFE0E0":
                side = "maternal"
            else:
                side = "—"
            n = len(members)
            desc = descs.get(str(cid), "")
            color_box = (
                f'<span style="display:inline-block;width:18px;height:18px;'
                f'background:{color};border:1px solid #aaa;'
                f'vertical-align:middle;border-radius:3px;"></span>'
            )
            rows_html.append(
                f"<tr>"
                f"<td style='text-align:center'>#{cid}</td>"
                f"<td style='text-align:center'>{n}</td>"
                f"<td>{side}</td>"
                f"<td style='text-align:center'>{color_box}</td>"
                f"<td>{desc}</td>"
                f"</tr>"
            )

        table_body = "\n".join(rows_html)
        html = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Cluster-Report — Kit {kit_id}</title>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 32px; color: #222; }}
    h1   {{ color: #1A1A2E; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th   {{ background: #1A1A2E; color: #fff; padding: 8px 12px; text-align: left; }}
    td   {{ padding: 6px 12px; border-bottom: 1px solid #e0e0e0; }}
    tr:nth-child(even) td {{ background: #f7f7f7; }}
    footer {{ margin-top: 32px; color: #888; font-size: 0.85em; }}
  </style>
</head>
<body>
  <h1>Cluster-Report — Kit {kit_id}</h1>
  <p>Erstellt am {today} &nbsp;|&nbsp; {len(self._clusters)} Cluster</p>
  <table>
    <thead>
      <tr>
        <th>Cluster-ID</th>
        <th>Anzahl Matches</th>
        <th>Seite</th>
        <th>Farbe</th>
        <th>Beschreibung</th>
      </tr>
    </thead>
    <tbody>
{table_body}
    </tbody>
  </table>
  <footer>Erstellt mit dem Genealogie-DNA-Analyse-Tool &mdash; {today}</footer>
</body>
</html>
"""
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
        except OSError as exc:
            messagebox.showerror("Report – Fehler", str(exc))
            return

        self._set_status(f"Cluster-Report gespeichert: {path}")
        webbrowser.open(f"file://{path}")

    # ── Stammbaum-Analyse-Popup ───────────────────────────────────────────────

    def _show_tree(self):
        sel = self._cluster_list.selection()
        if not sel:
            messagebox.showinfo(self._state.t("dlg.no_cluster"),
                                self._state.t("dlg.m_choose_cluster"))
            return
        cid     = int(sel[0])
        members = self._clusters.get(cid, [])
        if not members:
            return
        test_guid = self._get_current_guid()
        if not test_guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"), self._state.t("dlg.m_choose_kit"))
            return

        guids   = {m["guid"] for m in members}
        id_name = {m["guid"]: m["name"] for m in members}
        all_peds = self._state.db.get_all_pedigrees(test_guid, match_guids=list(guids))

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
                        "generations": set(),
                        "guid_gens": {},
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

        color = COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])]
        win = tk.Toplevel(self)
        win.title(f"Cluster #{cid} – Stammbaum-Analyse ({len(members)} Matches)")
        win.geometry("1150x680")
        win.configure(bg=color)

        n_total = len(members)
        ttk.Label(win,
                  text=(f"Cluster #{cid} · {n_total} Mitglieder · "
                        f"{len(persons)} einzigartige Vorfahren in den Ahnentafeln"),
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        register_lang(self._state, ttk.Label(win,
                  text=(self._state.t("cl.tree_legend")),
                  foreground="#333333"), "cl.tree_legend").pack(anchor="w", padx=12, pady=(2, 6))

        t = self._state.t
        cols  = ("count", "person", "birth", "place", "gen", "matches")
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
            tv.heading(c, text=t(key), command=lambda c=c: _sort(c))
            tv.column(c, width=w,
                      anchor=("center" if c in ("count", "birth", "gen") else "w"),
                      stretch=(c == "matches"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tv.tag_configure("all",  background="#D6F5E3")
        tv.tag_configure("many", background="#FFD6D6")
        tv.tag_configure("two",  background="#FFF3CD")
        tv.tag_configure("one",  background="#FFFFFF")

        st = {"col": "count", "desc": True}

        def _fill():
            col, desc = st["col"], st["desc"]
            sort_key = {
                "count":   lambda p: -len(p["guids"]),
                "person":  lambda p: (p["surname"] + " " + p["given"]).lower(),
                "birth":   lambda p: p["birth_year"] or "9999",
                "place":   lambda p: p["birth_place"].lower(),
                "gen":     lambda p: min(p["generations"]) if p["generations"] else 99,
                "matches": lambda p: ", ".join(sorted(p["names"])),
            }
            data = sorted(persons,
                          key=sort_key.get(col, sort_key["count"]),
                          reverse=(desc and col == "count"))
            tv.delete(*tv.get_children())
            for p in data:
                n  = len(p["guids"])
                nm = f"{p['given']} {p['surname']}".strip() or "?"
                all_gens = sorted(p["generations"])
                gen_str  = "/".join(str(g) for g in all_gens)
                show_ann = len(all_gens) > 1
                match_parts = []
                for guid in sorted(p["guids"], key=lambda g: id_name.get(g, g)):
                    mname = id_name.get(guid, guid[:10])
                    if show_ann:
                        gg = sorted(p["guid_gens"].get(guid, set()))
                        if gg:
                            mname += f" ({', '.join(str(g) for g in gg)})"
                    match_parts.append(mname)
                ms  = ", ".join(match_parts)
                tag = ("all"  if n >= n_total and n_total > 1
                       else "many" if n >= 3
                       else "two"  if n >= 2
                       else "one")
                tv.insert("", "end", tags=(tag,), values=(
                    n, nm, p["birth_year"], p["birth_place"], gen_str, ms))

        def _sort(col):
            st["desc"] = not st["desc"] if st["col"] == col else True
            st["col"]  = col
            _fill()

        _fill()

        n_shared = sum(1 for p in persons if len(p["guids"]) >= 2)
        n_all    = sum(1 for p in persons if len(p["guids"]) >= n_total and n_total > 1)
        ttk.Label(win,
                  text=(f"Personen in ≥2 Bäumen: {n_shared}  |  "
                        f"In allen {n_total} Bäumen: {n_all}  "
                        f"(Klick auf Spaltenköpfe = sortieren)"),
                  foreground="#444444").pack(anchor="w", padx=12, pady=(0, 6))
        mf = ttk.LabelFrame(win, text="Cluster-Mitglieder", padding=4)
        mf.pack(fill="x", padx=12, pady=(0, 8))
        for i, m in enumerate(sorted(members, key=lambda x: -(x["cm"] or 0))):
            ttk.Label(mf, text=f"#{i + 1} {m['name']}  ({m['cm']:.0f} cM)",
                      foreground=COLORS["primary"]).grid(
                row=0, column=i, padx=10, pady=2, sticky="w")

    # ── B3: Cluster-Merge-UI ─────────────────────────────────────────────────

    def _on_cluster_right_click(self, event):
        """Selektiert die angeklickte Row und öffnet das Kontextmenü."""
        iid = self._cluster_list.identify_row(event.y)
        if iid:
            self._cluster_list.selection_set(iid)
            self._cluster_list.focus(iid)
        try:
            self._cluster_ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._cluster_ctx_menu.grab_release()

    def _merge_cluster_dialog(self):
        """Öffnet Dialog zum Zusammenführen des gewählten Clusters mit einem anderen."""
        sel = self._cluster_list.selection()
        if not sel:
            messagebox.showinfo("Merge", "Bitte zuerst einen Cluster auswählen.")
            return
        src_cid = int(sel[0])
        other_cids = [cid for cid in self._clusters if cid != src_cid]
        if not other_cids:
            messagebox.showinfo("Merge", "Keine weiteren Cluster vorhanden.")
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Cluster #{src_cid} zusammenführen mit …")
        dlg.geometry("320x300")
        dlg.resizable(False, False)

        ttk.Label(
            dlg,
            text=f"Cluster #{src_cid} ({len(self._clusters[src_cid])} Matches)\n"
                 "→ alle Matches werden in den Ziel-Cluster verschoben.",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        ttk.Label(dlg, text="Ziel-Cluster wählen:").pack(anchor="w", padx=12)

        lb_frame = ttk.Frame(dlg)
        lb_frame.pack(fill="both", expand=True, padx=12, pady=4)
        lb = tk.Listbox(lb_frame, selectmode="browse", font=("Segoe UI", 9))
        lb_sb = ttk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=lb_sb.set)
        lb.pack(side="left", fill="both", expand=True)
        lb_sb.pack(side="right", fill="y")

        for cid in sorted(other_cids):
            members = self._clusters.get(cid, [])
            top = members[0]["name"] if members else "—"
            lb.insert("end", f"#{cid}  ({len(members)} Matches)  Top: {top}")

        def _do_merge():
            idx = lb.curselection()
            if not idx:
                messagebox.showwarning("Merge", "Kein Ziel-Cluster ausgewählt.")
                return
            dst_cid = sorted(other_cids)[idx[0]]
            dlg.destroy()
            self._execute_merge(src_cid, dst_cid)

        bf = ttk.Frame(dlg)
        bf.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(bf, text="Abbrechen", command=dlg.destroy).pack(side="right")
        ttk.Button(bf, text="✅ OK – Zusammenführen",
                   command=_do_merge).pack(side="right", padx=4)

    def _execute_merge(self, src_cid: int, dst_cid: int):
        """Verschiebt alle Matches von src_cid → dst_cid, aktualisiert Treeview."""
        test_guid = self._get_current_guid()
        src_members = self._clusters.get(src_cid, [])
        dst_members = self._clusters.get(dst_cid, [])

        if not src_members:
            messagebox.showinfo("Merge", f"Cluster #{src_cid} ist leer.")
            return

        src_guids = [m["guid"] for m in src_members]

        # DB-Update: cluster_id gibt es nicht als Spalte in matches — wir
        # ändern stattdessen paternal_maternal um Konsistenz zu wahren und
        # schreiben in cluster_colors die neue Zuordnung.
        # Die In-Memory-Datenstruktur wird sofort aktualisiert.
        try:
            # Übernehme Seite des Ziel-Clusters
            dst_color = self._cluster_side_colors.get(
                dst_cid, COLORS["cluster"][(dst_cid - 1) % len(COLORS["cluster"])]
            )
            if dst_color == "#DDF0FF":
                dst_side = "paternal"
            elif dst_color == "#FFE0E0":
                dst_side = "maternal"
            else:
                dst_side = ""

            if dst_side and src_guids:
                with self._state.db._cursor() as cur:
                    cur.execute(
                        "UPDATE matches SET paternal_maternal = ? "
                        "WHERE match_guid IN ({})".format(
                            ",".join("?" * len(src_guids))
                        ),
                        [dst_side, *src_guids],
                    )
        except Exception as exc:
            log.warning("merge DB update: %s", exc)

        # In-Memory: src-Matches in dst verschieben
        combined = dst_members + src_members
        self._clusters[dst_cid] = combined
        del self._clusters[src_cid]

        # Src-Farbe aufräumen
        self._cluster_side_colors.pop(src_cid, None)

        # Treeview aktualisieren
        # Src-Row entfernen
        if self._cluster_list.exists(str(src_cid)):
            self._cluster_list.delete(str(src_cid))

        # Dst-Row aktualisieren
        if self._cluster_list.exists(str(dst_cid)):
            new_n = len(combined)
            cms = [m["cm"] for m in combined]
            dst_vals = list(self._cluster_list.item(str(dst_cid), "values"))
            if dst_vals:
                dst_vals[1] = new_n
                if cms:
                    dst_vals[2] = f"{max(cms):.0f}"
                self._cluster_list.item(str(dst_cid), values=dst_vals)

        # B1: Persistierung
        self._save_cluster_colors()

        self._set_status(
            f"Cluster #{src_cid} → #{dst_cid} zusammengeführt "
            f"({len(combined)} Matches)."
        )

    # ── Tab-Lebenszyklus ──────────────────────────────────────────────────────

    def on_show(self):
        """Wird aufgerufen wenn dieser Tab aktiviert wird."""
        # B1: Persistierte Cluster-Farben wiederherstellen
        self._load_cluster_colors()
        # Combobox mit aktuellen Kits befüllen
        self._populate_phase_kits()

    # ── Public accessor für _show_cluster_tree (Rückwärtskompatibilität) ──────

    def get_clusters(self) -> dict:
        return self._clusters

    def get_cluster_list_selection(self):
        return self._cluster_list.selection()
