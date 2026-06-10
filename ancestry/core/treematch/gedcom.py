"""
GEDCOM-Lader und Ahnenlinien-Funktionen.

Enthält: load_gedcom_full, load_own_tree, build_ancestor_map,
mrca_on_direct_line, render_kinship.
"""

import os
import logging

from ._persons import _person_from_indi

log = logging.getLogger(__name__)


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
    n = g - 2                       # Anzahl "Ur" (g3=1, g4=2, …)
    if n >= 4:
        label = f"{n}×{base}"       # kompakt, z.B. '5×Urgroßvater'
    else:
        label = ("Ur-" * (n - 1)) + base
    return label + " " + side


def mrca_on_direct_line(iid: str, individuals: dict, families: dict,
                        amap: dict, max_up: int = 14):
    """Klettert von einer (Seitenlinien-)Person im GEDCOM nach oben, bis sie auf
    die direkte Ahnenlinie (amap) der Wurzelperson trifft = gemeinsamer Vorfahr.
    Liefert (mrca_iid, pfad) oder (None, None)."""
    from collections import deque
    if not iid:
        return None, None
    seen = set()
    q = deque([(iid, 0)])
    while q:
        cur, depth = q.popleft()
        if cur in seen or depth > max_up:
            continue
        seen.add(cur)
        if cur in amap:
            return cur, amap[cur]
        for fc in (individuals.get(cur, {}).get("FAMC") or []):
            fam = families.get(fc) or {}
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par:
                    q.append((par, depth + 1))
    return None, None
