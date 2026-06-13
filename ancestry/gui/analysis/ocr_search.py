"""Kirchenbuch-Suche: Volltextsuche über die OCR-Rohtexte (ancestry.tools.ocr_index).

Tippe einen Namen/Ort → Treffer mit Pfarrei/Buch/Seite + Snippet. Phonetik-Modus
(Kölner Phonetik) findet auch Lese-/Schreibvarianten. Doppelklick öffnet die
zugehörige .txt bzw. Person/Seite. Alles lokal & token-frei.
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk


class OcrSearch(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self._rows: dict[str, dict] = {}
        self.pack(fill="both", expand=True)
        self._build()
        self._refresh_status()

    def _build(self):
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(bar, text="🔎 Kirchenbuch-Suche",
                  font=("Segoe UI", 12, "bold")).pack(side="left")
        self._q = tk.StringVar()
        e = ttk.Entry(bar, textvariable=self._q, width=30)
        e.pack(side="left", padx=8)
        e.bind("<Return>", lambda _: self.search())
        self._phon = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="phonetisch", variable=self._phon).pack(side="left")
        ttk.Button(bar, text="Suchen", command=self.search).pack(side="left", padx=6)
        ttk.Button(bar, text="📑 Index neu bauen", command=self.rebuild).pack(side="left")
        self._status = ttk.Label(bar, text="", foreground="#666")
        self._status.pack(side="right")

        cols = ("kind", "head", "snip")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("kind", "Typ", 120), ("head", "Pfarrei / Buch / Seite", 240),
                        ("snip", "Fundstelle", 520)):
            self._tree.heading(c, text=t)
            self._tree.column(c, width=w, anchor="w", stretch=(c == "snip"))
        sy = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sy.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sy.pack(side="left", fill="y", pady=8)
        self._tree.bind("<Double-1>", self._open)
        e.focus_set()

    def _refresh_status(self):
        from ancestry.tools.ocr_index import INDEX_PATH
        if os.path.exists(INDEX_PATH):
            self._status.configure(text="Index bereit")
        else:
            self._status.configure(text="Kein Index — erst 'Index neu bauen' klicken.")

    def search(self):
        q = self._q.get().strip()
        if not q:
            return
        self._tree.delete(*self._tree.get_children())
        self._rows.clear()
        self._status.configure(text="suche …")

        def _bg():
            try:
                from ancestry.tools.ocr_index import search
                hits = search(q, phonetic=self._phon.get())
            except Exception as exc:
                self.after(0, lambda e=exc: self._status.configure(text=f"⚠ {e}"))
                return
            self.after(0, lambda: self._fill(hits))
        threading.Thread(target=_bg, daemon=True, name="ocr-search").start()

    def _fill(self, hits):
        for h in hits:
            iid = self._tree.insert("", "end", values=(h["kind"], h["head"], h["snip"]))
            self._rows[iid] = h
        self._status.configure(text=f"{len(hits)} Treffer")

    def _open(self, _=None):
        sel = self._tree.selection()
        if not sel or sel[0] not in self._rows:
            return
        path = self._rows[sel[0]].get("path", "")
        if path and os.path.exists(path):
            try:
                os.startfile(path)            # type: ignore[attr-defined]
            except Exception:
                import webbrowser
                webbrowser.open(f"file://{path}")

    def rebuild(self):
        self._status.configure(text="Index wird gebaut …")

        def _bg():
            try:
                from ancestry.tools.ocr_index import build_index
                info = build_index()
                msg = (f"Index: {info['ocr']} OCR-Seiten, {info['entries']} Belege, "
                       f"{info['persons']} Personen")
            except Exception as exc:
                msg = f"⚠ {exc}"
            self.after(0, lambda: self._status.configure(text=msg))
        threading.Thread(target=_bg, daemon=True, name="ocr-build").start()


def open_ocr_search(parent=None):
    win = tk.Toplevel(parent)
    win.title("Kirchenbuch-Suche (OCR-Volltext)")
    win.geometry("1040x640")
    try:
        OcrSearch(win)
    except Exception as exc:
        ttk.Label(win, text=f"Suche-Fehler:\n{exc}", foreground="#b00020",
                  padding=20, justify="left").pack()
    return win
