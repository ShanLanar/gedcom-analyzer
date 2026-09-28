"""Analyse-Dialoge-Mixin für AncestryDnaApp (Namenskarte, Ahnentafel,
Shared-Cluster (Leeds-Methode), Segment-Triangulation, kombinierter
Cluster-Stammbaum).

Dritter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Diese Methoden lesen nur gemeinsamen App-Zustand
(self._state, self._db, self._selected_match, self._gedcom, self._scraper,
self._client) und rufen andere App-Methoden auf (self._t, self._set_status,
self._current_guid, self._ensure_gedcom_loaded, self._on_progress) — sie
erzeugen selbst KEIN Zustandsattribut, das andere Teile der App brauchen.
Viele delegieren nur an bereits ausgelagerte Dialog-Module unter
ancestry/gui/analysis/*.

Erwartet von der Host-Klasse (AncestryDnaApp): self._state, self._db,
self._selected_match, self._current_guid(), self._t(), self._set_status(),
self._ensure_gedcom_loaded(), self._on_progress, self._client, self._scraper,
self._gedcom.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ancestry.core.scraper import Scraper

log = logging.getLogger(__name__)


class AnalysisDialogsMixin:
    """Namenskarte/Nachname/Ort/MRCA/Netzwerkgraph/Ahnentafel/Shared-Cluster
    (Leeds)/Segment-Triangulation/kombinierter Cluster-Stammbaum."""

    def _open_namenskarte(self, surname: str):
        from ancestry.gui.analysis.names import open_namenskarte
        open_namenskarte(self, surname)

    def _show_surname_analysis(self):
        from ancestry.gui.analysis.names import show_surname_analysis
        show_surname_analysis(self)

    def _show_place_analysis(self):
        from ancestry.gui.analysis.names import show_place_analysis
        show_place_analysis(self)

    def _show_mrca_analysis(self, match=None):
        from ancestry.gui.analysis.mrca import show_mrca_analysis
        show_mrca_analysis(self, match)

    def _show_network_graph(self):
        from ancestry.gui.analysis.mrca import show_network_graph
        show_network_graph(self)

    def _show_ancestor_groups(self):
        from ancestry.gui.analysis.pedigree import show_ancestor_groups
        show_ancestor_groups(self)

    def _export_ancestor_groups(self):
        guid = self._current_guid()
        if not guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        groups = self._db.get_ancestor_groups(guid, min_matches=2)
        if not groups:
            messagebox.showinfo(self._t("dlg.no_data"), self._t("dlg.m_no_shared_anc"))
            return
        path = filedialog.asksaveasfilename(
            title=self._t("dlg.t_save_anc_groups"), defaultextension=".csv",
            filetypes=[("CSV","*.csv")])
        if not path:
            return
        import csv
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, quoting=csv.QUOTE_ALL)
                w.writerow(["Gemeinsamer Vorfahr","*Jahr","Anzahl Matches","Match","cM","Pfad"])
                for g in groups:
                    for guid_m, name, pth, cm in sorted(g["matches"], key=lambda x:-(x[3] or 0)):
                        w.writerow([g["ancestor_name"], g["birth_year"], g["count"],
                                    name or guid_m, f"{cm:.0f}" if cm else "", pth or ""])
            messagebox.showinfo(self._t("dlg.export"), f"{len(groups)} Vorfahren-Gruppen gespeichert.")
            self._set_status(f"Vorfahren-Gruppen exportiert: {len(groups)}")
        except Exception as e:
            log.debug("export_ancestor_groups: %s", e)
            self._set_status(f"⚠ Vorfahren-Gruppen-Export: {e}", "warn")

    def _show_match_pedigree(self):
        if not self._selected_match:
            messagebox.showinfo(self._t("dlg.no_match"), self._t("dlg.m_choose_match"))
            return
        guid = self._selected_match.match_guid
        test_guid = self._current_guid()
        rows = self._db.get_pedigree_for_match(test_guid, guid)
        if not rows:
            messagebox.showinfo(self._t("dlg.no_pedigree"),
                self._t("dlg.m_no_pedigree"))
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
            ttk.Label(win, text=self._t("dlg.l_no_common_anc"),
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
        """Leeds-Cluster aus den Shared Matches (Connected Components).

        Rein cM-/ICW-basiert (kein Segment-Abgleich) — NICHT zu verwechseln
        mit echter Segment-Triangulation (self._show_triangulation), die
        überlappende Chromosom-Segmente prüft."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return

        win = tk.Toplevel(self)
        win.title("Shared-Cluster – Leeds-Gruppen (ICW, kein Segment-Abgleich)")
        win.geometry("820x600")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text=self._t("dlg.l_cm_window"), style="Bold.TLabel").pack(side="left")
        lo_var = tk.StringVar(value="20"); hi_var = tk.StringVar(value="400")
        ttk.Entry(top, textvariable=lo_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="bis").pack(side="left")
        ttk.Entry(top, textvariable=hi_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="cM   (sehr enge/weite Matches verbinden alles)").pack(side="left")

        ttk.Label(win,
            text="ℹ Leeds-Methode: gruppiert Matches rein über gegenseitige Shared-Match-"
                 "Treffer (cM), OHNE DNA-Segmente zu vergleichen. Für echte Segment-"
                 "Triangulation → Menü Analyse → Segment-Triangulation.",
            foreground="#555", wraplength=780, justify="left",
            font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 2))

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
            from ancestry.core.treematch import cluster_confidence
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
                messagebox.showinfo(self._t("dlg.no_cluster"), self._t("dlg.m_choose_cluster"))
                return
            c = store.get(sel[0])
            if not c:
                return
            guids = [g for g, _n, _cm in c["members"]]

            def _after_load(ged):
                import threading

                from ancestry.core.treematch import Person
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
                messagebox.showinfo(self._t("dlg.no_cluster"), self._t("dlg.m_choose_cluster"))
                return
            c = store.get(sel[0])
            if not c:
                return
            guids = [g for g, _n, _cm in c["members"]]
            if not messagebox.askyesno(
                    self._t("dlg.deepen_cluster"),
                    f"Für {len(guids)} Cluster-Matches tiefere Ahnentafeln "
                    f"(bis 8 Generationen) laden?\n\n"
                    "Nötig für entfernte Cousins (gemeinsamer Vorfahr >5 Gen.).\n"
                    "Dauert etwas (mehrere Calls pro Match)."):
                return
            if not self._client:
                messagebox.showwarning(self._t("dlg.not_logged"), self._t("dlg.m_login_first"))
                return
            self._scraper = Scraper(self._client, self._db,
                                    on_progress=self._on_progress,
                                    on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                    on_done=lambda r: self.after(0, lambda: messagebox.showinfo(
                                        self._t("dlg.deep_pedigrees"), r.message + "\n\nJetzt erneut "
                                        "'Cluster-Linie suchen'.")))
            self._scraper.start_deepen_pedigrees(test_guid, guids)

        ttk.Button(top, text=self._t("dlg.b_deepen_cluster"),
                   command=deepen_cluster).pack(side="left", padx=4)

        def combined_tree():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo(self._t("dlg.no_cluster"), self._t("dlg.m_choose_cluster"))
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
                messagebox.showinfo(self._t("dlg.no_cluster"), self._t("dlg.m_choose_cluster"))
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
        from ancestry.gui.analysis.triangulation_view import show_triangulation
        show_triangulation(self)

    def _build_cluster_tree(self, test_guid, cluster):
        """Verschmilzt die Ahnentafeln aller Cluster-Mitglieder zu einem
        kombinierten Cluster-Stammbaum und zeigt Konvergenz + Andockpunkt."""
        import threading

        from ancestry.core.treematch import Person, merge_person_list, render_kinship
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
                            from ancestry.core.treematch import mrca_on_direct_line
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
        from ancestry.gui.analysis.cluster_views import show_cluster_tree_win
        show_cluster_tree_win(self, cluster, rows, n_with_ped, has_ged, name_by_member)

    def _show_cluster_relationships(self, test_guid, cluster):
        from ancestry.gui.analysis.cluster_views import show_cluster_relationships
        show_cluster_relationships(self, test_guid, cluster)

    def _show_cluster_dock(self, cluster, hits, n_with_ped):
        from ancestry.gui.analysis.cluster_views import show_cluster_dock
        show_cluster_dock(self, cluster, hits, n_with_ped)
