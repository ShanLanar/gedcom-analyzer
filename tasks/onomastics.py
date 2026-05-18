# -*- coding: utf-8 -*-
"""tasks/onomastics.py – Onomastische Analyse (religiöse / regionale Namensmuster)

Klassifiziert Vornamen nach traditionellen Namenspools (katholisch, protestantisch,
germanisch-vorchristlich, sonstige) und aggregiert pro Region/Epoche, um Muster
in der Verteilung sichtbar zu machen.
"""

from collections import defaultdict

from lib.gedcom import safe_extract_year
from lib.places import extract_country_from_place


# ── Namens-Pools ──────────────────────────────────────────────────────────────

CATHOLIC_NAMES = {
    "MARIA", "ANNA", "MARGARETHA", "MARGARETA", "ELISABETH",
    "KATHARINA", "BARBARA", "JOSEF", "JOSEPH", "ANTON", "FRANZ",
    "IGNATZ", "ALOYSIUS", "PETER", "MICHAEL", "JOHANN",
}

PROTESTANT_NAMES = {
    "FRIEDRICH", "HEINRICH", "WILHELM", "KARL", "GOTTFRIED",
    "GEORG", "ERNST", "AUGUST", "DOROTHEA", "SOPHIE",
    "CHARLOTTE", "LUISE", "WILHELMINE", "JOHANNA",
}

PAGAN_GERMANIC = {
    "WOLFGANG", "SIEGFRIED", "GUNTHER", "HARTMUT", "DETLEF",
    "DIETRICH", "EDITH", "HILDEGARD", "GERTRUD", "BRIGITTE",
}


# ── Epochen ───────────────────────────────────────────────────────────────────

_EPOCHS = [
    ("vor_1800",   None, 1800),
    ("1800-1850",  1800, 1850),
    ("1850-1900",  1850, 1900),
    ("1900-1950",  1900, 1950),
    ("nach_1950",  1950, None),
]


def _epoch_for(year):
    if year is None:
        return None
    for label, lo, hi in _EPOCHS:
        if lo is not None and year < lo:
            continue
        if hi is not None and year >= hi:
            continue
        return label
    return None


_EPOCH_ORDER = {lbl: i for i, (lbl, _, _) in enumerate(_EPOCHS)}


# ── Vornamen-Extraktion / Klassifikation ──────────────────────────────────────

def _first_given_name(name_str: str) -> str:
    """Extrahiert den ersten Vornamen vor '/Nachname/', uppercased."""
    if not name_str:
        return ""
    s = str(name_str)
    # Alles vor dem ersten Slash ist der Vornamenteil
    if "/" in s:
        s = s.split("/", 1)[0]
    s = s.strip()
    if not s:
        return ""
    first = s.split()[0]
    # Punkte/Kommas am Wortende entfernen
    first = first.strip(".,;:()[]'\"")
    return first.upper()


def _classify(first_upper: str) -> str:
    if not first_upper:
        return "sonstige"
    if first_upper in CATHOLIC_NAMES:
        return "katholisch"
    if first_upper in PROTESTANT_NAMES:
        return "protestantisch"
    if first_upper in PAGAN_GERMANIC:
        return "germanisch-vorchristlich"
    return "sonstige"


# ── Haupt-Analyse ─────────────────────────────────────────────────────────────

ONOMASTICS_HEADERS = [
    "Epoche", "Region", "Gesamt",
    "Katholisch %", "Protestantisch %",
    "Germanisch-vorchristlich %", "Sonstige %",
    "Dominante Klasse",
]


def analyze_onomastics(individuals, progress_cb=None, location_data=None) -> list:
    """Aggregiert Namensklassen pro (Epoche, Region).

    Parameters
    ----------
    individuals : dict
    progress_cb : callable
    location_data : dict, optional
        Wird an `extract_country_from_place` weitergereicht.  Wenn None,
        wird ein leeres Dict verwendet (extract_country_from_place ist
        defensiv).
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Onomastik-Analyse …")

    loc = location_data if location_data is not None else {}

    # buckets[(epoch, region)] = {"katholisch": n, "protestantisch": n, ...}
    buckets = defaultdict(lambda: defaultdict(int))

    total = len(individuals)
    for i, (pid, pdata) in enumerate(individuals.items()):
        if i % 5000 == 0 and i > 0:
            p(f"  Onomastik: {i:,}/{total:,} …")

        name = pdata.get("NAME") or ""
        first = _first_given_name(name)
        if not first:
            continue
        klass = _classify(first)

        birt = pdata.get("BIRT") or {}
        year = birt.get("YEAR") or safe_extract_year(birt.get("DATE"))
        epoch = _epoch_for(year)
        if epoch is None:
            continue

        place = birt.get("PLAC") or ""
        country = extract_country_from_place(place, loc) if place else None
        region = country or "unbekannt"

        b = buckets[(epoch, region)]
        b[klass] += 1
        b["__total__"] += 1

    rows = []
    for (epoch, region), counts in buckets.items():
        tot = counts.get("__total__", 0)
        if tot < 5:
            continue
        cath = counts.get("katholisch", 0)
        prot = counts.get("protestantisch", 0)
        germ = counts.get("germanisch-vorchristlich", 0)
        sons = counts.get("sonstige", 0)

        def pct(n):
            return round((n / tot) * 100.0, 1) if tot else 0.0

        shares = {
            "Katholisch": cath,
            "Protestantisch": prot,
            "Germanisch-vorchristlich": germ,
            "Sonstige": sons,
        }
        dominant = max(shares.items(), key=lambda kv: kv[1])[0]

        rows.append([
            epoch, region, tot,
            pct(cath), pct(prot), pct(germ), pct(sons),
            dominant,
        ])

    rows.sort(key=lambda r: (_EPOCH_ORDER.get(r[0], 99), -r[2]))
    p(f"Onomastik: {len(rows):,} Zeilen", tag="ok")
    return rows
