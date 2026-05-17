# -*- coding: utf-8 -*-
"""tasks/spatial.py – Räumliche Analysen: Heiratsmigration, Lebens-Triangulation,
Sesshaftigkeit, Nachnamen-Region-Matrix."""

from collections import Counter, defaultdict
from lib.gedcom import safe_extract_year
from lib.places import extract_country_from_place, format_place_for_display
from lib.helpers import safe_extract_family_name


MAX_ROWS = 50_000


def _first_token(place: str) -> str:
    if not place:
        return ""
    return place.split(",")[0].strip()


# ── Heiratsmigration ───────────────────────────────────────────────────────────

MARRIAGE_MIGRATION_HEADERS = [
    "Familie-ID", "Frau", "Frau-Geburtsort", "Mann", "Mann-Geburtsort",
    "Heiratsort", "Heiratsjahr", "Klassifikation"
]


def analyze_marriage_migration(individuals, families, location_data,
                                progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Heiratsmigration analysieren …")

    rows = []
    for fid, fam in families.items():
        wife_id = fam.get("WIFE")
        husb_id = fam.get("HUSB")
        if not wife_id or wife_id not in individuals:
            continue
        wife = individuals[wife_id]
        husb = individuals.get(husb_id, {}) if husb_id else {}

        wife_birth = (wife.get("BIRT") or {}).get("PLAC", "") or wife.get("BIRTH_PLACE", "")
        husb_birth = (husb.get("BIRT") or {}).get("PLAC", "") or husb.get("BIRTH_PLACE", "")
        marr_place = fam.get("MARR_PLACE", "") or ""
        marr_year = safe_extract_year(fam.get("MARR_DATE"))

        if not wife_birth or not marr_place:
            classification = "Unbekannt"
        else:
            wife_city = _first_token(wife_birth).lower()
            marr_city = _first_token(marr_place).lower()
            wife_country = extract_country_from_place(wife_birth, location_data)
            marr_country = extract_country_from_place(marr_place, location_data)
            if wife_city and wife_city == marr_city:
                classification = "Lokal"
            elif wife_country and marr_country and wife_country == marr_country:
                classification = "Region"
            elif wife_country and marr_country and wife_country != marr_country:
                classification = "Land"
            else:
                classification = "Unbekannt"

        rows.append([
            fid,
            (wife.get("NAME") or "")[:60],
            format_place_for_display(wife_birth) if wife_birth else "",
            (husb.get("NAME") or "")[:60],
            format_place_for_display(husb_birth) if husb_birth else "",
            format_place_for_display(marr_place) if marr_place else "",
            marr_year or "",
            classification,
        ])

        if len(rows) >= MAX_ROWS:
            break

    p(f"Heiratsmigration: {len(rows)} Familien", tag="ok")
    return rows


# ── Lebens-Triangulation ───────────────────────────────────────────────────────

LIFE_TRIANGULATION_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr", "Geburtsort", "Heiratsort",
    "Sterbeort", "Klassifikation"
]


def analyze_life_triangulation(individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Lebens-Triangulation analysieren …")

    rows = []
    for pid, pdata in individuals.items():
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        birth_place = birt.get("PLAC", "")
        death_place = deat.get("PLAC", "")
        if not birth_place or not death_place:
            continue

        marr_place = ""
        fams = pdata.get("FAMS", [])
        if fams:
            first_fam = families.get(fams[0], {})
            marr_place = first_fam.get("MARR_PLACE", "") or ""

        cities = {_first_token(birth_place).lower()}
        countries = set()
        for pl in (birth_place, marr_place, death_place):
            if pl:
                cities.add(_first_token(pl).lower())
        cities.discard("")

        for pl in (birth_place, marr_place, death_place):
            if pl:
                tokens = [t.strip() for t in pl.split(",") if t.strip()]
                if tokens:
                    countries.add(tokens[-1].lower())

        if len(cities) == 1:
            classification = "Sesshaft"
        elif len(countries) <= 1:
            classification = "Regional"
        else:
            classification = "Übergreifend"

        birth_year = safe_extract_year(birt.get("DATE"))

        rows.append([
            pid,
            (pdata.get("NAME") or "")[:60],
            birth_year or "",
            format_place_for_display(birth_place),
            format_place_for_display(marr_place) if marr_place else "",
            format_place_for_display(death_place),
            classification,
        ])

        if len(rows) >= MAX_ROWS:
            break

    p(f"Lebens-Triangulation: {len(rows)} Personen", tag="ok")
    return rows


# ── Sesshaftigkeit ─────────────────────────────────────────────────────────────

SEDENTARINESS_HEADERS = [
    "Familie-ID", "Eltern", "Heiratsjahr", "Anzahl Kinder",
    "Distinkte Geburtsorte", "Sesshaftigkeit-Score", "Hauptort"
]


def analyze_sedentariness(individuals, families, root_id, location_data,
                           max_depth=8, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Sesshaftigkeit analysieren …")

    rows = []
    for fid, fam in families.items():
        husb_id = fam.get("HUSB")
        wife_id = fam.get("WIFE")
        children = fam.get("CHIL", [])

        places = []
        for pid in (husb_id, wife_id, *children):
            if not pid or pid not in individuals:
                continue
            bp = (individuals[pid].get("BIRT") or {}).get("PLAC", "")
            if bp:
                places.append(_first_token(bp))

        if not places:
            continue

        city_counter = Counter(c.lower() for c in places if c)
        distinct = len(city_counter)
        score = 1.0 / (distinct + 1)
        main_city, _main_count = city_counter.most_common(1)[0]

        husb_name = (individuals.get(husb_id, {}).get("NAME") or "")[:40] if husb_id else ""
        wife_name = (individuals.get(wife_id, {}).get("NAME") or "")[:40] if wife_id else ""
        parents = f"{husb_name} & {wife_name}".strip(" &")

        marr_year = safe_extract_year(fam.get("MARR_DATE"))

        # Display the main city in original casing (find first match).
        main_display = next((c for c in places if c.lower() == main_city), main_city)

        rows.append([
            fid,
            parents,
            marr_year or "",
            len(children),
            distinct,
            round(score, 4),
            main_display,
        ])

        if len(rows) >= MAX_ROWS:
            break

    rows.sort(key=lambda r: r[5], reverse=True)
    p(f"Sesshaftigkeit: {len(rows)} Familien", tag="ok")
    return rows


# ── Nachnamen-Region-Matrix ────────────────────────────────────────────────────

SURNAME_REGION_HEADERS = [
    "Nachname", "Land", "Anzahl", "Jahres-Spanne",
    "Anteil dieses Nachnamens in diesem Land %"
]


def analyze_surname_region_matrix(individuals, location_data,
                                   progress_cb=None, top_surnames=50) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Nachnamen-Region-Matrix analysieren …")

    surname_total = Counter()
    pair_counts = defaultdict(int)
    pair_years = defaultdict(list)

    for pid, pdata in individuals.items():
        surname = (safe_extract_family_name(pdata.get("NAME", "")) or "").strip()
        if len(surname) < 2:
            continue
        bp = (pdata.get("BIRT") or {}).get("PLAC", "")
        country = extract_country_from_place(bp, location_data) if bp else None
        if not country:
            continue
        surname_total[surname] += 1
        key = (surname, country)
        pair_counts[key] += 1
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if by:
            pair_years[key].append(by)

    top = {s for s, _ in surname_total.most_common(top_surnames)}

    rows = []
    for (surname, country), cnt in pair_counts.items():
        if cnt < 3 or surname not in top:
            continue
        years = pair_years[(surname, country)]
        span = f"{min(years)}-{max(years)}" if years else "unbekannt"
        share = cnt / surname_total[surname] * 100 if surname_total[surname] else 0
        rows.append([
            surname, country, cnt, span, f"{share:.1f}%"
        ])
        if len(rows) >= MAX_ROWS:
            break

    rows.sort(key=lambda r: (-r[2], r[0]))
    p(f"Nachnamen-Region-Matrix: {len(rows)} Paare", tag="ok")
    return rows
