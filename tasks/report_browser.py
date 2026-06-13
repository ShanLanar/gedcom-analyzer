"""In-App-Report-Browser für die GEDCOM-Analyzer-Reports.

Macht die ~84 sonst nur im Excel-Export sichtbaren Reports IM Programm sichtbar:
links eine nach Themen-Kategorie (A–I) gruppierte Liste, rechts die Tabelle des
gewählten Reports. Liest die zuletzt berechneten Reports aus tasks._runner._state
(get_report_sheets / get_report_category).

Aufruf:  open_report_browser(parent_or_none)
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def _load():
    """(grouped, total): {Kategorie: [(name, headers, rows)]}, Anzahl."""
    from tasks import _runner
    # Reports aus dem aktuellen _state neu bauen (ohne Excel zu schreiben);
    # schlägt fehl, solange keine Analysen gelaufen sind → leerer Browser.
    try:
        _runner.collect_report_sheets()
    except Exception:
        pass
    sheets = _runner.get_report_sheets() or []
    grouped: dict[str, list] = {}
    for item in sheets:
        try:
            name, headers, rows = item[0], item[1], item[2]
        except Exception:
            continue
        cat = _runner.get_report_category(name)
        grouped.setdefault(cat, []).append((name, headers, rows))
    return grouped, len(sheets)


class ReportBrowser(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.pack(fill="both", expand=True)
        self._by_iid: dict[str, tuple] = {}
        self._build()
        self.reload()

    def _build(self):
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(bar, text="📊 Report-Browser",
                  font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Button(bar, text="↻ Aktualisieren", command=self.reload).pack(side="right")
        self._info = ttk.Label(bar, text="", foreground="#888")
        self._info.pack(side="right", padx=8)

        pan = ttk.Panedwindow(self, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(pan); pan.add(left, weight=1)
        self._tree = ttk.Treeview(left, show="tree", selectmode="browse")
        sy = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sy.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        right = ttk.Frame(pan); pan.add(right, weight=3)
        self._title = ttk.Label(right, text="Report wählen …",
                                 font=("Segoe UI", 11, "bold"))
        self._title.pack(anchor="w", padx=4, pady=(0, 4))
        tw = ttk.Frame(right); tw.pack(fill="both", expand=True)
        self._table = ttk.Treeview(tw, show="headings", selectmode="browse")
        txs = ttk.Scrollbar(tw, orient="horizontal", command=self._table.xview)
        tys = ttk.Scrollbar(tw, orient="vertical", command=self._table.yview)
        self._table.configure(xscrollcommand=txs.set, yscrollcommand=tys.set)
        tys.pack(side="right", fill="y")
        txs.pack(side="bottom", fill="x")
        self._table.pack(side="left", fill="both", expand=True)

    def reload(self):
        self._tree.delete(*self._tree.get_children())
        self._by_iid.clear()
        grouped, total = _load()
        if not total:
            self._info.configure(
                text="Keine Reports — erst Analysen/Export im Stammbaum-Tab laufen lassen.")
            return
        self._info.configure(text=f"{total} Reports")
        for cat in sorted(grouped):
            entries = grouped[cat]
            cnode = self._tree.insert("", "end", text=f"{cat}  ({len(entries)})",
                                      open=True)
            for name, headers, rows in entries:
                n = len(rows) if hasattr(rows, "__len__") else 0
                iid = self._tree.insert(cnode, "end", text=f"{name}  · {n}")
                self._by_iid[iid] = (name, headers, rows)

    def _on_select(self, _=None):
        sel = self._tree.selection()
        if not sel or sel[0] not in self._by_iid:
            return
        name, headers, rows = self._by_iid[sel[0]]
        self._title.configure(text=name)
        self._table.delete(*self._table.get_children())
        cols = [str(h) for h in (headers or [])]
        self._table["columns"] = cols
        for c in cols:
            self._table.heading(c, text=c)
            self._table.column(c, width=max(60, min(260, len(c) * 9)),
                               stretch=False, anchor="w")
        for row in (rows or [])[:5000]:
            vals = [("" if v is None else str(v)) for v in row]
            self._table.insert("", "end", values=vals)


def open_report_browser(parent=None):
    """Öffnet den Report-Browser als eigenes Fenster (oder eingebettet, wenn ein
    Parent übergeben wird)."""
    if parent is None:
        win = tk.Toplevel()
    else:
        win = tk.Toplevel(parent)
    win.title("Report-Browser — Genealogie-Reports")
    win.geometry("1100x720")
    try:
        ReportBrowser(win)
    except Exception as exc:  # defensiv: Fenster bleibt offen mit Hinweis
        ttk.Label(win, text=f"Report-Browser-Fehler:\n{exc}",
                  foreground="#b00020", padding=20, justify="left").pack()
    return win
