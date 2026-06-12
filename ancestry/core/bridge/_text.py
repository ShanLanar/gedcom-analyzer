"""
_text.py — Normalisierung, Phonetik und String-Distanzen für das Bridge-Modul.
"""

import re
import unicodedata
from difflib import SequenceMatcher


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


def _name_sim(a: str, b: str) -> float:
    """0..1 Ähnlichkeit zweier Namen: kombiniert SequenceMatcher-Ratio und
    längen-normierte Levenshtein-Distanz."""
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    lev = _lev(a, b, cap=max(len(a), len(b)))
    lev_sim = 1.0 - lev / max(len(a), len(b))
    return max(seq, lev_sim)


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
    """0..1 Ortsähnlichkeit: spezifischster Teil (vor erstem Komma) plus Region.
    Robust gegen unterschiedliche Tiefe ('Schwagstorf' vs 'Schwagstorf, …')."""
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    a0 = a.split(",")[0].strip()
    b0 = b.split(",")[0].strip()
    spec = _name_sim(a0, b0)                 # Ort-Kern (z.B. Schwagstorf)
    reg  = 1.0 if _extract_region(a) and _extract_region(a) == _extract_region(b) else 0.0
    return max(spec, 0.6 * spec + 0.4 * reg)
