"""
ancestry/gui/analysis/mrca.py – MRCA-, Netzwerkgraph- und Endogamie-Analyse-Popups.

Jede Funktion erhält die App-Instanz als erstes Argument (``app``) und
verhält sich identisch zum ursprünglichen self-Aufruf in app.py.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from ancestry.gui.widgets.theme import COLORS


# cM → Beziehungs-Wahrscheinlichkeitstabelle (Shared cM Project 2020 + DNAPainter)
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


# ── MRCA-Wahrscheinlichkeit ────────────────────────────────────────────────────

def show_mrca_analysis(app, match=None):
    """Popup: cM-basierte MRCA-Wahrscheinlichkeiten für den gewählten Match."""
    if match is None:
        match = getattr(app, "_selected_match", None)
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

    win = tk.Toplevel(app)
    win.title(f"MRCA-Analyse: {match.display_name}")
    win.geometry("580x460")
    win.resizable(True, True)

    ttk.Label(win, text=f"{match.display_name}",
              style="Bold.TLabel", font=("Segoe UI",12,"bold")).pack(anchor="w", padx=14, pady=(12,2))
    ttk.Label(win, text=f"{cm:.1f} cM  ·  {segs} Segmente  ·  längstes {longest:.1f} cM"
                        f"  ·  {match.predicted_relationship or '?'}",
              foreground="#555").pack(anchor="w", padx=14, pady=(0,6))

    # cM-Nachschlagetabelle
    rel_frame = ttk.LabelFrame(win, text="Beziehungsbereich (Shared cM Project 2020)", padding=8)
    rel_frame.pack(fill="x", padx=14, pady=4)

    match_row = None
    for lo, hi, label, gen in _CM_RANGES:
        if lo <= cm <= hi:
            match_row = (lo, hi, label, gen)
            break
    # Bester Treffer auch außerhalb der exakten Bereiche
    if match_row is None:
        dists = [(abs(cm - (lo+hi)/2), lo, hi, label, gen) for lo,hi,label,gen in _CM_RANGES]
        dists.sort()
        _, lo, hi, label, gen = dists[0]
        match_row = (lo, hi, label, gen)

    cols2 = ttk.Treeview(rel_frame, columns=("rel","range","gen","match"),
                         show="headings", height=len(_CM_RANGES))
    cols2.heading("rel",   text="Beziehung")
    cols2.heading("range", text="cM-Bereich")
    cols2.heading("gen",   text="Gen.")
    cols2.heading("match", text="Trifft zu")
    cols2.column("rel",   width=260, anchor="w")
    cols2.column("range", width=110, anchor="center")
    cols2.column("gen",   width=45,  anchor="center")
    cols2.column("match", width=70,  anchor="center")
    cols2.tag_configure("hit", background="#d8f0d8", font=("Segoe UI",9,"bold"))
    for lo, hi, label, gen in _CM_RANGES:
        tag = ("hit",) if (lo, hi) == (match_row[0], match_row[1]) else ()
        cols2.insert("", "end", tags=tag, values=(
            label, f"{lo}–{hi}", gen,
            "✓" if (lo, hi) == (match_row[0], match_row[1]) else ""))
    cols2.pack(fill="x")

    # MRCA-Generationsschätzung
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


# ── Cluster-Netzwerkgraph (Canvas) ────────────────────────────────────────────

def show_network_graph(app):
    """Popup: Canvas-basierter Netzwerkgraph der Cluster-Mitglieder mit shared-cM als Kantengewicht."""
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return

    win = tk.Toplevel(app)
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

        clusters = app._db.get_shared_clusters(test_guid, lo, hi)
        if not clusters:
            canvas.create_text(500, 300, text="Keine Cluster – erst Shared Matches laden (Schritt B).",
                               fill="white", font=("Segoe UI",12))
            return

        # Alle Mitglieder (dedupliziert) mit Cluster-Zuweisung sammeln
        import math
        import random
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

        # Einfaches kraft-basiertes Layout (Federmodell, 30 Iterationen)
        guids = list(all_members.keys())
        n = len(guids)
        angle_step = 2 * math.pi / max(n, 1)
        r0 = min(W, H) * 0.38
        # Startpositionen: Kreis
        pos = {g: (W/2 + r0 * math.cos(i * angle_step),
                   H/2 + r0 * math.sin(i * angle_step))
               for i, g in enumerate(guids)}

        # Kanten aus shared_matches sammeln
        edges: list = []
        for ci, cl in enumerate(clusters[:20]):
            cl_guids = [g for g, _, _ in cl["members"]]
            pairs = app._db.get_pairwise_shared(test_guid, cl_guids)
            for (ga, gb, cm_ab) in pairs:
                if cm_ab and cm_ab >= min_edge and ga in pos and gb in pos:
                    edges.append((ga, gb, cm_ab))

        # Federlayout-Iterationen
        k = math.sqrt(W * H / max(n, 1)) * 0.6
        for _ in range(40):
            disp = {g: [0.0, 0.0] for g in guids}
            # Abstoßung
            for i in range(n):
                for j in range(i+1, n):
                    gi, gj = guids[i], guids[j]
                    dx = pos[gi][0] - pos[gj][0]
                    dy = pos[gi][1] - pos[gj][1]
                    d  = max(math.hypot(dx, dy), 1)
                    f  = k*k / d
                    disp[gi][0] += dx/d*f; disp[gi][1] += dy/d*f
                    disp[gj][0] -= dx/d*f; disp[gj][1] -= dy/d*f
            # Anziehung entlang Kanten
            for ga, gb, cm_ab in edges:
                if ga not in pos or gb not in pos: continue
                dx = pos[ga][0] - pos[gb][0]
                dy = pos[ga][1] - pos[gb][1]
                d  = max(math.hypot(dx, dy), 1)
                f  = d*d / k
                disp[ga][0] -= dx/d*f; disp[ga][1] -= dy/d*f
                disp[gb][0] += dx/d*f; disp[gb][1] += dy/d*f
            # Verschiebung anwenden (gedämpft)
            temp = 20
            for g in guids:
                dm = math.hypot(*disp[g])
                if dm > 0:
                    scale = min(dm, temp) / dm
                    x = max(40, min(W-40, pos[g][0] + disp[g][0]*scale))
                    y = max(40, min(H-40, pos[g][1] + disp[g][1]*scale))
                    pos[g] = (x, y)

        # Kanten zeichnen
        max_cm_edge = max((cm for _, _, cm in edges), default=1)
        for ga, gb, cm_ab in edges:
            if ga not in pos or gb not in pos: continue
            w = max(1, int(cm_ab / max_cm_edge * 5))
            try:
                canvas.create_line(pos[ga][0], pos[ga][1], pos[gb][0], pos[gb][1],
                                   width=w, fill="#4488cc", smooth=True)
            except Exception:
                pass

        # Knoten zeichnen
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


# ── Endogamie-Score-Analyse ───────────────────────────────────────────────────

def show_endogamy_analysis(app):
    """Popup: Matches mit erhöhtem Endogamie-Score."""
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return

    win = tk.Toplevel(app)
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
            rows = app._db.get_endogamy_candidates(test_guid, thr)
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
