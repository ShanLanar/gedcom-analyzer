"""
ancestry/gui/analysis/population.py — Bevölkerungsstatistik-Popup.

Vier Tabs:
  1. Geburtsverteilung  — Personen/Jahrzehnt × Region (Balken + Tabelle)
  2. Migration          — Eltern→Kind-Regionsflüsse (Tabelle mit Balkenanzeige)
  3. cM-Verteilung      — Histogramm geteilter cM (Balken + Verwandtschaftshinweis)
  4. Nachnamen-Entropie — Shannon-Diversität pro Jahrzehnt (Linienchart + Tabelle)
"""
from __future__ import annotations

import logging
import tkinter as tk
from collections import defaultdict
from tkinter import ttk

log = logging.getLogger(__name__)

_PALETTE = [
    "#1a73e8", "#e8711a", "#2da44e", "#a832a8", "#e81a4b",
    "#1ab8e8", "#8e8e00", "#e8a81a", "#888", "#444",
]


# ── Canvas-Hilfsroutinen ──────────────────────────────────────────────────────

def _bar_chart(canvas: tk.Canvas, bars: list[tuple[str, float]],
               title: str = "", colors: list[str] | None = None) -> None:
    """Einfaches Balkendiagramm auf einem Canvas."""
    canvas.delete("all")
    W = canvas.winfo_width() or 800
    H = canvas.winfo_height() or 260
    if not bars:
        canvas.create_text(W // 2, H // 2, text="Keine Daten", fill="#888",
                           font=("Segoe UI", 10))
        return

    ml, mr, mt, mb = 62, 14, 28, 44
    dw, dh = W - ml - mr, H - mt - mb
    max_v = max(v for _, v in bars) or 1
    n = len(bars)
    gap = max(1, dw // n // 8)
    bw = max(2, dw // n - gap)

    if title:
        canvas.create_text(W // 2, 12, text=title, font=("Segoe UI", 9, "bold"),
                           fill="#333")

    # y-Gitterlinien
    for pct in (0.25, 0.5, 0.75, 1.0):
        y = mt + dh - int(dh * pct)
        canvas.create_line(ml, y, W - mr, y, fill="#e8e8e8", dash=(4, 4))
        canvas.create_text(ml - 4, y, text=f"{int(max_v * pct):,}",
                           anchor="e", font=("Segoe UI", 7), fill="#666")

    # Achsen
    canvas.create_line(ml, mt, ml, mt + dh, fill="#bbb")
    canvas.create_line(ml, mt + dh, W - mr, mt + dh, fill="#bbb")

    for i, (label, val) in enumerate(bars):
        x0 = ml + i * (dw // n) + gap
        bh = max(1, int(dh * val / max_v))
        y1 = mt + dh
        y0 = y1 - bh
        col = (colors[i % len(colors)] if colors else _PALETTE[i % len(_PALETTE)])
        canvas.create_rectangle(x0, y0, x0 + bw, y1, fill=col, outline="")
        if bh > 14:
            canvas.create_text(x0 + bw // 2, y0 - 2, text=f"{int(val):,}",
                               anchor="s", font=("Segoe UI", 7), fill="#333")
        # x-Label (schräg wenn viele)
        angle = 40 if n > 12 else 0
        canvas.create_text(x0 + bw // 2, y1 + 4, text=label,
                           anchor="n", font=("Segoe UI", 7), fill="#555",
                           angle=angle)


def _line_chart(canvas: tk.Canvas, series: list[tuple[float, float]],
                title: str = "", y_fmt: str = "{:.1f}",
                color: str = "#1a73e8") -> None:
    """Einfaches Liniendiagramm auf einem Canvas."""
    canvas.delete("all")
    W = canvas.winfo_width() or 800
    H = canvas.winfo_height() or 260
    if len(series) < 2:
        canvas.create_text(W // 2, H // 2, text="Zu wenig Daten", fill="#888",
                           font=("Segoe UI", 10))
        return

    ml, mr, mt, mb = 62, 14, 28, 44
    dw, dh = W - ml - mr, H - mt - mb

    xs = [p[0] for p in series]
    ys = [p[1] for p in series]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x == min_x:
        return
    pad = (max_y - min_y) * 0.08 or 0.5
    min_y -= pad
    max_y += pad

    if title:
        canvas.create_text(W // 2, 12, text=title, font=("Segoe UI", 9, "bold"),
                           fill="#333")

    def tx(x): return ml + int(dw * (x - min_x) / (max_x - min_x))
    def ty(y): return mt + dh - int(dh * (y - min_y) / (max_y - min_y))

    # Gitter + y-Achsen-Labels
    for pct in (0, 0.25, 0.5, 0.75, 1.0):
        yv = min_y + (max_y - min_y) * pct
        yp = ty(yv)
        canvas.create_line(ml, yp, W - mr, yp, fill="#e8e8e8", dash=(4, 4))
        canvas.create_text(ml - 4, yp, text=y_fmt.format(yv),
                           anchor="e", font=("Segoe UI", 7), fill="#666")

    # Achsen
    canvas.create_line(ml, mt, ml, mt + dh, fill="#bbb")
    canvas.create_line(ml, mt + dh, W - mr, mt + dh, fill="#bbb")

    # x-Labels (ca. 8 gleichmäßig)
    step = max(1, len(series) // 8)
    for i, (x, _) in enumerate(series):
        if i % step == 0 or i == len(series) - 1:
            canvas.create_text(tx(x), mt + dh + 4, text=str(int(x)),
                               anchor="n", font=("Segoe UI", 7), fill="#555")

    # Linie + Punkte
    coords = [(tx(x), ty(y)) for x, y in series]
    for i in range(len(coords) - 1):
        canvas.create_line(*coords[i], *coords[i + 1], fill=color, width=2)
    for cx, cy in coords:
        canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                           fill=color, outline="white", width=1)


# ── Haupt-Einstiegspunkt ──────────────────────────────────────────────────────

def show_population_stats(app) -> None:
    """Öffnet das Bevölkerungsstatistik-Popup."""
    from tkinter import messagebox
    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return

    win = tk.Toplevel(app)
    win.title("Bevölkerungsstatistiken")
    win.geometry("1000x660")

    nb = ttk.Notebook(win)
    nb.pack(fill="both", expand=True, padx=6, pady=6)

    _build_birth_tab(nb, app)
    _build_migration_tab(nb, app)
    _build_cm_tab(nb, app, test_guid)
    _build_entropy_tab(nb, app)


# ── Tab 1: Geburtsverteilung ──────────────────────────────────────────────────

def _build_birth_tab(nb: ttk.Notebook, app) -> None:
    from ancestry.core.population_stats import birth_distribution

    frame = ttk.Frame(nb)
    nb.add(frame, text="Geburtsverteilung")

    info = ttk.Label(frame, text="Lädt …", style="Bold.TLabel")
    info.pack(anchor="w", padx=10, pady=(6, 2))

    # Oberer Bereich: Canvas-Chart (Gesamt pro Jahrzehnt)
    canvas = tk.Canvas(frame, bg="#f8f8f8", height=220,
                       highlightthickness=1, highlightbackground="#ddd")
    canvas.pack(fill="x", padx=8, pady=4)

    # Unterer Bereich: Treeview Jahrzehnt × Region
    tf = ttk.Frame(frame)
    tf.pack(fill="both", expand=True, padx=8, pady=(0, 6))
    cols = ("decade", "region", "count")
    tv = ttk.Treeview(tf, columns=cols, show="headings", height=8)
    for col, lbl, w in [("decade", "Jahrzehnt", 90), ("region", "Region", 280),
                        ("count", "Personen", 90)]:
        tv.heading(col, text=lbl,
                   command=lambda c=col: _sort_tv(tv, c, c == "count"))
        tv.column(col, width=w, anchor="center" if col != "region" else "w")
    sb = ttk.Scrollbar(tf, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def _load():
        rows = birth_distribution(app._db)
        if not rows:
            info.configure(text="Keine Daten – GEDCOM oder Match-Ahnentafeln laden.")
            return

        total = sum(r["count"] for r in rows)
        regions = sorted({r["region"] for r in rows})
        decades = sorted({r["decade"] for r in rows})
        info.configure(text=(
            f"{total:,} Personen · {len(decades)} Jahrzehnte · "
            f"{len(regions)} Regionen"))

        # Gesamt pro Jahrzehnt für den Chart
        decade_total: dict[int, int] = defaultdict(int)
        for r in rows:
            decade_total[r["decade"]] += r["count"]
        series = [(d, decade_total[d]) for d in sorted(decade_total)]
        bars = [(str(d), v) for d, v in series]
        frame.after(60, lambda: _bar_chart(canvas, bars,
                                           "Personen pro Jahrzehnt (alle Quellen)",
                                           colors=["#1a73e8"] * len(bars)))

        tv.delete(*tv.get_children())
        for r in rows:
            tv.insert("", "end", values=(r["decade"], r["region"], f"{r['count']:,}"))

    frame.after(100, _load)


# ── Tab 2: Migration ──────────────────────────────────────────────────────────

def _build_migration_tab(nb: ttk.Notebook, app) -> None:
    from ancestry.core.population_stats import migration_matrix

    frame = ttk.Frame(nb)
    nb.add(frame, text="Migration")

    info = ttk.Label(frame, text="Lädt …", style="Bold.TLabel")
    info.pack(anchor="w", padx=10, pady=(6, 2))

    ttk.Label(frame,
              text="Elternregion → Kindregion: wo sind die Kinder im Vergleich zu den Eltern geboren?",
              font=("Segoe UI", 8), foreground="#666").pack(anchor="w", padx=10)

    tf = ttk.Frame(frame)
    tf.pack(fill="both", expand=True, padx=8, pady=6)

    cols = ("from_r", "to_r", "count", "bar")
    tv = ttk.Treeview(tf, columns=cols, show="headings")
    for col, lbl, w, anc in [
        ("from_r", "Von (Elternregion)", 240, "w"),
        ("to_r",   "Nach (Kindregion)",  240, "w"),
        ("count",  "Anzahl",              80, "center"),
        ("bar",    "",                   220, "w"),
    ]:
        tv.heading(col, text=lbl,
                   command=lambda c=col: _sort_tv(tv, c, c == "count"))
        tv.column(col, width=w, anchor=anc)
    sb = ttk.Scrollbar(tf, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def _load():
        rows = migration_matrix(app._db)
        if not rows:
            info.configure(text="Keine Migrations-Daten – Ahnentafeln und GEDCOM laden.")
            return
        total_flows = sum(r["count"] for r in rows)
        info.configure(text=(
            f"{len(rows)} Wanderungspfade · {total_flows:,} Eltern-Kind-Paare"))
        max_cnt = rows[0]["count"] if rows else 1
        tv.delete(*tv.get_children())
        for r in rows:
            bar_len = int(30 * r["count"] / max_cnt)
            bar = "█" * bar_len
            tv.insert("", "end", values=(
                r["from_region"], r["to_region"], f"{r['count']:,}", bar))

    frame.after(100, _load)


# ── Tab 3: cM-Verteilung ──────────────────────────────────────────────────────

def _build_cm_tab(nb: ttk.Notebook, app, test_guid: str) -> None:
    from ancestry.core.population_stats import cm_histogram

    frame = ttk.Frame(nb)
    nb.add(frame, text="cM-Verteilung")

    info = ttk.Label(frame, text="Lädt …", style="Bold.TLabel")
    info.pack(anchor="w", padx=10, pady=(6, 2))

    ttk.Label(frame,
              text="Häufigkeit der geteilten cM über alle Matches — "
                   "Spitze links = viele entfernte Cousins, Ausreißer rechts = nahe Verwandte.",
              font=("Segoe UI", 8), foreground="#666",
              wraplength=940, justify="left").pack(anchor="w", padx=10)

    canvas = tk.Canvas(frame, bg="#f8f8f8", height=280,
                       highlightthickness=1, highlightbackground="#ddd")
    canvas.pack(fill="x", padx=8, pady=4)

    # Detailtabelle
    tf = ttk.Frame(frame)
    tf.pack(fill="both", expand=True, padx=8, pady=(0, 6))
    cols = ("range", "observed", "rel")
    tv = ttk.Treeview(tf, columns=cols, show="headings", height=5)
    for col, lbl, w in [("range", "cM-Bereich", 120), ("observed", "Matches", 90),
                        ("rel", "Ungefähre Verwandtschaft", 300)]:
        tv.heading(col, text=lbl)
        tv.column(col, width=w, anchor="center" if col == "observed" else "w")
    sb = ttk.Scrollbar(tf, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def _load():
        rows = cm_histogram(app._db, test_guid)
        if not rows:
            info.configure(text="Keine Matches gefunden.")
            return
        total = sum(r["observed"] for r in rows)
        max_cm_val = max(
            (r["bin_hi"] for r in rows if r["observed"] > 0), default=0)
        mean_approx = sum(
            (r["bin_lo"] + r["bin_hi"]) / 2 * r["observed"]
            for r in rows if r["bin_hi"] < 4000
        ) / max(1, sum(r["observed"] for r in rows if r["bin_hi"] < 4000))
        info.configure(text=(
            f"{total:,} Matches · Ø ≈ {mean_approx:.0f} cM · "
            f"größter Bin bis {max_cm_val} cM"))

        bars = [(r["label"], r["observed"]) for r in rows]
        # Gradient: kleine cM hellblau, große cM dunkelblau
        clrs = [f"#{max(30, 26 - i*2):02x}{max(30, 115 - i*10):02x}{max(80, 232 - i*15):02x}"
                for i in range(len(bars))]
        frame.after(50, lambda: _bar_chart(canvas, bars,
                                           "Matches nach geteilten cM",
                                           colors=clrs))

        tv.delete(*tv.get_children())
        for r in rows:
            pct = r["observed"] / total * 100 if total else 0
            tv.insert("", "end", values=(
                r["label"],
                f"{r['observed']:,} ({pct:.1f}%)",
                r["rel_hint"]))

    frame.after(100, _load)


# ── Tab 4: Nachnamen-Entropie ─────────────────────────────────────────────────

def _build_entropy_tab(nb: ttk.Notebook, app) -> None:
    from ancestry.core.population_stats import surname_entropy_series

    frame = ttk.Frame(nb)
    nb.add(frame, text="Nachnamen-Entropie")

    info = ttk.Label(frame, text="Lädt …", style="Bold.TLabel")
    info.pack(anchor="w", padx=10, pady=(6, 2))

    ttk.Label(frame,
              text="Shannon-Entropie der Nachnamen pro Jahrzehnt — "
                   "Einbrüche = Gründereffekt / Datenlücke, Anstieg = Zuzug / bessere Quellenabdeckung.",
              font=("Segoe UI", 8), foreground="#666",
              wraplength=940, justify="left").pack(anchor="w", padx=10)

    canvas = tk.Canvas(frame, bg="#f8f8f8", height=240,
                       highlightthickness=1, highlightbackground="#ddd")
    canvas.pack(fill="x", padx=8, pady=4)

    tf = ttk.Frame(frame)
    tf.pack(fill="both", expand=True, padx=8, pady=(0, 6))
    cols = ("decade", "entropy", "unique", "total")
    tv = ttk.Treeview(tf, columns=cols, show="headings", height=6)
    for col, lbl, w in [
        ("decade",  "Jahrzehnt",        90),
        ("entropy", "Entropie (bits)",  120),
        ("unique",  "Versch. Namen",    110),
        ("total",   "Personen",          90),
    ]:
        tv.heading(col, text=lbl,
                   command=lambda c=col: _sort_tv(tv, c, c in ("entropy", "unique", "total")))
        tv.column(col, width=w, anchor="center")
    sb = ttk.Scrollbar(tf, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    tv.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def _load():
        rows = surname_entropy_series(app._db)
        if not rows:
            info.configure(text="Keine Daten – GEDCOM oder Match-Ahnentafeln laden.")
            return
        min_e = min(r["entropy"] for r in rows)
        max_e = max(r["entropy"] for r in rows)
        total_persons = sum(r["total"] for r in rows)
        info.configure(text=(
            f"{len(rows)} Jahrzehnte · Entropie {min_e:.2f}–{max_e:.2f} bits · "
            f"{total_persons:,} Personen gesamt"))

        series = [(r["decade"], r["entropy"]) for r in rows]
        frame.after(50, lambda: _line_chart(
            canvas, series,
            title="Nachnamen-Entropie pro Jahrzehnt (Shannon H, bits)",
            y_fmt="{:.2f}", color="#2da44e"))

        tv.delete(*tv.get_children())
        for r in rows:
            tv.insert("", "end", values=(
                r["decade"], f"{r['entropy']:.3f}", f"{r['unique']:,}", f"{r['total']:,}"))

    frame.after(100, _load)


# ── Tabellen-Sortierhilfe ─────────────────────────────────────────────────────

def _sort_tv(tv: ttk.Treeview, col: str, numeric: bool) -> None:
    """Sortiert ein Treeview nach Spalte (toggle asc/desc)."""
    items = [(tv.set(iid, col), iid) for iid in tv.get_children("")]
    reverse = getattr(tv, f"_sort_desc_{col}", False)
    if numeric:
        try:
            items.sort(key=lambda x: float(x[0].replace(",", "").split()[0]),
                       reverse=reverse)
        except (ValueError, IndexError):
            items.sort(reverse=reverse)
    else:
        items.sort(reverse=reverse)
    for i, (_, iid) in enumerate(items):
        tv.move(iid, "", i)
    setattr(tv, f"_sort_desc_{col}", not reverse)
