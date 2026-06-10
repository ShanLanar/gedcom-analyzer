"""
research_dashboard.py — Gamifiziertes Forschungs-Dashboard.

Zeigt vier Dinge auf einen Blick:
  1. Gesamtfortschritts-Score (0–100 %) + Forscher-Level
  2. Fortschrittsbalken für 5 Dimensionen (Cluster, Ahnentafel, Herkunft, Ahnen, Quellen)
  3. Freigeschaltete Achievements (Badges — grün = erreicht, grau = noch nicht)
  4. Nächste Schritte (regelbasiert + optionale KI-Empfehlung via Claude)
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import scrolledtext, ttk

log = logging.getLogger(__name__)

# ── Achievements ──────────────────────────────────────────────────────────────
# (key, emoji, kurztext, bedingung(stats)->bool)

ACHIEVEMENTS: list[tuple[str, str, str, object]] = [
    ("erste_matches",   "🧬", "Erste Matches",       lambda s: s["total"] > 0),
    ("tausend",         "🔱", "1.000+ Matches",        lambda s: s["total"] >= 1_000),
    ("fuenftausend",    "🏅", "5.000+ Matches",        lambda s: s["total"] >= 5_000),
    ("zehntausend",     "👑", "10.000+ Matches",       lambda s: s["total"] >= 10_000),
    ("cluster_calc",    "🌀", "Cluster berechnet",     lambda s: s["clusters"] > 0),
    ("cluster_meister", "🌪", "10+ Cluster",           lambda s: s["clusters"] >= 10),
    ("ahnentafeln",     "📜", "Ahnentafeln geladen",   lambda s: s["with_pedigree"] > 50),
    ("gedcom",          "🌳", "GEDCOM verbunden",      lambda s: s["gedcom_persons"] > 0),
    ("herkunft",        "🗺", "100+ mit Herkunft",     lambda s: s["with_origin"] >= 100),
    ("ml_pionier",      "🤖", "ML-Modell trainiert",  lambda s: s["ml_model_exists"]),
    ("kirchenbuch",     "⛪", "Kirchenbücher aktiv",   lambda s: s["matricula"] > 0),
    ("bevoelkerung",    "📊", "Bevölkerungsstat.",     lambda s: s["birth_dist"] > 100),
]

_LEVELS = [
    (90, "Meister-Genealoge"),
    (75, "Fortgeschrittener"),
    (50, "Aktiver Forscher"),
    (25, "Einsteiger"),
    (0,  "Am Anfang"),
]


# ── Daten sammeln ─────────────────────────────────────────────────────────────

def _gather(db, test_guid: str, app) -> dict:
    s: dict = {
        "total": 0, "clustered": 0, "with_pedigree": 0, "with_origin": 0,
        "gedcom_persons": 0, "sosa_filled": 0, "clusters": 0,
        "ml_model_exists": False, "matricula": 0, "birth_dist": 0,
    }

    def _q(sql: str, params: tuple = ()) -> int:
        try:
            with db._cursor() as cur:
                row = cur.execute(sql, params).fetchone()
                return int(row[0]) if row else 0
        except Exception as e:
            log.debug("dashboard query: %s", e)
            return 0

    s["total"]        = _q("SELECT COUNT(*) FROM matches WHERE test_guid=?", (test_guid,))
    s["with_pedigree"]= _q("SELECT COUNT(DISTINCT match_guid) FROM match_pedigree WHERE test_guid=?",
                            (test_guid,))
    s["with_origin"]  = _q("SELECT COUNT(*) FROM matches WHERE test_guid=? "
                            "AND probable_origin IS NOT NULL AND probable_origin != '' "
                            "AND probable_origin != 'null'", (test_guid,))
    s["gedcom_persons"]= _q("SELECT COUNT(*) FROM gedcom_persons")
    s["sosa_filled"]  = _q("SELECT COUNT(DISTINCT sosa_number) FROM gedcom_persons "
                            "WHERE sosa_number BETWEEN 1 AND 31")
    s["matricula"]    = _q("SELECT COUNT(*) FROM matricula_entries")  # graceful if missing

    clusters = getattr(app, "_clusters", {}) or {}
    s["clusters"]  = len(clusters)
    s["clustered"] = sum(len(v) for v in clusters.values())

    try:
        from ancestry.core.ml_origin import MODEL_PATH
        s["ml_model_exists"] = MODEL_PATH.exists()
    except Exception:
        pass

    try:
        from ancestry.core.population_stats import birth_distribution
        s["birth_dist"] = sum(r["count"] for r in birth_distribution(db, min_count=1))
    except Exception as e:
        log.debug("dashboard birth_dist: %s", e)

    return s


def _score(s: dict) -> tuple[int, str, dict[str, float]]:
    total = max(1, s["total"])
    dims: dict[str, float] = {
        "Cluster":        min(1.0, s["clustered"]    / total),
        "Ahnentafeln":    min(1.0, s["with_pedigree"]/ total),
        "Herkunft":       min(1.0, s["with_origin"]  / total),
        "Ahnen-Vollst.":  min(1.0, s["sosa_filled"]  / 31),
        "Quellenbreite":  min(1.0, sum([
            int(s["gedcom_persons"] > 0),
            int(s["ml_model_exists"]),
            int(s["matricula"] > 0),
            int(s["birth_dist"] > 0),
        ]) / 4),
    }
    weights = (0.25, 0.25, 0.20, 0.20, 0.10)
    pts = int(sum(v * w * 100 for v, w in zip(dims.values(), weights)))
    level = next(name for thresh, name in _LEVELS if pts >= thresh)
    return pts, level, dims


def _steps(s: dict) -> list[str]:
    total = max(1, s["total"])
    result = []
    if s["clustered"] / total < 0.5:
        result.append(f"🌀  Cluster berechnen — erst {s['clustered'] / total:.0%} geclustert")
    if s["with_pedigree"] / total < 0.6:
        result.append(f"📜  Ahnentafeln laden — {s['total'] - s['with_pedigree']:,} Matches ohne Pedigree")
    if s["with_origin"] / total < 0.4:
        result.append(f"🗺  Herkunfts-Inferenz starten — {s['with_origin'] / total:.0%} zugewiesen")
    if not s["ml_model_exists"] and s["gedcom_persons"] >= 1_000:
        result.append("🤖  ML-Modell trainieren (Auswertung → ML-Herkunft)")
    if s["sosa_filled"] < 20:
        result.append(f"🌳  GEDCOM ergänzen — nur {s['sosa_filled']}/31 direkte Vorfahren (Gen. 1–5)")
    if s["matricula"] == 0 and s["gedcom_persons"] > 0:
        result.append("⛪  Kirchenbücher scannen (Matricula-Tab) — noch kein Eintrag")
    if not result:
        result.append("✅  Exzellenter Forschungsstand — alle Hauptdimensionen gut abgedeckt!")
    return result[:3]


# ── Canvas-Hilfsfunktionen ────────────────────────────────────────────────────

def _bar_color(pct: float) -> str:
    if pct >= 0.70:
        return "#2da44e"
    if pct >= 0.40:
        return "#f5a623"
    return "#e8711a"


def _draw_score_bar(canvas: tk.Canvas, pts: int, level: str) -> None:
    canvas.delete("all")
    W = canvas.winfo_width() or 620
    H = canvas.winfo_height() or 56

    label_w = 160
    pct_w   = 52
    bx = label_w + 8
    bw = W - bx - pct_w - 12
    by, bh = H // 2 - 10, 20

    canvas.create_text(label_w - 4, H // 2, text=level,
                       anchor="e", font=("Segoe UI", 10, "bold"), fill="#444")
    canvas.create_rectangle(bx, by, bx + bw, by + bh, fill="#e0e0e0", outline="")
    fill = max(1, int(bw * pts / 100))
    col  = _bar_color(pts / 100)
    canvas.create_rectangle(bx, by, bx + fill, by + bh, fill=col, outline="")
    canvas.create_text(bx + bw + 8, H // 2,
                       text=f"{pts} %", anchor="w",
                       font=("Segoe UI", 11, "bold"), fill=col)


def _draw_dim_bar(canvas: tk.Canvas, pct: float) -> None:
    canvas.delete("all")
    W = canvas.winfo_width() or 300
    H = canvas.winfo_height() or 16
    canvas.create_rectangle(0, 0, W, H, fill="#e0e0e0", outline="")
    fw = max(1, int(W * pct))
    canvas.create_rectangle(0, 0, fw, H, fill=_bar_color(pct), outline="")
    canvas.create_text(W - 4, H // 2, text=f"{pct:.0%}",
                       anchor="e", font=("Segoe UI", 7, "bold"), fill="#fff" if pct > 0.15 else "#555")


# ── Hauptfenster ──────────────────────────────────────────────────────────────

def show_research_dashboard(app) -> None:
    """Öffnet das Forschungs-Dashboard-Popup."""
    import threading
    from tkinter import messagebox

    from ancestry.core.ai_copilot import (availability_hint, explain_async,
                                           gaps_prompt, is_available)

    test_guid = app._current_guid()
    if not test_guid:
        messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
        return
    db = app._db

    win = tk.Toplevel(app)
    win.title("🏅 Forschungs-Dashboard")
    win.geometry("700x660")
    win.resizable(True, True)

    # ── Score ─────────────────────────────────────────────────────────────────
    sf = ttk.LabelFrame(win, text="Gesamtfortschritt", padding=(10, 6))
    sf.pack(fill="x", padx=12, pady=(10, 4))
    score_canvas = tk.Canvas(sf, height=52, bg="#f8f8f8", highlightthickness=0)
    score_canvas.pack(fill="x")

    # ── Dimensionen ───────────────────────────────────────────────────────────
    df = ttk.LabelFrame(win, text="Fortschritt nach Dimension", padding=(10, 6))
    df.pack(fill="x", padx=12, pady=4)
    _dim_canvases: dict[str, tk.Canvas] = {}
    _dim_pct_vars: dict[str, tk.StringVar] = {}

    DIM_NAMES = ("Cluster", "Ahnentafeln", "Herkunft", "Ahnen-Vollst.", "Quellenbreite")
    for i, name in enumerate(DIM_NAMES):
        ttk.Label(df, text=name, width=15, anchor="e").grid(
            row=i, column=0, padx=(0, 8), pady=2, sticky="e")
        c = tk.Canvas(df, height=16, width=330, bg="#e0e0e0", highlightthickness=0)
        c.grid(row=i, column=1, padx=4, pady=2)
        _dim_canvases[name] = c
        sv = tk.StringVar(value="—")
        ttk.Label(df, textvariable=sv, font=("Segoe UI", 8, "bold"),
                  foreground="#555", width=6).grid(row=i, column=2, padx=2, sticky="w")
        _dim_pct_vars[name] = sv

    # ── Achievements ──────────────────────────────────────────────────────────
    af = ttk.LabelFrame(win, text="Erfolge", padding=(10, 6))
    af.pack(fill="x", padx=12, pady=4)
    _ach_widgets: dict[str, tk.Label] = {}
    for col_idx, (key, emoji, label, _) in enumerate(ACHIEVEMENTS):
        cell = tk.Frame(af, relief="groove", bd=1)
        cell.grid(row=col_idx // 6, column=col_idx % 6, padx=5, pady=4, ipadx=4, ipady=3)
        lbl = tk.Label(cell, text=f"{emoji}\n{label}",
                       font=("Segoe UI", 7), width=10, justify="center",
                       bg="#e8e8e8", fg="#aaa", wraplength=70)
        lbl.pack(fill="both", expand=True)
        _ach_widgets[key] = lbl

    # ── Nächste Schritte ──────────────────────────────────────────────────────
    nf = ttk.LabelFrame(win, text="Nächste Schritte (regelbasiert)", padding=(10, 6))
    nf.pack(fill="x", padx=12, pady=4)
    steps_var = tk.StringVar(value="Daten werden geladen …")
    ttk.Label(nf, textvariable=steps_var, font=("Segoe UI", 9),
              justify="left", wraplength=650).pack(anchor="w")

    # ── KI-Empfehlung ─────────────────────────────────────────────────────────
    kf = ttk.LabelFrame(win, text="KI-Forschungsempfehlung (Claude Copilot)", padding=(10, 6))
    kf.pack(fill="x", padx=12, pady=4)

    ai_text = scrolledtext.ScrolledText(
        kf, height=6, wrap="word", font=("Segoe UI", 9),
        state="disabled", bg="#fafafa")
    ai_text.pack(fill="x")

    hint = availability_hint()
    if hint:
        ai_text.configure(state="normal")
        ai_text.insert("end", hint)
        ai_text.configure(state="disabled")

    btn_bar = ttk.Frame(kf)
    btn_bar.pack(fill="x", pady=(4, 0))
    ai_btn_var = tk.StringVar(value="🤖 KI-Empfehlung holen")
    ai_btn = ttk.Button(btn_bar, textvariable=ai_btn_var,
                        state="normal" if is_available() else "disabled")
    ai_btn.pack(side="right")
    refresh_btn = ttk.Button(btn_bar, text="↻ Neu laden")
    refresh_btn.pack(side="left")

    ttk.Button(win, text="Schließen", command=win.destroy).pack(
        anchor="e", padx=12, pady=(4, 10))

    # ── Render & Laden ────────────────────────────────────────────────────────
    _stats: list[dict] = [{}]

    def _render(s: dict) -> None:
        pts, level, dims = _score(s)
        _stats[0] = s

        # Score-Balken (nach kurzem Delay damit Canvas-Breite bekannt ist)
        win.after(60, lambda: _draw_score_bar(score_canvas, pts, level))

        # Dimensions-Balken
        win.after(80, lambda: _redraw_dims(dims))

        # Achievements
        for key, _, _, cond in ACHIEVEMENTS:
            lbl = _ach_widgets.get(key)
            if lbl is None:
                continue
            if cond(s):
                lbl.configure(bg="#d4edda", fg="#155724")
            else:
                lbl.configure(bg="#e8e8e8", fg="#aaa")

        # Nächste Schritte
        steps_var.set("\n".join(f"  {st}" for st in _steps(s)))

    def _redraw_dims(dims: dict[str, float]) -> None:
        for name, pct in dims.items():
            c = _dim_canvases.get(name)
            if c:
                _draw_dim_bar(c, pct)
            sv = _dim_pct_vars.get(name)
            if sv:
                sv.set(f"{pct:.0%}")

    def _load() -> None:
        s = _gather(db, test_guid, app)
        win.after(0, lambda: _render(s))

    threading.Thread(target=_load, daemon=True).start()
    refresh_btn.configure(command=lambda: threading.Thread(target=_load, daemon=True).start())

    # ── KI-Button-Logik ───────────────────────────────────────────────────────

    def _ask_ai() -> None:
        s = _stats[0]
        if not s:
            return
        ai_btn.configure(state="disabled")
        ai_btn_var.set("⏳ Claude denkt …")
        ai_text.configure(state="normal")
        ai_text.delete("1.0", "end")

        def _chunk(text: str) -> None:
            win.after(0, lambda t=text: _append(t))

        def _done(_: str) -> None:
            win.after(0, _finish)

        def _append(text: str) -> None:
            ai_text.configure(state="normal")
            ai_text.insert("end", text)
            ai_text.see("end")

        def _finish() -> None:
            ai_text.configure(state="disabled")
            ai_btn.configure(state="normal")
            ai_btn_var.set("🤖 KI-Empfehlung holen")

        explain_async(gaps_prompt(s), on_chunk=_chunk, on_done=_done)

    ai_btn.configure(command=_ask_ai)
