"""Research-To-Do-Manager — Dialog (Feature B1).

Zeigt Aufgaben (research_tasks) in einem Treeview mit Anlegen / Status /
Bearbeiten / Löschen. Wird entweder global geöffnet oder auf eine Entität
(Match / Ahn / Ort) eingeschränkt — dann sind neue Aufgaben vorbelegt.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

_STATUS_ICON = {"open": "○", "doing": "◐", "done": "✓"}
_STATUS_LABEL = {"open": "offen", "doing": "in Arbeit", "done": "erledigt"}
_PRIO_LABEL = {1: "hoch", 2: "normal", 3: "niedrig"}
_PRIO_FROM_LABEL = {v: k for k, v in _PRIO_LABEL.items()}


def show_research_tasks(parent, state, entity_type: str = "", entity_key: str = "",
                        entity_label: str = "", set_status=None):
    db = getattr(state, "db", None)
    if db is None:
        messagebox.showerror("Aufgaben", "Keine Datenbank verfügbar.")
        return

    scoped = bool(entity_type and entity_key)
    win = tk.Toplevel(parent)
    win.title("Aufgaben" + (f" — {entity_label}" if entity_label else " (Forschungs-To-Dos)"))
    win.geometry("820x520")

    # ── Eingabe: neue Aufgabe ────────────────────────────────────────────────
    add_row = ttk.Frame(win)
    add_row.pack(fill="x", padx=10, pady=(10, 4))
    ttk.Label(add_row, text="Neue Aufgabe:").pack(side="left")
    title_var = tk.StringVar()
    ent = ttk.Entry(add_row, textvariable=title_var, width=44)
    ent.pack(side="left", padx=6)
    prio_var = tk.StringVar(value="normal")
    ttk.Combobox(add_row, textvariable=prio_var, width=8, state="readonly",
                 values=["hoch", "normal", "niedrig"]).pack(side="left", padx=(0, 6))

    # ── Filter ───────────────────────────────────────────────────────────────
    filt_var = tk.StringVar(value="offen+aktiv")
    ttk.Label(add_row, text="Filter:").pack(side="left", padx=(14, 2))
    ttk.Combobox(add_row, textvariable=filt_var, width=12, state="readonly",
                 values=["alle", "offen+aktiv", "offen", "in Arbeit", "erledigt"]
                 ).pack(side="left")

    # ── Treeview ─────────────────────────────────────────────────────────────
    cols = ("status", "prio", "title", "entity", "due", "result")
    tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse")
    for c, (lbl, w, anchor) in {
        "status": ("Status", 70, "center"),
        "prio":   ("Prio", 60, "center"),
        "title":  ("Aufgabe", 300, "w"),
        "entity": ("Bezug", 150, "w"),
        "due":    ("Fällig", 90, "center"),
        "result": ("Ergebnis", 160, "w"),
    }.items():
        tv.heading(c, text=lbl)
        tv.column(c, width=w, anchor=anchor, stretch=(c in ("title", "result")))
    tv.pack(fill="both", expand=True, padx=10, pady=4)
    tv.tag_configure("done", foreground="#888888")
    tv.tag_configure("doing", background="#fff4d6")

    id_by_iid: dict[str, int] = {}

    def _status_set(msg):
        if callable(set_status):
            try:
                set_status(msg)
            except Exception:
                pass

    def _reload():
        tv.delete(*tv.get_children())
        id_by_iid.clear()
        f = filt_var.get()
        kw = {}
        if scoped:
            kw = {"entity_type": entity_type, "entity_key": entity_key}
        if f == "offen+aktiv":
            kw["include_done"] = False
        elif f == "offen":
            kw["status"] = "open"
        elif f == "in Arbeit":
            kw["status"] = "doing"
        elif f == "erledigt":
            kw["status"] = "done"
        try:
            tasks = db.get_tasks(**kw)
        except Exception as e:
            messagebox.showerror("Aufgaben", f"Laden fehlgeschlagen: {e}")
            return
        for t in tasks:
            st = t.get("status", "open")
            ent_txt = "" if scoped else (
                f"{t.get('entity_label') or t.get('entity_key') or ''}"
                + (f" [{t.get('entity_type')}]" if t.get("entity_type") else ""))
            iid = tv.insert("", "end", tags=(st,), values=(
                f"{_STATUS_ICON.get(st, '?')} {_STATUS_LABEL.get(st, st)}",
                _PRIO_LABEL.get(t.get("priority", 2), "normal"),
                t.get("title", ""),
                ent_txt.strip(),
                t.get("due_date", ""),
                t.get("result", ""),
            ))
            id_by_iid[iid] = t["task_id"]
        n_open = db.count_open_tasks(entity_type or None, entity_key or None) \
            if scoped else db.count_open_tasks()
        _status_set(f"{len(tasks)} Aufgaben angezeigt · {n_open} offen")

    def _add(_=None):
        title = title_var.get().strip()
        if not title:
            return
        db.add_task(title, entity_type=entity_type, entity_key=entity_key,
                    entity_label=entity_label,
                    priority=_PRIO_FROM_LABEL.get(prio_var.get(), 2))
        title_var.set("")
        _reload()

    def _selected_id():
        sel = tv.selection()
        return id_by_iid.get(sel[0]) if sel else None

    def _set_status_sel(status):
        tid = _selected_id()
        if tid is None:
            return
        db.set_task_status(tid, status)
        _reload()

    def _edit():
        tid = _selected_id()
        if tid is None:
            return
        new_title = simpledialog.askstring("Aufgabe bearbeiten", "Titel:", parent=win)
        if new_title and new_title.strip():
            db.update_task(tid, title=new_title.strip())
            _reload()

    def _set_result():
        tid = _selected_id()
        if tid is None:
            return
        res = simpledialog.askstring("Ergebnis festhalten",
                                     "Ergebnis / Fundstelle:", parent=win)
        if res is not None:
            db.update_task(tid, result=res.strip(), status="done")
            _reload()

    def _delete():
        tid = _selected_id()
        if tid is None:
            return
        if messagebox.askyesno("Löschen", "Aufgabe wirklich löschen?", parent=win):
            db.delete_task(tid)
            _reload()

    # ── Buttonleiste ─────────────────────────────────────────────────────────
    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Button(btns, text="✓ erledigt", command=lambda: _set_status_sel("done")).pack(side="left")
    ttk.Button(btns, text="◐ in Arbeit", command=lambda: _set_status_sel("doing")).pack(side="left", padx=4)
    ttk.Button(btns, text="○ offen", command=lambda: _set_status_sel("open")).pack(side="left")
    ttk.Button(btns, text="📝 Ergebnis…", command=_set_result).pack(side="left", padx=4)
    ttk.Button(btns, text="✎ Titel…", command=_edit).pack(side="left")
    ttk.Button(btns, text="🗑 Löschen", command=_delete).pack(side="left", padx=4)
    ttk.Button(btns, text="Schließen", command=win.destroy).pack(side="right")

    ent.bind("<Return>", _add)
    add_row_add = ttk.Button(add_row, text="➕ Anlegen", command=_add)
    add_row_add.pack(side="left", padx=6)
    filt_var.trace_add("write", lambda *_: _reload())
    tv.bind("<Double-1>", lambda _: _set_status_sel(
        "done" if (_cur := _current_status(tv)) != "done" else "open"))

    _reload()
    ent.focus_set()


def _current_status(tv) -> str:
    sel = tv.selection()
    if not sel:
        return ""
    tags = tv.item(sel[0], "tags")
    return tags[0] if tags else ""
