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


def _given_tokens(given: str) -> set:
    return {t for t in _norm(given).split() if t and len(t) > 1}


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


# ── Eigenen Baum laden ──────────────────────────────────────────────────────

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


def load_gedcom_full(gedcom_path: str):
    """Lädt GEDCOM → (people, individuals, families).
    people = Person-Objekte für den Abgleich; individuals/families = Rohdaten
    für die Ahnenlinien-Berechnung (Sosa)."""
    from lib.gedcom import robust_load_gedcom
    individuals, families = robust_load_gedcom(gedcom_path)
    people = []
    for iid, ind in individuals.items():
        p = _person_from_indi(iid, ind)
        if p is not None:
            people.append(p)
    log.info("Eigener Baum geladen: %d Personen aus %s",
             len(people), os.path.basename(gedcom_path))
    return people, individuals, families


def load_own_tree(gedcom_path: str) -> list:
    """Nur die Person-Liste (Rückwärtskompatibel)."""
    people, _i, _f = load_gedcom_full(gedcom_path)
    return people


def build_ancestor_map(root_id: str, individuals: dict, families: dict) -> dict:
    """{iid: F/M-Pfad ab Wurzel} für alle Vorfahren der Wurzelperson.
    '' = Wurzel selbst, 'F' = Vater, 'FM' = Großmutter väterl. usw."""
    if not root_id or root_id not in individuals:
        return {}
    amap = {}
    stack = [(root_id, "")]
    while stack:
        iid, path = stack.pop()
        if iid in amap:
            continue
        amap[iid] = path
        for fc in (individuals.get(iid, {}).get("FAMC") or []):
            fam = families.get(fc) or {}
            father, mother = fam.get("HUSB"), fam.get("WIFE")
            if father:
                stack.append((father, path + "F"))
            if mother:
                stack.append((mother, path + "M"))
    return amap


def render_kinship(path: str) -> str:
    """F/M-Pfad → lesbare deutsche Verwandtschaftsbezeichnung."""
    g = len(path)
    if g == 0:
        return "Wurzelperson (du)"
    male = path[-1] == "F"
    side = "väterlicherseits" if path[0] == "F" else "mütterlicherseits"
    if g == 1:
        return "Vater" if male else "Mutter"
    if g == 2:
        return ("Großvater" if male else "Großmutter") + " " + side
    base = "Urgroßvater" if male else "Urgroßmutter"
    label = ("Ur-" * (g - 3)) + base
    return label + " " + side


def endogamy_flag(total_cm: float, num_segments: int, longest: float):
    """Schätzt aus Segmentdaten, ob Endogamie/mehrere Linien vorliegen.
    Viele kleine Segmente bei moderater Gesamt-cM = mehrere geteilte Ahnenlinien.
    Ein großes längstes Segment = jüngerer gemeinsamer Vorfahr (eine klare Linie).
    Liefert (label, score 0..1) – score hoch = Endogamie wahrscheinlich."""
    total_cm = total_cm or 0
    num = num_segments or 0
    longest = longest or 0
    if num <= 0:
        return "unbekannt", 0.0
    avg = total_cm / num
    score = 0.0
    # viele Segmente, aber im Schnitt klein → typische Endogamie-Signatur
    if num >= 4 and avg < 12:
        score += 0.5
    if num >= 7 and longest < 15:
        score += 0.3
    if total_cm < 90 and num >= 5:
        score += 0.2
    # großes längstes Segment spricht GEGEN Endogamie (jüngere, klare Linie)
    if longest >= 30:
        score -= 0.4
    score = max(0.0, min(score, 1.0))
    label = ("Endogamie wahrscheinlich" if score >= 0.6 else
             "Endogamie möglich" if score >= 0.3 else
             "eher eine klare Linie")
    return label, round(score, 2)


def longest_to_generation(longest: float):
    """Grobe Generation des gemeinsamen Vorfahren aus dem längsten Segment
    (endogamie-robuster als Gesamt-cM). Wurzel=Gen 1."""
    l = longest or 0
    for thr, gen in [(90, 3), (50, 4), (30, 5), (18, 6), (12, 7), (0, 8)]:
        if l >= thr:
            return gen
    return 8


def cluster_confidence(size: int, density: float, median_cm: float = 0.0,
                       conv_frac: float = None, endogamy_score: float = 0.0):
    """Bewertet einen Cluster. Liefert dict mit:
      realness  – P(Cluster ist echt, kein Zufall) 0..1 (Größe × Dichte)
      cohesion  – Dichte (eine Linie vs. mehrere verschmolzen)
      conv      – Anteil Mitglieder, die auf denselben Vorfahren konvergieren
      label, note.
    Mitglieder sind NICHT unabhängig – darum dominiert die gegenseitige
    Vernetzung (Dichte), nicht die bloße Anzahl.

    Kombination per Noisy-OR: realness = 1 − ∏(1 − pᵢ) über die UNABHÄNGIGEN
    Evidenzquellen (1) Struktur=Größe×Dichte und (2) cM-Höhe. Innerhalb des
    Clusters wird NICHT pro Mitglied multipliziert (keine Unabhängigkeit) –
    die Größe geht dichte-gewichtet als 'effektive Bestätigungen' ein."""
    size = max(size, 1)
    d = max(0.0, min(density or 0.0, 1.0))
    # (1) Strukturelle Evidenz: effektive Bestätigungen ~ Größe × Dichte
    eff = 1 + (size - 1) * max(d, 0.25)
    p_struct = 1 - 0.5 ** eff
    # (2) cM-Evidenz: hohe cM ⇒ Mitglied praktisch sicher echt (kein IBC-Zufall)
    cm = median_cm or 0
    p_cm = 1 - 0.5 ** (cm / 18.0)          # 18cM→0.5, 36→0.75, 54→0.875, 90→0.97
    # Noisy-OR der unabhängigen Quellen
    realness = 1 - (1 - p_struct) * (1 - p_cm)
    if realness >= 0.97:
        label = "sehr hoch"
    elif realness >= 0.85:
        label = "hoch"
    elif realness >= 0.6:
        label = "mittel"
    else:
        label = "niedrig"
    note = ""
    if cm and cm < 15:
        note = "niedrige cM → je Mitglied erhöhtes False-Positive-Risiko (IBC)"
    elif endogamy_score and endogamy_score >= 0.6:
        note = "viele kleine Segmente → Endogamie wahrscheinlich (mehrere Linien)"
    elif d < 0.3 and size >= 6:
        note = "lose vernetzt → evtl. mehrere Linien verschmolzen (Endogamie?)"
    elif conv_frac is not None and conv_frac < 0.4 and size >= 4:
        note = "geringe Pedigree-Konvergenz → Vorhersage unsicher"
    return {"realness": realness, "cohesion": d, "conv": conv_frac,
            "label": label, "note": note, "endogamy": endogamy_score}


def cm_to_mrca(cm: float):
    """Schätzt aus geteilten cM die Beziehung und die Pedigree-Generation des
    gemeinsamen Vorfahren (Wurzel=Gen 1). Basiert auf Shared-cM-Project-Mittelwerten.
    ACHTUNG: Endogamie erhöht cM → echte Verwandtschaft eher ENTFERNTER (= tiefer).
    Liefert (label, gen). gen = erwartete Generation des gemeinsamen Vorfahren."""
    c = cm or 0
    table = [
        (1300, "Großeltern-/Onkel-/Tante-Ebene", 2),
        (575,  "1. Cousin (gem. Großeltern)",     3),
        (300,  "1C1R / 2. Cousin",                 4),
        (140,  "2. Cousin (gem. Urgroßeltern)",    4),
        (75,   "2C1R / 3. Cousin",                 5),
        (45,   "3. Cousin (gem. Ur-Urgroßeltern)", 5),
        (28,   "4. Cousin (gem. 3×-Urgroßeltern)", 6),
        (18,   "4.–5. Cousin",                     7),
        (10,   "5.–6. Cousin",                     8),
        (0,    "entfernt (≥6. Cousin)",            9),
    ]
    for thr, label, gen in table:
        if c >= thr:
            return label, gen
    return "unbekannt", 9


def merge_person_list(persons: list, thresh: float = 0.72) -> list:
    """Verschmilzt überlappende Personen (Schreibvarianten) zu kanonischen Gruppen.
    persons: Person-Objekte (ref trägt Herkunft). Liefert
    [{'rep':Person, 'items':[Person,...]}] – je Gruppe = eine reale Person."""
    groups = []
    by_pre = {}  # Nachnamen-Präfix[:4] -> Liste Gruppen-Indizes
    for p in persons:
        cand = set()
        for t in p.stoks:
            if len(t) >= 3:
                for gi in by_pre.get(t[:4], ()):
                    cand.add(gi)
        best_gi, best_s = None, thresh
        for gi in cand:
            s = fuzzy_score(p, groups[gi]["rep"])
            if s >= best_s:
                best_s, best_gi = s, gi
        if best_gi is None:
            gi = len(groups)
            groups.append({"rep": p, "items": [p]})
            for t in p.stoks:
                if len(t) >= 3:
                    by_pre.setdefault(t[:4], []).append(gi)
        else:
            groups[best_gi]["items"].append(p)
            # längeren Namen als Repräsentant bevorzugen
            if len(p.display) > len(groups[best_gi]["rep"].display):
                groups[best_gi]["rep"] = p
    return groups


def find_root_candidate(people: list, name_query: str):
    """Findet die wahrscheinlichste Wurzelperson per Namenssuche. (ref, score)."""
    if not name_query:
        return None, 0.0
    q = Person(name_query, "", None, "")
    # Wenn der Query einen Nachnamen enthält, besser aufteilen:
    parts = name_query.strip().rsplit(" ", 1)
    if len(parts) == 2:
        q = Person(parts[0], parts[1], None, "")
    best, best_s = None, 0.0
    for p in people:
        s = fuzzy_score(q, p, year_tol=200)
        if s > best_s:
            best, best_s = p, s
    return (best.ref if best else None), best_s


# ── Index für schnellen Abgleich ────────────────────────────────────────────

class TreeIndex:
    """Indiziert den eigenen Baum für schnelles Matching.
    Schlüssel: (Nachnamen-Token-Präfix[:4], Geburtsjahr) – das schrumpft die
    Kandidatenmenge drastisch (sonst quadratische Laufzeit bei großen Bäumen)."""

    def __init__(self, people: list):
        self.people = people
        self._buckets: dict = {}
        for p in people:
            yr = int(p.year) if p.year else None
            for key in self._keys(p.stoks, yr):
                self._buckets.setdefault(key, []).append(p)

    @staticmethod
    def _keys(stoks: set, year):
        """Schlüssel pro Person: jedes Nachnamen-Präfix × tatsächliches Jahr
        (oder None, wenn jahrlos). NICHT zusätzlich None setzen, sonst bläht
        sich der None-Bucket auf alle Personen auf."""
        out = set()
        y = year if year else None
        for t in stoks:
            if len(t) >= 3:
                out.add((t[:4], y))
        return out

    def _candidate_keys(self, q: "Person", year_tol: int = 3):
        out = set()
        if q.year:
            qy = int(q.year)
            years = list(range(qy - year_tol, qy + year_tol + 1)) + [None]
        else:
            years = [None]
        for t in q.stoks:
            if len(t) >= 3:
                pre = t[:4]
                for y in years:
                    out.add((pre, y))
        return out

    def best_match(self, q: "Person", min_score: float = 0.6):
        """Beste(r) Treffer im eigenen Baum für Person q. Liefert (Person, score)."""
        cands = set()
        for key in self._candidate_keys(q):
            bucket = self._buckets.get(key)
            if bucket:
                cands.update(bucket)
        best, best_s = None, 0.0
        for p in cands:
            s = fuzzy_score(q, p)
            if s > best_s:
                best, best_s = p, s
                if best_s >= 0.99:
                    break
        if best and best_s >= min_score:
            return best, best_s
        return None, 0.0
