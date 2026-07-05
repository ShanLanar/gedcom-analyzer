"""
X-Chromosom-Vererbungs-Fächer.

Das X folgt nicht dem autosomalen Erbgang. Damit lässt sich — allein aus dem
Geschlecht des Testers — die Menge der Ahnen bestimmen, die überhaupt X-DNA
beigetragen haben können. Das grenzt die in Frage kommenden Linien für einen
X-DNA-Match drastisch ein (der X-Ahnenpool ist klein).

Regeln:
  * Ein Mann (XY) erbt sein X nur von der Mutter → keine X-DNA vom Vater.
  * Eine Frau (XX) erbt X von beiden Eltern; ihr väterliches X stammt aber
    vollständig von der Großmutter väterlicherseits (der Vater gibt sein
    einziges — von seiner Mutter geerbtes — X unverändert weiter).
  * Kurz: kein Mann erbt X von seinem Vater. Auf keinem gültigen X-Pfad dürfen
    zwei „Väter" hintereinander stehen (Vater→dessen Vater bricht die X-Linie).

Die Zahl der X-Ahnen je Generation folgt der Fibonacci-Folge.

Sosa-Stradonitz-Nummerierung: 1 = Testperson, 2 = Vater, 3 = Mutter,
2n = Vater von n, 2n+1 = Mutter von n. Für Sosa ≥ 2 gilt: gerade = männlich,
ungerade = weiblich.
"""
from __future__ import annotations

from functools import lru_cache


def _sosa_is_male(sosa: int, tester_sex: str) -> bool:
    """Geschlecht der Person an einer Sosa-Position."""
    if sosa == 1:
        return tester_sex.upper().startswith("M")
    return sosa % 2 == 0          # gerade = Vater(sseite) = männlich


@lru_cache(maxsize=None)
def _is_x_ancestor(sosa: int, tester_sex: str) -> bool:
    if sosa < 1:
        return False
    if sosa == 1:
        return True                # die Testperson selbst
    child = sosa // 2              # wessen Elternteil diese Position ist
    if not _is_x_ancestor(child, tester_sex):
        return False               # X-Linie ist schon oberhalb gebrochen
    child_is_male = _sosa_is_male(child, tester_sex)
    this_is_father = (sosa % 2 == 0)   # gerade Sosa = Vater des Kindes
    # Ein männliches Kind erbt KEIN X von seinem Vater → dieser Pfad bricht.
    return not (child_is_male and this_is_father)


def is_x_ancestor(sosa: int, tester_sex: str) -> bool:
    """True, wenn die Ahnenposition (Sosa) X-DNA zur Testperson beitragen kann.

    tester_sex: 'M'/'männlich'/'male' oder 'F'/'W'/'weiblich'/'female'.
    """
    s = (tester_sex or "").strip().upper()
    sex = "M" if s.startswith("M") else "F"   # W/F/weiblich/female → F
    return _is_x_ancestor(int(sosa), sex)


def x_ancestor_sosa(tester_sex: str, max_gen: int) -> set[int]:
    """Menge aller X-tragenden Sosa-Nummern bis einschließlich Generation max_gen.

    Generation 1 = Testperson (Sosa 1), Gen 2 = Eltern (Sosa 2–3),
    Gen g = Sosa 2^(g-1) … 2^g − 1.
    """
    result: set[int] = set()
    for g in range(1, max_gen + 1):
        for sosa in range(2 ** (g - 1), 2 ** g):
            if is_x_ancestor(sosa, tester_sex):
                result.add(sosa)
    return result


def x_ancestor_count_per_gen(tester_sex: str, max_gen: int) -> list[int]:
    """X-Ahnenzahl je Generation (folgt der Fibonacci-Folge)."""
    fan = x_ancestor_sosa(tester_sex, max_gen)
    counts = []
    for g in range(1, max_gen + 1):
        counts.append(sum(1 for s in fan if 2 ** (g - 1) <= s < 2 ** g))
    return counts
