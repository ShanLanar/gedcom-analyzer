"""
ancestry/gui/analysis/pedigree.py – Ahnentafel- und Vorfahren-Analyse-Popups.

Jede Funktion erhält die App-Instanz als erstes Argument (``app``) und
verhält sich identisch zum ursprünglichen self-Aufruf in app.py.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from ancestry.gui.analysis.names import open_namenskarte


# ── Gemeinsame Vorfahren-Gruppen ───────────────────────────────────────────────

def show_ancestor_groups(app):
    """Popup: Vorfahren, die von mehreren Matches geteilt werden."""
    guid = app._current_guid()
    if not guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return
    groups = app._db.get_ancestor_groups(guid, min_matches=2)
    if not groups:
        messagebox.showinfo("Keine Daten",
            "Noch keine geteilten Vorfahren gefunden.\n"
            "Erst 'Vorfahren & Orte laden' ausführen.")
        return

    win = tk.Toplevel(app)
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

    # Zuordnung iid → Gruppe (lokal, kein app-Attribut nötig)
    anc_groups = {}
    for g in groups:
        iid = tv.insert("", "end", values=(g["ancestor_name"], g["birth_year"], g["count"]))
        anc_groups[iid] = g

    ttk.Label(bot, text="Matches dieses Vorfahren:",
              style="Bold.TLabel").pack(anchor="w", pady=(4,2))
    detail = tk.Text(bot, height=8, wrap="word", font=("Segoe UI", 9))
    detail.pack(fill="both", expand=True)

    def on_sel(_):
        sel = tv.selection()
        if not sel: return
        g = anc_groups.get(sel[0])
        detail.delete("1.0","end")
        if not g: return
        detail.insert("end", f"{g['ancestor_name']}  (*{g['birth_year'] or '?'})  "
                             f"– {g['count']} Matches:\n\n")
        for guid_m, name, path, cm in sorted(g["matches"], key=lambda x:-(x[3] or 0)):
            detail.insert("end", f"  • {name or guid_m[:8]}   "
                                 f"{cm:.0f} cM   Pfad: {path or '?'}\n")
    tv.bind("<<TreeviewSelect>>", on_sel)


# ── Pedigree-Überlagerung ──────────────────────────────────────────────────────

def show_pedigree_overlay(app):
    """Popup: Vorfahren, die in mehreren Match-Ahnentafeln vorkommen (gruppierbar)."""
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return

    win = tk.Toplevel(app)
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

    # Toolbar mit Namenskarte-Button (aktiv im Nachname-Modus)
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
            open_namenskarte(app, g["label"])
        else:
            # Nachnamen-Token aus dem Personennamen extrahieren
            parts = g["label"].split()
            if parts:
                open_namenskarte(app, parts[-1])

    ttk.Button(tb, text="🗺 Namenskarte.com",
               command=_namenskarte_from_overlay).pack(side="left", padx=4)

    def reload(*_):
        try:
            mm = max(2, int(minm_var.get() or 2))
        except ValueError:
            mm = 2
        groups = app._db.get_pedigree_groups(test_guid, min_matches=mm,
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


# ── Ahnentafel-Lücken-Analyse ──────────────────────────────────────────────────

def show_pedigree_gaps(app):
    """Popup: Zeigt, welche Generationen in Match-Ahnentafeln noch fehlen."""
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return

    win = tk.Toplevel(app)
    win.title("Ahnentafel-Lücken-Analyse")
    win.geometry("900x600")

    ttk.Label(win, text="Matches mit unvollständigen Ahnentafeln (nach Generation):",
              style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

    cols = ("name","cm","gen2","gen3","gen4","gen5","gen6")
    tv = ttk.Treeview(win, columns=cols, show="headings")
    for col, (lbl, w) in {
        "name": ("Match",     200),
        "cm":   ("cM",         65),
        "gen2": ("Gen 2",      60),
        "gen3": ("Gen 3",      60),
        "gen4": ("Gen 4",      60),
        "gen5": ("Gen 5",      60),
        "gen6": ("Gen 6+",     60),
    }.items():
        tv.heading(col, text=lbl)
        tv.column(col, width=w, anchor=("e" if col=="cm" else "center" if col!="name" else "w"))

    tv.tag_configure("gap3", background="#FFF3CD")
    tv.tag_configure("gap2", background="#FFD6D6")

    sy = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sy.set)
    tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=4)
    sy.pack(side="right", fill="y", pady=4)

    try:
        data = app._db.get_pedigree_completeness_per_match(test_guid)
    except Exception as e:
        messagebox.showerror("Fehler", str(e))
        return

    max_gen = {2: 4, 3: 8, 4: 16, 5: 32, 6: 64}
    for entry in data[:200]:
        gens = entry.get("generations", {})
        def fmt(g):
            got = gens.get(g, 0)
            exp = max_gen.get(g, 0)
            return f"{got}/{exp}" if exp else f"{got}"
        g3 = gens.get(3, 0); g4 = gens.get(4, 0)
        tags = ("gap2",) if g3 < 4 else (("gap3",) if g4 < 8 else ())
        tv.insert("", "end", tags=tags, values=(
            entry.get("display_name","?")[:30],
            f"{entry.get('shared_cm',0):.0f}",
            fmt(2), fmt(3), fmt(4), fmt(5), fmt(6),
        ))
    if not data:
        tv.insert("", "end", values=("—",) * 7)
