#!/usr/bin/env python3
"""
Genealogie-Datenviewer — durchsucht und navigiert die gesammelten Personen-
daten in einer Baum-/Detailansicht (ähnlich der Ancestry-Personenseite).

Quellen:
  • Anverwandte   – ancestry/tools/webtrees_crawl.db  (Tabelle wt_persons)
  • GEDCOM/extern – ancestry/ancestry_dna.db          (Tabelle gedcom_persons)

Der Viewer öffnet die Crawl-DB READ-ONLY und mit busy_timeout, damit er den
LAUFENDEN Crawler NICHT stört. „🔄 Aktualisieren" lädt neu hinzugekommene
Personen nach – man kann also live zusehen, wie der Baum wächst.

Start:
    python viewer.py                       # Standard: Anverwandte-Crawl-DB
    python viewer.py pfad/zur/datenbank.db
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tkinter as tk
from tkinter import ttk, messagebox

ROOT = os.path.dirname(os.path.abspath(__file__))
CRAWL_DB   = os.path.join(ROOT, "ancestry", "tools", "webtrees_crawl.db")
ANCESTRY_DB = os.path.join(ROOT, "ancestry", "ancestry_dna.db")

# ── Farben (an die Ancestry-Optik angelehnt) ─────────────────────────────────
C = {
    "bg":        "#1f2327",
    "panel":     "#2a2f35",
    "card":      "#3a4048",
    "card_m":    "#5a7a9a",   # männlich (blau)
    "card_f":    "#9a6a6a",   # weiblich (rot/rosa)
    "text":      "#e8e8e8",
    "muted":     "#9aa4ae",
    "accent":    "#7cb342",
    "link":      "#8ab4f8",
    "sel":       "#3d5a3d",
}


def _ro_connect(path: str) -> sqlite3.Connection | None:
    """Öffnet eine SQLite-DB read-only (URI-Modus), stört keinen Schreiber."""
    if not os.path.exists(path):
        return None
    try:
        uri = f"file:{path}?mode=ro&immutable=0"
        c = sqlite3.connect(uri, uri=True, timeout=5.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=4000")
        return c
    except Exception:
        try:
            c = sqlite3.connect(path, timeout=5.0)
            c.row_factory = sqlite3.Row
            return c
        except Exception:
            return None


def _years(birth: str, death: str) -> str:
    b = (birth or "").strip()
    d = (death or "").strip()
    if not b and not d:
        return ""
    return f"{b or '?'}–{d or ''}".rstrip("–")


def _loads(s) -> list:
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class DataViewer(tk.Frame):
    """Eigenständig (master=None) oder eingebettet (master=<Frame>)."""

    def __init__(self, master=None, db_path: str | None = None):
        self._embedded = master is not None
        if master is None:
            master = tk.Tk()
        super().__init__(master, bg=C["bg"])
        root = self.winfo_toplevel()
        if not self._embedded:
            root.title("Genealogie-Datenviewer")
            root.geometry("1280x820")
            root.minsize(1000, 640)
            root.configure(bg=C["bg"])
        self.pack(fill="both", expand=True)

        self._db_path = db_path or CRAWL_DB
        self._source  = "anverwandte"        # anverwandte | gedcom
        self._conn: sqlite3.Connection | None = None
        self._current_id: str | None = None
        self._name_cache: dict[str, str] = {}
        self._history: list[str] = []

        self._build()
        self._open_db()
        self._refresh_stats()
        self._do_search()

    # ── DB ────────────────────────────────────────────────────────────────────
    def _open_db(self):
        if self._source == "anverwandte":
            self._conn = _ro_connect(self._db_path)
        else:
            self._conn = _ro_connect(ANCESTRY_DB)
        if self._conn is None:
            self._status.set("⚠ Datenbank nicht gefunden / noch nicht angelegt: "
                             + (self._db_path if self._source == "anverwandte"
                                else ANCESTRY_DB))

    def _reopen(self):
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._name_cache.clear()
        self._open_db()
        self._refresh_stats()
        self._do_search()

    # ── UI-Aufbau ───────────────────────────────────────────────────────────
    def _build(self):
        # Top-Leiste
        top = tk.Frame(self, bg=C["panel"]); top.pack(fill="x")
        tk.Label(top, text="Quelle:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4), pady=8)
        self._src_var = tk.StringVar(value="Anverwandte (Crawl)")
        src = ttk.Combobox(top, textvariable=self._src_var, width=24,
                           state="readonly",
                           values=["Anverwandte (Crawl)", "GEDCOM / extern"])
        src.pack(side="left", pady=8)
        src.bind("<<ComboboxSelected>>", self._on_source_change)

        tk.Label(top, text="Suche:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(16, 4))
        self._search_var = tk.StringVar()
        e = tk.Entry(top, textvariable=self._search_var, width=28)
        e.pack(side="left", pady=8)
        e.bind("<Return>", lambda _: self._do_search())
        tk.Button(top, text="🔍", command=self._do_search).pack(side="left", padx=4)
        tk.Button(top, text="🔄 Aktualisieren", command=self._reopen).pack(
            side="left", padx=12)

        self._stats = tk.StringVar(value="")
        tk.Label(top, textvariable=self._stats, bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 9, "bold")).pack(side="right", padx=12)

        # Hauptbereich: links Liste, Mitte Baum, rechts Detail
        body = tk.Frame(self, bg=C["bg"]); body.pack(fill="both", expand=True)

        # Links: Suchergebnisse
        left = tk.Frame(body, bg=C["panel"], width=300); left.pack(
            side="left", fill="y"); left.pack_propagate(False)
        tk.Label(left, text="Ergebnisse", bg=C["panel"], fg=C["muted"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        cols = ("name", "years", "place")
        self._list = ttk.Treeview(left, columns=cols, show="headings",
                                  selectmode="browse")
        self._list.heading("name", text="Name")
        self._list.heading("years", text="Jahre")
        self._list.heading("place", text="Ort")
        self._list.column("name", width=150)
        self._list.column("years", width=70, anchor="center")
        self._list.column("place", width=70)
        self._list.pack(fill="both", expand=True, padx=6, pady=6)
        self._list.bind("<<TreeviewSelect>>", self._on_list_select)

        # Mitte: navigierbarer Mini-Baum
        mid = tk.Frame(body, bg=C["bg"]); mid.pack(side="left", fill="both",
                                                   expand=True)
        nav = tk.Frame(mid, bg=C["bg"]); nav.pack(fill="x")
        tk.Button(nav, text="◀ Zurück", command=self._go_back).pack(
            side="left", padx=8, pady=6)
        self._tree_canvas = tk.Frame(mid, bg=C["bg"])
        self._tree_canvas.pack(fill="both", expand=True, padx=8, pady=8)

        # Rechts: Detailpanel (scrollbar)
        right = tk.Frame(body, bg=C["panel"], width=360); right.pack(
            side="right", fill="y"); right.pack_propagate(False)
        self._detail_canvas = tk.Canvas(right, bg=C["panel"],
                                        highlightthickness=0, width=360)
        dsb = ttk.Scrollbar(right, orient="vertical",
                            command=self._detail_canvas.yview)
        self._detail = tk.Frame(self._detail_canvas, bg=C["panel"])
        self._detail.bind("<Configure>", lambda _: self._detail_canvas.configure(
            scrollregion=self._detail_canvas.bbox("all")))
        self._detail_canvas.create_window((0, 0), window=self._detail, anchor="nw")
        self._detail_canvas.configure(yscrollcommand=dsb.set)
        self._detail_canvas.pack(side="left", fill="both", expand=True)
        dsb.pack(side="right", fill="y")

        # Statuszeile
        self._status = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status, bg=C["bg"], fg=C["muted"],
                 anchor="w").pack(fill="x", side="bottom")

    # ── Datenquellen-Wechsel ─────────────────────────────────────────────────
    def _on_source_change(self, _=None):
        self._source = ("anverwandte" if self._src_var.get().startswith("Anver")
                        else "gedcom")
        self._reopen()

    # ── Statistik (Live) ─────────────────────────────────────────────────────
    def _refresh_stats(self):
        if not self._conn:
            self._stats.set("—")
            return
        try:
            if self._source == "anverwandte":
                n = self._conn.execute(
                    "SELECT COUNT(*) FROM wt_persons").fetchone()[0]
                openf = 0
                try:
                    openf = self._conn.execute(
                        "SELECT COUNT(*) FROM wt_frontier WHERE done=0"
                    ).fetchone()[0]
                except Exception:
                    pass
                self._stats.set(f"{n:,} Personen · {openf:,} offen".replace(",", "."))
            else:
                n = self._conn.execute(
                    "SELECT COUNT(*) FROM gedcom_persons").fetchone()[0]
                self._stats.set(f"{n:,} Personen".replace(",", "."))
        except Exception as e:
            self._stats.set(f"⚠ {e}")

    # ── Suche ─────────────────────────────────────────────────────────────────
    def _do_search(self):
        self._list.delete(*self._list.get_children())
        if not self._conn:
            return
        q = self._search_var.get().strip()
        try:
            if self._source == "anverwandte":
                if q:
                    rows = self._conn.execute(
                        "SELECT id, name, given_name, surname, birth_year, "
                        "death_year, birth_place FROM wt_persons "
                        "WHERE name LIKE ? OR surname LIKE ? OR given_name LIKE ? "
                        "ORDER BY surname, given_name LIMIT 500",
                        (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT id, name, given_name, surname, birth_year, "
                        "death_year, birth_place FROM wt_persons "
                        "ORDER BY rowid DESC LIMIT 300").fetchall()
                for r in rows:
                    label = r["name"] or f"{r['given_name']} {r['surname']}".strip()
                    self._list.insert("", "end", iid=r["id"], values=(
                        label, _years(r["birth_year"], r["death_year"]),
                        (r["birth_place"] or "")[:18]))
            else:
                if q:
                    rows = self._conn.execute(
                        "SELECT ged_id, given_name, surname, birth_year, "
                        "death_year, birth_place FROM gedcom_persons "
                        "WHERE surname LIKE ? OR given_name LIKE ? "
                        "ORDER BY surname, given_name LIMIT 500",
                        (f"%{q}%", f"%{q}%")).fetchall()
                else:
                    rows = self._conn.execute(
                        "SELECT ged_id, given_name, surname, birth_year, "
                        "death_year, birth_place FROM gedcom_persons "
                        "ORDER BY surname, given_name LIMIT 300").fetchall()
                for r in rows:
                    label = f"{r['given_name']} {r['surname']}".strip()
                    self._list.insert("", "end", iid=r["ged_id"], values=(
                        label,
                        _years(str(r["birth_year"] or ""), str(r["death_year"] or "")),
                        (r["birth_place"] or "")[:18]))
        except Exception as e:
            self._status.set(f"⚠ Suche: {e}")

    def _on_list_select(self, _=None):
        sel = self._list.selection()
        if sel:
            self._navigate(sel[0])

    # ── Personen laden ────────────────────────────────────────────────────────
    def _person(self, pid: str) -> dict | None:
        if not self._conn or not pid:
            return None
        try:
            if self._source == "anverwandte":
                r = self._conn.execute(
                    "SELECT * FROM wt_persons WHERE id=?", (pid,)).fetchone()
            else:
                r = self._conn.execute(
                    "SELECT * FROM gedcom_persons WHERE ged_id=?", (pid,)).fetchone()
            return dict(r) if r else None
        except Exception:
            return None

    def _label_for(self, pid: str) -> str:
        """Anzeigename für eine ID (aus Cache/DB), Fallback = ID."""
        if pid in self._name_cache:
            return self._name_cache[pid]
        p = self._person(pid)
        if p:
            if self._source == "anverwandte":
                lbl = p.get("name") or f"{p.get('given_name','')} {p.get('surname','')}".strip()
                yrs = _years(p.get("birth_year"), p.get("death_year"))
            else:
                lbl = f"{p.get('given_name','')} {p.get('surname','')}".strip()
                yrs = _years(str(p.get("birth_year") or ""), str(p.get("death_year") or ""))
            lbl = (lbl + (f"\n{yrs}" if yrs else "")) or pid
        else:
            lbl = f"{pid}\n(noch nicht geladen)"
        self._name_cache[pid] = lbl
        return lbl

    # ── Navigation ────────────────────────────────────────────────────────────
    def _navigate(self, pid: str, push=True):
        if push and self._current_id and self._current_id != pid:
            self._history.append(self._current_id)
        self._current_id = pid
        self._render_tree(pid)
        self._render_detail(pid)

    def _go_back(self):
        if self._history:
            self._navigate(self._history.pop(), push=False)

    # ── Mini-Baum (Mitte) ─────────────────────────────────────────────────────
    def _render_tree(self, pid: str):
        for w in self._tree_canvas.winfo_children():
            w.destroy()
        p = self._person(pid)
        if not p:
            tk.Label(self._tree_canvas, text="Person nicht gefunden.",
                     bg=C["bg"], fg=C["muted"]).pack(pady=20)
            return

        if self._source == "anverwandte":
            parents = _loads(p.get("parents_json"))
            spouses = _loads(p.get("spouses_json"))
            children = _loads(p.get("children_json"))
            siblings = _loads(p.get("siblings_json"))
        else:
            parents = spouses = children = siblings = []

        # Eltern-Reihe
        if parents:
            row = tk.Frame(self._tree_canvas, bg=C["bg"]); row.pack(pady=(4, 0))
            tk.Label(row, text="Eltern", bg=C["bg"], fg=C["muted"]).pack()
            prow = tk.Frame(self._tree_canvas, bg=C["bg"]); prow.pack()
            for par in parents:
                self._person_card(prow, par).pack(side="left", padx=6, pady=4)
            tk.Label(self._tree_canvas, text="│", bg=C["bg"], fg=C["muted"]).pack()

        # Person + Partner
        crow = tk.Frame(self._tree_canvas, bg=C["bg"]); crow.pack(pady=4)
        self._person_card(crow, pid, highlight=True).pack(side="left", padx=6)
        for sp in spouses:
            tk.Label(crow, text="⚭", bg=C["bg"], fg=C["muted"],
                     font=("Segoe UI", 14)).pack(side="left")
            self._person_card(crow, sp).pack(side="left", padx=6)

        # Kinder-Reihe
        if children:
            tk.Label(self._tree_canvas, text="│", bg=C["bg"], fg=C["muted"]).pack()
            tk.Label(self._tree_canvas, text=f"Kinder ({len(children)})",
                     bg=C["bg"], fg=C["muted"]).pack()
            kwrap = tk.Frame(self._tree_canvas, bg=C["bg"]); kwrap.pack()
            # bis zu 12 Kinder in Reihen zu je 6
            for i, ch in enumerate(children[:12]):
                if i % 6 == 0:
                    krow = tk.Frame(kwrap, bg=C["bg"]); krow.pack()
                self._person_card(krow, ch, small=True).pack(
                    side="left", padx=4, pady=4)
            if len(children) > 12:
                tk.Label(kwrap, text=f"… +{len(children)-12} weitere",
                         bg=C["bg"], fg=C["muted"]).pack()

        # Geschwister (kompakt)
        if siblings:
            tk.Label(self._tree_canvas, text=f"Geschwister: {len(siblings)}",
                     bg=C["bg"], fg=C["muted"]).pack(pady=(10, 0))

    def _person_card(self, parent, pid: str, highlight=False, small=False) -> tk.Widget:
        p = self._person(pid)
        sex = (p or {}).get("sex", "") if p else ""
        bg = C["card_m"] if sex == "M" else C["card_f"] if sex == "F" else C["card"]
        if highlight:
            frame = tk.Frame(parent, bg=C["accent"], bd=0)
            inner = tk.Frame(frame, bg=bg); inner.pack(padx=3, pady=3)
        else:
            frame = tk.Frame(parent, bg=bg)
            inner = frame
        lbl_text = self._label_for(pid)
        w = 14 if small else 18
        btn = tk.Label(inner, text=lbl_text, bg=bg, fg="white",
                       width=w, justify="center", cursor="hand2",
                       font=("Segoe UI", 7 if small else 9),
                       padx=4, pady=4, wraplength=130)
        btn.pack()
        btn.bind("<Button-1>", lambda _, i=pid: self._navigate(i))
        return frame

    # ── Detailpanel (rechts) ──────────────────────────────────────────────────
    def _render_detail(self, pid: str):
        for w in self._detail.winfo_children():
            w.destroy()
        p = self._person(pid)
        if not p:
            return

        def hdr(t):
            tk.Label(self._detail, text=t, bg=C["panel"], fg=C["accent"],
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(
                fill="x", padx=12, pady=(12, 2))

        def fact(label, value, link_id=None):
            if not value:
                return
            f = tk.Frame(self._detail, bg=C["panel"]); f.pack(fill="x", padx=12, pady=1)
            tk.Label(f, text=label, bg=C["panel"], fg=C["muted"], width=11,
                     anchor="w", font=("Segoe UI", 8)).pack(side="left")
            fg = C["link"] if link_id else C["text"]
            lab = tk.Label(f, text=value, bg=C["panel"], fg=fg, anchor="w",
                           justify="left", wraplength=230,
                           cursor="hand2" if link_id else "arrow")
            lab.pack(side="left", fill="x", expand=True)
            if link_id:
                lab.bind("<Button-1>", lambda _, i=link_id: self._navigate(i))

        if self._source == "anverwandte":
            name = p.get("name") or f"{p.get('given_name','')} {p.get('surname','')}".strip()
            tk.Label(self._detail, text=name, bg=C["panel"], fg="white",
                     font=("Segoe UI", 14, "bold"), wraplength=320,
                     anchor="w").pack(fill="x", padx=12, pady=(12, 0))
            tk.Label(self._detail, text=f"ID {p.get('id','')} · {p.get('sex','')}",
                     bg=C["panel"], fg=C["muted"], anchor="w").pack(
                fill="x", padx=12)

            hdr("Lebensdaten")
            fact("Geboren", " · ".join(x for x in (
                p.get("birth_date"), p.get("birth_place")) if x))
            fact("Gestorben", " · ".join(x for x in (
                p.get("death_date"), p.get("death_place")) if x))

            hdr("Beziehungen")
            for par in _loads(p.get("parents_json")):
                fact("Elternteil", self._label_for(par).replace("\n", " "), par)
            for sp in _loads(p.get("spouses_json")):
                fact("Partner", self._label_for(sp).replace("\n", " "), sp)
            ch = _loads(p.get("children_json"))
            for c in ch:
                fact("Kind", self._label_for(c).replace("\n", " "), c)
            for sib in _loads(p.get("siblings_json")):
                fact("Geschwister", self._label_for(sib).replace("\n", " "), sib)

            # Matricula-Belege
            matric = _loads(p.get("matricula_json"))
            if matric:
                hdr("Kirchenbuch-Belege (Matricula)")
                for m in matric:
                    if not isinstance(m, dict):
                        continue
                    parts = []
                    if m.get("parish_old"): parts.append(m["parish_old"])
                    if m.get("ref"):        parts.append(m["ref"])
                    if m.get("diocese"):    parts.append(f"({m['diocese']})")
                    txt = " ".join(parts) or m.get("url_old", "")
                    fact("Beleg", txt)
                    if m.get("url_old"):
                        u = tk.Label(self._detail, text=m["url_old"][:50] + "…",
                                     bg=C["panel"], fg=C["link"], cursor="hand2",
                                     anchor="w", font=("Segoe UI", 7), wraplength=320)
                        u.pack(fill="x", padx=24)
                        u.bind("<Button-1>", lambda _, url=m["url_old"]:
                               self._open_url(url))

            if p.get("url"):
                hdr("Quelle")
                u = tk.Label(self._detail, text=p["url"], bg=C["panel"],
                             fg=C["link"], cursor="hand2", anchor="w",
                             font=("Segoe UI", 7), wraplength=320)
                u.pack(fill="x", padx=12)
                u.bind("<Button-1>", lambda _, url=p["url"]: self._open_url(url))
        else:
            name = f"{p.get('given_name','')} {p.get('surname','')}".strip()
            tk.Label(self._detail, text=name, bg=C["panel"], fg="white",
                     font=("Segoe UI", 14, "bold"), wraplength=320,
                     anchor="w").pack(fill="x", padx=12, pady=(12, 0))
            tk.Label(self._detail,
                     text=f"{p.get('ged_id','')} · Quelle: {p.get('source','')}",
                     bg=C["panel"], fg=C["muted"], anchor="w").pack(
                fill="x", padx=12)
            hdr("Lebensdaten")
            fact("Geboren", " · ".join(str(x) for x in (
                p.get("birth_year"), p.get("birth_place")) if x))
            fact("Gestorben", " · ".join(str(x) for x in (
                p.get("death_year"), p.get("death_place")) if x))
            fact("Sosa", str(p.get("sosa_number") or "") if p.get("sosa_number") else "")
            fact("Geschlecht", p.get("sex", ""))

        self._status.set(f"Anzeige: {pid}")

    def _open_url(self, url: str):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            messagebox.showinfo("Link", f"{url}\n\n({e})")

    def mainloop(self, *a, **k):
        self.winfo_toplevel().mainloop(*a, **k)


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else CRAWL_DB
    app = DataViewer(db_path=db)
    app.mainloop()


if __name__ == "__main__":
    main()
