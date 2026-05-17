"""Tests für lib.helpers – Verwandtschaftslabels und Ahnenpfade."""
from lib.helpers import (relationship_label, get_ancestor_paths,
                          safe_extract_family_name,
                          safe_determine_migration_status,
                          clear_migration_status_cache,
                          _MIGRATION_STATUS_CACHE)


# ── relationship_label ────────────────────────────────────────────────────────

def test_relationship_label_direct_line():
    assert relationship_label(1, 0, True) == "Elternteil"
    assert relationship_label(2, 0, True) == "Großelternteil"
    assert relationship_label(3, 0, True) == "Urgroßelternteil"
    assert relationship_label(4, 0, True) == "2-fach Urgroßelternteil"


def test_relationship_label_sibling_and_uncle():
    assert relationship_label(1, 1, False) == "Geschwister"
    assert relationship_label(2, 1, False) == "Onkel/Tante"
    assert relationship_label(3, 1, False) == "Großonkel/-tante"


def test_relationship_label_cousins():
    # 1st cousin: beide Großeltern gemeinsam, Tiefe 2 bei beiden.
    assert relationship_label(2, 2, False) == "Cousin 1. Grades"
    assert relationship_label(3, 3, False) == "Cousin 2. Grades"
    # 1st cousin 1x removed: einer Tiefe 2, anderer Tiefe 3.
    assert relationship_label(2, 3, False) == "Cousin 1. Grades, 1x entfernt"


# ── get_ancestor_paths ────────────────────────────────────────────────────────

def _mini_tree():
    indiv = {
        "@C@":   {"FAMC": ["@F1@"]},
        "@P1@":  {"FAMC": ["@F2@"]},
        "@P2@":  {},
        "@GP1@": {}, "@GP2@": {},
    }
    fams = {
        "@F1@": {"HUSB": "@P1@", "WIFE": "@P2@"},
        "@F2@": {"HUSB": "@GP1@", "WIFE": "@GP2@"},
    }
    return indiv, fams


def test_get_ancestor_paths_basic():
    indiv, fams = _mini_tree()
    paths = get_ancestor_paths("@C@", indiv, fams)
    # Beide Eltern, beide Großeltern müssen erreicht werden.
    assert set(paths) == {"@P1@", "@P2@", "@GP1@", "@GP2@"}
    assert len(paths["@P1@"][0]) == 2   # [@C@, @P1@]
    assert len(paths["@GP1@"][0]) == 3  # [@C@, @P1@, @GP1@]


def test_get_ancestor_paths_unknown_root():
    paths = get_ancestor_paths("@X@", {}, {})
    assert dict(paths) == {}


# ── safe_extract_family_name ──────────────────────────────────────────────────

def test_extract_family_name_strips_symbols():
    assert safe_extract_family_name("Hans ✠ /Müller/ mig.1882") == "Müller"
    assert safe_extract_family_name("Jane Smith") == "Smith"
    assert safe_extract_family_name("") == ""
    assert safe_extract_family_name(None) == ""


# ── safe_determine_migration_status (Memoization) ─────────────────────────────

def test_migration_status_memoized():
    clear_migration_status_cache()
    ld = {"countries": {
        "Deutschland": {"aliases": ["deutschland"], "states": {}},
        "USA":         {"aliases": ["usa"], "states": {}},
    }}
    pdata = {"BIRT": {"PLAC": "Berlin, Deutschland"},
             "DEAT": {"PLAC": "New York, USA"}}
    r1 = safe_determine_migration_status(pdata, "Hans Müller", ld)
    r2 = safe_determine_migration_status(pdata, "Hans Müller", ld)
    assert r1.startswith("ja")
    assert r1 == r2
    assert len(_MIGRATION_STATUS_CACHE) == 1


def test_migration_status_structured_fields():
    clear_migration_status_cache()
    ld = {"countries": {
        "Deutschland": {"aliases": ["deutschland"], "states": {}},
        "USA":         {"aliases": ["usa"], "states": {}},
    }}
    pdata = {"BIRT": {"PLAC": "Berlin, Deutschland"},
             "DEAT": {"PLAC": "New York, USA"},
             "DIED_IN_BATTLE": False}
    status = safe_determine_migration_status(pdata, "Hans Müller", ld)
    # Backward-Compat: ist immer noch ein String.
    assert isinstance(status, str)
    assert status.startswith("ja")
    # Neu: strukturierte Felder.
    assert status.migrated is True
    assert status.from_country == "Deutschland"
    assert status.to_country == "USA"
    assert status.died_in_battle is False
    assert status.has_marker is False


def test_migration_status_battle_flag():
    clear_migration_status_cache()
    ld = {"countries": {
        "Deutschland": {"aliases": ["deutschland"], "states": {}},
        "Frankreich":  {"aliases": ["frankreich"], "states": {}},
    }}
    pdata = {"BIRT": {"PLAC": "Köln, Deutschland"},
             "DEAT": {"PLAC": "Paris, Frankreich"},
             "DIED_IN_BATTLE": True}
    # Default: gefallen → nicht als Migration werten
    s_default = safe_determine_migration_status(pdata, "Hans", ld)
    assert not s_default.startswith("ja")
    assert s_default.migrated is False
    assert s_default.died_in_battle is True
    # Migration-Task-Modus: Länderwechsel zählt trotz Tod
    s_mig = safe_determine_migration_status(pdata, "Hans", ld,
                                             battle_counts_as_migration=True)
    assert s_mig.startswith("ja")
    assert s_mig.migrated is True
