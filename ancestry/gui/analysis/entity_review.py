"""Entity-Kandidaten Review — bestätigt oder lehnt entity_candidates ab."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk


def open_entity_review(parent, db) -> None:
    """Öffnet das Entity-Kandidaten-Review-Fenster."""
    win = tk.Toplevel(parent)
    win.title("🔗 Entity-Kandidaten Review")
    win.geometry("1100x620")

    # Kopfzeile
    top = ttk.Frame(win)
    top.pack(fill="x", padx=10, pady=(8, 4))
    count_var = tk.StringVar(value="Wird geladen …")
    ttk.Label(top, textvariable=count_var,
              font=("Segoe UI", 9, "bold")).pack(side="left")
    ttk.Label(top, text="  Filter:").pack(side="left", padx=(12, 2))
    filter_var = tk.StringVar(value="pending")
    ttk.Combobox(
        top, textvariable=filter_var,
        values=["pending", "confirmed", "rejected", "alle"],
        width=10, state="readonly").pack(side="left")
    reload_btn = ttk.Button(top, text="↺ Neu laden")
    reload_btn.pack(side="left", padx=6)
    ttk.Label(top,
        text="Konfidenz ≥", foreground="#666").pack(side="left", padx=(12, 2))
    min_conf_var = tk.StringVar(value="0.0")
    ttk.Entry(top, textvariable=min_conf_var, width=5).pack(side="left")

    # Treeview
    cols = ("conf", "src_a", "name_a", "role_a", "src_b", "name_b", "role_b", "ev_type")
    frm = ttk.Frame(win)
    frm.pack(fill="both", expand=True, padx=10)
    tv = ttk.Treeview(frm, columns=cols, show="headings", selectmode="browse")
    for col, lbl, w in [
        ("conf",    "Konfidenz",    68),
        ("src_a",   "Quelle A",    110),
        ("name_a",  "Person A",    190),
        ("role_a",  "Rolle A",      80),
        ("src_b",   "Quelle B",    110),
        ("name_b",  "Person B",    190),
        ("role_b",  "Rolle B",      80),
        ("ev_type", "Evidenz-Typ", 120),
    ]:
        tv.heading(col, text=lbl)
        tv.column(col, width=w, anchor="center" if col == "conf" else "w")
    tv.tag_configure("confirmed", foreground="#2da44e")
    tv.tag_configure("rejected",  foreground="#aaaaaa")
    vsb = ttk.Scrollbar(frm, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    tv.pack(fill="both", expand=True)

    # Evidenz-Details
    detail_var = tk.StringVar(value="")
    ttk.Label(win, textvariable=detail_var,
              font=("Segoe UI", 8), foreground="#555",
              wraplength=1060).pack(fill="x", padx=10, pady=(4, 2))

    # Aktions-Leiste
    btn_bar = ttk.Frame(win)
    btn_bar.pack(fill="x", padx=10, pady=(0, 10))
    conf_btn = ttk.Button(btn_bar, text="✓ Bestätigen")
    conf_btn.pack(side="left", padx=(0, 4))
    rej_btn = ttk.Button(btn_bar, text="✗ Ablehnen")
    rej_btn.pack(side="left", padx=4)
    skip_btn = ttk.Button(btn_bar, text="→ Nächster")
    skip_btn.pack(side="left", padx=4)

    _rows: list[dict] = []

    def _load(*_) -> None:
        status = filter_var.get()
        try:
            min_c = float(min_conf_var.get())
        except ValueError:
            min_c = 0.0
        where = (f"WHERE status='{status}'" if status != "alle" else "WHERE 1=1")
        try:
            with db._cursor() as cur:
                rows = cur.execute(f"""
                    SELECT candidate_id, source_table_a, source_row_id_a, person_role_a,
                           source_table_b, source_row_id_b, person_role_b,
                           confidence, evidence, status
                    FROM entity_candidates {where}
                      AND confidence >= ?
                    ORDER BY confidence DESC
                    LIMIT 500
                """, (min_c,)).fetchall()
        except Exception as exc:
            count_var.set(f"Fehler: {exc}")
            return
        _rows.clear()
        tv.delete(*tv.get_children())
        for r in rows:
            row = dict(r)
            _rows.append(row)
            ev: dict = {}
            try:
                ev = json.loads(r["evidence"] or "{}")
            except Exception:
                pass
            name_a = (ev.get("wt_name") or ev.get("match_name") or
                      str(r["source_row_id_a"]))
            name_b = (ev.get("mat_name") or ev.get("ner_name") or
                      ev.get("anv_name") or str(r["source_row_id_b"]))
            ev_type = ev.get("type", "")
            tag = r["status"] if r["status"] in ("confirmed", "rejected") else ""
            tv.insert("", "end", iid=str(r["candidate_id"]),
                      tags=(tag,) if tag else (),
                      values=(f"{r['confidence']:.2f}",
                              r["source_table_a"], name_a, r["person_role_a"],
                              r["source_table_b"], name_b, r["person_role_b"],
                              ev_type))
        count_var.set(f"{len(_rows)} Kandidaten · Filter: {status}, conf ≥ {min_c:.2f}")

    def _get_cid() -> int | None:
        sel = tv.selection()
        return int(sel[0]) if sel else None

    def _on_select(_=None) -> None:
        cid = _get_cid()
        if cid is None:
            return
        row = next((r for r in _rows if r["candidate_id"] == cid), None)
        if not row:
            return
        ev: dict = {}
        try:
            ev = json.loads(row["evidence"] or "{}")
        except Exception:
            pass
        detail_var.set(
            f"ID {cid}  ·  "
            f"{row['source_table_a']}/{row['source_row_id_a']} [{row['person_role_a']}]"
            f"  ↔  "
            f"{row['source_table_b']}/{row['source_row_id_b']} [{row['person_role_b']}]"
            f"  ·  {json.dumps(ev, ensure_ascii=False)[:240]}")

    def _move_next() -> None:
        items = tv.get_children()
        sel = tv.selection()
        if sel and sel[0] in items:
            idx = list(items).index(sel[0])
            nxt = idx + 1
            if nxt < len(items):
                tv.selection_set(items[nxt])
                tv.see(items[nxt])
        elif items:
            tv.selection_set(items[0])

    def _set_status(status: str) -> None:
        cid = _get_cid()
        if cid is None:
            return
        try:
            with db._cursor() as cur:
                cur.execute(
                    "UPDATE entity_candidates SET status=?, reviewed_at=datetime('now') "
                    "WHERE candidate_id=?",
                    (status, cid))
        except Exception as exc:
            messagebox.showerror("Fehler", str(exc))
            return
        _rows[:] = [r for r in _rows if r["candidate_id"] != cid]
        items = tv.get_children()
        idx = list(items).index(str(cid)) if str(cid) in items else 0
        tv.delete(str(cid))
        remaining = tv.get_children()
        if remaining:
            nxt_idx = min(idx, len(remaining) - 1)
            tv.selection_set(remaining[nxt_idx])
            tv.see(remaining[nxt_idx])
        count_var.set(f"{len(_rows)} Kandidaten übrig")

    tv.bind("<<TreeviewSelect>>", _on_select)
    conf_btn.configure(command=lambda: _set_status("confirmed"))
    rej_btn.configure(command=lambda: _set_status("rejected"))
    skip_btn.configure(command=_move_next)
    reload_btn.configure(command=_load)
    filter_var.trace_add("write", lambda *_: _load())

    _load()
