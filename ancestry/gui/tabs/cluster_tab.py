"""ClusterTabMixin – Tab 4: Cluster-Analyse für AncestryDnaApp."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ancestry.core.cluster import build_clusters, suggest_grandparent_lines
from ancestry.gui._colors import COLORS


class ClusterTabMixin:
    """Mixin mit allen Cluster-Tab-Methoden für AncestryDnaApp."""

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
        ttk.Label(cf, textvariable=_sv_pt).pack(side="left", padx=(4, 4))
        self._lang_widgets.append((_sv_pt, "cl.prim_to"))
        self._cluster_max_cm_var = tk.StringVar(value="400")
        ttk.Entry(cf, textvariable=self._cluster_max_cm_var, width=6).pack(side="left")
        _sv_sm = tk.StringVar(value=self._t("cl.shared_min"))
        ttk.Label(cf, textvariable=_sv_sm).pack(side="left", padx=(14, 4))
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
        df = ttk.Frame(f); df.pack(fill="x", padx=14, pady=(0, 4))
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
                  wraplength=900, justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        # Pane: Cluster-Liste | Mitglieder | Gegenseitige cM
        pane = ttk.PanedWindow(f, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=14, pady=4)

        # Linke Seite: Cluster-Liste
        left = ttk.LabelFrame(pane, text=self._t("cl.frm_left"), padding=6)
        self._lang_widgets.append((left, "cl.frm_left"))
        pane.add(left, weight=1)
        self._cluster_list = ttk.Treeview(left, columns=("cid", "count", "max_cm", "top", "quality"),
                                           show="headings", selectmode="browse")
        for col, (key, w) in {
            "cid"     : ("cl.cid",     50),
            "count"   : ("cl.count",   55),
            "max_cm"  : ("cl.maxcm",   65),
            "top"     : ("cl.top",    175),
            "quality" : ("cl.quality", 80),
        }.items():
            self._cluster_list.heading(col, text=self._t(key))
            self._cluster_list.column(col, width=w, stretch=(col == "top"),
                                       anchor="center" if col in ("quality", "count") else "w")
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
        self._member_tree = ttk.Treeview(mid, columns=("name", "cm", "rel", "baum", "src"),
                                          show="headings", selectmode="browse")
        for col, (key, w, anchor) in {
            "name": ("mb.name", 180, "w"),
            "cm"  : ("mb.cm",    60, "e"),
            "rel" : ("mb.rel",  140, "w"),
            "baum": ("mb.baum",  55, "center"),
            "src" : ("mb.src",   65, "center"),
        }.items():
            self._member_tree.heading(col, text=self._t(key))
            self._member_tree.column(col, width=w, anchor=anchor, stretch=(col == "name"))
            self._lang_headings.append((self._member_tree, col, key))
        sy2 = ttk.Scrollbar(mid, orient="vertical", command=self._member_tree.yview)
        self._member_tree.configure(yscrollcommand=sy2.set)
        self._member_tree.pack(side="left", fill="both", expand=True)
        sy2.pack(side="right", fill="y")

        # Rechte Seite: Paarweise cM zwischen Mitgliedern
        right = ttk.LabelFrame(pane, text=self._t("cl.frm_right"), padding=6)
        self._lang_widgets.append((right, "cl.frm_right"))
        pane.add(right, weight=2)
        self._pairwise_tree = ttk.Treeview(right, columns=("a", "b", "cm"),
                                            show="headings", selectmode="none")
        for col, (key, w, anch) in {
            "a":  ("pw.a",  190, "w"),
            "b":  ("pw.b",  190, "w"),
            "cm": ("pw.cm",  90, "e"),
        }.items():
            self._pairwise_tree.heading(col, text=self._t(key))
            self._pairwise_tree.column(col, width=w, anchor=anch, stretch=(col in ("a", "b")))
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
                from ancestry.core.treematch import cluster_confidence
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
        if not sel:
            return
        cid = int(sel[0])
        members = self._clusters.get(cid, [])
        descs = self._load_ui_settings().get("cluster_descs", {})
        if hasattr(self, "_cluster_desc_var"):
            self._cluster_desc_var.set(descs.get(str(cid), ""))
        color = getattr(self, "_cluster_side_colors", {}).get(
            cid, COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])])

        test_guid = self._current_guid()
        guid_match: dict = {}
        if test_guid:
            try:
                guid_match = {m.match_guid: m for m in self._db.get_matches(test_guid)}
            except Exception:
                pass

        m_guids = [m["guid"] for m in members]
        src_map: dict = {}
        if m_guids:
            try:
                with self._db._cursor() as _cur:
                    src_rows = _cur.execute(
                        "SELECT match_guid, source FROM matches WHERE match_guid IN ({})".format(
                            ",".join("?" * len(m_guids))),
                        m_guids,
                    ).fetchall()
                src_map = {r["match_guid"]: (r["source"] or "ancestry") for r in src_rows}
            except Exception:
                pass

        _SRC_BADGE = {"myheritage": "🔵MH", "gedmatch": "⚪GED"}
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
            src_badge = _SRC_BADGE.get(src_map.get(m["guid"], "ancestry"), "🧬ANC")
            self._member_tree.insert("", "end", tags=("row",),
                                      values=(m["name"], f"{m['cm']:.1f}",
                                              m.get("rel", ""), baum_val, src_badge))

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
        """Stammbaum-Analyse: Ahnentafeln aller Cluster-Mitglieder zusammenführen."""
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

        # Vorfahren zusammenführen (Schlüssel: Nachname+Geburtsjahrzehnt)
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
                        "guid_gens":   {},
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

        # Fenster
        color = COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])]
        win = tk.Toplevel(self)
        win.title(f"Cluster #{cid} – Stammbaum-Analyse ({len(members)} Matches)")
        win.geometry("1150x680")
        win.configure(bg=color)

        n_total = len(members)
        ttk.Label(win,
                  text=f"Cluster #{cid} · {n_total} Mitglieder · "
                       f"{len(persons)} einzigartige Vorfahren in den Ahnentafeln",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 0))
        ttk.Label(win,
                  text="Grün = alle Mitglieder teilen diese Person  |  "
                       "Gelb = ≥3 Mitglieder  |  Orange = 2 Mitglieder  |  "
                       "Weiß = nur 1 Mitglied  →  mehr Übereinstimmungen = wahrscheinlicherer Vorfahre",
                  foreground="#333333").pack(anchor="w", padx=12, pady=(2, 6))

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
            tv.heading(c, text=self._t(key), command=lambda c=c: _sort(c))
            tv.column(c, width=w,
                      anchor=("center" if c in ("count", "birth", "gen") else "w"),
                      stretch=(c == "matches"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tv.tag_configure("all",   background="#D6F5E3")
        tv.tag_configure("many",  background="#FFD6D6")
        tv.tag_configure("two",   background="#FFF3CD")
        tv.tag_configure("one",   background="#FFFFFF")

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
                       else "two"  if n >= 2
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
                  foreground="#444444").pack(anchor="w", padx=12, pady=(0, 6))

        # Mitglieder-Übersicht
        mf = ttk.LabelFrame(win, text="Cluster-Mitglieder", padding=4)
        mf.pack(fill="x", padx=12, pady=(0, 8))
        for i, m in enumerate(sorted(members, key=lambda x: -(x["cm"] or 0))):
            ttk.Label(mf, text=f"#{i+1} {m['name']}  ({m['cm']:.0f} cM)",
                      foreground=COLORS["primary"]).grid(
                row=0, column=i, padx=10, pady=2, sticky="w")
