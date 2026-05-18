# -*- coding: utf-8 -*-
"""tasks/lineage.py – Abstammungslinien, Quartil-Ahnen, Linien-Erlöschen, Verzweigung"""

from collections import defaultdict, deque
from lib.gedcom import safe_extract_year
from lib.helpers import safe_extract_family_name
from lib.places import extract_country_from_place


# ── Y-Linie (rein paternal) ───────────────────────────────────────────────────

Y_LINE_HEADERS = [
    "Generation (0=Root)", "ID", "Name", "Geburtsjahr", "Sterbejahr", "Geburtsort"
]


def _walk_single_parent_line(root_id, individuals, families, parent_tag):
    """Walks up via FAMC -> parent_tag ("HUSB" oder "WIFE"). Returns list of
    (generation, pid) starting from root (gen 0)."""
    chain = []
    visited = set()
    current = root_id
    gen = 0
    while current and current in individuals and current not in visited:
        visited.add(current)
        chain.append((gen, current))
        pdata = individuals.get(current, {})
        famc_list = pdata.get("FAMC") or []
        if not famc_list:
            break
        fam = families.get(famc_list[0], {})
        if not fam:
            break
        parent = fam.get(parent_tag)
        if not parent or parent not in individuals:
            break
        current = parent
        gen += 1
    return chain


def _line_to_rows(chain, individuals):
    rows = []
    for gen, pid in chain:
        pdata = individuals.get(pid, {})
        name = pdata.get("NAME", "") or ""
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = safe_extract_year(birt.get("DATE")) or ""
        dy = safe_extract_year(deat.get("DATE")) or ""
        bp = birt.get("PLAC", "") or ""
        rows.append([gen, pid, name, by, dy, bp])
    # Deepest last → oldest ancestor at bottom: sort by generation ascending
    # is the natural order; we want deepest last, which means largest gen last.
    rows.sort(key=lambda r: r[0])
    return rows


def trace_y_line(root_id, individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Y-Linien-Analyse (rein paternal) …")
    chain = _walk_single_parent_line(root_id, individuals, families, "HUSB")
    rows = _line_to_rows(chain, individuals)
    p(f"Y-Linie: {len(rows)} Generationen verfolgt", tag="ok")
    return rows


# ── mtDNA-Linie (rein maternal) ───────────────────────────────────────────────

MT_LINE_HEADERS = [
    "Generation (0=Root)", "ID", "Name", "Geburtsjahr", "Sterbejahr", "Geburtsort"
]


def trace_mt_line(root_id, individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("mtDNA-Linien-Analyse (rein maternal) …")
    chain = _walk_single_parent_line(root_id, individuals, families, "WIFE")
    rows = _line_to_rows(chain, individuals)
    p(f"mtDNA-Linie: {len(rows)} Generationen verfolgt", tag="ok")
    return rows


# ── Großeltern-Quartile ───────────────────────────────────────────────────────

QUARTILE_HEADERS = [
    "Quartil", "Großeltern-ID", "Großeltern-Name", "Anzahl Ahnen",
    "Ø Lebenserwartung", "Migriert (Anzahl)", "% Migriert",
    "Distinkte Länder", "Frühestes Geburtsjahr"
]


def _parent_via(person_id, individuals, families, parent_tag):
    pdata = individuals.get(person_id, {})
    famc_list = pdata.get("FAMC") or []
    if not famc_list:
        return None
    fam = families.get(famc_list[0], {})
    if not fam:
        return None
    parent = fam.get(parent_tag)
    if parent and parent in individuals:
        return parent
    return None


def _person_migrated(pdata) -> bool:
    if pdata.get("MIGRATED"):
        return True
    if pdata.get("EMIG"):
        return True
    return False


def _collect_ancestors_bfs(start_id, individuals, families, max_gen=8):
    """All ancestors of start_id (including start_id itself) up to max_gen."""
    if not start_id or start_id not in individuals:
        return set()
    found = set()
    queue = deque([(start_id, 0)])
    while queue:
        cur, gen = queue.popleft()
        if cur in found or gen > max_gen:
            continue
        found.add(cur)
        cdata = individuals.get(cur, {})
        for fid in cdata.get("FAMC", []) or []:
            fam = families.get(fid, {})
            if not fam:
                continue
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par and par in individuals and par not in found:
                    queue.append((par, gen + 1))
    return found


def _quartile_stats(label, gp_id, individuals, families, location_data):
    if not gp_id or gp_id not in individuals:
        return [label, "", "", 0, "", 0, "", 0, ""]

    gp_data = individuals.get(gp_id, {})
    gp_name = gp_data.get("NAME", "") or ""

    ancestors = _collect_ancestors_bfs(gp_id, individuals, families, max_gen=8)
    n = len(ancestors)

    lifespans = []
    migrated_cnt = 0
    countries = set()
    earliest = None

    for aid in ancestors:
        a = individuals.get(aid, {})
        birt = a.get("BIRT") or {}
        deat = a.get("DEAT") or {}
        by = safe_extract_year(birt.get("DATE"))
        dy = safe_extract_year(deat.get("DATE"))
        if by is not None and dy is not None and dy >= by:
            lifespans.append(dy - by)
        if by is not None:
            if earliest is None or by < earliest:
                earliest = by
        if _person_migrated(a):
            migrated_cnt += 1
        bp = birt.get("PLAC", "") or ""
        if bp:
            country = extract_country_from_place(bp, location_data)
            if country:
                countries.add(country)

    avg_life = round(sum(lifespans) / len(lifespans), 1) if lifespans else ""
    pct_migr = round(migrated_cnt / n * 100, 1) if n else ""

    return [
        label, gp_id, gp_name, n, avg_life,
        migrated_cnt, pct_migr, len(countries),
        earliest if earliest is not None else ""
    ]


def analyze_grandparent_quartiles(root_id, individuals, families,
                                   location_data, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Großeltern-Quartil-Analyse …")

    father = _parent_via(root_id, individuals, families, "HUSB")
    mother = _parent_via(root_id, individuals, families, "WIFE")

    pp = _parent_via(father, individuals, families, "HUSB") if father else None
    pm = _parent_via(father, individuals, families, "WIFE") if father else None
    mp = _parent_via(mother, individuals, families, "HUSB") if mother else None
    mm = _parent_via(mother, individuals, families, "WIFE") if mother else None

    rows = [
        _quartile_stats("PP – paterner Großvater", pp, individuals, families, location_data),
        _quartile_stats("PM – paterne Großmutter", pm, individuals, families, location_data),
        _quartile_stats("MP – materner Großvater", mp, individuals, families, location_data),
        _quartile_stats("MM – materne Großmutter", mm, individuals, families, location_data),
    ]

    found = sum(1 for r in rows if r[1])
    p(f"Quartile: {found}/4 Großeltern in den Daten gefunden", tag="ok")
    return rows


# ── Linien-Erlöschen ──────────────────────────────────────────────────────────

EXTINCTION_HEADERS = [
    "Nachname", "Anzahl Bearer", "Erstbeleg-Jahr", "Letztbeleg-Jahr",
    "Letzter Bearer (Name)", "Status", "Männl. Nachkommen mit Namen (Anzahl)"
]


# Heuristische Schwelle: wenn der jüngst geborene Bearer eines Nachnamens
# vor mehr als 80 Jahren geboren wurde, gehen wir davon aus, dass eine
# weitere männliche Fortführung dieses Namens hier nicht mehr stattfindet.
_EXTINCTION_THRESHOLD_YEARS = 80
# Bezugsjahr für die "vor … Jahren"-Berechnung. Bewusst statisch, damit
# Ergebnisse über Runs hinweg reproduzierbar sind.
_REFERENCE_YEAR = 2026


def detect_lineage_extinction(individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Linien-Erlöschen-Analyse …")

    by_surname: dict = defaultdict(list)
    for pid, pdata in individuals.items():
        name = pdata.get("NAME", "") or ""
        surname = safe_extract_family_name(name)
        if not surname or surname == "Unbekannt":
            continue
        by_surname[surname].append(pid)

    cutoff_birth = _REFERENCE_YEAR - _EXTINCTION_THRESHOLD_YEARS
    rows = []

    for surname, bearers in by_surname.items():
        if len(bearers) < 3:
            continue

        years = []
        latest_pid = None
        latest_year = None
        for pid in bearers:
            pdata = individuals.get(pid, {})
            by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
            if by is None:
                continue
            years.append(by)
            if latest_year is None or by > latest_year:
                latest_year = by
                latest_pid = pid

        if not years or latest_pid is None:
            continue

        earliest_year = min(years)
        latest_data = individuals.get(latest_pid, {})
        latest_name = latest_data.get("NAME", "") or ""

        # Männliche Kinder mit gleichem Nachnamen zählen
        male_desc_count = 0
        for fid in latest_data.get("FAMS", []) or []:
            fam = families.get(fid, {})
            if not fam:
                continue
            for cid in fam.get("CHIL", []) or []:
                cdata = individuals.get(cid, {})
                if not cdata:
                    continue
                if cdata.get("SEX") != "M":
                    continue
                csurname = safe_extract_family_name(cdata.get("NAME", "") or "")
                if csurname == surname:
                    male_desc_count += 1

        if male_desc_count > 0:
            status = "Fortgeführt"
        elif latest_year < cutoff_birth:
            status = "Wahrscheinlich erloschen"
        else:
            status = "Möglicherweise noch aktiv"

        rows.append([
            surname, len(bearers), earliest_year, latest_year,
            latest_name, status, male_desc_count
        ])

    status_order = {
        "Wahrscheinlich erloschen": 0,
        "Möglicherweise noch aktiv": 1,
        "Fortgeführt": 2,
    }
    rows.sort(key=lambda r: (status_order.get(r[5], 99), r[3]))

    extinct_cnt = sum(1 for r in rows if r[5] == "Wahrscheinlich erloschen")
    p(f"Linien-Erlöschen: {len(rows)} Nachnamen geprüft, "
      f"{extinct_cnt} wahrscheinlich erloschen", tag="ok")
    return rows


# ── Verzweigungsfaktor ────────────────────────────────────────────────────────

BRANCHING_HEADERS = [
    "Generation", "Distinkte Ahnen", "Ø Kinder pro Ahn (in der gesamten Familie)",
    "Max Kinder", "Min Kinder", "Verzweigungs-Klassifikation"
]


def _classify_branching(avg: float) -> str:
    if avg > 6:
        return "Explosiv"
    if avg > 4:
        return "Stark"
    if avg > 2:
        return "Normal"
    return "Schwach"


def analyze_branching_factor(root_id, individuals, families, max_depth=10,
                              progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Verzweigungsfaktor-Analyse …")

    # Ahnen je Generation sammeln (root = Gen 0 wird übersprungen, da er
    # selbst kein "Ahn" ist – wir messen die Verzweigung der Vorfahren).
    gen_ancestors: dict = defaultdict(set)
    queue = deque([(root_id, 0)])
    seen = set()
    while queue:
        cur, gen = queue.popleft()
        if gen > max_depth:
            continue
        if (cur, gen) in seen:
            continue
        seen.add((cur, gen))
        if gen > 0:
            gen_ancestors[gen].add(cur)
        cdata = individuals.get(cur, {})
        for fid in cdata.get("FAMC", []) or []:
            fam = families.get(fid, {})
            if not fam:
                continue
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par and par in individuals:
                    queue.append((par, gen + 1))

    rows = []
    for gen in sorted(gen_ancestors.keys()):
        ancestors = gen_ancestors[gen]
        child_counts = []
        for aid in ancestors:
            adata = individuals.get(aid, {})
            kids = set()
            for fid in adata.get("FAMS", []) or []:
                fam = families.get(fid, {})
                if not fam:
                    continue
                for cid in fam.get("CHIL", []) or []:
                    if cid in individuals:
                        kids.add(cid)
            # Mindestens 1 Kind (die Linie zum Root), defensiv gegen
            # unvollständige Daten.
            child_counts.append(max(len(kids), 1))

        if not child_counts:
            continue
        avg = sum(child_counts) / len(child_counts)
        rows.append([
            gen, len(ancestors), round(avg, 2),
            max(child_counts), min(child_counts),
            _classify_branching(avg)
        ])

    p(f"Verzweigung: {len(rows)} Generationen analysiert", tag="ok")
    return rows
