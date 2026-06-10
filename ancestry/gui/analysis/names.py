"""
ancestry/gui/analysis/names.py – Nachname- und Geburtsort-Analyse-Popups.

Jede Funktion erhält die App-Instanz als erstes Argument (``app``) und
verhält sich identisch zum ursprünglichen self-Aufruf in app.py.
"""

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from urllib.parse import quote


# ── Namenskarte.com-Helfer ─────────────────────────────────────────────────────

def open_namenskarte(app, surname: str):
    """Öffnet namenskarte.com für den übergebenen Nachnamen im Standardbrowser."""
    url = f"https://www.namenskarte.com/nachname/{quote(surname)}"
    webbrowser.open(url)


# ── Nachname-Analyse ───────────────────────────────────────────────────────────

def show_surname_analysis(app):
    """Popup: häufigste Nachnamen in Match-Ahnentafeln."""
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return

    win = tk.Toplevel(app)
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
            open_namenskarte(app, s)
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
        groups = app._db.get_pedigree_groups(test_guid, min_matches=mm, mode="surname")
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


# ── Geburtsort-Analyse ─────────────────────────────────────────────────────────

def show_place_analysis(app):
    """Popup: häufigste Geburts­orte in Match-Ahnentafeln."""
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return

    win = tk.Toplevel(app)
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
        groups = app._db.get_pedigree_groups(test_guid, min_matches=mm, mode="place")
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
