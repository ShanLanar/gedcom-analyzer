"""DNA-Segment-Ansichten: X-DNA- und IBD2-Matches (Sprint 9 GUI-Anbindung).

Macht die in Sprint 7 ergänzten Segment-Analysen sichtbar:
  * X-DNA-Matches  (get_x_dna_matches) — X folgt eigenem Erbgang, grenzt Linien ein
  * IBD2-Matches   (get_ibd2_matches)  — fully identical regions ⇒ Vollgeschwister
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


def _name_map(db, test_guid: str, guids: set[str]) -> dict[str, str]:
    """match_guid → Anzeigename (nur für die tatsächlich vorkommenden GUIDs)."""
    if not guids:
        return {}
    out: dict[str, str] = {}
    try:
        guid_list = list(guids)
        with db._cursor() as cur:
            for start in range(0, len(guid_list), 900):
                chunk = guid_list[start:start + 900]
                ph = ",".join("?" * len(chunk))
                for r in cur.execute(
                    f"SELECT match_guid, display_name FROM matches "
                    f"WHERE match_guid IN ({ph})", chunk
                ).fetchall():
                    out[r[0]] = r[1] or ""
    except Exception:
        pass
    return out


def show_dna_segments(parent, db, test_guid, *, set_status=None) -> None:
    """Fenster mit zwei Listen: X-DNA-Matches und IBD2-Matches für test_guid."""
    if not test_guid:
        messagebox.showinfo("DNA-Segmente",
                            "Kein Kit ausgewählt. Bitte zuerst ein Kit wählen.")
        return

    try:
        x_rows = db.get_x_dna_matches(test_guid)
        ibd2_rows = db.get_ibd2_matches(test_guid)
    except Exception as exc:
        messagebox.showerror("DNA-Segmente", f"Fehler beim Laden: {exc}")
        return

    guids = {r["match_guid"] for r in x_rows} | {r["match_guid"] for r in ibd2_rows}
    names = _name_map(db, test_guid, guids)

    win = tk.Toplevel(parent)
    win.title("DNA-Segmente – X-DNA & IBD2")
    win.geometry("720x560")

    ttk.Label(win, text="🧬 X-DNA & IBD2",
              font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 0))

    if not x_rows and not ibd2_rows:
        ttk.Label(
            win,
            text=("Keine X-/IBD2-Segmente gefunden.\n\n"
                  "Diese Analysen brauchen importierte Segmentdaten "
                  "(GEDmatch/MyHeritage/FTDNA).\n"
                  "Ancestry liefert keine Segmentpositionen — bitte Segment-CSV "
                  "importieren (Werkzeuge → Segment-Import)."),
            foreground="#777777", justify="left", wraplength=660,
        ).pack(anchor="w", padx=14, pady=16)
        if set_status:
            set_status("DNA-Segmente: keine Daten (Segment-Import nötig).")
        return

    # ── X-DNA ─────────────────────────────────────────────────────────────────
    x_frame = ttk.LabelFrame(
        win, text="X-DNA-Matches (Chromosom 23 – nur mütterliche Linien bei Männern)",
        padding=6)
    x_frame.pack(fill="both", expand=True, padx=12, pady=(8, 4))
    x_cols = ("name", "x_cm", "x_segments", "longest")
    x_tv = ttk.Treeview(x_frame, columns=x_cols, show="headings", height=8)
    for col, lbl, w in [("name", "Match", 300), ("x_cm", "X-cM gesamt", 100),
                        ("x_segments", "Segmente", 80), ("longest", "längstes cM", 100)]:
        x_tv.heading(col, text=lbl)
        x_tv.column(col, width=w, anchor="w" if col == "name" else "center")
    for r in x_rows:
        x_tv.insert("", "end", values=(
            names.get(r["match_guid"], r["match_guid"]),
            f"{r['x_cm']:.1f}", r["x_segments"], f"{r['longest_x_cm']:.1f}"))
    x_tv.pack(fill="both", expand=True)

    # ── IBD2 ──────────────────────────────────────────────────────────────────
    ibd2_frame = ttk.LabelFrame(
        win, text="IBD2 – fully identical regions (starkes Vollgeschwister-Signal)",
        padding=6)
    ibd2_frame.pack(fill="both", expand=True, padx=12, pady=(4, 10))
    i_cols = ("name", "ibd2_cm", "ibd2_segments")
    i_tv = ttk.Treeview(ibd2_frame, columns=i_cols, show="headings", height=6)
    for col, lbl, w in [("name", "Match", 340), ("ibd2_cm", "IBD2-cM", 120),
                        ("ibd2_segments", "Segmente", 100)]:
        i_tv.heading(col, text=lbl)
        i_tv.column(col, width=w, anchor="w" if col == "name" else "center")
    if ibd2_rows:
        for r in ibd2_rows:
            i_tv.insert("", "end", values=(
                names.get(r["match_guid"], r["match_guid"]),
                f"{r['ibd2_cm']:.1f}", r["ibd2_segments"]))
    else:
        i_tv.insert("", "end", values=(
            "(keine IBD2-Segmente – Standard-CSV enthält keine FIR-Daten)", "", ""))
    i_tv.pack(fill="both", expand=True)

    # ── X-Ahnen-Fächer (echte Linien-Eingrenzung, braucht Testergeschlecht) ────
    xa_frame = ttk.LabelFrame(
        win, text="X-Ahnen-Fächer – aus welchen Linien X-DNA stammen KANN", padding=6)
    xa_frame.pack(fill="both", expand=True, padx=12, pady=(4, 10))
    ctl = ttk.Frame(xa_frame)
    ctl.pack(fill="x")
    ttk.Label(ctl, text="Geschlecht der Testperson:").pack(side="left")
    sex_var = tk.StringVar(value="männlich")
    ttk.Combobox(ctl, textvariable=sex_var, width=12, state="readonly",
                 values=["männlich", "weiblich"]).pack(side="left", padx=(4, 8))
    info_var = tk.StringVar(value="")
    ttk.Label(xa_frame, textvariable=info_var, foreground="#555566",
              wraplength=660, justify="left").pack(anchor="w", pady=(4, 2))

    xa_tv = ttk.Treeview(xa_frame, columns=("sosa", "gen", "name", "yr"),
                         show="headings", height=6)
    for col, lbl, w in [("sosa", "Sosa", 60), ("gen", "Gen", 45),
                        ("name", "Ahn", 320), ("yr", "geb.", 70)]:
        xa_tv.heading(col, text=lbl)
        xa_tv.column(col, width=w, anchor="w" if col == "name" else "center")
    xa_tv.pack(fill="both", expand=True, pady=(2, 0))

    def _refresh_x_fan(*_):
        from ancestry.core.x_inheritance import x_ancestor_count_per_gen
        sex = sex_var.get()
        counts = x_ancestor_count_per_gen(sex, 6)
        try:
            ancestors = db.get_x_ancestors(sex)
        except Exception:
            ancestors = []
        info_var.set(
            "X-Ahnen je Generation (Gen 2–6): "
            + ", ".join(str(c) for c in counts[1:])
            + f"  ·  im Stammbaum X-relevant: {len(ancestors)}"
            + ("" if ancestors else
               "  (keine Sosa-Nummern — GEDCOM mit Root/Familien laden)"))
        xa_tv.delete(*xa_tv.get_children())
        for a in ancestors:
            xa_tv.insert("", "end", values=(
                a["sosa"], a["generation"], a["name"] or "?", a["birth_year"] or ""))

    sex_var.trace_add("write", _refresh_x_fan)
    _refresh_x_fan()

    if set_status:
        set_status(f"DNA-Segmente: {len(x_rows)} X-Matches, {len(ibd2_rows)} IBD2.")
