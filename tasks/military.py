# -*- coding: utf-8 -*-
"""tasks/military.py – Detaillierte Militäranalyse"""

from lib.gedcom import safe_extract_year
from lib.places import format_place_for_display
from lib.helpers import extract_military_force_from_name


def analyze_military_service_detailed(individuals, families, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Militäranalyse …")

    results = []
    MIL_KEYWORDS = ["gefallen", "soldat", "veteran", "armee", "wehr",
                     "infanterist", "unteroffizier", "offizier"]
    RANK_MAP = {
        "offizier": ["offizier", "officer", "leutnant", "lieutenant", "hauptmann",
                     "captain", "major", "oberst", "colonel", "general"],
        "unteroffizier": ["unteroffizier", "feldwebel", "sergeant", "corporal",
                           "sgt", "cpl", "wachtmeister"],
        "soldat":   ["soldat", "schütze", "grenadier", "infanterist", "private",
                     "gefreiter", "rekrut", "kanonier"],
        "matrose":  ["matrose", "seemann", "sailor", "marine", "seaman", "bootsmann"],
        "flieger":  ["flieger", "pilot", "luftwaffe", "air force"],
    }

    for pid, pdata in individuals.items():
        name = pdata.get("NAME", "") or ""
        has_sym = any(s in name for s in ["✠", "★", "⚔"])
        if not has_sym and not any(kw in name.lower() for kw in MIL_KEYWORDS):
            continue

        force = extract_military_force_from_name(name)
        nl = name.lower()
        rank = next((rt for rt, inds in RANK_MAP.items()
                     if any(ind in nl for ind in inds)), "unbekannt")

        death_year = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        death_place = (pdata.get("DEAT") or {}).get("PLAC", "") or ""
        birth_year  = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))

        wars = []
        if death_year:
            if 1914 <= death_year <= 1918: wars.append("WWI")
            if 1939 <= death_year <= 1945: wars.append("WWII")
            if 1870 <= death_year <= 1871: wars.append("Deutsch-Französischer Krieg")

        dpl = death_place.lower()
        units = []
        if force == "deutsch":
            if any(w in dpl for w in ["frankreich", "france", "paris"]):   units.append("Westfront")
            elif any(w in dpl for w in ["russland", "russia", "stalingrad"]): units.append("Ostfront")
            elif any(w in dpl for w in ["afrika", "tunesien", "libyen"]):  units.append("Afrikakorps")
        elif force == "australisch":
            if any(w in dpl for w in ["gallipoli", "anzac"]): units.append("Gallipoli")
            elif any(w in dpl for w in ["kokoda", "papua"]): units.append("Pazifikkrieg")

        children = 0; spouse_name = ""
        for fid in pdata.get("FAMS", []):
            fam = families.get(fid, {})
            if fam:
                children += len(fam.get("CHIL", []))
                sid = fam.get("WIFE") if fam.get("HUSB") == pid else fam.get("HUSB")
                if sid and sid in individuals and not spouse_name:
                    spouse_name = individuals[sid].get("NAME", "") or ""

        age_at_death = death_year - birth_year if birth_year and death_year else None
        died_battle  = "⚔" in name or "gefallen" in nl

        results.append([
            pid, name, force, rank,
            ", ".join(units[:2]), ", ".join(wars) or "unbekannt",
            death_year or "", age_at_death or "",
            ("kurz (≤25J.)" if age_at_death and age_at_death <= 25
             else "mittel (26-35J.)" if age_at_death and age_at_death <= 35
             else "lang (>35J.)" if age_at_death else ""),
            format_place_for_display(death_place),
            "ja" if died_battle else "nein",
            "ja" if pdata.get("VETERAN") else "nein",
            "ja" if children > 0 else "nein", children,
            spouse_name[:40], birth_year or ""
        ])

    results.sort(key=lambda x: (x[6] or 0, x[7] or 0), reverse=True)
    p(f"Militär: {len(results)} Einträge analysiert", tag="ok")
    return results


MILITARY_HEADERS = [
    "ID", "Name", "Streitkraft", "Dienstgrad",
    "Sterbe-Region (Heuristik)", "Krieg",
    "Todesjahr", "Sterbealter", "Sterbealter-Klasse",
    "Sterbeort", "Gefallen", "Veteran",
    "Hat Kinder", "Kinderanzahl", "Ehepartner", "Geburtsjahr"
]
