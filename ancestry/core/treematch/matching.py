"""
Matching-Algorithmen: Personen-Listen zusammenführen, Wurzelkandidaten finden,
schneller Baum-Index für Abgleich.

Enthält: merge_person_list, find_root_candidate, TreeIndex.
"""

from ._persons import Person, fuzzy_score


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
