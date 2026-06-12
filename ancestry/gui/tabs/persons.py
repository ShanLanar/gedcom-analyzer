"""PersonsTab – Tab „👪 Personen" für das Ancestry-DNA-Tool.

Durchsuchbarer Personen-Browser mit navigierbarem Stammbaum (Canvas) und
Detailpanel inkl. DNA-Matches. Liest direkt aus gedcom_persons /
gedcom_links / matches der Haupt-DB (ancestry_dna.db) – kein separater
Crawl-DB-Zugriff nötig, da Webtrees-/WikiTree-Personen über die Spalte
`source` ebenfalls in gedcom_persons liegen.

Die Familienbeziehungen (parents_json/…) werden beim GEDCOM-Import in
ancestry/core/bridge/gedcom_import.py befüllt; ohne geladenes GEDCOM bleibt
der Baum auf die jeweils ausgewählte Person beschränkt.
"""
from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk

from ancestry.gui.state import AppState

# ── helle Karten-Palette ──────────────────────────────────────────────────────
_CARD_M   = "#cfe0f5"   # männlich  (blau)
_CARD_F   = "#f5d6d6"   # weiblich  (rosa)
_CARD_N   = "#e6e6e6"   # unbekannt
_FOCUS    = "#fff3cd"   # Fokusperson (gelb)
_LINE     = "#9aa4ae"
_TXT      = "#1f2327"
_MUTED    = "#6c7086"

_SRC_LABEL = {"": "Alle Quellen", "gedcom": "GEDCOM", "anverwandte": "Webtrees",
              "wikitree": "WikiTree"}


def _years(b, d) -> str:
    b = str(b or "").strip()
    d = str(d or "").strip()
    if b in ("", "0", "None"):
        b = ""
    if d in ("", "0", "None"):
        d = ""
    if not b and not d:
        return ""
    return f"{b or '?'}–{d}".rstrip("–")


def _loads(s) -> list:
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _lighten(hex_color: str, amount: int = 24) -> str:
    try:
        r = min(255, int(hex_color[1:3], 16) + amount)
        g = min(255, int(hex_color[3:5], 16) + amount)
        b = min(255, int(hex_color[5:7], 16) + amount)
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return hex_color


class PersonsTab(ttk.Frame):
    """Personen-/Stammbaum-Tab des Ancestry-DNA-Tools."""

    def __init__(self, parent: tk.Widget, state: AppState):
        super().__init__(parent)
        self._state = state
        self._pers_history: list[str] = []
        self._pers_current: str | None = None
        self._build()

    @property
    def _db(self):
        return self._state.db

    def _build(self):
        f = self

        outer = ttk.Panedwindow(f, orient="horizontal")
        outer.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Links: Suche + Personenliste ──────────────────────────────────
        left = ttk.Frame(outer)
        outer.add(left, weight=1)
        bar = ttk.Frame(left); bar.pack(fill="x", pady=(0, 4))
        ttk.Label(bar, text="Suche:").pack(side="left")
        self._pers_search = tk.StringVar()
        self._pers_search.trace_add("write", lambda *_: self._pers_reload_list())
        ttk.Entry(bar, textvariable=self._pers_search, width=18).pack(
            side="left", padx=4)
        self._pers_source = tk.StringVar(value="Alle Quellen")
        src_cb = ttk.Combobox(bar, textvariable=self._pers_source, width=12,
                              state="readonly",
                              values=list(_SRC_LABEL.values()))
        src_cb.pack(side="left", padx=4)
        src_cb.bind("<<ComboboxSelected>>", lambda _: self._pers_reload_list())

        cols = ("name", "years")
        self._pers_list = ttk.Treeview(left, columns=cols, show="headings",
                                       selectmode="browse", height=20)
        self._pers_list.heading("name", text="Name")
        self._pers_list.heading("years", text="Jahre")
        self._pers_list.column("name", width=190, stretch=True)
        self._pers_list.column("years", width=92, anchor="center", stretch=False)
        psb = ttk.Scrollbar(left, orient="vertical",
                            command=self._pers_list.yview)
        self._pers_list.configure(yscrollcommand=psb.set)
        self._pers_list.pack(side="left", fill="both", expand=True)
        psb.pack(side="right", fill="y")
        self._pers_list.bind("<<TreeviewSelect>>", self._pers_on_list_select)
        self._pers_count = tk.StringVar(value="")
        ttk.Label(left, textvariable=self._pers_count,
                  foreground=_MUTED).pack(side="bottom", anchor="w")

        # ── Mitte: Stammbaum-Canvas ───────────────────────────────────────
        mid = ttk.Frame(outer)
        outer.add(mid, weight=3)
        nav = ttk.Frame(mid); nav.pack(fill="x")
        ttk.Button(nav, text="◀ Zurück", command=self._pers_go_back).pack(
            side="left", pady=(0, 4))
        cwrap = ttk.Frame(mid); cwrap.pack(fill="both", expand=True)
        self._pers_canvas = tk.Canvas(cwrap, bg="#ffffff", highlightthickness=0)
        cvsb = ttk.Scrollbar(cwrap, orient="vertical",
                            command=self._pers_canvas.yview)
        chsb = ttk.Scrollbar(cwrap, orient="horizontal",
                            command=self._pers_canvas.xview)
        self._pers_canvas.configure(yscrollcommand=cvsb.set,
                                    xscrollcommand=chsb.set)
        cvsb.pack(side="right", fill="y")
        chsb.pack(side="bottom", fill="x")
        self._pers_canvas.pack(side="left", fill="both", expand=True)
        self._pers_canvas.bind(
            "<MouseWheel>",
            lambda e: self._pers_canvas.yview_scroll(-1*(e.delta//120), "units"))
        self._pers_canvas.bind(
            "<Shift-MouseWheel>",
            lambda e: self._pers_canvas.xview_scroll(-1*(e.delta//120), "units"))

        # ── Rechts: Detail ────────────────────────────────────────────────
        right = ttk.Frame(outer, width=320)
        outer.add(right, weight=1)
        self._pers_detail = ttk.Frame(right)
        self._pers_detail.pack(fill="both", expand=True)

        # Erstbefüllung verzögert (keine DB-Arbeit beim Aufbau → kein Start-Freeze)
        self.after(120, self._pers_initial_load)

    # ── Datenzugriff ──────────────────────────────────────────────────────
    def _pers_source_key(self) -> str:
        label = self._pers_source.get()
        for k, v in _SRC_LABEL.items():
            if v == label:
                return k
        return ""

    def _pers_initial_load(self):
        # Einmalig Index für die DNA-Verknüpfung sicherstellen (sonst Scan)
        def _bg():
            try:
                with self._db._cursor() as cur:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_gl_ged "
                                "ON gedcom_links(ged_id)")
            except Exception:
                pass
            self.after(0, self._pers_reload_list)
        threading.Thread(target=_bg, daemon=True, name="pers-init").start()

    def _pers_reload_list(self, *_):
        q = (self._pers_search.get() or "").strip()
        src = self._pers_source_key()
        gen = getattr(self, "_pers_list_gen", 0) + 1
        self._pers_list_gen = gen

        def _fetch():
            conds, params = [], []
            if src:
                conds.append("source = ?"); params.append(src)
            if q:
                conds.append("(given_name LIKE ? OR surname LIKE ?)")
                params += [f"%{q}%", f"%{q}%"]
            where = ("WHERE " + " AND ".join(conds)) if conds else ""
            sql = (f"SELECT ged_id, given_name, surname, birth_year, death_year, "
                   f"sex FROM gedcom_persons {where} "
                   f"ORDER BY surname, given_name LIMIT 600")
            try:
                with self._db._cursor() as cur:
                    rows = cur.execute(sql, params).fetchall()
            except Exception as exc:
                self.after(0, lambda e=exc: self._pers_count.set(f"⚠ {e}"))
                return
            data = [(r["ged_id"],
                     f"{(r['given_name'] or '').strip()} {(r['surname'] or '').strip()}".strip()
                     or r["ged_id"],
                     _years(r["birth_year"], r["death_year"]))
                    for r in rows]
            self.after(0, lambda: self._pers_fill_list(data, gen))
        threading.Thread(target=_fetch, daemon=True, name="pers-list").start()

    def _pers_fill_list(self, data, gen):
        if getattr(self, "_pers_list_gen", 0) != gen:
            return
        self._pers_list.delete(*self._pers_list.get_children())
        for ged_id, name, years in data:
            self._pers_list.insert("", "end", iid=ged_id, values=(name, years))
        self._pers_count.set(f"{len(data)} Personen"
                             + (" (max. 600)" if len(data) >= 600 else ""))

    def _pers_get(self, ged_id: str) -> dict | None:
        if not ged_id:
            return None
        try:
            with self._db._cursor() as cur:
                r = cur.execute(
                    "SELECT * FROM gedcom_persons WHERE ged_id=?",
                    (ged_id,)).fetchone()
            return dict(r) if r else None
        except Exception:
            return None

    def _pers_batch(self, ids: list[str]) -> dict[str, dict]:
        ids = [str(i) for i in ids if i]
        if not ids:
            return {}
        ph = ",".join("?" * len(ids))
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    f"SELECT * FROM gedcom_persons WHERE ged_id IN ({ph})",
                    ids).fetchall()
            return {str(r["ged_id"]): dict(r) for r in rows}
        except Exception:
            return {}

    # ── Navigation ────────────────────────────────────────────────────────
    def _pers_on_list_select(self, _=None):
        sel = self._pers_list.selection()
        if sel:
            self._pers_navigate(sel[0])

    def _pers_navigate(self, ged_id: str, push: bool = True):
        if push and self._pers_current and self._pers_current != ged_id:
            self._pers_history.append(self._pers_current)
        self._pers_current = ged_id
        self._pers_render_tree(ged_id)
        self._pers_render_detail(ged_id)

    def _pers_go_back(self):
        if self._pers_history:
            self._pers_navigate(self._pers_history.pop(), push=False)

    # ── Stammbaum (Canvas) ────────────────────────────────────────────────
    def _pers_render_tree(self, ged_id: str):
        tc = self._pers_canvas
        tc.delete("all")
        tc.update_idletasks()
        cw = max(tc.winfo_width(), 820)

        p = self._pers_get(ged_id)
        if not p:
            tc.create_text(cw // 2, 60, text="Person nicht gefunden.",
                           fill=_MUTED, font=("Segoe UI", 10))
            tc.configure(scrollregion=(0, 0, cw, 120))
            return

        parents  = _loads(p.get("parents_json"))
        spouses  = _loads(p.get("spouses_json"))
        children = _loads(p.get("children_json"))
        siblings = _loads(p.get("siblings_json"))

        # Großeltern je Elternteil sammeln
        grandparents: list[str] = []
        par_gp_map: dict[str, list[str]] = {}
        for par in parents:
            pd = self._pers_get(par)
            gps = _loads(pd.get("parents_json")) if pd else []
            par_gp_map[par] = gps
            grandparents.extend(gps)

        sib_l = [s for s in siblings[:3] if s != ged_id][:3]
        sib_r = [s for s in siblings[3:6] if s != ged_id][:3]
        chi   = children[:8]
        gp_sh = list(dict.fromkeys(grandparents))[:8]
        sp_sh = [s for s in spouses[:2] if s]

        all_ids = list(dict.fromkeys(
            [ged_id] + parents + sp_sh + chi + sib_l + sib_r + gp_sh))
        persons = self._pers_batch(all_ids)

        CW, CH = 120, 80
        SW, SH = 92, 62
        HG, CONN = 14, 24

        rows: list[str] = []
        if gp_sh:   rows.append("gp")
        if parents: rows.append("par")
        rows.append("foc")
        if chi:     rows.append("chi")
        y_pos, cur_y = {}, 26
        for row in rows:
            y_pos[row] = cur_y
            cur_y += (SH if row in ("gp", "chi") else CH) + CONN + 14
        total_h = cur_y + 16
        cx = cw // 2

        def pdata(xid):
            return persons.get(str(xid)) or self._pers_get(xid) or {}

        def pname(xid):
            d = pdata(xid)
            n = f"{(d.get('given_name') or '').strip()} {(d.get('surname') or '').strip()}".strip()
            return (n or str(xid)), _years(d.get("birth_year"), d.get("death_year"))

        def draw_card(x, y, xid, small=False, focus=False):
            w = SW if small else CW
            h = SH if small else CH
            sex = pdata(xid).get("sex", "")
            name, yrs = pname(xid)
            base = _CARD_M if sex == "M" else _CARD_F if sex == "F" else _CARD_N
            if focus:
                base = _FOCUS
            avt = _lighten(base, 14)
            tag = f"pp_{xid}"
            tc.create_rectangle(x, y, x+w, y+h, fill="#b9c2cc", outline="", tags=tag)
            tc.create_rectangle(x+2, y+2, x+w-2, y+h-2, fill=base, outline="", tags=tag)
            avt_h = max(20, int(h*0.38))
            tc.create_rectangle(x+2, y+2, x+w-2, y+2+avt_h, fill=avt, outline="", tags=tag)
            hx = x + w//2
            hr = max(6, int(w*0.09))
            tc.create_oval(hx-hr, y+4, hx+hr, y+4+hr*2, fill="#ffffff",
                           outline="#9aa4ae", tags=tag)
            bw = max(9, int(w*0.19))
            tc.create_oval(hx-bw, y+avt_h-4, hx+bw, y+avt_h+max(4, int(avt_h*0.25)),
                           fill="#ffffff", outline="#9aa4ae", tags=tag)
            fsz = 7 if small else 9
            tc.create_text(hx, y+avt_h+5, text=name, fill=_TXT,
                           font=("Segoe UI", fsz), anchor="n", width=w-8, tags=tag)
            if yrs:
                tc.create_text(hx, y+h-3, text=yrs, fill=_MUTED,
                               font=("Segoe UI", 6 if small else 7),
                               anchor="s", tags=tag)
            tc.tag_bind(tag, "<Button-1>", lambda e, i=xid: self._pers_navigate(i))
            tc.tag_bind(tag, "<Enter>", lambda e: tc.configure(cursor="hand2"))
            tc.tag_bind(tag, "<Leave>", lambda e: tc.configure(cursor=""))
            return x+w//2, y, y+h

        def vline(x, y1, y2):
            if y1 != y2:
                tc.create_line(x, y1, x, y2, fill=_LINE, dash=(2, 3))

        def hline(y, x1, x2):
            if x1 != x2:
                tc.create_line(min(x1, x2), y, max(x1, x2), y, fill=_LINE)

        def label(y, text):
            tc.create_text(6, y, text=text, fill=_MUTED,
                           font=("Segoe UI", 8, "bold"), anchor="nw")

        # Fokuszeile (Geschwister | Fokus | Geschwister)
        foc_y = y_pos["foc"]
        foc_row = sib_l + [ged_id] + sib_r
        n_foc = len(foc_row)
        foc_idx = len(sib_l)
        focal_left = foc_idx * (CW + HG)
        row_start = cx - focal_left - CW//2
        foc_mids, foc_tops = {}, {}
        for i, xid in enumerate(foc_row):
            rx = row_start + i * (CW + HG)
            mx, ty, _ = draw_card(rx, foc_y, xid, focus=(xid == ged_id))
            foc_mids[xid] = mx; foc_tops[xid] = ty
        focal_mid = foc_mids[ged_id]
        focal_top = foc_tops[ged_id]
        focal_bot = foc_y + CH
        label(foc_y, f"Geschwister ({len(siblings)}) · Fokus" if siblings else "Fokus")

        # Partner rechts
        if sp_sh:
            sp_x = row_start + n_foc * (CW + HG) + 6
            for i, sp in enumerate(sp_sh):
                sym = sp_x + i * (CW + HG + 22)
                tc.create_text(sym+10, foc_y+CH//2, text="⚭", fill=_MUTED,
                               font=("Segoe UI", 14))
                draw_card(sym+22, foc_y, sp)

        # Elternzeile
        par_mids = {}
        if parents:
            par_y = y_pos["par"]
            n_par = len(parents)
            par_sx = cx - (n_par*CW + (n_par-1)*HG)//2
            for i, par in enumerate(parents):
                rx = par_sx + i*(CW+HG)
                mx, _, _ = draw_card(rx, par_y, par)
                par_mids[par] = mx
            label(par_y, "Eltern")
            mid_y = par_y + CH + CONN//2
            if len(parents) == 2:
                a, b = par_mids[parents[0]], par_mids[parents[1]]
                vline(a, par_y+CH, mid_y); vline(b, par_y+CH, mid_y)
                hline(mid_y, a, b); vline((a+b)//2, mid_y, focal_top)
            elif len(parents) == 1:
                vline(par_mids[parents[0]], par_y+CH, focal_top)

            # Großeltern
            if gp_sh:
                gp_y = y_pos["gp"]
                n_gp = len(gp_sh)
                gp_sx = cx - (n_gp*SW + (n_gp-1)*HG)//2
                gp_mids = {}
                for i, gp in enumerate(gp_sh):
                    rx = gp_sx + i*(SW+HG)
                    mx, _, _ = draw_card(rx, gp_y, gp, small=True)
                    gp_mids[gp] = mx
                label(gp_y, "Großeltern")
                for par in parents:
                    mxs = [gp_mids[g] for g in par_gp_map.get(par, []) if g in gp_mids]
                    if not mxs:
                        continue
                    gy = gp_y + SH + CONN//2
                    if len(mxs) >= 2:
                        vline(mxs[0], gp_y+SH, gy); vline(mxs[-1], gp_y+SH, gy)
                        hline(gy, mxs[0], mxs[-1])
                        vline((mxs[0]+mxs[-1])//2, gy, par_y)
                    else:
                        vline(mxs[0], gp_y+SH, par_y)

        # Geschwister-Querbalken
        if sib_l or sib_r:
            in_row = [s for s in foc_row if s in foc_mids]
            if in_row:
                bar_y = focal_top - CONN//2
                hline(bar_y, foc_mids[in_row[0]], foc_mids[in_row[-1]])
                for xid in in_row:
                    vline(foc_mids[xid], bar_y, foc_tops[xid])
                if parents:
                    if len(parents) == 2:
                        bcx = (par_mids[parents[0]] + par_mids[parents[1]])//2
                    else:
                        bcx = par_mids[parents[0]]
                    vline(bcx, y_pos["par"]+CH+CONN//2, bar_y)

        # Kinder
        if chi:
            chi_y = y_pos["chi"]
            n_chi = len(chi)
            chi_sx = focal_mid - (n_chi*SW + (n_chi-1)*HG)//2
            mids = []
            for i, ch in enumerate(chi):
                rx = chi_sx + i*(SW+HG)
                mx, _, _ = draw_card(rx, chi_y, ch, small=True)
                mids.append(mx)
            if len(children) > len(chi):
                tc.create_text(chi_sx + n_chi*(SW+HG) + 6, chi_y+SH//2,
                               text=f"+{len(children)-len(chi)} weitere",
                               fill=_MUTED, font=("Segoe UI", 8), anchor="w")
            label(chi_y, f"Kinder ({len(children)})")
            cy = focal_bot + CONN//2
            vline(focal_mid, focal_bot, cy)
            if mids:
                hline(cy, mids[0], mids[-1])
                for mx in mids:
                    vline(mx, cy, chi_y)

        tc.update_idletasks()
        bbox = tc.bbox("all")
        if bbox:
            pad = 22
            tc.configure(scrollregion=(bbox[0]-pad, bbox[1]-pad,
                                       bbox[2]+pad, bbox[3]+pad))
        else:
            tc.configure(scrollregion=(0, 0, cw, total_h))

    # ── Detail + DNA-Matches ──────────────────────────────────────────────
    def _pers_render_detail(self, ged_id: str):
        for w in self._pers_detail.winfo_children():
            w.destroy()
        p = self._pers_get(ged_id)
        if not p:
            return
        name = f"{(p.get('given_name') or '').strip()} {(p.get('surname') or '').strip()}".strip()
        ttk.Label(self._pers_detail, text=name or ged_id,
                  font=("Segoe UI", 13, "bold"), wraplength=300).pack(
            anchor="w", padx=10, pady=(10, 2))
        meta = f"{ged_id} · {p.get('sex') or '?'} · {_SRC_LABEL.get(p.get('source',''), p.get('source',''))}"
        ttk.Label(self._pers_detail, text=meta, foreground=_MUTED).pack(
            anchor="w", padx=10)

        def fact(lbl, val):
            if not val:
                return
            r = ttk.Frame(self._pers_detail); r.pack(fill="x", padx=10, pady=1)
            ttk.Label(r, text=lbl, width=10, foreground=_MUTED).pack(side="left")
            ttk.Label(r, text=str(val), wraplength=210).pack(side="left")

        fact("Geboren", _years(p.get("birth_year"), "") or None)
        fact("Geburtsort", p.get("birth_place"))
        fact("Gestorben", _years(p.get("death_year"), "") or None)
        fact("Sterbeort", p.get("death_place"))
        if p.get("sosa_number"):
            fact("SOSA", p.get("sosa_number"))

        self._pers_render_dna(ged_id)

    def _pers_render_dna(self, ged_id: str):
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    "SELECT m.display_name, m.shared_cm, m.predicted_relationship "
                    "FROM gedcom_links gl "
                    "JOIN matches m ON m.match_guid = gl.match_guid "
                    "WHERE gl.ged_id = ? "
                    "ORDER BY m.shared_cm DESC LIMIT 30", (ged_id,)).fetchall()
        except Exception:
            return
        if not rows:
            return
        ttk.Separator(self._pers_detail).pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(self._pers_detail, text=f"🧬 DNA-Matches ({len(rows)})",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10)
        tree = ttk.Treeview(self._pers_detail, columns=("n", "cm", "rel"),
                            show="headings", height=min(12, len(rows)))
        tree.heading("n", text="Name"); tree.heading("cm", text="cM")
        tree.heading("rel", text="Beziehung")
        tree.column("n", width=120, stretch=True)
        tree.column("cm", width=46, anchor="e", stretch=False)
        tree.column("rel", width=110, stretch=True)
        for r in rows:
            cm = r["shared_cm"] or 0
            tree.insert("", "end", values=(
                (r["display_name"] or "—")[:28], f"{cm:.0f}",
                r["predicted_relationship"] or ""))
        tree.pack(fill="both", expand=True, padx=10, pady=(2, 8))
