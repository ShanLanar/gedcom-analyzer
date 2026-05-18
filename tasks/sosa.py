# -*- coding: utf-8 -*-
"""
tasks/sosa.py — Sosa-Stradonitz/Kekule-Nummerierung der Ahnen.

Klassischer genealogischer Standard: Proband = 1, Vater = 2, Mutter = 3,
väterlicher Großvater = 4, väterliche Großmutter = 5, mütterlicher
Großvater = 6, mütterliche Großmutter = 7, … Für jede Person N gilt:
   Vater von N = 2·N
   Mutter von N = 2·N + 1
Bei Pedigree-Collapse (Implex) hat eine Person mehrere Sosa-Nummern.
"""

from collections import defaultdict, deque

from lib.gedcom import safe_extract_year


# ── Sosa-Berechnung ────────────────────────────────────────────────────────────

def compute_sosa_numbers(root_id, individuals, families, max_gen=15) -> dict:
    """
    Berechnet alle Sosa-Nummern für Root + dessen Ahnen.

    Rückgabe: {person_id: [sosa1, sosa2, ...]} — bei Pedigree-Collapse
    bekommt eine Person mehrere Nummern (Implex).
    """
    sosa_map: dict = defaultdict(list)
    sosa_map[root_id].append(1)
    queue = deque([(root_id, 1)])

    while queue:
        person_id, sosa = queue.popleft()
        # Generation = bit_length(sosa) - 1. Sosa = 2^max_gen wäre Gen max_gen.
        if sosa >= 2 ** max_gen:
            continue
        person = individuals.get(person_id, {})
        # Nur die erste FAMC-Familie nutzen (biologische Eltern)
        for fid in person.get("FAMC", []):
            fam = families.get(fid, {})
            father = fam.get("HUSB")
            mother = fam.get("WIFE")
            if father and father in individuals:
                fs = sosa * 2
                if fs not in sosa_map[father]:
                    sosa_map[father].append(fs)
                    queue.append((father, fs))
            if mother and mother in individuals:
                ms = sosa * 2 + 1
                if ms not in sosa_map[mother]:
                    sosa_map[mother].append(ms)
                    queue.append((mother, ms))
            break

    return dict(sosa_map)


def sosa_to_generation(sosa: int) -> int:
    """Generation aus Sosa-Nummer: 1 → 0, 2-3 → 1, 4-7 → 2, 8-15 → 3, …"""
    return sosa.bit_length() - 1


def sosa_to_role(sosa: int) -> str:
    """Beschreibender Label für die Rolle (Proband/Vater/Mutter/…)."""
    if sosa == 1:
        return "Proband"
    gen = sosa_to_generation(sosa)
    # Pfad von der Person zurück zur Root: an jedem Bit-Übergang
    # entscheidet sich „Vater (gerade) oder Mutter (ungerade)"
    path = []
    s = sosa
    while s > 1:
        path.append("Vater" if s % 2 == 0 else "Mutter")
        s //= 2
    path.reverse()
    if gen == 1:
        return path[0]
    if gen == 2:
        return "Groß" + path[1].lower() + " (" + path[0] + "-Linie)"
    # Ab Gen 3: Urgroßeltern, Ururgroßeltern, …
    prefix = "Ur" * (gen - 2) + "groß"
    return prefix + path[-1].lower() + " (" + " → ".join(path[:-1]) + ")"


# ── Sheet-Output ───────────────────────────────────────────────────────────────

SOSA_HEADERS = [
    "Sosa-Nr.", "Generation", "Person-ID", "Name", "Rolle",
    "Geburt (Jahr)", "Geburtsort", "Tod (Jahr)", "Sterbeort",
    "Implex (weitere Sosa-Nrn)",
]


def build_sosa_ahnentafel(root_id, individuals, families, max_gen=12,
                            progress_cb=None) -> list:
    """Klassische Ahnentafel — eine Zeile pro Sosa-Nummer, sortiert."""
    p = progress_cb or (lambda m, **kw: None)
    p("Sosa-Stradonitz-Ahnentafel …")

    sosa_map = compute_sosa_numbers(root_id, individuals, families, max_gen)

    rows = []
    for person_id, sosa_list in sosa_map.items():
        person = individuals.get(person_id, {})
        if not person:
            continue
        # Bei Implex: alle Sosa-Nummern auflisten, aber nur die kleinste als
        # primären Eintrag
        sosa_list_sorted = sorted(sosa_list)
        primary_sosa = sosa_list_sorted[0]
        gen = sosa_to_generation(primary_sosa)
        if gen > max_gen:
            continue
        name = (person.get("NAME") or "")[:60]
        role = sosa_to_role(primary_sosa)
        birth = person.get("BIRT") or {}
        death = person.get("DEAT") or {}
        by = birth.get("YEAR") or safe_extract_year(birth.get("DATE"))
        dy = death.get("YEAR") or safe_extract_year(death.get("DATE"))
        bp = (birth.get("PLAC") or "")[:50]
        dp = (death.get("PLAC") or "")[:50]
        implex_str = ", ".join(str(s) for s in sosa_list_sorted[1:]) \
                      if len(sosa_list_sorted) > 1 else ""

        rows.append([
            primary_sosa, gen, person_id, name, role,
            by or "", bp, dy or "", dp, implex_str,
        ])

    rows.sort(key=lambda r: r[0])  # nach Sosa-Nummer
    p(f"Ahnentafel: {len(rows):,} Ahnen mit Sosa-Nummer (max Generation {max_gen})",
      tag="ok")
    return rows


def annotate_with_sosa(rows, sosa_map, id_column=0) -> list:
    """Hängt eine Sosa-Nummern-Spalte an jede Zeile an, deren Person-ID
    in sosa_map auftaucht. Für Bereicherung bestehender Sheets."""
    out = []
    for row in rows:
        pid = row[id_column] if len(row) > id_column else None
        sosas = sosa_map.get(pid, [])
        sosa_str = ", ".join(str(s) for s in sorted(sosas)) if sosas else ""
        out.append(list(row) + [sosa_str])
    return out
