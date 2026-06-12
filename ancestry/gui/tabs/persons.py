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
import os
import re
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk

from ancestry.paths import ROOT
from ancestry.gui.state import AppState

# ── Pfarrei-/Konfessions-Lookup (Matricula) ───────────────────────────────────
# Übernommen aus dem früheren Standalone-Datenviewer: ordnet einem Geburtsort
# eine Matricula-Pfarrei + Konfession zu. Schema-unabhängig (reine JSON-Datei).
_PARISH_JSON = os.path.join(str(ROOT), "ancestry", "tools", "matricula_parishes.json")
_parish_lookup_cache: dict | None = None


def _parish_lookup() -> dict:
    global _parish_lookup_cache
    if _parish_lookup_cache is None:
        try:
            with open(_PARISH_JSON, encoding="utf-8") as f:
                _parish_lookup_cache = json.load(f)
        except Exception:
            _parish_lookup_cache = {}
    return _parish_lookup_cache


def _parish_for(birth_place: str) -> dict | None:
    """Pfarrei-Info für einen Geburtsort (direkter, Kurz- oder Teil-Match)."""
    lookup = _parish_lookup()
    if not birth_place or not lookup:
        return None
    place = birth_place.strip().lower()
    if place in lookup:
        return lookup[place]
    short = re.split(r"[,\(]", place)[0].strip()
    if short and short in lookup:
        return lookup[short]
    for key, val in lookup.items():
        if key and (key in place or place in key):
            return val
    return None

# ── helle Karten-Palette ──────────────────────────────────────────────────────
_CARD_M   = "#cfe0f5"   # männlich  (blau)
_CARD_F   = "#f5d6d6"   # weiblich  (rosa)
_CARD_N   = "#e6e6e6"   # unbekannt
_FOCUS    = "#fff3cd"   # Fokusperson (gelb)
_LINE     = "#9aa4ae"
_TXT      = "#1f2327"
_MUTED    = "#6c7086"
_KATH     = "#1565c0"   # katholisch (blau)
_EV       = "#558b2f"   # evangelisch (grün)
_LINK     = "#1a56c4"   # anklickbare Verknüpfung

_SRC_LABEL = {"": "Alle Quellen", "gedcom": "GEDCOM", "anverwandte": "Webtrees",
              "wikitree": "WikiTree"}

# Konfessions-Filter: Label → interner Schlüssel ('' = alle, 'unbekannt' = keine Pfarrei)
_CONF_LABELS = {"": "Alle Konfessionen", "kath": "Katholisch",
                "ev": "Evangelisch", "unbekannt": "Unbekannt"}


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


def _kinship_from_sosa(sosa) -> str:
    """Verwandtschaftsgrad zur Wurzelperson aus der Sosa-Stradonitz-Nummer.

    Sosa 1 = Wurzel, 2=Vater, 3=Mutter, 4=Vaters Vater … Die Binärdarstellung
    (ohne führende 1) ergibt den F/M-Pfad (0=Vater, 1=Mutter), den render_kinship
    in eine deutsche Bezeichnung übersetzt. Nicht-Vorfahren (sosa 0) → ''."""
    try:
        n = int(sosa or 0)
    except (TypeError, ValueError):
        return ""
    if n < 1:
        return ""
    if n == 1:
        return "Wurzelperson"
    path = "".join("F" if b == "0" else "M" for b in bin(n)[3:])
    try:
        from ancestry.core.treematch import render_kinship
        return render_kinship(path)
    except Exception:
        return ""


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
        # Konfessions-Filter (aus Geburtsort via Matricula-Pfarrei)
        self._pers_conf = tk.StringVar(value="Alle Konfessionen")
        conf_cb = ttk.Combobox(bar, textvariable=self._pers_conf, width=13,
                               state="readonly",
                               values=list(_CONF_LABELS.values()))
        conf_cb.pack(side="left", padx=4)
        conf_cb.bind("<<ComboboxSelected>>", lambda _: self._pers_reload_list())

        cols = ("name", "years", "rel")
        self._pers_list = ttk.Treeview(left, columns=cols, show="headings",
                                       selectmode="browse", height=20)
        self._pers_list.heading("name", text="Name")
        self._pers_list.heading("years", text="Jahre")
        self._pers_list.heading("rel", text="Verwandtschaft")
        self._pers_list.column("name", width=170, stretch=True)
        self._pers_list.column("years", width=82, anchor="center", stretch=False)
        self._pers_list.column("rel", width=120, stretch=True)
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
        ttk.Label(nav, text="  Generationen:").pack(side="left")
        self._pers_depth = tk.IntVar(value=2)
        depth_sb = ttk.Spinbox(nav, from_=1, to=5, width=3, textvariable=self._pers_depth,
                               command=self._pers_redraw_tree)
        depth_sb.pack(side="left", padx=(2, 8))
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

    def _pers_conf_key(self) -> str:
        label = self._pers_conf.get() if hasattr(self, "_pers_conf") else ""
        for k, v in _CONF_LABELS.items():
            if v == label:
                return k
        return ""

    def _pers_reload_list(self, *_):
        q = (self._pers_search.get() or "").strip()
        src = self._pers_source_key()
        conf = self._pers_conf_key()
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
            # Bei Konfessionsfilter mehr Zeilen holen (Filterung erfolgt in Python)
            limit = 4000 if conf else 600
            sql = (f"SELECT ged_id, given_name, surname, birth_year, death_year, "
                   f"sex, birth_place, sosa_number FROM gedcom_persons {where} "
                   f"ORDER BY surname, given_name LIMIT {limit}")
            try:
                with self._db._cursor() as cur:
                    rows = cur.execute(sql, params).fetchall()
            except Exception as exc:
                self.after(0, lambda e=exc: self._pers_count.set(f"⚠ {e}"))
                return
            data = []
            for r in rows:
                if conf:
                    info = _parish_for(r["birth_place"] or "")
                    person_conf = (info or {}).get("confession", "") or "unbekannt"
                    if person_conf != conf:
                        continue
                data.append((
                    r["ged_id"],
                    f"{(r['given_name'] or '').strip()} {(r['surname'] or '').strip()}".strip()
                    or r["ged_id"],
                    _years(r["birth_year"], r["death_year"]),
                    _kinship_from_sosa(r["sosa_number"])))
                if len(data) >= 600:
                    break
            self.after(0, lambda: self._pers_fill_list(data, gen))
        threading.Thread(target=_fetch, daemon=True, name="pers-list").start()

    def _pers_fill_list(self, data, gen):
        if getattr(self, "_pers_list_gen", 0) != gen:
            return
        self._pers_list.delete(*self._pers_list.get_children())
        for ged_id, name, years, rel in data:
            self._pers_list.insert("", "end", iid=ged_id, values=(name, years, rel))
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
        try:
            self._pers_render_tree(ged_id)
        except Exception as exc:
            self._pers_canvas.delete("all")
            self._pers_canvas.create_text(
                30, 30, anchor="nw", fill="#b00020",
                text=f"Stammbaum konnte nicht gezeichnet werden:\n{exc}")
        try:
            self._pers_render_detail(ged_id)
        except Exception:
            pass

    def _pers_redraw_tree(self, *_):
        """Zeichnet den Baum der aktuellen Person neu (z. B. nach Tiefenänderung)."""
        if self._pers_current:
            try:
                self._pers_render_tree(self._pers_current)
            except Exception:
                pass

    def _pers_go_back(self):
        if self._pers_history:
            self._pers_navigate(self._pers_history.pop(), push=False)

    # ── Stammbaum (Canvas) ────────────────────────────────────────────────
    def _pers_render_tree(self, ged_id: str):
        tc = self._pers_canvas
        tc.delete("all")
        tc.update_idletasks()
        try:
            depth = max(1, min(5, int(self._pers_depth.get())))
        except Exception:
            depth = 2

        focus = self._pers_get(ged_id)
        if not focus:
            tc.create_text(60, 50, anchor="nw", text="Person nicht gefunden.",
                           fill=_MUTED, font=("Segoe UI", 10))
            tc.configure(scrollregion=(0, 0, 820, 120))
            return

        # ── Vorfahren in Sosa-Slots sammeln: anc[(gen, slot)] = ged_id ──
        # gen 1 = Eltern (slot 0=Vater, 1=Mutter); pro Generation 2^gen Slots.
        anc: dict = {}
        for i, pid in enumerate(_loads(focus.get("parents_json"))[:2]):
            if pid:
                anc[(1, i)] = pid
        for g in range(1, depth):
            for slot in range(2 ** g):
                pid = anc.get((g, slot))
                if not pid:
                    continue
                pd = self._pers_get(pid)
                for i, gp in enumerate((_loads(pd.get("parents_json")) if pd else [])[:2]):
                    if gp:
                        anc[(g + 1, 2 * slot + i)] = gp

        siblings = [s for s in _loads(focus.get("siblings_json")) if s != ged_id]
        spouses  = [s for s in _loads(focus.get("spouses_json")) if s]
        children = _loads(focus.get("children_json"))

        all_ids = [ged_id] + list(anc.values()) + siblings[:6] + spouses[:2] + children[:12]
        all_ids = [str(i) for i in all_ids if i]
        persons = self._pers_batch(all_ids)

        # DNA-Treffer vorab bestimmen (eine Abfrage statt pro Karte)
        dna_ids = set()
        if all_ids:
            try:
                ph = ",".join("?" * len(all_ids))
                with self._db._cursor() as cur:
                    dna_ids = {str(r[0]) for r in cur.execute(
                        f"SELECT DISTINCT ged_id FROM gedcom_links WHERE ged_id IN ({ph})",
                        all_ids).fetchall()}
            except Exception:
                dna_ids = set()

        def pdata(xid):
            return persons.get(str(xid)) or self._pers_get(xid) or {}

        def pname(xid):
            d = pdata(xid)
            n = f"{(d.get('given_name') or '').strip()} {(d.get('surname') or '').strip()}".strip()
            return (n or str(xid)), _years(d.get("birth_year"), d.get("death_year"))

        # ── Geometrie ──
        SW, SH = 96, 56
        CW, CH = 132, 78
        ROW = max(SH, CH) + 46
        HGAP = 14
        slots_bottom = 2 ** depth
        canvas_w = max(tc.winfo_width(), slots_bottom * (SW + HGAP) + 40, 860)
        y_focus = 36 + depth * ROW

        def label(x, y, text):
            tc.create_text(x, y, text=text, fill=_MUTED, anchor="nw",
                           font=("Segoe UI", 8, "bold"))

        def draw_card(cx_center, top_y, xid, focus_card=False):
            w = CW if focus_card else SW
            h = CH if focus_card else SH
            x = cx_center - w // 2
            d = pdata(xid)
            sex = d.get("sex", "")
            base = _CARD_M if sex == "M" else _CARD_F if sex == "F" else _CARD_N
            if focus_card:
                base = _FOCUS
            is_dna = str(xid) in dna_ids
            outline = "#0aa6a6" if is_dna else "#b9c2cc"
            tag = f"pp_{xid}"
            tc.create_rectangle(x, top_y, x + w, top_y + h, fill=base,
                                outline=outline, width=3 if is_dna else 1, tags=tag)
            name, yrs = pname(xid)
            fsz = 9 if focus_card else 8
            tc.create_text(x + w // 2, top_y + 6, text=name, fill=_TXT, anchor="n",
                           width=w - 8, font=("Segoe UI", fsz), tags=tag)
            if is_dna:
                tc.create_text(x + w - 4, top_y + 4, text="🧬", anchor="ne",
                               font=("Segoe UI", 8), tags=tag)
            if yrs:
                tc.create_text(x + w // 2, top_y + h - 4, text=yrs, fill=_MUTED,
                               anchor="s", font=("Segoe UI", 7), tags=tag)
            tc.tag_bind(tag, "<Button-1>", lambda e, i=xid: self._pers_navigate(i))
            tc.tag_bind(tag, "<Enter>", lambda e: tc.configure(cursor="hand2"))
            tc.tag_bind(tag, "<Leave>", lambda e: tc.configure(cursor=""))
            return cx_center, top_y, top_y + h

        def connect(x1, y1, x2, y2):
            if (x1, y1) != (x2, y2):
                tc.create_line(x1, y1, x2, y2, fill=_LINE)

        # ── Fokus-Reihe (Geschwister | Fokus | Geschwister) + Partner ──
        sib_l = siblings[:3][::-1]
        sib_r = siblings[3:6]
        foc_row = sib_l + [ged_id] + sib_r
        foc_n = len(foc_row)
        start_x = canvas_w // 2 - (foc_n * (CW + HGAP)) // 2 + CW // 2
        focus_mid = focus_top = focus_bot = None
        for i, xid in enumerate(foc_row):
            cxx = start_x + i * (CW + HGAP)
            mid, top, bot = draw_card(cxx, y_focus, xid, focus_card=(xid == ged_id))
            if xid == ged_id:
                focus_mid, focus_top, focus_bot = mid, top, bot
        if focus_mid is None:
            focus_mid, focus_top, focus_bot = canvas_w // 2, y_focus, y_focus + CH
        label(6, y_focus, f"Geschwister ({len(siblings)}) · Fokus" if siblings else "Fokus")
        for j, sp in enumerate(spouses[:2]):
            sx = start_x + foc_n * (CW + HGAP) + j * (CW + HGAP + 20)
            tc.create_text(sx - HGAP, y_focus + CH // 2, text="⚭", fill=_MUTED,
                           font=("Segoe UI", 13))
            draw_card(sx + CW // 2, y_focus, sp)

        # ── Vorfahren-Pyramide ──
        pos = {}
        for g in range(1, depth + 1):
            n = 2 ** g
            slot_w = canvas_w / n
            for slot in range(n):
                pid = anc.get((g, slot))
                if not pid:
                    continue
                pos[(g, slot)] = draw_card(slot_w * (slot + 0.5), y_focus - g * ROW, pid)
        for (g, slot), (mx, ty, by) in pos.items():
            if g == 1:
                cm, ct = focus_mid, focus_top
            else:
                cpos = pos.get((g - 1, slot // 2))
                if not cpos:
                    continue
                cm, ct = cpos[0], cpos[1]
            connect(mx, by, cm, ct)
        for g in range(1, depth + 1):
            if any((g, s) in pos for s in range(2 ** g)):
                label(6, y_focus - g * ROW, "Eltern" if g == 1 else f"{g}. Generation ↑")

        # ── Kinder ──
        if children:
            chi = children[:12]
            n = len(chi)
            sx = int(focus_mid) - (n * (SW + HGAP)) // 2 + SW // 2
            yy = y_focus + ROW
            label(6, yy, f"Kinder ({len(children)})")
            for i, ch in enumerate(chi):
                mid, top, _ = draw_card(sx + i * (SW + HGAP), yy, ch)
                connect(focus_mid, focus_bot, mid, top)
            if len(children) > n:
                tc.create_text(sx + n * (SW + HGAP), yy + SH // 2, anchor="w",
                               text=f"+{len(children)-n} weitere", fill=_MUTED,
                               font=("Segoe UI", 8))

        tc.update_idletasks()
        bbox = tc.bbox("all")
        if bbox:
            pad = 24
            tc.configure(scrollregion=(bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad))
        else:
            tc.configure(scrollregion=(0, 0, canvas_w, y_focus + 2 * ROW))

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
        kin = _kinship_from_sosa(p.get("sosa_number"))
        if kin:
            ttk.Label(self._pers_detail, text=f"⛓ {kin}", foreground=_LINK,
                      font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10)

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

        # Zusammengeführte Detail-Abschnitte (früher: separater Datenviewer)
        self._pers_render_parish(p)        # Kirchspiel / Konfession (Matricula)
        self._pers_render_relations(p)     # Eltern/Partner/Kinder/Geschwister (Links)
        self._pers_render_xref(ged_id)     # GEDCOM-Verknüpfung (Quellen-Dedup)
        self._pers_render_dna(ged_id)      # DNA-Matches (Anker)

    # ── Detail-Abschnitt: Beziehungen (anklickbar) ────────────────────────────
    def _pers_render_relations(self, p: dict):
        groups = [
            ("Elternteil", _loads(p.get("parents_json"))),
            ("Partner",    _loads(p.get("spouses_json"))),
            ("Kind",       _loads(p.get("children_json"))),
            ("Geschwister", _loads(p.get("siblings_json"))),
        ]
        if not any(ids for _, ids in groups):
            return
        self._pers_hdr("👪 Beziehungen")
        batch = self._pers_batch([i for _, ids in groups for i in ids])

        def _name(xid):
            d = batch.get(str(xid)) or {}
            n = f"{(d.get('given_name') or '').strip()} {(d.get('surname') or '').strip()}".strip()
            yrs = _years(d.get("birth_year"), d.get("death_year"))
            return (n or str(xid)) + (f" ({yrs})" if yrs else "")

        for label, ids in groups:
            for xid in ids:
                row = ttk.Frame(self._pers_detail); row.pack(fill="x", padx=10, pady=1)
                ttk.Label(row, text=label, width=10, foreground=_MUTED).pack(side="left")
                lk = ttk.Label(row, text=_name(xid), foreground=_LINK,
                               cursor="hand2", wraplength=210)
                lk.pack(side="left")
                lk.bind("<Button-1>", lambda e, i=str(xid): self._pers_navigate(i))

    # ── Detail-Abschnitt: Kirchspiel / Konfession (Matricula) ──────────────────
    def _pers_hdr(self, text: str):
        ttk.Separator(self._pers_detail).pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(self._pers_detail, text=text,
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10)

    def _pers_render_parish(self, p: dict):
        parish = _parish_for(p.get("birth_place") or "")
        if not parish:
            return
        self._pers_hdr("⛪ Kirchspiel (Matricula)")
        conf = parish.get("confession", "")
        conf_label = ("Katholisch" if conf == "kath"
                      else "Evangelisch" if conf == "ev"
                      else (conf or "—"))
        conf_color = (_KATH if conf == "kath" else _EV if conf == "ev" else _TXT)
        r = ttk.Frame(self._pers_detail); r.pack(fill="x", padx=10, pady=1)
        ttk.Label(r, text="Konfession", width=10, foreground=_MUTED).pack(side="left")
        ttk.Label(r, text=conf_label, foreground=conf_color,
                  font=("Segoe UI", 9, "bold")).pack(side="left")
        for lbl, key in (("Pfarrei", "parish"), ("Diözese", "diocese")):
            if parish.get(key):
                rr = ttk.Frame(self._pers_detail); rr.pack(fill="x", padx=10, pady=1)
                ttk.Label(rr, text=lbl, width=10, foreground=_MUTED).pack(side="left")
                ttk.Label(rr, text=str(parish[key]), wraplength=210).pack(side="left")
        if parish.get("parent_id"):
            rr = ttk.Frame(self._pers_detail); rr.pack(fill="x", padx=10, pady=1)
            ttk.Label(rr, text="Mutterpfarrei", width=10, foreground=_MUTED).pack(side="left")
            ttk.Label(rr, text=str(parish["parent_id"]).replace("-", " ").title(),
                      wraplength=210).pack(side="left")
        if parish.get("founded"):
            rr = ttk.Frame(self._pers_detail); rr.pack(fill="x", padx=10, pady=1)
            ttk.Label(rr, text="Gegründet", width=10, foreground=_MUTED).pack(side="left")
            ttk.Label(rr, text=str(parish["founded"])).pack(side="left")

    # ── Detail-Abschnitt: GEDCOM-Verknüpfung (Quellen-Dedup) ───────────────────
    def _pers_render_xref(self, ged_id: str):
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    "SELECT ged_id_primary, source_primary, ged_id_other, "
                    "source_other, status, score FROM gedcom_person_xref "
                    "WHERE (ged_id_primary=? OR ged_id_other=?) "
                    "AND status != 'rejected' LIMIT 8",
                    (ged_id, ged_id)).fetchall()
        except Exception:
            return
        if not rows:
            return
        self._pers_hdr("🔗 GEDCOM-Verknüpfung")
        for r in rows:
            if str(r["ged_id_primary"]) == str(ged_id):
                other_id, other_src = r["ged_id_other"], r["source_other"]
            else:
                other_id, other_src = r["ged_id_primary"], r["source_primary"]
            status = r["status"] or "auto"
            mark = "✓ bestätigt" if status == "confirmed" else "~ automatisch"
            line = ttk.Frame(self._pers_detail); line.pack(fill="x", padx=10, pady=1)
            ttk.Label(line, text=_SRC_LABEL.get(other_src, other_src),
                      width=10, foreground=_MUTED).pack(side="left")
            lbl = ttk.Label(line, text=f"{other_id}  ({mark})",
                            foreground=_LINK, cursor="hand2", wraplength=210)
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, i=str(other_id): self._pers_navigate(i))

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
