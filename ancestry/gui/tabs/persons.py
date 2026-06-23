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
import logging
import os
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from ancestry.core.place_concordance import map_place
from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import register_lang
from ancestry.gui.widgets.tooltip import register_tooltip

log = logging.getLogger(__name__)
from ancestry.paths import ROOT

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


def _descendant_label(d: int) -> str:
    """Nachfahren-Bezeichnung (geschlechtsneutral, Stil wie lib.helpers):
    Kind, Enkelkind, Urenkelkind, N-fach Urenkelkind."""
    if d <= 0:
        return ""
    if d == 1:
        return "Kind"
    if d == 2:
        return "Enkelkind"
    if d == 3:
        return "Urenkelkind"
    return f"{d-2}-fach Urenkelkind"


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

    def __init__(self, parent: tk.Widget, state: AppState,
                 on_goto_matches=None):
        super().__init__(parent)
        self._state = state
        self._on_goto_matches = on_goto_matches
        self._pers_history: list[str] = []
        self._pers_current: str | None = None
        self._search_after_id: str | None = None  # B3: Debounce-Handle
        self._build()

    def set_on_goto_matches(self, cb):
        """Setzt den Callback zum Wechsel in den Matches-Tab."""
        self._on_goto_matches = cb

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
        self._pers_search.trace_add("write", self._on_pers_search_changed)
        _search_e = ttk.Entry(bar, textvariable=self._pers_search, width=18)
        _search_e.pack(side="left", padx=4)
        register_tooltip(_search_e, "tt.pe_search", self._state)
        self._pers_source = tk.StringVar(value="Alle Quellen")
        src_cb = ttk.Combobox(bar, textvariable=self._pers_source, width=12,
                              state="readonly",
                              values=list(_SRC_LABEL.values()))
        src_cb.pack(side="left", padx=4)
        src_cb.bind("<<ComboboxSelected>>", lambda _: self._pers_reload_list())
        register_tooltip(src_cb, "tt.pe_src", self._state)
        # Konfessions-Filter (aus Geburtsort via Matricula-Pfarrei)
        self._pers_conf = tk.StringVar(value="Alle Konfessionen")
        conf_cb = ttk.Combobox(bar, textvariable=self._pers_conf, width=13,
                               state="readonly",
                               values=list(_CONF_LABELS.values()))
        conf_cb.pack(side="left", padx=4)
        conf_cb.bind("<<ComboboxSelected>>", lambda _: self._pers_reload_list())
        register_tooltip(conf_cb, "tt.pe_conf", self._state)
        _b = ttk.Button(bar, text="🔍 Dubletten", command=self._pers_open_dedup)
        _b.pack(side="left", padx=4)
        register_tooltip(_b, "tt.pe_dedup", self._state)
        _bw = ttk.Button(bar, text="🧱 Brick-Wall-Analyse",
                         command=self._pers_open_brickwall)
        _bw.pack(side="left", padx=4)
        _bg = ttk.Button(bar, text="📤 GRAMPS exportieren",
                         command=self._pers_export_gramps)
        _bg.pack(side="left", padx=4)

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
        # A1: Spaltenbreiten speichern wenn der Nutzer eine Spalte zieht
        self._pers_list.bind("<ButtonRelease-1>", self._pers_save_col_widths)
        self._pers_count = tk.StringVar(value="")
        ttk.Label(left, textvariable=self._pers_count,
                  foreground=_MUTED).pack(side="bottom", anchor="w")
        self._build_entity_resolution_panel(left)

        # ── Mitte: Stammbaum-Canvas ───────────────────────────────────────
        mid = ttk.Frame(outer)
        outer.add(mid, weight=3)
        nav = ttk.Frame(mid); nav.pack(fill="x")
        _b = register_lang(self._state, ttk.Button(nav, text=self._state.t("pe.b_back"), command=self._pers_go_back), "pe.b_back")
        _b.pack(side="left", pady=(0, 4))
        register_tooltip(_b, "tt.pe_back", self._state)
        ttk.Label(nav, text="  Generationen:").pack(side="left")
        self._pers_depth = tk.IntVar(value=2)
        depth_sb = ttk.Spinbox(nav, from_=1, to=5, width=3, textvariable=self._pers_depth,
                               command=self._pers_redraw_tree)
        depth_sb.pack(side="left", padx=(2, 8))
        register_tooltip(depth_sb, "tt.pe_depth", self._state)
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

    def _pers_open_dedup(self):
        try:
            from ancestry.gui.analysis.dedup_review import open_dedup_review
            open_dedup_review(self.winfo_toplevel(), self._db)
        except Exception as exc:
            messagebox.showerror("Dubletten", str(exc))

    # ── A2: Brick-Wall-Finder ─────────────────────────────────────────────────
    def _pers_open_brickwall(self):
        """Öffnet den Brick-Wall-Finder-Dialog (A2)."""
        try:
            from ancestry.gui.analysis.brickwall_finder import show_brickwall_finder
            show_brickwall_finder(self, self._state)
        except Exception as exc:
            log.exception("Brick-Wall-Finder Fehler")
            messagebox.showerror("Brick-Wall-Analyse", str(exc))

    # ── D3: GRAMPS-Export ─────────────────────────────────────────────────────
    def _pers_export_gramps(self):
        """Exportiert Vorfahren-Gruppen als Gramps-XML (D3)."""
        test_guid = getattr(self._state, "current_test_guid", None)
        if not test_guid:
            messagebox.showwarning(
                "GRAMPS exportieren",
                "Kein DNA-Kit ausgewählt.\n\n"
                "Bitte zuerst im Download-Tab ein Kit auswählen.")
            return
        try:
            groups = self._db.get_pedigree_groups(
                test_guid, min_matches=2, mode="person")
        except Exception as exc:
            messagebox.showerror("GRAMPS exportieren",
                                 f"Datenbankfehler: {exc}")
            return
        if not groups:
            messagebox.showinfo(
                "GRAMPS exportieren",
                "Keine Vorfahren-Gruppen gefunden.\n\n"
                "Bitte zuerst Ahnentafeln für die Matches laden "
                "(z. B. über den Matches-Tab → 🌳 GEDCOM abgleichen).")
            return
        path = filedialog.asksaveasfilename(
            title="GRAMPS-Export speichern",
            defaultextension=".gramps",
            filetypes=[("GRAMPS", "*.gramps"), ("XML", "*.xml")],
            initialfile="ancestry_dna_ancestors.gramps")
        if not path:
            return

        def _do_export():
            try:
                from ancestry.core.gramps_export import export_gramps
                n = export_gramps(groups, path, mask_living=True)
                self.after(0, lambda: messagebox.showinfo(
                    "GRAMPS exportieren",
                    f"{n} Personen exportiert → {path}\n"
                    "Lebende Personen wurden als [privat] maskiert (DSGVO)."))
            except Exception as exc:  # noqa: BLE001
                log.exception("GRAMPS-Export fehlgeschlagen")
                msg = str(exc)
                self.after(0, lambda m=msg: messagebox.showerror(
                    "GRAMPS exportieren", m))

        threading.Thread(target=_do_export, daemon=True,
                         name="gramps-export").start()

    # ── Datenzugriff ──────────────────────────────────────────────────────
    def _pers_source_key(self) -> str:
        label = self._pers_source.get()
        for k, v in _SRC_LABEL.items():
            if v == label:
                return k
        return ""

    def invalidate_tree_cache(self):
        """Verwirft die gecachte Wurzel-/Vorfahren-Karte. Aufrufen, wenn sich die
        GEDCOM-Daten ändern (z.B. nach einem Import), damit die Stammbaum-Logik
        die neue Wurzelperson erkennt."""
        self._pers_rels_cache = {}
        self._root_anc_cache = None
        self.__dict__.pop("_root_id_cache", None)

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
            self.after(0, self._pers_load_col_widths)  # A1: gespeicherte Breiten laden
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
            # Verwandtschaft in der Liste: alle DIREKTEN Vorfahren der Wurzel
            # (über die einmal berechnete Vorfahrenkarte; deckt auch Webtrees ab).
            # Cousins/Seitenlinien zeigt das Detailpanel (zu teuer pro Zeile).
            # Die Wurzel-Vorfahrenkarte (~176ms BFS) wird NICHT bei jeder Suche
            # neu aufgebaut — sie ändert sich beim Tippen/Filtern nicht. Lazy-Cache
            # in _pers_root_anc_map() baut sie einmalig; Invalidierung via
            # invalidate_tree_cache() (z.B. nach GEDCOM-Import).
            ra = self._pers_root_anc_map()
            rid = self._pers_root_id()
            try:
                from lib.helpers import relationship_label as _rel
            except Exception:
                _rel = None
            data = []
            for r in rows:
                if conf:
                    info = _parish_for(r["birth_place"] or "")
                    person_conf = (info or {}).get("confession", "") or "unbekannt"
                    if person_conf != conf:
                        continue
                gid = str(r["ged_id"])
                if rid and gid == str(rid):
                    rel = "Wurzelperson"
                elif _rel and gid in ra and ra[gid] > 0:
                    rel = _rel(ra[gid], 0, is_target_ancestor=True)
                else:
                    rel = ""
                data.append((
                    r["ged_id"],
                    f"{(r['given_name'] or '').strip()} {(r['surname'] or '').strip()}".strip()
                    or r["ged_id"],
                    _years(r["birth_year"], r["death_year"]),
                    rel))
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

    # ── A1: Persistente Spaltenbreiten ────────────────────────────────────────────
    def _pref_get(self, key: str, default: str = "") -> str:
        """Liest einen Wert aus user_prefs (key/value-Tabelle)."""
        try:
            with self._db._cursor() as cur:
                r = cur.execute(
                    "SELECT value FROM user_prefs WHERE key=?", (key,)
                ).fetchone()
            return str(r[0]) if r else default
        except Exception:
            return default

    def _pref_set(self, key: str, value: str) -> None:
        """Schreibt einen Wert in user_prefs (INSERT OR REPLACE)."""
        try:
            with self._db._cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO user_prefs (key, value) VALUES (?, ?)",
                    (key, value),
                )
                self._db._conn.commit()
        except Exception:
            pass

    def _pers_save_col_widths(self, _event=None) -> None:
        """Speichert die aktuellen Spaltenbreiten des Personen-Treeviews."""
        for col in ("name", "years", "rel"):
            try:
                w = self._pers_list.column(col, "width")
                self._pref_set(f"persons_col_{col}", str(w))
            except Exception:
                pass

    def _pers_load_col_widths(self) -> None:
        """Lädt gespeicherte Spaltenbreiten und wendet sie auf den Treeview an."""
        defaults = {"name": 170, "years": 82, "rel": 120}
        for col, default_w in defaults.items():
            try:
                val = self._pref_get(f"persons_col_{col}", str(default_w))
                w = int(val)
                if w > 0:
                    self._pers_list.column(col, width=w)
            except Exception:
                pass

    # ── B3: Debounced Suche ───────────────────────────────────────────────────────
    def _on_pers_search_changed(self, *_):
        """Entprellt die Personensuche (350 ms) — B3."""
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(350, self._pers_reload_list)

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
        except Exception as exc:
            for w in self._pers_detail.winfo_children():
                w.destroy()
            ttk.Label(self._pers_detail, text=f"Detail-Fehler:\n{exc}",
                      foreground="#b00020", wraplength=300,
                      justify="left").pack(anchor="w", padx=10, pady=10)

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
    def _pers_find_twins(self, ged_id: str, p: dict) -> list[dict]:
        """Findet 'Zwillinge' derselben realen Person in anderen Quellen:
        bestätigte/automatische Links aus gedcom_person_xref plus Fuzzy-Treffer
        (gleicher Nachname + Geburtsjahr ±1, andere ged_id). Für den virtuellen
        Overlay von Webtrees- und GEDCOM-Baum."""
        found: dict[str, bool] = {}
        try:
            with self._db._cursor() as cur:
                for r in cur.execute(
                    "SELECT ged_id_primary, ged_id_other FROM gedcom_person_xref "
                    "WHERE (ged_id_primary=? OR ged_id_other=?) AND status!='rejected'",
                    (ged_id, ged_id)).fetchall():
                    other = (r["ged_id_other"] if str(r["ged_id_primary"]) == str(ged_id)
                             else r["ged_id_primary"])
                    if str(other) != str(ged_id):
                        found[str(other)] = True
                sn = (p.get("surname") or "").strip()
                by = p.get("birth_year")
                if sn and by:
                    for r in cur.execute(
                        "SELECT ged_id FROM gedcom_persons WHERE surname=? "
                        "AND birth_year BETWEEN ? AND ? AND ged_id!=? LIMIT 5",
                        (sn, int(by) - 1, int(by) + 1, ged_id)).fetchall():
                        found[str(r["ged_id"])] = True
        except Exception:
            return []
        out = []
        for t in found:
            d = self._pers_get(t)
            if d:
                out.append(d)
        return out

    def _pers_rels(self, ged_id: str, p: dict | None = None):
        """(parents, spouses, children, siblings) einer Person. Hat die Person
        selbst keinen Baum (typisch für Webtrees/WikiTree ohne Beziehungs-Import),
        werden die Beziehungen der Zwillingsperson aus der anderen Quelle
        übernommen (virtueller Overlay beider Bäume)."""
        cache = getattr(self, "_pers_rels_cache", None)
        if cache is not None and ged_id in cache:
            return cache[ged_id]
        if p is None:
            p = self._pers_get(ged_id) or {}
        parents  = list(_loads(p.get("parents_json")))
        spouses  = list(_loads(p.get("spouses_json")))
        children = list(_loads(p.get("children_json")))
        siblings = [s for s in _loads(p.get("siblings_json")) if s != ged_id]
        if not parents and not children:        # eigener Baum leer → Overlay
            for tw in self._pers_find_twins(ged_id, p):
                parents  = parents  or list(_loads(tw.get("parents_json")))
                spouses  = spouses  or list(_loads(tw.get("spouses_json")))
                children = children or list(_loads(tw.get("children_json")))
                if not siblings:
                    siblings = [s for s in _loads(tw.get("siblings_json")) if s != ged_id]
                if parents or children:
                    break
        result = (parents, spouses, children, siblings)
        if cache is not None:
            cache[ged_id] = result
        return result

    # ── Verwandtschaftsgrad (graphbasiert, Labels via lib.helpers) ────────────
    def _pers_root_id(self) -> str | None:
        if not hasattr(self, "_root_id_cache"):
            rid = None
            try:
                with self._db._cursor() as cur:
                    r = cur.execute("SELECT ged_id FROM gedcom_persons "
                                    "WHERE sosa_number=1 LIMIT 1").fetchone()
                    rid = str(r["ged_id"]) if r else None
            except Exception:
                rid = None
            self._root_id_cache = rid
        return self._root_id_cache

    def _pers_anc_map(self, start: str, max_gen: int = 22) -> dict:
        """{ged_id: Generation} aller Vorfahren von start (start=0), Overlay-aware
        (Webtrees↔GEDCOM über _pers_rels)."""
        dist = {str(start): 0}
        frontier = [str(start)]
        g = 0
        while frontier and g < max_gen:
            g += 1
            nxt = []
            for pid in frontier:
                for par in self._pers_rels(pid)[0]:
                    par = str(par)
                    if par and par not in dist:
                        dist[par] = g
                        nxt.append(par)
            frontier = nxt
        return dist

    def _pers_root_anc_map(self) -> dict:
        if getattr(self, "_root_anc_cache", None) is None:
            rid = self._pers_root_id()
            self._root_anc_cache = self._pers_anc_map(rid) if rid else {}
        return self._root_anc_cache

    def _pers_full_relationship(self, ged_id: str, p: dict | None = None) -> str:
        """Präziser Verwandtschaftsgrad zur Wurzelperson über den gemeinsamen
        Vorfahren – nutzt dieselbe Label-Logik wie die Statistik
        (lib.helpers.relationship_label)."""
        rid = self._pers_root_id()
        if not rid:
            return ""
        if str(ged_id) == str(rid):
            return "Wurzelperson (du)"
        if not hasattr(self, "_pers_rels_cache"):
            self._pers_rels_cache = {}
        ra = self._pers_root_anc_map()
        pa = self._pers_anc_map(ged_id)
        best = None
        for cid, td in pa.items():
            if cid in ra:
                tot = ra[cid] + td
                if best is None or tot < best[0]:
                    best = (tot, ra[cid], td)
        if best is None:
            return ""
        _, root_d, target_d = best
        if root_d == 0:                      # MRCA = Wurzel → Nachfahr
            return _descendant_label(target_d)
        try:
            from lib.helpers import relationship_label
            return relationship_label(root_d, target_d,
                                      is_target_ancestor=(target_d == 0))
        except Exception:
            return ""

    def _pers_render_tree(self, ged_id: str):
        tc = self._pers_canvas
        tc.delete("all")
        tc.update_idletasks()
        self._pers_rels_cache = {}
        try:
            depth = max(1, min(5, int(self._pers_depth.get())))
        except Exception:
            depth = 2

        # C1: Tiefenbegrenzung für große Bäume (>10.000 Personen → max. 2 Gen.)
        try:
            with self._db._cursor() as cur:
                total = cur.execute(
                    "SELECT COUNT(*) FROM gedcom_persons").fetchone()[0]
            if total > 10_000:
                depth = min(self._pers_depth.get(), 2)
                self._pers_depth.set(depth)
        except Exception:
            pass

        focus = self._pers_get(ged_id)
        if not focus:
            tc.create_text(60, 50, anchor="nw", text=self._state.t("pe.not_found"),
                           fill=_MUTED, font=("Segoe UI", 10))
            tc.configure(scrollregion=(0, 0, 820, 120))
            return

        # ── Vorfahren in Sosa-Slots sammeln: anc[(gen, slot)] = ged_id ──
        # gen 1 = Eltern (slot 0=Vater, 1=Mutter); pro Generation 2^gen Slots.
        # Beziehungen mit Overlay aus anderen Quellen (Webtrees ↔ GEDCOM).
        f_parents, spouses, children, siblings = self._pers_rels(ged_id, focus)
        anc: dict = {}
        for i, pid in enumerate(f_parents[:2]):
            if pid:
                anc[(1, i)] = pid
        for g in range(1, depth):
            for slot in range(2 ** g):
                pid = anc.get((g, slot))
                if not pid:
                    continue
                gp_parents, *_ = self._pers_rels(pid)
                for i, gp in enumerate(gp_parents[:2]):
                    if gp:
                        anc[(g + 1, 2 * slot + i)] = gp

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
        try:
            from ancestry.core.bridge.gedcom_import import get_xref_ids
            xrefs = get_xref_ids(self._state.db, ged_id, "anverwandte")
            if xrefs:
                meta += f" · {xrefs[0]}"
        except Exception:
            pass
        ttk.Label(self._pers_detail, text=meta, foreground=_MUTED).pack(
            anchor="w", padx=10)
        kin = self._pers_full_relationship(ged_id, p)
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
        fact("Geburtsort", map_place(p.get("birth_place")))
        fact("Gestorben", _years(p.get("death_year"), "") or None)
        fact("Sterbeort", map_place(p.get("death_place")))
        if p.get("sosa_number"):
            fact("SOSA", p.get("sosa_number"))

        # C4: Zeitleiste-Button (neben anderen Aktions-Buttons)
        _btn_row = ttk.Frame(self._pers_detail)
        _btn_row.pack(anchor="w", padx=10, pady=(4, 2))
        self._timeline_btn = ttk.Button(
            _btn_row, text="📅 Zeitleiste",
            command=lambda: self._pers_show_timeline(ged_id, name or ged_id))
        self._timeline_btn.pack(side="left")

        # Zusammengeführte Detail-Abschnitte (früher: separater Datenviewer)
        self._pers_render_insights(p)      # Herkunft / Nachnamen-Häufigkeit / Datenqualität
        self._pers_render_parish(p)        # Kirchspiel / Konfession (Matricula)
        self._pers_render_hints(p, ged_id) # Recherche-Tipps (externe Quellen) + Aufgabe
        self._pers_render_wikitree(p)           # WikiTree-Profil-Links (mit Konfidenz)
        self._pers_render_online_research(p)   # Schnell-Buttons für Online-Quellen
        self._pers_render_duplicates(p)    # Entity-Resolution: mögliche Duplikate
        self._pers_render_relations(p)     # Eltern/Partner/Kinder/Geschwister (Links)
        self._pers_render_xref(ged_id)     # GEDCOM-Verknüpfung (Quellen-Dedup)
        self._pers_render_ner(p)           # Kirchenbuch-NER (Paten, Zeugen, …)
        self._pers_render_dna(ged_id)      # DNA-Matches (Anker)
        self._pers_render_entity_links(p)  # A3: Entity-Resolution-Ergebnisse (DNA-Verknüpfungen)
        self._pers_render_matricula(p)     # A4: Matricula-Bridge-Treffer
        self._pers_render_pedigree_gaps(p) # B4: Pedigree-Vollständigkeit

        # Allgemeiner „In Matches suchen"-Button (immer am Ende, falls Callback gesetzt)
        display_name = name
        if display_name and getattr(self, "_on_goto_matches", None):
            sep = ttk.Separator(self._pers_detail, orient="horizontal")
            sep.pack(fill="x", padx=8, pady=6)
            ttk.Button(
                self._pers_detail,
                text=f"🔍 In Matches suchen: {display_name}",
                command=lambda n=display_name: self._on_goto_matches(n),
            ).pack(anchor="w", padx=12, pady=(0, 8))

    # ── Detail-Abschnitt: Recherche-Tipps (externe Quellen, anklickbar) ────────
    def _pers_render_hints(self, p: dict, ged_id: str):
        """Zeigt auf Person+Ort+Zeit zugeschnittene Recherche-Links — nutzt die
        vorhandenen URL-Builder aus tasks.externe_quellen. Jeder Link öffnet im
        Browser; ein Button legt für die Person eine Forschungsaufgabe an."""
        given   = (p.get("given_name") or "").strip()
        surname = (p.get("surname") or "").strip()
        if not surname:
            return
        by    = p.get("birth_year")
        place = (p.get("birth_place") or p.get("death_place") or "").strip()
        try:
            from tasks import externe_quellen as eq
        except Exception:
            return
        dach = eq._is_dach(place)
        kb   = (not by or by < 1875)
        war  = bool(by and 1870 <= by <= 1928)
        hints: list[tuple[str, str]] = []
        try:
            if kb and dach:
                hints.append(("Matricula (kath. Kirchenbücher)", eq._matricula(given, surname, place, by)))
                hints.append(("Archion (ev. Kirchenbücher)",     eq._archion(given, surname, place)))
            hints.append(("FamilySearch", eq._familysearch(given, surname, by, place)))
            if dach:
                hints.append(("GEDBAS (verwandte Bäume)", eq._gedbas(surname, place)))
                if by and by >= 1874:
                    hints.append(("ArcInSys (Staatsarchiv NI)", eq._arcinsys(surname, place)))
                hints.append(("Archivportal-D", eq._archivportal(surname, place)))
            if war:
                hints.append(("Volksbund (Kriegsgräber)", eq._volksbund(given, surname, by)))
            hints.append(("Geneanet", eq._geneanet(given, surname, place)))
        except Exception as e:
            log.debug("record hints build: %s", e)
        hints = [(lbl, url) for lbl, url in hints if url]
        if not hints:
            return

        self._pers_hdr("🔎 Recherche-Tipps")
        import webbrowser
        for lbl, url in hints:
            row = ttk.Frame(self._pers_detail); row.pack(fill="x", padx=10, pady=1)
            lk = ttk.Label(row, text="• " + lbl, foreground=_LINK,
                           cursor="hand2", wraplength=260)
            lk.pack(side="left")
            lk.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
        # Forschungsaufgabe für diese Person anlegen (Feature B1)
        btnrow = ttk.Frame(self._pers_detail); btnrow.pack(fill="x", padx=10, pady=(3, 1))
        label = f"{given} {surname}".strip()
        ttk.Button(btnrow, text="🗂 Aufgabe für diese Person",
                   command=lambda: self._pers_open_tasks(ged_id, label)).pack(side="left")
        ttk.Button(btnrow, text="🔍 Ahnen-Lücken",
                   command=lambda: self._pers_show_gaps(ged_id, label)).pack(side="left", padx=4)

    def _pers_show_gaps(self, ged_id: str, label: str):
        """F3: Per-Person-Ahnenlückenanalyse (DB-gestützt) on-demand öffnen."""
        try:
            from ancestry.core.analysis.gaps import (
                analyze_pedigree_gaps, get_pedigree_completeness)
            gaps = analyze_pedigree_gaps(self._state.db, ged_id)
            comp = get_pedigree_completeness(self._state.db, ged_id)
        except Exception as e:
            log.debug("gaps analysis: %s", e)
            from tkinter import messagebox
            messagebox.showinfo("Ahnen-Lücken",
                                f"Analyse nicht möglich: {e}")
            return
        _GAP_LABEL = {"maternal_parent": "Mutter fehlt",
                      "paternal_parent": "Vater fehlt",
                      "both_parents": "beide Eltern fehlen"}
        by_gen = comp.get("by_generation", {})
        known_total = sum(g.get("known", 0) for g in by_gen.values())
        first_gap = comp.get("first_gap_gen")
        complete_through = (first_gap - 1) if first_gap else (max(by_gen) if by_gen else 0)
        dlg = tk.Toplevel(self)
        dlg.title(f"Ahnen-Lücken — {label}")
        dlg.geometry("540x460")
        head = (f"Lückenlos bis Generation {complete_through} · "
                f"{known_total} Ahnen erfasst · "
                f"{len(gaps)} offene Lücke(n)")
        ttk.Label(dlg, text=head, font=("Segoe UI", 9, "bold"),
                  wraplength=520).pack(fill="x", padx=10, pady=8)
        cols = ("gen", "type", "via")
        tv = ttk.Treeview(dlg, columns=cols, show="headings", height=16)
        for c, t, w in (("gen", "Gen.", 50), ("type", "Lücke", 200),
                        ("via", "letzter bekannter Ahn", 260)):
            tv.heading(c, text=t); tv.column(c, width=w, anchor="w")
        tv.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for g in gaps:
            tv.insert("", "end", values=(
                g.get("generation", ""),
                _GAP_LABEL.get(g.get("gap_type", ""), g.get("gap_type", "")),
                g.get("last_known", "")))
        if not gaps:
            ttk.Label(dlg, text="Keine offenen Lücken in den erfassten Generationen.",
                      foreground="#2e7d32").pack(pady=4)
        ttk.Button(dlg, text="Schließen", command=dlg.destroy).pack(pady=(0, 8))

    def _pers_open_tasks(self, ged_id: str, label: str):
        try:
            from ancestry.gui.analysis.research_tasks_view import show_research_tasks
            show_research_tasks(self, self._state, entity_type="ged_person",
                                entity_key=ged_id, entity_label=label)
        except Exception as e:
            log.debug("open tasks: %s", e)

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

        def _xref_id(xid):
            """Gibt die Anverwandte-ID zurück, falls verknüpft."""
            try:
                from ancestry.core.bridge.gedcom_import import get_xref_ids
                ids = get_xref_ids(self._state.db, str(xid), "anverwandte")
                return ids[0] if ids else None
            except Exception:
                return None

        for label, ids in groups:
            for xid in ids:
                row = ttk.Frame(self._pers_detail); row.pack(fill="x", padx=10, pady=1)
                ttk.Label(row, text=label, width=10, foreground=_MUTED).pack(side="left")
                text = _name(xid)
                anvw_id = _xref_id(xid)
                if anvw_id:
                    text += f" · {anvw_id}"
                lk = ttk.Label(row, text=text, foreground=_LINK,
                               cursor="hand2", wraplength=210)
                lk.pack(side="left")
                lk.bind("<Button-1>", lambda e, i=str(xid): self._pers_navigate(i))

    # ── Detail-Abschnitt: Kirchspiel / Konfession (Matricula) ──────────────────
    def _pers_hdr(self, text: str):
        ttk.Separator(self._pers_detail).pack(fill="x", padx=10, pady=(8, 4))
        ttk.Label(self._pers_detail, text=text,
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10)

    # ── Detail-Abschnitt: Einordnung (Herkunft/Häufigkeit/Datenqualität) ───────
    def _pers_render_insights(self, p: dict):
        sn = (p.get("surname") or "").strip()
        by = p.get("birth_year")
        rows = []   # (Label, Wert, Farbe)

        # Herkunftsregion (ML-Modell; leer wenn kein Modell trainiert)
        try:
            from ancestry.core.ml_origin import predict_region
            regs = predict_region(sn, by, top=2) if sn else []
        except Exception:
            regs = []
        if regs:
            txt = ", ".join(f"{r} ({pr*100:.0f}%)" for r, pr in regs)
            rows.append(("Herkunft", txt, _TXT))

        # Nachnamen-Häufigkeit in der Datenbank
        if sn:
            try:
                with self._db._cursor() as cur:
                    n = cur.execute("SELECT COUNT(*) FROM gedcom_persons "
                                    "WHERE surname=?", (sn,)).fetchone()[0]
                tag = "selten" if n <= 3 else "häufig" if n >= 25 else ""
                rows.append(("Nachname", f"{n}× im Baum" + (f" · {tag}" if tag else ""),
                             _LINK if n <= 3 else _TXT))
            except Exception:
                pass

        # Datenqualität (Vollständigkeit der Kernfelder)
        keys = ("given_name", "surname", "sex", "birth_year", "birth_place",
                "death_year", "death_place")
        filled = sum(1 for k in keys if str(p.get(k) or "").strip() not in ("", "0"))
        pct = round(100 * filled / len(keys))
        qcol = _EV if pct >= 70 else _KATH if pct >= 40 else "#b58b00"
        rows.append(("Datenqualität", f"{pct}% ({filled}/{len(keys)} Felder)", qcol))

        if not rows:
            return
        self._pers_hdr("📈 Einordnung")
        for lbl, val, col in rows:
            r = ttk.Frame(self._pers_detail); r.pack(fill="x", padx=10, pady=1)
            ttk.Label(r, text=lbl, width=10, foreground=_MUTED).pack(side="left")
            ttk.Label(r, text=val, foreground=col, wraplength=210).pack(side="left")

    def _pers_render_parish(self, p: dict):
        parish = _parish_for(map_place(p.get("birth_place")) or "")
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
            ttk.Label(rr, text=self._state.t("pe.founded"), width=10, foreground=_MUTED).pack(side="left")
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

    def _pers_render_ner(self, p: dict):
        sn = (p.get("surname") or "").strip()
        if not sn:
            return
        try:
            from ancestry.core.bridge._text import _koelner
            code = _koelner(sn)
            if not code:
                return
            with self._db._cursor() as cur:
                rows = cur.execute("""
                    SELECT n.name_raw, n.rolle, n.event_year, n.ort,
                           e.entry_type, e.book_id, e.village
                    FROM matrikula_ner n
                    JOIN source_matrikula_entries e ON e.entry_id = n.entry_id
                    WHERE n.koeln_code = ?
                    ORDER BY n.event_year ASC
                    LIMIT 20
                """, (code,)).fetchall()
        except Exception:
            return
        if not rows:
            return
        _ROLLE = {
            "kind": "Täufling", "vater": "Vater", "mutter": "Mutter",
            "pate": "Pate/Patin", "braeutigam": "Bräutigam", "braut": "Braut",
            "braeutigam_vater": "Vater d. Bräutigams", "braut_vater": "Vater d. Braut",
            "zeuge": "Zeuge", "verstorbener": "Verstorbener", "elternteil": "Elternteil",
        }
        self._pers_hdr(f"⛪ Kirchenbuch-NER ({len(rows)})")
        for r in rows:
            row = ttk.Frame(self._pers_detail); row.pack(fill="x", padx=10, pady=1)
            rolle_lbl = _ROLLE.get(r["rolle"], r["rolle"])
            yr = str(r["event_year"] or "?")
            village = (r["ort"] or r["village"] or "").strip()
            ttk.Label(row, text=rolle_lbl, width=18, foreground=_MUTED).pack(side="left")
            txt = f"{r['name_raw']} · {r['entry_type']} {yr}"
            if village:
                txt += f" · {village}"
            ttk.Label(row, text=txt, wraplength=185).pack(side="left")

    # ── Detail-Abschnitt: WikiTree-Profil-Links ─────────────────────────────────
    def _pers_render_wikitree(self, p: dict):
        """Zeigt WikiTree-Such- und Profil-Links mit Konfidenz-Indikatoren.

        Konfidenz-Levels mit Farbcodierung:
          - HIGH (≥0.85):   grün · exakter Name + ±5 Jahre
          - MEDIUM (0.65–0.85): orange · Fuzzy-Match oder Jahr-Range
          - LOW (<0.65):    grau · nur Name oder nur Jahr
        """
        given   = (p.get("given_name") or "").strip()
        surname = (p.get("surname") or "").strip()
        if not surname:
            return

        try:
            from tasks.wikitree_lookup import _search_url, _confidence
        except Exception:
            return

        by = p.get("birth_year")

        # Konfidenz-Farben
        _CONF_COLOR = {
            "HOCH": _EV,     # grün (sehr wahrscheinlich)
            "MITTEL": "#f57c00",  # orange (plausibel)
            "NIEDRIG": _MUTED    # grau (unsicher)
        }

        # Basis-Such-URL (immer vorhanden, braucht keine API)
        search_url = _search_url(given, surname, by)

        # Versuch, Konfidenz zu berechnen (für Anzeige, nicht für API-Call)
        # Im echten Betrieb würde das von der Excel-Sheet kommen; hier zeigen wir
        # nur die Such-URL mit Konfidenz-Indikator
        konfidenz, score = _confidence(given, surname, by, {
            "LastNameAtBirth": surname,
            "FirstName": given,
            "BirthDate": f"{by}-01-01" if by else ""
        })

        self._pers_hdr("🌍 WikiTree-Integration")

        # WikiTree-Button + Such-Link
        btn_row = ttk.Frame(self._pers_detail)
        btn_row.pack(fill="x", padx=10, pady=(3, 1))

        # Button: direkt zur Such-Seite
        ttk.Button(
            btn_row,
            text=f"📌 WikiTree suchen ({konfidenz})",
            command=lambda u=search_url: webbrowser.open(u)
        ).pack(side="left")

        # Info-Text mit Konfidenz-Begründung
        info_row = ttk.Frame(self._pers_detail)
        info_row.pack(fill="x", padx=10, pady=2)

        conf_label = f"[{konfidenz}] {score*100:.0f}% Konfidenz"
        ttk.Label(
            info_row,
            text=conf_label,
            foreground=_CONF_COLOR.get(konfidenz, _MUTED),
            font=("Segoe UI", 9, "bold")
        ).pack(side="left")

        # Erklär-Text
        if konfidenz == "HOCH":
            hint = "Exakter Name + Geburtsjahr ±5 Jahre"
        elif konfidenz == "MITTEL":
            hint = "Fuzzy-Match oder Name + Jahr-Range"
        else:
            hint = "Nur Name oder Jahr — präzisieren empfohlen"

        ttk.Label(
            info_row,
            text=f"· {hint}",
            foreground=_MUTED
        ).pack(side="left")

        # WikiTree-Name → Matches-Tab
        display_name = f"{given} {surname}".strip()
        if display_name and getattr(self, "_on_goto_matches", None):
            btn = ttk.Button(
                self._pers_detail,
                text=f"🔍 → Matches: {display_name}",
                command=lambda n=display_name: self._on_goto_matches(n),
            )
            btn.pack(anchor="w", padx=12, pady=2)

    # ── Detail-Abschnitt: Online-Recherche-Schnell-Buttons ──────────────────────
    def _pers_render_online_research(self, p: dict):
        """Schnell-Buttons für externe Online-Quellen pro Person."""
        given   = (p.get("given_name") or p.get("first_name") or "").strip()
        surname = (p.get("surname") or p.get("last_name") or "").strip()
        birth_y = str(p.get("birth_year") or "").strip()
        birth_p = (p.get("birth_place") or "").strip()

        if not given and not surname:
            return

        self._pers_hdr("🔍 Online-Quellen")
        frame = ttk.Frame(self._pers_detail)
        frame.pack(anchor="w", padx=12, pady=(0, 6))

        name_q = f"{given} {surname}".strip()

        links = [
            ("🌍 FamilySearch",
             f"https://www.familysearch.org/search/record/results?q.givenName={given}&q.surname={surname}&q.birthLikeDate.from={birth_y}"),
            ("📖 Archion",
             f"https://www.archion.de/de/browse/?no_cache=1&q={name_q}"),
            ("🗿 BillionGraves",
             f"https://billiongraves.com/search/results/#search={name_q}"),
            ("✝ FindAGrave",
             f"https://www.findagrave.com/memorial/search?firstname={given}&lastname={surname}&birthyear={birth_y}"),
            ("📊 GOV-Orte",
             f"http://gov.genealogy.net/search/index?id={birth_p}" if birth_p else ""),
            ("🔤 DFD-Name",
             f"https://www.namenforschung.net/dfd/woerterbuch/liste/?tx_dfd_main%5Baction%5D=search&tx_dfd_main%5Bcontroller%5D=Entry&tx_dfd_main%5Bsearch%5D%5Bq%5D={surname}"
             if surname else ""),
            ("📰 Zeitungsarchiv",
             f"https://www.deutsche-digitale-bibliothek.de/newspaper/search?fulltext={name_q}"),
        ]

        col = 0
        row_frame = None
        for label, url in links:
            if not url:
                continue
            if col % 3 == 0:
                row_frame = ttk.Frame(frame)
                row_frame.pack(anchor="w", pady=1)
            ttk.Button(
                row_frame,
                text=label,
                command=lambda u=url: webbrowser.open(u),
                width=18,
            ).pack(side="left", padx=(0, 4))
            col += 1

    # ── Detail-Abschnitt: Entity-Resolution – mögliche Duplikate ────────────────
    def _pers_render_duplicates(self, p: dict):
        """Zeigt bis zu 5 Personen aus der DB, die möglicherweise dieselbe
        reale Person darstellen (gleicher Nachname / Vorname-Ersttoken,
        optional Geburtsjahr ±5 Jahre)."""
        given   = (p.get("given_name") or "").strip()
        surname = (p.get("surname") or "").strip()
        if not given and not surname:
            return

        # Geburtsjahr ermitteln (direkt oder aus birth_date)
        p_year: int | None = None
        by = p.get("birth_year")
        if by:
            try:
                p_year = int(by)
            except (ValueError, TypeError):
                pass
        if p_year is None:
            bd = str(p.get("birth_date") or "")
            m = re.search(r"\b(\d{4})\b", bd)
            if m:
                p_year = int(m.group(1))

        first_token = given.split()[0] if given else ""
        sn_filter   = f"%{surname}%" if surname else "%"
        fn_filter   = f"%{first_token}%" if first_token else "%"
        current_id  = str(p.get("ged_id", ""))

        try:
            with self._db._cursor() as cur:
                raw = cur.execute(
                    """
                    SELECT ged_id, given_name, surname, birth_year, source
                    FROM gedcom_persons
                    WHERE ged_id != ?
                      AND (given_name LIKE ? OR surname LIKE ?)
                    LIMIT 10
                    """,
                    (current_id, fn_filter, sn_filter),
                ).fetchall()
        except Exception:
            return

        candidates = []
        for r in raw:
            r_given   = (r["given_name"] or "").strip()
            r_surname = (r["surname"] or "").strip()
            # Name-Relevanz: gleicher Nachname (case-insensitive) ODER
            # gleicher Vorname-Ersttoken
            same_sn = (surname and r_surname.lower() == surname.lower())
            r_first = r_given.split()[0].lower() if r_given else ""
            same_fn = bool(first_token and r_first == first_token.lower())
            if not (same_sn or same_fn):
                continue
            # Geburtsjahr-Filter: wenn für beide Seiten bekannt, max. ±5 Jahre
            if p_year is not None and r["birth_year"]:
                try:
                    if abs(int(r["birth_year"]) - p_year) > 5:
                        continue
                except (ValueError, TypeError):
                    pass
            candidates.append(dict(r))
            if len(candidates) >= 5:
                break

        if not candidates:
            return

        self._pers_hdr("🔍 Mögliche Duplikate")
        for cand in candidates:
            cid     = str(cand["ged_id"])
            cn      = f"{(cand['given_name'] or '').strip()} {(cand['surname'] or '').strip()}".strip() or cid
            cby     = cand.get("birth_year")
            csrc    = _SRC_LABEL.get(cand.get("source", ""), cand.get("source", ""))
            details = cn
            if cby:
                details += f" · *{cby}"
            if csrc:
                details += f" · {csrc}"
            row = ttk.Frame(self._pers_detail)
            row.pack(fill="x", padx=10, pady=2)
            ttk.Label(row, text=details, wraplength=210, foreground=_TXT).pack(
                side="left", fill="x", expand=True)
            ttk.Button(
                row,
                text="→ Anzeigen",
                command=lambda i=cid: self._select_person_by_id(i),
            ).pack(side="right")

    # ── C4: Personen-Zeitleiste ───────────────────────────────────────────────────
    def _pers_show_timeline(self, ged_id: str, display_name: str):
        """Öffnet einen Toplevel-Dialog mit der chronologischen Zeitleiste der
        Lebensereignisse der ausgewählten Person sowie ihrer Eltern und Kinder."""
        p = self._pers_get(ged_id)
        if not p:
            messagebox.showinfo("Zeitleiste", "Person nicht gefunden.")
            return

        # Alle relevanten Personen sammeln: Fokusperson + Eltern + Kinder
        parents_ids  = _loads(p.get("parents_json"))
        children_ids = _loads(p.get("children_json"))
        all_ids = [str(ged_id)] + [str(i) for i in parents_ids] + [str(i) for i in children_ids]
        all_ids = list(dict.fromkeys(all_ids))  # Duplikate entfernen, Reihenfolge behalten

        persons_map: dict[str, dict] = {}
        if all_ids:
            try:
                ph = ",".join("?" * len(all_ids))
                with self._db._cursor() as cur:
                    rows = cur.execute(
                        f"SELECT ged_id, given_name, surname, birth_year, death_year, "
                        f"birth_place, death_place, sex, "
                        f"baptism_year, burial_year, baptism_place, burial_place "
                        f"FROM gedcom_persons WHERE ged_id IN ({ph})",
                        all_ids,
                    ).fetchall()
                persons_map = {str(r["ged_id"]): dict(r) for r in rows}
            except Exception:
                # Spalten baptism_year / burial_year existieren möglicherweise nicht
                try:
                    ph = ",".join("?" * len(all_ids))
                    with self._db._cursor() as cur:
                        rows = cur.execute(
                            f"SELECT ged_id, given_name, surname, birth_year, death_year, "
                            f"birth_place, death_place, sex "
                            f"FROM gedcom_persons WHERE ged_id IN ({ph})",
                            all_ids,
                        ).fetchall()
                    persons_map = {str(r["ged_id"]): dict(r) for r in rows}
                except Exception:
                    persons_map = {}

        # Ereignisse zusammenstellen
        events: list[tuple[int, str, str, str]] = []  # (sort_year, label, person_name, ort)

        _EVENT_LABELS = {
            "birth":   "Geburt",
            "baptism": "Taufe",
            "death":   "Tod",
            "burial":  "Begräbnis",
        }

        def _person_name(pd: dict) -> str:
            n = f"{(pd.get('given_name') or '').strip()} {(pd.get('surname') or '').strip()}".strip()
            return n or str(pd.get("ged_id", "?"))

        def _add_event(year_val, event_key: str, place_val, person_data: dict):
            try:
                yr = int(str(year_val).strip()) if year_val else None
            except (ValueError, TypeError):
                yr = None
            if not yr or yr <= 0:
                return
            lbl = _EVENT_LABELS.get(event_key, event_key)
            ort = (str(place_val or "")).strip() or "—"
            pname = _person_name(person_data)
            events.append((yr, lbl, pname, ort))

        # Heiraten aus families-Tabelle (falls vorhanden)
        def _add_marriages(xid: str, pdata: dict):
            try:
                with self._db._cursor() as cur:
                    rows = cur.execute(
                        "SELECT marriage_year, marriage_place "
                        "FROM gedcom_families "
                        "WHERE husb_id=? OR wife_id=?",
                        (xid, xid),
                    ).fetchall()
                for r in rows:
                    _add_event(r[0], "Heirat", r[1], pdata)
            except Exception:
                # Tabelle existiert nicht oder hat andere Spalten → ignorieren
                pass

        # Spouses auch: Heiratsjahr aus spouses_json ist nicht direkt vorhanden;
        # gedcom_families ist die richtige Quelle.
        for pid in all_ids:
            pd = persons_map.get(pid)
            if not pd:
                continue
            _add_event(pd.get("birth_year"),   "birth",   pd.get("birth_place"),   pd)
            _add_event(pd.get("baptism_year"), "baptism", pd.get("baptism_place"), pd)
            _add_event(pd.get("death_year"),   "death",   pd.get("death_place"),   pd)
            _add_event(pd.get("burial_year"),  "burial",  pd.get("burial_place"),  pd)
            _add_marriages(pid, pd)

        # Heiraten der Fokusperson auch aus spouses_json (als Fallback)
        spouses_ids = _loads(p.get("spouses_json"))
        # gedcom_families für Fokusperson bereits oben verarbeitet

        events.sort(key=lambda e: e[0])

        # ── Dialog aufbauen ──
        dlg = tk.Toplevel(self)
        dlg.title(f"Zeitleiste — {display_name}")
        dlg.geometry("640x460")
        dlg.resizable(True, True)

        ttk.Label(
            dlg,
            text=f"Lebensereignisse: {display_name} + Eltern & Kinder",
            font=("Segoe UI", 10, "bold"),
            wraplength=600,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        cols = ("year", "event", "person", "place")
        tv = ttk.Treeview(dlg, columns=cols, show="headings", height=18)
        tv.heading("year",   text="Jahr")
        tv.heading("event",  text="Ereignis")
        tv.heading("person", text="Person")
        tv.heading("place",  text="Ort")
        tv.column("year",   width=55,  anchor="center", stretch=False)
        tv.column("event",  width=90,  anchor="w",      stretch=False)
        tv.column("person", width=200, anchor="w",      stretch=True)
        tv.column("place",  width=260, anchor="w",      stretch=True)

        sb_v = ttk.Scrollbar(dlg, orient="vertical",   command=tv.yview)
        sb_h = ttk.Scrollbar(dlg, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)

        sb_v.pack(side="right", fill="y")
        sb_h.pack(side="bottom", fill="x")
        tv.pack(fill="both", expand=True, padx=(12, 0), pady=(0, 4))

        if events:
            for yr, lbl, pname, ort in events:
                tv.insert("", "end", values=(yr, lbl, pname, ort))
        else:
            tv.insert("", "end", values=("—", "Keine Ereignisse gefunden", "", ""))

        ttk.Label(
            dlg,
            text=f"{len(events)} Ereignis(se) · Person + {len(parents_ids)} Elternteil(e) + {len(children_ids)} Kind(er)",
            foreground=_MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=12, pady=(0, 2))

        ttk.Button(dlg, text="Schließen", command=dlg.destroy).pack(pady=(2, 8))

    # ── Entity-Resolution: Duplikat-Prüf-Panel ───────────────────────────────────
    def _build_entity_resolution_panel(self, parent: tk.Widget):
        """Panel zum Prüfen und Bestätigen von Personen-Duplikaten."""
        frame = ttk.LabelFrame(
            parent, text="🔗 Mögliche Duplikate (Entity-Resolution)", padding=8)
        frame.pack(fill="both", expand=False, padx=6, pady=4)

        ctrl = ttk.Frame(frame)
        ctrl.pack(fill="x")
        ttk.Button(ctrl, text="🔍 Kandidaten laden",
                   command=self._load_er_candidates).pack(side="left")
        ttk.Label(ctrl, text="  Kandidaten mit hoher Namensähnlichkeit",
                  foreground="#888888").pack(side="left")

        cols = ("p1", "p2", "score", "reason")
        self._er_tree = ttk.Treeview(frame, columns=cols, show="headings",
                                     height=8, selectmode="browse")
        self._er_tree.heading("p1",     text="Person 1")
        self._er_tree.heading("p2",     text="Person 2")
        self._er_tree.heading("score",  text="Score")
        self._er_tree.heading("reason", text="Grund")
        self._er_tree.column("p1",     width=180)
        self._er_tree.column("p2",     width=180)
        self._er_tree.column("score",  width=55, anchor="e")
        self._er_tree.column("reason", width=200)
        sb = ttk.Scrollbar(frame, orient="vertical", command=self._er_tree.yview)
        self._er_tree.configure(yscrollcommand=sb.set)
        self._er_tree.pack(fill="both", expand=True, side="left")
        sb.pack(side="left", fill="y")

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text="✓ Gleiche Person (zusammenführen)",
                   command=lambda: self._er_decision("merge")).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="✗ Verschiedene Personen",
                   command=lambda: self._er_decision("different")).pack(side="left")

    def _load_er_candidates(self):
        """Lädt Kandidaten-Paare aus entity_resolution oder direkte SQL-Abfrage."""
        candidates: list[dict] = []
        try:
            from ancestry.core.entity_resolution import find_duplicate_candidates
            candidates = find_duplicate_candidates(self._state.db, limit=100)
        except (ImportError, Exception):
            try:
                with self._state.db._cursor() as cur:
                    rows = cur.execute("""
                        SELECT a.xref_id, a.name, b.xref_id, b.name,
                               a.birth_year, b.birth_year, a.source, b.source
                        FROM gedcom_persons a
                        JOIN gedcom_persons b ON (
                            a.name = b.name
                            AND a.xref_id < b.xref_id
                            AND (a.birth_year IS NULL OR b.birth_year IS NULL
                                 OR ABS(CAST(a.birth_year AS INT) - CAST(b.birth_year AS INT)) <= 3)
                        )
                        LIMIT 100
                    """).fetchall()
                    for r in rows:
                        candidates.append({
                            "id1": r[0], "name1": r[1],
                            "id2": r[2], "name2": r[3],
                            "score": (0.9 if r[4] and r[5]
                                      and abs((r[4] or 0) - (r[5] or 0)) <= 1
                                      else 0.7),
                            "reason": (f"Gleicher Name"
                                       f"{', ähnl. Geburtsjahr' if r[4] and r[5] else ''}"),
                        })
            except Exception:
                # Fallback: query on gedcom_persons without xref_id column
                try:
                    with self._state.db._cursor() as cur:
                        rows = cur.execute("""
                            SELECT a.ged_id, a.given_name || ' ' || COALESCE(a.surname,'') as aname,
                                   b.ged_id, b.given_name || ' ' || COALESCE(b.surname,'') as bname,
                                   a.birth_year, b.birth_year
                            FROM gedcom_persons a
                            JOIN gedcom_persons b ON (
                                a.surname = b.surname
                                AND COALESCE(a.given_name,'') = COALESCE(b.given_name,'')
                                AND a.ged_id < b.ged_id
                                AND (a.birth_year IS NULL OR b.birth_year IS NULL
                                     OR ABS(CAST(a.birth_year AS INT) - CAST(b.birth_year AS INT)) <= 3)
                            )
                            LIMIT 100
                        """).fetchall()
                        for r in rows:
                            candidates.append({
                                "id1": r[0], "name1": r[1],
                                "id2": r[2], "name2": r[3],
                                "score": (0.9 if r[4] and r[5]
                                          and abs((r[4] or 0) - (r[5] or 0)) <= 1
                                          else 0.7),
                                "reason": (f"Gleicher Name"
                                           f"{', ähnl. Geburtsjahr' if r[4] and r[5] else ''}"),
                            })
                except Exception:
                    candidates = []

        if not hasattr(self, "_er_tree"):
            return
        for item in self._er_tree.get_children():
            self._er_tree.delete(item)
        for c in candidates:
            n1 = c.get("name1") or c.get("name") or c.get("id1", "?")
            n2 = c.get("name2") or c.get("id2", "?")
            score = c.get("score", 0)
            reason = c.get("reason", "")
            iid = f"{c.get('id1', '?')}||{c.get('id2', '?')}"
            self._er_tree.insert("", "end", iid=iid,
                                 values=(n1, n2, f"{score:.0%}", reason))

    def _er_decision(self, decision: str):
        if not hasattr(self, "_er_tree"):
            return
        sel = self._er_tree.selection()
        if not sel:
            return
        iid = sel[0]
        id1, id2 = iid.split("||") if "||" in iid else (iid, "")
        try:
            import datetime
            with self._state.db._cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS entity_decisions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        person_id_1 TEXT, person_id_2 TEXT,
                        decision TEXT, decided_at TEXT
                    )
                """)
                cur.execute(
                    "INSERT INTO entity_decisions "
                    "(person_id_1, person_id_2, decision, decided_at) VALUES (?,?,?,?)",
                    (id1, id2, decision,
                     datetime.datetime.now().isoformat())
                )
                self._state.db._conn.commit()
        except Exception:
            pass
        self._er_tree.delete(iid)

    def _select_person_by_id(self, person_id: str):
        """Wählt eine Person im Listenfeld aus und löst die Detail-Anzeige aus."""
        iid = str(person_id)
        # Falls der Eintrag bereits in der Treeview-Liste vorhanden ist, direkt
        # selektieren; andernfalls die Liste zurücksetzen und dann navigieren.
        if self._pers_list.exists(iid):
            self._pers_list.selection_set(iid)
            self._pers_list.see(iid)
            self._pers_navigate(iid)
        else:
            # Suche leeren → komplette Liste laden, dann navigieren
            self._pers_search.set("")
            self._pers_navigate(iid)

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

    # ── A3: Entity-Resolution-Ergebnisse (DNA-Match-Verknüpfungen) ───────────────
    def _pers_render_entity_links(self, p: dict):
        """Zeigt entity_assignments (DNA-Match-Verknüpfungen) für diese Person."""
        ged_id = p.get("ged_id", "")
        if not ged_id:
            return
        try:
            with self._db._cursor() as cur:
                rows = cur.execute("""
                    SELECT ea.match_guid, ea.confidence, ea.source, m.name, m.cm
                    FROM entity_assignments ea
                    LEFT JOIN matches m ON ea.match_guid = m.guid
                    WHERE ea.ged_id = ?
                    ORDER BY ea.confidence DESC
                    LIMIT 10
                """, (ged_id,)).fetchall()
        except Exception:
            rows = []

        if not rows:
            return

        self._pers_hdr("🔗 Entitäts-Zuordnungen")
        for r in rows[:5]:
            name = r["name"] if hasattr(r, "keys") else r[3]
            cm = r["cm"] if hasattr(r, "keys") else r[4]
            conf = r["confidence"] if hasattr(r, "keys") else r[1]
            pct = f"{conf:.0%}" if conf else "?"
            ttk.Label(self._pers_detail,
                      text=f"  DNA: {name or '?'}  {cm or '?'} cM  [{pct}]",
                      font=("Segoe UI", 8), foreground="#336699"
                      ).pack(anchor="w", padx=14)

    # ── A4: Matricula-Bridge-Treffer ─────────────────────────────────────────────
    def _pers_render_matricula(self, p: dict):
        """Zeigt passende Kirchenbucheinträge für diese Person."""
        given = p.get("given_name", "").strip()
        surname = p.get("surname", "").strip()
        if not given and not surname:
            return
        try:
            with self._db._cursor() as cur:
                rows = cur.execute("""
                    SELECT entry_id, entry_type, person_name, event_date
                    FROM source_matrikula_entries
                    WHERE person_name LIKE ? OR person_name LIKE ?
                    LIMIT 5
                """, (f"%{surname}%", f"%{given}%")).fetchall()
        except Exception:
            rows = []

        if not rows:
            return

        self._pers_hdr("⛪ Kirchenbuch-Treffer")
        for r in rows[:4]:
            etype = r["entry_type"] if hasattr(r, "keys") else r[1]
            pname = r["person_name"] if hasattr(r, "keys") else r[2]
            date = r["event_date"] if hasattr(r, "keys") else r[3]
            ttk.Label(self._pers_detail,
                      text=f"  {etype or '?'}: {pname}  {date or ''}",
                      font=("Segoe UI", 8), foreground="#5a3e00"
                      ).pack(anchor="w", padx=14)

    # ── B4: Pedigree-Vollständigkeit ─────────────────────────────────────────────
    def _pers_render_pedigree_gaps(self, p: dict):
        """Zeigt GEDCOM-Vollständigkeit über Generationen."""
        ged_id = p.get("ged_id", "")
        if not ged_id:
            return
        try:
            with self._db._cursor() as cur:
                total = cur.execute(
                    "SELECT COUNT(*) FROM gedcom_persons"
                ).fetchone()[0]
        except Exception:
            return

        if total <= 0:
            return

        self._pers_hdr("📊 Stammbaum-Vollständigkeit")
        bar_frame = ttk.Frame(self._pers_detail)
        bar_frame.pack(anchor="w", padx=12, pady=(0, 6))

        try:
            with self._db._cursor() as cur:
                gen_data = []
                for gen in range(1, 7):
                    min_sosa = 2 ** gen
                    max_sosa = 2 ** (gen + 1) - 1
                    expected = max_sosa - min_sosa + 1
                    found = cur.execute(
                        "SELECT COUNT(*) FROM gedcom_persons "
                        "WHERE sosa_number BETWEEN ? AND ?",
                        (min_sosa, max_sosa)
                    ).fetchone()[0]
                    pct = found / expected if expected else 0
                    gen_data.append((gen, found, expected, pct))

            for gen, found, expected, pct in gen_data:
                row = ttk.Frame(bar_frame)
                row.pack(fill="x", pady=1)
                ttk.Label(row, text=f"Gen {gen}:", width=6).pack(side="left")
                bar = ttk.Progressbar(row, length=120, maximum=100,
                                      value=int(pct * 100), mode="determinate")
                bar.pack(side="left", padx=4)
                ttk.Label(row, text=f"{found}/{expected}  ({pct:.0%})",
                          foreground="#666666", font=("Segoe UI", 8)).pack(side="left")
        except Exception:
            ttk.Label(bar_frame, text=f"  {total} Personen gesamt",
                      foreground="#666666").pack(anchor="w")
