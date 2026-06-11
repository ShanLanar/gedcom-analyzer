"""AnalysisTabMixin – Analyse-Popups für AncestryDnaApp."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Optional
from urllib.parse import quote

from ancestry.core.scraper import Scraper


class AnalysisTabMixin:
    """Mixin mit allen Analyse-Popup-Methoden für AncestryDnaApp."""

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
            import math
            import random
            random.seed(42)
            W = canvas.winfo_width() or 980
            H = canvas.winfo_height() or 650
            all_members: dict = {}  # guid → {name, cm, cluster_idx, cluster_color}
            cl_colors = self._active_colors()["cluster"]
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
                          foreground=self._active_colors()["primary"],
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
                      style="Bold.TLabel", foreground=self._active_colors()["primary"]
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

