# -*- coding: utf-8 -*-
"""tasks/cousins.py – Cousin- und Verwandtschaftsanalyse"""

from collections import Counter
from lib.helpers import (get_ancestor_paths, relationship_label,
                          extract_military_force_from_name,
                          safe_determine_migration_status)
from lib.places import format_place_for_display
from lib import logger as _log_module

_logger = None

def _p(msg, tag=""):
    if _logger:
        {"ok": _logger.info, "warn": _logger.warning,
         "err": _logger.error}.get(tag, _logger.info)(msg)
    else:
        print(msg)


def run(individuals, families, location_data, root_id, cache=None,
        progress_cb=None, **_kw):
    global _logger
    if progress_cb:
        _logger = None  # nutze progress_cb direkt
    p = progress_cb or (lambda m, **kw: None)

    p("Starte Cousin-Analyse …")
    root_paths = get_ancestor_paths(root_id, individuals, families, cache)

    root_parent_map = {}
    for fam_id in (individuals.get(root_id) or {}).get("FAMC", []):
        fam = families.get(fam_id, {})
        if fam.get("HUSB"): root_parent_map[fam["HUSB"]] = "father"
        if fam.get("WIFE"): root_parent_map[fam["WIFE"]] = "mother"

    output_rows = []
    MULT_MAP = {2: "double", 3: "triple", 4: "quadruple", 5: "quintuple",
                6: "sextuple", 7: "septuple", 8: "octuple", 9: "nonuple"}

    for tid, tdata in individuals.items():
        if tid == root_id:
            continue
        target_paths = get_ancestor_paths(tid, individuals, families, cache)
        common = set(root_paths) & set(target_paths)
        if not common:
            continue

        best_ancestors, best_score = [], None
        for anc in common:
            is_anc = (tid in root_paths)
            r_depths = [len(p) - (2 if is_anc else 1) for p in root_paths[anc]]
            t_depths = [len(p) - (2 if is_anc else 1) for p in target_paths[anc]]
            if not r_depths or not t_depths: continue
            score = max(min(r_depths), min(t_depths))
            if best_score is None or score < best_score:
                best_score, best_ancestors = score, [anc]
            elif score == best_score:
                best_ancestors.append(anc)

        if not best_ancestors:
            continue

        max_marriages = max(
            len(root_paths.get(a, [])) * len(target_paths.get(a, []))
            for a in common)
        multiplier  = MULT_MAP.get(max_marriages, "")
        alt_mult    = MULT_MAP.get(len(common), "") if len(common) > 1 else ""

        is_anc = (tid in root_paths)
        min_root   = min(len(pp) - (2 if is_anc else 1)
                         for a in best_ancestors for pp in root_paths[a])
        min_target = min(len(pp) - (2 if is_anc else 1)
                         for a in best_ancestors for pp in target_paths[a])
        relation = relationship_label(min_root, min_target, is_anc)

        sides = set()
        for anc in best_ancestors:
            for rpath in root_paths.get(anc, []):
                if len(rpath) >= 2:
                    s = root_parent_map.get(rpath[1])
                    if s: sides.add(s)
        lineage = ("both" if "father" in sides and "mother" in sides
                   else "father" if "father" in sides
                   else "mother" if "mother" in sides else "")

        name = tdata.get("NAME", "") or ""
        output_rows.append([
            tid, name,
            extract_military_force_from_name(name),
            safe_determine_migration_status(tdata, name, location_data),
            "ja" if tdata.get("DIED_IN_BATTLE") else "nein",
            "ja" if tdata.get("VETERAN") else "nein",
            "ja" if tdata.get("LINE_ENDS") else "nein",
            "ja" if tdata.get("GERMAN_SOLDIER") else "nein",
            "ja" if tdata.get("OTHER_SOLDIER") else "nein",
            multiplier, alt_mult, relation, lineage,
            ", ".join(individuals.get(a, {}).get("NAME", "") or ""
                      for a in best_ancestors[:3]),
            (tdata.get("BIRT") or {}).get("DATE", ""),
            format_place_for_display((tdata.get("BIRT") or {}).get("PLAC", "")),
            (tdata.get("DEAT") or {}).get("DATE", ""),
            format_place_for_display((tdata.get("DEAT") or {}).get("PLAC", "")),
        ])

    p(f"Cousin-Analyse abgeschlossen: {len(output_rows)} Beziehungen", tag="ok")
    return output_rows


HEADERS = [
    "Person ID", "Name", "Streitkraft", "Migriert", "Gefallen",
    "Veteran", "Linie endet", "Deutscher Soldat", "Anderer Soldat",
    "Multiplikator", "Alt Multiplikator", "Beziehung", "Linie",
    "Gemeinsame Ahnen", "Geburtsdatum", "Geburtsort",
    "Sterbedatum", "Sterbeort"
]
