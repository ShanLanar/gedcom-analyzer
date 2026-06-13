"""Dubletten-Review: zeigt vom Dubletten-Detektor (ancestry.core.dedup_ml)
gefundene Personenpaar-Kandidaten und lässt sie als „Dublette" / „keine
Dublette" bestätigen. Jede Entscheidung wird in gedcom_person_xref geschrieben
(confirmed/rejected) – das sind zugleich die Labels, mit denen sich das Modell
trainieren lässt („🧠 Modell trainieren").
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox


class DedupReview(ttk.Frame):
    def __init__(self, master, db):
        super().__init__(master)
        self._db = db
        self._pairs: dict[str, dict] = {}
        self.pack(fill="both", expand=True)
        self._build()
        self.reload()

    def _build(self):
        bar = ttk.Frame(self); bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(bar, text="🔍 Dubletten-Erkennung",
                  font=("Segoe UI", 12, "bold")).pack(side="left")
        ttk.Label(bar, text="  Schwelle:").pack(side="left", padx=(12, 2))
        self._thr = tk.DoubleVar(value=0.6)
        ttk.Spinbox(bar, from_=0.3, to=0.95, increment=0.05, width=5,
                    textvariable=self._thr, command=self.reload).pack(side="left")
        ttk.Button(bar, text="🔁 Neu suchen", command=self.reload).pack(side="left", padx=8)
        ttk.Button(bar, text="🧠 Modell trainieren", command=self._train).pack(side="left")
        self._status = ttk.Label(bar, text="", foreground="#666")
        self._status.pack(side="right")

        cols = ("a", "ya", "b", "yb", "ort", "score", "q")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("a", "Person A", 180), ("ya", "*A", 50), ("b", "Person B", 180),
                        ("yb", "*B", 50), ("ort", "Ort", 140), ("score", "Score", 60),
                        ("q", "Quelle", 60)):
            self._tree.heading(c, text=t)
            self._tree.column(c, width=w, anchor="w", stretch=(c in ("a", "b", "ort")))
        sy = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sy.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        sy.pack(side="left", fill="y", pady=8)

        act = ttk.Frame(self); act.pack(side="right", fill="y", padx=8, pady=8)
        ttk.Button(act, text="✓ Ist Dublette", command=lambda: self._mark("confirmed")
                   ).pack(fill="x", pady=4)
        ttk.Button(act, text="✗ Keine Dublette", command=lambda: self._mark("rejected")
                   ).pack(fill="x", pady=4)
        ttk.Label(act, text="Entscheidungen werden\nals Labels gespeichert\n"
                            "und trainieren das Modell.", foreground="#888",
                  justify="left").pack(pady=(16, 0))

    def reload(self):
        self._tree.delete(*self._tree.get_children())
        self._pairs.clear()
        self._status.configure(text="suche …")

        def _bg():
            try:
                from ancestry.core import dedup_ml
                rows = dedup_ml.find_duplicates(self._db, threshold=float(self._thr.get()))
            except Exception as exc:
                self.after(0, lambda e=exc: self._status.configure(text=f"⚠ {e}"))
                return
            self.after(0, lambda: self._fill(rows))
        threading.Thread(target=_bg, daemon=True, name="dedup").start()

    def _fill(self, rows):
        for r in rows:
            ort = r.get("place_a") or r.get("place_b") or ""
            iid = self._tree.insert("", "end", values=(
                r["name_a"], r.get("birth_a") or "", r["name_b"], r.get("birth_b") or "",
                ort[:24], f"{r['score']:.2f}", r.get("source", "")))
            self._pairs[iid] = r
        self._status.configure(text=f"{len(rows)} Kandidaten")

    def _mark(self, status: str):
        sel = self._tree.selection()
        if not sel or sel[0] not in self._pairs:
            return
        r = self._pairs[sel[0]]
        try:
            with self._db._cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO gedcom_person_xref"
                    "(ged_id_primary, source_primary, ged_id_other, source_other, status, score)"
                    " VALUES (?,?,?,?,?,?)",
                    (str(r["ged_id_a"]), r.get("source_a", "gedcom"),
                     str(r["ged_id_b"]), r.get("source_b", "gedcom"),
                     status, float(r["score"])))
        except Exception as exc:
            messagebox.showerror("Speichern", str(exc))
            return
        self._tree.delete(sel[0])
        self._pairs.pop(sel[0], None)
        self._status.configure(text=f"{len(self._pairs)} Kandidaten · gespeichert: {status}")

    def _train(self):
        from ancestry.core import dedup_ml
        res = dedup_ml.train(self._db)
        if "error" in res:
            messagebox.showinfo("Training", f"Nicht trainiert: {res['error']}\n\n"
                                "Erst ein paar Paare als Dublette/keine markieren.")
        else:
            messagebox.showinfo("Training",
                                f"Modell trainiert.\nLabels: {res['n_train']} "
                                f"(davon {res['n_pos']} Dubletten)\n"
                                f"Trainingsgenauigkeit: {res['train_acc']*100:.0f}%")
            self.reload()


def open_dedup_review(parent, db):
    win = tk.Toplevel(parent)
    win.title("Dubletten-Erkennung — Personen")
    win.geometry("1020x640")
    try:
        DedupReview(win, db)
    except Exception as exc:
        ttk.Label(win, text=f"Dubletten-Review-Fehler:\n{exc}",
                  foreground="#b00020", padding=20, justify="left").pack()
    return win
