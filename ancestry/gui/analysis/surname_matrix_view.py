"""surname_matrix_view.py – Nachnamen-Ähnlichkeits-Matrix dialog.

Opens a Toplevel window showing Jaccard similarity between DNA matches based
on the surnames found in their pedigree trees.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ancestry.core.surname_matrix import compute_surname_pairs
from ancestry.gui.widgets.theme import resolve_t

_MAX_PAIRS = 2_000
_MAX_COMMON_SHOWN = 5


def show_surname_matrix(app) -> None:
    """Open the surname similarity matrix dialog."""
    _t = resolve_t(app)

    # ── guard: need an active kit ────────────────────────────────────────────
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning(_t("dlg.no_kit"), _t("dlg.m_choose_kit"))
        return
    if app._db is None:
        messagebox.showerror(_t("sm.title"), _t("sm.no_data"))
        return

    # ── window ───────────────────────────────────────────────────────────────
    win = tk.Toplevel(app)
    win.title(_t("sm.title"))
    win.geometry("1020x640")

    # ── top controls ─────────────────────────────────────────────────────────
    top = ttk.Frame(win)
    top.pack(fill="x", padx=10, pady=(10, 4))

    ttk.Label(top, text=_t("sm.min_cm")).pack(side="left")
    min_cm_var = tk.StringVar(value="0")
    ttk.Entry(top, textvariable=min_cm_var, width=6).pack(side="left", padx=(2, 10))

    ttk.Label(top, text=_t("sm.min_score")).pack(side="left")
    min_score_var = tk.StringVar(value="0.05")
    ttk.Entry(top, textvariable=min_score_var, width=6).pack(side="left", padx=(2, 10))

    calc_btn = ttk.Button(top, text=_t("sm.calc"))
    calc_btn.pack(side="left", padx=(4, 0))

    # ── treeview ─────────────────────────────────────────────────────────────
    cols = ("match_a", "match_b", "count", "score", "common")
    col_cfg = {
        "match_a": (_t("sm.match_a"), 180, "w"),
        "match_b": (_t("sm.match_b"), 180, "w"),
        "count":   (_t("sm.count"),    60, "center"),
        "score":   (_t("sm.score"),    70, "center"),
        "common":  (_t("sm.common"),  350, "w"),
    }

    frm = ttk.Frame(win)
    frm.pack(fill="both", expand=True, padx=10, pady=(0, 4))

    tv = ttk.Treeview(frm, columns=cols, show="headings", selectmode="browse")
    for col in cols:
        label, width, anchor = col_cfg[col]
        tv.heading(col, text=label,
                   command=lambda c=col: _sort_column(tv, c, False))
        tv.column(col, width=width, anchor=anchor, stretch=(col == "common"))

    vsb = ttk.Scrollbar(frm, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    tv.pack(fill="both", expand=True)

    # ── status bar ───────────────────────────────────────────────────────────
    status_var = tk.StringVar(value="")
    status_lbl = ttk.Label(win, textvariable=status_var, anchor="w")
    status_lbl.pack(fill="x", padx=10, pady=(0, 6))

    # ── column sort helper ────────────────────────────────────────────────────
    def _sort_column(tree: ttk.Treeview, col: str, reverse: bool) -> None:
        data = [(tree.set(child, col), child) for child in tree.get_children("")]
        try:
            data.sort(key=lambda t: float(t[0]), reverse=reverse)
        except ValueError:
            data.sort(key=lambda t: t[0].lower(), reverse=reverse)
        for idx, (_, child) in enumerate(data):
            tree.move(child, "", idx)
        tree.heading(col, command=lambda: _sort_column(tree, col, not reverse))

    # ── calculation ───────────────────────────────────────────────────────────
    def _calculate() -> None:
        calc_btn.state(["disabled"])
        status_var.set(_t("sm.computing"))
        win.update_idletasks()

        try:
            try:
                min_cm = float(min_cm_var.get())
            except ValueError:
                min_cm = 0.0
            try:
                min_score = float(min_score_var.get())
            except ValueError:
                min_score = 0.05

            # Step 1: get matches with optional cM filter
            matches = app._db.get_matches(test_guid, min_cm=min_cm, limit=0)
            valid_guids = {m.match_guid for m in matches}
            match_names = {m.match_guid: m.display_name for m in matches}

            # Step 2: get all surname groups
            groups = app._db.get_pedigree_groups(
                test_guid, min_matches=1, mode="surname"
            )

            # Step 3: build match → surname mapping
            # groups[i]["matches"] is a list of tuples:
            # (match_guid, display_name, ahnen_path, generation, shared_cm)
            match_to_surnames: dict[str, frozenset[str]] = {}
            for group in groups:
                sur = group["label"].lower().strip()
                for entry in group["matches"]:
                    # entry is a tuple: (match_guid, display_name, ...)
                    g = entry[0]
                    if g not in valid_guids:
                        continue
                    if g not in match_to_surnames:
                        match_to_surnames[g] = frozenset()
                    match_to_surnames[g] = match_to_surnames[g] | {sur}

            # Step 4: compute pairs
            pairs = compute_surname_pairs(match_to_surnames, min_score=min_score)

            # Step 5: populate treeview
            for child in tv.get_children():
                tv.delete(child)

            shown = 0
            for p in pairs[:_MAX_PAIRS]:
                g_a = p["guid_a"]
                g_b = p["guid_b"]
                name_a = match_names.get(g_a, g_a)
                name_b = match_names.get(g_b, g_b)
                common = p["common"]
                if len(common) > _MAX_COMMON_SHOWN:
                    common_str = ", ".join(common[:_MAX_COMMON_SHOWN]) + " …"
                else:
                    common_str = ", ".join(common)
                tv.insert("", "end", values=(
                    name_a,
                    name_b,
                    p["count"],
                    f"{p['score']:.4f}",
                    common_str,
                ))
                shown += 1

            n_matches = len(match_to_surnames)
            status_var.set(
                _t("sm.pairs")
                .format(n=shown, m=n_matches)
            )

        except Exception as exc:  # noqa: BLE001
            status_var.set(str(exc))
        finally:
            calc_btn.state(["!disabled"])

    calc_btn.configure(command=_calculate)
