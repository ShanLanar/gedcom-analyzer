# -*- coding: utf-8 -*-
"""tasks/endogamy.py – Endogamie-Score und Top-Ahnen-Analyse"""

import math
import re
from collections import defaultdict
from lib.gedcom import safe_extract_year
from lib.places import (format_place_for_display, get_place_with_fallback,
                         parse_detailed_place)
from lib.helpers import (get_ancestor_paths, relationship_label,
                          safe_determine_migration_status,
                          safe_extract_family_name,
                          extract_military_force_from_name)


# ── Endogamie ──────────────────────────────────────────────────────────────────

def compute_endogamy_with_detailed_places(individuals, families, root_id,
                                           location_data, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Endogamie-Analyse …")

    detailed_stats = defaultdict(lambda: {
        "count": 0, "persons": [], "surnames": set(), "birth_years": [],
        "german_soldiers": 0, "other_soldiers": 0, "fallen": 0,
        "veterans": 0, "migrated": 0,
        "details": {"stadt": set(), "bezirk": set(), "provinz": set(), "land": set()}
    })

    generic = location_data.get("generic_indicators", [])
    zusatz  = location_data.get("zusatz_keywords", [])

    for pid, pdata in individuals.items():
        bp = (pdata.get("BIRT") or {}).get("PLAC", "")
        if not bp: continue

        # Letzte 4 Komma-Teile; Hof-/Farm-Namen vorangestellt entfernen
        raw = [pt.strip() for pt in str(bp).split(",") if pt.strip()]
        cleaned = []
        for part in raw:
            pt = re.sub(r'\([^)]*\)', '', part)
            pt = re.sub(r'\b(hof|farm|anwesen|gut|haus|nr\.?|no\.?|number)\b', '',
                        pt, flags=re.IGNORECASE)
            pt = re.sub(r'\b\d+\b', '', pt)
            for z in zusatz:
                pt = re.sub(fr'\b{re.escape(z)}\b', '', pt, flags=re.IGNORECASE)
            pt = pt.strip(' ,.-')
            if pt and len(pt) >= 2:
                cleaned.append(pt)

        if not cleaned or len(cleaned) < 2: continue
        place_parts = cleaned[-4:]
        key = ", ".join(place_parts)

        if any(ind in key.lower() for ind in generic): continue
        if len(key) < 5: continue

        name = pdata.get("NAME", "") or ""
        st = detailed_stats[key]
        st["count"] += 1; st["persons"].append(pid)
        sn = safe_extract_family_name(name)
        if sn and len(sn) > 1: st["surnames"].add(sn)
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if by: st["birth_years"].append(by)
        if pdata.get("GERMAN_SOLDIER"): st["german_soldiers"] += 1
        if pdata.get("OTHER_SOLDIER"):  st["other_soldiers"] += 1
        if pdata.get("DIED_IN_BATTLE"): st["fallen"] += 1
        if pdata.get("VETERAN"):        st["veterans"] += 1
        if safe_determine_migration_status(pdata, name, location_data).startswith("ja"):
            st["migrated"] += 1
        for i, tag in enumerate(["stadt", "bezirk", "provinz", "land"]):
            if i < len(place_parts): st["details"][tag].add(place_parts[i])

    results = []
    for place, data in detailed_stats.items():
        cnt = data["count"]
        sn_div = len(data["surnames"])
        if cnt < 3 or sn_div < 2: continue

        # Endogamie-Score
        base = 1.0 / sn_div
        person_factor = min(2.0, math.log10(cnt + 1))
        score = min(1.0, base * person_factor)
        bys = data["birth_years"]
        if bys and max(bys) - min(bys) > 100:
            score = min(1.0, score * 1.2)

        yr_span = max(bys) - min(bys) if len(bys) >= 2 else 0

        if score > 0.8:   klasse = "SEHR HOCH (geschlossene Gemeinschaft)"
        elif score > 0.6: klasse = "HOCH (starke Lokalverbundenheit)"
        elif score > 0.4: klasse = "MITTEL (regionale Heiratskreise)"
        elif score > 0.2: klasse = "NIEDRIG (offene Gemeinschaft)"
        else:             klasse = "SEHR NIEDRIG (durchmischte Bevölkerung)"

        details_str = " | ".join(
            f"{k}: {', '.join(list(v)[:3])}"
            for k, v in data["details"].items() if v)[:80]

        examples = [
            (individuals.get(pid, {}).get("NAME") or "")[:25]
            + (f" (*{safe_extract_year((individuals.get(pid, {}).get('BIRT') or {}).get('DATE'))})"
               if safe_extract_year((individuals.get(pid, {}).get('BIRT') or {}).get('DATE')) else "")
            for pid in data["persons"][:3] if pid in individuals
        ]

        results.append([
            place, cnt, sn_div, round(score, 3), klasse,
            f"{min(bys)}-{max(bys)}" if bys else "n/a", yr_span,
            data["german_soldiers"], data["other_soldiers"], data["fallen"],
            data["migrated"],
            round(data["german_soldiers"] / cnt, 3),
            round(data["other_soldiers"] / cnt, 3),
            round(data["migrated"] / cnt, 3),
            details_str,
            ", ".join(examples)
        ])

    results.sort(key=lambda x: x[3], reverse=True)
    p(f"Endogamie: {len(results)} Orte analysiert", tag="ok")
    return results


ENDOGAMY_HEADERS = [
    "Vollständiger Ort", "Anzahl Personen", "Nachnamen-Diversität", "Endogamie Score",
    "Endogamie-Klasse", "Geburtsjahr-Spanne", "Jahres-Spanne",
    "✠ Deutsche Soldaten", "★ Andere Soldaten", "⚔ Gefallene", "Migriert",
    "Deutsche Soldaten Ratio", "Andere Soldaten Ratio", "Migrations-Ratio",
    "Ortsdetails", "Beispielpersonen"
]


# ── Top-Ahnen ──────────────────────────────────────────────────────────────────

def get_top_ancestors_with_info(individuals, families, location_data,
                                 root_id, exclude_id, cache=None,
                                 progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Top-Ahnen-Analyse …")

    root_paths = get_ancestor_paths(root_id, individuals, families, cache)
    if not root_paths:
        p("Keine Ahnen für Root gefunden", tag="warn")
        return []

    # Top-Ahnen: keine eigenen Eltern
    top_ancestors = [aid for aid in root_paths
                     if not individuals.get(aid, {}).get("FAMC") and aid != root_id]

    if exclude_id in individuals:
        excl = set(get_ancestor_paths(exclude_id, individuals, families, cache))
        top_ancestors = [a for a in top_ancestors if a not in excl]

    root_parents: dict = {}
    for fid in (individuals.get(root_id) or {}).get("FAMC", []):
        fam = families.get(fid, {})
        if fam.get("HUSB"): root_parents[fam["HUSB"]] = "väterlich"
        if fam.get("WIFE"): root_parents[fam["WIFE"]] = "mütterlich"

    rows = []
    for aid in sorted(top_ancestors):
        pdata = individuals.get(aid, {})
        if not pdata: continue
        name = pdata.get("NAME", "") or ""
        place = format_place_for_display(
            get_place_with_fallback(individuals, families, aid, location_data))

        # Verwandtschaftsgrad
        if aid in root_paths:
            sp = min(root_paths[aid], key=len)
            rel = relationship_label(len(sp) - 1, 0, True)
        else:
            rel = "unbekannt"

        # Linie
        sides = set()
        for rpath in root_paths.get(aid, []):
            if len(rpath) >= 2:
                s = root_parents.get(rpath[1])
                if s: sides.add(s)
        lineage = ("beide" if len(sides) > 1 else next(iter(sides), "unbekannt"))

        by = (pdata.get("BIRT") or {}).get("YEAR") or \
             safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))

        mil = ("✠ Deutsch" if "✠" in name else
               "★ Niederländisch" if ("★" in name and "niederl" in name.lower()) else
               "★ Australisch"   if ("★" in name and "austral" in name.lower()) else
               "★ Andere"        if "★" in name else "")
        fallen = "⚔" if "⚔" in name else ""
        migrated = safe_determine_migration_status(pdata, name, location_data)

        rows.append([aid, name, str(by) if by else "", place, lineage,
                     rel, mil, fallen, migrated])

    p(f"Top-Ahnen: {len(rows)} identifiziert", tag="ok")
    return rows


TOP_ANCESTOR_HEADERS = [
    "ID", "Name", "Geburtsjahr", "Geburtsort", "Linie",
    "Verwandtschaft zu Root", "Streitkraft", "Gefallen", "Migriert"
]
