#!/usr/bin/env python3
"""
Genealogie-Datenviewer — durchsucht und navigiert die gesammelten Personen-
daten in einer Baum-/Detailansicht (ähnlich der Ancestry-Personenseite).

Quellen:
  • Anverwandte   – ancestry/tools/webtrees_crawl.db  (Tabelle wt_persons)
  • GEDCOM/extern – ancestry/ancestry_dna.db          (Tabelle gedcom_persons)

Der Viewer öffnet die Crawl-DB READ-ONLY und mit busy_timeout, damit er den
LAUFENDEN Crawler NICHT stört. „🔄 Aktualisieren" lädt neu hinzugekommene
Personen nach – man kann also live zusehen, wie der Baum wächst.

Start:
    python viewer.py                       # Standard: Anverwandte-Crawl-DB
    python viewer.py pfad/zur/datenbank.db
"""
from __future__ import annotations

import functools
import json
import os
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import webbrowser
import tkinter as tk
from collections import deque
from tkinter import ttk, messagebox, filedialog

ROOT = os.path.dirname(os.path.abspath(__file__))
CRAWL_DB      = os.path.join(ROOT, "ancestry", "tools", "webtrees_crawl.db")
ANCESTRY_DB   = os.path.join(ROOT, "ancestry", "ancestry_dna.db")
PARISH_JSON   = os.path.join(ROOT, "ancestry", "tools", "matricula_parishes.json")
PARISH_DB     = os.path.join(ROOT, "ancestry", "tools", "matricula_parishes.db")
PROFILES_JSON = os.path.join(ROOT, "ancestry", "tools", "webtrees_profiles.json")
_TOOLS = {
    "webtrees":     os.path.join(ROOT, "ancestry", "tools", "crawl_webtrees.py"),
    "mat_catalog":  os.path.join(ROOT, "ancestry", "tools", "scrape_matricula_osnabrueck.py"),
    "mat_books":    os.path.join(ROOT, "ancestry", "tools", "fetch_matricula_books.py"),
    "mat_scan":     os.path.join(ROOT, "ancestry", "tools", "scan_matricula_kirchspiel.py"),
    "mat_viewer":   os.path.join(ROOT, "ancestry", "tools", "matricula_viewer.py"),
    "myheritage":   os.path.join(ROOT, "ancestry", "tools", "fetch_mh_shared_matches.py"),
    "mh_download":  os.path.join(ROOT, "ancestry", "tools", "download_myheritage.py"),
    "imp_mh_csv":   os.path.join(ROOT, "ancestry", "tools", "import_mh_csv.py"),
    "imp_gedmatch": os.path.join(ROOT, "ancestry", "tools", "import_gedmatch.py"),
    "imp_wikitree": os.path.join(ROOT, "ancestry", "tools", "import_wikitree.py"),
    "imp_webtrees": os.path.join(ROOT, "ancestry", "tools", "import_webtrees.py"),
    "entity_browser": os.path.join(ROOT, "ancestry", "tools", "entity_browser.py"),
    "ged_slim":       os.path.join(ROOT, "ancestry", "tools", "ged_slim.py"),
}

# ── Farben (an die Ancestry-Optik angelehnt) ─────────────────────────────────
C = {
    "bg":        "#1f2327",
    "panel":     "#2a2f35",
    "card":      "#3a4048",
    "card_m":    "#5a7a9a",   # männlich (blau)
    "card_f":    "#9a6a6a",   # weiblich (rot/rosa)
    "text":      "#e8e8e8",
    "muted":     "#9aa4ae",
    "accent":    "#7cb342",
    "link":      "#8ab4f8",
    "sel":       "#3d5a3d",
    "mapped":    "#2e7d32",   # dunkelgrün  – im GEDCOM bestätigt
    "fuzzy":     "#5d4037",   # dunkelbraun – fuzzy-Match
    "cluster":   "#6a1b9a",   # lila        – DNA-Cluster
    "dna":       "#00838f",   # petrol      – DNA-Match
    "kath":      "#1565c0",   # blau        – katholisch
    "ev":        "#558b2f",   # grün        – evangelisch
}

_FILTER_ALL    = "Alle"
_FILTER_MAPPED = "Im GEDCOM ✓"
_FILTER_FUZZY  = "Fuzzy-Match ~"
_FILTER_UNMAP  = "Nicht im GEDCOM"
_FILTER_DNA    = "DNA-Match 🧬"

_CONF_ALL  = "Alle Konfessionen"
_CONF_KATH = "Katholisch"
_CONF_EV   = "Evangelisch"
_CONF_UNK  = "Unbekannt"

# cM-Bereiche → erwarteter Verwandtschaftsgrad (nach ISOGG/DNA Painter)
_CM_RANGES = [
    (2600, 9999, "Elternteil / Zwilling"),
    (1700, 2599, "Geschwister / Halbgeschwister"),
    (1160, 1699, "Großelternteil / Onkel/Tante"),
    (575,  1159, "Urgroßelternteil / Cousin 1. Grades"),
    (215,   574, "Cousin 2. Grades / Großonkel/tante"),
    (90,    214, "Cousin 3. Grades"),
    (45,     89, "Cousin 4. Grades"),
    (20,     44, "Cousin 5. Grades"),
    (6,      19, "Entfernt verwandt"),
    (0,       5, "Sehr entfernt / Rauschen"),
]


def _cm_to_rel(cm: float) -> str:
    for lo, hi, label in _CM_RANGES:
        if lo <= cm <= hi:
            return label
    return ""


def _load_parish_lookup() -> dict:
    """Lädt matricula_parishes.json: Ortsname (lower) → Pfarrei-Info."""
    if not os.path.exists(PARISH_JSON):
        return {}
    try:
        with open(PARISH_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# Globaler Pfarrei-Lookup (einmal geladen)
_PARISH_LOOKUP: dict = _load_parish_lookup()


def _parish_for(birth_place: str) -> dict | None:
    """Gibt Pfarrei-Info für einen Geburtsort zurück oder None."""
    if not birth_place or not _PARISH_LOOKUP:
        return None
    place = birth_place.strip().lower()
    # Direkter Match
    if place in _PARISH_LOOKUP:
        return _PARISH_LOOKUP[place]
    # Erster Teil vor Komma/Klammer (z.B. "Hagen a.T.W., Landkreis Osnabrück")
    short = re.split(r"[,\(]", place)[0].strip()
    if short and short in _PARISH_LOOKUP:
        return _PARISH_LOOKUP[short]
    # Partial-Match: Lookup-Schlüssel der im Ortsnamen enthalten ist
    for key, val in _PARISH_LOOKUP.items():
        if key in place or place in key:
            return val
    return None


def _ro_connect(path: str) -> sqlite3.Connection | None:
    """Öffnet eine SQLite-DB read-only (URI-Modus), stört keinen Schreiber."""
    if not os.path.exists(path):
        return None
    try:
        uri = f"file:{path}?mode=ro&immutable=0"
        c = sqlite3.connect(uri, uri=True, timeout=5.0, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=4000")
        return c
    except Exception:
        try:
            c = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
            c.row_factory = sqlite3.Row
            return c
        except Exception:
            return None


def _rw_connect(path: str) -> sqlite3.Connection | None:
    """Öffnet eine SQLite-DB read-write und stellt sicher, dass xref existiert."""
    if not os.path.exists(path):
        return None
    try:
        c = sqlite3.connect(path, timeout=10.0, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS gedcom_person_xref (
                ged_id_main   TEXT,
                ged_id_other  TEXT,
                source_main   TEXT,
                source_other  TEXT,
                status        TEXT DEFAULT 'confirmed',
                PRIMARY KEY (ged_id_other, source_other)
            )""")
        c.commit()
        return c
    except Exception:
        return None


def _years(birth: str, death: str) -> str:
    b = (birth or "").strip()
    d = (death or "").strip()
    if not b and not d:
        return ""
    return f"{b or '?'}–{d or ''}".rstrip("–")


def _loads(s) -> list:
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


_NN_PATTERN = re.compile(r"\bN\.N\.?\b|/N\.N\.?/", re.IGNORECASE)


def _sanitize(text: str) -> str:
    """Replace 'N.N.' placeholders with '_____'."""
    return _NN_PATTERN.sub("_____", text or "").strip()


def _lighten(hex_color: str, amount: int = 30) -> str:
    """Return a lighter version of a #RRGGBB color."""
    try:
        r = min(255, int(hex_color[1:3], 16) + amount)
        g = min(255, int(hex_color[3:5], 16) + amount)
        b = min(255, int(hex_color[5:7], 16) + amount)
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return hex_color


# ── Matching-Hilfsfunktionen ────────────────────────────────────────────────

@functools.lru_cache(maxsize=65536)
def _norm_str(s: str) -> str:
    """Normalisiert einen String für Vergleiche (wie bridge._norm)."""
    s = (s or "").lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@functools.lru_cache(maxsize=65536)
def _koelner(name: str) -> str:
    """Kölner Phonetik — identisch mit bridge._koelner."""
    if not name:
        return ""
    name = name.upper().strip()
    name = (name.replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE")
            .replace("ß", "SS").replace("PH", "F").replace("TH", "T"))
    name = re.sub(r"[^A-Z]", "", name)
    if not name:
        return ""
    codes: list[str] = []
    n = len(name)
    for i, ch in enumerate(name):
        nxt  = name[i + 1] if i < n - 1 else ""
        prev = name[i - 1] if i > 0     else ""
        if ch in "AEIJOUY":   codes.append("0")
        elif ch == "H":        continue
        elif ch == "B":        codes.append("1")
        elif ch == "P":        codes.append("1" if nxt != "H" else "3")
        elif ch in "DT":       codes.append("2" if nxt not in "CSZ" else "8")
        elif ch in "FVW":      codes.append("3")
        elif ch in "GKQ":      codes.append("4")
        elif ch == "C":
            if i == 0:         codes.append("4" if nxt in "AHKLOQRUX" else "8")
            elif prev in "SZ": codes.append("8")
            elif nxt in "AHKOQUX": codes.append("4")
            else:              codes.append("8")
        elif ch == "X":        codes.extend(["4", "8"])
        elif ch == "L":        codes.append("5")
        elif ch in "MN":       codes.append("6")
        elif ch == "R":        codes.append("7")
        elif ch in "SZ":       codes.append("8")
    reduced: list[str] = []
    for c in codes:
        if not reduced or c != reduced[-1]:
            reduced.append(c)
    return "".join(reduced).lstrip("0") or "0"


def _score_pair(wt: dict, g: dict) -> float:
    """Berechnet einen Ähnlichkeits-Score zwischen einer wt_person und einer gedcom_person.
    Positiv = ähnlich; Threshold 5.0 → wahrscheinlich dieselbe Person."""
    score = 0.0

    # ── Nachname ─────────────────────────────────────────────────
    wt_sn = _norm_str(wt.get("surname") or "")
    g_sn  = g.get("surname_norm") or _norm_str(g.get("surname") or "")
    wt_kk = _koelner(wt_sn)
    g_kk  = g.get("koelner_code") or _koelner(g_sn)

    if not wt_sn or not g_sn:
        score -= 1.0           # fehlender Nachname → unsicher
    elif wt_sn == g_sn:
        score += 5.0           # exakter Norm-Match
    elif wt_kk and g_kk and wt_kk == g_kk:
        score += 3.0           # Kölner Phonetik stimmt überein
    elif wt_kk and g_kk and wt_kk[:3] == g_kk[:3]:
        score += 1.5           # Phonetik-Präfix stimmt
    else:
        score -= 3.0           # komplett anderer Nachname → sehr unwahrscheinlich

    # ── Vorname (erstes Token) ────────────────────────────────────
    wt_gn_raw = (wt.get("given_name") or "").strip()
    g_gn_raw  = (g.get("given_name") or "").strip()
    _wt_tok = wt_gn_raw.split()
    _g_tok  = g_gn_raw.split()
    wt_gn = _norm_str(_wt_tok[0]) if _wt_tok else ""
    g_gn  = _norm_str(_g_tok[0])  if _g_tok  else ""

    if wt_gn and g_gn:
        if wt_gn == g_gn:
            score += 4.0
        elif wt_gn[:3] == g_gn[:3]:   # Kürzungen wie "Wil" ↔ "Wilhelm"
            score += 2.0
        elif wt_gn in g_gn or g_gn in wt_gn:
            score += 1.0
        else:
            score -= 1.5
    elif not wt_gn and not g_gn:
        pass                   # beide fehlen – neutral
    else:
        score -= 0.5           # nur einer fehlt

    # ── Geburtsjahr ───────────────────────────────────────────────
    try:
        wt_by = int(wt.get("birth_year") or 0)
        g_by  = int(g.get("birth_year")  or 0)
    except (ValueError, TypeError):
        wt_by = g_by = 0
    if wt_by and g_by:
        diff = abs(wt_by - g_by)
        if diff == 0:
            score += 3.0
        elif diff <= 2:
            score += 2.0
        elif diff <= 5:
            score += 1.0
        elif diff <= 10:
            score -= 1.0
        else:
            score -= 4.0      # stark unterschiedliches Geburtsjahr

    # ── Geschlecht ────────────────────────────────────────────────
    wt_sex = (wt.get("sex") or "").upper()[:1]
    g_sex  = (g.get("sex")  or "").upper()[:1]
    if wt_sex and g_sex:
        if wt_sex == g_sex:
            score += 1.0
        else:
            score -= 6.0      # Geschlecht-Widerspruch → fast sicher falsch

    return score


def _sosa_to_rel(sosa: int, sex: str = "") -> str:
    """Convert a Sosa-Stradonitz number to a German relationship label."""
    if sosa <= 0:
        return ""
    if sosa == 1:
        return "Root"
    import math
    gen = int(math.log2(sosa))
    f = sex == "F"
    _LABELS = [
        ("Root",           "Root"),
        ("Vater",          "Mutter"),
        ("Großvater",      "Großmutter"),
        ("Urgroßvater",    "Urgroßmutter"),
        ("Ururgroßvater",  "Ururgroßmutter"),
    ]
    if gen < len(_LABELS):
        return _LABELS[gen][1 if f else 0]
    return f"Vorfahre {gen}. Gen."


def _rel_degree_label(dist_a: int, dist_b: int) -> str:
    """Verwandtschaftsgrad aus zwei Generationsabständen zum nächsten gemeinsamen Vorfahren."""
    if dist_a == 0 and dist_b == 0:
        return "Dieselbe Person"
    if dist_a == 0:
        labels = ["", "Kind", "Enkelkind", "Urenkelkind", "Ururenkind"]
        return labels[dist_b] if dist_b < len(labels) else f"Nachkomme ({dist_b}. Gen.)"
    if dist_b == 0:
        labels = ["", "Elternteil", "Großelternteil", "Urgroßelternteil", "Ururgroßelternteil"]
        return labels[dist_a] if dist_a < len(labels) else f"Vorfahre ({dist_a}. Gen.)"
    if dist_a == 1 and dist_b == 1:
        return "Geschwister"
    if dist_a == 1 and dist_b == 2:
        return "Nichte/Neffe"
    if dist_a == 2 and dist_b == 1:
        return "Onkel/Tante"
    if dist_a == 1 and dist_b == 3:
        return "Großnichte/Großneffe"
    if dist_a == 3 and dist_b == 1:
        return "Großonkel/Großtante"
    degree  = min(dist_a, dist_b) - 1
    removal = abs(dist_a - dist_b)
    deg_names = {1: "1. Grades", 2: "2. Grades", 3: "3. Grades", 4: "4. Grades", 5: "5. Grades"}
    base = f"Cousin/Cousine {deg_names.get(degree, f'{degree}. Grades')}"
    if removal == 0:
        return base
    removal_words = {1: "einmal", 2: "zweimal", 3: "dreimal"}
    suffix = f"{removal_words.get(removal, f'{removal}×')} entfernt"
    return f"{base}, {suffix}"


class _ToolTip:
    """Hover-Tooltip — erscheint nach 500 ms Verzögerung unter dem Widget."""
    _DELAY = 500

    def __init__(self, widget: tk.Widget, text: str):
        self._w, self._text = widget, text
        self._job: str | None  = None
        self._tw:  tk.Toplevel | None = None
        widget.bind("<Enter>",  self._schedule, add="+")
        widget.bind("<Leave>",  self._cancel,   add="+")
        widget.bind("<Button>", self._cancel,   add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._job = self._w.after(self._DELAY, self._show)

    def _cancel(self, _=None):
        if self._job:
            self._w.after_cancel(self._job)
            self._job = None
        if self._tw:
            self._tw.destroy()
            self._tw = None

    def _show(self):
        if self._tw:
            return
        x = self._w.winfo_rootx() + 20
        y = self._w.winfo_rooty() + self._w.winfo_height() + 4
        self._tw = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        tk.Label(tw, text=self._text, wraplength=320, justify="left",
                 bg="#1e2435", fg="#e8eaed", font=("Segoe UI", 9),
                 padx=10, pady=6, bd=1, relief="solid").pack()


class DataViewer(tk.Frame):
    """Eigenständig (master=None) oder eingebettet (master=<Frame>)."""

    def __init__(self, master=None, db_path: str | None = None):
        self._embedded = master is not None
        if master is None:
            master = tk.Tk()
        super().__init__(master, bg=C["bg"])
        root = self.winfo_toplevel()
        if not self._embedded:
            root.title("Genealogie-Datenviewer")
            root.geometry("1280x820")
            root.minsize(1000, 640)
            root.configure(bg=C["bg"])
        self.pack(fill="both", expand=True)

        self._db_path = db_path or CRAWL_DB
        self._source  = "anverwandte"        # anverwandte | gedcom
        self._conn: sqlite3.Connection | None = None
        self._anc_conn: sqlite3.Connection | None = None
        self._anc_write: sqlite3.Connection | None = None  # Schreib-Verbindung für xref
        self._current_id: str | None = None
        self._name_cache: dict[str, str] = {}
        self._history: list[str] = []

        # GEDCOM-Mapping-Caches
        self._gedcom_map: dict[str, str] = {}    # wt_id  → ged_id (bestätigt via xref)
        self._fuzzy_map:  dict[str, str] = {}    # wt_id  → ged_id (fuzzy Name+Jahr)
        self._auto_map:   dict[str, str] = {}    # wt_id  → ged_id (auto Score-Matching)
        self._auto_scores: dict[str, float] = {} # wt_id  → Score
        self._cluster_map: dict[str, int] = {}   # ged_id → cluster_id
        self._dna_map: dict[str, tuple] = {}     # ged_id → (best_cm, match_name)
        self._sosa_map: dict[str, tuple] = {}    # ged_id → (sosa_number, sex)
        self._sosa_rev: dict[int, str] = {}      # sosa_number → ged_id (für Pfad)
        self._rejected: set[str] = set()          # wt_ids mit abgelehntem Match
        self._ged_cache: dict[str, dict] = {}    # ged_id → person-dict (für Sub-Zeilen)
        self._sub_ids: set[str] = set()          # iids von eingerückten GEDCOM-Zeilen
        self._parish_cache: dict[str, dict | None] = {}  # birth_place → parish-info
        self._undo_stack: list[dict] = []        # für Rückgängig-Funktion
        self._filter_state: dict[str, tuple] = {}  # source → (flt, conf, src, q)
        self._rel_target: str | None = None      # Person A für Verwandtschaftspfad
        self._rel_target_name: str = ""

        self._build()
        # Defer heavy DB init so the window appears before blocking work starts
        self.after(0, self._deferred_load)

    # ── DB ────────────────────────────────────────────────────────────────────
    def _deferred_load(self):
        """Runs after the first mainloop iteration so the window paints first."""
        self._open_db()
        self._refresh_stats()
        self._do_search()

    def _ensure_indexes(self):
        """Create read-optimised indexes if not yet present.

        Two target DBs:
          • Crawl-DB (wt_persons)   – Sortier-/Such-Indizes
          • ancestry_dna.db         – DNA-Join-Indizes (gedcom_links ⋈ matches),
            ohne die jeder Personen-Klick die ganze matches-Tabelle scannt und
            die GUI einfriert.
        Braucht je eine Write-Verbindung; überspringt still, wenn DB fehlt/gesperrt.
        """
        import sqlite3 as _sq3

        def _make(db_path: str, statements: list[str]):
            if not os.path.exists(db_path):
                return
            try:
                wc = _sq3.connect(db_path, timeout=3.0)
            except Exception:
                return
            for stmt in statements:
                try:
                    wc.execute(stmt)
                except Exception:
                    # Tabelle/Spalte evtl. (noch) nicht vorhanden – nächste versuchen
                    pass
            try:
                wc.commit()
            finally:
                wc.close()

        # Crawl-DB: nur wenn wt_persons dort existiert (anverwandte-Quelle)
        crawl_db = self._db_path if self._source == "anverwandte" else None
        if crawl_db:
            _make(crawl_db, [
                "CREATE INDEX IF NOT EXISTS idx_wtp_sort "
                "ON wt_persons(surname, given_name)",
                "CREATE INDEX IF NOT EXISTS idx_wtp_search "
                "ON wt_persons(surname, given_name, name)",
            ])

        # ancestry_dna.db: DNA-Join-Indizes – immer sicherstellen
        _make(ANCESTRY_DB, [
            "CREATE INDEX IF NOT EXISTS idx_gl_ged    ON gedcom_links(ged_id)",
            "CREATE INDEX IF NOT EXISTS idx_gl_guid   ON gedcom_links(match_guid)",
            "CREATE INDEX IF NOT EXISTS idx_m_guid    ON matches(match_guid)",
            "CREATE INDEX IF NOT EXISTS idx_m_cluster ON matches(cluster_id)",
        ])

    def _open_db(self):
        if self._source == "anverwandte":
            self._conn = _ro_connect(self._db_path)
        else:
            self._conn = _ro_connect(ANCESTRY_DB)
        self._anc_conn = _ro_connect(ANCESTRY_DB)
        self._anc_write = _rw_connect(ANCESTRY_DB)
        if self._conn is None:
            self._status.set("⚠ Datenbank nicht gefunden / noch nicht angelegt: "
                             + (self._db_path if self._source == "anverwandte"
                                else ANCESTRY_DB))
        self._ensure_indexes()
        self._load_rejected()
        self._load_gedcom_mapping()
        self._load_clusters()
        self._load_dna_match_map()
        self._load_sosa_map()
        self._refresh_dna_src_dropdown()
        # _build_auto_match is slow (scores wt_persons vs gedcom_persons); run in background
        import threading
        def _bg_auto():
            self._build_auto_match()
            self.after(0, self._refresh_dna_src_dropdown)
            self.after(0, self._do_search)
            self.after(0, lambda: self._status.set(
                f"✓ Auto-Match fertig — {len(self._auto_map)} Zuordnungen"))
        threading.Thread(target=_bg_auto, daemon=True).start()

    def _reopen(self):
        for c in (self._conn, self._anc_conn, self._anc_write):
            try:
                if c:
                    c.close()
            except Exception:
                pass
        self._anc_write = None
        self._name_cache.clear()
        self._parish_cache.clear()
        self._open_db()
        self._refresh_stats()
        self._do_search()

    # ── GEDCOM-Mapping ────────────────────────────────────────────────────────
    def _load_gedcom_mapping(self):
        """Befüllt _gedcom_map (bestätigt) und _fuzzy_map (Schätzung)."""
        self._gedcom_map.clear()
        self._fuzzy_map.clear()
        if not self._anc_conn:
            return

        # 1) Bestätigte Links aus gedcom_person_xref
        try:
            rows = self._anc_conn.execute(
                "SELECT ged_id_main, ged_id_other, source_main, source_other "
                "FROM gedcom_person_xref WHERE status != 'rejected'"
            ).fetchall()
            for r in rows:
                m, o  = r["ged_id_main"],   r["ged_id_other"]
                sm, so = r["source_main"], r["source_other"]
                if so == "anverwandte":
                    self._gedcom_map[o] = m
                elif sm == "anverwandte":
                    self._gedcom_map[m] = o
        except Exception:
            pass

        # 2) Fuzzy-Fallback: gleicher Nachname + Geburtsjahr ±5
        if self._source != "anverwandte" or not self._conn:
            return
        try:
            ged_rows = self._anc_conn.execute(
                "SELECT ged_id, surname, birth_year FROM gedcom_persons "
                "WHERE source='gedcom'"
            ).fetchall()
        except Exception:
            return

        # Nachname → [(ged_id, birth_year)]
        ged_index: dict[str, list[tuple]] = {}
        for r in ged_rows:
            sn = (r["surname"] or "").strip().lower()
            if sn:
                ged_index.setdefault(sn, []).append((r["ged_id"], r["birth_year"]))

        try:
            wt_rows = self._conn.execute(
                "SELECT id, surname, birth_year FROM wt_persons"
            ).fetchall()
        except Exception:
            return

        for r in wt_rows:
            wt_id = str(r["id"])
            if wt_id in self._gedcom_map:
                continue
            sn = (r["surname"] or "").strip().lower()
            if not sn:
                continue
            by_raw = r["birth_year"]
            candidates = ged_index.get(sn, [])
            best_score, best_id = -99, None
            for ged_id, ged_by in candidates:
                score = 0
                try:
                    if by_raw and ged_by:
                        diff = abs(int(by_raw) - int(ged_by))
                        score = 3 if diff == 0 else 2 if diff <= 2 else 1 if diff <= 5 else (
                            0 if diff <= 10 else -2)
                    elif not by_raw and not ged_by:
                        score = 1
                    else:
                        score = -1
                except (ValueError, TypeError):
                    pass
                if score > best_score:
                    best_score, best_id = score, ged_id
            if best_id is not None and best_score >= 0:
                self._fuzzy_map[wt_id] = str(best_id)

    def _load_clusters(self):
        """Befüllt _cluster_map: ged_id → cluster_id aus der DNA-Datenbank."""
        self._cluster_map.clear()
        if not self._anc_conn:
            return
        # Versuche über gedcom_links (match_guid → ged_id) + matches.cluster_id
        for sql in (
            ("SELECT gl.ged_id, m.cluster_id FROM gedcom_links gl "
             "JOIN matches m ON m.match_guid = gl.match_guid "
             "WHERE m.cluster_id IS NOT NULL"),
            ("SELECT ged_id, cluster_id FROM gedcom_person_cluster "
             "WHERE cluster_id IS NOT NULL"),
        ):
            try:
                rows = self._anc_conn.execute(sql).fetchall()
                for r in rows:
                    ged_id = str(r["ged_id"])
                    if ged_id not in self._cluster_map:
                        self._cluster_map[ged_id] = int(r["cluster_id"])
                if self._cluster_map:
                    break
            except Exception:
                continue

    def _load_dna_match_map(self):
        """Befüllt _dna_map: ged_id → (cm_or_None, match_name, source_set)."""
        self._dna_map.clear()
        if not self._anc_conn:
            return
        try:
            rows = self._anc_conn.execute(
                "SELECT gl.ged_id, m.name, MAX(m.shared_cm) AS cm, "
                "GROUP_CONCAT(DISTINCT m.source) AS sources "
                "FROM gedcom_links gl "
                "JOIN matches m ON m.match_guid = gl.match_guid "
                "GROUP BY gl.ged_id"
            ).fetchall()
            for r in rows:
                cm = float(r["cm"]) if r["cm"] is not None else None
                srcs = set((r["sources"] or "").split(",")) - {""}
                self._dna_map[str(r["ged_id"])] = (cm, r["name"] or "", srcs)
        except Exception:
            pass

    def _load_sosa_map(self):
        """Lädt sosa_number + sex für alle gedcom_persons; baut auch _sosa_rev auf."""
        self._sosa_map.clear()
        self._sosa_rev.clear()
        if not self._anc_conn:
            return
        try:
            rows = self._anc_conn.execute(
                "SELECT ged_id, sosa_number, sex FROM gedcom_persons "
                "WHERE sosa_number > 0"
            ).fetchall()
            for r in rows:
                gid  = str(r["ged_id"])
                sosa = r["sosa_number"] or 0
                self._sosa_map[gid] = (sosa, r["sex"] or "")
                self._sosa_rev[sosa] = gid
        except Exception:
            pass

    def _build_auto_match(self):
        """Score-basiertes Mapping von wt_persons → gedcom_persons.

        Läuft einmalig beim DB-Öffnen. Befüllt _auto_map (wt_id → ged_id)
        und _ged_cache (ged_id → person-dict) für alle gematchten Personen.
        """
        self._auto_map.clear()
        self._auto_scores.clear()
        self._ged_cache.clear()

        if not self._anc_conn:
            return

        # ── Alle gedcom_persons aus dem GEDCOM laden (nicht Anverwandte-Einträge)
        try:
            g_rows = self._anc_conn.execute(
                "SELECT ged_id, given_name, surname, surname_norm, koelner_code, "
                "sex, birth_year, birth_place, death_year, sosa_number "
                "FROM gedcom_persons WHERE source = 'gedcom'"
            ).fetchall()
        except Exception:
            return
        if not g_rows:
            return

        # Index: koelner_code[:3] → liste von gedcom-dicts
        ged_by_kk: dict[str, list[dict]] = {}
        for r in g_rows:
            g = dict(r)
            kk = (g["koelner_code"] or "")[:3]
            if kk:
                ged_by_kk.setdefault(kk, []).append(g)
            # Auch erste 3 Zeichen von surname_norm als Fallback
            sn3 = (g["surname_norm"] or "")[:3]
            if sn3 and sn3 != kk:
                ged_by_kk.setdefault("n:" + sn3, []).append(g)

        # Bereits gematchte wt_ids
        already = set(self._gedcom_map) | set(self._fuzzy_map)

        if not self._conn:
            return
        try:
            wt_rows = self._conn.execute(
                "SELECT id, given_name, surname, birth_year, sex "
                "FROM wt_persons"
            ).fetchall()
        except Exception:
            return

        THRESHOLD = 5.0
        import time
        n_total = len(wt_rows)

        for idx, wt_row in enumerate(wt_rows):
            # GIL regelmäßig abgeben, damit die UI flüssig bleibt, und
            # Fortschritt in der Statuszeile anzeigen
            if idx % 200 == 0:
                time.sleep(0.002)
                if idx:
                    pct = idx * 100 // n_total
                    self.after(0, lambda p=pct: self._status.set(
                        f"⏳ Auto-Match läuft im Hintergrund … {p} %"))
            wt_id = str(wt_row["id"])
            if wt_id in already:
                continue
            if wt_id in self._rejected:
                continue

            wt = dict(wt_row)
            wt_sn = _norm_str(wt.get("surname") or "")
            wt_kk = _koelner(wt_sn)[:3]
            wt_sn3 = wt_sn[:3]

            # Kandidaten per Phonetik-Index
            candidates: dict[str, dict] = {}  # ged_id → g
            for key in ([wt_kk] if wt_kk else []) + (["n:" + wt_sn3] if wt_sn3 else []):
                for g in ged_by_kk.get(key, []):
                    candidates[g["ged_id"]] = g

            best_score = THRESHOLD - 0.001
            best_ged_id: str | None = None
            for g in candidates.values():
                s = _score_pair(wt, g)
                if s > best_score:
                    best_score = s
                    best_ged_id = g["ged_id"]

            if best_ged_id:
                self._auto_map[wt_id] = best_ged_id
                self._auto_scores[wt_id] = round(best_score, 1)

        # _ged_cache: alle gematchten ged_ids + alle SOSA-Vorfahren (für Pfad-Anzeige)
        all_ged_ids = (set(self._gedcom_map.values()) |
                       set(self._fuzzy_map.values()) |
                       set(self._auto_map.values()))
        if all_ged_ids:
            try:
                placeholders = ",".join("?" * len(all_ged_ids))
                rows = self._anc_conn.execute(
                    f"SELECT ged_id, given_name, surname, sex, birth_year, "
                    f"birth_place, death_year, sosa_number "
                    f"FROM gedcom_persons WHERE ged_id IN ({placeholders})",
                    list(all_ged_ids),
                ).fetchall()
                for r in rows:
                    self._ged_cache[r["ged_id"]] = dict(r)
            except Exception:
                pass
        # Alle SOSA-Vorfahren für den Vorfahrenpfad laden
        try:
            rows = self._anc_conn.execute(
                "SELECT ged_id, given_name, surname, sex, birth_year, "
                "birth_place, death_year, sosa_number "
                "FROM gedcom_persons WHERE sosa_number > 0"
            ).fetchall()
            for r in rows:
                if r["ged_id"] not in self._ged_cache:
                    self._ged_cache[r["ged_id"]] = dict(r)
        except Exception:
            pass

    # ── Rejected-Set laden ──────────────────────────────────────────────────
    def _load_rejected(self):
        """Lädt abgelehnte Paare aus gedcom_person_xref in _rejected."""
        self._rejected.clear()
        if not self._anc_conn:
            return
        try:
            rows = self._anc_conn.execute(
                "SELECT ged_id_main, ged_id_other FROM gedcom_person_xref "
                "WHERE status = 'rejected' AND source_other = 'anverwandte'"
            ).fetchall()
            for r in rows:
                self._rejected.add(str(r["ged_id_other"]))
        except Exception:
            pass

    # ── Vorfahrenpfad ────────────────────────────────────────────────────────
    def _ancestor_path(self, ged_id: str) -> list:
        """Pfad von Root (SOSA 1) zur angegebenen Person via SOSA-Arithmetik.
        Gibt [(ged_id, name, sosa, rel_label), ...] zurück (Root zuerst)."""
        import math
        info = self._sosa_map.get(ged_id)
        if not info or not info[0]:
            return []
        sosa = info[0]
        path = []
        s = sosa
        while s >= 1:
            gid = self._sosa_rev.get(s, "")
            g   = self._ged_cache.get(gid, {})
            gn  = _sanitize(g.get("given_name") or "")
            sn  = _sanitize(g.get("surname") or "")
            name = f"{gn} {sn}".strip() or (gid or f"SOSA {s}")
            gen  = int(math.log2(s)) if s > 0 else 0
            rel  = _sosa_to_rel(s, g.get("sex") or "")
            path.append((gid, name, s, rel))
            if s <= 1:
                break
            s = s // 2
        path.reverse()
        return path

    # ── Verwandtschaftspfad zwischen beliebigen zwei Personen ───────────────
    def _find_ancestors_bfs(self, wt_id: str, max_gen: int = 18
                            ) -> tuple[dict[str, int], dict[str, str | None]]:
        """BFS aufwärts durch parents_json.
        Gibt (dist{id→Generationen}, prev{id→Kind_das_zu_x_führte}) zurück."""
        dist: dict[str, int] = {wt_id: 0}
        prev: dict[str, str | None] = {wt_id: None}
        queue: deque[tuple[str, int]] = deque([(wt_id, 0)])
        while queue:
            curr, d = queue.popleft()
            if d >= max_gen:
                continue
            p = self._person(curr)
            if not p:
                continue
            for par in _loads(p.get("parents_json")):
                if par not in dist:
                    dist[par] = d + 1
                    prev[par] = curr
                    queue.append((par, d + 1))
        return dist, prev

    def _trace_path_upward(self, target: str, prev: dict) -> list[str]:
        """Rekonstruiert [start, …, target] aus BFS-prev-Zeigern (start = Node ohne Vorgänger)."""
        path: list[str] = []
        curr: str | None = target
        while curr is not None:
            path.append(curr)
            curr = prev.get(curr)
        return list(reversed(path))

    def _compute_relationship(self, id_a: str, id_b: str):
        """Findet den nächsten gemeinsamen Vorfahren (LCA) und gibt den vollständigen Pfad zurück.
        Rückgabe: (path_a_to_lca, path_b_to_lca, dist_a, dist_b, lca_id) oder None."""
        if id_a == id_b:
            return None
        dist_a, prev_a = self._find_ancestors_bfs(id_a)
        dist_b, prev_b = self._find_ancestors_bfs(id_b)
        common = set(dist_a.keys()) & set(dist_b.keys())
        if not common:
            return None
        lca = min(common, key=lambda x: dist_a[x] + dist_b[x])
        path_a = self._trace_path_upward(lca, prev_a)  # id_a → … → lca
        path_b = self._trace_path_upward(lca, prev_b)  # id_b → … → lca
        return path_a, path_b, dist_a[lca], dist_b[lca], lca

    def _show_rel_path_window(self, id_a: str, id_b: str):
        """Öffnet Fenster mit dem Verwandtschaftspfad zwischen zwei Personen."""
        result = self._compute_relationship(id_a, id_b)

        win = tk.Toplevel(self.winfo_toplevel())
        win.title("Verwandtschaftspfad")
        win.geometry("640x540")
        win.configure(bg=C["bg"])

        cv = tk.Canvas(win, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(win, orient="vertical", command=cv.yview)
        fr = tk.Frame(cv, bg=C["bg"])
        fr.bind("<Configure>", lambda _e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=fr, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def row(text, fg=C["text"], font=("Segoe UI", 9), padx=16, pady=1, anchor="w"):
            tk.Label(fr, text=text, bg=C["bg"], fg=fg, font=font,
                     anchor=anchor, padx=padx, pady=pady, wraplength=580).pack(fill="x")

        name_a = self._label_for(id_a).replace("\n", " ")
        name_b = self._label_for(id_b).replace("\n", " ")

        row("🔗 Verwandtschaftspfad", fg=C["accent"], font=("Segoe UI", 13, "bold"), pady=(16, 4))

        if result is None:
            row("Keine nachweisliche Verwandtschaft gefunden.", fg=C["muted"], font=("Segoe UI", 10))
            row(f"  • {name_a}", fg=C["text"])
            row(f"  • {name_b}", fg=C["text"])
            row("(Der verfügbare Baum reicht möglicherweise nicht weit genug zurück.)",
                fg=C["muted"], font=("Segoe UI", 8))
            tk.Button(fr, text="Schließen", command=win.destroy,
                      bg=C["card"], fg=C["text"], relief="flat", padx=10).pack(pady=12)
            return

        path_a, path_b, dist_a, dist_b, lca = result
        rel_label = _rel_degree_label(dist_a, dist_b)
        lca_name  = self._label_for(lca).replace("\n", " ")

        row(name_a, fg=C["accent"], font=("Segoe UI", 10, "bold"), pady=2)
        row(f"  ist  {rel_label}  von", fg=C["dna"], font=("Segoe UI", 11, "bold"), pady=2)
        row(name_b, fg=C["accent"], font=("Segoe UI", 10, "bold"), pady=2)
        row(f"Gemeinsamer Vorfahre: {lca_name}", fg=C["muted"], pady=(4, 0))
        row(f"Generationsabstand: Person A = {dist_a},  Person B = {dist_b}",
            fg=C["muted"], font=("Segoe UI", 8), pady=(0, 4))
        tk.Frame(fr, bg=C["card"], height=1).pack(fill="x", padx=16, pady=6)

        # Vollständiger Pfad: A → … → LCA → … → B
        full_path: list[str] = path_a + list(reversed(path_b))[1:]  # LCA nicht doppelt
        lca_idx = len(path_a) - 1

        row("Pfad:", fg=C["accent"], font=("Segoe UI", 9, "bold"))

        for i, pid in enumerate(full_path):
            is_lca   = (i == lca_idx)
            is_start = (i == 0)
            is_end   = (i == len(full_path) - 1)
            going_up = (i < lca_idx)

            entry_row = tk.Frame(fr, bg=C["bg"]); entry_row.pack(fill="x", padx=24, pady=1)

            sym       = "◆" if is_lca else ("●" if (is_start or is_end) else "○")
            sym_color = C["dna"] if is_lca else (C["accent"] if (is_start or is_end) else C["muted"])
            tk.Label(entry_row, text=sym, bg=C["bg"], fg=sym_color,
                     font=("Segoe UI", 10), width=2).pack(side="left")

            pname = self._label_for(pid).replace("\n", " ")
            if is_lca:
                display = f"{pname}  ← Gemeinsamer Vorfahre"
                fg_c = C["dna"]; fnt = ("Segoe UI", 9, "bold")
            elif is_start:
                display = f"{pname}  (Person A)"
                fg_c = C["accent"]; fnt = ("Segoe UI", 9, "bold")
            elif is_end:
                display = f"{pname}  (Person B)"
                fg_c = C["accent"]; fnt = ("Segoe UI", 9, "bold")
            else:
                display = pname
                fg_c = C["link"]; fnt = ("Segoe UI", 9)

            lbl = tk.Label(entry_row, text=display, bg=C["bg"], fg=fg_c,
                           font=fnt, anchor="w", cursor="hand2")
            lbl.pack(side="left", fill="x", expand=True)
            _pid = pid
            lbl.bind("<Button-1>", lambda _, p=_pid: self._navigate(p))

            if i < len(full_path) - 1:
                arrow = "↑" if going_up else "↓"
                tk.Label(fr, text=f"   {arrow}", bg=C["bg"], fg=C["muted"],
                         font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=42)

        tk.Frame(fr, bg=C["card"], height=1).pack(fill="x", padx=16, pady=8)
        tk.Button(fr, text="Schließen", command=win.destroy,
                  bg=C["card"], fg=C["text"], relief="flat", padx=10).pack(pady=8)

    def _set_rel_target(self, wt_id: str, name: str):
        """Setzt Person A für den Verwandtschaftspfad und aktualisiert das Detail-Panel."""
        self._rel_target      = wt_id
        self._rel_target_name = name
        if self._current_id:
            self._render_detail(self._current_id)

    def _clear_rel_target(self, render: bool = True):
        """Löscht die gespeicherte Person A und aktualisiert das Panel."""
        self._rel_target      = None
        self._rel_target_name = ""
        if render and self._current_id:
            self._render_detail(self._current_id)

    # ── Bestätigen / Ablehnen ────────────────────────────────────────────────
    def _confirm_match(self, wt_id: str, ged_id: str, _push=True):
        """Schreibt ein bestätigtes Mapping in gedcom_person_xref."""
        if not self._anc_write:
            messagebox.showerror("Fehler", "Keine Schreibverbindung zur Datenbank.")
            return
        try:
            self._anc_write.execute(
                "INSERT OR REPLACE INTO gedcom_person_xref "
                "(ged_id_main, ged_id_other, source_main, source_other, status) "
                "VALUES (?, ?, 'gedcom', 'anverwandte', 'confirmed')",
                (ged_id, wt_id)
            )
            self._anc_write.commit()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            return
        if _push:
            prev = ("auto" if wt_id in self._auto_map else
                    "fuzzy" if wt_id in self._fuzzy_map else "none")
            self._push_undo("confirm", wt_id, ged_id, prev)
        # In-memory aktualisieren
        self._gedcom_map[wt_id] = ged_id
        self._fuzzy_map.pop(wt_id, None)
        self._auto_map.pop(wt_id, None)
        self._rejected.discard(wt_id)
        self._do_search()
        self.after(50, lambda: self._navigate(wt_id, push=False))

    def _reject_match(self, wt_id: str, ged_id: str, _push=True):
        """Schreibt 'rejected' in xref — verhindert künftige Auto-Matches."""
        if _push:
            prev = ("confirmed" if wt_id in self._gedcom_map else
                    "fuzzy" if wt_id in self._fuzzy_map else
                    "auto" if wt_id in self._auto_map else "none")
            self._push_undo("reject", wt_id, ged_id, prev)
        if self._anc_write:
            try:
                self._anc_write.execute(
                    "INSERT OR REPLACE INTO gedcom_person_xref "
                    "(ged_id_main, ged_id_other, source_main, source_other, status) "
                    "VALUES (?, ?, 'gedcom', 'anverwandte', 'rejected')",
                    (ged_id, wt_id)
                )
                self._anc_write.commit()
            except Exception:
                pass
        # In-memory entfernen
        self._gedcom_map.pop(wt_id, None)
        self._fuzzy_map.pop(wt_id, None)
        self._auto_map.pop(wt_id, None)
        self._rejected.add(wt_id)
        self._do_search()

    # ── DNA-Statistik-Fenster ────────────────────────────────────────────────
    def _show_stats_window(self):
        """Öffnet ein Toplevel-Fenster mit DNA-Match-Statistiken."""
        win = tk.Toplevel(self.winfo_toplevel())
        win.title("DNA-Statistiken")
        win.geometry("760x640")
        win.configure(bg=C["bg"])

        cv = tk.Canvas(win, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(win, orient="vertical", command=cv.yview)
        fr = tk.Frame(cv, bg=C["bg"])
        fr.bind("<Configure>", lambda _: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=fr, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def hdr(t):
            tk.Label(fr, text=t, bg=C["bg"], fg=C["accent"],
                     font=("Segoe UI", 11, "bold"), anchor="w").pack(
                fill="x", padx=16, pady=(16, 4))

        def row(label, value, color=None):
            f = tk.Frame(fr, bg=C["bg"]); f.pack(fill="x", padx=24, pady=1)
            tk.Label(f, text=label, bg=C["bg"], fg=C["muted"], width=36,
                     anchor="w", font=("Segoe UI", 9)).pack(side="left")
            tk.Label(f, text=str(value), bg=C["bg"],
                     fg=color or C["text"], anchor="w",
                     font=("Segoe UI", 9)).pack(side="left")

        if not self._anc_conn:
            tk.Label(fr, text="Keine Datenbank.", bg=C["bg"],
                     fg=C["muted"]).pack(pady=20)
            return

        # ── Übersicht ─────────────────────────────────────────────────────
        hdr("Übersicht")
        try:
            r_t = self._anc_conn.execute("SELECT COUNT(*) FROM matches").fetchone()
            total = r_t[0] if r_t else 0
            row("Gesamt DNA-Matches", f"{total:,}".replace(",", "."))
        except Exception:
            pass
        try:
            srcs = self._anc_conn.execute(
                "SELECT source, COUNT(*) AS n FROM matches GROUP BY source"
            ).fetchall()
            for s in srcs:
                row(f"  Quelle: {s['source'] or 'unbekannt'}", s['n'])
        except Exception:
            pass
        row("Im GEDCOM verknüpft (ged_id)",
            len(self._dna_map), C["dna"])
        row("Davon mit SOSA-Vorfahrenpfad",
            sum(1 for gid in self._dna_map if gid in self._sosa_map),
            C["accent"])

        # ── cM-Verteilung ────────────────────────────────────────────────
        hdr("cM-Verteilung nach erwartetem Verwandtschaftsgrad")
        try:
            cm_rows = self._anc_conn.execute(
                "SELECT shared_cm FROM matches WHERE shared_cm IS NOT NULL"
            ).fetchall()
            cm_vals = [float(r[0]) for r in cm_rows if r[0]]
            buckets: dict[str, int] = {}
            for cm in cm_vals:
                lbl = _cm_to_rel(cm) or "?"
                buckets[lbl] = buckets.get(lbl, 0) + 1
            total_cm = len(cm_vals)
            for _, _, label in _CM_RANGES:
                n = buckets.get(label, 0)
                if n:
                    pct = 100 * n / total_cm if total_cm else 0
                    bar = "█" * min(30, int(pct / 2))
                    row(label, f"{n:>5}   {bar} {pct:.1f}%")
        except Exception as e:
            row("Fehler", str(e))

        # ── Top-Namen ─────────────────────────────────────────────────────
        hdr("Häufigste Namen unter DNA-Matches (Top 25)")
        try:
            name_rows = self._anc_conn.execute(
                "SELECT name, COUNT(*) AS n FROM matches "
                "WHERE name IS NOT NULL GROUP BY name ORDER BY n DESC LIMIT 25"
            ).fetchall()
            for r in name_rows:
                row(r["name"] or "–", r["n"])
        except Exception:
            pass

        # ── Cluster-Übersicht ─────────────────────────────────────────────
        hdr("DNA-Cluster")
        try:
            cl_rows = self._anc_conn.execute(
                "SELECT cluster_id, COUNT(*) AS n FROM matches "
                "WHERE cluster_id IS NOT NULL "
                "GROUP BY cluster_id ORDER BY cluster_id"
            ).fetchall()
            if cl_rows:
                for r in cl_rows:
                    row(f"Cluster {r['cluster_id']}", f"{r['n']} Matches")
            else:
                row("Keine Cluster angelegt", "")
        except Exception:
            pass

        # ── Auto-Match-Status ─────────────────────────────────────────────
        hdr("Auto-Match-Status")
        row("Bestätigte Verknüpfungen", len(self._gedcom_map), C["mapped"])
        row("Fuzzy-Matches",            len(self._fuzzy_map),  C["fuzzy"])
        row("Auto-Matches (Score)",     len(self._auto_map),   C["dna"])
        row("Abgelehnte Personen",      len(self._rejected),   C["muted"])
        if self._auto_scores:
            scores = list(self._auto_scores.values())
            row("  Ø Score Auto-Matches",
                f"{sum(scores)/len(scores):.1f}  (min {min(scores):.1f} / max {max(scores):.1f})")

        # ── Fehlende Personen ─────────────────────────────────────────────
        hdr("Lückenanalyse")
        try:
            r2 = self._anc_conn.execute(
                "SELECT COUNT(*) FROM gedcom_persons gp "
                "WHERE gp.source='gedcom' AND NOT EXISTS "
                "(SELECT 1 FROM gedcom_links gl WHERE gl.ged_id = gp.ged_id)"
            ).fetchone()
            row("GEDCOM-Personen ohne DNA-Match", r2[0] if r2 else "?", C["muted"])
        except Exception:
            pass
        try:
            r3 = self._anc_conn.execute(
                "SELECT COUNT(DISTINCT m.match_guid) FROM matches m "
                "WHERE NOT EXISTS "
                "(SELECT 1 FROM gedcom_links gl WHERE gl.match_guid = m.match_guid)"
            ).fetchone()
            row("DNA-Matches ohne GEDCOM-Eintrag", r3[0] if r3 else "?", C["fuzzy"])
        except Exception:
            pass
        try:
            r4 = self._anc_conn.execute(
                "SELECT COUNT(*) FROM wt_persons").fetchone()
            wt_total = r4[0] if r4 else 0
            wt_mapped = len(self._gedcom_map) + len(self._fuzzy_map) + len(self._auto_map)
            row("Anverwandte ohne Mapping",
                f"{wt_total - wt_mapped} von {wt_total}", C["card"])
        except Exception:
            pass

    # ── DNA-Quellen-Dropdown befüllen ─────────────────────────────────────────
    def _refresh_dna_src_dropdown(self):
        srcs = {"Alle"}
        for _, _, src_set in self._dna_map.values():
            srcs.update(src_set)
        values = ["Alle"] + sorted(srcs - {"Alle"})
        try:
            self._dna_src_box["values"] = values
            if self._dna_src_var.get() not in values:
                self._dna_src_var.set("Alle")
        except Exception:
            pass

    # ── Undo-Stack ────────────────────────────────────────────────────────────
    def _push_undo(self, action: str, wt_id: str, ged_id: str, prev: str):
        self._undo_stack.append({"action": action, "wt_id": wt_id,
                                  "ged_id": ged_id, "prev": prev})
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)
        try:
            self._undo_btn.configure(state="normal", fg=C["text"])
        except Exception:
            pass

    def _undo_last(self):
        if not self._undo_stack:
            return
        op = self._undo_stack.pop()
        wt_id, ged_id, action, prev = op["wt_id"], op["ged_id"], op["action"], op["prev"]

        # xref-Eintrag rückgängig machen
        if self._anc_write:
            try:
                if prev in ("auto", "fuzzy", None):
                    self._anc_write.execute(
                        "DELETE FROM gedcom_person_xref "
                        "WHERE ged_id_other=? AND source_other='anverwandte'", (wt_id,))
                else:
                    self._anc_write.execute(
                        "INSERT OR REPLACE INTO gedcom_person_xref "
                        "(ged_id_main, ged_id_other, source_main, source_other, status) "
                        "VALUES (?, ?, 'gedcom', 'anverwandte', ?)",
                        (ged_id, wt_id, prev))
                self._anc_write.commit()
            except Exception:
                pass

        # In-memory wiederherstellen
        if action == "confirm":
            self._gedcom_map.pop(wt_id, None)
            if prev == "fuzzy":
                self._fuzzy_map[wt_id] = ged_id
            elif prev == "auto":
                self._auto_map[wt_id] = ged_id
        elif action == "reject":
            self._rejected.discard(wt_id)
            if prev == "confirmed":
                self._gedcom_map[wt_id] = ged_id
            elif prev == "fuzzy":
                self._fuzzy_map[wt_id] = ged_id
            elif prev == "auto":
                self._auto_map[wt_id] = ged_id

        if not self._undo_stack:
            try:
                self._undo_btn.configure(state="disabled", fg=C["muted"])
            except Exception:
                pass
        self._do_search()

    # ── Bulk-Confirm-Fenster ──────────────────────────────────────────────────
    # ── Tools-Fenster ────────────────────────────────────────────────────────

    def _show_tools_window(self):
        """Springt direkt zum Werkzeuge-Tab (bleibt für Rückwärtskompatibilität)."""
        self._nb.select(self._tools_tab)

    # ── gemeinsame Hilfs-Methoden ─────────────────────────────────────────────

    def _tool_help(self, parent, lines: list[str]):
        """Erklär-Panel oben in einem Tab (Was tut das Tool / Voraussetzungen)."""
        f = tk.Frame(parent, bg=C["card"])
        f.pack(fill="x", padx=6, pady=(6, 0))
        tk.Label(f, text="\n".join(lines), bg=C["card"], fg=C["text"],
                 justify="left", anchor="w", wraplength=890,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=8)

    def _tool_log_widget(self, parent) -> tk.Text:
        """Erzeugt ein dunkles Log-Textfeld mit Scrollbar."""
        f = tk.Frame(parent, bg=C["bg"])
        f.pack(fill="both", expand=True, padx=6, pady=(4, 6))
        sb = tk.Scrollbar(f)
        sb.pack(side="right", fill="y")
        log = tk.Text(f, bg="#1a1a1a", fg="#d4d4d4", font=("Consolas", 8),
                      wrap="word", yscrollcommand=sb.set, state="disabled")
        log.pack(fill="both", expand=True)
        sb.config(command=log.yview)
        return log

    def _tool_append(self, log: tk.Text, text: str):
        log.configure(state="normal")
        log.insert("end", text)
        log.see("end")
        log.configure(state="disabled")

    def _tool_start(self, key: str, cmd: list[str], log: tk.Text,
                    btn_start: tk.Button, btn_stop: tk.Button):
        """Startet einen Subprocess und streamt stdout in den Log."""
        if not cmd:
            return  # z. B. Pflichtfeld leer — Hinweis kam schon per Dialog
        if self._tool_procs.get(key):
            return
        self._tool_append(log, f"▶ {' '.join(cmd)}\n\n")
        btn_start.configure(state="disabled")
        btn_stop.configure(state="normal")
        q: queue.Queue[str | None] = queue.Queue()

        def _reader(proc: subprocess.Popen):
            assert proc.stdout
            for line in proc.stdout:
                q.put(line)
            proc.wait()
            q.put(None)  # sentinel

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=ROOT,
            )
        except Exception as exc:
            self._tool_append(log, f"⚠ Fehler: {exc}\n")
            btn_start.configure(state="normal")
            btn_stop.configure(state="disabled")
            return

        self._tool_procs[key] = proc
        threading.Thread(target=_reader, args=(proc,), daemon=True).start()

        def _poll():
            while True:
                try:
                    line = q.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    rc = proc.returncode
                    self._tool_append(log, f"\n✓ Fertig (RC {rc})\n")
                    self._tool_procs[key] = None
                    btn_start.configure(state="normal")
                    btn_stop.configure(state="disabled")
                    return
                self._tool_append(log, line)
            log.after(400, _poll)

        log.after(400, _poll)

    def _tool_stop(self, key: str, log: tk.Text,
                   btn_start: tk.Button, btn_stop: tk.Button):
        proc = self._tool_procs.get(key)
        if proc:
            proc.terminate()
            self._tool_append(log, "\n■ Gestoppt.\n")
            self._tool_procs[key] = None
        btn_start.configure(state="normal")
        btn_stop.configure(state="disabled")

    def _tool_open_url(self, url: str, delay_ms: int = 1500):
        """Öffnet eine lokale Viewer-URL im Browser (nach kurzer Server-Anlaufzeit)."""
        self.after(delay_ms, lambda: webbrowser.open(url))

    # ── Werkzeuge-Tab (Haupt-Tab des Notebooks) ────────────────────────────────

    def _build_tools_tab(self, frame: tk.Frame):
        """Pipeline-Leiste oben + 6 Sub-Reiter darunter."""
        # ── Pipeline-Leiste ─────────────────────────────────────────────────
        bar = tk.Frame(frame, bg=C["panel"])
        bar.pack(fill="x")
        tk.Frame(frame, bg=C["card"], height=1).pack(fill="x")

        # Sub-Notebook (wird zuerst erzeugt, damit Pipeline-Closures greifen)
        inner = ttk.Notebook(frame)
        inner.pack(fill="both", expand=True, padx=6, pady=(4, 8))

        self._build_overview_tab(inner)    # 0  ℹ Übersicht
        self._build_webtrees_tab(inner)    # 1  Webtrees Crawler
        self._build_matricula_tab(inner)   # 2  Matricula Download
        self._build_myheritage_tab(inner)  # 3  MyHeritage Matches
        self._build_import_tab(inner)      # 4  Importe
        self._build_viewer_tab(inner)      # 5  Web-Viewer

        # Pipeline-Leiste befüllen (inner existiert jetzt → Closures OK)
        STAGES = [
            ("⬇",  "Webtrees\nCrawl",           "#3d5f8a", 1,
             "Öffentliche Stammbäume crawlen\n(crawl_webtrees.py)"),
            ("📥", "Import\nin DB",              "#2e6b3e", 4,
             "Heruntergeladene Daten in ancestry_dna.db übernehmen"),
            ("⛪", "Matricula\nKirchenbücher",   "#1a4f8a", 2,
             "Kirchenbücher scannen + mit Claude Vision transkribieren\nVoraussetzung: ANTHROPIC_API_KEY"),
            ("🧬", "MyHeritage\nDNA-Matches",    "#006f6f", 3,
             "Matchliste herunterladen + Shared Matches laden\nVoraussetzung: Chrome mit Remote-Debugging"),
            ("📊", "Auswertung\n& Web-Viewer",   "#5a1a8a", 5,
             "Matricula-Viewer (5000) und Entity-Browser (5001) öffnen"),
        ]
        tk.Label(bar, text="  Workflow: ", bg=C["panel"], fg=C["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(10, 4), pady=8)
        for i, (icon, label, color, idx, tip) in enumerate(STAGES):
            if i > 0:
                tk.Label(bar, text=" →", bg=C["panel"], fg=C["muted"],
                         font=("Segoe UI", 11, "bold")).pack(side="left")
            btn = tk.Button(bar, text=f"{icon}  {label}",
                            bg=color, fg="white",
                            font=("Segoe UI", 8, "bold"),
                            relief="flat", bd=0,
                            padx=10, pady=6, cursor="hand2", justify="center",
                            command=lambda i=idx: inner.select(i))
            btn.pack(side="left", padx=2, pady=6)
            _ToolTip(btn, tip)
        tk.Label(bar, text="  Klick = direkt zum Schritt",
                 bg=C["panel"], fg=C["muted"], font=("Segoe UI", 8)).pack(
            side="left", padx=8)

    # ── Tab: Übersicht ────────────────────────────────────────────────────────

    def _build_overview_tab(self, nb: ttk.Notebook):
        tab = tk.Frame(nb, bg=C["bg"]); nb.add(tab, text="ℹ Übersicht")

        sb = tk.Scrollbar(tab); sb.pack(side="right", fill="y")
        txt = tk.Text(tab, bg=C["bg"], fg=C["text"], font=("Segoe UI", 10),
                      wrap="word", yscrollcommand=sb.set, relief="flat",
                      padx=16, pady=12, spacing1=2, spacing3=4)
        txt.pack(fill="both", expand=True, padx=6, pady=6)
        sb.config(command=txt.yview)

        txt.tag_configure("h",  font=("Segoe UI", 12, "bold"), foreground=C["accent"],
                          spacing1=12, spacing3=4)
        txt.tag_configure("b",  font=("Segoe UI", 10, "bold"), foreground=C["link"])
        txt.tag_configure("dim", foreground=C["muted"])
        txt.tag_configure("code", font=("Consolas", 9), foreground="#c8e6c9")

        def line(text="", tag=None):
            txt.insert("end", text + "\n", tag or ())

        line("Was kann dieses Fenster?", "h")
        line("Hier startest du alle Sammel- und Import-Werkzeuge direkt per Knopf — "
             "ohne Kommandozeile. Jeder Tab erklärt oben, was er tut und was er "
             "voraussetzt. Die Ausgabe der Programme läuft live im schwarzen "
             "Log-Feld mit.")
        line()
        line("Empfohlene Reihenfolge", "h")

        line("A · Stammbaum (Webtrees)", "b")
        line("  1. Webtrees Crawler  – lädt öffentliche Bäume (anverwandte.info) herunter")
        line("  2. Importe › Webtrees → DB  – übernimmt die Personen in die Hauptdatenbank")
        line()
        line("B · Kirchenbücher (Matricula)", "b")
        line("  0. Pfarrei-Katalog  – EINMALIG: baut die Liste aller Pfarreien auf")
        line("  1. Bücherverzeichnis holen  – welche Taufe/Heirat/Tod-Bücher gibt es?")
        line("  2. Seiten scannen (Claude Vision)  – liest die alten Seiten als Text")
        line("       Voraussetzung: Umgebungsvariable ANTHROPIC_API_KEY gesetzt", "dim")
        line("  3. Web-Viewer › Matricula  – Seiten + Transkripte ansehen/korrigieren")
        line()
        line("C · DNA (MyHeritage / GEDmatch)", "b")
        line("  1. MyHeritage › Matchliste herunterladen  (Chrome mit Remote-Debugging)")
        line("  2. Importe › MyHeritage-CSV bzw. GEDmatch-TSV  – in die DB übernehmen")
        line()
        line("D · Auswertung / Pflege", "b")
        line("  • Web-Viewer › Entity-Browser  – Quellen zusammenführen & prüfen")
        line()
        line("Tipp", "h")
        line("Tools, die das Internet brauchen (Crawler, Matricula, MyHeritage), "
             "können je nach Umfang lange laufen. Du kannst sie jederzeit mit „■ Stop“ "
             "abbrechen und später fortsetzen — der Fortschritt wird in den Datenbanken "
             "gespeichert.")
        line()
        line("Ausführliche Doku: WORKFLOW.md im Projektordner.", "dim")

        txt.configure(state="disabled")

    # ── Tab: Webtrees ─────────────────────────────────────────────────────────

    def _build_webtrees_tab(self, nb: ttk.Notebook):
        tab = tk.Frame(nb, bg=C["bg"]); nb.add(tab, text="Webtrees Crawler")

        self._tool_help(tab, [
            "Lädt öffentliche Webtrees-Stammbäume (z. B. stammbaum.anverwandte.info) "
            "Person für Person herunter und speichert sie lokal in webtrees_crawl.db.",
            "Höflicher Crawler: 4–6 Sek. Pause, max. 300 Seiten/Lauf, fortsetzbar.",
            "",
            "--discover    : kompletten Baum aufdecken (neue Personen verfolgen)",
            "--reset-stale : veraltete Seiten erneut abrufen",
            "",
            "Danach: Tab „Importe“ › „Webtrees → DB“, um die Personen zu übernehmen.",
        ])

        opt = tk.Frame(tab, bg=C["panel"]); opt.pack(fill="x", padx=6, pady=6)

        # Profile
        tk.Label(opt, text="Profil:", bg=C["panel"], fg=C["text"]).grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        profiles = ["anverwandte"]
        try:
            data = json.loads(open(PROFILES_JSON, encoding="utf-8").read())
            profiles = list(data.keys())
        except Exception:
            pass
        self._wt_profile = tk.StringVar(value=profiles[0] if profiles else "anverwandte")
        ttk.Combobox(opt, textvariable=self._wt_profile, values=profiles,
                     state="readonly", width=22).grid(row=0, column=1, sticky="w", padx=4)

        # Optionen
        self._wt_discover    = tk.BooleanVar(value=True)
        self._wt_reset_stale = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text="--discover (vollständiger Baum)",
                       variable=self._wt_discover,
                       bg=C["panel"], fg=C["text"], selectcolor=C["bg"]).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=8)
        tk.Checkbutton(opt, text="--reset-stale (veraltete Seiten neu holen)",
                       variable=self._wt_reset_stale,
                       bg=C["panel"], fg=C["text"], selectcolor=C["bg"]).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8)

        # Buttons
        bf = tk.Frame(opt, bg=C["panel"]); bf.grid(row=3, column=0, columnspan=3,
                                                    sticky="w", padx=8, pady=6)
        log = self._tool_log_widget(tab)
        btn_stop  = tk.Button(bf, text="■ Stop",  state="disabled",
                              bg="#7a2020", fg="white", relief="flat", padx=10,
                              command=lambda: self._tool_stop("wt", log, btn_start, btn_stop))
        btn_start = tk.Button(bf, text="▶ Start", bg=C["accent"], fg="white",
                              relief="flat", padx=10,
                              command=lambda: self._tool_start(
                                  "wt", self._wt_cmd(), log, btn_start, btn_stop))
        btn_start.pack(side="left", padx=(0, 4))
        btn_stop.pack(side="left")

        # GEDCOM-Export der gecrawlten Personen
        tk.Frame(opt, bg=C["muted"], height=1).grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=(6, 4), padx=6)
        ef = tk.Frame(opt, bg=C["panel"]); ef.grid(
            row=5, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 6))
        tk.Label(ef, text="Gecrawlten Baum als GEDCOM speichern:",
                 bg=C["panel"], fg=C["text"]).pack(side="left")
        gx = tk.Button(ef, text="💾 GEDCOM exportieren", bg="#5a3d8a", fg="white",
                       relief="flat", padx=10,
                       command=lambda: self._wt_export_gedcom(log))
        gx.pack(side="left", padx=8)
        _ToolTip(gx, "Schreibt die im gewählten Profil gecrawlten Personen als "
                     ".ged-Datei (Personen + Familien). Danach z. B. mit GED Slim "
                     "verkleinern oder in andere Programme laden.")

    def _wt_cmd(self) -> list[str]:
        cmd = [sys.executable, "-u", _TOOLS["webtrees"], "crawl",
               "--profile", self._wt_profile.get()]
        if self._wt_discover.get():
            cmd.append("--discover")
        if self._wt_reset_stale.get():
            cmd.append("--reset-stale")
        return cmd

    def _wt_export_gedcom(self, log: tk.Text):
        profile = self._wt_profile.get()
        out = filedialog.asksaveasfilename(
            title="GEDCOM speichern unter",
            defaultextension=".ged",
            initialfile=f"{profile}.ged",
            filetypes=[("GEDCOM", "*.ged"), ("Alle Dateien", "*.*")])
        if not out:
            return
        cmd = [sys.executable, "-u", _TOOLS["webtrees"], "export-gedcom",
               "--profile", profile, "--out", out]
        # Reusable hidden buttons (export has no own start/stop controls)
        if not hasattr(self, "_wt_exp_btns"):
            self._wt_exp_btns = (tk.Button(self), tk.Button(self))
        self._tool_start("wt_export", cmd, log, *self._wt_exp_btns)

    # ── Tab: Matricula ────────────────────────────────────────────────────────

    def _build_matricula_tab(self, nb: ttk.Notebook):
        tab = tk.Frame(nb, bg=C["bg"]); nb.add(tab, text="Matricula Download")

        self._tool_help(tab, [
            "Kirchenbücher von Matricula-Online (Bistum Osnabrück).  Reihenfolge:",
            "  0. Pfarrei-Katalog  – EINMALIG, baut die Pfarrei-Liste auf (füllt das Auswahlfeld)",
            "  1. Bücherverzeichnis  – welche Taufe/Heirat/Tod-Bücher hat die Pfarrei?",
            "  2. Seiten scannen     – Claude Vision liest die Seiten als Text  (braucht ANTHROPIC_API_KEY)",
            "",
            "Buchtyp/Jahr leer = alles. --retranscribe transkribiert bereits geladene "
            "Bilder neu, ohne erneuten Web-Abruf.",
        ])

        opt = tk.Frame(tab, bg=C["panel"]); opt.pack(fill="x", padx=6, pady=6)

        # Pfarrei
        tk.Label(opt, text="Pfarrei:", bg=C["panel"], fg=C["text"]).grid(
            row=0, column=0, sticky="w", padx=8, pady=4)
        parishes = self._load_parishes()
        self._mat_parish = tk.StringVar(value=parishes[0] if parishes else "")
        cb = ttk.Combobox(opt, textvariable=self._mat_parish,
                          values=parishes, width=38)
        cb.grid(row=0, column=1, columnspan=3, sticky="w", padx=4)

        # Buchtyp
        tk.Label(opt, text="Buchtyp:", bg=C["panel"], fg=C["text"]).grid(
            row=1, column=0, sticky="w", padx=8, pady=4)
        self._mat_booktype = tk.StringVar(value="")
        ttk.Combobox(opt, textvariable=self._mat_booktype, width=14,
                     values=["", "Taufe", "Heirat", "Tod", "Konfirmation"],
                     state="readonly").grid(row=1, column=1, sticky="w", padx=4)

        # Jahr
        tk.Label(opt, text="Jahr von:", bg=C["panel"], fg=C["text"]).grid(
            row=1, column=2, sticky="w", padx=(12, 4))
        self._mat_year_from = tk.StringVar()
        tk.Entry(opt, textvariable=self._mat_year_from, width=6).grid(
            row=1, column=3, sticky="w")
        tk.Label(opt, text="bis:", bg=C["panel"], fg=C["text"]).grid(
            row=1, column=4, sticky="w", padx=(6, 4))
        self._mat_year_to = tk.StringVar()
        tk.Entry(opt, textvariable=self._mat_year_to, width=6).grid(
            row=1, column=5, sticky="w")

        # Optionen
        self._mat_retranscribe = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text="--retranscribe (nur Re-Transkription, kein Web-Abruf)",
                       variable=self._mat_retranscribe,
                       bg=C["panel"], fg=C["text"], selectcolor=C["bg"]).grid(
            row=2, column=0, columnspan=6, sticky="w", padx=8)

        # Buttons — zwei Stufen: erst Bücherverzeichnis, dann Scan
        bf = tk.Frame(opt, bg=C["panel"]); bf.grid(row=3, column=0, columnspan=6,
                                                    sticky="w", padx=8, pady=6)
        log = self._tool_log_widget(tab)

        btn_stop0  = tk.Button(bf, text="■", state="disabled",
                               bg="#7a2020", fg="white", relief="flat", padx=6)
        btn_stop2  = tk.Button(bf, text="■", state="disabled",
                               bg="#7a2020", fg="white", relief="flat", padx=6)
        btn_stop1  = tk.Button(bf, text="■", state="disabled",
                               bg="#7a2020", fg="white", relief="flat", padx=6)
        btn_cat    = tk.Button(bf, text="0. Pfarrei-Katalog (einmalig)",
                               bg=C["card"], fg=C["text"], relief="flat", padx=10)
        btn_books  = tk.Button(bf, text="1. Bücherverzeichnis holen",
                               bg=C["card"], fg=C["text"], relief="flat", padx=10)
        btn_scan   = tk.Button(bf, text="2. Seiten scannen (Claude Vision)",
                               bg=C["accent"], fg="white", relief="flat", padx=10)

        btn_stop0.configure(command=lambda: self._tool_stop(
            "mat_catalog", log, btn_cat, btn_stop0))
        btn_stop1.configure(command=lambda: self._tool_stop(
            "mat_books", log, btn_books, btn_stop1))
        btn_stop2.configure(command=lambda: self._tool_stop(
            "mat_scan", log, btn_scan, btn_stop2))
        btn_cat.configure(command=lambda: self._tool_start(
            "mat_catalog", [sys.executable, "-u", _TOOLS["mat_catalog"]],
            log, btn_cat, btn_stop0))
        btn_books.configure(command=lambda: self._tool_start(
            "mat_books", self._mat_books_cmd(), log, btn_books, btn_stop1))
        btn_scan.configure(command=lambda: self._tool_start(
            "mat_scan", self._mat_scan_cmd(), log, btn_scan, btn_stop2))

        btn_cat.pack(side="left", padx=(0, 2))
        btn_stop0.pack(side="left", padx=(0, 8))
        btn_books.pack(side="left", padx=(0, 2))
        btn_stop1.pack(side="left", padx=(0, 8))
        btn_scan.pack(side="left", padx=(0, 2))
        btn_stop2.pack(side="left")

    def _load_parishes(self) -> list[str]:
        try:
            import sqlite3 as _sq
            db = _sq.connect(PARISH_DB)
            rows = db.execute("SELECT id, name FROM parishes ORDER BY name").fetchall()
            db.close()
            return [f"{name}  [{pid}]" for pid, name in rows]
        except Exception:
            return []

    def _mat_parish_id(self) -> str:
        v = self._mat_parish.get().strip()
        # Extract id from "Name  [id]" format
        import re as _re
        m = _re.search(r'\[([^\]]+)\]$', v)
        return m.group(1) if m else v

    def _mat_books_cmd(self) -> list[str]:
        pid = self._mat_parish_id()
        cmd = [sys.executable, "-u", _TOOLS["mat_books"]]
        if pid:
            cmd += ["--parish", pid]
        return cmd

    def _mat_scan_cmd(self) -> list[str]:
        pid = self._mat_parish_id()
        cmd = [sys.executable, "-u", _TOOLS["mat_scan"], "--parish", pid or ""]
        bt = self._mat_booktype.get()
        if bt:
            cmd += ["--book-type", bt]
        yf = self._mat_year_from.get().strip()
        if yf.isdigit():
            cmd += ["--year-from", yf]
        yt = self._mat_year_to.get().strip()
        if yt.isdigit():
            cmd += ["--year-to", yt]
        if self._mat_retranscribe.get():
            cmd.append("--retranscribe")
        return cmd

    # ── Tab: MyHeritage Matches ───────────────────────────────────────────────

    def _build_myheritage_tab(self, nb: ttk.Notebook):
        tab = tk.Frame(nb, bg=C["bg"]); nb.add(tab, text="MyHeritage Matches")

        self._tool_help(tab, [
            "DNA-Matches von MyHeritage laden.  Zwei Schritte:",
            "  1. Matchliste herunterladen  – holt deine Match-Liste (download_myheritage.py)",
            "  2. Gemeinsame Matches        – pro Match die „shared matches“ (braucht eine CSV-Datei)",
            "",
            "Voraussetzung: angemeldetes Chrome mit Remote-Debugging:",
            '   chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\\chrome-cdp"',
        ])

        opt = tk.Frame(tab, bg=C["panel"]); opt.pack(fill="x", padx=6, pady=6)

        # Schritt 1 – Matchliste
        self._mh_only_new     = tk.BooleanVar(value=False)
        self._mh_no_segments  = tk.BooleanVar(value=False)
        tk.Label(opt, text="Schritt 1 – Matchliste:", bg=C["panel"], fg=C["link"],
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=3,
                 sticky="w", padx=8, pady=(6, 0))
        tk.Checkbutton(opt, text="--only-new (nur neue Matches)",
                       variable=self._mh_only_new, bg=C["panel"], fg=C["text"],
                       selectcolor=C["bg"]).grid(row=1, column=0, sticky="w", padx=8)
        tk.Checkbutton(opt, text="--no-segments (schneller, ohne Segmentdetails)",
                       variable=self._mh_no_segments, bg=C["panel"], fg=C["text"],
                       selectcolor=C["bg"]).grid(row=1, column=1, columnspan=2, sticky="w")
        tk.Label(opt, text="Min. cM:", bg=C["panel"], fg=C["text"]).grid(
            row=2, column=0, sticky="w", padx=8)
        self._mh_min_cm = tk.StringVar(value="8")
        tk.Entry(opt, textvariable=self._mh_min_cm, width=6).grid(
            row=2, column=1, sticky="w")

        # Schritt 2 – Shared matches (CSV)
        tk.Label(opt, text="Schritt 2 – CSV-Datei:", bg=C["panel"], fg=C["link"],
                 font=("Segoe UI", 9, "bold")).grid(row=3, column=0, columnspan=3,
                 sticky="w", padx=8, pady=(8, 0))
        self._mh_csv = tk.StringVar()
        tk.Entry(opt, textvariable=self._mh_csv, width=44).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=8)
        tk.Button(opt, text="…", bg=C["card"], fg=C["text"], relief="flat", padx=8,
                  command=self._mh_pick_csv).grid(row=4, column=2, sticky="w", padx=4)

        bf = tk.Frame(opt, bg=C["panel"]); bf.grid(row=5, column=0, columnspan=4,
                                                   sticky="w", padx=8, pady=8)
        log = self._tool_log_widget(tab)

        btn_stop1 = tk.Button(bf, text="■", state="disabled",
                              bg="#7a2020", fg="white", relief="flat", padx=6)
        btn_stop2 = tk.Button(bf, text="■", state="disabled",
                              bg="#7a2020", fg="white", relief="flat", padx=6)
        btn_dl    = tk.Button(bf, text="1. Matchliste herunterladen",
                              bg=C["accent"], fg="white", relief="flat", padx=10)
        btn_sh    = tk.Button(bf, text="2. Gemeinsame Matches",
                              bg=C["card"], fg=C["text"], relief="flat", padx=10)

        btn_stop1.configure(command=lambda: self._tool_stop(
            "mh_dl", log, btn_dl, btn_stop1))
        btn_stop2.configure(command=lambda: self._tool_stop(
            "mh", log, btn_sh, btn_stop2))
        btn_dl.configure(command=lambda: self._tool_start(
            "mh_dl", self._mh_download_cmd(), log, btn_dl, btn_stop1))
        btn_sh.configure(command=lambda: self._mh_start_shared(log, btn_sh, btn_stop2))

        btn_dl.pack(side="left", padx=(0, 2))
        btn_stop1.pack(side="left", padx=(0, 8))
        btn_sh.pack(side="left", padx=(0, 2))
        btn_stop2.pack(side="left")

    def _mh_pick_csv(self):
        p = filedialog.askopenfilename(
            title="MyHeritage Match-CSV wählen",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")])
        if p:
            self._mh_csv.set(p)

    def _mh_download_cmd(self) -> list[str]:
        cmd = [sys.executable, "-u", _TOOLS["mh_download"]]
        if self._mh_only_new.get():
            cmd.append("--only-new")
        if self._mh_no_segments.get():
            cmd.append("--no-segments")
        cm = self._mh_min_cm.get().strip()
        if cm:
            cmd += ["--min-cm", cm]
        return cmd

    def _mh_start_shared(self, log, btn, btn_stop):
        csv = self._mh_csv.get().strip()
        if not csv or not os.path.exists(csv):
            messagebox.showinfo(
                "CSV fehlt",
                "Für „Gemeinsame Matches“ wird eine Match-CSV benötigt.\n"
                "Bitte oben unter Schritt 2 eine Datei auswählen.")
            return
        self._tool_start(
            "mh", [sys.executable, "-u", _TOOLS["myheritage"], "--csv", csv],
            log, btn, btn_stop)

    # ── Tab: Importe ──────────────────────────────────────────────────────────

    def _build_import_tab(self, nb: ttk.Notebook):
        tab = tk.Frame(nb, bg=C["bg"]); nb.add(tab, text="Importe")

        self._tool_help(tab, [
            "Übernimmt heruntergeladene/gecrawlte Daten in die Hauptdatenbank "
            "(ancestry_dna.db).  Dubletten werden gegen das GEDCOM abgeglichen und "
            "NICHT überschrieben.",
            "",
            "Reihenfolge im Workflow: erst sammeln (andere Tabs), dann hier importieren.",
        ])

        opt = tk.Frame(tab, bg=C["panel"]); opt.pack(fill="x", padx=6, pady=6)
        log = self._tool_log_widget(tab)

        def add_row(r: int, label: str, key: str, build_cmd):
            tk.Label(opt, text=label, bg=C["panel"], fg=C["text"],
                     anchor="w", width=22).grid(row=r, column=0, sticky="w",
                                                padx=8, pady=4)
            btn_stop = tk.Button(opt, text="■", state="disabled", bg="#7a2020",
                                 fg="white", relief="flat", padx=6)
            btn = tk.Button(opt, text="▶ Start", bg=C["accent"], fg="white",
                            relief="flat", padx=10)
            btn_stop.configure(command=lambda: self._tool_stop(key, log, btn, btn_stop))
            btn.configure(command=lambda: self._tool_start(
                key, build_cmd(), log, btn, btn_stop))
            btn.grid(row=r, column=3, sticky="w", padx=(8, 2))
            btn_stop.grid(row=r, column=4, sticky="w")
            return btn

        # Webtrees → DB
        self._imp_wt_nolink = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text="--no-link (kein GEDCOM-Abgleich)",
                       variable=self._imp_wt_nolink, bg=C["panel"], fg=C["text"],
                       selectcolor=C["bg"]).grid(row=0, column=1, columnspan=2, sticky="w")
        add_row(0, "Webtrees → DB", "imp_webtrees", lambda: (
            [sys.executable, "-u", _TOOLS["imp_webtrees"]]
            + (["--no-link"] if self._imp_wt_nolink.get() else [])))

        # MyHeritage CSV
        self._imp_mh_file = tk.StringVar()
        ef = tk.Frame(opt, bg=C["panel"]); ef.grid(row=1, column=1, columnspan=2, sticky="w")
        tk.Entry(ef, textvariable=self._imp_mh_file, width=30).pack(side="left")
        tk.Button(ef, text="…", bg=C["card"], fg=C["text"], relief="flat", padx=6,
                  command=lambda: self._pick_into(self._imp_mh_file, "CSV", "*.csv")
                  ).pack(side="left", padx=4)
        add_row(1, "MyHeritage-CSV → DB", "imp_mh_csv", lambda: (
            [sys.executable, "-u", _TOOLS["imp_mh_csv"]]
            + ([self._imp_mh_file.get().strip()] if self._imp_mh_file.get().strip() else [])))

        # GEDmatch TSV
        self._imp_gm_file = tk.StringVar()
        gf = tk.Frame(opt, bg=C["panel"]); gf.grid(row=2, column=1, columnspan=2, sticky="w")
        tk.Entry(gf, textvariable=self._imp_gm_file, width=30).pack(side="left")
        tk.Button(gf, text="…", bg=C["card"], fg=C["text"], relief="flat", padx=6,
                  command=lambda: self._pick_into(self._imp_gm_file, "TSV/CSV", "*.*")
                  ).pack(side="left", padx=4)
        add_row(2, "GEDmatch-TSV → DB", "imp_gedmatch", lambda: (
            [sys.executable, "-u", _TOOLS["imp_gedmatch"]]
            + ([self._imp_gm_file.get().strip()] if self._imp_gm_file.get().strip() else [])))

        # WikiTree
        self._imp_wk_key = tk.StringVar()
        self._imp_wk_depth = tk.StringVar(value="6")
        wf = tk.Frame(opt, bg=C["panel"]); wf.grid(row=3, column=1, columnspan=2, sticky="w")
        tk.Label(wf, text="ID:", bg=C["panel"], fg=C["text"]).pack(side="left")
        tk.Entry(wf, textvariable=self._imp_wk_key, width=16).pack(side="left", padx=(2, 8))
        tk.Label(wf, text="Tiefe:", bg=C["panel"], fg=C["text"]).pack(side="left")
        tk.Entry(wf, textvariable=self._imp_wk_depth, width=4).pack(side="left", padx=2)
        add_row(3, "WikiTree → DB", "imp_wikitree", self._imp_wikitree_cmd)

        # ── GEDCOM Slim ───────────────────────────────────────────────────
        tk.Frame(opt, bg=C["muted"], height=1).grid(
            row=4, column=0, columnspan=5, sticky="ew", pady=(8, 4), padx=6)
        tk.Label(opt, text="GEDCOM eindampfen",
                 bg=C["panel"], fg=C["text"], anchor="w", width=22,
                 font=("Segoe UI", 9)).grid(row=5, column=0, sticky="w", padx=8)
        tk.Label(opt, text="Öffnet eigene GUI  –  entfernt Quellen-Refs, GPS, URLs",
                 bg=C["panel"], fg=C["muted"], font=("Segoe UI", 8)
                 ).grid(row=5, column=1, columnspan=2, sticky="w")
        slim_btn = tk.Button(opt, text="▶ Öffnen", bg="#5a3d8a", fg="white",
                             relief="flat", padx=10,
                             command=self._launch_ged_slim)
        slim_btn.grid(row=5, column=3, sticky="w", padx=(8, 2))
        _ToolTip(slim_btn,
                 "Öffnet GED Slim als eigenständiges Fenster.\n"
                 "Große GEDCOM-Dateien (300+ MB) auf ~50–80 MB reduzieren.")

    def _launch_ged_slim(self):
        """Startet ged_slim.py als eigenständiges GUI-Fenster."""
        tool = _TOOLS.get("ged_slim", "")
        if not os.path.exists(tool):
            messagebox.showerror("Nicht gefunden", f"ged_slim.py nicht gefunden:\n{tool}")
            return
        try:
            subprocess.Popen([sys.executable, tool], cwd=ROOT,
                             start_new_session=True)
        except Exception as exc:
            messagebox.showerror("Fehler", str(exc))

    def _pick_into(self, var: tk.StringVar, label: str, pattern: str):
        p = filedialog.askopenfilename(
            title=f"{label}-Datei wählen",
            filetypes=[(label, pattern), ("Alle Dateien", "*.*")])
        if p:
            var.set(p)

    def _imp_wikitree_cmd(self) -> list[str]:
        key = self._imp_wk_key.get().strip()
        if not key:
            messagebox.showinfo("WikiTree-ID fehlt",
                                "Bitte eine WikiTree-ID angeben, z. B. Kovermann-123.")
            return []
        cmd = [sys.executable, "-u", _TOOLS["imp_wikitree"], key]
        depth = self._imp_wk_depth.get().strip()
        if depth.isdigit():
            cmd += ["--depth", depth]
        return cmd

    # ── Tab: Web-Viewer ───────────────────────────────────────────────────────

    def _build_viewer_tab(self, nb: ttk.Notebook):
        tab = tk.Frame(nb, bg=C["bg"]); nb.add(tab, text="Web-Viewer")

        self._tool_help(tab, [
            "Startet lokale Web-Oberflächen.  Der Server läuft im Log unten; der "
            "Browser öffnet sich nach ein paar Sekunden automatisch.  Zum Beenden "
            "„■ Stop“ drücken.",
            "",
            "• Matricula-Viewer (Port 5000): gescannte Kirchenbuch-Seiten + Transkripte "
            "ansehen und korrigieren.",
            "• Entity-Browser (Port 5001): alle Quellen (DNA, Baum, Matricula) "
            "zusammenführen und prüfen.",
        ])

        opt = tk.Frame(tab, bg=C["panel"]); opt.pack(fill="x", padx=6, pady=6)
        log = self._tool_log_widget(tab)

        def add_server(r, label, key, tool, url):
            tk.Label(opt, text=label, bg=C["panel"], fg=C["text"], anchor="w",
                     width=30).grid(row=r, column=0, sticky="w", padx=8, pady=6)
            btn_stop = tk.Button(opt, text="■ Stop", state="disabled", bg="#7a2020",
                                 fg="white", relief="flat", padx=8)
            btn = tk.Button(opt, text="▶ Starten & öffnen", bg=C["accent"],
                            fg="white", relief="flat", padx=10)
            btn_stop.configure(command=lambda: self._tool_stop(key, log, btn, btn_stop))

            def _go():
                self._tool_start(key, [sys.executable, "-u", _TOOLS[tool]],
                                 log, btn, btn_stop)
                if self._tool_procs.get(key):
                    self._tool_open_url(url)
            btn.configure(command=_go)
            btn.grid(row=r, column=1, sticky="w", padx=(8, 2))
            btn_stop.grid(row=r, column=2, sticky="w")
            tk.Button(opt, text="↗ Browser", bg=C["card"], fg=C["text"], relief="flat",
                      padx=8, command=lambda: webbrowser.open(url)).grid(
                row=r, column=3, sticky="w", padx=6)

        add_server(0, "Matricula-Viewer  (localhost:5000)", "mat_viewer",
                   "mat_viewer", "http://127.0.0.1:5000")
        add_server(1, "Entity-Browser  (localhost:5001)", "entity_browser",
                   "entity_browser", "http://127.0.0.1:5001")

    # ── Hilfe-Tab ─────────────────────────────────────────────────────────────

    def _build_help_tab(self, frame: tk.Frame):
        """Schnellreferenz & Workflow-Dokumentation."""
        sb = tk.Scrollbar(frame); sb.pack(side="right", fill="y")
        txt = tk.Text(frame, bg=C["bg"], fg=C["text"], font=("Segoe UI", 10),
                      wrap="word", yscrollcommand=sb.set, relief="flat",
                      padx=18, pady=14, spacing1=2, spacing3=4)
        txt.pack(fill="both", expand=True, padx=6, pady=6)
        sb.config(command=txt.yview)

        txt.tag_configure("h",   font=("Segoe UI", 13, "bold"),
                          foreground=C["accent"], spacing1=14, spacing3=4)
        txt.tag_configure("h2",  font=("Segoe UI", 10, "bold"),
                          foreground=C["link"], spacing1=8, spacing3=2)
        txt.tag_configure("dim", foreground=C["muted"])
        txt.tag_configure("mono", font=("Consolas", 9), foreground="#c8e6c9")

        def ln(text="", tag=None):
            txt.insert("end", text + "\n", tag or ())

        ln("Genealogie-Datenviewer — Schnellreferenz", "h")
        ln("Webtrees-Crawler, GEDCOM, Matricula-Kirchenbücher und DNA-Matches "
           "in einer Oberfläche. Die drei Haupt-Tabs strukturieren die Arbeit:")
        ln()
        ln("🌳 Personen & DNA", "h")
        ln("Quellen:", "h2")
        ln("  • Anverwandte (Crawl) — gecrawlte Personen aus stammbaum.anverwandte.info")
        ln("  • GEDCOM / extern     — eigene Personen aus der importierten GEDCOM-Datei")
        ln("Farb-Legende:", "h2")
        ln("  🧬 DNA-Match · blaugrün   = Person hat DNA-Treffer in der DB", "dim")
        ln("  ◆ DNA-Cluster · lila      = einem DNA-Cluster zugeordnet", "dim")
        ln("  ✓ Im GEDCOM · dunkelgrün  = Verknüpfung mit GEDCOM-Person bestätigt", "dim")
        ln("  ~ Fuzzy-Match · braun     = automatischer Treffer (unbestätigt)", "dim")
        ln("  ✝ Kath. · blau / Ev. · grün = konfessionelle Zuordnung aus Matricula", "dim")
        ln("Klick auf eine Person:", "h2")
        ln("  → Minibaum (Mitte): Eltern, Partner, Kinder, Geschwister")
        ln("  → Detailpanel (rechts): Lebensdaten, GEDCOM-Verknüpfung, alle DNA-Matches")
        ln("  → Verknüpfung ✓ bestätigen oder ✗ ablehnen direkt im Detailpanel")
        ln("  → DNA-Matches-Tabelle zeigt alle Treffer mit cM und geschätztem Verwandtschaftsgrad")
        ln()
        ln("🔧 Werkzeuge & Import", "h")
        ln("Pipeline (Klick auf farbige Schaltflächen = direkt zum Schritt):", "h2")
        ln("  1. ⬇ Webtrees Crawl  — öffentliche Bäume laden")
        ln("       python ancestry/tools/crawl_webtrees.py crawl --profile anverwandte --discover", "mono")
        ln("  2. 📥 Import in DB   — Crawl-Ergebnis übernehmen")
        ln("       python ancestry/tools/import_webtrees.py", "mono")
        ln("  3. ⛪ Matricula       — Kirchenbücher scannen  (ANTHROPIC_API_KEY nötig)")
        ln("       0. Pfarrei-Katalog (einmalig)  →  1. Bücherverzeichnis  →  2. Seiten-Scan", "dim")
        ln("  4. 🧬 MyHeritage DNA  — Matchliste + Shared Matches")
        ln("       Voraussetzung: chrome.exe --remote-debugging-port=9222", "dim")
        ln("  5. 📊 Auswertung/Viewer — Matricula-Viewer (5000) + Entity-Browser (5001)")
        ln()
        ln("❓ Hilfe & Workflow", "h")
        ln("Dieser Tab. Die ausführliche Pipeline-Dokumentation mit allen Kommandos "
           "und Voraussetzungen steht in WORKFLOW.md im Projektordner.", "dim")
        ln()
        ln("Tastenkürzel", "h")
        ln("  Enter im Suchfeld  = Suche starten")
        ln("  🔄 (Aktualisieren)  = Datenbank neu einlesen (für laufende Crawls)")
        ln("  ⚡ Bulk             = Auto-/Fuzzy-Matches auf einmal bestätigen/ablehnen")

        txt.configure(state="disabled")

    # ── Bulk-Fenster ──────────────────────────────────────────────────────────

    def _show_bulk_window(self):
        """Zeigt alle offenen Auto- und Fuzzy-Matches zum Bulk-Bestätigen/-Ablehnen."""
        if not self._anc_conn:
            return
        win = tk.Toplevel(self.winfo_toplevel())
        win.title("Bulk-Aktionen – offene Matches")
        win.geometry("860x580")
        win.configure(bg=C["bg"])

        # Score-Schwellwert
        ctrl = tk.Frame(win, bg=C["panel"]); ctrl.pack(fill="x", padx=8, pady=6)
        tk.Label(ctrl, text="Min. Score:", bg=C["panel"], fg=C["text"]).pack(side="left", padx=6)
        score_var = tk.DoubleVar(value=5.0)
        tk.Spinbox(ctrl, from_=0, to=20, increment=0.5, textvariable=score_var,
                   width=6, bg=C["card"], fg=C["text"]).pack(side="left")

        tree = ttk.Treeview(win, columns=("type","wt","ged","score","by","sex"),
                            show="headings", selectmode="extended")
        for col, txt, w in (("type","Art",60),("wt","Anverwandte",180),
                             ("ged","GEDCOM",180),("score","Score",60),
                             ("by","Geb.",55),("sex","Sex",40)):
            tree.heading(col, text=txt); tree.column(col, width=w)
        sb2 = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb2.set)
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)
        sb2.pack(side="left", fill="y", pady=4)

        def _populate():
            tree.delete(*tree.get_children())
            min_s = score_var.get()
            # Auto-Matches
            for wt_id, ged_id in list(self._auto_map.items()):
                sc = self._auto_scores.get(wt_id, 0)
                if sc < min_s:
                    continue
                g = self._ged_cache.get(ged_id, {})
                wt_name = ""
                if self._conn:
                    try:
                        r = self._conn.execute(
                            "SELECT name, birth_year FROM wt_persons WHERE id=?",
                            (wt_id,)).fetchone()
                        if r:
                            wt_name = _sanitize(r["name"] or "")
                    except Exception:
                        pass
                g_name = _sanitize(
                    f"{g.get('given_name','')} {g.get('surname','')}".strip())
                tree.insert("", "end", iid=f"auto_{wt_id}",
                            values=("Auto", wt_name, g_name, f"{sc:.1f}",
                                    g.get("birth_year",""), g.get("sex","")),
                            tags=("auto",))
            # Fuzzy-Matches
            for wt_id, ged_id in list(self._fuzzy_map.items()):
                g = self._ged_cache.get(ged_id, {})
                wt_name = ""
                if self._conn:
                    try:
                        r = self._conn.execute(
                            "SELECT name FROM wt_persons WHERE id=?",
                            (wt_id,)).fetchone()
                        if r:
                            wt_name = _sanitize(r["name"] or "")
                    except Exception:
                        pass
                g_name = _sanitize(
                    f"{g.get('given_name','')} {g.get('surname','')}".strip())
                tree.insert("", "end", iid=f"fuzzy_{wt_id}",
                            values=("Fuzzy", wt_name, g_name, "—",
                                    g.get("birth_year",""), g.get("sex","")),
                            tags=("fuzzy",))
            tree.tag_configure("auto",  foreground=C["dna"])
            tree.tag_configure("fuzzy", foreground=C["fuzzy"])

        _populate()
        tk.Button(ctrl, text="🔄 Aktualisieren", command=_populate,
                  bg=C["card"], fg=C["text"], relief="flat").pack(side="left", padx=8)

        def _confirm_sel():
            for iid in tree.selection():
                parts = iid.split("_", 1)
                if len(parts) != 2:
                    continue
                kind, wt_id = parts
                ged_id = (self._auto_map if kind == "auto" else self._fuzzy_map).get(wt_id)
                if ged_id:
                    prev = kind
                    self._push_undo("confirm", wt_id, ged_id, prev)
                    self._confirm_match(wt_id, ged_id)
            _populate()

        def _reject_sel():
            for iid in tree.selection():
                parts = iid.split("_", 1)
                if len(parts) != 2:
                    continue
                kind, wt_id = parts
                ged_id = (self._auto_map if kind == "auto" else self._fuzzy_map).get(wt_id)
                if ged_id:
                    prev = kind
                    self._push_undo("reject", wt_id, ged_id, prev)
                    self._reject_match(wt_id, ged_id)
            _populate()

        def _confirm_all():
            min_s = score_var.get()
            for wt_id, ged_id in list(self._auto_map.items()):
                if self._auto_scores.get(wt_id, 0) >= min_s:
                    self._push_undo("confirm", wt_id, ged_id, "auto")
                    self._confirm_match(wt_id, ged_id)
            _populate()

        btns = tk.Frame(win, bg=C["bg"]); btns.pack(fill="x", padx=8, pady=6)
        tk.Button(btns, text="✓ Auswahl bestätigen", bg=C["mapped"], fg="white",
                  relief="flat", padx=8, command=_confirm_sel).pack(side="left", padx=4)
        tk.Button(btns, text="✗ Auswahl ablehnen", bg=C["card"], fg=C["muted"],
                  relief="flat", padx=8, command=_reject_sel).pack(side="left", padx=4)
        tk.Button(btns, text=f"✓✓ Alle Auto ≥ Score bestätigen", bg=C["accent"], fg="white",
                  relief="flat", padx=8, command=_confirm_all).pack(side="left", padx=4)

    # ────────────────────────────────────────────────────────────────────────
    def _rel_for_wt(self, wt_id: str) -> str:
        """Verwandtschaftsgrad einer Anverwandten-Person via GEDCOM-Mapping."""
        ged_id, _ = self._mapping_for(str(wt_id))
        if ged_id:
            sosa, sex = self._sosa_map.get(str(ged_id), (0, ""))
            return _sosa_to_rel(sosa, sex)
        return ""

    def _parish_info(self, birth_place: str) -> dict | None:
        """Pfarrei-Info für einen Geburtsort (gecacht)."""
        if birth_place not in self._parish_cache:
            self._parish_cache[birth_place] = _parish_for(birth_place)
        return self._parish_cache[birth_place]

    def _confession_of(self, birth_place: str) -> str:
        """'kath' | 'ev' | '' für einen Geburtsort."""
        info = self._parish_info(birth_place or "")
        return (info or {}).get("confession", "")

    def _mapping_for(self, wt_id: str) -> tuple[str | None, bool]:
        """Gibt (ged_id, is_fuzzy) zurück oder (None, False) wenn ungemappt."""
        wt_id = str(wt_id)
        if wt_id in self._gedcom_map:
            return self._gedcom_map[wt_id], False
        if wt_id in self._fuzzy_map:
            return self._fuzzy_map[wt_id], True
        if wt_id in self._auto_map:
            return self._auto_map[wt_id], True
        return None, False

    def _cluster_for_wt(self, wt_id: str) -> int | None:
        ged_id, _ = self._mapping_for(wt_id)
        if ged_id:
            return self._cluster_map.get(ged_id)
        return None

    # ── UI-Aufbau ───────────────────────────────────────────────────────────
    def _build(self):
        self._tool_procs: dict[str, subprocess.Popen | None] = {}

        # Statuszeile ganz unten — muss VOR dem Notebook gepackt werden
        self._status = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status, bg=C["bg"], fg=C["muted"],
                 anchor="w").pack(fill="x", side="bottom")

        # ── Haupt-Notebook ─────────────────────────────────────────────────
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True)

        # ── Tab 1: Personen & DNA ───────────────────────────────────────────
        pt = tk.Frame(self._nb, bg=C["bg"])
        self._nb.add(pt, text="  🌳  Personen & DNA  ")

        # Toolbar (Parent: pt)
        top = tk.Frame(pt, bg=C["panel"]); top.pack(fill="x")
        tk.Label(top, text="Quelle:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4), pady=6)
        self._src_var = tk.StringVar(value="Anverwandte (Crawl)")
        src = ttk.Combobox(top, textvariable=self._src_var, width=22,
                           state="readonly",
                           values=["Anverwandte (Crawl)", "GEDCOM / extern"])
        src.pack(side="left", pady=6)
        src.bind("<<ComboboxSelected>>", self._on_source_change)
        _ToolTip(src, "Anverwandte: gecrawlte Personen aus stammbaum.anverwandte.info\n"
                      "GEDCOM / extern: eigene Personen aus der importierten GEDCOM-Datei")

        tk.Label(top, text="Filter:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(12, 4))
        self._filter_var = tk.StringVar(value=_FILTER_ALL)
        flt = ttk.Combobox(top, textvariable=self._filter_var, width=16,
                           state="readonly",
                           values=[_FILTER_ALL, _FILTER_DNA, _FILTER_MAPPED,
                                   _FILTER_FUZZY, _FILTER_UNMAP])
        flt.pack(side="left", pady=6)
        flt.bind("<<ComboboxSelected>>", lambda _: self._do_search())
        _ToolTip(flt, "🧬 DNA-Match    = Person ist mit einem DNA-Treffer verknüpft\n"
                      "✓ Im GEDCOM     = Verknüpfung mit eigener GEDCOM-Person bestätigt\n"
                      "~ Fuzzy-Match   = automatischer Treffer (unbestätigt)\n"
                      "○ Nicht im GEDCOM = noch keine Verknüpfung")

        tk.Label(top, text="Konfession:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4))
        self._conf_var = tk.StringVar(value=_CONF_ALL)
        conf = ttk.Combobox(top, textvariable=self._conf_var, width=13,
                            state="readonly",
                            values=[_CONF_ALL, _CONF_KATH, _CONF_EV, _CONF_UNK])
        conf.pack(side="left", pady=6)
        conf.bind("<<ComboboxSelected>>", lambda _: self._do_search())
        _ToolTip(conf, "Konfessionelle Zuordnung aus dem Matricula-Kirchspiel-Lookup")

        tk.Label(top, text="DNA-Quelle:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4))
        self._dna_src_var = tk.StringVar(value="Alle")
        self._dna_src_box = ttk.Combobox(top, textvariable=self._dna_src_var, width=13,
                                          state="readonly", values=["Alle"])
        self._dna_src_box.pack(side="left", pady=6)
        self._dna_src_box.bind("<<ComboboxSelected>>", lambda _: self._do_search())
        _ToolTip(self._dna_src_box, "Nur DNA-Matches einer bestimmten Plattform anzeigen\n"
                                    "(MyHeritage, GEDmatch, Ancestry …)")

        tk.Label(top, text="Suche:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4))
        self._search_var = tk.StringVar()
        e = tk.Entry(top, textvariable=self._search_var, width=22)
        e.pack(side="left", pady=6)
        e.bind("<Return>", lambda _: self._do_search())

        b_search = tk.Button(top, text="🔍", command=self._do_search)
        b_search.pack(side="left", padx=2)
        _ToolTip(b_search, "Suche starten (auch Enter im Suchfeld)")

        b_refresh = tk.Button(top, text="🔄", command=self._reopen,
                              bg=C["panel"], fg=C["text"], relief="flat")
        b_refresh.pack(side="left", padx=4)
        _ToolTip(b_refresh, "Datenbank neu einlesen — nützlich wenn der Crawler\n"
                             "gerade im Hintergrund läuft und neue Personen ergänzt")

        b_stats = tk.Button(top, text="📊 Statistik", command=self._show_stats_window,
                            bg=C["panel"], fg=C["text"], relief="flat")
        b_stats.pack(side="left", padx=2)
        _ToolTip(b_stats, "Statistiken: Personen, GEDCOM-Abdeckung, DNA-Matches")

        b_bulk = tk.Button(top, text="⚡ Bulk", command=self._show_bulk_window,
                           bg=C["panel"], fg=C["dna"], relief="flat")
        b_bulk.pack(side="left", padx=2)
        _ToolTip(b_bulk, "Bulk-Aktionen: Auto-/Fuzzy-Matches auf einmal\nbestätigen oder ablehnen")

        self._undo_btn = tk.Button(top, text="↩ Rückgängig", command=self._undo_last,
                                   bg=C["panel"], fg=C["muted"], relief="flat",
                                   state="disabled")
        self._undo_btn.pack(side="left", padx=4)
        _ToolTip(self._undo_btn, "Letzte Verknüpfungs-Aktion rückgängig machen")

        self._stats = tk.StringVar(value="")
        tk.Label(top, textvariable=self._stats, bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 9, "bold")).pack(side="right", padx=12)

        # Farb-Legende (Parent: pt)
        leg = tk.Frame(pt, bg=C["bg"]); leg.pack(fill="x")
        for color, label in (
            (C["dna"],     "🧬 DNA-Match"),
            (C["cluster"], "◆ DNA-Cluster"),
            (C["mapped"],  "✓ Im GEDCOM"),
            (C["fuzzy"],   "~ Fuzzy-Match"),
            (C["card"],    "○ Ungemappt"),
            (C["kath"],    "✝ Katholisch"),
            (C["ev"],      "✝ Evangelisch"),
        ):
            tk.Label(leg, text="  ■ ", bg=C["bg"], fg=color,
                     font=("Segoe UI", 8)).pack(side="left")
            tk.Label(leg, text=label, bg=C["bg"], fg=C["muted"],
                     font=("Segoe UI", 8)).pack(side="left")

        # Hauptbereich: links Liste, Mitte Baum, rechts Detail (Parent: pt)
        body = tk.Frame(pt, bg=C["bg"]); body.pack(fill="both", expand=True)

        # Links: Suchergebnisse
        left = tk.Frame(body, bg=C["panel"], width=440); left.pack(
            side="left", fill="y"); left.pack_propagate(False)
        tk.Label(left, text="Ergebnisse", bg=C["panel"], fg=C["muted"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        cols = ("name", "years", "rel", "place", "status")
        self._list = ttk.Treeview(left, columns=cols, show="headings",
                                  selectmode="browse")
        self._list.heading("name",   text="Name")
        self._list.heading("years",  text="Jahre")
        self._list.heading("rel",    text="Verwandtschaft")
        self._list.heading("place",  text="Ort")
        self._list.heading("status", text="GED")
        self._list.column("name",   width=180, stretch=True)
        self._list.column("years",  width=65,  anchor="center", stretch=False)
        self._list.column("rel",    width=130, anchor="w", stretch=True)
        self._list.column("place",  width=110, stretch=True)
        self._list.column("status", width=56,  anchor="center", stretch=False)
        self._list.pack(fill="both", expand=True, padx=6, pady=6)
        self._list.bind("<<TreeviewSelect>>", self._on_list_select)
        self._list.tag_configure("mapped",  foreground=C["mapped"])
        self._list.tag_configure("fuzzy",   foreground=C["fuzzy"])
        self._list.tag_configure("cluster", foreground=C["cluster"])
        self._list.tag_configure("dna",     foreground=C["dna"])
        self._list.tag_configure("kath",    foreground=C["kath"])
        self._list.tag_configure("ev",      foreground=C["ev"])
        self._list.tag_configure("sub",     foreground=C["muted"])

        # Mitte: navigierbarer Mini-Baum
        mid = tk.Frame(body, bg=C["bg"]); mid.pack(side="left", fill="both", expand=True)
        nav = tk.Frame(mid, bg=C["bg"]); nav.pack(fill="x")
        b_back = tk.Button(nav, text="◀ Zurück", command=self._go_back)
        b_back.pack(side="left", padx=8, pady=6)
        _ToolTip(b_back, "Zur vorher angezeigten Person zurück")
        _tc_frame = tk.Frame(mid, bg=C["bg"])
        _tc_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self._tree_canvas = tk.Canvas(_tc_frame, bg=C["bg"], highlightthickness=0)
        _tc_vsb = ttk.Scrollbar(_tc_frame, orient="vertical",
                                command=self._tree_canvas.yview)
        _tc_hsb = ttk.Scrollbar(_tc_frame, orient="horizontal",
                                command=self._tree_canvas.xview)
        self._tree_canvas.configure(xscrollcommand=_tc_hsb.set,
                                    yscrollcommand=_tc_vsb.set)
        _tc_vsb.pack(side="right", fill="y")
        _tc_hsb.pack(side="bottom", fill="x")
        self._tree_canvas.pack(fill="both", expand=True)
        self._tree_canvas.bind("<MouseWheel>",
            lambda e: self._tree_canvas.yview_scroll(-1*(e.delta//120), "units"))
        self._tree_canvas.bind("<Shift-MouseWheel>",
            lambda e: self._tree_canvas.xview_scroll(-1*(e.delta//120), "units"))

        # Rechts: Detailpanel
        right = tk.Frame(body, bg=C["panel"], width=380); right.pack(
            side="right", fill="y"); right.pack_propagate(False)
        self._detail_canvas = tk.Canvas(right, bg=C["panel"],
                                        highlightthickness=0, width=380)
        dsb = ttk.Scrollbar(right, orient="vertical",
                            command=self._detail_canvas.yview)
        self._detail = tk.Frame(self._detail_canvas, bg=C["panel"])
        self._detail.bind("<Configure>", lambda _: self._detail_canvas.configure(
            scrollregion=self._detail_canvas.bbox("all")))
        self._detail_canvas.create_window((0, 0), window=self._detail, anchor="nw")
        self._detail_canvas.configure(yscrollcommand=dsb.set)
        self._detail_canvas.pack(side="left", fill="both", expand=True)
        dsb.pack(side="right", fill="y")

        # ── Tab 2: Werkzeuge & Import ───────────────────────────────────────
        self._tools_tab = tk.Frame(self._nb, bg=C["bg"])
        self._nb.add(self._tools_tab, text="  🔧  Werkzeuge & Import  ")
        self._build_tools_tab(self._tools_tab)

        # ── Tab 3: Hilfe & Workflow ─────────────────────────────────────────
        ht = tk.Frame(self._nb, bg=C["bg"])
        self._nb.add(ht, text="  ❓  Hilfe & Workflow  ")
        self._build_help_tab(ht)

    # ── Datenquellen-Wechsel ─────────────────────────────────────────────────
    def _on_source_change(self, _=None):
        # Aktuellen Filter-Zustand speichern
        self._filter_state[self._source] = (
            self._filter_var.get(),
            self._conf_var.get(),
            self._dna_src_var.get(),
            self._search_var.get(),
        )
        self._source = ("anverwandte" if self._src_var.get().startswith("Anver")
                        else "gedcom")
        self._clear_rel_target(render=False)
        self._current_id = None
        # Gespeicherten Zustand wiederherstellen (falls vorhanden)
        saved = self._filter_state.get(self._source)
        if saved:
            self._filter_var.set(saved[0])
            self._conf_var.set(saved[1])
            self._dna_src_var.set(saved[2])
            self._search_var.set(saved[3])
        self._reopen()

    # ── Statistik (Live) ─────────────────────────────────────────────────────
    def _refresh_stats(self):
        if not self._conn:
            self._stats.set("—")
            return
        try:
            if self._source == "anverwandte":
                _r = self._conn.execute("SELECT COUNT(*) FROM wt_persons").fetchone()
                n = _r[0] if _r else 0
                openf = 0
                try:
                    _rf = self._conn.execute(
                        "SELECT COUNT(*) FROM wt_frontier WHERE done=0").fetchone()
                    openf = _rf[0] if _rf else 0
                except Exception:
                    pass
                mapped = len(self._gedcom_map)
                fuzzy  = len(self._fuzzy_map)
                dna_ct = len(self._dna_map)
                self._stats.set(
                    f"{n:,} Personen · {openf:,} offen · "
                    f"{mapped:,} gemappt · {fuzzy:,} fuzzy · "
                    f"🧬{dna_ct:,} DNA"
                    .replace(",", "."))
            else:
                _rg = self._conn.execute("SELECT COUNT(*) FROM gedcom_persons").fetchone()
                n = _rg[0] if _rg else 0
                self._stats.set(f"{n:,} Personen".replace(",", "."))
        except Exception as e:
            self._stats.set(f"⚠ {e}")

    # ── Suche ─────────────────────────────────────────────────────────────────
    def _do_search(self):
        if not self._conn:
            self._list.delete(*self._list.get_children())
            self._sub_ids.clear()
            return

        # Snapshot all UI state and shared dicts on the main thread
        q           = self._search_var.get().strip()
        flt         = self._filter_var.get()
        conf_flt    = self._conf_var.get()
        dna_src_sel = self._dna_src_var.get()
        source      = self._source
        gedcom_map  = dict(self._gedcom_map)
        fuzzy_map   = dict(self._fuzzy_map)
        auto_map    = dict(self._auto_map)
        auto_scores = dict(self._auto_scores)
        cluster_map = dict(self._cluster_map)
        dna_map     = dict(self._dna_map)
        ged_cache   = dict(self._ged_cache)

        # Generation counter — stale results from a previous search are discarded
        if not hasattr(self, "_search_gen"):
            self._search_gen = 0
        self._search_gen += 1
        gen = self._search_gen

        def _mapping_for_snap(wt_id: str):
            if wt_id in gedcom_map:
                return gedcom_map[wt_id], False
            if wt_id in fuzzy_map:
                return fuzzy_map[wt_id], True
            if wt_id in auto_map:
                return auto_map[wt_id], True
            return None, False

        # ── Background: SQL + per-row processing ─────────────────────────────
        def _fetch():
            rows_out = []   # list of (iid, parent, tags, values) for main rows
            subs_out = []   # list of (iid, parent_iid, tags, values) for sub-rows
            seen_subs: set = set()

            try:
                if source == "anverwandte":
                    if q:
                        rows = self._conn.execute(
                            "SELECT id, name, given_name, surname, birth_year, "
                            "death_year, birth_place FROM wt_persons "
                            "WHERE name LIKE ? OR surname LIKE ? OR given_name LIKE ? "
                            "ORDER BY surname, given_name LIMIT 500",
                            (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
                    else:
                        rows = self._conn.execute(
                            "SELECT id, name, given_name, surname, birth_year, "
                            "death_year, birth_place FROM wt_persons "
                            "ORDER BY surname, given_name LIMIT 500").fetchall()

                    for r in rows:
                        wt_id  = str(r["id"])
                        ged_id, is_fuzzy = _mapping_for_snap(wt_id)
                        cluster    = cluster_map.get(ged_id) if ged_id else None
                        confession = self._confession_of(r["birth_place"] or "")

                        if flt == _FILTER_MAPPED and (not ged_id or is_fuzzy):
                            continue
                        if flt == _FILTER_FUZZY and not is_fuzzy:
                            continue
                        if flt == _FILTER_UNMAP and ged_id:
                            continue
                        if conf_flt == _CONF_KATH and confession != "kath":
                            continue
                        if conf_flt == _CONF_EV and confession != "ev":
                            continue
                        if conf_flt == _CONF_UNK and confession:
                            continue

                        dna_info = dna_map.get(ged_id) if ged_id else None
                        has_dna  = dna_info is not None
                        dna_cm   = dna_info[0] if dna_info else None
                        dna_src  = dna_info[2] if dna_info else set()

                        if flt == _FILTER_DNA and not has_dna:
                            continue
                        if dna_src_sel and dna_src_sel != "Alle" and has_dna:
                            if dna_src_sel not in dna_src:
                                continue

                        raw_label = r["name"] or f"{r['given_name']} {r['surname']}".strip()
                        label = _sanitize(raw_label)

                        if has_dna:
                            cm_str = f"{dna_cm:.0f}" if dna_cm is not None else "?"
                            pfx = "✓" if (ged_id and not is_fuzzy) else ("~" if is_fuzzy else "")
                            ged_badge = f"{pfx}🧬{cm_str}"
                        else:
                            ged_badge = ""
                            if ged_id and not is_fuzzy:
                                ged_badge = "✓"
                            elif is_fuzzy:
                                ged_badge = "~"
                            if cluster is not None:
                                ged_badge += f"C{cluster}"
                        conf_badge = ("✝K" if confession == "kath" else
                                      "✝E" if confession == "ev" else "")
                        if conf_badge:
                            ged_badge = f"{conf_badge} {ged_badge}".strip()

                        rel = self._rel_for_wt(wt_id)
                        tag = ("cluster" if cluster is not None else
                               "dna"     if has_dna else
                               "mapped"  if ged_id and not is_fuzzy else
                               "fuzzy"   if is_fuzzy else
                               "kath"    if confession == "kath" else
                               "ev"      if confession == "ev" else "")
                        rows_out.append((wt_id, "", (tag,) if tag else (), (
                            label,
                            _years(r["birth_year"], r["death_year"]),
                            rel,
                            (r["birth_place"] or "")[:18],
                            ged_badge,
                        )))

                        if ged_id and ged_id in ged_cache:
                            g = ged_cache[ged_id]
                            g_gn = _sanitize(g.get("given_name") or "")
                            g_sn = _sanitize(g.get("surname") or "")
                            g_name = f"{g_gn} {g_sn}".strip() or ged_id
                            g_rel  = _sosa_to_rel(g.get("sosa_number") or 0, g.get("sex") or "")
                            score  = auto_scores.get(wt_id, 0)
                            g_dna  = dna_map.get(ged_id)
                            if g_dna:
                                sub_badge = f"🧬{g_dna[0]:.0f}" if g_dna[0] is not None else "🧬?"
                            elif wt_id in gedcom_map:
                                sub_badge = "✓"
                            else:
                                sub_badge = f"~{score:.0f}"
                            sub_iid = f"{ged_id}_{wt_id}"
                            if sub_iid not in seen_subs:
                                seen_subs.add(sub_iid)
                                subs_out.append((sub_iid, wt_id, ("sub",), (
                                    "  └ " + g_name,
                                    _years(str(g.get("birth_year") or ""),
                                           str(g.get("death_year") or "")),
                                    g_rel,
                                    (g.get("birth_place") or "")[:18],
                                    sub_badge,
                                )))

                else:
                    # GEDCOM source
                    if q:
                        rows = self._conn.execute(
                            "SELECT ged_id, given_name, surname, birth_year, death_year, "
                            "birth_place, sosa_number, sex FROM gedcom_persons "
                            "WHERE surname LIKE ? OR given_name LIKE ? "
                            "ORDER BY surname, given_name LIMIT 500",
                            (f"%{q}%", f"%{q}%")).fetchall()
                    else:
                        rows = self._conn.execute(
                            "SELECT ged_id, given_name, surname, birth_year, death_year, "
                            "birth_place, sosa_number, sex FROM gedcom_persons "
                            "ORDER BY surname, given_name LIMIT 500").fetchall()
                    for r in rows:
                        gn = _sanitize(r["given_name"] or "")
                        sn = _sanitize(r["surname"] or "")
                        label    = f"{gn} {sn}".strip() or _sanitize(r["ged_id"])
                        ged_id_g = str(r["ged_id"])
                        cluster  = cluster_map.get(ged_id_g)
                        dna_info = dna_map.get(ged_id_g)
                        has_dna  = dna_info is not None
                        dna_cm   = dna_info[0] if dna_info else None
                        sosa = r["sosa_number"] or 0
                        rel  = _sosa_to_rel(sosa, r["sex"] or "")
                        if flt == _FILTER_DNA and not has_dna:
                            continue
                        if has_dna:
                            badge = f"🧬{dna_cm:.0f}" if dna_cm is not None else "🧬?"
                        elif cluster is not None:
                            badge = f"C{cluster}"
                        else:
                            badge = ""
                        tag = ("cluster" if cluster is not None else
                               "dna"     if has_dna else "")
                        rows_out.append((ged_id_g, "", (tag,) if tag else (), (
                            label,
                            _years(str(r["birth_year"] or ""), str(r["death_year"] or "")),
                            rel,
                            (r["birth_place"] or "")[:18],
                            badge,
                        )))

            except Exception as e:
                self.after(0, lambda e=e: self._status.set(f"⚠ Suche: {e}"))
                return

            self.after(0, lambda: _apply(rows_out, subs_out, seen_subs))

        # ── Main thread: insert prepared rows into Treeview ───────────────────
        def _apply(rows_out, subs_out, seen_subs):
            if self._search_gen != gen or not self.winfo_exists():
                return
            self._list.delete(*self._list.get_children())
            self._sub_ids.clear()
            for iid, parent, tags, values in rows_out:
                try:
                    self._list.insert(parent, "end", iid=iid, values=values,
                                      tags=tags)
                except Exception:
                    pass
            for iid, parent_iid, tags, values in subs_out:
                try:
                    self._list.insert(parent_iid, "end", iid=iid, values=values,
                                      tags=tags)
                    self._sub_ids.add(iid)
                except Exception:
                    pass

        import threading
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_list_select(self, _=None):
        sel = self._list.selection()
        if not sel:
            return
        pid = sel[0]
        if pid in self._sub_ids:
            ged_id = pid.rsplit("_", 1)[0]
            self._render_gedcom_sub_detail(ged_id)
        else:
            self._navigate(pid)

    # ── Personen laden ────────────────────────────────────────────────────────
    def _person(self, pid: str) -> dict | None:
        return self._person_for(self._source, pid)

    def _person_for(self, source: str, pid: str) -> dict | None:
        """Fetch a person dict from the correct table for `source`."""
        if not pid:
            return None
        try:
            if source == "anverwandte":
                conn = self._conn
                if not conn:
                    return None
                r = conn.execute("SELECT * FROM wt_persons WHERE id=?", (pid,)).fetchone()
            else:
                conn = self._anc_conn
                if not conn:
                    return None
                r = conn.execute(
                    "SELECT * FROM gedcom_persons WHERE ged_id=?", (pid,)).fetchone()
            return dict(r) if r else None
        except Exception:
            return None

    def _label_for(self, pid: str) -> str:
        """Anzeigename für eine ID (aus Cache/DB), Fallback = ID."""
        if pid in self._name_cache:
            return self._name_cache[pid]
        p = self._person(pid)
        if p:
            if self._source == "anverwandte":
                lbl = _sanitize(p.get("name") or
                                f"{p.get('given_name','')} {p.get('surname','')}".strip())
                yrs = _years(p.get("birth_year"), p.get("death_year"))
            else:
                lbl = _sanitize(
                    f"{p.get('given_name','')} {p.get('surname','')}".strip())
                yrs = _years(str(p.get("birth_year") or ""), str(p.get("death_year") or ""))
            lbl = (lbl + (f"\n{yrs}" if yrs else "")) or pid
        else:
            lbl = f"{pid}\n(noch nicht geladen)"
        self._name_cache[pid] = lbl
        return lbl

    # ── Navigation ────────────────────────────────────────────────────────────
    def _navigate_ged(self, ged_id: str):
        """Zeigt eine GEDCOM-Person im Detailpanel — ohne Quell-Wechsel."""
        self._render_gedcom_sub_detail(ged_id)

    def _navigate(self, pid: str, push=True):
        if push and self._current_id and self._current_id != pid:
            self._history.append(self._current_id)
        self._current_id = pid
        self._render_tree(pid)
        self._render_detail(pid)

    def _go_back(self):
        if self._history:
            self._navigate(self._history.pop(), push=False)

    # ── Personen-Batch-Laden ──────────────────────────────────────────────────
    def _batch_fetch_persons(self, source: str, pids: list) -> dict:
        """Single-query load for a list of person IDs. Returns {id: dict}."""
        pids = [str(p) for p in pids if p]
        if not pids:
            return {}
        ph = ",".join("?" * len(pids))
        try:
            if source == "anverwandte":
                if not self._conn:
                    return {}
                rows = self._conn.execute(
                    f"SELECT * FROM wt_persons WHERE id IN ({ph})", pids).fetchall()
                return {str(r["id"]): dict(r) for r in rows}
            else:
                if not self._anc_conn:
                    return {}
                rows = self._anc_conn.execute(
                    f"SELECT * FROM gedcom_persons WHERE ged_id IN ({ph})", pids).fetchall()
                return {str(r["ged_id"]): dict(r) for r in rows}
        except Exception:
            return {}

    # ── Canvas-Stammbaum ──────────────────────────────────────────────────────
    def _render_tree(self, pid: str):
        tc = self._tree_canvas
        tc.delete("all")
        tc.update_idletasks()
        cw = max(tc.winfo_width(), 900)

        source = self._source
        p = self._person_for(source, pid)
        if not p:
            tc.create_text(cw // 2, 60, text="Person nicht gefunden.",
                           fill=C["muted"], font=("Segoe UI", 10))
            tc.configure(scrollregion=(0, 0, cw, 120))
            return

        parents  = _loads(p.get("parents_json"))
        spouses  = _loads(p.get("spouses_json"))
        children = _loads(p.get("children_json"))
        siblings = _loads(p.get("siblings_json"))

        # SOSA fallback for GEDCOM persons without stored family JSON
        if not parents and source == "gedcom":
            sosa, _ = self._sosa_map.get(pid, (0, ""))
            if sosa:
                f_id = self._sosa_rev.get(sosa * 2)
                m_id = self._sosa_rev.get(sosa * 2 + 1)
                parents = [g for g in [f_id, m_id] if g]
                for gs in [sosa*4, sosa*4+1, sosa*4+2, sosa*4+3]:
                    pass  # grandparents fetched below via parents
                if sosa > 1:
                    ch_sosa = sosa // 2
                    ch_id = self._sosa_rev.get(ch_sosa)
                    children = [ch_id] if ch_id else []
                    co_sosa = ch_sosa * 2 + (1 if sosa % 2 == 0 else 0)
                    co_id = self._sosa_rev.get(co_sosa)
                    spouses = [co_id] if co_id and co_id != pid else []
                else:
                    children, spouses = [], []

        # Collect grandparents via parents
        grandparents: list[str] = []
        par_gp_map: dict[str, list[str]] = {}  # parent_id -> [grandparent_ids]
        for par in parents:
            par_data = self._person_for(source, par)
            gps: list[str] = []
            if par_data:
                gps = _loads(par_data.get("parents_json"))
                if not gps and source == "gedcom":
                    par_sosa, _ = self._sosa_map.get(par, (0, ""))
                    if par_sosa:
                        for gs in [par_sosa*2, par_sosa*2+1]:
                            gp = self._sosa_rev.get(gs)
                            if gp:
                                gps.append(gp)
            par_gp_map[par] = gps
            grandparents.extend(gps)

        # Visible subsets
        sib_left  = [s for s in siblings[:3] if s != pid][:3]
        sib_right = [s for s in siblings[3:6] if s != pid][:3]
        chi_show  = children[:8]
        gp_show   = list(dict.fromkeys(grandparents))[:8]
        sp_show   = [s for s in spouses[:2] if s]

        # Batch-fetch all persons in one query each
        all_ids = list(dict.fromkeys(
            [pid] + parents + sp_show + chi_show +
            sib_left + sib_right + gp_show
        ))
        persons = self._batch_fetch_persons(source, all_ids)

        # ── Layout constants ───────────────────────────────────────────────
        CW, CH = 120, 82   # full card width / height
        SW, SH = 90,  64   # small card
        HG     = 14        # horizontal gap between cards
        CONN   = 24        # connector segment height

        # Build row list and compute Y positions
        rows: list[str] = []
        if gp_show:   rows.append("gp")
        if parents:   rows.append("par")
        rows.append("foc")
        if chi_show:  rows.append("chi")

        y_pos: dict[str, int] = {}
        cur_y = 28
        for row in rows:
            y_pos[row] = cur_y
            rh = SH if row in ("gp", "chi") else CH
            cur_y += rh + CONN + 14
        total_h = cur_y + 20

        cx = cw // 2

        # ── Person data helpers ────────────────────────────────────────────
        def _pdata(xid: str) -> dict:
            return persons.get(str(xid)) or {}

        def _pname(xid: str) -> tuple[str, str]:
            d = _pdata(xid)
            if source == "anverwandte":
                n = _sanitize(d.get("name") or
                              f"{d.get('given_name','')}{d.get('surname','')}".strip())
                yr = _years(d.get("birth_year", ""), d.get("death_year", ""))
            else:
                n  = _sanitize(
                    f"{d.get('given_name','')}{d.get('surname','')}".strip())
                yr = _years(str(d.get("birth_year") or ""),
                            str(d.get("death_year") or ""))
            return n.strip(), yr

        def _psex(xid: str) -> str:
            return _pdata(xid).get("sex", "")

        # ── Card drawing ───────────────────────────────────────────────────
        def draw_card(x: int, y: int, xid: str, small: bool = False,
                      highlight: bool = False) -> tuple[int, int, int]:
            """Draw person card. Returns (mid_x, top_y, bot_y)."""
            w = SW if small else CW
            h = SH if small else CH
            sex  = _psex(xid)
            name, yrs = _pname(xid)

            base = (C["card_m"] if sex == "M" else
                    C["card_f"] if sex == "F" else C["card"])
            avt  = _lighten(base, 28)

            ged_m: str | None = None
            is_fz = False
            cluster: int | None = None
            if source == "anverwandte":
                ged_m, is_fz = self._mapping_for(str(xid))
                if ged_m:
                    cluster = self._cluster_map.get(ged_m)

            if highlight:
                bdr = C["accent"]
            elif cluster is not None:
                bdr = C["cluster"]
            elif ged_m and not is_fz:
                bdr = C["mapped"]
            elif is_fz:
                bdr = C["fuzzy"]
            else:
                bdr = base

            tag = f"p_{xid}"

            # Border rect → card background
            tc.create_rectangle(x, y, x+w, y+h,
                                fill=bdr, outline="", tags=tag)
            tc.create_rectangle(x+2, y+2, x+w-2, y+h-2,
                                fill=base, outline="", tags=tag)

            # Avatar strip (top ~38 % of card)
            avt_h = max(20, int(h * 0.38))
            tc.create_rectangle(x+2, y+2, x+w-2, y+2+avt_h,
                                fill=avt, outline="", tags=tag)

            # Silhouette: head oval + shoulder arc
            hx = x + w // 2
            hr = max(6, int(w * 0.09))
            tc.create_oval(hx-hr, y+4, hx+hr, y+4+hr*2,
                           fill=base, outline="", tags=tag)
            bw = max(9, int(w * 0.19))
            tc.create_oval(hx-bw, y+avt_h-4,
                           hx+bw, y+avt_h+max(4, int(avt_h*0.25)),
                           fill=base, outline="", tags=tag)

            # Name (wrapping text below avatar)
            fsz = 7 if small else 9
            ty  = y + avt_h + 5
            tc.create_text(hx, ty, text=name, fill="white",
                           font=("Segoe UI", fsz), anchor="n",
                           width=w - 8, tags=tag)

            # Years (bottom)
            if yrs:
                tc.create_text(hx, y+h-3, text=yrs, fill=C["muted"],
                               font=("Segoe UI", 6 if small else 7),
                               anchor="s", tags=tag)

            # Mapping badge (top-right corner)
            if source == "anverwandte" and not highlight:
                badge = ("◆" if cluster is not None else
                         "✓" if ged_m and not is_fz else
                         "~" if is_fz else "")
                if badge:
                    tc.create_text(x+w-3, y+3, text=badge, fill="white",
                                   font=("Segoe UI", 7, "bold"),
                                   anchor="ne", tags=tag)

            tc.tag_bind(tag, "<Button-1>",
                        lambda e, i=xid: self._navigate(i))
            tc.tag_bind(tag, "<Enter>",
                        lambda e: tc.configure(cursor="hand2"))
            tc.tag_bind(tag, "<Leave>",
                        lambda e: tc.configure(cursor=""))

            return x + w//2, y, y + h

        # ── Line helpers ───────────────────────────────────────────────────
        def vline(x: int, y1: int, y2: int):
            if y1 != y2:
                tc.create_line(x, y1, x, y2, fill=C["muted"], width=1, dash=(2, 3))

        def hline(y: int, x1: int, x2: int):
            if x1 != x2:
                tc.create_line(min(x1, x2), y, max(x1, x2), y,
                               fill=C["muted"], width=1)

        def row_label(y: int, text: str):
            tc.create_text(6, y, text=text, fill=C["muted"],
                           font=("Segoe UI", 8, "bold"), anchor="nw")

        # ── Focal row (siblings left | focal | siblings right) ─────────────
        foc_y   = y_pos["foc"]
        foc_row = sib_left + [pid] + sib_right
        n_foc   = len(foc_row)
        foc_idx = len(sib_left)   # index of focal person in foc_row

        foc_row_w   = n_foc * CW + (n_foc - 1) * HG
        # Focal card left-edge relative to row start
        focal_left  = foc_idx * (CW + HG)
        # Place row so that focal card center = cx
        row_start_x = cx - focal_left - CW // 2

        foc_mids: dict[str, int] = {}
        foc_tops: dict[str, int] = {}
        foc_bots: dict[str, int] = {}
        for i, xid in enumerate(foc_row):
            rx = row_start_x + i * (CW + HG)
            mx, ty, by = draw_card(rx, foc_y, xid, highlight=(xid == pid))
            foc_mids[xid] = mx
            foc_tops[xid] = ty
            foc_bots[xid] = by

        focal_mid_x = foc_mids[pid]
        focal_bot_y = foc_bots[pid]
        focal_top_y = foc_tops[pid]

        if sib_left or sib_right:
            row_label(foc_y, f"Geschwister ({len(siblings)})  /  Fokus")
        else:
            row_label(foc_y, "Fokus")

        # Spouses to the right of sibling row
        sp_mids: dict[str, int] = {}
        if sp_show:
            sp_x = row_start_x + n_foc * (CW + HG) + 6
            for i, sp in enumerate(sp_show):
                sym_x = sp_x + i * (CW + HG + 22)
                tc.create_text(sym_x + 10, foc_y + CH // 2, text="⚭",
                               fill=C["muted"], font=("Segoe UI", 14))
                mx, _, _ = draw_card(sym_x + 22, foc_y, sp)
                sp_mids[sp] = mx

        # ── Parent row ────────────────────────────────────────────────────
        par_mids: dict[str, int] = {}
        if parents:
            par_y  = y_pos["par"]
            n_par  = len(parents)
            par_tw = n_par * CW + (n_par - 1) * HG
            par_sx = cx - par_tw // 2
            for i, par in enumerate(parents):
                rx = par_sx + i * (CW + HG)
                mx, _, _ = draw_card(rx, par_y, par)
                par_mids[par] = mx

            row_label(par_y, "Eltern")

            # Connectors: parents → focal
            conn_mid_y = par_y + CH + CONN // 2
            if len(parents) == 2:
                px0, px1 = par_mids[parents[0]], par_mids[parents[1]]
                vline(px0, par_y + CH, conn_mid_y)
                vline(px1, par_y + CH, conn_mid_y)
                hline(conn_mid_y, px0, px1)
                bar_cx = (px0 + px1) // 2
                vline(bar_cx, conn_mid_y, focal_top_y)
            elif len(parents) == 1:
                vline(par_mids[parents[0]], par_y + CH, focal_top_y)

            # ── Grandparent row ───────────────────────────────────────────
            if gp_show:
                gp_y  = y_pos["gp"]
                n_gp  = len(gp_show)
                gp_tw = n_gp * SW + (n_gp - 1) * HG
                gp_sx = cx - gp_tw // 2
                gp_mids: dict[str, int] = {}
                for i, gp in enumerate(gp_show):
                    rx = gp_sx + i * (SW + HG)
                    mx, _, _ = draw_card(rx, gp_y, gp, small=True)
                    gp_mids[gp] = mx

                row_label(gp_y, "Großeltern")

                # Connectors: grandparents → parents
                for par in parents:
                    par_gps = [g for g in par_gp_map.get(par, [])
                               if g in gp_mids]
                    if not par_gps:
                        continue
                    pmx = par_mids[par]
                    gp_mxs = [gp_mids[g] for g in par_gps]
                    gp_conn_y = gp_y + SH + CONN // 2
                    if len(gp_mxs) >= 2:
                        vline(gp_mxs[0], gp_y + SH, gp_conn_y)
                        vline(gp_mxs[-1], gp_y + SH, gp_conn_y)
                        hline(gp_conn_y, gp_mxs[0], gp_mxs[-1])
                        bar_cx2 = (gp_mxs[0] + gp_mxs[-1]) // 2
                        vline(bar_cx2, gp_conn_y, par_y)
                    elif len(gp_mxs) == 1:
                        vline(gp_mxs[0], gp_y + SH, par_y)

        # Connector: siblings share a horizontal bar linked to parent connector
        if sib_left or sib_right:
            sib_ids = [s for s in (sib_left + sib_right) if s in foc_mids]
            all_in_row = [s for s in foc_row if s in foc_mids]
            if all_in_row:
                bar_y = focal_top_y - CONN // 2
                left_x  = foc_mids[all_in_row[0]]
                right_x = foc_mids[all_in_row[-1]]
                hline(bar_y, left_x, right_x)
                for xid in all_in_row:
                    vline(foc_mids[xid], bar_y, foc_tops[xid])
                # Connect bar to parent connector line
                if parents:
                    if len(parents) == 2:
                        bar_cx = (par_mids[parents[0]] + par_mids[parents[1]]) // 2
                    else:
                        bar_cx = par_mids[parents[0]] if parents else focal_mid_x
                    conn_mid_y2 = y_pos["par"] + CH + CONN // 2
                    vline(bar_cx, conn_mid_y2, bar_y)

        # ── Children row ──────────────────────────────────────────────────
        if chi_show:
            chi_y  = y_pos["chi"]
            n_chi  = len(chi_show)
            chi_tw = n_chi * SW + (n_chi - 1) * HG
            chi_sx = focal_mid_x - chi_tw // 2
            chi_mids: list[int] = []
            for i, ch in enumerate(chi_show):
                rx = chi_sx + i * (SW + HG)
                mx, _, _ = draw_card(rx, chi_y, ch, small=True)
                chi_mids.append(mx)

            more_chi = len(children) - len(chi_show)
            if more_chi > 0:
                tc.create_text(chi_sx + n_chi * (SW + HG) + 6,
                               chi_y + SH // 2,
                               text=f"+{more_chi} weitere",
                               fill=C["muted"], font=("Segoe UI", 8), anchor="w")

            row_label(chi_y, f"Kinder ({len(children)})")

            # Connector: focal → children
            chi_conn_y = focal_bot_y + CONN // 2
            vline(focal_mid_x, focal_bot_y, chi_conn_y)
            if chi_mids:
                hline(chi_conn_y, chi_mids[0], chi_mids[-1])
                for mx in chi_mids:
                    vline(mx, chi_conn_y, chi_y)

        # ── Update scroll region ──────────────────────────────────────────
        tc.update_idletasks()
        bbox = tc.bbox("all")
        if bbox:
            pad = 24
            tc.configure(scrollregion=(
                bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad))
        else:
            tc.configure(scrollregion=(0, 0, cw, total_h))

    # ── GEDCOM-Sub-Detail (eingerückte Zeile angeklickt) ─────────────────────
    def _render_gedcom_sub_detail(self, ged_id: str):
        """Zeigt Detailinfo für eine gematchte GEDCOM-Person (aus _ged_cache)."""
        for w in self._detail.winfo_children():
            w.destroy()
        g = self._ged_cache.get(ged_id)
        if not g:
            tk.Label(self._detail, text=f"Kein Cache für {ged_id}",
                     bg=C["panel"], fg=C["muted"]).pack(pady=20)
            return

        def hdr(t):
            tk.Label(self._detail, text=t, bg=C["panel"], fg=C["accent"],
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(
                fill="x", padx=12, pady=(12, 2))

        def fact(label, value):
            if not value:
                return
            f = tk.Frame(self._detail, bg=C["panel"]); f.pack(fill="x", padx=12, pady=1)
            tk.Label(f, text=label, bg=C["panel"], fg=C["muted"], width=11,
                     anchor="w", font=("Segoe UI", 8)).pack(side="left")
            tk.Label(f, text=value, bg=C["panel"], fg=C["text"], anchor="w",
                     justify="left", wraplength=230).pack(side="left", fill="x", expand=True)

        g_gn = _sanitize(g.get("given_name") or "")
        g_sn = _sanitize(g.get("surname") or "")
        name = f"{g_gn} {g_sn}".strip() or ged_id
        tk.Label(self._detail, text=name, bg=C["panel"], fg="white",
                 font=("Segoe UI", 14, "bold"), wraplength=320,
                 anchor="w").pack(fill="x", padx=12, pady=(12, 0))

        sosa = g.get("sosa_number") or 0
        rel_label = _sosa_to_rel(sosa, g.get("sex") or "")
        meta = f"{ged_id} · GEDCOM"
        if rel_label:
            meta += f" · {rel_label}"
        tk.Label(self._detail, text=meta, bg=C["panel"], fg=C["muted"],
                 anchor="w").pack(fill="x", padx=12)

        dna_info = self._dna_map.get(ged_id)
        cluster  = self._cluster_map.get(ged_id)
        if dna_info or cluster is not None:
            hdr("DNA-Verknüpfung")
        if dna_info:
            fd = tk.Frame(self._detail, bg=C["panel"]); fd.pack(fill="x", padx=12, pady=1)
            tk.Label(fd, text="cM-Wert", bg=C["panel"], fg=C["muted"],
                     width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
            _cm_s = f"{dna_info[0]:.1f} cM" if dna_info[0] is not None else "? cM"
            tk.Label(fd, text=f"🧬 {_cm_s}  —  {dna_info[1]}",
                     bg=C["panel"], fg=C["dna"], anchor="w",
                     font=("Segoe UI", 8, "bold")).pack(side="left")
        if cluster is not None:
            f3 = tk.Frame(self._detail, bg=C["panel"]); f3.pack(fill="x", padx=12, pady=1)
            tk.Label(f3, text="Cluster", bg=C["panel"], fg=C["muted"],
                     width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
            tk.Label(f3, text=f"Cluster {cluster}", bg=C["panel"],
                     fg=C["cluster"], anchor="w",
                     font=("Segoe UI", 8, "bold")).pack(side="left")

        hdr("Lebensdaten")
        fact("Geboren", " · ".join(str(x) for x in (
            g.get("birth_year"), g.get("birth_place")) if x))
        fact("Gestorben", " · ".join(str(x) for x in (
            g.get("death_year"),) if x))
        fact("Geschlecht", g.get("sex", ""))
        if sosa:
            fact("Sosa-Nr.", str(sosa))
        if dna_info:
            if dna_info[0] is not None:
                fact("Erwarteter Grad", _cm_to_rel(dna_info[0]))

        # Vorfahrenpfad
        path = self._ancestor_path(ged_id)
        if path:
            hdr("Vorfahrenpfad")
            pf = tk.Frame(self._detail, bg=C["panel"]); pf.pack(fill="x", padx=12, pady=2)
            for i, (gid_p, pname, ps, prel) in enumerate(path):
                if i:
                    tk.Label(pf, text=" › ", bg=C["panel"], fg=C["muted"],
                             font=("Segoe UI", 8)).pack(side="left")
                lbl = tk.Label(pf, text=pname, bg=C["panel"],
                               fg=C["link"] if gid_p else C["muted"],
                               font=("Segoe UI", 8), cursor="hand2" if gid_p else "arrow")
                lbl.pack(side="left")
                if gid_p:
                    lbl.bind("<Button-1>", lambda _, i=gid_p: self._navigate_ged(i))

        self._status.set(f"GEDCOM: {ged_id}")

    # ── Detailpanel (rechts) ──────────────────────────────────────────────────
    def _render_dna_matches(self, ged_id: str):
        """Rendert alle DNA-Matches einer GEDCOM-Person als Tabelle im Detailpanel."""
        if not self._anc_conn or not ged_id:
            return
        try:
            rows = self._anc_conn.execute(
                "SELECT m.name, m.shared_cm, m.source, m.cluster_id "
                "FROM gedcom_links gl "
                "JOIN matches m ON m.match_guid = gl.match_guid "
                "WHERE gl.ged_id = ? "
                "ORDER BY CAST(m.shared_cm AS REAL) DESC "
                "LIMIT 30",
                (ged_id,)
            ).fetchall()
        except Exception:
            return
        if not rows:
            return

        # Abschnitt-Header
        hf = tk.Frame(self._detail, bg=C["panel"]); hf.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(hf, text="🧬  DNA-Matches", bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(hf, text=f"  {len(rows)} Treffer", bg=C["panel"], fg=C["muted"],
                 font=("Segoe UI", 8)).pack(side="left")

        # Spaltenköpfe
        ch = tk.Frame(self._detail, bg=C["card"]); ch.pack(fill="x", padx=12)
        tk.Label(ch, text="Name", bg=C["card"], fg=C["muted"],
                 width=23, anchor="w", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(4, 0))
        tk.Label(ch, text="cM", bg=C["card"], fg=C["muted"],
                 width=6, anchor="e", font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(ch, text="  Verwandtschaft", bg=C["card"], fg=C["muted"],
                 anchor="w", font=("Segoe UI", 8, "bold")).pack(side="left")

        # Datenzeilen (alternierend eingefärbt)
        for i, r in enumerate(rows):
            cm  = float(r["shared_cm"]) if r["shared_cm"] is not None else 0.0
            rel = _cm_to_rel(cm)
            bg  = C["panel"] if i % 2 == 0 else C["bg"]
            rf  = tk.Frame(self._detail, bg=bg); rf.pack(fill="x", padx=12)
            src = (r["source"] or "")[:6]
            nm  = (r["name"]   or "—")[:26]
            nm_s = f"{nm}  [{src}]" if src else nm
            tk.Label(rf, text=nm_s, bg=bg, fg=C["text"],
                     width=23, anchor="w", font=("Segoe UI", 8)).pack(side="left", padx=(4, 0))
            tk.Label(rf, text=f"{cm:.0f}", bg=bg, fg=C["dna"],
                     width=6, anchor="e", font=("Segoe UI", 8, "bold")).pack(side="left")
            tk.Label(rf, text=f"  {rel}", bg=bg, fg=C["muted"],
                     anchor="w", font=("Segoe UI", 8)).pack(side="left")

    def _render_detail(self, pid: str):
        for w in self._detail.winfo_children():
            w.destroy()
        p = self._person(pid)
        if not p:
            return

        def hdr(t):
            tk.Label(self._detail, text=t, bg=C["panel"], fg=C["accent"],
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(
                fill="x", padx=12, pady=(12, 2))

        def fact(label, value, link_id=None):
            if not value:
                return
            f = tk.Frame(self._detail, bg=C["panel"]); f.pack(fill="x", padx=12, pady=1)
            tk.Label(f, text=label, bg=C["panel"], fg=C["muted"], width=11,
                     anchor="w", font=("Segoe UI", 8)).pack(side="left")
            fg = C["link"] if link_id else C["text"]
            lab = tk.Label(f, text=value, bg=C["panel"], fg=fg, anchor="w",
                           justify="left", wraplength=230,
                           cursor="hand2" if link_id else "arrow")
            lab.pack(side="left", fill="x", expand=True)
            if link_id:
                lab.bind("<Button-1>", lambda _, i=link_id: self._navigate(i))

        if self._source == "anverwandte":
            name = _sanitize(p.get("name") or
                             f"{p.get('given_name','')} {p.get('surname','')}".strip())
            tk.Label(self._detail, text=name, bg=C["panel"], fg="white",
                     font=("Segoe UI", 14, "bold"), wraplength=320,
                     anchor="w").pack(fill="x", padx=12, pady=(12, 0))
            rel_label = self._rel_for_wt(str(p.get("id", pid)))
            meta = f"ID {p.get('id','')} · {p.get('sex','')}"
            if rel_label:
                meta += f" · {rel_label}"
            tk.Label(self._detail, text=meta,
                     bg=C["panel"], fg=C["muted"], anchor="w").pack(
                fill="x", padx=12)

            # GEDCOM-Mapping + DNA anzeigen
            wt_id = str(p.get("id", pid))
            ged_id, is_fuzzy = self._mapping_for(wt_id)
            cluster  = self._cluster_map.get(ged_id) if ged_id else None
            dna_info = self._dna_map.get(ged_id) if ged_id else None

            is_auto  = wt_id in self._auto_map
            is_confirmed = wt_id in self._gedcom_map

            if ged_id or cluster is not None or dna_info:
                hdr("GEDCOM-Verknüpfung")
            if ged_id:
                if is_confirmed:
                    kind, color = "Bestätigt (✓)", C["mapped"]
                elif is_auto:
                    kind, color = f"Auto-Match (Score {self._auto_scores.get(wt_id, 0):.1f})", C["dna"]
                else:
                    kind, color = "Fuzzy-Match (~)", C["fuzzy"]
                f2 = tk.Frame(self._detail, bg=C["panel"])
                f2.pack(fill="x", padx=12, pady=1)
                tk.Label(f2, text="Status", bg=C["panel"], fg=C["muted"],
                         width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
                tk.Label(f2, text=kind, bg=C["panel"], fg=color, anchor="w",
                         font=("Segoe UI", 8, "bold")).pack(side="left")
                fact("GED-ID", ged_id)

                # Bestätigen / Ablehnen / Aufheben
                btn_frame = tk.Frame(self._detail, bg=C["panel"])
                btn_frame.pack(fill="x", padx=12, pady=(2, 4))
                if not is_confirmed:
                    tk.Button(btn_frame, text="✓ Bestätigen",
                              bg=C["mapped"], fg="white", font=("Segoe UI", 8),
                              relief="flat", padx=6, pady=2,
                              command=lambda wi=wt_id, gi=ged_id: self._confirm_match(wi, gi)
                              ).pack(side="left", padx=(0, 4))
                tk.Button(btn_frame,
                          text="✗ Ablehnen" if not is_confirmed else "↩ Verknüpfung aufheben",
                          bg=C["card"], fg=C["muted"], font=("Segoe UI", 8),
                          relief="flat", padx=6, pady=2,
                          command=lambda wi=wt_id, gi=ged_id: self._reject_match(wi, gi)
                          ).pack(side="left")

            if ged_id:
                self._render_dna_matches(ged_id)
            if cluster is not None:
                f3 = tk.Frame(self._detail, bg=C["panel"])
                f3.pack(fill="x", padx=12, pady=1)
                tk.Label(f3, text="DNA-Cluster", bg=C["panel"], fg=C["muted"],
                         width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
                tk.Label(f3, text=f"Cluster {cluster}", bg=C["panel"],
                         fg=C["cluster"], anchor="w",
                         font=("Segoe UI", 8, "bold")).pack(side="left")

            # Vorfahrenpfad (wenn ged_id eine SOSA-Nummer hat)
            if ged_id:
                path = self._ancestor_path(ged_id)
                if path:
                    hdr("Vorfahrenpfad")
                    pf = tk.Frame(self._detail, bg=C["panel"])
                    pf.pack(fill="x", padx=12, pady=2)
                    for i, (gid_p, pname, ps, prel) in enumerate(path):
                        if i:
                            tk.Label(pf, text=" › ", bg=C["panel"], fg=C["muted"],
                                     font=("Segoe UI", 8)).pack(side="left")
                        lbl = tk.Label(pf, text=pname, bg=C["panel"],
                                       fg=C["link"] if gid_p else C["muted"],
                                       font=("Segoe UI", 8), cursor="hand2" if gid_p else "arrow")
                        lbl.pack(side="left")
                        if gid_p:
                            lbl.bind("<Button-1>", lambda _, i=gid_p: self._navigate_ged(i))

            hdr("Lebensdaten")
            fact("Geboren", " · ".join(x for x in (
                p.get("birth_date"), p.get("birth_place")) if x))
            fact("Gestorben", " · ".join(x for x in (
                p.get("death_date"), p.get("death_place")) if x))

            # Pfarrei-Info aus Matricula-Lookup
            parish = self._parish_info(p.get("birth_place") or "")
            if parish:
                hdr("Kirchspiel (Matricula)")
                conf_label = ("Katholisch" if parish.get("confession") == "kath"
                              else "Evangelisch" if parish.get("confession") == "ev"
                              else parish.get("confession", ""))
                conf_color = (C["kath"] if parish.get("confession") == "kath"
                              else C["ev"] if parish.get("confession") == "ev"
                              else C["text"])
                f_conf = tk.Frame(self._detail, bg=C["panel"])
                f_conf.pack(fill="x", padx=12, pady=1)
                tk.Label(f_conf, text="Konfession", bg=C["panel"], fg=C["muted"],
                         width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
                tk.Label(f_conf, text=conf_label, bg=C["panel"], fg=conf_color,
                         anchor="w", font=("Segoe UI", 8, "bold")).pack(side="left")
                fact("Pfarrei", parish.get("parish", ""))
                if parish.get("parent_id"):
                    fact("Mutterpfarrei", parish.get("parent_id", "").replace("-", " ").title())
                if parish.get("founded"):
                    fact("Gegründet", str(parish["founded"]))

            hdr("Beziehungen")
            for par in _loads(p.get("parents_json")):
                fact("Elternteil", self._label_for(par).replace("\n", " "), par)
            for sp in _loads(p.get("spouses_json")):
                fact("Partner", self._label_for(sp).replace("\n", " "), sp)
            ch = _loads(p.get("children_json"))
            for c in ch:
                fact("Kind", self._label_for(c).replace("\n", " "), c)
            for sib in _loads(p.get("siblings_json")):
                fact("Geschwister", self._label_for(sib).replace("\n", " "), sib)

            # Matricula-Belege
            matric = _loads(p.get("matricula_json"))
            if matric:
                hdr("Kirchenbuch-Belege (Matricula)")
                for m in matric:
                    if not isinstance(m, dict):
                        continue
                    parts = []
                    if m.get("parish_old"): parts.append(m["parish_old"])
                    if m.get("ref"):        parts.append(m["ref"])
                    if m.get("diocese"):    parts.append(f"({m['diocese']})")
                    txt = " ".join(parts) or m.get("url_old", "")
                    fact("Beleg", txt)
                    if m.get("url_old"):
                        u = tk.Label(self._detail, text=m["url_old"][:50] + "…",
                                     bg=C["panel"], fg=C["link"], cursor="hand2",
                                     anchor="w", font=("Segoe UI", 7), wraplength=320)
                        u.pack(fill="x", padx=24)
                        u.bind("<Button-1>", lambda _, url=m["url_old"]:
                               self._open_url(url))

            if p.get("url"):
                hdr("Quelle")
                u = tk.Label(self._detail, text=p["url"], bg=C["panel"],
                             fg=C["link"], cursor="hand2", anchor="w",
                             font=("Segoe UI", 7), wraplength=320)
                u.pack(fill="x", padx=12)
                u.bind("<Button-1>", lambda _, url=p["url"]: self._open_url(url))

            # ── Verwandtschaft berechnen ──────────────────────────────────
            hdr("Verwandtschaft")
            fp = tk.Frame(self._detail, bg=C["panel"]); fp.pack(fill="x", padx=12, pady=4)
            if self._rel_target and self._rel_target != wt_id:
                rel_name = self._label_for(self._rel_target).replace("\n", " ")[:35]
                tk.Button(
                    fp, text=f"🔗 Verwandtschaft zu {rel_name}",
                    bg=C["dna"], fg="white", font=("Segoe UI", 8), relief="flat",
                    padx=6, pady=3, wraplength=220, justify="left",
                    command=lambda a=wt_id, b=self._rel_target: self._show_rel_path_window(a, b)
                ).pack(side="left", padx=(0, 4))
                tk.Button(fp, text="✕ Aufheben", bg=C["card"], fg=C["muted"],
                          font=("Segoe UI", 8), relief="flat", padx=4, pady=3,
                          command=self._clear_rel_target).pack(side="left")
            elif self._rel_target == wt_id:
                tk.Button(fp, text="📌 Person A gesetzt – wähle Person B",
                          bg=C["mapped"], fg="white", font=("Segoe UI", 8),
                          relief="flat", padx=6, pady=3, state="disabled"
                          ).pack(side="left", padx=(0, 4))
                tk.Button(fp, text="✕ Aufheben", bg=C["card"], fg=C["muted"],
                          font=("Segoe UI", 8), relief="flat", padx=4, pady=3,
                          command=self._clear_rel_target).pack(side="left")
            else:
                tk.Button(fp, text="📌 Als Person A festlegen",
                          bg=C["card"], fg=C["text"], font=("Segoe UI", 8),
                          relief="flat", padx=6, pady=3,
                          command=lambda wi=wt_id, n=name: self._set_rel_target(wi, n)
                          ).pack(side="left")
        else:
            name = _sanitize(
                f"{p.get('given_name','')} {p.get('surname','')}".strip())
            tk.Label(self._detail, text=name, bg=C["panel"], fg="white",
                     font=("Segoe UI", 14, "bold"), wraplength=320,
                     anchor="w").pack(fill="x", padx=12, pady=(12, 0))
            sosa = p.get("sosa_number") or 0
            rel_label = _sosa_to_rel(sosa, p.get("sex") or "")
            meta = f"{p.get('ged_id','')} · Quelle: {p.get('source','')}"
            if rel_label:
                meta += f" · {rel_label}"
            tk.Label(self._detail, text=meta,
                     bg=C["panel"], fg=C["muted"], anchor="w").pack(
                fill="x", padx=12)

            # DNA-Matches + Cluster anzeigen (für GEDCOM-Personen direkt)
            ged_id_p = str(p.get("ged_id", ""))
            cluster  = self._cluster_map.get(ged_id_p)
            self._render_dna_matches(ged_id_p)
            if cluster is not None:
                f3 = tk.Frame(self._detail, bg=C["panel"])
                f3.pack(fill="x", padx=12, pady=1)
                tk.Label(f3, text="Cluster", bg=C["panel"], fg=C["muted"],
                         width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
                tk.Label(f3, text=f"Cluster {cluster}", bg=C["panel"],
                         fg=C["cluster"], anchor="w",
                         font=("Segoe UI", 8, "bold")).pack(side="left")

            hdr("Lebensdaten")
            fact("Geboren", " · ".join(str(x) for x in (
                p.get("birth_year"), p.get("birth_place")) if x))
            fact("Gestorben", " · ".join(str(x) for x in (
                p.get("death_year"), p.get("death_place")) if x))
            fact("Sosa", str(p.get("sosa_number") or "") if p.get("sosa_number") else "")
            fact("Geschlecht", p.get("sex", ""))

            # Familie (aus SOSA-Arithmetik abgeleitet)
            sosa_d, _ = self._sosa_map.get(pid, (0, ""))
            if sosa_d:
                hdr("Familie")
                father_d = self._sosa_rev.get(sosa_d * 2)
                mother_d = self._sosa_rev.get(sosa_d * 2 + 1)
                if father_d:
                    fact("Vater", self._label_for(father_d).replace("\n", " "), father_d)
                if mother_d:
                    fact("Mutter", self._label_for(mother_d).replace("\n", " "), mother_d)
                if sosa_d > 1:
                    child_d = self._sosa_rev.get(sosa_d // 2)
                    co_sosa_d = (sosa_d // 2) * 2 + (1 if sosa_d % 2 == 0 else 0)
                    co_d = self._sosa_rev.get(co_sosa_d)
                    if co_d and co_d != pid:
                        fact("Partner", self._label_for(co_d).replace("\n", " "), co_d)
                    if child_d:
                        fact("Kind (Ahnenreihe)",
                             self._label_for(child_d).replace("\n", " "), child_d)

            # Vorfahrenpfad
            path_d = self._ancestor_path(pid)
            if path_d:
                hdr("Vorfahrenpfad")
                pf2 = tk.Frame(self._detail, bg=C["panel"]); pf2.pack(fill="x", padx=12, pady=2)
                for i, (gid_p, pname, _ps, _prel) in enumerate(path_d):
                    if i:
                        tk.Label(pf2, text=" › ", bg=C["panel"], fg=C["muted"],
                                 font=("Segoe UI", 8)).pack(side="left")
                    lbl2 = tk.Label(pf2, text=pname, bg=C["panel"],
                                    fg=C["link"] if gid_p else C["muted"],
                                    font=("Segoe UI", 8), cursor="hand2" if gid_p else "arrow")
                    lbl2.pack(side="left")
                    if gid_p:
                        lbl2.bind("<Button-1>", lambda _, i=gid_p: self._navigate(i))

        self._status.set(f"Anzeige: {pid}")

    def _open_url(self, url: str):
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            messagebox.showinfo("Link", f"{url}\n\n({e})")

    def mainloop(self, *a, **k):
        self.winfo_toplevel().mainloop(*a, **k)


def main():
    db = sys.argv[1] if len(sys.argv) > 1 else CRAWL_DB
    app = DataViewer(db_path=db)
    app.mainloop()


if __name__ == "__main__":
    main()
