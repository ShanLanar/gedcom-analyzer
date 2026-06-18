"""Popup: Pedigree-Lücken-Übersicht über alle Matches mit Ahnentafel.

Zeigt je Match, bis zu welcher Generation die Ahnentafel lückenlos ist und wo
die erste Lücke sitzt – als Hinweis, wo sich weitere Forschung/Download lohnt.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ancestry.gui.widgets.theme import COLORS


def show_pedigree_gaps(parent, db, test_guid, set_status=None):
    """parent: tk-Widget · db: Database · test_guid: aktuelles Kit."""
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit auswählen.")
        return

    from ancestry.core.pedigree_gaps import summarize_match_gaps

    try:
        raw = db.get_pedigree_completeness_per_match(test_guid)
    except Exception as e:  # noqa: BLE001
        messagebox.showerror("Fehler", str(e))
        return

    rows = summarize_match_gaps(raw)
    if not rows:
        messagebox.showinfo(
            "Keine Daten",
            "Keine Ahnentafel-Daten vorhanden.\n→ Erst 'Ahnentafeln laden' ausführen.")
        return

    win = tk.Toplevel(parent)
    win.title("Pedigree-Lücken – Ahnentafel-Vollständigkeit pro Match")
    win.geometry("780x560")

    ttk.Label(win, text="Pedigree-Lücken-Analyse",
              font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
    ttk.Label(win,
              text=("'Voll bis Gen' = letzte lückenlose Generation · "
                    "'Lücke ab Gen' = erste unvollständige Generation. "
                    "Tief & vollständig zuerst."),
              foreground="#444466", wraplength=740, justify="left").pack(
        anchor="w", padx=14, pady=(2, 8))

    cols = ("name", "cm", "maxgen", "fullto", "gap", "pct")
    heads = {"name": "Match", "cm": "cM", "maxgen": "Max Gen",
             "fullto": "Voll bis Gen", "gap": "Lücke ab Gen", "pct": "Vollständig %"}
    widths = {"name": 240, "cm": 70, "maxgen": 80, "fullto": 100, "gap": 100, "pct": 110}

    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=12, pady=4)
    tv = ttk.Treeview(frame, columns=cols, show="headings")
    for c in cols:
        tv.heading(c, text=heads[c])
        tv.column(c, width=widths[c],
                  anchor="w" if c == "name" else "center")
    sy = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sy.set)
    tv.pack(side="left", fill="both", expand=True)
    sy.pack(side="left", fill="y")

    for r in rows:
        gap = r["first_gap_gen"]
        tv.insert("", "end", values=(
            r["display_name"] or r["match_guid"][:12],
            f"{r['shared_cm']:.0f}" if r["shared_cm"] else "",
            r["max_gen"],
            r["complete_through"] if r["complete_through"] >= 2 else "—",
            gap if gap is not None else "—",
            f"{r['pct']:.0f}%",
        ))

    deepest = max(r["complete_through"] for r in rows)
    ttk.Label(win,
              text=f"{len(rows)} Matches mit Ahnentafel · tiefste lückenlose "
                   f"Generation: {deepest}",
              foreground=COLORS.get("primary", "#225588")).pack(
        anchor="w", padx=14, pady=(2, 10))

    if set_status:
        set_status(f"Pedigree-Lücken: {len(rows)} Matches analysiert.")
