"""
GEDCOM 5.5.1 export of shared match ancestors.

Converts pedigree groups from the DNA match database into a standard
GEDCOM file that can be imported by FamilySearch, Gramps, MacFamilyTree etc.

Each INDI record represents an ancestor shared by ≥N DNA matches.
The DNA evidence (match count, total/median cM, Sosa path) is embedded as
NOTE and _SOSA custom tag records so that standard parsers are not broken.

Family structure is derived from Sosa-Stradonitz numbers: if ancestor A has
Sosa 4 and ancestor B has Sosa 2, then B is the father of A — a FAM record
is created with HUSB/WIFE and CHIL pointers, and the INDI records carry
matching FAMS/FAMC back-references so the file passes GEDCOM validation.
"""

import re
from collections import defaultdict
from pathlib import Path


def _ged_tag(level: int, tag: str, value: str = "") -> str:
    line = f"{level} {tag}"
    if value:
        line += f" {value}"
    return line


def _clean(text) -> str:
    """Strip characters that break GEDCOM parsers."""
    if not text:
        return ""
    return re.sub(r"[\r\n@]", " ", str(text)).strip()


def _sosa_from_path(path: str) -> int:
    """Convert an ancestor path string (e.g. 'FF', 'MFM') to a Sosa number."""
    sosa = 1
    for ch in (path or ""):
        sosa = sosa * 2 if ch == "F" else sosa * 2 + 1
    return sosa


def export_gedcom(groups: list, output_path: str,
                  submitter_name: str = "AncestryDNATool") -> int:
    """Write pedigree groups to a GEDCOM 5.5.1 file.

    Parameters
    ----------
    groups : list of dicts from ``db.get_pedigree_groups(mode="person")``
        Each dict has keys:
          label     – ancestor full name
          detail    – birth year string (may be empty or "*YYYY")
          count     – number of DNA matches that share this ancestor
          matches   – list of (match_guid, display_name, ahnen_path, generation, shared_cm)
    output_path : str
        Destination file path (.ged)
    submitter_name : str
        Written into the SUBM record.

    Returns
    -------
    int – number of INDI records written
    """
    # ── Phase 1: Collect unique individuals and their DNA evidence ────────────
    # Key: (name_lower, birth_year) → ensures same ancestor from multiple groups
    # merges into one INDI.
    indi_order: list[tuple] = []           # insertion-ordered unique keys
    indi_meta: dict[tuple, dict] = {}      # key → {pid, label, birth_year, ...}
    sosa_to_keys: dict[int, list[tuple]] = defaultdict(list)  # sosa → [key, ...]

    indi_count = 0

    def _register(label: str, birth_year: str, count: int,
                  matches: list, sosas: set, birth_place: str = "") -> tuple:
        key = (_clean(label).lower(), _clean(birth_year))
        if key not in indi_meta:
            nonlocal indi_count
            indi_count += 1
            pid = f"@I{indi_count:05d}@"
            parts = label.split()
            given = " ".join(parts[:-1]) if len(parts) >= 2 else ""
            surn  = parts[-1] if parts else ""
            total_cm  = sum(float(m[4] or 0) for m in matches)
            s_list    = sorted(float(m[4] or 0) for m in matches)
            median_cm = s_list[len(s_list) // 2] if s_list else 0.0
            match_names = [_clean(m[1]) for m in matches[:5] if m[1]]
            indi_meta[key] = {
                "pid":        pid,
                "label":      _clean(label),
                "birth_year": _clean(birth_year),
                "birth_place": _clean(birth_place),
                "given":      given,
                "surn":       surn,
                "count":      count,
                "total_cm":   total_cm,
                "median_cm":  median_cm,
                "match_names": match_names,
                "extra_matches": len(matches) - len(match_names),
                "sosas":      set(sosas),
                # FAMS/FAMC will be filled in phase 2
                "fams": [],   # list of fam_ids where this person is spouse
                "famc": [],   # list of fam_ids where this person is child
            }
            indi_order.append(key)
        else:
            # Merge additional DNA evidence
            meta = indi_meta[key]
            meta["count"]    += count
            meta["total_cm"] += sum(float(m[4] or 0) for m in matches)
            meta["sosas"].update(sosas)
        for s in sosas:
            if key not in sosa_to_keys[s]:
                sosa_to_keys[s].append(key)
        return key

    for group in groups:
        label   = _clean(group.get("label", ""))
        detail  = _clean(group.get("detail", ""))
        count   = group.get("count", 0)
        matches = group.get("matches", [])
        if not label:
            continue
        birth_year  = detail.lstrip("*").strip()
        birth_place = _clean(group.get("birth_place", ""))
        sosas: set[int] = set()
        for m in matches:
            path = m[2] if len(m) > 2 else ""
            if path:
                sosas.add(_sosa_from_path(path))
        _register(label, birth_year, count, matches, sosas, birth_place)

    # ── Phase 2: Build family structure from Sosa arithmetic ─────────────────
    # Sosa 4 → father is Sosa 2, mother is Sosa 3.
    # Even sosa → father's side (Vater). Odd sosa (>1) → mother's side (Mutter).
    fam_count = 0
    # family key: (father_pid_or_"", mother_pid_or_"") → fam_id
    fam_registry: dict[tuple, str] = {}
    # child_pid → fam_id  (a child can only have one biological family here)
    child_to_fam: dict[str, str] = {}
    # fam_id → list of child_pids
    fam_children: dict[str, list] = defaultdict(list)

    all_sosas = set(sosa_to_keys.keys())

    for child_key in indi_order:
        meta = indi_meta[child_key]
        child_pid = meta["pid"]

        for sosa in list(meta["sosas"]):
            if sosa <= 1:
                continue
            # Sosa rule: father of person S has sosa 2S, mother has sosa 2S+1
            father_sosa = sosa * 2
            mother_sosa = sosa * 2 + 1
            # Look up father and mother among known ancestors
            father_keys = sosa_to_keys.get(father_sosa, [])
            mother_keys = sosa_to_keys.get(mother_sosa, [])
            if not father_keys and not mother_keys:
                continue
            father_pid = indi_meta[father_keys[0]]["pid"] if father_keys else ""
            mother_pid = indi_meta[mother_keys[0]]["pid"] if mother_keys else ""
            fam_key = (father_pid, mother_pid)
            if fam_key not in fam_registry:
                fam_count += 1
                fam_id = f"@F{fam_count:05d}@"
                fam_registry[fam_key] = fam_id
                # Add FAMS back-references to parents
                if father_pid:
                    f_key = next(k for k in indi_order if indi_meta[k]["pid"] == father_pid)
                    if fam_id not in indi_meta[f_key]["fams"]:
                        indi_meta[f_key]["fams"].append(fam_id)
                if mother_pid:
                    m_key = next(k for k in indi_order if indi_meta[k]["pid"] == mother_pid)
                    if fam_id not in indi_meta[m_key]["fams"]:
                        indi_meta[m_key]["fams"].append(fam_id)
            else:
                fam_id = fam_registry[fam_key]

            # Each child can only be listed once per family
            if child_pid not in fam_children[fam_id]:
                fam_children[fam_id].append(child_pid)
            if fam_id not in meta["famc"]:
                meta["famc"].append(fam_id)
            break  # one biological family per ancestor is enough

    # ── Phase 3: Write GEDCOM lines ───────────────────────────────────────────
    lines = [
        "0 HEAD",
        "1 SOUR AncestryDNATool",
        "2 NAME Ancestry DNA Tool",
        "2 VERS 1.0",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "1 SUBM @SUBM1@",
        "0 @SUBM1@ SUBM",
        f"1 NAME {_clean(submitter_name)}",
        "0 @S001@ SOUR",
        "1 TITL AncestryDNA – Genetische Analyse",
        "1 AUTH Ancestry.com Operations Inc.",
        "1 PUBL Erstellt mit AncestryDNATool (DNA-Genealogie-Analyse)",
    ]

    # INDI records
    for key in indi_order:
        meta = indi_meta[key]
        pid   = meta["pid"]
        given = _clean(meta["given"])
        surn  = _clean(meta["surn"])
        full_name = f"{given} /{surn}/" if surn else given

        lines.append(f"0 {pid} INDI")
        if full_name.strip():
            lines.append(f"1 NAME {full_name}")
            if surn:
                lines.append(f"2 SURN {surn}")
            if given:
                lines.append(f"2 GIVN {given}")

        by = meta["birth_year"]
        bp = meta.get("birth_place", "")
        if by or bp:
            lines.append("1 BIRT")
            if by:
                lines.append(f"2 DATE {by}")
            if bp:
                lines.append(f"2 PLAC {bp}")

        # Family links (required for GEDCOM pedigree traversal)
        for fam_id in meta["famc"]:
            lines.append(f"1 FAMC {fam_id}")
        for fam_id in meta["fams"]:
            lines.append(f"1 FAMS {fam_id}")

        # DNA evidence
        cnt  = meta["count"]
        tcm  = meta["total_cm"]
        mcm  = meta["median_cm"]
        lines.append(f"1 NOTE DNA-Beleg: {cnt} Matches · gesamt {tcm:.0f} cM"
                     f" · Median {mcm:.0f} cM")
        lines.append("1 SOUR @S001@")
        lines.append(f"2 PAGE {cnt} DNA-Matches · gesamt {tcm:.0f} cM · Median {mcm:.0f} cM")
        lines.append("2 QUAY 3")

        # Sosa numbers
        sosa_str = ",".join(str(s) for s in sorted(meta["sosas"])[:8])
        if sosa_str:
            lines.append(f"1 _SOSA {sosa_str}")

        # Match names
        match_names = meta["match_names"]
        if match_names:
            joined = "; ".join(match_names)
            if meta["extra_matches"] > 0:
                joined += f" (+{meta['extra_matches']} weitere)"
            lines.append(f"1 NOTE Belegt durch: {joined}")

    # FAM records
    for (husb, wife), fam_id in fam_registry.items():
        lines.append(f"0 {fam_id} FAM")
        if husb:
            lines.append(f"1 HUSB {husb}")
        if wife:
            lines.append(f"1 WIFE {wife}")
        for chil_pid in fam_children.get(fam_id, []):
            lines.append(f"1 CHIL {chil_pid}")

    lines.append("0 TRLR")

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return indi_count
