"""Matches-Tab: Tabellenansicht mit Filtern, Detail-Panel und Sub-Tabs."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Callable, Optional
from urllib.parse import quote

from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import register_lang, COLORS
from ancestry.gui.widgets.tooltip import register_tooltip
from ancestry.models import DnaMatch

log = logging.getLogger(__name__)


class MatchesTab(ttk.Frame):
    """Matches-Tab des Ancestry-DNA-Tools.

    Parameters
    ----------
    parent:
        ttk.Frame aus dem Notebook.
    state:
        Gemeinsamer App-Zustand.
    get_test_guid:
        Liefert die aktuelle primäre Test-GUID (oder None).
    get_gedcom:
        Liefert den geladenen GEDCOM-Cache (oder None).
    load_ui_settings:
        Lädt das UI-Settings-Dict.
    save_ui_settings:
        Speichert UI-Settings-Schlüssel.
    set_status:
        Setzt die App-Statuszeile.
    cm_ranges:
        cM → Verwandtschafts-Tabelle (Shared cM Project) für den MRCA-Hinweis.
    on_auto_assign_sides / on_gedmatch_bridge:
        Aktionen der Kit-Leiste (bleiben in app.py).
    on_goto_download:
        Wechselt zum Download-Tab (Empty-State-Button).
    on_choose_gedcom / on_gedcom_match_all / on_endogamy_transfer /
    on_xref_review / on_ml_origin / on_wikitree_extend / on_origin_inference:
        Aktionen der GEDCOM-Treffer-Toolbar (bleiben in app.py).
    on_gedcom_header_update:
        Zeigt den GEDCOM-Dateinamen im Panel-Header an.
    """

    _ALL_SOURCES_LABEL = "— Alle Plattformen —"

    # Max. Zeilen, die in die Tabelle eingefügt werden. Bei sehr großen
    # Beständen (>50.000 Matches) würde ein vollständiges Befüllen des
    # Tkinter-Treeview die GUI minutenlang einfrieren. Wir zeigen die nach
    # cM wichtigsten Treffer; der Rest ist über Suche/Filter erreichbar.
    _MAX_DISPLAY_ROWS = 2000

    def __init__(
        self,
        parent: tk.Widget,
        state: AppState,
        get_test_guid:           Callable[[], Optional[str]],
        get_gedcom:              Callable[[], Optional[dict]],
        load_ui_settings:        Callable[[], dict],
        save_ui_settings:        Callable[..., None],
        set_status:              Callable[[str], None],
        cm_ranges:               list,
        on_auto_assign_sides:    Callable,
        on_gedmatch_bridge:      Callable,
        on_goto_download:        Callable,
        on_choose_gedcom:        Callable,
        on_gedcom_match_all:     Callable,
        on_endogamy_transfer:    Callable,
        on_xref_review:          Callable,
        on_ml_origin:            Callable,
        on_wikitree_extend:      Callable,
        on_origin_inference:     Callable,
        on_gedcom_header_update: Callable[[dict], None],
    ):
        super().__init__(parent)
        self._state                   = state
        self._get_test_guid           = get_test_guid
        self._get_gedcom              = get_gedcom
        self._load_ui_settings        = load_ui_settings
        self._save_ui_settings        = save_ui_settings
        self._set_status              = set_status
        self._cm_ranges               = cm_ranges
        self._on_auto_assign_sides    = on_auto_assign_sides
        self._on_gedmatch_bridge      = on_gedmatch_bridge
        self._on_goto_download        = on_goto_download
        self._on_choose_gedcom        = on_choose_gedcom
        self._on_gedcom_match_all     = on_gedcom_match_all
        self._on_endogamy_transfer    = on_endogamy_transfer
        self._on_xref_review          = on_xref_review
        self._on_ml_origin            = on_ml_origin
        self._on_wikitree_extend      = on_wikitree_extend
        self._on_origin_inference     = on_origin_inference
        self._on_gedcom_header_update = on_gedcom_header_update

        self._matches: list = []
        self._matches_kit_guid_map: dict = state.matches_kit_guid_map
        self._selected_match: Optional[DnaMatch] = None
        self._build()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_match(self) -> Optional[DnaMatch]:
        return self._selected_match

    @property
    def matches(self) -> list:
        return self._matches

    def update_kit_combo(self):
        """Befüllt den Kit-Selektor im Matches-Tab aus DB + kit_map."""
        if not hasattr(self, "_matches_kit_combo"):
            return
        try:
            db_kits = self._state.db.get_kits()
        except Exception as e:
            log.debug("update_kit_combo get_kits: %s", e)
            db_kits = []
        combined: dict[str, str] = {}
        # Sentinel für plattformübergreifende Ansicht
        combined[self._ALL_SOURCES_LABEL] = ""
        for k in db_kits:
            name = k.name or f"Kit {k.guid[:8]}"
            combined[name] = k.guid
        for name, guid in self._state.kit_map.items():
            combined.setdefault(name, guid)
        self._matches_kit_guid_map = combined
        names = list(combined.keys())
        self._matches_kit_combo["values"] = names
        if names and self._matches_kit_var.get() not in names:
            self._matches_kit_combo.current(0)

    def _on_search_changed(self, *_):
        if hasattr(self, "_search_after_id"):
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(300, self.refresh)

    def refresh(self, *_):
        try:
            self._refresh_match_table_inner()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("_refresh_match_table fehlgeschlagen")
            try:
                if hasattr(self, "_match_count_var"):
                    self._match_count_var.set(f"⚠ Fehler: {exc}")
            except Exception as e:
                log.debug("match_count_var update: %s", e)

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        f  = self
        t  = self._state.t
        lw = self._state.lang_widgets

        # Kit-Leiste
        kl = ttk.Frame(f); kl.pack(fill="x", padx=10, pady=(6, 0))
        _sv_kit = tk.StringVar(value=t("mf.kit"))
        ttk.Label(kl, textvariable=_sv_kit, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        lw.append((_sv_kit, "mf.kit"))
        self._matches_kit_var = tk.StringVar()
        self._matches_kit_combo = ttk.Combobox(
            kl, textvariable=self._matches_kit_var, width=38, state="readonly")
        self._matches_kit_combo.pack(side="left")
        self._matches_kit_combo.bind(
            "<<ComboboxSelected>>", lambda _: self.refresh())
        _sv_sides = tk.StringVar(value=t("mf.sides"))
        _b = ttk.Button(kl, textvariable=_sv_sides, command=self._on_auto_assign_sides)
        _b.pack(side="left", padx=(12, 0))
        register_tooltip(_b, "tt.mf_sides", self._state)
        lw.append((_sv_sides, "mf.sides"))
        _b = register_lang(self._state, ttk.Button(kl, text=self._state.t("mf.b_bridge"), command=self._on_gedmatch_bridge), "mf.b_bridge")
        _b.pack(side="left", padx=(8, 0))
        register_tooltip(_b, "tt.mf_bridge", self._state)

        # Filter-Leiste
        fl = ttk.Frame(f); fl.pack(fill="x", padx=10, pady=6)
        _sv_s = tk.StringVar(value=t("mf.search"))
        ttk.Label(fl, textvariable=_sv_s).pack(side="left", padx=(0,4))
        lw.append((_sv_s, "mf.search"))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)
        ttk.Entry(fl, textvariable=self._search_var, width=20).pack(side="left")

        _sv_r = tk.StringVar(value=t("mf.rel"))
        ttk.Label(fl, textvariable=_sv_r).pack(side="left", padx=(10,4))
        lw.append((_sv_r, "mf.rel"))
        self._rel_var = tk.StringVar(value="(alle)")
        self._rel_combo = ttk.Combobox(fl, textvariable=self._rel_var, width=22, state="readonly")
        self._rel_combo.pack(side="left")
        self._rel_combo.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        ttk.Label(fl, text="Seite:").pack(side="left", padx=(10,4))
        self._side_var = tk.StringVar(value="(alle)")
        ttk.Combobox(fl, textvariable=self._side_var, width=12, state="readonly",
                     values=["(alle)", "paternal", "maternal", "both"]).pack(side="left")
        self._side_var.trace_add("write", lambda *_: self.refresh())

        _sv_c = tk.StringVar(value=t("mf.mincm"))
        ttk.Label(fl, textvariable=_sv_c).pack(side="left", padx=(10,4))
        lw.append((_sv_c, "mf.mincm"))
        self._min_cm_var = tk.StringVar(value="0")
        ttk.Entry(fl, textvariable=self._min_cm_var, width=6).pack(side="left")
        ttk.Button(fl, text="↩", width=3, command=self.refresh).pack(side="left", padx=2)

        self._starred_var = tk.BooleanVar()
        _sv_starred = tk.StringVar(value=t("mf.starred"))
        ttk.Checkbutton(fl, textvariable=_sv_starred, variable=self._starred_var,
                        command=self.refresh).pack(side="left", padx=(10,0))
        lw.append((_sv_starred, "mf.starred"))
        self._tree_var = tk.BooleanVar()
        _sv_tree = tk.StringVar(value=t("mf.tree"))
        ttk.Checkbutton(fl, textvariable=_sv_tree, variable=self._tree_var,
                        command=self.refresh).pack(side="left", padx=6)
        lw.append((_sv_tree, "mf.tree"))
        self._hide_endo_var = tk.BooleanVar()
        _sv_endo = tk.StringVar(value=t("mf.endo"))
        ttk.Checkbutton(fl, textvariable=_sv_endo, variable=self._hide_endo_var,
                        command=self.refresh).pack(side="left", padx=6)
        lw.append((_sv_endo, "mf.endo"))
        _sv_autoendo = tk.StringVar(value=t("mf.endo_auto"))
        _b = ttk.Button(fl, textvariable=_sv_autoendo, command=self._auto_flag_endogamy)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.mf_endo_auto", self._state)
        lw.append((_sv_autoendo, "mf.endo_auto"))

        self._match_count_var = tk.StringVar(value="")
        ttk.Label(fl, textvariable=self._match_count_var,
                  foreground=COLORS["primary"]).pack(side="right", padx=8)
        ttk.Button(fl, text="↻", command=self.refresh).pack(side="right", padx=4)

        # Schnellfilter-Chips
        cf = ttk.Frame(f); cf.pack(fill="x", padx=10, pady=(0, 4))
        self._chip_vars: dict[str, tk.BooleanVar] = {}
        chip_defs = [
            ("star",  "mf.chip_star",  self._chip_starred),
            ("tree",  "mf.chip_tree",  self._chip_tree),
            ("cm200", "mf.chip_200",   self._chip_cm200),
            ("pat",   "mf.chip_pat",   self._chip_pat),
            ("mat",   "mf.chip_mat",   self._chip_mat),
            ("new",   "mf.chip_new",   self._chip_new),
        ]
        self._chip_btns: dict[str, tk.Button] = {}
        self._chip_t_keys: dict[str, str] = {}
        for key, t_key, cmd in chip_defs:
            var = tk.BooleanVar(value=False)
            self._chip_vars[key] = var
            btn = tk.Button(
                cf, text=t(t_key),
                font=("Segoe UI", 9), relief="flat", bd=1,
                bg=COLORS["light"], fg=COLORS["text"],
                activebackground=COLORS["primary"], activeforeground=COLORS["white"],
                cursor="hand2", padx=10, pady=3,
                command=lambda k=key, c=cmd: self._toggle_chip(k, c),
            )
            btn.pack(side="left", padx=3)
            self._chip_btns[key] = btn
            self._chip_t_keys[key] = t_key
            lw.append((btn, t_key))

        # Haupt-Pane
        pane = ttk.PanedWindow(f, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=4)

        left = ttk.Frame(pane); pane.add(left, weight=3)
        right = ttk.Frame(pane); pane.add(right, weight=2)

        self._build_match_tree(left)
        self._build_detail_panel(right)

    def _chip_starred(self):
        self._starred_var.set(self._chip_vars["star"].get())
        self.refresh()

    def _chip_tree(self):
        self._tree_var.set(self._chip_vars["tree"].get())
        self.refresh()

    def _chip_cm200(self):
        self._min_cm_var.set("200" if self._chip_vars["cm200"].get() else "0")
        self.refresh()

    def _chip_pat(self):
        if self._chip_vars["pat"].get():
            self._chip_vars["mat"].set(False)
            self._chip_btns["mat"].configure(bg=COLORS["light"], fg=COLORS["text"])
        self.refresh()

    def _chip_mat(self):
        if self._chip_vars["mat"].get():
            self._chip_vars["pat"].set(False)
            self._chip_btns["pat"].configure(bg=COLORS["light"], fg=COLORS["text"])
        self.refresh()

    def _chip_new(self):
        self.refresh()

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
        t  = self._state.t
        lw = self._state.lang_widgets
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
            self._tree.heading(col, text=t(key), command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))
            self._state.lang_headings.append((self._tree, col, key))

        self._tree.tag_configure("paternal",  background="#DDF0FF")
        self._tree.tag_configure("maternal",  background="#FFE0E0")
        self._tree.tag_configure("close",    background="#D6F5E3")
        self._tree.tag_configure("starred",  background="#FFF3CD")
        self._tree.tag_configure("no_tree",  foreground="#999999")
        self._tree.tag_configure("endogamy", background="#E0E0E0", foreground="#666666")
        self._tree.tag_configure("new_match", background="#FFF0D0", foreground="#8B4000")

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
        self._tree.bind("<Escape>", lambda _: self._search_var.set("") or self.refresh())
        self.bind_all("<F5>", lambda _: self.refresh())

        # Empty state overlay
        self._empty_frame = ttk.Frame(parent)
        _ev = tk.StringVar(value=t("mf.empty"))
        ttk.Label(self._empty_frame, textvariable=_ev,
                  font=("Segoe UI", 14), foreground="#888888").pack(pady=(60, 8))
        lw.append((_ev, "mf.empty"))
        _eh = tk.StringVar(value=t("mf.empty_hint"))
        ttk.Label(self._empty_frame, textvariable=_eh,
                  font=("Segoe UI", 10), foreground="#AAAAAA").pack()
        lw.append((_eh, "mf.empty_hint"))
        ttk.Button(self._empty_frame, text="→ Download",
                   command=self._on_goto_download).pack(pady=12)

    def _build_detail_panel(self, parent):
        t  = self._state.t
        lw = self._state.lang_widgets

        # Oberer Teil: Matchdetails
        self._detail_nb = ttk.Notebook(parent)
        self._detail_nb.pack(fill="both", expand=True)

        # Sub-Tab 1: Info + Notiz
        info_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(info_frame, text=t("md.tab_info"))
        self._state.lang_inner_nb_tabs.append((self._detail_nb, info_frame, "md.tab_info"))

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
            sv_lbl = tk.StringVar(value=t(key))
            ttk.Label(row, textvariable=sv_lbl, width=15, anchor="e",
                      foreground="#555555").pack(side="left")
            lw.append((sv_lbl, key))
            var = tk.StringVar(value="—")
            ttk.Label(row, textvariable=var, anchor="w").pack(side="left", padx=4)
            self._detail_fields[de_lbl] = var

        # Relationship probability bars
        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=4)
        _sv_rp = tk.StringVar(value=t("md.rel_prob"))
        ttk.Label(info_frame, textvariable=_sv_rp,
                  style="Bold.TLabel").pack(anchor="w", padx=8)
        lw.append((_sv_rp, "md.rel_prob"))
        self._rel_prob_canvas = tk.Canvas(info_frame, height=52, bg=COLORS["bg"],
                                          highlightthickness=0)
        self._rel_prob_canvas.pack(fill="x", padx=8, pady=(2, 4))

        # Research checklist
        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=2)
        _sv_cl = tk.StringVar(value=t("md.checklist"))
        ttk.Label(info_frame, textvariable=_sv_cl,
                  style="Bold.TLabel").pack(anchor="w", padx=8)
        lw.append((_sv_cl, "md.checklist"))
        self._checklist_vars: list[tk.BooleanVar] = []
        chk_frame = ttk.Frame(info_frame); chk_frame.pack(fill="x", padx=8)
        for i, key in enumerate(["md.chk0","md.chk1","md.chk2","md.chk3","md.chk4"]):
            var = tk.BooleanVar()
            self._checklist_vars.append(var)
            _sv_c = tk.StringVar(value=t(key))
            cb = ttk.Checkbutton(chk_frame, textvariable=_sv_c, variable=var,
                                  command=lambda i=i: self._save_checklist(i))
            cb.pack(anchor="w")
            lw.append((_sv_c, key))

        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=4)
        _sv = tk.StringVar(value=t("md.note"))
        ttk.Label(info_frame, textvariable=_sv, style="Bold.TLabel").pack(anchor="w", padx=8)
        lw.append((_sv, "md.note"))
        self._note_text = tk.Text(info_frame, height=4, font=("Segoe UI", 9),
                                   wrap="word", relief="solid", borderwidth=1)
        self._note_text.pack(fill="x", padx=8, pady=4)
        btn_row = ttk.Frame(info_frame); btn_row.pack(fill="x", padx=8, pady=2)
        _sv = tk.StringVar(value=t("md.save_note"))
        _b = ttk.Button(btn_row, textvariable=_sv, command=self._save_note)
        _b.pack(side="left", padx=(0,4))
        register_tooltip(_b, "tt.md_note", self._state)
        lw.append((_sv, "md.save_note"))
        _sv = tk.StringVar(value=t("md.open_anc"))
        _b = ttk.Button(btn_row, textvariable=_sv, command=self._open_in_ancestry)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.md_anc", self._state)
        lw.append((_sv, "md.open_anc"))
        _sv_fs = tk.StringVar(value=t("md.fs_link"))
        _b = ttk.Button(btn_row, textvariable=_sv_fs, command=self._open_familysearch)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.md_fs", self._state)
        lw.append((_sv_fs, "md.fs_link"))

        _ai_btn_var = tk.StringVar(value="🤖")
        self._match_ai_btn = ttk.Button(btn_row, textvariable=_ai_btn_var,
                                         command=self._copilot_explain_match, width=4)
        self._match_ai_btn.pack(side="left", padx=4)
        self._match_ai_btn.configure(state="disabled")
        self._match_ai_btn_var = _ai_btn_var

        _b = ttk.Button(btn_row, text="🧬", width=4,
                        command=self._open_chromosome_browser)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.md_chrom", self._state)
        _b = ttk.Button(btn_row, text="🗂", width=4, command=self._open_match_tasks)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.md_tasks", self._state)

        # Sub-Tab 2: Shared Matches
        sm_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(sm_frame, text=t("md.tab_shared"))
        self._state.lang_inner_nb_tabs.append((self._detail_nb, sm_frame, "md.tab_shared"))
        self._build_shared_panel(sm_frame)

        # Sub-Tab 3: GEDCOM-Bridge
        ged_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(ged_frame, text=t("md.tab_gedcom"))
        self._state.lang_inner_nb_tabs.append((self._detail_nb, ged_frame, "md.tab_gedcom"))
        self._build_gedcom_link_panel(ged_frame)

        # Sub-Tab 4: Gemeinsame Vorfahren (Ancestry match_ancestors)
        anc_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(anc_frame, text=t("md.tab_ancestors"))
        self._state.lang_inner_nb_tabs.append((self._detail_nb, anc_frame, "md.tab_ancestors"))
        self._build_ancestors_panel(anc_frame)

        # Sub-Tab 5: Kirchenbücher – Matricula-Treffer für Nachnamen aus der Ahnentafel
        kb_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(kb_frame, text=t("md.tab_kirchenbuch"))
        self._state.lang_inner_nb_tabs.append((self._detail_nb, kb_frame, "md.tab_kirchenbuch"))
        self._build_kirchenbuch_panel(kb_frame)

        # Sub-Tab 6: WikiTree-Direktsuche + gespeicherte Treffer
        wt_frame = ttk.Frame(self._detail_nb)
        self._detail_nb.add(wt_frame, text=t("md.tab_wikitree"))
        self._state.lang_inner_nb_tabs.append((self._detail_nb, wt_frame, "md.tab_wikitree"))
        self._build_wikitree_panel(wt_frame)

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
        t  = self._state.t
        lw = self._state.lang_widgets

        # Zeile 1: GEDCOM-Datei-Info + Wählen-Button
        hdr = ttk.Frame(parent); hdr.pack(fill="x", padx=6, pady=(4, 0))
        self._ged_file_var = tk.StringVar(value="—")
        ttk.Label(hdr, text="🌳", font=("Segoe UI", 10)).pack(side="left")
        ttk.Label(hdr, textvariable=self._ged_file_var,
                  foreground="#555555", font=("Segoe UI", 8)).pack(side="left", padx=4)
        _b = ttk.Button(hdr, text="📂", width=3, command=self._on_choose_gedcom)
        _b.pack(side="left")
        register_tooltip(_b, "tt.md_choose", self._state)
        _sv_orig = tk.StringVar(value=t("md.ged_origin"))
        _b = ttk.Button(hdr, textvariable=_sv_orig, command=self._on_origin_inference)
        _b.pack(side="right", padx=4)
        register_tooltip(_b, "tt.md_origin", self._state)
        lw.append((_sv_orig, "md.ged_origin"))
        _b = ttk.Button(hdr, text="🔗 WikiTree", command=self._on_wikitree_extend)
        _b.pack(side="right", padx=4)
        register_tooltip(_b, "tt.md_wikitree", self._state)
        _b = ttk.Button(hdr, text="🤖 ML-Herkunft", command=self._on_ml_origin)
        _b.pack(side="right", padx=4)
        register_tooltip(_b, "tt.md_ml", self._state)
        _b = register_lang(self._state, ttk.Button(hdr, text=self._state.t("mf.b_dups"), command=self._on_xref_review), "mf.b_dups")
        _b.pack(side="right", padx=4)
        register_tooltip(_b, "tt.md_dup", self._state)
        _sv_endo_btn = tk.StringVar(value=t("md.ged_endogamy"))
        _b = ttk.Button(hdr, textvariable=_sv_endo_btn, command=self._on_endogamy_transfer)
        _b.pack(side="right", padx=4)
        register_tooltip(_b, "tt.md_endo", self._state)
        lw.append((_sv_endo_btn, "md.ged_endogamy"))

        # Zeile 2: Status + Re-run + Bulk-Abgleich-Button
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=(2, 4))
        self._ged_link_status = tk.StringVar(value=t("md.ged_none"))
        ttk.Label(tb, textvariable=self._ged_link_status,
                  foreground=COLORS["primary"]).pack(side="left")
        _sv_all = tk.StringVar(value=t("md.ged_run_all"))
        _b = ttk.Button(tb, textvariable=_sv_all, command=self._on_gedcom_match_all)
        _b.pack(side="right")
        register_tooltip(_b, "tt.md_runall", self._state)
        lw.append((_sv_all, "md.ged_run_all"))
        _sv_rerun = tk.StringVar(value=t("md.ged_rerun"))
        self._ged_rerun_btn = ttk.Button(
            tb, textvariable=_sv_rerun,
            command=self._rerun_gedcom_for_selected, state="disabled")
        self._ged_rerun_btn.pack(side="right", padx=(0, 4))
        lw.append((_sv_rerun, "md.ged_rerun"))

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

    def load_gedcom_link_panel(self, match: "DnaMatch"):
        """Füllt den GEDCOM-Treffer-Tab für den ausgewählten Match."""
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        self._ged_rerun_btn.configure(state="normal")
        ged = self._get_gedcom()
        if not ged:
            self._ged_link_status.set(self._state.t("md.ged_none"))
            return

        test_guid = self._get_test_guid()
        if not test_guid:
            return

        self._ged_link_status.set(self._state.t("md.ged_searching"))

        self.after(0, lambda: self._on_gedcom_header_update(ged))

        def _worker():
            try:
                from ancestry.core import bridge
                bridge.ensure_tables(self._state.db)
                # GEDCOM-Personen importieren, falls leer
                if bridge.get_gedcom_person_count(self._state.db) == 0:
                    n = bridge.import_gedcom_persons(
                        self._state.db, ged["individuals"], ged.get("path", ""),
                        families=ged.get("families") or {})
                    log.info("bridge: %d Personen importiert", n)
                rows = bridge.run_match_for_match(self._state.db, test_guid, match.match_guid)
                self.after(0, lambda: self._fill_ged_link_tree(rows, match))
            except Exception as exc:
                log.warning("bridge: %s", exc)
                msg = str(exc).lower()
                if "no such table" in msg or "no table" in msg:
                    hint = "Bitte zuerst GEDCOM-Datei laden (Werkzeuge → GEDCOM-Import)"
                elif "no column" in msg or "no such column" in msg:
                    hint = "DB-Schema veraltet — bitte Anwendung neu starten"
                else:
                    hint = f"Fehler: {exc}"
                self.after(0, lambda h=hint: self._ged_link_status.set(h))

        import threading
        threading.Thread(target=_worker, daemon=True, name="bridge").start()

    def _fill_ged_link_tree(self, rows: list, match: "DnaMatch"):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != match.match_guid:
            return
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        if not rows:
            self._ged_link_status.set(self._state.t("md.ged_no_ped"))
            return
        hits = sum(1 for r in rows if r["icon"])
        self._ged_link_status.set(
            f"{hits} Treffer von {len(rows)} Vorfahren  ·  {match.display_name}")
        try:
            from ancestry.core.bridge import path_to_sosa
        except ImportError:
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

    def _rerun_gedcom_for_selected(self):
        """Re-runs GEDCOM matching for the currently selected match on demand."""
        if self._selected_match:
            self.load_gedcom_link_panel(self._selected_match)

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
        """Füllt den Gemeinsame-Vorfahren-Tab für den ausgewählten Match (im Hintergrund)."""
        self._anc_tree.delete(*self._anc_tree.get_children())
        def _worker():
            try:
                rows = self._state.db.get_ancestors_for_match(match.match_guid)
            except Exception as e:
                log.debug("get_ancestors_for_match %s: %s", match.match_guid[:8], e)
                rows = []
            self.after(0, lambda: self._fill_ancestors_panel(match, rows))
        threading.Thread(target=_worker, daemon=True).start()

    def _fill_ancestors_panel(self, match: "DnaMatch", rows):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != match.match_guid:
            return
        self._anc_tree.delete(*self._anc_tree.get_children())
        if not rows:
            self._anc_status_var.set(self._state.t("md.anc_none"))
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

    # ── Tabelle ──────────────────────────────────────────────────────────────

    def _refresh_match_table_inner(self, *_):
        # ── UI-Status auf dem Main-Thread lesen (Tk-Vars sind nicht thread-safe) ──
        try:
            min_cm = float(self._min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            min_cm = 0.0

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
            active_kit = self._get_test_guid()

        _cv = getattr(self, "_chip_vars", {})
        # Chip-Filter: pat/mat überschreiben den Dropdown wenn aktiv
        _pm = getattr(self, "_side_var", tk.StringVar()).get() or None
        if _cv.get("pat", tk.BooleanVar()).get():
            _pm = "paternal"
        elif _cv.get("mat", tk.BooleanVar()).get():
            _pm = "maternal"

        # Ein Eintrag mehr als das Limit holen, um zu erkennen, ob mehr
        # Treffer existieren als angezeigt werden (→ Hinweis im Zähler).
        query = dict(
            test_guid          = active_kit,
            all_sources        = all_sources_mode,
            search             = self._search_var.get().strip() or None,
            relationship       = self._rel_var.get() if hasattr(self,"_rel_var") else None,
            starred_only       = self._starred_var.get() if hasattr(self,"_starred_var") else False,
            has_tree_only      = self._tree_var.get() if hasattr(self,"_tree_var") else False,
            min_cm             = min_cm,
            hide_endogamy      = getattr(self, "_hide_endo_var", tk.BooleanVar()).get(),
            paternal_maternal  = _pm,
            new_only           = _cv.get("new", tk.BooleanVar()).get(),
            sort_col           = sort_col,
            sort_asc           = self._sort_asc,
            limit              = self._MAX_DISPLAY_ROWS + 1,
        )
        gedcom_loaded = bool(self._get_gedcom())
        tg = self._get_test_guid()

        # Nur das jüngste Refresh anwenden (Tipp-/Filter-Stürme erzeugen mehrere)
        gen = getattr(self, "_match_table_gen", 0) + 1
        self._match_table_gen = gen

        def _worker():
            bundle: dict = {}
            try:
                bundle["rels"] = self._state.db.get_distinct_relationships()
            except Exception as e:
                log.debug("get_distinct_relationships: %s", e)
                bundle["rels"] = []
            try:
                matches = self._state.db.get_matches(**query)
            except Exception as e:
                log.debug("get_matches: %s", e)
                self.after(0, lambda e=e: self._match_count_var.set(f"⚠ Fehler: {e}"))
                return
            capped = len(matches) > self._MAX_DISPLAY_ROWS
            if capped:
                matches = matches[:self._MAX_DISPLAY_ROWS]
            bundle["matches"] = matches
            bundle["capped"]  = capped

            # Overlap-Set: welche der angezeigten GUIDs kommen in anderen Kits vor?
            # Nur die sichtbare Seite prüfen (max 2001), nicht alle 300k.
            overlap_guids: set = set()
            if active_kit and matches:
                try:
                    all_kits = [k.guid for k in self._state.db.get_kits() if k.guid != active_kit]
                    page_guids = [m.match_guid for m in matches]
                    if all_kits and page_guids:
                        ph_kits  = ",".join("?" * len(all_kits))
                        ph_guids = ",".join("?" * len(page_guids))
                        with self._state.db._cursor() as _cur:
                            rows = _cur.execute(
                                f"SELECT DISTINCT match_guid FROM match_kit_membership "
                                f"WHERE test_guid IN ({ph_kits}) AND match_guid IN ({ph_guids})",
                                all_kits + page_guids,
                            ).fetchall()
                        overlap_guids = {r[0] for r in rows}
                except Exception as e:
                    log.debug("overlap_guids: %s", e)
            bundle["overlap_guids"] = overlap_guids

            # Diagnose-Zähler nur bei 0 Treffern
            diag = None
            if not matches:
                try:
                    with self._state.db._cursor() as _dc:
                        db_total = _dc.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
                        mkm_total = _dc.execute("SELECT COUNT(*) FROM match_kit_membership").fetchone()[0]
                    diag = (db_total, mkm_total)
                except Exception as e:
                    log.debug("diagnostic count: %s", e)
            bundle["diag"] = diag

            # Bridge-Treffer-Zähler (leer wenn kein GEDCOM / keine Tabelle)
            bridge_hits: dict = {}
            if gedcom_loaded and tg:
                try:
                    bridge_hits = self._state.db.get_bridge_hit_counts(tg)
                except Exception as e:
                    log.debug("bridge_hit_counts: %s", e)
            bundle["bridge_hits"] = bridge_hits

            self.after(0, lambda: self._fill_match_table(gen, bundle))

        threading.Thread(target=_worker, daemon=True, name="match-table").start()

    def _fill_match_table(self, gen, bundle):
        # Stale-Guard: nur das jüngste Refresh-Ergebnis darstellen
        if gen != getattr(self, "_match_table_gen", gen):
            return
        if hasattr(self, "_rel_combo"):
            self._rel_combo["values"] = ["(alle)"] + bundle.get("rels", [])

        self._matches  = bundle.get("matches", [])
        capped         = bundle.get("capped", False)
        overlap_guids  = bundle.get("overlap_guids", set())
        bridge_hits    = bundle.get("bridge_hits", {})

        n = len(self._matches)
        if n == 0:
            diag = bundle.get("diag")
            if diag and diag[0] > 0:
                db_total, mkm_total = diag
                self._match_count_var.set(
                    f"0 Match(es) — {db_total:,} in DB, {mkm_total:,} in kit-membership"
                    f"  →  oben Kit auswählen oder 'Alle Plattformen' wählen")
            elif diag:
                self._match_count_var.set("0 Match(es) — DB leer, bitte Matches herunterladen")
            else:
                self._match_count_var.set("0 Match(es)")
        elif capped:
            self._match_count_var.set(
                f"Top {self._MAX_DISPLAY_ROWS:,} (nach cM) angezeigt "
                f"— Suche/Filter zum Eingrenzen nutzen")
        else:
            self._match_count_var.set(f"{n:,} Match(es)")
        self._tree.delete(*self._tree.get_children())
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
            # Neu seit ≤ 7 Tagen
            fsa = getattr(m, "first_seen_at", "") or ""
            if fsa:
                from datetime import datetime, timezone, timedelta
                try:
                    _seen = datetime.fromisoformat(fsa.replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) - _seen <= timedelta(days=7):
                        tags.append("new_match")
                except ValueError:
                    pass

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
        # Auswahl + Scroll-Position wiederherstellen (nach Bearbeitung tief in
        # der Liste); wird vom Worker-Refresh asynchron befüllt.
        guid = getattr(self, "_pending_reselect", None)
        if guid and self._tree.exists(guid):
            self._tree.selection_set(guid)
            self._tree.see(guid)
        self._pending_reselect = None

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
            label=self._state.t("mf.b_open_anc"),
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
            self._state.db.set_endogamy_cluster(match.match_guid, name)
            match.endogamy_cluster = name
            if name and name not in known:
                known.append(name)
                self._save_ui_settings(endogamy_clusters=known)
            self._refresh_and_reselect(match.match_guid)
            dlg.destroy()

        bf = ttk.Frame(dlg); bf.pack(anchor="e", padx=14, pady=4)
        ttk.Button(bf, text=self._state.t("dlg.cancel"), command=dlg.destroy).pack(side="left", padx=4)
        ttk.Button(bf, text=self._state.t("dlg.save"), command=_save).pack(side="left")
        dlg.bind("<Return>", lambda _: _save())

    def _clear_endogamy_cluster(self, match):
        self._state.db.set_endogamy_cluster(match.match_guid, "")
        match.endogamy_cluster = ""
        self._refresh_and_reselect(match.match_guid)

    def _auto_flag_endogamy(self):
        """Markiert Endogamie-verdächtige Matches (viele kurze Segmente)
        automatisch als endogamy_cluster='(auto)'."""
        from tkinter import messagebox
        guid = self._get_test_guid()
        if not guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"),
                                   self._state.t("dlg.m_choose_kit"))
            return
        n = self._state.db.auto_flag_endogamy(guid)
        self.refresh()
        self._set_status(self._state.t("mf.endo_auto_done").format(n=n))
        messagebox.showinfo(self._state.t("mf.endo_auto"),
                            self._state.t("mf.endo_auto_done").format(n=n))

    def _refresh_and_reselect(self, guid: str):
        """Aktualisiert die Tabelle und stellt Auswahl + Scroll-Position wieder her,
        damit man nach einer Bearbeitung tief in der Liste nicht den Platz verliert.
        Die Tabelle wird asynchron befüllt — die Auswahl setzt _fill_match_table."""
        self._pending_reselect = guid
        self.refresh()

    def _set_custom_rel(self, match, rel: str):
        self._state.db.update_note(match.match_guid,
                                   match.note or "")
        with self._state.db._cursor() as cur:
            cur.execute("UPDATE matches SET custom_relationship=? WHERE match_guid=?",
                        (rel, match.match_guid))
        self._set_status(f"{match.display_name} → {rel}")
        self._refresh_and_reselect(match.match_guid)

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
            with self._state.db._cursor() as cur:
                cur.execute("UPDATE matches SET display_name=? WHERE match_guid=?",
                            (name.strip(), match.match_guid))
            self._set_status(f"Name gespeichert: {name.strip()}")
            self._refresh_and_reselect(match.match_guid)

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col in ("name","rel")
        # Update column header to show sort direction
        for c in ("name","guid","note","cm","seg","rel","tree","ca","starred"):
            base = self._state.t({
                "name":"m.name","guid":"m.guid","note":"m.note","cm":"m.cm",
                "seg":"m.seg","rel":"m.rel","tree":"m.tree","ca":"m.ca","starred":"m.starred",
            }[c])
            if c == self._sort_col:
                self._tree.heading(c, text=base + (" ▲" if self._sort_asc else " ▼"))
            else:
                self._tree.heading(c, text=base)
        self.refresh()

    # ── Detail-Panel ─────────────────────────────────────────────────────────

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
        if self._selected_match and self._note_text.edit_modified():
            self._save_note()
        self._selected_match = match
        if hasattr(self, "_match_ai_btn"):
            from ancestry.core.ai_copilot import is_available
            self._match_ai_btn.configure(
                state="normal" if is_available() else "disabled")

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
        test_guid_af = self._get_test_guid()
        self._detail_fields["Ahnentafel"].set("…")
        def _load_ped(guid=match.match_guid, tg=test_guid_af):
            try:
                summary = self._state.db.get_pedigree_summary_for_match(tg, guid)
                def _set_ped(s=summary, g=guid):
                    if self._selected_match and self._selected_match.match_guid == g:
                        self._detail_fields["Ahnentafel"].set(s if s else "—")
                self.after(0, _set_ped)
            except Exception as e:
                log.debug("_load_ped %s: %s", guid[:8], e)
                self.after(0, lambda g=guid: (
                    self._selected_match and self._selected_match.match_guid == g and
                    self._detail_fields["Ahnentafel"].set("—")))
        import threading as _thr
        _thr.Thread(target=_load_ped, daemon=True, name="ped-summary").start()

        # Herkunfts-Schätzung aus probable_origin-Spalte laden
        self._detail_fields["Herkunft"].set("…")
        def _load_origin(guid=match.match_guid):
            try:
                import json as _json
                with self._state.db._cursor() as _cur:
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
                def _set_orig(lb=label, g=guid):
                    if self._selected_match and self._selected_match.match_guid == g:
                        self._detail_fields["Herkunft"].set(lb)
                self.after(0, _set_orig)
            except Exception as e:
                log.debug("_load_origin %s: %s", guid[:8], e)
                self.after(0, lambda g=guid: (
                    self._selected_match and self._selected_match.match_guid == g and
                    self._detail_fields["Herkunft"].set("—")))
        _thr.Thread(target=_load_origin, daemon=True, name="origin-load").start()

        # ML-Herkunft (zweite Meinung) aus ml_origin-Spalte laden
        self._detail_fields["Herkunft (ML)"].set("…")
        def _load_ml_origin(guid=match.match_guid):
            try:
                import json as _json
                with self._state.db._cursor() as _cur:
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
                def _set_ml(lb=label, g=guid):
                    if self._selected_match and self._selected_match.match_guid == g:
                        self._detail_fields["Herkunft (ML)"].set(lb)
                self.after(0, _set_ml)
            except Exception as e:
                log.debug("_load_ml_origin %s: %s", guid[:8], e)
                self.after(0, lambda g=guid: (
                    self._selected_match and self._selected_match.match_guid == g and
                    self._detail_fields["Herkunft (ML)"].set("—")))
        _thr.Thread(target=_load_ml_origin, daemon=True, name="ml-origin-load").start()

        self._note_text.delete("1.0","end")
        self._note_text.insert("1.0", match.note or "")
        self._note_text.edit_modified(False)

        # MRCA-Schätzung im Status (einzeilig, nicht invasiv)
        cm = match.shared_cm or 0
        mrca_hint = ""
        for lo, hi, label, gen in self._cm_ranges:
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
        self.load_gedcom_link_panel(match)
        self._load_ancestors_panel(match)
        self._load_kirchenbuch_panel(match)
        self._load_wikitree_panel(match)

    def _copilot_explain_match(self):
        """Erklärt den ausgewählten Match via Claude-Copilot."""
        from tkinter import scrolledtext
        from ancestry.core.ai_copilot import (
            availability_hint, explain_async, is_available, match_prompt,
        )
        match = self._selected_match
        if match is None:
            return
        win = tk.Toplevel(self)
        win.title(f"🤖 KI-Erklärung: {match.display_name}")
        win.geometry("580x380")
        txt = scrolledtext.ScrolledText(win, wrap="word", font=("Segoe UI", 9),
                                        state="disabled", bg="#fafafa")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        hint = availability_hint()
        if hint:
            txt.configure(state="normal")
            txt.insert("end", hint)
            txt.configure(state="disabled")
            return
        # Sammle Kontext
        try:
            shared = self._state.db.get_shared_matches(
                self._get_test_guid(), match.match_guid)
            shared_count = len(shared) if shared else 0
        except Exception:
            shared_count = 0
        try:
            from ancestry.core.matricula_bridge import _pedigree_surnames
            surnames = _pedigree_surnames(
                self._state.db, self._get_test_guid(), match.match_guid, 2)
        except Exception:
            surnames = []
        prompt = match_prompt(
            match_name=match.display_name or "",
            shared_cm=float(match.shared_cm or 0),
            predicted_rel=match.predicted_relationship or "",
            shared_count=shared_count,
            pedigree_names=surnames[:8],
        )
        txt.configure(state="normal")
        txt.insert("end", "Claude analysiert …\n\n")
        txt.configure(state="disabled")
        def _chunk(t):
            win.after(0, lambda c=t: _append(c))
        def _done(_):
            pass
        def _append(t):
            txt.configure(state="normal")
            txt.insert("end", t)
            txt.see("end")
            txt.configure(state="disabled")
        explain_async(prompt, on_chunk=_chunk, on_done=_done, max_tokens=350)

    def _load_shared_panel(self, match: DnaMatch):
        """Lädt Shared Matches für den ausgewählten primären Match (im Hintergrund)."""
        test_guid = self._get_test_guid()
        if not test_guid:
            return
        self._sm_count_var.set("…")
        def _worker():
            shared = self._state.db.get_shared_matches(test_guid, match.match_guid)
            self.after(0, lambda: self._fill_shared_panel(match, shared, test_guid))
        threading.Thread(target=_worker, daemon=True).start()

    def _fill_shared_panel(self, match: DnaMatch, shared, test_guid: str):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != match.match_guid:
            return
        self._sm_tree.delete(*self._sm_tree.get_children())
        if not shared:
            fetched = self._state.db.is_shared_fetched(test_guid, match.match_guid)
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

    def _open_chromosome_browser(self):
        """Öffnet den Chromosomen-Browser (B4) für den ausgewählten Match."""
        if not self._selected_match:
            return
        test_guid = self._get_test_guid()
        if not test_guid:
            return
        try:
            from ancestry.gui.analysis.chromosome_browser import show_chromosome_browser
            show_chromosome_browser(self, self._state, test_guid,
                                    self._selected_match.match_guid,
                                    self._selected_match.display_name or "")
        except Exception as e:
            log.debug("chromosome browser: %s", e)

    def _open_match_tasks(self):
        """Öffnet den Aufgaben-Dialog (B1), eingeschränkt auf den Match."""
        if not self._selected_match:
            return
        try:
            from ancestry.gui.analysis.research_tasks_view import show_research_tasks
            show_research_tasks(self, self._state, entity_type="match",
                                entity_key=self._selected_match.match_guid,
                                entity_label=self._selected_match.display_name or "")
        except Exception as e:
            log.debug("match tasks: %s", e)

    def _open_in_ancestry(self):
        """Öffnet den aktuellen Match in Ancestry im Browser."""
        if not self._selected_match:
            return
        test_guid  = self._get_test_guid()
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
        self._state.db.update_note(self._selected_match.match_guid, note)
        self._selected_match.note = note
        self._set_status(f"Notiz gespeichert: {self._selected_match.display_name}")

    def _save_checklist(self, changed_index: int):
        """Save research checklist state as bitmask to DB."""
        if not self._selected_match:
            return
        flags = sum(1 << i for i, v in enumerate(self._checklist_vars) if v.get())
        try:
            self._state.db.update_research_flags(self._selected_match.match_guid, flags)
        except Exception as e:
            log.debug("Checklist speichern: %s", e)

    def _open_familysearch(self):
        """Search FamilySearch for the selected match's name."""
        if not self._selected_match:
            return
        name = self._selected_match.display_name or ""
        if not name or name in ("Anonym", "?"):
            messagebox.showinfo(self._state.t("mf.no_name_t"), self._state.t("mf.m_no_name"))
            return
        url = f"https://www.familysearch.org/search/record/results?q.surname={quote(name.split()[-1])}"
        webbrowser.open(url)

    @staticmethod
    def _rel_cm_summary(cm: float) -> str:
        """Shared-cM-Project-Verteilung als Einzeiler, z.B.
        '70% 2. Cousin · 19% Halb-1C · 11% …'."""
        try:
            from ancestry.core.shared_cm import summary_line
            return summary_line(cm, top=3) if cm and cm > 0 else "—"
        except ImportError:
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
            from ancestry.core.shared_cm import relationship_probabilities
            probs = relationship_probabilities(cm, top=3)
            scored = [(p["probability"], p["labels"][0]) for p in probs]
        except ImportError:
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

    # ── Kirchenbücher ─────────────────────────────────────────────────────────

    def _build_kirchenbuch_panel(self, parent):
        """Sub-Tab 5: Kirchenbuch-Treffer für Nachnamen aus der Match-Ahnentafel."""
        t  = self._state.t
        lw = self._state.lang_widgets

        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        _sv = tk.StringVar(value=t("md.kb_min_gen"))
        ttk.Label(tb, textvariable=_sv).pack(side="left")
        lw.append((_sv, "md.kb_min_gen"))
        self._kb_gen_var = tk.StringVar(value="2")
        ttk.Entry(tb, textvariable=self._kb_gen_var, width=3).pack(side="left", padx=4)
        _sv = tk.StringVar(value=t("md.kb_reload"))
        ttk.Button(tb, textvariable=_sv,
                   command=lambda: self._load_kirchenbuch_panel(self._selected_match)).pack(
                   side="left", padx=4)
        lw.append((_sv, "md.kb_reload"))
        self._kb_surnames_var = tk.StringVar(value="")
        ttk.Label(tb, textvariable=self._kb_surnames_var,
                  foreground="#666666", wraplength=300).pack(side="left", padx=(12, 0))

        cols = ("book_id", "year", "entry_type", "person", "person2",
                "father", "mother", "village", "match")
        self._kb_tree = ttk.Treeview(parent, columns=cols, show="headings",
                                      selectmode="browse")
        for col, lbl, w, anchor in [
            ("book_id",    "Kirchenbuch",    160, "w"),
            ("year",       "Jahr",            50, "center"),
            ("entry_type", "Art",             60, "w"),
            ("person",     "Person",         170, "w"),
            ("person2",    "Person 2",       130, "w"),
            ("father",     "Vater",          130, "w"),
            ("mother",     "Mutter",         130, "w"),
            ("village",    "Ort",             90, "w"),
            ("match",      "Treffer-Name",    90, "w"),
        ]:
            self._kb_tree.heading(col, text=lbl)
            self._kb_tree.column(col, width=w, anchor=anchor,
                                  stretch=(col in ("person","book_id")))
        self._kb_tree.tag_configure("exact",   foreground=COLORS.get("primary","#1a73e8"))
        self._kb_tree.tag_configure("phonetic",foreground=COLORS.get("text","#333"))
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._kb_tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=self._kb_tree.xview)
        self._kb_tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self._kb_tree.pack(side="left", fill="both", expand=True, padx=(6, 0))
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")

    def _load_kirchenbuch_panel(self, match: "Optional[DnaMatch]"):
        """Füllt den Kirchenbuch-Tab für den ausgewählten Match (im Hintergrund).

        Die NER-Suche macht zwei nicht-indizierbare LIKE-Scans über matrikula_ner;
        deshalb läuft sie im Worker-Thread statt auf dem GUI-Thread."""
        self._kb_tree.delete(*self._kb_tree.get_children())
        self._kb_surnames_var.set("")
        if match is None:
            return
        try:
            min_gen = int(self._kb_gen_var.get() or 2)
        except ValueError:
            min_gen = 2
        test_guid = self._get_test_guid()
        guid = match.match_guid
        self._kb_surnames_var.set("…")

        def _worker():
            bundle: dict = {}
            try:
                with self._state.db._cursor() as cur:
                    ner_count = cur.execute("SELECT COUNT(*) FROM matrikula_ner").fetchone()[0]
                    mat_count = cur.execute(
                        "SELECT COUNT(*) FROM source_matrikula_entries").fetchone()[0]
                if mat_count > 0 and ner_count == 0:
                    bundle["status"] = ("⚠  Kirchenbücher vorhanden, aber NER noch nicht "
                                        "extrahiert → Matricula-Tab → „NER extrahieren“")
                    self.after(0, lambda: self._fill_kirchenbuch_panel(guid, bundle))
                    return
            except Exception:
                pass
            try:
                from ancestry.core.matricula_bridge import (
                    _pedigree_surnames, find_matricula_for_match)
                surnames = _pedigree_surnames(self._state.db, test_guid, guid, min_gen)
                bundle["surnames"] = surnames
                if surnames:
                    bundle["hits"] = find_matricula_for_match(
                        self._state.db, test_guid, guid, min_generation=min_gen)
            except Exception as e:
                bundle["error"] = str(e)
            self.after(0, lambda: self._fill_kirchenbuch_panel(guid, bundle))

        threading.Thread(target=_worker, daemon=True, name="kb-panel").start()

    def _fill_kirchenbuch_panel(self, guid, bundle):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != guid:
            return
        t = self._state.t
        self._kb_tree.delete(*self._kb_tree.get_children())
        if "status" in bundle:
            self._kb_surnames_var.set(bundle["status"])
            return
        if "error" in bundle:
            self._kb_surnames_var.set(f"Fehler: {bundle['error']}")
            return
        surnames = bundle.get("surnames") or []
        if not surnames:
            self._kb_surnames_var.set(t("md.kb_no_ped"))
            return
        self._kb_surnames_var.set(
            f"{t('md.kb_surnames')} {', '.join(surnames[:8])}"
            + (" …" if len(surnames) > 8 else ""))
        hits = bundle.get("hits") or []
        if not hits:
            self._kb_surnames_var.set(
                f"{t('md.kb_no_hits')}  ({t('md.kb_surnames')} {', '.join(surnames[:4])})")
            return
        for h in hits:
            # Buchpfad kürzen: "deutschland/osnabrueck/ostercappeln/b1" → "ostercappeln/b1"
            book = h.get("book_id") or ""
            parts = book.split("/")
            book_short = "/".join(parts[-2:]) if len(parts) >= 2 else book
            tag = "exact" if h.get("exact_match") else "phonetic"
            self._kb_tree.insert("", "end", tags=(tag,), values=(
                book_short,
                h.get("event_year") or "—",
                h.get("entry_type") or "—",
                h.get("person_name") or "—",
                h.get("person2_name") or "",
                h.get("father_name") or "",
                h.get("mother_name") or "",
                h.get("village") or "",
                h.get("name_raw") or "",
            ))

    # ── WikiTree Sub-Tab ──────────────────────────────────────────────────────

    def _build_wikitree_panel(self, parent):
        """Sub-Tab 6: WikiTree-Direktsuche und gespeicherte Treffer."""
        t  = self._state.t
        lw = self._state.lang_widgets

        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._wt_status_var = tk.StringVar(value=t("md.wt_no_match"))
        ttk.Label(tb, textvariable=self._wt_status_var,
                  foreground=COLORS["primary"]).pack(side="left")
        _sv_btn = tk.StringVar(value=t("md.wt_search"))
        self._wt_search_btn = ttk.Button(tb, textvariable=_sv_btn,
                                          command=self._wt_open_search, state="disabled")
        self._wt_search_btn.pack(side="right", padx=4)
        lw.append((_sv_btn, "md.wt_search"))

        cols = ("confidence", "wt_id", "name", "birth", "death", "location", "link")
        self._wt_tree = ttk.Treeview(parent, columns=cols, show="headings",
                                      selectmode="browse")
        for col, lbl, w, anchor in [
            ("confidence", "Konfidenz",  80, "center"),
            ("wt_id",      "WikiTree-ID",100, "w"),
            ("name",       "Name",       200, "w"),
            ("birth",      "Geb.",        55, "center"),
            ("death",      "Gest.",       55, "center"),
            ("location",   "Ort",        150, "w"),
            ("link",       "Profil",      60, "center"),
        ]:
            self._wt_tree.heading(col, text=lbl)
            self._wt_tree.column(col, width=w, anchor=anchor,
                                  stretch=(col == "name"))
        self._wt_tree.tag_configure("HOCH",   foreground=COLORS.get("success", "#198754"))
        self._wt_tree.tag_configure("MITTEL", foreground=COLORS.get("primary", "#1a73e8"))
        self._wt_tree.tag_configure("NIEDRIG",foreground="#888888")
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._wt_tree.yview)
        self._wt_tree.configure(yscrollcommand=sy.set)
        self._wt_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=2)
        sy.pack(side="right", fill="y", pady=2)
        self._wt_tree.bind("<Double-1>", self._wt_open_profile)

    def _load_wikitree_panel(self, match: "Optional[DnaMatch]"):
        """Füllt den WikiTree-Tab für den ausgewählten Match."""
        if not hasattr(self, "_wt_tree"):
            return
        self._wt_tree.delete(*self._wt_tree.get_children())
        t = self._state.t
        if match is None:
            self._wt_status_var.set(t("md.wt_no_match"))
            self._wt_search_btn.configure(state="disabled")
            return
        self._wt_search_btn.configure(state="normal")
        # Versuche gespeicherte WikiTree-Zeilen aus dem Runner-State
        rows: list = []
        try:
            import tasks._runner as _runner
            all_rows = _runner._state.get("wikitree_rows") or []
            guid = match.match_guid
            rows = [r for r in all_rows
                    if isinstance(r, (list, tuple)) and len(r) >= 2 and r[1] == guid]
        except Exception:
            rows = []
        if not rows:
            self._wt_status_var.set(t("md.wt_no_data"))
            return
        self._wt_status_var.set(f"{len(rows)} WikiTree-Treffer  ·  {match.display_name}")
        for r in rows:
            # WIKITREE_HEADERS = [Konfidenz, Match-GUID, WikiTree-ID, Name, Geb., Gest.,
            #                      Geburtsort, Sterbeort, URL, …]
            conf = r[0] if len(r) > 0 else ""
            wt_id = r[2] if len(r) > 2 else ""
            name = r[3] if len(r) > 3 else ""
            birth = r[4] if len(r) > 4 else ""
            death = r[5] if len(r) > 5 else ""
            loc   = r[6] if len(r) > 6 else ""
            url   = r[8] if len(r) > 8 else ""
            tag = conf if conf in ("HOCH", "MITTEL", "NIEDRIG") else ""
            self._wt_tree.insert("", "end", tags=(tag,) if tag else (), values=(
                conf, wt_id, name, birth, death, loc,
                "→ öffnen" if url else "—",
            ), iid=None)
            if url:
                # URL in row-Daten speichern für Doppelklick
                self._wt_tree.set(self._wt_tree.get_children()[-1], "link", "→ öffnen")
                self._wt_tree.item(self._wt_tree.get_children()[-1], tags=(tag or "", url))

    def _wt_open_search(self):
        """Öffnet die WikiTree-Suche für den ausgewählten Match im Browser."""
        match = self._selected_match
        if not match:
            return
        name = match.display_name or ""
        parts = name.split()
        if len(parts) >= 2:
            first = parts[0]
            last  = parts[-1]
        elif parts:
            first, last = "", parts[0]
        else:
            first, last = "", ""
        q = f"{first}+{last}".strip("+")
        url = f"https://www.wikitree.com/index.php?title=Special:SearchPerson&q={quote(q)}"
        webbrowser.open(url)

    def _wt_open_profile(self, _event=None):
        """Doppelklick auf einen WikiTree-Treffer → Profil im Browser öffnen."""
        sel = self._wt_tree.selection()
        if not sel:
            return
        tags = self._wt_tree.item(sel[0], "tags")
        # Der zweite Tag ist die URL (wenn gesetzt)
        url = tags[1] if len(tags) >= 2 and tags[1].startswith("http") else None
        if url:
            webbrowser.open(url)
        else:
            wt_id = self._wt_tree.set(sel[0], "wt_id")
            if wt_id:
                webbrowser.open(f"https://www.wikitree.com/wiki/{quote(wt_id)}")
