"""
GEDCOM 5.5.1 export of shared match ancestors.

Converts pedigree groups from the DNA match database into a standard
GEDCOM file that can be imported by FamilySearch, Gramps, MacFamilyTree etc.

Each INDI record represents an ancestor shared by ≥N DNA matches.
The DNA evidence (match count, total/median cM, Sosa path) is embedded as
NOTE and _SOSA custom tag records so that standard parsers are not broken.
"""

import re
from pathlib import Path
from typing import Optional


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
    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        "0 HEAD",
        "1 SOUR AncestryDNATool",
        "2 NAME Ancestry DNA Tool",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "1 SUBM @SUBM1@",
        "0 @SUBM1@ SUBM",
        f"1 NAME {_clean(submitter_name)}",
    ]

    indi_count = 0
    # dedup by (name_lower, birth_year)
    seen: dict[tuple, str] = {}
    written_pids: set[str] = set()

    def _indi_id(label: str, birth_year: str) -> tuple[str, bool]:
        """Return (pid, is_new). is_new=False means this ancestor was already written."""
        key = (_clean(label).lower(), _clean(birth_year))
        if key not in seen:
            nonlocal indi_count
            indi_count += 1
            seen[key] = f"@I{indi_count:05d}@"
            return seen[key], True
        return seen[key], False

    # ── INDI records (one per unique ancestor) ─────────────────────────────
    # We also track (label, birth_year) → pid for FAM generation below.
    pid_map: dict[tuple, str] = {}

    for group in groups:
        label   = _clean(group.get("label", ""))
        detail  = _clean(group.get("detail", ""))  # may be "*1800" or "1800"
        count   = group.get("count", 0)
        matches = group.get("matches", [])

        if not label:
            continue

        birth_year = detail.lstrip("*").strip()
        pid, is_new = _indi_id(label, birth_year)
        pid_map[(label.lower(), birth_year)] = pid
        if not is_new:
            continue   # ancestor already written; skip duplicate block

        # Split name into given/surname heuristically (last word = surname)
        parts = label.split()
        if len(parts) >= 2:
            given = " ".join(parts[:-1])
            surn  = parts[-1]
        else:
            given = ""
            surn  = label

        full_name = f"{given} /{surn}/" if surn else given

        lines.append(f"0 {pid} INDI")
        if full_name.strip():
            lines.append(f"1 NAME {full_name}")
            if surn:
                lines.append(f"2 SURN {surn}")
            if given:
                lines.append(f"2 GIVN {given}")

        if birth_year:
            lines.append("1 BIRT")
            lines.append(f"2 DATE {birth_year}")

        # ── DNA evidence note ─────────────────────────────────────────────
        total_cm  = sum(float(m[4] or 0) for m in matches)
        median_cm = sorted(float(m[4] or 0) for m in matches)[len(matches) // 2] if matches else 0.0

        lines.append(f"1 NOTE DNA-Beleg: {count} Matches · gesamt {total_cm:.0f} cM"
                     f" · Median {median_cm:.0f} cM")

        # Collect unique Sosa numbers from ahnen_paths
        sosas: list[int] = []
        for m in matches:
            path = m[2] if len(m) > 2 else ""
            if path:
                sosas.append(_sosa_from_path(path))
        if sosas:
            sosa_str = ",".join(str(s) for s in sorted(set(sosas))[:8])
            lines.append(f"1 _SOSA {sosa_str}")

        # List up to 5 match names as a continuation note
        match_names = [_clean(m[1]) for m in matches[:5] if m[1]]
        if match_names:
            joined = "; ".join(match_names)
            if len(matches) > 5:
                joined += f" (+{len(matches) - 5} weitere)"
            lines.append(f"1 NOTE Belegt durch: {joined}")

    # ── FAM records: derive parent-child links from Sosa numbers ────────────
    fam_count   = 0
    fam_by_pair: dict[tuple, str] = {}   # (father_pid, mother_pid) → @Fxxx@

    for group in groups:
        label      = _clean(group.get("label", ""))
        detail     = _clean(group.get("detail", ""))
        birth_year = detail.lstrip("*").strip()
        child_pid  = pid_map.get((label.lower(), birth_year))
        if not child_pid:
            continue

        matches = group.get("matches", [])
        # Collect Sosa numbers for this ancestor; derive parent's Sosa
        sosas: set[int] = set()
        for m in matches:
            path = m[2] if len(m) > 2 else ""
            if path:
                sosas.add(_sosa_from_path(path))

        # For each Sosa we can compute the father (sosa*2) and mother (sosa*2+1) → grandparent
        # We want to find the PARENT of this person (sosa/2 → path without last char)
        for sosa in sosas:
            if sosa <= 1:
                continue
            parent_sosa = sosa // 2
            # Find a group whose Sosa set includes parent_sosa
            for pg in groups:
                pm = pg.get("matches", [])
                p_label     = _clean(pg.get("label", ""))
                p_detail    = _clean(pg.get("detail", ""))
                p_birth_yr  = p_detail.lstrip("*").strip()
                p_pid       = pid_map.get((p_label.lower(), p_birth_yr))
                if not p_pid or p_pid == child_pid:
                    continue
                p_sosas = set()
                for pm_ in pm:
                    ppath = pm_[2] if len(pm_) > 2 else ""
                    if ppath:
                        p_sosas.add(_sosa_from_path(ppath))
                if parent_sosa not in p_sosas:
                    continue
                # p_pid is a parent of child_pid
                # Determine sex from Sosa: even = male (Vater), odd = female (Mutter)
                is_father = (sosa % 2 == 0)
                fam_key   = (p_pid, "") if is_father else ("", p_pid)
                fam_id_key = fam_key
                if fam_id_key not in fam_by_pair:
                    fam_count += 1
                    fam_by_pair[fam_id_key] = f"@F{fam_count:05d}@"
                fam_id = fam_by_pair[fam_id_key]
                break

    # Write FAM records
    for (husb, wife), fam_id in fam_by_pair.items():
        lines.append(f"0 {fam_id} FAM")
        if husb:
            lines.append(f"1 HUSB {husb}")
        if wife:
            lines.append(f"1 WIFE {wife}")

    lines.append("0 TRLR")

    Path(output_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return indi_count
