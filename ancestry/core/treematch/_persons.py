"""
Personen-Datenmodell und Text-Normalisierungshelfer für Tree-Matching.

Enthält: _strip_accents, _norm, _tok_ratio, _fuzzy_overlap, _surname_tokens,
_canon_given, _given_tokens, Person, fuzzy_score, _parse_name, _person_from_indi.
"""

import re
import unicodedata
from difflib import SequenceMatcher

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
    plus die Zahl der Treffer. Exakte Treffer zuerst (ohne SequenceMatcher),
    nur der Rest wird unscharf verglichen."""
    if not toks_a or not toks_b:
        return 0.0, 0
    exact = toks_a & toks_b
    hits = len(exact)
    rem_a = toks_a - exact
    rem_b = toks_b - exact
    if rem_a and rem_b:
        for a in rem_a:
            if any(_tok_ratio(a, b) >= thresh for b in rem_b):
                hits += 1
    denom = max(len(toks_a), len(toks_b))
    return hits / denom, hits


def _surname_tokens(surname: str) -> set:
    """Nachnamen-Tokens; 'Rustmeier gen Quade' → {rustmeier, quade}."""
    s = _norm(surname)
    s = re.sub(r"\b(gen|genannt|gnt|or|oder)\b", " ", s)
    return {t for t in s.split() if t and t not in _STOP and len(t) > 1}


# Deutsch↔Englisch (anglisierte Auswanderer-Vornamen) → gemeinsame Kanon-Form.
_NAME_EQUIV_GROUPS = [
    ("heinrich", "henry", "harry", "hank"),
    ("wilhelm", "william", "will", "willie", "bill"),
    ("johann", "johannes", "john", "johan", "john", "jack"),
    ("friedrich", "frederick", "fred", "frederic", "fritz"),
    ("karl", "carl", "charles", "charlie", "chuck"),
    ("ludwig", "louis", "lewis", "lou"),
    ("georg", "george"),
    ("jakob", "jacob", "jake"),
    ("franz", "frank", "francis"),
    ("ernst", "ernest", "ernie"),
    ("hermann", "herman"),
    ("august", "augustus", "gus"),
    ("gottlieb", "godlove"),
    ("gottfried", "godfrey"),
    ("bernhard", "bernard", "barney"),
    ("albrecht", "albert", "al"),
    ("conrad", "konrad"),
    ("theodor", "theodore", "ted"),
    ("rudolf", "rudolph", "rudy"),
    ("adolf", "adolph"),
    ("gustav", "gustave", "gustaf"),
    ("anna", "anne", "ann", "annie"),
    ("maria", "mary", "marie", "maja"),
    ("margarethe", "margaretha", "margaret", "margarete", "maggie", "greta"),
    ("elisabeth", "elizabeth", "lisbeth", "betty", "liz", "elise"),
    ("katharina", "catherine", "katherine", "kathryn", "kate", "katie"),
    ("dorothea", "dorothy", "dora"),
    ("sophie", "sophia", "sophy"),
    ("wilhelmine", "wilma", "minnie"),
    ("caroline", "karoline", "carolina", "carrie"),
    ("luise", "louise", "luisa"),
    ("auguste", "augusta"),
    ("henriette", "harriet"),
    ("friederike", "frederica"),
    ("christine", "christina", "christiane", "tina"),
    ("magdalena", "magdalene", "lena"),
]
_NAME_CANON = {v: grp[0] for grp in _NAME_EQUIV_GROUPS for v in grp}


def _canon_given(tok: str) -> str:
    return _NAME_CANON.get(tok, tok)


def _given_tokens(given: str) -> set:
    return {_canon_given(t) for t in _norm(given).split() if t and len(t) > 1}


# ── Personen-Schlüssel ──────────────────────────────────────────────────────

class Person:
    __slots__ = ("given", "surname", "year", "place", "bdate",
                 "gtoks", "stoks", "ref")

    def __init__(self, given, surname, year, place, ref=None, bdate=""):
        self.given = given or ""
        self.surname = surname or ""
        self.year = year
        self.place = place or ""
        self.bdate = bdate or ""      # volles Geburtsdatum, falls vorhanden
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

    # Vorname: Rufname-tauglich – ist der kürzere Namenssatz im längeren
    # enthalten (z.B. 'Friedrich' ⊂ 'Heinrich Friedrich Wilhelm'), zählt das stark.
    if a.gtoks and b.gtoks:
        _, g_hits = _fuzzy_overlap(a.gtoks, b.gtoks)
        g_overlap = g_hits / min(len(a.gtoks), len(b.gtoks))
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


# ── GEDCOM-Namens-Parser ────────────────────────────────────────────────────

def _parse_name(raw: str, givn: str, surn: str):
    """Liefert (given, surname) aus GEDCOM-NAME ('Vorname /Nachname/') o. GIVN/SURN."""
    if givn or surn:
        return (givn or "").strip(), (surn or "").strip()
    raw = raw or ""
    m = re.search(r"/([^/]*)/", raw)
    if m:
        surname = m.group(1).strip()
        # Vorname = NUR der Teil VOR dem Nachnamen. Den Teil danach (Suffix wie
        # 'Jr.' oder Forschungssymbole ‼/✠) NICHT an den Vornamen hängen, sonst
        # erscheint er fälschlich vor dem Nachnamen.
        given = raw[:m.start()].strip()
        return given, surname
    parts = raw.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (raw, "")


def _person_from_indi(iid, ind):
    given, surname = _parse_name(ind.get("NAME"),
                                 ind.get("_GIVN"), ind.get("_SURN"))
    birt = ind.get("BIRT") or {}
    place = birt.get("PLAC") or ind.get("BIRTH_PLACE") or ""
    if not (given or surname):
        return None
    return Person(given, surname, birt.get("YEAR"), place, ref=iid)
