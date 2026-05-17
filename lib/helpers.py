# -*- coding: utf-8 -*-
"""lib/helpers.py – Gemeinsame Hilfsfunktionen"""

import re
from collections import defaultdict, deque
from lib.gedcom import safe_extract_year
from lib.places import (extract_country_from_place, format_place_for_display,
                         parse_detailed_place)


# ── Name-Extraktion ────────────────────────────────────────────────────────────

def safe_extract_family_name(name_str: str) -> str:
    """Extrahiert Nachname aus GEDCOM-Name, bereinigt Symbole."""
    try:
        if not name_str:
            return ""
        cleaned = str(name_str)
        for sym in ["✠", "★", "⚔", "‡", "‼"]:
            cleaned = cleaned.replace(sym, " ")
        cleaned = re.sub(r'\bmig\.\S*', '', cleaned, flags=re.IGNORECASE).strip()
        if "/" in cleaned:
            parts = cleaned.split("/")
            surname = parts[1].strip() if len(parts) >= 2 else ""
            if surname:
                return surname
        words = cleaned.strip().split()
        return words[-1] if words else ""
    except Exception:
        return ""


def extract_military_force_from_name(name: str) -> str:
    if not name:
        return "kein Militär"
    name_str = str(name)
    if "✠" in name_str:
        return "deutsch"
    if "★" in name_str:
        nl = name_str.lower()
        if any(w in nl for w in ["niederl", "holländ", "dutch"]):   return "niederländisch"
        if any(w in nl for w in ["austral", "anzac"]):              return "australisch"
        if any(w in nl for w in ["usa", "u.s.", "american"]):       return "amerikanisch"
        return "andere"
    if "⚔" in name_str:
        return "gefallen (unbekannt)"
    return "kein Militär"


def extract_emigration_year_from_name(name: str):
    if not name:
        return None
    for pat in [r'mig\.‼(\d{4})', r'mig\.(\d{4})', r'mig\s*(\d{4})']:
        m = re.search(pat, str(name), re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def extract_emigration_data_from_gedcom(pdata: dict):
    """Gibt (jahr, ort, event_typ) aus EMIG/IMMI zurück."""
    for ev_key in ("EMIG", "IMMI"):
        ev = pdata.get(ev_key, {})
        if ev and ev.get("DATE"):
            year = safe_extract_year(ev.get("DATE"))
            if year:
                return year, ev.get("PLAC", ""), ev_key
    return None, None, None


# ── Migrationsstatus ───────────────────────────────────────────────────────────

def safe_determine_migration_status(pdata: dict, name: str, location_data) -> str:
    try:
        name_str = name or ""
        has_marker = "mig." in name_str.lower()
        birth_place = (pdata.get("BIRT") or {}).get("PLAC") or ""
        death_place  = (pdata.get("DEAT") or {}).get("PLAC") or ""
        if not birth_place or not death_place:
            return "unbekannt (markiert)" if has_marker else "unbekannt"
        bc = extract_country_from_place(birth_place, location_data)
        dc = extract_country_from_place(death_place, location_data)
        if not dc and "australia" in death_place.lower():
            dc = "Australien"
        if not bc or not dc:
            return "unbekannt (markiert)" if has_marker else "unbekannt"
        if bc != dc:
            if pdata.get("DIED_IN_BATTLE"):
                return f"nein (in {dc} gefallen)"
            prefix = "ja (markiert: " if has_marker else "ja ("
            return f"{prefix}{bc} → {dc})"
        return (f"nein (markiert, aber in {bc} geblieben)" if has_marker
                else f"nein (in {bc})")
    except Exception:
        return "unbekannt (Fehler)"


# ── Verwandtschaft ─────────────────────────────────────────────────────────────

def get_ancestor_paths(start_id: str, individuals, families, cache=None):
    """Gibt {person_id: [liste von Pfaden]} zurück."""
    if cache:
        return cache.get_ancestors(start_id, individuals, families)
    paths = defaultdict(list)
    if start_id not in individuals:
        return paths
    queue = deque([[start_id]])
    while queue:
        path = queue.popleft()
        current = path[-1]
        for fam_id in (individuals.get(current) or {}).get("FAMC", []):
            fam = families.get(fam_id)
            if not fam:
                continue
            for parent in (fam.get("HUSB"), fam.get("WIFE")):
                if parent and parent in individuals:
                    new_path = path + [parent]
                    paths[parent].append(new_path)
                    queue.append(new_path)
    return paths


def relationship_label(root_d: int, target_d: int,
                        is_target_ancestor: bool = False) -> str:
    if is_target_ancestor:
        if root_d == 1: return "parent"
        if root_d == 2: return "grandparent"
        if root_d == 3: return "greatgrandparent"
        return f"{root_d-2}x greatgrandparent"
    if root_d == 1 and target_d == 1: return "sibling"
    if target_d == 1 and root_d > 1:
        if root_d == 2: return "uncle/aunt"
        if root_d == 3: return "granduncle/aunt"
        return f"{root_d-1}x great-uncle/aunt"
    if root_d == 1 and target_d > 1:
        if target_d == 2: return "nephew/niece"
        if target_d == 3: return "grandnephew/niece"
        return f"{target_d-1}x great-nephew/niece"
    removed = abs(root_d - target_d)
    grade   = max(0, min(root_d, target_d) - 1)
    suffix  = {0: "0th", 1: "1st", 2: "2nd", 3: "3rd"}.get(grade, f"{grade}th")
    base    = f"{suffix} cousin"
    return f"{base} {removed}x removed" if removed else base
