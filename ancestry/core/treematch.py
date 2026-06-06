"""
Tree-Matching: gleicht die Ahnentafeln der DNA-Matches gegen den EIGENEN
Stammbaum (GEDCOM) ab und findet so den Anknüpfungspunkt – auch dann, wenn
Ancestry selbst keinen gemeinsamen Vorfahren erkannt hat.

Enthält zugleich die Fuzzy-/Duplikaterkennung für ungenaue Personendaten
(unterschiedliche Schreibweisen, Rufname-in-Großbuchstaben, leichte
Jahresabweichungen, "genannt"-Namen usw.).
"""

import os
import re
import sys
import unicodedata
import logging
from difflib import SequenceMatcher

log = logging.getLogger(__name__)

# Root des Repos in den Pfad, um den vorhandenen GEDCOM-Parser zu nutzen.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Normalisierung ──────────────────────────────────────────────────────────

_STOP = {"von", "van", "de", "der", "den", "zu", "zum", "zur", "the", "of"}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _norm(s: str) -> str:
    s = (s or "").lower().replace("ß", "ss")
    s = _strip_accents(s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tok_ratio(a: str, b: str) -> float:
    """Ähnlichkeit zweier Tokens (0..1). Fängt Schreibvarianten ab."""
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _fuzzy_overlap(toks_a: set, toks_b: set, thresh: float = 0.82):
    """Anteil von toks_a, die in toks_b einen ähnlichen Partner haben (0..1),
    plus die Zahl der Treffer. Toleriert Tippfehler/Varianten."""
    if not toks_a or not toks_b:
        return 0.0, 0
    hits = 0
    for a in toks_a:
        if any(_tok_ratio(a, b) >= thresh for b in toks_b):
            hits += 1
    denom = max(len(toks_a), len(toks_b))
    return hits / denom, hits


def _surname_tokens(surname: str) -> set:
    """Nachnamen-Tokens; 'Rustmeier gen Quade' → {rustmeier, quade}."""
    s = _norm(surname)
    s = re.sub(r"\b(gen|genannt|gnt|or|oder)\b", " ", s)
    return {t for t in s.split() if t and t not in _STOP and len(t) > 1}


def _given_tokens(given: str) -> set:
    return {t for t in _norm(given).split() if t and len(t) > 1}


# ── Personen-Schlüssel ──────────────────────────────────────────────────────

class Person:
    __slots__ = ("given", "surname", "year", "place", "gtoks", "stoks", "ref")

    def __init__(self, given, surname, year, place, ref=None):
        self.given = given or ""
        self.surname = surname or ""
        self.year = year
        self.place = place or ""
        self.gtoks = _given_tokens(self.given)
        self.stoks = _surname_tokens(self.surname)
        self.ref = ref

    @property
    def display(self):
        return (self.given + " " + self.surname).strip()


def fuzzy_score(a: "Person", b: "Person", year_tol: int = 3) -> float:
    """0..1 Ähnlichkeit zweier Personen. >=0.6 gilt als (möglicher) Treffer."""
    if not a.stoks or not b.stoks:
        return 0.0
    # Nachname: mindestens ein ähnliches Token nötig (toleriert Varianten)
    s_overlap, s_hits = _fuzzy_overlap(a.stoks, b.stoks)
    if s_hits == 0:
        return 0.0

    # Vorname: unscharfe Token-Überlappung (Rufname reicht)
    if a.gtoks and b.gtoks:
        g_overlap, _ = _fuzzy_overlap(a.gtoks, b.gtoks)
    else:
        g_overlap = 0.4  # ein Vorname fehlt → neutral-leicht

    # Jahr
    if a.year and b.year:
        diff = abs(int(a.year) - int(b.year))
        if diff == 0:
            y = 1.0
        elif diff <= year_tol:
            y = 1.0 - diff / (year_tol + 1)
        else:
            return 0.0  # Jahr zu weit auseinander → kein Treffer
    else:
        y = 0.5  # ein Jahr fehlt → neutral

    # Gewichtung: Nachname 0.4, Vorname 0.35, Jahr 0.25
    return round(0.4 * s_overlap + 0.35 * g_overlap + 0.25 * y, 3)


# ── Eigenen Baum laden ──────────────────────────────────────────────────────

def _parse_name(raw: str, givn: str, surn: str):
    """Liefert (given, surname) aus GEDCOM-NAME ('Vorname /Nachname/') o. GIVN/SURN."""
    if givn or surn:
        return (givn or "").strip(), (surn or "").strip()
    raw = raw or ""
    m = re.search(r"/([^/]*)/", raw)
    if m:
        surname = m.group(1).strip()
        given = (raw[:m.start()] + raw[m.end():]).strip()
        return given, surname
    parts = raw.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (raw, "")


def load_own_tree(gedcom_path: str) -> list:
    """Lädt alle Personen des eigenen GEDCOM als Person-Objekte (für Abgleich)."""
    from lib.gedcom import robust_load_gedcom
    individuals, _families = robust_load_gedcom(gedcom_path)
    people = []
    for iid, ind in individuals.items():
        given, surname = _parse_name(ind.get("NAME"),
                                     ind.get("_GIVN"), ind.get("_SURN"))
        birt = ind.get("BIRT") or {}
        year = birt.get("YEAR")
        place = birt.get("PLAC") or ind.get("BIRTH_PLACE") or ""
        if not (given or surname):
            continue
        people.append(Person(given, surname, year, place, ref=iid))
    log.info("Eigener Baum geladen: %d Personen aus %s",
             len(people), os.path.basename(gedcom_path))
    return people


# ── Index für schnellen Abgleich ────────────────────────────────────────────

class TreeIndex:
    """Indiziert den eigenen Baum nach Nachnamen-Token für schnelles Matching."""

    def __init__(self, people: list):
        self.people = people
        # Bucket nach Nachnamen-Token-Präfix (3 Zeichen) → fängt Schreibvarianten.
        self._buckets: dict = {}
        for p in people:
            for key in self._keys(p.stoks):
                self._buckets.setdefault(key, []).append(p)

    @staticmethod
    def _keys(stoks: set) -> set:
        return {t[:3] for t in stoks if len(t) >= 3}

    def best_match(self, q: "Person", min_score: float = 0.6):
        """Beste(r) Treffer im eigenen Baum für Person q. Liefert (Person, score)."""
        cands = set()
        for key in self._keys(q.stoks):
            for p in self._buckets.get(key, ()):
                cands.add(p)
        best, best_s = None, 0.0
        for p in cands:
            s = fuzzy_score(q, p)
            if s > best_s:
                best, best_s = p, s
        if best and best_s >= min_score:
            return best, best_s
        return None, 0.0
