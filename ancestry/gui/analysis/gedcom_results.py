"""
ancestry/gui/analysis/gedcom_results.py — GEDCOM-Abgleich-Ergebnis-Popup.

Zeigt alle verankerten DNA-Matches im eigenen Stammbaum mit Filter,
Sortierung, Cluster-Farbmarkierung und Cluster-Stammbaum-Button.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from ancestry.gui.widgets.theme import COLORS


def show_gedcom_results(app, results, n_people, n_peds, cluster_lookup=None) -> None:
    """Öffnet das GEDCOM-Abgleich-Popup."""
    win = tk.Toplevel(app)
    win.title("GEDCOM-Abgleich – wo hängt jeder Match in deinem Baum?")
    win.geometry("1100x640")

    cl = cluster_lookup or {}
    cluster_ids = sorted({cid for cid in cl.values()}) if cl else []

    data = []
    for name, cm, (score, r, own, _p), kin, linked, guid in results:
        ab = " ".join(x for x in (str(own.year or ""), own.place) if x).strip()
        cid = cl.get(guid)
        data.append({
            "linked": linked,
            "link": app._t("gc.linked") if linked else app._t("gc.new"),
            "match": name or "?", "cm": float(cm or 0),
            "anchor": own.display, "abirth": ab,
            "kin": kin or "—", "line": r["ahnen_path"] or "?",
            "score": float(score or 0),
            "cluster": cid,
            "cluster_str": f"#{cid}" if cid else "—",
        })
    n_new = sum(1 for d in data if not d["linked"])

    # ── Filterleiste ────────────────────────────────────────────────────────
    bar = ttk.Frame(win); bar.pack(fill="x", padx=10, pady=(10, 2))
    ttk.Label(bar, text=app._t("gc.f.search")).pack(side="left")
    f_search = tk.StringVar()
    ttk.Entry(bar, textvariable=f_search, width=20).pack(side="left", padx=4)
    f_new = tk.BooleanVar(value=False)
    ttk.Checkbutton(bar, text=app._t("gc.f.new"),
                    variable=f_new).pack(side="left", padx=6)
    f_direct = tk.BooleanVar(value=False)
    ttk.Checkbutton(bar, text=app._t("gc.f.direct"),
                    variable=f_direct).pack(side="left", padx=6)
    ttk.Label(bar, text=app._t("gc.f.mincm")).pack(side="left")
    f_cm = tk.StringVar(value="0")
    ttk.Entry(bar, textvariable=f_cm, width=5).pack(side="left", padx=4)
    ttk.Label(bar, text=app._t("gc.f.cluster")).pack(side="left", padx=(10, 0))
    f_cluster = tk.StringVar(value="")
    cluster_opts = [""] + [str(c) for c in cluster_ids]
    cb_cluster = ttk.Combobox(bar, textvariable=f_cluster,
                               values=cluster_opts, width=5, state="readonly")
    cb_cluster.pack(side="left", padx=4)

    hdr = ttk.Label(win, text="", style="Bold.TLabel")
    hdr.pack(anchor="w", padx=10, pady=(0, 2))

    btn_bar = ttk.Frame(win)
    _cluster_btn = ttk.Button(btn_bar, text=app._t("gc.tree_btn"), state="disabled")
    _cluster_btn.pack(side="left", padx=4)
    btn_bar.pack(fill="x", padx=10, pady=(0, 4), side="bottom")
    _sel_cid: list = [None]

    cols = ("cluster", "link", "match", "cm", "anchor", "abirth", "kin", "line", "score")
    heads = {
        "cluster": ("gc.cluster", 58),
        "link":    ("gc.link",    72),
        "match":   ("gc.match",  165),
        "cm":      ("gc.cm",      52),
        "anchor":  ("gc.anchor", 185),
        "abirth":  ("gc.abirth", 115),
        "kin":     ("gc.kin",    165),
        "line":    ("gc.line",    72),
        "score":   ("gc.score",   65),
    }
    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=(10, 0), pady=6)
    tv = ttk.Treeview(frame, columns=cols, show="headings")
    for c, (key, w) in heads.items():
        tv.column(c, width=w,
                  anchor=("center" if c in ("cluster", "cm", "line", "score", "link") else "w"))
    tv.pack(side="left", fill="both", expand=True)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    sb.pack(side="right", fill="y")
    tv.configure(yscrollcommand=sb.set)

    tv.tag_configure("strong",  background="#d8f0d8")
    tv.tag_configure("newlead", background="#fde9c8")
    clr = COLORS["cluster"]
    for i in range(1, len(clr) + 1):
        tv.tag_configure(f"cl{i}", background=clr[(i - 1) % len(clr)])

    def _on_tv_select(_):
        sel = tv.selection()
        _sel_cid[0] = None
        if not sel:
            _cluster_btn.configure(state="disabled")
            return
        vals = tv.item(sel[0], "values")
        cstr = vals[0] if vals else ""
        if cstr and cstr != "—":
            try:
                cid = int(cstr.lstrip("#"))
                if cid in getattr(app, "_clusters", {}):
                    _sel_cid[0] = cid
                    _cluster_btn.configure(state="normal")
                    return
            except (ValueError, AttributeError):
                pass
        _cluster_btn.configure(state="disabled")

    def _open_cluster_tree():
        cid = _sel_cid[0]
        clusters = getattr(app, "_clusters", {})
        if cid is None or cid not in clusters:
            messagebox.showinfo(
                "Cluster nicht berechnet",
                "Bitte zuerst im Cluster-Tab Clustering durchführen.")
            return
        members = clusters[cid]
        cluster_obj = {"members": [(m["guid"], m["name"], m["cm"]) for m in members]}
        tg = app._state.current_test_guid or app._current_guid()
        if tg:
            app._build_cluster_tree(tg, cluster_obj)

    _cluster_btn.configure(command=_open_cluster_tree)
    tv.bind("<<TreeviewSelect>>", _on_tv_select)

    state = {"col": "cm", "desc": True}

    def populate(*_):
        q = f_search.get().strip().lower()
        try:
            mincm = float(f_cm.get() or 0)
        except ValueError:
            mincm = 0
        fc = f_cluster.get().strip()
        rows = [d for d in data
                if d["cm"] >= mincm
                and (not f_new.get() or not d["linked"])
                and (not f_direct.get() or ("Seitenlinie" not in d["kin"]
                                            and d["kin"] != "—"))
                and (not fc or str(d.get("cluster", "")) == fc)
                and (not q or q in d["match"].lower()
                     or q in d["anchor"].lower() or q in d["kin"].lower())]
        col, desc = state["col"], state["desc"]
        rows.sort(key=lambda d: (d[col] is None, d[col] or 0), reverse=desc)
        tv.delete(*tv.get_children())
        for d in rows:
            cid = d.get("cluster")
            if not d["linked"]:
                tag = ("newlead",)
            elif d["score"] >= 0.8:
                tag = ("strong",)
            elif cid:
                tag = (f"cl{cid}",)
            else:
                tag = ()
            tv.insert("", "end", tags=tag, values=(
                d["cluster_str"], d["link"], d["match"],
                f"{d['cm']:.0f}", d["anchor"], d["abirth"],
                d["kin"], d["line"], f"{d['score']:.2f}"))
        hdr.configure(text=(
            f"Eigener Baum: {n_people} Pers. · "
            f"{len(data)} verankert ({n_new} neu) · angezeigt: {len(rows)} · "
            f"Sort: {app._t(heads[col][0])} {'▼' if desc else '▲'}"))

    def sort_by(col):
        state["desc"] = not state["desc"] if state["col"] == col else True
        state["col"] = col
        populate()

    for c, (key, w) in heads.items():
        tv.heading(c, text=app._t(key), command=lambda c=c: sort_by(c))

    for var in (f_search, f_new, f_direct, f_cm, f_cluster):
        var.trace_add("write", populate)
    populate()
    app._set_status(f"GEDCOM-Abgleich: {len(data)}/{n_peds} Matches verankert.")


def show_wikitree_results(app, match_name: str, results: list) -> None:
    """Zeigt WikiTree-Treffer und gefundene Ahnenlinien in einem Textfenster."""
    win = tk.Toplevel(app)
    win.title(f"WikiTree-Linien: {match_name}")
    win.geometry("640x520")
    txt = tk.Text(win, wrap="word", font=("Segoe UI", 9))
    sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    txt.pack(fill="both", expand=True)

    if not results:
        txt.insert("end", "Keine Ahnen mit Nachnamen in der Ahnentafel dieses Matches.\n")
    for r in results:
        q = r.get("query", {})
        txt.insert("end", f"▶ {q.get('first_name', '')} {q.get('surname', '')}"
                          f"  ({q.get('birth_place', '')} {q.get('birth_year', '')})\n")
        if r.get("error"):
            txt.insert("end", f"   Fehler: {r['error']}\n\n")
            continue
        best = r.get("best")
        if not best:
            txt.insert("end",
                f"   kein WikiTree-Treffer ({len(r.get('candidates', []))} Kandidaten)\n\n")
            continue
        txt.insert("end",
            f"   ✓ {best.get('Name', '?')}: {best.get('FirstName', '')} "
            f"{best.get('LastNameAtBirth', '')}  "
            f"* {best.get('BirthDate', '?')} {best.get('BirthLocation', '')}\n")
        lin = r.get("lineage", [])
        if lin:
            txt.insert("end", f"   Ahnenlinie ({len(lin)}):\n")
            for a in lin[:12]:
                txt.insert("end",
                    f"      • {a.get('FirstName', '')} "
                    f"{a.get('LastNameAtBirth', '')}  "
                    f"* {a.get('BirthDate', '?')} {a.get('BirthLocation', '')}\n")
        txt.insert("end", "\n")
    txt.configure(state="disabled")
