"""CSV utility helpers for the MyHeritage shared-matches scraper."""
from __future__ import annotations

import csv
import io
import re

from ancestry.models.match import SharedMatch


def _parse_cm(val: str) -> float:
    """'3.533,5' oder '255.5' → float."""
    if not val:
        return 0.0
    # MH verwendet manchmal Punkt als Tausender und Komma als Dezimal
    val = val.strip().replace("\xa0", "")
    if "," in val and "." in val:
        # z.B. "3.533,5" → 3533.5
        val = val.replace(".", "").replace(",", ".")
    elif "," in val:
        val = val.replace(",", ".")
    elif val.count(".") > 1:
        # mehrere Punkte, kein Komma: z.B. "3.533.5" → 3533.5
        # letzter Punkt = Dezimaltrenner, alle anderen = Tausender
        _idx = val.rfind(".")
        val = val[:_idx].replace(".", "") + val[_idx:]
    try:
        return float(val)
    except ValueError:
        return 0.0


def _extract_guid(url: str) -> str:
    """Extrahiert die Match-GUID aus einer MH-URL."""
    # https://www.myheritage.com/dna/match/D-AAA-D-BBB  → D-BBB
    parts = url.rstrip("/").split("/")
    last = parts[-1] if parts else ""
    # Format: D-XXXXX-D-YYYYY → zweite GUID
    m = re.search(r"(D-[0-9A-F-]{30,})", last, re.I)
    if m:
        return m.group(1).upper()
    return last


def _load_main_csv(path: str, min_cm: float) -> list[dict]:
    """Liest die MH Match-List-CSV und filtert nach min_cm."""
    matches = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        # Debug: Spalten beim ersten Lauf ausgeben
        if not hasattr(_load_main_csv, "_headers_printed"):
            _load_main_csv._headers_printed = True  # type: ignore[attr-defined]
            print(f"CSV-Spalten: {headers}")
        # Flexible Spaltenerkennung (MH ändert manchmal Sprache/Format)
        cm_col   = next((h for h in headers if "cm" in h.lower() and "shared" in h.lower()), None) \
                or next((h for h in headers if "cM" in h or "cm" in h.lower()), None) \
                or "Shared cM"
        name_col = next((h for h in headers if "name" in h.lower() and "match" in h.lower()), None) \
                or next((h for h in headers if "name" in h.lower()), None) \
                or "Match Name"
        url_col  = next((h for h in headers if "url" in h.lower()), None) or "URL"
        guid_col = next((h for h in headers if "guid" in h.lower()), None) or "GUID"
        for row in reader:
            cm = _parse_cm(row.get(cm_col, "0"))
            if cm < min_cm:
                continue
            url  = (row.get(url_col)  or "").strip()
            guid = (row.get(guid_col) or "").strip()
            if not url and not guid:
                continue
            matches.append({
                "name":  (row.get(name_col) or "").strip(),
                "cm":    cm,
                "guid":  guid,
                "url":   url,
            })
    matches.sort(key=lambda x: x["cm"], reverse=True)
    return matches


def _parse_shared_csv(csv_text: str, test_guid: str,
                      match_guid_a: str, fetched_at: str) -> list[SharedMatch]:
    """Parst eine MH Shared-Matches-CSV in SharedMatch-Objekte."""
    results = []
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            guid_b = row.get("GUID", "").strip()
            if not guid_b:
                continue
            cm_b  = _parse_cm(row.get("Shared cM", "0"))
            cm_ab = _parse_cm(row.get("Shared cM with Match", "0"))
            results.append(SharedMatch(
                test_guid       = test_guid,
                match_guid_a    = match_guid_a,
                match_guid_b    = guid_b,
                display_name_b  = row.get("Match Name", "").strip(),
                shared_cm_b     = cm_b,
                shared_cm_ab    = cm_ab,
                shared_segments_b = 0,
                relationship_b  = row.get("Estimated Relationship", "").strip(),
                has_tree_b      = bool(row.get("Tree Size", "0").strip()
                                       not in ("", "0")),
                fetched_at      = fetched_at,
            ))
    except Exception as e:
        print(f"    ⚠ CSV-Parse-Fehler: {e}")
    return results
