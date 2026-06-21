"""
_text.py — Normalisierung, Phonetik und String-Distanzen für das Bridge-Modul.
"""

import json
import os
import re
import unicodedata
from difflib import SequenceMatcher

# ── DFD-Varianten-Cache ───────────────────────────────────────────────────────
# Befüllt beim ersten Aufruf von expand_surname_variants() aus data/dfd_variants.json.

_SURNAME_VARIANTS: dict[str, list[str]] = {}
_VARIANTS_LOADED = False


def _load_surname_variants() -> None:
    global _SURNAME_VARIANTS, _VARIANTS_LOADED
    if _VARIANTS_LOADED:
        return
    _VARIANTS_LOADED = True
    try:
        _here = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        path = os.path.join(_here, "data", "dfd_variants.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                raw: dict = json.load(f)
            _SURNAME_VARIANTS = {k: list(v) for k, v in raw.items()}
    except (OSError, json.JSONDecodeError, ValueError):
        pass


def expand_surname_variants(sn_norm: str) -> set[str]:
    """Gibt {sn_norm} plus alle normierten DFD-Varianten zurück."""
    _load_surname_variants()
    result = {sn_norm}
    for raw_sn, variants in _SURNAME_VARIANTS.items():
        if _norm(raw_sn) == sn_norm:
            for v in variants:
                nv = _norm(v)
                if nv:
                    result.add(nv)
            break
    return result

# ── Normalisierung (standalone, kein Import aus treematch nötig) ──────────────

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _norm(s: str) -> str:
    """Lowercase, ß→ss, Diakritika weg, nur a-z0-9 Leerzeichen."""
    s = (s or "").lower().replace("ß", "ss")
    s = _strip_accents(s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ── Kölner Phonetik (standalone, keine externen Abhängigkeiten) ───────────────

def _koelner(name: str) -> str:
    if not name:
        return ""
    name = name.upper().strip()
    name = (name.replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE")
            .replace("ß", "SS").replace("PH", "F").replace("TH", "T"))
    name = re.sub(r"[^A-Z]", "", name)
    if not name:
        return ""
    codes = []
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


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[lb]


def _lev(a: str, b: str, cap: int = 4) -> int:
    """Levenshtein-Distanz mit Früh-Abbruch bei > cap (Performance)."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > cap:
        return cap + 1
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        row_min = cur[0]
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            row_min = min(row_min, cur[j])
        if row_min > cap:
            return cap + 1
        prev = cur
    return prev[lb]


def _damerau_levenshtein(a: str, b: str) -> int:
    """Optimal-String-Alignment-Distanz: wie Levenshtein, aber eine Vertauschung
    benachbarter Zeichen (Maier↔Maeir) kostet 1 statt 2 — genau das häufigste
    Schreibvariantenmuster bei Nachnamen."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def _jaro(a: str, b: str) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    match_dist = max(0, max(la, lb) // 2 - 1)
    a_match = [False] * la
    b_match = [False] * lb
    matches = 0
    for i in range(la):
        start = max(0, i - match_dist)
        end   = min(i + match_dist + 1, lb)
        for j in range(start, end):
            if b_match[j] or a[i] != b[j]:
                continue
            a_match[i] = b_match[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    t = k = 0
    for i in range(la):
        if not a_match[i]:
            continue
        while not b_match[k]:
            k += 1
        if a[i] != b[k]:
            t += 1
        k += 1
    t //= 2
    return (matches / la + matches / lb + (matches - t) / matches) / 3.0


def _jaro_winkler(a: str, b: str, p: float = 0.1, max_prefix: int = 4) -> float:
    """Jaro-Winkler-Ähnlichkeit (0..1): belohnt gemeinsame Präfixe — der in
    Record-Linkage bewährte Nachnamen-Vergleicher (Schmidt/Schmitt punkten hoch)."""
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return 0.0
    j = _jaro(a, b)
    prefix = 0
    for i in range(min(max_prefix, len(a), len(b))):
        if a[i] == b[i]:
            prefix += 1
        else:
            break
    return j + prefix * p * (1 - j)


def _name_sim(a: str, b: str) -> float:
    """0..1 Ähnlichkeit zweier Namen: kombiniert SequenceMatcher-Ratio,
    längen-normierte Damerau-Levenshtein-Distanz und Jaro-Winkler (präfix-
    gewichtet, transpositions-robust)."""
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    maxlen = max(len(a), len(b))
    lev_sim = 1.0 - _damerau_levenshtein(a, b) / maxlen
    return max(seq, lev_sim, _jaro_winkler(a, b))


# ── Ort-Nachnamen-Korrelation: wahrscheinliche Herkunftsregion ────────────────

def _extract_region(birth_place: str) -> str:
    """Extrahiert die Region (letzter nicht-leerer Teil nach Komma) aus einem Geburtsort."""
    if not birth_place:
        return ""
    parts = [p.strip() for p in birth_place.split(",") if p.strip()]
    if not parts:
        return ""
    # Last part is typically country, second-to-last is region/state
    if len(parts) >= 2:
        return parts[-2].lower()
    return parts[-1].lower()


def _place_sim(a: str, b: str) -> float:
    """0..1 Ortsähnlichkeit: spezifischster Teil (vor erstem Komma) plus
    Überlappung der gesamten Orts-Hierarchie (Kreis/Region/Land).
    Robust gegen unterschiedliche Tiefe ('Schwagstorf' vs 'Schwagstorf, …')
    und gegen verschieden geschriebene Dörfer im selben Kreis."""
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    a0 = a.split(",")[0].strip()
    b0 = b.split(",")[0].strip()
    spec = _name_sim(a0, b0)                 # Ort-Kern (z.B. Schwagstorf)
    # Komponenten-Überlappung über die gesamte Hierarchie: teilen sich zwei
    # Orte Kreis/Region/Land, ist geografische Nähe wahrscheinlich, auch wenn
    # die Dorfnamen abweichen.
    a_comp = {_norm(p) for p in a.split(",") if _norm(p)}
    b_comp = {_norm(p) for p in b.split(",") if _norm(p)}
    if a_comp and b_comp:
        overlap = len(a_comp & b_comp) / min(len(a_comp), len(b_comp))
    else:
        overlap = 0.0
    reg = 1.0 if _extract_region(a) and _extract_region(a) == _extract_region(b) else 0.0
    return max(spec, 0.6 * spec + 0.4 * reg, 0.5 * spec + 0.5 * overlap)
