"""Ortskonkordanz-Editor – zeigt alle Webtrees-Rohorte mit automatischer
Normalisierung und erlaubt manuelle Überschreibungen (→ place_concordance.json).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox


def _collect_raw_places(db_paths: list[Path]) -> list[tuple[str, int]]:
    """Sammelt alle distinkten Rohorte aus wt_persons (birth/death + facts)."""
    from collections import Counter
    cnt: Counter = Counter()
    for db_path in db_paths:
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            for row in conn.execute(
                    "SELECT birth_place, death_place, facts_json FROM wt_persons"):
                for pl in (row["birth_place"], row["death_place"]):
                    pl = (pl or "").strip()
                    if pl:
                        cnt[pl] += 1
                facts_raw = row["facts_json"] or "[]"
                try:
                    facts = json.loads(facts_raw)
                except (ValueError, TypeError):
                    facts = []
                for f in facts:
                    pl = (f.get("place") or "").strip()
                    if pl:
                        cnt[pl] += 1
            conn.close()
        except Exception:
            pass
    return cnt.most_common()


class PlaceEditorDialog(tk.Toplevel):
    """Toplevel-Dialog: Ortskonkordanz manuell bearbeiten."""

    def __init__(self, master, db_paths: list[Path]):
        super().__init__(master)
        self.title("✏ Ortskonkordanz bearbeiten")
        self.geometry("980x620")
        self.minsize(700, 400)
        self._db_paths = db_paths
        self._rows: list[dict] = []   # {raw, auto, override}
        self._edit_iid: str | None = None
        self._build()
        self._load()

    def _build(self):
        # ── Toolbar ───────────────────────────────────────────────────────
        bar = ttk.Frame(self, padding=(8, 6, 8, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="✏ Ortskonkordanz bearbeiten",
                  font=("Segoe UI", 11, "bold")).pack(side="left")
        self._status = ttk.Label(bar, text="Lade …", foreground="#666")
        self._status.pack(side="left", padx=12)
        ttk.Button(bar, text="💾 Speichern", command=self._save).pack(side="right", padx=4)
        ttk.Button(bar, text="🔁 Neu laden", command=self._load).pack(side="right", padx=4)

        # ── Suchzeile ─────────────────────────────────────────────────────
        sf = ttk.Frame(self, padding=(8, 0, 8, 4))
        sf.pack(fill="x")
        ttk.Label(sf, text="Suche:").pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        ttk.Entry(sf, textvariable=self._search_var, width=40).pack(side="left", padx=6)
        ttk.Button(sf, text="✕", width=3,
                   command=lambda: self._search_var.set("")).pack(side="left")
        ttk.Label(sf, text="  Doppelklick → Überschreibung bearbeiten",
                  foreground="#888").pack(side="left", padx=16)

        # ── Treeview ──────────────────────────────────────────────────────
        cols = ("raw", "auto", "override", "n")
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                  selectmode="browse")
        for c, t, w, stretch in (
            ("raw",      "Webtrees (Roh)",         280, True),
            ("auto",     "Normalisiert (auto)",     300, True),
            ("override", "Überschreibung (manuell)", 280, True),
            ("n",        "N",                        40, False),
        ):
            self._tree.heading(c, text=t,
                               command=lambda col=c: self._sort(col))
            self._tree.column(c, width=w, anchor="w", stretch=stretch)

        self._tree.tag_configure("has_override", foreground="#1a6b1a")
        self._tree.tag_configure("differs",      foreground="#7a3a00")

        sy = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        sx = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True, padx=8)
        self._tree.bind("<Double-1>", self._on_dblclick)

        # ── Bearbeitungsleiste ────────────────────────────────────────────
        ef = ttk.LabelFrame(self, text="Überschreibung", padding=(8, 4))
        ef.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Label(ef, text="Roh:").grid(row=0, column=0, sticky="w")
        self._lbl_raw = ttk.Label(ef, text="", foreground="#555", width=50)
        self._lbl_raw.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(ef, text="Auto:").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self._lbl_auto = ttk.Label(ef, text="", foreground="#555", width=50)
        self._lbl_auto.grid(row=0, column=3, sticky="w", padx=4)
        ttk.Label(ef, text="Überschreibung:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self._override_var = tk.StringVar()
        self._override_entry = ttk.Entry(ef, textvariable=self._override_var, width=60)
        self._override_entry.grid(row=1, column=1, columnspan=2, sticky="ew",
                                  padx=4, pady=(4, 0))
        ttk.Button(ef, text="✓ Übernehmen",
                   command=self._apply_edit).grid(row=1, column=3, padx=(8, 0), pady=(4, 0))
        ttk.Button(ef, text="✕ Löschen",
                   command=self._delete_edit).grid(row=1, column=4, padx=4, pady=(4, 0))
        ef.columnconfigure(1, weight=1)
        ef.columnconfigure(3, weight=1)
        self._override_entry.bind("<Return>", lambda _: self._apply_edit())

    # ── Laden ─────────────────────────────────────────────────────────────

    def _load(self):
        self._status.configure(text="Lade …")
        self._rows.clear()
        self._tree.delete(*self._tree.get_children())

        def _bg():
            from ancestry.tools.crawl_webtrees import normalize_place
            from ancestry.core.place_concordance import load as load_conc, CONCORDANCE_PATH
            raw_places = _collect_raw_places(self._db_paths)
            conc = {}
            try:
                import json as _json
                with open(CONCORDANCE_PATH, encoding="utf-8") as f:
                    conc = _json.load(f)
            except (FileNotFoundError, ValueError, OSError):
                conc = {}
            rows = []
            for raw, n in raw_places:
                auto = normalize_place(raw)
                override = conc.get(raw) or conc.get(raw.strip().lower()) or ""
                rows.append({"raw": raw, "auto": auto, "override": override, "n": n})
            self.after(0, lambda: self._fill(rows))

        threading.Thread(target=_bg, daemon=True, name="place_editor_load").start()

    def _fill(self, rows: list[dict]):
        self._rows = rows
        self._filter()
        self._status.configure(text=f"{len(rows)} Orte")

    def _filter(self):
        q = self._search_var.get().strip().lower()
        self._tree.delete(*self._tree.get_children())
        for r in self._rows:
            raw = r["raw"]
            auto = r["auto"]
            ov = r["override"]
            if q and q not in raw.lower() and q not in auto.lower() and q not in ov.lower():
                continue
            tag = "has_override" if ov else ("differs" if auto != raw else "")
            self._tree.insert("", "end", iid=raw, values=(raw, auto, ov, r["n"]),
                              tags=(tag,) if tag else ())

    def _sort(self, col: str):
        items = [(self._tree.set(iid, col), iid) for iid in self._tree.get_children()]
        items.sort(key=lambda x: x[0].lower())
        for i, (_, iid) in enumerate(items):
            self._tree.move(iid, "", i)

    # ── Bearbeiten ────────────────────────────────────────────────────────

    def _on_dblclick(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        self._edit_iid = iid
        vals = self._tree.item(iid, "values")
        raw, auto, ov = vals[0], vals[1], vals[2]
        self._lbl_raw.configure(text=raw)
        self._lbl_auto.configure(text=auto)
        self._override_var.set(ov)
        self._override_entry.focus_set()
        self._override_entry.selection_range(0, "end")

    def _apply_edit(self):
        if not self._edit_iid:
            return
        iid = self._edit_iid
        ov = self._override_var.get().strip()
        vals = list(self._tree.item(iid, "values"))
        vals[2] = ov
        tag = "has_override" if ov else ("differs" if vals[1] != vals[0] else "")
        self._tree.item(iid, values=vals, tags=(tag,) if tag else ())
        for r in self._rows:
            if r["raw"] == iid:
                r["override"] = ov
                break

    def _delete_edit(self):
        self._override_var.set("")
        self._apply_edit()

    # ── Speichern ─────────────────────────────────────────────────────────

    def _save(self):
        from ancestry.core.place_concordance import CONCORDANCE_PATH, load, save
        try:
            import json as _json
            try:
                with open(CONCORDANCE_PATH, encoding="utf-8") as f:
                    conc = _json.load(f)
            except (FileNotFoundError, ValueError, OSError):
                conc = {}
            for r in self._rows:
                raw = r["raw"]
                ov = r["override"].strip()
                if ov:
                    conc[raw] = ov
                else:
                    conc.pop(raw, None)
                    conc.pop(raw.strip().lower(), None)
            save(conc)
            self._status.configure(text=f"Gespeichert: {CONCORDANCE_PATH}")
        except Exception as exc:
            messagebox.showerror("Fehler", f"Speichern fehlgeschlagen:\n{exc}", parent=self)
