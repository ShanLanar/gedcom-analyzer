"""Tests für lib.helpers – Verwandtschaftslabels und Ahnenpfade."""
from lib.helpers import (relationship_label, get_ancestor_paths,
                          safe_extract_family_name,
                          safe_determine_migration_status,
                          clear_migration_status_cache,
                          _MIGRATION_STATUS_CACHE)


# ── relationship_label ────────────────────────────────────────────────────────

def test_relationship_label_direct_line():
    assert relationship_label(1, 0, True) == "parent"
    assert relationship_label(2, 0, True) == "grandparent"
    assert relationship_label(3, 0, True) == "greatgrandparent"


def test_relationship_label_sibling_and_uncle():
    assert relationship_label(1, 1, False) == "sibling"
    assert relationship_label(2, 1, False) == "uncle/aunt"
    assert relationship_label(3, 1, False) == "granduncle/aunt"


def test_relationship_label_cousins():
    # 1st cousin: beide Großeltern gemeinsam, Tiefe 2 bei beiden.
    assert relationship_label(2, 2, False) == "1st cousin"
    assert relationship_label(3, 3, False) == "2nd cousin"
    # 1st cousin 1x removed: einer Tiefe 2, anderer Tiefe 3.
    assert relationship_label(2, 3, False) == "1st cousin 1x removed"


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
