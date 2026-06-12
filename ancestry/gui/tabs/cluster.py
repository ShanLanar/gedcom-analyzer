"""Cluster-Tab: Leeds-Clustering-Ansicht für das Ancestry-DNA-Tool."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ancestry.core.cluster import build_clusters, suggest_grandparent_lines
from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import COLORS

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
        _sv = tk.StringVar(value=t("cl.calc_btn"))
        ttk.Button(cf, textvariable=_sv, command=self.refresh).pack(side="left", padx=14)
        lw.append((_sv, "cl.calc_btn"))
        self._count_var = tk.StringVar(value="")
        ttk.Label(cf, textvariable=self._count_var,
                  foreground=COLORS["primary"]).pack(side="left")
        _sv = tk.StringVar(value=t("cl.tree_btn"))
        ttk.Button(cf, textvariable=_sv, command=self._show_tree).pack(side="left", padx=14)
        lw.append((_sv, "cl.tree_btn"))
        _sv = tk.StringVar(value=t("cl.timeline"))
        ttk.Button(cf, textvariable=_sv, command=self._on_show_timeline).pack(side="left", padx=4)
        lw.append((_sv, "cl.timeline"))
        _sv = tk.StringVar(value=t("cl.assign_side"))
        ttk.Button(cf, textvariable=_sv, command=self._on_assign_side).pack(side="left", padx=4)
        lw.append((_sv, "cl.assign_side"))

        # Cluster-Beschreibung
        df = ttk.Frame(self)
        df.pack(fill="x", padx=14, pady=(0, 4))
        _sv = tk.StringVar(value=t("cl.desc"))
        ttk.Label(df, textvariable=_sv).pack(side="left")
        lw.append((_sv, "cl.desc"))
        self._desc_var = tk.StringVar()
        ttk.Entry(df, textvariable=self._desc_var, width=50).pack(side="left", padx=6)
        ttk.Button(df, text="💾", command=self._save_desc, width=3).pack(side="left")

        self._text_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._text_var,
                  foreground="#444466", font=("Segoe UI", 9),
                  wraplength=900, justify="left").pack(anchor="w", padx=14, pady=(0, 6))

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

    # ── Daten laden ──────────────────────────────────────────────────────────

    def refresh(self):
        test_guid = self._get_test_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return
        try:
            min_prim   = float(self._min_cm_var.get()    or 20)
            max_prim   = float(self._max_cm_var.get()    or 400)
            min_shared = float(self._shared_cm_var.get() or 20)
        except ValueError:
            min_prim, max_prim, min_shared = 20.0, 400.0, 20.0

        shared_data = self._state.db.get_all_shared_for_cluster(
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
        self._count_var.set(f"{len(self._clusters)} Cluster")
        self._text_var.set(suggest_grandparent_lines(self._clusters))

        # Seiten-Map
        all_guids = [m["guid"] for mlist in self._clusters.values() for m in mlist]
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
                from ancestry.core.treematch import cluster_confidence
                med_cm = sum(m["cm"] for m in members) / n if n else 0.0
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

    # ── Selektion ────────────────────────────────────────────────────────────

    def _on_select(self, _=None):
        sel = self._cluster_list.selection()
        if not sel:
            return
        cid     = int(sel[0])
        members = self._clusters.get(cid, [])
        descs   = self._load_settings().get("cluster_descs", {})
        self._desc_var.set(descs.get(str(cid), ""))
        color = self._cluster_side_colors.get(
            cid, COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])])

        test_guid = self._get_current_guid()
        guid_match: dict = {}
        if test_guid:
            try:
                guid_match = {m.match_guid: m
                              for m in self._state.db.get_matches(test_guid)}
            except Exception as e:
                log.debug("cluster guid_match: %s", e)

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
        if test_guid and len(members) >= 2:
            guids     = [m["guid"] for m in members]
            guid_name = {m["guid"]: m["name"] for m in members}
            pairs     = self._state.db.get_pairwise_shared(test_guid, guids)
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
        cid  = int(sel[0])
        desc = self._desc_var.get().strip()
        descs = self._load_settings().get("cluster_descs", {})
        descs[str(cid)] = desc
        self._save_settings(cluster_descs=descs)
        self._set_status(f"Cluster #{cid} Beschreibung gespeichert.")

    # ── Stammbaum-Analyse-Popup ───────────────────────────────────────────────

    def _show_tree(self):
        sel = self._cluster_list.selection()
        if not sel:
            messagebox.showinfo("Kein Cluster",
                                "Bitte zuerst einen Cluster in der Liste auswählen.")
            return
        cid     = int(sel[0])
        members = self._clusters.get(cid, [])
        if not members:
            return
        test_guid = self._get_current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return

        guids   = {m["guid"] for m in members}
        id_name = {m["guid"]: m["name"] for m in members}
        all_peds = self._state.db.get_all_pedigrees(test_guid)

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
        ttk.Label(win,
                  text=("Grün = alle Mitglieder teilen diese Person  |  "
                        "Gelb = ≥3 Mitglieder  |  Orange = 2 Mitglieder  |  "
                        "Weiß = nur 1 Mitglied  →  mehr = wahrscheinlicherer Vorfahre"),
                  foreground="#333333").pack(anchor="w", padx=12, pady=(2, 6))

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

    # ── Public accessor für _show_cluster_tree (Rückwärtskompatibilität) ──────

    def get_clusters(self) -> dict:
        return self._clusters

    def get_cluster_list_selection(self):
        return self._cluster_list.selection()
