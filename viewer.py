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
import re
import sqlite3
import sys
import tkinter as tk
from collections import deque
from tkinter import ttk, messagebox

ROOT = os.path.dirname(os.path.abspath(__file__))
CRAWL_DB      = os.path.join(ROOT, "ancestry", "tools", "webtrees_crawl.db")
ANCESTRY_DB   = os.path.join(ROOT, "ancestry", "ancestry_dna.db")
PARISH_JSON   = os.path.join(ROOT, "ancestry", "tools", "matricula_parishes.json")

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
        """Create read-optimised indexes on wt_persons if not yet present.

        Needs a write connection; silently skips if the DB is locked or absent.
        """
        db_path = self._db_path if self._source == "anverwandte" else ANCESTRY_DB
        if not os.path.exists(db_path):
            return
        try:
            import sqlite3 as _sq3
            wc = _sq3.connect(db_path, timeout=3.0)
            wc.execute(
                "CREATE INDEX IF NOT EXISTS idx_wtp_sort "
                "ON wt_persons(surname, given_name)")
            wc.execute(
                "CREATE INDEX IF NOT EXISTS idx_wtp_search "
                "ON wt_persons(surname, given_name, name)")
            wc.commit()
            wc.close()
        except Exception:
            pass

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
        # Zeile 1: Quelle, Filter, Suche, Aktionen
        top = tk.Frame(self, bg=C["panel"]); top.pack(fill="x")
        tk.Label(top, text="Quelle:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4), pady=6)
        self._src_var = tk.StringVar(value="Anverwandte (Crawl)")
        src = ttk.Combobox(top, textvariable=self._src_var, width=22,
                           state="readonly",
                           values=["Anverwandte (Crawl)", "GEDCOM / extern"])
        src.pack(side="left", pady=6)
        src.bind("<<ComboboxSelected>>", self._on_source_change)

        tk.Label(top, text="Filter:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(12, 4))
        self._filter_var = tk.StringVar(value=_FILTER_ALL)
        flt = ttk.Combobox(top, textvariable=self._filter_var, width=16,
                           state="readonly",
                           values=[_FILTER_ALL, _FILTER_DNA, _FILTER_MAPPED,
                                   _FILTER_FUZZY, _FILTER_UNMAP])
        flt.pack(side="left", pady=6)
        flt.bind("<<ComboboxSelected>>", lambda _: self._do_search())

        tk.Label(top, text="Konfession:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4))
        self._conf_var = tk.StringVar(value=_CONF_ALL)
        conf = ttk.Combobox(top, textvariable=self._conf_var, width=13,
                            state="readonly",
                            values=[_CONF_ALL, _CONF_KATH, _CONF_EV, _CONF_UNK])
        conf.pack(side="left", pady=6)
        conf.bind("<<ComboboxSelected>>", lambda _: self._do_search())

        tk.Label(top, text="DNA-Quelle:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4))
        self._dna_src_var = tk.StringVar(value="Alle")
        self._dna_src_box = ttk.Combobox(top, textvariable=self._dna_src_var, width=13,
                                          state="readonly",
                                          values=["Alle"])
        self._dna_src_box.pack(side="left", pady=6)
        self._dna_src_box.bind("<<ComboboxSelected>>", lambda _: self._do_search())

        tk.Label(top, text="Suche:", bg=C["panel"], fg=C["text"]).pack(
            side="left", padx=(10, 4))
        self._search_var = tk.StringVar()
        e = tk.Entry(top, textvariable=self._search_var, width=22)
        e.pack(side="left", pady=6)
        e.bind("<Return>", lambda _: self._do_search())
        tk.Button(top, text="🔍", command=self._do_search).pack(side="left", padx=2)
        tk.Button(top, text="🔄", command=self._reopen,
                  bg=C["panel"], fg=C["text"], relief="flat").pack(side="left", padx=4)
        tk.Button(top, text="📊 Statistik", command=self._show_stats_window,
                  bg=C["panel"], fg=C["text"], relief="flat").pack(side="left", padx=2)
        tk.Button(top, text="⚡ Bulk", command=self._show_bulk_window,
                  bg=C["panel"], fg=C["dna"], relief="flat").pack(side="left", padx=2)
        self._undo_btn = tk.Button(top, text="↩ Rückgängig", command=self._undo_last,
                                   bg=C["panel"], fg=C["muted"], relief="flat",
                                   state="disabled")
        self._undo_btn.pack(side="left", padx=4)

        self._stats = tk.StringVar(value="")
        tk.Label(top, textvariable=self._stats, bg=C["panel"], fg=C["accent"],
                 font=("Segoe UI", 9, "bold")).pack(side="right", padx=12)

        # Mapping-Legende
        leg = tk.Frame(self, bg=C["bg"]); leg.pack(fill="x")
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

        # Hauptbereich: links Liste, Mitte Baum, rechts Detail
        body = tk.Frame(self, bg=C["bg"]); body.pack(fill="both", expand=True)

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

        # Treeview-Tags für Farbkodierung
        self._list.tag_configure("mapped",   foreground=C["mapped"])
        self._list.tag_configure("fuzzy",    foreground=C["fuzzy"])
        self._list.tag_configure("cluster",  foreground=C["cluster"])
        self._list.tag_configure("dna",      foreground=C["dna"])
        self._list.tag_configure("kath",     foreground=C["kath"])
        self._list.tag_configure("ev",       foreground=C["ev"])
        self._list.tag_configure("sub",      foreground=C["muted"])

        # Mitte: navigierbarer Mini-Baum
        mid = tk.Frame(body, bg=C["bg"]); mid.pack(side="left", fill="both",
                                                   expand=True)
        nav = tk.Frame(mid, bg=C["bg"]); nav.pack(fill="x")
        tk.Button(nav, text="◀ Zurück", command=self._go_back).pack(
            side="left", padx=8, pady=6)
        self._tree_canvas = tk.Frame(mid, bg=C["bg"])
        self._tree_canvas.pack(fill="both", expand=True, padx=8, pady=8)

        # Rechts: Detailpanel (scrollbar)
        right = tk.Frame(body, bg=C["panel"], width=360); right.pack(
            side="right", fill="y"); right.pack_propagate(False)
        self._detail_canvas = tk.Canvas(right, bg=C["panel"],
                                        highlightthickness=0, width=360)
        dsb = ttk.Scrollbar(right, orient="vertical",
                            command=self._detail_canvas.yview)
        self._detail = tk.Frame(self._detail_canvas, bg=C["panel"])
        self._detail.bind("<Configure>", lambda _: self._detail_canvas.configure(
            scrollregion=self._detail_canvas.bbox("all")))
        self._detail_canvas.create_window((0, 0), window=self._detail, anchor="nw")
        self._detail_canvas.configure(yscrollcommand=dsb.set)
        self._detail_canvas.pack(side="left", fill="both", expand=True)
        dsb.pack(side="right", fill="y")

        # Statuszeile
        self._status = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status, bg=C["bg"], fg=C["muted"],
                 anchor="w").pack(fill="x", side="bottom")

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

    # ── Mini-Baum (Mitte) ─────────────────────────────────────────────────────
    def _render_tree(self, pid: str):
        for w in self._tree_canvas.winfo_children():
            w.destroy()

        # Side-by-side: show anverwandte + GEDCOM columns when a match exists
        if self._source == "anverwandte":
            ged_id, _ = self._mapping_for(str(pid))
            if ged_id:
                hdr_row = tk.Frame(self._tree_canvas, bg=C["bg"])
                hdr_row.pack(fill="x", padx=4, pady=(4, 0))
                tk.Label(hdr_row, text="◀ Anverwandte", bg=C["bg"], fg=C["accent"],
                         font=("Segoe UI", 9, "bold")).pack(side="left", padx=8)
                tk.Label(hdr_row, text="GEDCOM ▶", bg=C["bg"], fg=C["dna"],
                         font=("Segoe UI", 9, "bold")).pack(side="right", padx=8)
                cols = tk.Frame(self._tree_canvas, bg=C["bg"])
                cols.pack(fill="both", expand=True)
                left = tk.Frame(cols, bg=C["bg"])
                left.pack(side="left", fill="both", expand=True, padx=4)
                tk.Frame(cols, bg=C["muted"], width=1).pack(side="left", fill="y", pady=4)
                right = tk.Frame(cols, bg=C["bg"])
                right.pack(side="right", fill="both", expand=True, padx=4)
                self._render_one_tree(left, "anverwandte", pid)
                self._render_one_tree(right, "gedcom", ged_id)
                return

        self._render_one_tree(self._tree_canvas, self._source, pid)

    def _render_one_tree(self, container: tk.Widget, source: str, pid: str):
        """Render a family tree for `pid` into `container` using `source` DB."""
        def card(par, xid, highlight=False, small=False):
            if source == "gedcom":
                return self._person_card_ged(par, xid, highlight=highlight, small=small)
            return self._person_card(par, xid, highlight=highlight, small=small)

        p = self._person_for(source, pid)
        if not p:
            tk.Label(container, text="Person nicht gefunden.",
                     bg=C["bg"], fg=C["muted"]).pack(pady=20)
            return

        grandparents: list[str] = []

        # Both sources use stored JSON when available
        parents  = _loads(p.get("parents_json"))
        spouses  = _loads(p.get("spouses_json"))
        children = _loads(p.get("children_json"))
        siblings = _loads(p.get("siblings_json"))
        for par in parents:
            par_data = self._person_for(source, par)
            if par_data:
                grandparents.extend(_loads(par_data.get("parents_json")))

        # SOSA fallback for GEDCOM persons imported before family JSON was stored
        if not parents and source == "gedcom":
            sosa, _ = self._sosa_map.get(pid, (0, ""))
            if sosa:
                father_id = self._sosa_rev.get(sosa * 2)
                mother_id = self._sosa_rev.get(sosa * 2 + 1)
                parents   = [g for g in [father_id, mother_id] if g]
                for gs in [sosa * 4, sosa * 4 + 1, sosa * 4 + 2, sosa * 4 + 3]:
                    gp = self._sosa_rev.get(gs)
                    if gp:
                        grandparents.append(gp)
                if sosa > 1:
                    child_sosa = sosa // 2
                    child_id   = self._sosa_rev.get(child_sosa)
                    children   = [child_id] if child_id else []
                    co_sosa    = child_sosa * 2 + (1 if sosa % 2 == 0 else 0)
                    co_id      = self._sosa_rev.get(co_sosa)
                    spouses    = [co_id] if co_id and co_id != pid else []
                else:
                    children = []
                    spouses  = []

        if grandparents:
            tk.Label(container, text="Großeltern",
                     bg=C["bg"], fg=C["muted"]).pack(pady=(4, 0))
            gprow = tk.Frame(container, bg=C["bg"]); gprow.pack()
            for gp in grandparents[:8]:
                card(gprow, gp, small=True).pack(side="left", padx=4, pady=2)
            if len(grandparents) > 8:
                tk.Label(gprow, text=f"+{len(grandparents)-8}",
                         bg=C["bg"], fg=C["muted"]).pack(side="left")
            tk.Label(container, text="│", bg=C["bg"], fg=C["muted"]).pack()

        if parents:
            tk.Label(container, text="Eltern",
                     bg=C["bg"], fg=C["muted"]).pack(pady=(0, 0))
            prow = tk.Frame(container, bg=C["bg"]); prow.pack()
            for par in parents:
                card(prow, par).pack(side="left", padx=6, pady=4)
            tk.Label(container, text="│", bg=C["bg"], fg=C["muted"]).pack()

        crow = tk.Frame(container, bg=C["bg"]); crow.pack(pady=4)
        card(crow, pid, highlight=True).pack(side="left", padx=6)
        for sp in spouses:
            tk.Label(crow, text="⚭", bg=C["bg"], fg=C["muted"],
                     font=("Segoe UI", 14)).pack(side="left")
            card(crow, sp).pack(side="left", padx=6)

        child_label = ("Nachkomme (Ahnenreihe)" if source != "anverwandte" and len(children) == 1
                       else f"Kinder ({len(children)})")
        if children:
            tk.Label(container, text="│", bg=C["bg"], fg=C["muted"]).pack()
            tk.Label(container, text=child_label,
                     bg=C["bg"], fg=C["muted"]).pack()
            kwrap = tk.Frame(container, bg=C["bg"]); kwrap.pack()
            for i, ch in enumerate(children[:24]):
                if i % 8 == 0:
                    krow = tk.Frame(kwrap, bg=C["bg"]); krow.pack()
                card(krow, ch, small=True).pack(side="left", padx=4, pady=4)
            if len(children) > 24:
                tk.Label(kwrap, text=f"… +{len(children)-24} weitere",
                         bg=C["bg"], fg=C["muted"]).pack()

            grandchildren: list[str] = []
            if source == "anverwandte":
                for ch in children:
                    ch_data = self._person_for(source, ch)
                    if ch_data:
                        grandchildren.extend(_loads(ch_data.get("children_json")))
            if grandchildren:
                tk.Label(container, text="│", bg=C["bg"], fg=C["muted"]).pack()
                tk.Label(container, text=f"Enkelkinder ({len(grandchildren)})",
                         bg=C["bg"], fg=C["muted"]).pack()
                ekwrap = tk.Frame(container, bg=C["bg"]); ekwrap.pack()
                for i, ek in enumerate(grandchildren[:16]):
                    if i % 8 == 0:
                        ekrow = tk.Frame(ekwrap, bg=C["bg"]); ekrow.pack()
                    card(ekrow, ek, small=True).pack(side="left", padx=3, pady=2)
                if len(grandchildren) > 16:
                    tk.Label(ekwrap, text=f"… +{len(grandchildren)-16} weitere",
                             bg=C["bg"], fg=C["muted"]).pack()

        if siblings:
            tk.Label(container, text=f"Geschwister: {len(siblings)}",
                     bg=C["bg"], fg=C["muted"]).pack(pady=(10, 0))

    def _label_for_ged(self, ged_id: str) -> str:
        """Display name for a GEDCOM person (used in side-by-side view)."""
        if not ged_id:
            return ged_id
        g = self._person_for("gedcom", ged_id)
        if g:
            name = _sanitize(
                f"{g.get('given_name') or ''} {g.get('surname') or ''}".strip())
            yrs = _years(str(g.get("birth_year") or ""), str(g.get("death_year") or ""))
            return (name + (f"\n{yrs}" if yrs else "")) or ged_id
        return ged_id

    def _person_card_ged(self, parent, ged_id: str, highlight=False, small=False) -> tk.Widget:
        """Person card for a GEDCOM person (right column in side-by-side view)."""
        g   = self._person_for("gedcom", ged_id)
        sex = (g or {}).get("sex", "")
        bg  = C["card_m"] if sex == "M" else C["card_f"] if sex == "F" else C["card"]
        outer_bg = C["accent"] if highlight else bg
        frame = tk.Frame(parent, bg=outer_bg, bd=0)
        inner = tk.Frame(frame, bg=bg)
        inner.pack(padx=2, pady=2)
        lbl_text = self._label_for_ged(ged_id)
        # Relationship label on full-size cards
        if not small:
            sosa, gsex = self._sosa_map.get(ged_id, (0, ""))
            rel = _sosa_to_rel(sosa, gsex or sex)
            if rel:
                lbl_text = lbl_text + f"\n{rel}"
        w = 14 if small else 18
        btn = tk.Label(inner, text=lbl_text, bg=bg, fg="white",
                       width=w, justify="center", cursor="hand2",
                       font=("Segoe UI", 7 if small else 9),
                       padx=4, pady=4, wraplength=130)
        btn.pack()
        btn.bind("<Button-1>", lambda _, i=ged_id: self._navigate_ged(i))
        return frame

    def _person_card(self, parent, pid: str, highlight=False, small=False) -> tk.Widget:
        p   = self._person(pid)
        sex = (p or {}).get("sex", "") if p else ""
        bg  = C["card_m"] if sex == "M" else C["card_f"] if sex == "F" else C["card"]

        # GEDCOM-Mapping-Overlay-Farbe (nur Anverwandte-Modus)
        ged_id: str | None  = None
        is_fuzzy: bool      = False
        cluster: int | None = None
        if self._source == "anverwandte":
            ged_id, is_fuzzy = self._mapping_for(str(pid))
            if ged_id:
                cluster = self._cluster_map.get(ged_id)

        border_color = (C["cluster"] if cluster is not None else
                        C["mapped"]  if ged_id and not is_fuzzy else
                        C["fuzzy"]   if is_fuzzy else None)

        if highlight:
            outer_bg = C["accent"]
        elif border_color:
            outer_bg = border_color
        else:
            outer_bg = bg

        frame = tk.Frame(parent, bg=outer_bg, bd=0)
        inner = tk.Frame(frame, bg=bg)
        inner.pack(padx=2, pady=2)

        lbl_text = self._label_for(pid)
        # Badge: GED + Cluster
        badge = ""
        if cluster is not None:
            badge = f" ◆C{cluster}"
        elif ged_id and not is_fuzzy:
            badge = " ✓"
        elif is_fuzzy:
            badge = " ~"
        if badge:
            lbl_text = lbl_text.rstrip() + badge
        # Relationship label on full-size cards
        if not small:
            rel = self._rel_for_wt(str(pid))
            if rel:
                lbl_text = lbl_text + f"\n{rel}"

        w = 14 if small else 18
        btn = tk.Label(inner, text=lbl_text, bg=bg, fg="white",
                       width=w, justify="center", cursor="hand2",
                       font=("Segoe UI", 7 if small else 9),
                       padx=4, pady=4, wraplength=130)
        btn.pack()
        btn.bind("<Button-1>", lambda _, i=pid: self._navigate(i))
        return frame

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

            if dna_info:
                fd = tk.Frame(self._detail, bg=C["panel"])
                fd.pack(fill="x", padx=12, pady=1)
                tk.Label(fd, text="DNA-Match", bg=C["panel"], fg=C["muted"],
                         width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
                _cm_s2 = f"{dna_info[0]:.1f} cM  ({_cm_to_rel(dna_info[0])})" if dna_info[0] is not None else "? cM"
                tk.Label(fd, text=f"🧬 {_cm_s2}  —  {dna_info[1]}",
                         bg=C["panel"], fg=C["dna"], anchor="w",
                         font=("Segoe UI", 8, "bold"), wraplength=240).pack(side="left")
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

            # DNA-Match + Cluster anzeigen (für GEDCOM-Personen direkt)
            ged_id_p = str(p.get("ged_id", ""))
            dna_info = self._dna_map.get(ged_id_p)
            cluster  = self._cluster_map.get(ged_id_p)
            if dna_info or cluster is not None:
                hdr("DNA-Verknüpfung")
            if dna_info:
                fd = tk.Frame(self._detail, bg=C["panel"]); fd.pack(fill="x", padx=12, pady=1)
                tk.Label(fd, text="DNA-Match", bg=C["panel"], fg=C["muted"],
                         width=11, anchor="w", font=("Segoe UI", 8)).pack(side="left")
                _cm_s = f"{dna_info[0]:.1f} cM" if dna_info[0] is not None else "? cM"
                tk.Label(fd, text=f"🧬 {_cm_s}  —  {dna_info[1]}",
                         bg=C["panel"], fg=C["dna"], anchor="w",
                         font=("Segoe UI", 8, "bold")).pack(side="left")
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
