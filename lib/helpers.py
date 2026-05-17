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

class MigrationStatus(str):
    """String-Subklasse mit strukturierten Feldern.

    Bestehende Aufrufer können weiterhin `.startswith("ja")` o.ä. machen —
    die Instanz ist semantisch ein String. Neuere Aufrufer greifen direkt
    auf `migrated`, `from_country`, `to_country`, `died_in_battle`,
    `has_marker` zu, statt den Text zu parsen.
    """

    def __new__(cls, text: str, *, migrated: bool = False,
                has_marker: bool = False, from_country: str = "",
                to_country: str = "", died_in_battle: bool = False):
        obj = super().__new__(cls, text)
        obj.migrated = migrated
        obj.has_marker = has_marker
        obj.from_country = from_country
        obj.to_country = to_country
        obj.died_in_battle = died_in_battle
        return obj


# Modul-lokaler Cache: dieselben (Geburtsort, Sterbeort, marker, in-battle)-
# Kombinationen wiederholen sich tausendfach über alle Tasks; Memoization
# spart das Re-Parsen der Orte.
_MIGRATION_STATUS_CACHE: dict = {}


def clear_migration_status_cache() -> None:
    """Aufrufen, wenn die GEDCOM-Daten neu geladen werden."""
    _MIGRATION_STATUS_CACHE.clear()


def safe_determine_migration_status(pdata: dict, name: str, location_data,
                                     battle_counts_as_migration: bool = False) -> str:
    try:
        name_str = name or ""
        has_marker = "mig." in name_str.lower()
        birth_place = (pdata.get("BIRT") or {}).get("PLAC") or ""
        death_place = (pdata.get("DEAT") or {}).get("PLAC") or ""
        died_in_battle = bool(pdata.get("DIED_IN_BATTLE"))
        key = (birth_place, death_place, has_marker, died_in_battle,
               battle_counts_as_migration)
        cached = _MIGRATION_STATUS_CACHE.get(key)
        if cached is not None:
            return cached
        result = _compute_migration_status(birth_place, death_place,
                                            has_marker, died_in_battle,
                                            battle_counts_as_migration,
                                            location_data)
        _MIGRATION_STATUS_CACHE[key] = result
        return result
    except Exception:
        return "unbekannt (Fehler)"


def _compute_migration_status(birth_place: str, death_place: str,
                               has_marker: bool, died_in_battle: bool,
                               battle_counts_as_migration: bool,
                               location_data) -> MigrationStatus:
    def _mk(text: str, *, migrated: bool, bc: str = "", dc: str = ""):
        return MigrationStatus(text, migrated=migrated, has_marker=has_marker,
                                from_country=bc, to_country=dc,
                                died_in_battle=died_in_battle)

    if not birth_place or not death_place:
        return _mk("unbekannt (markiert)" if has_marker else "unbekannt",
                   migrated=False)
    bc = extract_country_from_place(birth_place, location_data)
    dc = extract_country_from_place(death_place, location_data)
    if not dc and "australia" in death_place.lower():
        dc = "Australien"
    if not bc or not dc:
        return _mk("unbekannt (markiert)" if has_marker else "unbekannt",
                   migrated=False)
    if bc != dc:
        if died_in_battle and not battle_counts_as_migration:
            return _mk(f"nein (in {dc} gefallen)", migrated=False,
                       bc=bc, dc=dc)
        prefix = "ja (markiert: " if has_marker else "ja ("
        return _mk(f"{prefix}{bc} → {dc})", migrated=True, bc=bc, dc=dc)
    return _mk(f"nein (markiert, aber in {bc} geblieben)" if has_marker
               else f"nein (in {bc})",
               migrated=False, bc=bc, dc=dc)


# ── Verwandtschaft ─────────────────────────────────────────────────────────────

def get_ancestor_paths(start_id: str, individuals, families, cache=None):
    """Gibt {person_id: [liste von Pfaden]} zurück. Die Pfadanzahl pro
    Ahne wird auf MAX_PATHS_PER_ANCESTOR begrenzt, damit Pedigree
    Collapse keinen exponentiellen Speicheraufbau erzeugt."""
    if cache:
        return cache.get_ancestors(start_id, individuals, families)
    from lib.cache import _MAX_PATHS_PER_ANCESTOR
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
                if not parent or parent not in individuals:
                    continue
                if len(paths[parent]) >= _MAX_PATHS_PER_ANCESTOR:
                    continue
                new_path = path + [parent]
                paths[parent].append(new_path)
                queue.append(new_path)
    return paths


def relationship_label(root_d: int, target_d: int,
                        is_target_ancestor: bool = False) -> str:
    """Liefert eine deutsche Verwandtschaftsbezeichnung.
    Wird gleichermaßen in Excel-Spalten und in tasks/migration._rel_distance
    konsumiert; letztere Funktion parst die deutschen Begriffe."""
    if is_target_ancestor:
        if root_d == 1: return "Elternteil"
        if root_d == 2: return "Großelternteil"
        if root_d == 3: return "Urgroßelternteil"
        return f"{root_d-2}-fach Urgroßelternteil"
    if root_d == 1 and target_d == 1: return "Geschwister"
    if target_d == 1 and root_d > 1:
        if root_d == 2: return "Onkel/Tante"
        if root_d == 3: return "Großonkel/-tante"
        return f"{root_d-1}-fach Urgroßonkel/-tante"
    if root_d == 1 and target_d > 1:
        if target_d == 2: return "Neffe/Nichte"
        if target_d == 3: return "Großneffe/-nichte"
        return f"{target_d-1}-fach Urgroßneffe/-nichte"
    removed = abs(root_d - target_d)
    grade   = max(0, min(root_d, target_d) - 1)
    base    = f"Cousin {grade}. Grades"
    return f"{base}, {removed}x entfernt" if removed else base
