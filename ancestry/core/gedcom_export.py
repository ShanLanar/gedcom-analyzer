"""
GEDCOM 5.5.1 export of shared match ancestors.

Converts pedigree groups from the DNA match database into a standard
GEDCOM file that can be imported by FamilySearch, Gramps, MacFamilyTree etc.
"""

import re
from typing import Optional


def _ged_tag(level: int, tag: str, value: str = "") -> str:
    line = f"{level} {tag}"
    if value:
        line += f" {value}"
    return line


def _clean(text: str) -> str:
    """Strip characters that break GEDCOM parsers."""
    if not text:
        return ""
    return re.sub(r"[\r\n@]", " ", str(text)).strip()


def export_gedcom(groups: list, output_path: str, submitter_name: str = "AncestryDNATool") -> int:
    """
    Write pedigree groups to a GEDCOM 5.5.1 file.

    Parameters
    ----------
    groups : list of dicts from db.get_pedigree_groups()
        Each group has keys: label, count, match_guids, ancestors (list of ancestor dicts)
        Ancestor dicts: given_name, surname, birth_year, birth_place, death_year, death_place, is_male
    output_path : str
        Destination file path (.ged)
    submitter_name : str
        Written into the SUBM record.

    Returns
    -------
    int  – number of INDI records written
    """
    lines = []

    # Header
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
    seen: dict[str, str] = {}  # (given_name, surname, birth_year) -> @Ixxx@

    def _indi_id(person: dict) -> str:
        key = (
            _clean(person.get("given_name", "")),
            _clean(person.get("surname", "")),
            _clean(person.get("birth_year", "")),
        )
        if key not in seen:
            nonlocal indi_count
            indi_count += 1
            seen[key] = f"@I{indi_count:05d}@"
        return seen[key]

    # Collect all unique individuals first
    all_persons = []
    for group in groups:
        for ancestor in group.get("ancestors", []):
            all_persons.append(ancestor)

    # Deduplicate
    unique_persons: dict[str, dict] = {}
    for p in all_persons:
        pid = _indi_id(p)
        if pid not in unique_persons:
            unique_persons[pid] = p

    # Write INDI records
    for pid, p in unique_persons.items():
        given = _clean(p.get("given_name", ""))
        surn = _clean(p.get("surname", ""))
        full_name = f"{given} /{surn}/" if surn else given
        sex = "M" if p.get("is_male") else "F"

        lines.append(f"0 {pid} INDI")
        if full_name.strip():
            lines.append(f"1 NAME {full_name}")
            if surn:
                lines.append(f"2 SURN {surn}")
            if given:
                lines.append(f"2 GIVN {given}")
        lines.append(f"1 SEX {sex}")

        by = _clean(p.get("birth_year", ""))
        bp = _clean(p.get("birth_place", ""))
        if by or bp:
            lines.append("1 BIRT")
            if by:
                lines.append(f"2 DATE {by}")
            if bp:
                lines.append(f"2 PLAC {bp}")

        dy = _clean(p.get("death_year", ""))
        dp = _clean(p.get("death_place", ""))
        if dy or dp:
            lines.append("1 DEAT")
            if dy:
                lines.append(f"2 DATE {dy}")
            if dp:
                lines.append(f"2 PLAC {dp}")

        # Note: which DNA match groups reference this ancestor
        for group in groups:
            if any(_indi_id(a) == pid for a in group.get("ancestors", [])):
                lines.append(f"1 NOTE DNA-Gruppe: {_clean(group.get('label', ''))}")
                break

    lines.append("0 TRLR")

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return indi_count
