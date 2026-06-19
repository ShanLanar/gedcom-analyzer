"""Kirchenbuch-NER-Suche: findet Personen nach Namen über alle Pfarreien."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

try:
    from tasks.names import koelner_phonetik as _kp
except ImportError:
    _kp = None


def _phonetik(name: str) -> str:
    if _kp and name:
        try:
            return _kp(name)
        except Exception:
            pass
    return ""


def show_ner_search(parent: tk.Widget, db) -> None:

    win = tk.Toplevel(parent)
    win.title("Kirchenbuch-Personensuche (NER)")
    win.geometry("860x560")

    top = ttk.Frame(win)
    top.pack(fill="x", padx=10, pady=8)

    ttk.Label(top, text="Name:").pack(side="left")
    name_var = tk.StringVar()
    name_entry = ttk.Entry(top, textvariable=name_var, width=28)
    name_entry.pack(side="left", padx=(4, 8))

    ttk.Label(top, text="Rolle:").pack(side="left")
    role_var = tk.StringVar(value="(alle)")
    ttk.Combobox(top, textvariable=role_var, width=18, state="readonly",
                 values=["(alle)", "kind", "vater", "mutter", "pate",
                          "braeutigam", "braut", "zeuge",
                          "verstorbener", "elternteil"]).pack(side="left", padx=(4, 8))

    ttk.Label(top, text="Jahr von:").pack(side="left")
    year_from_var = tk.StringVar()
    ttk.Entry(top, textvariable=year_from_var, width=6).pack(side="left", padx=(4, 4))
    ttk.Label(top, text="bis:").pack(side="left")
    year_to_var = tk.StringVar()
    ttk.Entry(top, textvariable=year_to_var, width=6).pack(side="left", padx=(4, 8))

    phonetik_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(top, text="Phonetik", variable=phonetik_var).pack(side="left", padx=(0, 8))

    search_btn = ttk.Button(top, text="Suchen")
    search_btn.pack(side="left")

    status_var = tk.StringVar(value="")
    ttk.Label(win, textvariable=status_var, foreground="#666").pack(
        anchor="w", padx=10, pady=(0, 2))

    cols = ("name_raw", "rolle", "beruf", "pfarrei", "buch_typ", "year", "ort")
    tv = ttk.Treeview(win, columns=cols, show="headings", height=20)
    for col, lbl, w in [
        ("name_raw",  "Name",        200),
        ("rolle",     "Rolle",        90),
        ("beruf",     "Beruf",       100),
        ("pfarrei",   "Pfarrei",     160),
        ("buch_typ",  "Buchtyp",      80),
        ("year",      "Jahr",         55),
        ("ort",       "Ort",         140),
    ]:
        tv.heading(col, text=lbl)
        tv.column(col, width=w, anchor="w" if w > 80 else "center")

    sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
    sb.pack(side="right", fill="y", pady=4)

    def _search(_event=None):
        tv.delete(*tv.get_children())
        name = name_var.get().strip()
        if not name:
            status_var.set("Bitte Namen eingeben.")
            return

        conditions = []
        params: list = []

        if phonetik_var.get() and _kp:
            code = _phonetik(name)
            if code:
                conditions.append("n.koeln_code = ?")
                params.append(code)
            else:
                conditions.append("n.name_norm LIKE ?")
                params.append(f"%{name.lower()}%")
        else:
            conditions.append("n.name_raw LIKE ?")
            params.append(f"%{name}%")

        rolle = role_var.get()
        if rolle and rolle != "(alle)":
            conditions.append("n.rolle = ?")
            params.append(rolle)

        try:
            yf = int(year_from_var.get())
            conditions.append("n.event_year >= ?"); params.append(yf)
        except ValueError:
            pass
        try:
            yt = int(year_to_var.get())
            conditions.append("n.event_year <= ?"); params.append(yt)
        except ValueError:
            pass

        where = " AND ".join(conditions) if conditions else "1=1"
        try:
            with db._cursor() as cur:
                rows = cur.execute(f"""
                    SELECT n.name_raw, n.rolle, n.beruf, n.ort,
                           n.event_year,
                           e.parish_id,
                           b.book_type
                    FROM matrikula_ner n
                    JOIN source_matrikula_entries e ON e.entry_id = n.entry_id
                    LEFT JOIN source_matrikula_books b ON b.book_id = n.book_id
                    WHERE {where}
                    ORDER BY n.event_year, e.parish_id
                    LIMIT 500
                """, params).fetchall()
        except Exception as exc:
            status_var.set(f"Fehler: {exc}")
            return

        for r in rows:
            tv.insert("", "end", values=(
                r["name_raw"] or "",
                r["rolle"] or "",
                r["beruf"] or "",
                r["parish_id"] or "",
                r["book_type"] or "",
                r["event_year"] or "",
                r["ort"] or "",
            ))

        count = len(rows)
        suffix = " (Limit 500 erreicht)" if count == 500 else ""
        status_var.set(f"{count} Treffer{suffix}")

    search_btn.configure(command=_search)
    name_entry.bind("<Return>", _search)
    name_entry.focus_set()
