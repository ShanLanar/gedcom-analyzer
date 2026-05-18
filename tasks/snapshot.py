# -*- coding: utf-8 -*-
"""tasks/snapshot.py – Stichjahr-Snapshot + Lebende-Generationen-Overlap"""

from collections import defaultdict, deque
from lib.gedcom import safe_extract_year


# ── Stichjahr-Snapshot ────────────────────────────────────────────────────────

SNAPSHOT_HEADERS = [
    "Stichjahr", "Lebende gesamt", "Männer", "Frauen", "Unbekannt",
    "Erwachsene (≥18 J.)", "Kinder (<18 J.)",
    "Ältester (Geburtsjahr / Alter)", "Beispielpersonen",
]


def snapshot_at_years(individuals, years=None, progress_cb=None) -> list:
    """Wer war zu jedem Stichjahr nachweislich am Leben?
    Lebend = birth_year ≤ year ≤ death_year (oder death_year unbekannt
    UND birth_year ≥ year - 100)."""
    p = progress_cb or (lambda m, **kw: None)
    if years is None:
        years = [1600, 1650, 1700, 1750, 1800, 1850, 1900, 1950, 2000]
    p(f"Stichjahr-Snapshot: {len(years)} Jahre …")

    rows = []
    for y in years:
        alive_ids = []
        sex_count = {"M": 0, "F": 0, "U": 0}
        adults = children = 0
        oldest_year = None
        for pid, indi in individuals.items():
            by = (indi.get("BIRT") or {}).get("YEAR") or \
                 safe_extract_year((indi.get("BIRT") or {}).get("DATE"))
            if not by or by > y:
                continue
            dy = (indi.get("DEAT") or {}).get("YEAR") or \
                 safe_extract_year((indi.get("DEAT") or {}).get("DATE"))
            if dy:
                if dy < y:
                    continue
            else:
                # Unbekanntes Sterbedatum: nur lebend wenn nicht zu lang her
                if y - by > 100:
                    continue
            alive_ids.append(pid)
            sx = indi.get("SEX", "U")
            sex_count[sx if sx in ("M", "F") else "U"] += 1
            age = y - by
            if age >= 18: adults += 1
            else:         children += 1
            if oldest_year is None or by < oldest_year:
                oldest_year = by

        if not alive_ids:
            continue

        examples = []
        for pid in alive_ids[:3]:
            name = (individuals[pid].get("NAME") or "")[:30]
            by   = (individuals[pid].get("BIRT") or {}).get("YEAR")
            examples.append(f"{name} (*{by})" if by else name)

        oldest_age = (y - oldest_year) if oldest_year else ""
        rows.append([
            y, len(alive_ids), sex_count["M"], sex_count["F"], sex_count["U"],
            adults, children,
            f"{oldest_year} / {oldest_age} J." if oldest_year else "",
            " · ".join(examples),
        ])
    p(f"Snapshot: {len(rows)} Jahre mit lebenden Personen", tag="ok")
    return rows


# ── Lebende-Generationen-Overlap ──────────────────────────────────────────────

GEN_OVERLAP_HEADERS = [
    "Jahrzehnt", "Distinkte Generationen lebend",
    "Älteste lebende Gen.", "Jüngste lebende Gen.",
    "Personen in ältester Gen.", "Personen in jüngster Gen.",
]


def _generation_map(individuals, families, root_id, max_depth=10) -> dict:
    """Ordnet jeder Person ihre Generation zu (Root = 0, Eltern = 1, …,
    Kinder = -1, Enkel = -2)."""
    gen_map: dict = {root_id: 0}

    # Vorfahren: BFS aufwärts
    queue = deque([root_id])
    while queue:
        cur = queue.popleft()
        cur_gen = gen_map[cur]
        if abs(cur_gen) >= max_depth:
            continue
        cd = individuals.get(cur, {})
        for fid in cd.get("FAMC", []):
            fam = families.get(fid, {})
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par and par in individuals and par not in gen_map:
                    gen_map[par] = cur_gen + 1
                    queue.append(par)

    # Nachfahren: BFS abwärts
    queue = deque([root_id])
    while queue:
        cur = queue.popleft()
        cur_gen = gen_map[cur]
        cd = individuals.get(cur, {})
        for fid in cd.get("FAMS", []):
            fam = families.get(fid, {})
            for child in fam.get("CHIL", []):
                if child in individuals and child not in gen_map:
                    gen_map[child] = cur_gen - 1
                    queue.append(child)
    return gen_map


def analyze_living_generations(individuals, families, root_id,
                                progress_cb=None) -> list:
    """Pro Jahrzehnt: wie viele Generationen waren gleichzeitig lebend?"""
    p = progress_cb or (lambda m, **kw: None)
    p("Lebende-Generationen-Overlap …")

    gen_map = _generation_map(individuals, families, root_id)
    if not gen_map:
        return []

    # Sammle pro Jahrzehnt die lebenden Personen und ihre Generationen
    decade_gens: dict = defaultdict(lambda: defaultdict(list))  # decade → gen → [ids]
    for pid, gen in gen_map.items():
        indi = individuals.get(pid, {})
        by = (indi.get("BIRT") or {}).get("YEAR") or \
             safe_extract_year((indi.get("BIRT") or {}).get("DATE"))
        dy = (indi.get("DEAT") or {}).get("YEAR") or \
             safe_extract_year((indi.get("DEAT") or {}).get("DATE"))
        if not by:
            continue
        # Wenn dy fehlt, nimm by + 75 als Schätzung
        end_y = dy if dy else by + 75
        if end_y < by:
            continue
        start_decade = (by // 10) * 10
        end_decade   = (end_y // 10) * 10
        for dec in range(start_decade, end_decade + 1, 10):
            if 1500 <= dec <= 2100:
                decade_gens[dec][gen].append(pid)

    rows = []
    for dec in sorted(decade_gens):
        gens = decade_gens[dec]
        if not gens:
            continue
        gen_keys = sorted(gens.keys())
        oldest_gen = max(gen_keys)
        youngest_gen = min(gen_keys)
        rows.append([
            f"{dec}er",
            len(gen_keys),
            f"Gen {oldest_gen:+d}",
            f"Gen {youngest_gen:+d}",
            len(gens[oldest_gen]),
            len(gens[youngest_gen]),
        ])
    p(f"Generations-Overlap: {len(rows)} Jahrzehnte ausgewertet", tag="ok")
    return rows
