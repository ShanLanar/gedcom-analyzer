"""Cluster-bezogene Popup-Fenster ohne Client-/Auth-Abhängigkeit.

Alle Funktionen nehmen `app` (die Hauptfenster-Instanz) als erstes Argument
und erzeugen ein tk.Toplevel-Fenster.
"""
from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox, ttk

from ancestry.gui.widgets.theme import COLORS


def show_cluster_tree_win(app, cluster, rows, n_with_ped, has_ged, name_by_member):
    """Kombinierter Cluster-Stammbaum: verschmolzene Ahnen aller Mitglieder."""
    from ancestry.core.treematch import render_kinship, cm_to_mrca, cluster_confidence

    win = tk.Toplevel(app)
    win.title("Kombinierter Cluster-Stammbaum")
    win.geometry("960x640")
    size = cluster["size"]
    shared = [r for r in rows if len(r["members"]) >= 2]
    ttk.Label(win, text=(f"Cluster: {size} Matches ({n_with_ped} mit Ahnentafel) · "
                         f"{len(rows)} Personen verschmolzen · "
                         f"{len(shared)} von ≥2 Mitgliedern geteilt"),
              style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10, 2))

    cms = sorted((cm for _g, _n, cm in cluster["members"] if cm), reverse=True)
    if cms:
        lbl_close, gen_close = cm_to_mrca(cms[0])
        lbl_far,   gen_far   = cm_to_mrca(cms[-1])
        ttk.Label(win, text=(
            f"cM-Schätzung: gem. Vorfahr ~Gen {gen_close}"
            + (f"–{gen_far}" if gen_far != gen_close else "")
            + f"  (nächstes Mitglied {cms[0]:.0f} cM = {lbl_close}; "
            f"entferntestes {cms[-1]:.0f} cM = {lbl_far}).  "
            "⚠ Endogamie → cM überhöht, echter Vorfahr eher tiefer."),
            foreground="#555").pack(anchor="w", padx=10, pady=(0, 2))

    conv_frac = (max((len(r["members"]) for r in rows), default=0)
                 / n_with_ped) if n_with_ped else 0.0
    conf = cluster_confidence(size, cluster.get("density", 0),
                              cluster.get("median_cm", 0), conv_frac,
                              endogamy_score=cluster.get("endogamy", 0),
                              n_confirmed=cluster.get("n_thrulines", 0)
                                          + cluster.get("n_linked", 0))
    ttk.Label(win, text=(
        f"Bewertung: Cluster echt ~{conf['realness']*100:.0f}% ({conf['label']}, "
        f"Dichte {cluster.get('density',0):.2f}) · "
        f"Pedigree-Konvergenz {conv_frac*100:.0f}% "
        f"(max. {max((len(r['members']) for r in rows), default=0)}/{n_with_ped} "
        f"auf einen Vorfahren)"
        + (f"  ⚠ {conf['note']}" if conf['note'] else "")),
        foreground="#333", style="Bold.TLabel").pack(anchor="w", padx=10, pady=(0, 4))

    def _birth(rep):
        d = rep.bdate or (str(rep.year) if rep.year else "")
        return " · ".join(x for x in (d, rep.place) if x)

    box = ttk.LabelFrame(win, text="🔮 Vorhergesagter gemeinsamer Vorfahr des Clusters")
    box.pack(fill="x", padx=10, pady=(2, 6))
    direct = sorted([r for r in shared if r["path"] is not None],
                    key=lambda r: (len(r["path"]), -len(r["members"])))
    pred = direct[0] if direct else (shared[0] if shared else (rows[0] if rows else None))
    if not pred:
        ttk.Label(box, text="Zu wenig Daten – Ahnentafeln der Mitglieder laden.",
                  foreground="#a05a00").pack(anchor="w", padx=8, pady=4)
    else:
        rep = pred["rep"]
        ttk.Label(box, text=f"{rep.display}   ({_birth(rep) or 'kein Datum/Ort'})",
                  style="Bold.TLabel").pack(anchor="w", padx=8, pady=(4, 0))
        ttk.Label(box, text=f"geteilt von {len(pred['members'])}/{size} "
                  f"Mitgliedern · Generation {pred['gen']}").pack(anchor="w", padx=8)
        if pred["path"] is not None:
            via_txt = (f"über Seitenlinie {pred['own'].display} → "
                       if pred.get("via") else "")
            ttk.Label(box, text=(f"✓ Andockpunkt in deinem Baum: {via_txt}"
                      f"deine Linie: {render_kinship(pred['path'])}"),
                      foreground=COLORS.get("primary", "#1b5e20"),
                      style="Bold.TLabel").pack(anchor="w", padx=8, pady=(0, 4))
        elif pred["own"] is not None:
            ttk.Label(box, text=(f"In deinem Baum als Seitenlinie: "
                      f"{pred['own'].display} (nicht direkte Ahnenlinie)"),
                      foreground="#a05a00").pack(anchor="w", padx=8, pady=(0, 4))
        else:
            ttk.Label(box, text=("❗ NICHT in deinem Baum → Forschungsziel: "
                      "diese Person suchen/eintragen, dann liefert Ancestry "
                      "ThruLines-Hints für den ganzen Cluster."),
                      foreground="#b00020", style="Bold.TLabel"
                      ).pack(anchor="w", padx=8, pady=(0, 4))
        fa, mo = pred.get("father"), pred.get("mother")
        if fa or mo:
            ft = f"Vater: {fa.display} ({_birth(fa) or '?'})" if fa else "Vater: ?"
            mt = f"Mutter: {mo.display} ({_birth(mo) or '?'})" if mo else "Mutter: ?"
            ttk.Label(box, text=f"   └ {ft}   |   {mt}",
                      foreground="#444").pack(anchor="w", padx=8, pady=(0, 4))
        if pred:
            rep = pred["rep"]
            btn_frame = ttk.Frame(box)
            btn_frame.pack(anchor="w", padx=8, pady=(0, 4))
            surnames = {s for s in [
                getattr(rep, "surname", None),
                getattr(fa, "surname", None) if pred.get("father") else None,
                getattr(mo, "surname", None) if pred.get("mother") else None,
            ] if s}
            for sur in list(surnames)[:4]:
                ttk.Button(btn_frame, text=f"🗺 {sur}",
                           command=lambda s=sur: app._open_namenskarte(s)
                           ).pack(side="left", padx=2)

    if not has_ged:
        ttk.Label(win, text="(GEDCOM nicht geladen → ohne Andock-Spalte. "
                  "Über 'Cluster-Linie in meinem Baum suchen' wird der Baum geladen.)",
                  foreground="#888").pack(anchor="w", padx=10)

    cols = ("person", "shared", "gen", "cms", "dock")
    tv = ttk.Treeview(win, columns=cols, show="headings")
    for c, (lbl, w) in {"person": ("Vorfahr (verschmolzen)", 300),
                        "shared": ("geteilt von", 90), "gen": ("Gen", 50),
                        "cms": ("cM der Mitglieder", 150),
                        "dock": ("= in deinem Baum (Sosa)", 260)}.items():
        tv.heading(c, text=lbl)
        tv.column(c, width=w, anchor=("center" if c in ("shared", "gen") else "w"))
    tv.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=6)
    sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
    sb.pack(side="right", fill="y", pady=6)
    tv.configure(yscrollcommand=sb.set)
    tv.tag_configure("shared", background="#fff3b0")
    tv.tag_configure("dock", background="#d8f0d8")

    row_reps = {}
    for r in rows:
        rep = r["rep"]
        indent = "  " * max(0, r["gen"] - 2)
        bd = rep.bdate or (str(rep.year) if rep.year else "")
        binfo = " · ".join(x for x in (bd, rep.place) if x)
        disp = f"{indent}{rep.display}" + (f"  (*{binfo})" if binfo else "")
        nshare = len(r["members"])
        dock = ""
        if r["path"] is not None:
            dock = f"{r['own'].display} – {render_kinship(r['path'])}"
        elif r["own"] is not None:
            dock = f"{r['own'].display} (Seitenlinie)"
        cms_str = ", ".join(f"{c:.0f}" for c in r["cms"][:6])
        tag = ("dock",) if r["path"] is not None else \
              (("shared",) if nshare >= 2 else ())
        iid = tv.insert("", "end", tags=tag, values=(
            disp, f"{nshare}/{size}", r["gen"], cms_str, dock))
        row_reps[iid] = rep

    nk_frame = ttk.Frame(win)
    nk_frame.pack(anchor="w", padx=10, pady=(0, 4), side="bottom")
    ttk.Label(nk_frame, text="Ausgewählter Vorfahr → Namenskarte:",
              foreground="#555").pack(side="left")
    nk_btn = ttk.Button(nk_frame, text="🗺 Namenskarte.com",
                        state="disabled", command=lambda: None)
    nk_btn.pack(side="left", padx=6)

    def _on_tree_sel(_):
        sel = tv.selection()
        if not sel:
            return
        rep = row_reps.get(sel[0])
        if not rep:
            return
        sur = getattr(rep, "surname", None) or rep.display.split()[-1]
        nk_btn.configure(state="normal",
                         command=lambda s=sur: app._open_namenskarte(s))

    tv.bind("<<TreeviewSelect>>", _on_tree_sel)


def show_cluster_relationships(app, test_guid, cluster):
    """Interne Beziehungs-Struktur: paarweise cM zwischen Cluster-Mitgliedern."""
    from ancestry.core.treematch import pair_relationship

    guids = [g for g, _n, _cm in cluster["members"]]
    name = {g: n for g, n, _cm in cluster["members"]}
    pairs = app._db.get_pairwise_shared(test_guid, guids)

    win = tk.Toplevel(app)
    win.title("Beziehungen im Cluster (interne Struktur)")
    win.geometry("760x540")
    ttk.Label(win, text=(f"{cluster['size']} Mitglieder · {len(pairs)} bekannte "
                         f"Paar-Beziehungen (aus geteilten cM untereinander):"),
              style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10, 2))
    ttk.Label(win, text="Hohe cM = nah (Eltern/Kind, Geschwister) → engere "
              "Teil-Familien im Cluster. Hilft, die Struktur zu rekonstruieren.",
              foreground="#555").pack(anchor="w", padx=10, pady=(0, 4))

    if not pairs:
        ttk.Label(win, text="Keine paarweisen cM gespeichert. Dafür müssen die "
                  "Shared Matches der Mitglieder geladen sein (Schritt B).",
                  foreground="#a05a00").pack(anchor="w", padx=10, pady=8)
        return

    cols = ("a", "b", "cm", "rel")
    tv = ttk.Treeview(win, columns=cols, show="headings")
    for c, (lbl, w) in {"a": ("Match A", 200), "b": ("Match B", 200),
                        "cm": ("cM A↔B", 80), "rel": ("Beziehung", 230)}.items():
        tv.heading(c, text=lbl)
        tv.column(c, width=w, anchor=("center" if c == "cm" else "w"))
    tv.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=6)
    sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
    sb.pack(side="right", fill="y", pady=6)
    tv.configure(yscrollcommand=sb.set)
    tv.tag_configure("close", background="#d8f0d8")

    for a, b, cm in pairs:
        tag = ("close",) if cm >= 200 else ()
        tv.insert("", "end", tags=tag, values=(
            name.get(a, a[:8]), name.get(b, b[:8]),
            f"{cm:.0f}", pair_relationship(cm)))


def show_cluster_dock(app, cluster, hits, n_with_ped):
    """Zeigt, wo die Cluster-Mitglieder in deinem Baum andocken."""
    from ancestry.core.treematch import render_kinship

    win = tk.Toplevel(app)
    win.title("Cluster-Linie → Andockpunkt in deinem Baum")
    win.geometry("840x540")
    ttk.Label(win, text=(f"Cluster mit {cluster['size']} Matches "
                         f"({n_with_ped} mit Ahnentafel) – Treffer in deinem Baum:"),
              style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10, 4))

    direct = [h for h in hits if h[4] is not None]
    if direct:
        best = direct[0]
        ttk.Label(win, text=(f"➡  Wahrscheinlicher Andockpunkt: {best[2]}  "
                             f"({render_kinship(best[4])}) – von {best[0]} "
                             f"Mitglied(ern) getroffen"),
                  style="Bold.TLabel", foreground=COLORS.get("primary", "#1b5e20")
                  ).pack(anchor="w", padx=10, pady=(0, 6))
    elif hits:
        ttk.Label(win, text=("Kein Treffer auf deiner direkten Ahnenlinie – "
                             "untenstehende sind Seitenlinien/Vorschläge."),
                  foreground="#a05a00").pack(anchor="w", padx=10, pady=(0, 6))
    else:
        ttk.Label(win, text=("Keine Treffer im Baum. Mögliche Gründe: Cluster-"
                             "Mitglieder haben (noch) keine Ahnentafel geladen, "
                             "oder die Linie liegt tiefer → ‚Cluster tiefer laden'."),
                  foreground="#a05a00").pack(anchor="w", padx=10, pady=(0, 6))

    cols = ("count", "line", "anchor", "score")
    tv = ttk.Treeview(win, columns=cols, show="headings")
    for c, (lbl, w) in {"count": ("getroffen von", 110),
                        "line": ("Deine Linie", 230),
                        "anchor": ("Person in deinem Baum", 230),
                        "score": ("Sicherheit", 80)}.items():
        tv.heading(c, text=lbl)
        tv.column(c, width=w, anchor=("center" if c in ("count", "score") else "w"))
    tv.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=6)
    sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
    sb.pack(side="right", fill="y", pady=6)
    tv.configure(yscrollcommand=sb.set)
    tv.tag_configure("direct", background="#d8f0d8")

    for count, score, owndisp, _own, path in hits:
        kin = render_kinship(path) if path is not None else "— (Seitenlinie)"
        tag = ("direct",) if path is not None else ()
        tv.insert("", "end", tags=tag, values=(
            f"{count}/{cluster['size']}", kin, owndisp, f"{score:.2f}"))


def show_cluster_timeline(app):
    """Zeigt Geburtsjahre der Cluster-Vorfahren als Zeitachse."""
    sel = app._cluster_list.selection()
    if not sel:
        messagebox.showinfo("Kein Cluster", "Bitte Cluster auswählen.")
        return
    cid = int(sel[0])
    members = app._clusters.get(cid, [])
    if not members:
        return
    test_guid = app._current_guid()
    if not test_guid:
        return

    try:
        guids = [m["guid"] for m in members]
        rows = app._db.get_cluster_ancestor_years(test_guid, guids)
    except Exception as e:
        messagebox.showerror("Fehler", str(e))
        return

    if not rows:
        messagebox.showinfo("Keine Daten",
                            "Keine Ahnentafel-Daten für diesen Cluster vorhanden.\n"
                            "→ Erst 'Ahnentafeln laden' ausführen.")
        return

    win = tk.Toplevel(app)
    color = COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])]
    win.title(f"Cluster #{cid} – Zeitachse der Vorfahren")
    win.geometry("900x400")

    years = [int(r.get("birth_year", 0)) for r in rows if r.get("birth_year")]
    if not years:
        return
    y_min, y_max = min(years), max(years)
    y_range = max(y_max - y_min, 50)

    c = tk.Canvas(win, bg="#FAFAFA", highlightthickness=0)
    c.pack(fill="both", expand=True, padx=10, pady=10)

    def draw(_event=None):
        c.delete("all")
        W = c.winfo_width() or 860
        H = c.winfo_height() or 340
        pad_x = 60
        pad_y = 40

        c.create_line(pad_x, H - pad_y, W - 20, H - pad_y, fill="#AAAAAA", width=1)
        decade_start = (y_min // 10) * 10
        decade_end   = ((y_max // 10) + 1) * 10
        for yr in range(decade_start, decade_end + 1, 10):
            x = pad_x + (yr - y_min) / y_range * (W - pad_x - 20)
            c.create_line(x, H - pad_y - 4, x, H - pad_y + 4, fill="#888888")
            c.create_text(x, H - pad_y + 16, text=str(yr),
                          font=("Segoe UI", 7), fill="#888888")

        random.seed(cid)
        for r in rows:
            yr = int(r.get("birth_year", 0))
            if not yr:
                continue
            x = pad_x + (yr - y_min) / y_range * (W - pad_x - 20)
            gen = r.get("generation", 3)
            y = pad_y + (gen - 1) * 18
            y = min(y, H - pad_y - 20)
            tag = f"d{id(r)}"
            c.create_oval(x - 5, y - 5, x + 5, y + 5, fill=color, outline="white",
                          width=1, tags=tag)
            name = f"{r.get('given_name', '')} {r.get('surname', '')}"
            c.tag_bind(tag, "<Enter>",
                       lambda e, n=name, yr=yr, gen=gen:
                           c.create_text(e.x + 10, e.y - 10,
                                         text=f"{n} ({yr}) Gen{gen}",
                                         font=("Segoe UI", 8), tags="tooltip",
                                         fill=COLORS["text"]))
            c.tag_bind(tag, "<Leave>", lambda _: c.delete("tooltip"))

    c.bind("<Configure>", draw)
    win.after(100, draw)
