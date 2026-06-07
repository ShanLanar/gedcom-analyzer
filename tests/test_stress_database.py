"""
Comprehensive pytest test suite for ancestry/core/database.py.

Covers: Kit CRUD, Match CRUD, get_matches filtering, Shared Matches,
Pedigree methods, Ancestors, get_pedigree_groups, get_shared_clusters,
get_statistics, and edge/stress cases.

Implementation notes:
- Database(":memory:") does NOT produce a truly isolated SQLite database
  because Database.__init__ converts relative paths: ":memory:" becomes
  "/…/ancestry/:memory:" — a real persistent file shared across all tests.
  We therefore use tempfile.mkstemp() to guarantee per-test isolation.
- get_statistics(test_guid=...) has a known SQL bug (double WHERE clause),
  so statistics tests call get_statistics() without a test_guid and ensure
  the database contains only the expected rows.
- endogamy_cluster is NOT written by upsert_match; use set_endogamy_cluster().
"""

import sys
import os
import types
import time
import tempfile

import pytest

_ANCESTRY = '/home/user/gedcom-analyzer/ancestry'
if _ANCESTRY not in sys.path:
    sys.path.append(_ANCESTRY)

if 'core' not in sys.modules:
    _core_stub = types.ModuleType('core')
    _core_stub.__path__ = [os.path.join(_ANCESTRY, 'core')]
    _core_stub.__package__ = 'core'
    sys.modules['core'] = _core_stub

from core.database import Database
from models import DnaKit, DnaMatch, SharedMatch


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def make_kit(guid="kit-001", name="Heinrich Kovermann", test_type="AncestryDNA",
             created_date="2020-01-01", is_owner=True) -> DnaKit:
    return DnaKit(guid=guid, name=name, test_type=test_type,
                  created_date=created_date, is_owner=is_owner)


def make_match(match_guid="m-001", test_guid="kit-001",
               display_name="Müller, Hans",
               shared_cm=250.0, shared_segments=12,
               longest_segment=45.0,
               predicted_relationship="2. Cousin",
               has_tree=False, tree_size=0, starred=False,
               note="") -> DnaMatch:
    return DnaMatch(
        match_guid=match_guid,
        test_guid=test_guid,
        display_name=display_name,
        shared_cm=shared_cm,
        shared_segments=shared_segments,
        longest_segment=longest_segment,
        predicted_relationship=predicted_relationship,
        has_tree=has_tree,
        tree_size=tree_size,
        starred=starred,
        note=note,
    )


def make_shared(test_guid="kit-001", match_guid_a="m-001", match_guid_b="m-002",
                display_name_b="Wapelhorst, Fritz",
                shared_cm_b=85.0, shared_cm_ab=30.0,
                relationship_b="3. Cousin",
                has_tree_b=False,
                fetched_at="2026-01-01T00:00:00Z") -> SharedMatch:
    return SharedMatch(
        test_guid=test_guid,
        match_guid_a=match_guid_a,
        match_guid_b=match_guid_b,
        display_name_b=display_name_b,
        shared_cm_b=shared_cm_b,
        shared_cm_ab=shared_cm_ab,
        shared_segments_b=5,
        relationship_b=relationship_b,
        has_tree_b=has_tree_b,
        fetched_at=fetched_at,
    )


# ---------------------------------------------------------------------------
# Fixture – uses a real tempfile so every test gets a clean, isolated DB
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Fresh isolated database for every test via a temporary file."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)          # let Database create it fresh
    database = Database(path)
    yield database
    database.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


# ===========================================================================
# 1. Kit CRUD (5 tests)
# ===========================================================================

def test_upsert_kit_stores_and_retrieves(db):
    """upsert_kit persists a kit that is returned by get_kits."""
    kit = make_kit(guid="kit-100", name="Heinrich Kovermann")
    db.upsert_kit(kit)
    kits = db.get_kits()
    assert len(kits) == 1
    assert kits[0].guid == "kit-100"
    assert kits[0].name == "Heinrich Kovermann"


def test_upsert_kit_updates_name_on_conflict(db):
    """Upserting the same kit guid updates name and last_sync, not creates a duplicate."""
    kit = make_kit(guid="kit-200", name="Alte Name")
    db.upsert_kit(kit, last_sync="2025-01-01")
    kit2 = make_kit(guid="kit-200", name="Neue Name Wapelhorst")
    db.upsert_kit(kit2, last_sync="2026-06-01")
    kits = db.get_kits()
    assert len(kits) == 1
    assert kits[0].name == "Neue Name Wapelhorst"


def test_get_kits_returns_ordered_by_name(db):
    """get_kits returns kits ordered alphabetically by name."""
    db.upsert_kit(make_kit(guid="g1", name="Zimmermann, Bertha"))
    db.upsert_kit(make_kit(guid="g2", name="Finkeldey, Anna"))
    db.upsert_kit(make_kit(guid="g3", name="Müller, Georg"))
    names = [k.name for k in db.get_kits()]
    assert names == sorted(names)


def test_get_kits_empty_db_returns_empty_list(db):
    """get_kits on an empty database returns an empty list, not an error."""
    assert db.get_kits() == []


def test_upsert_kit_is_owner_flag_preserved(db):
    """The is_owner flag is stored correctly for both True and False."""
    db.upsert_kit(make_kit(guid="owner-1", name="Kovermann Heinrich", is_owner=True))
    db.upsert_kit(make_kit(guid="other-1", name="Finkeldey Gast", is_owner=False))
    kits = {k.guid: k for k in db.get_kits()}
    assert kits["owner-1"].is_owner is True
    assert kits["other-1"].is_owner is False


# ===========================================================================
# 2. Match CRUD (10 tests)
# ===========================================================================

def test_upsert_match_basic_roundtrip(db):
    """upsert_match saves a match; it is found again via get_matches."""
    m = make_match(match_guid="m-001", display_name="Müller, Karl", shared_cm=312.5)
    db.upsert_match(m)
    results = db.get_matches(test_guid="kit-001")
    assert len(results) == 1
    assert results[0].match_guid == "m-001"
    assert results[0].display_name == "Müller, Karl"
    assert results[0].shared_cm == pytest.approx(312.5)


def test_bulk_upsert_returns_correct_count(db):
    """bulk_upsert returns the number of successfully stored matches."""
    matches = [make_match(match_guid=f"m-{i:04d}", test_guid="kit-001",
                          display_name=f"Kovermann {i}", shared_cm=float(100 + i))
               for i in range(10)]
    count = db.bulk_upsert(matches)
    assert count == 10


def test_match_exists_true_after_upsert(db):
    """match_exists returns True for a guid that was upserted."""
    db.upsert_match(make_match(match_guid="guid-exists"))
    assert db.match_exists("guid-exists") is True


def test_match_exists_false_for_unknown_guid(db):
    """match_exists returns False for a guid that has never been stored."""
    assert db.match_exists("guid-never-inserted") is False


def test_get_match_count_all_kits(db):
    """get_match_count without test_guid returns total across all kits."""
    db.upsert_match(make_match(match_guid="a1", test_guid="kit-A"))
    db.upsert_match(make_match(match_guid="b1", test_guid="kit-B"))
    db.upsert_match(make_match(match_guid="b2", test_guid="kit-B"))
    assert db.get_match_count() == 3


def test_get_match_count_per_kit(db):
    """get_match_count with test_guid counts only matches for that kit."""
    db.upsert_match(make_match(match_guid="a1", test_guid="kit-A"))
    db.upsert_match(make_match(match_guid="b1", test_guid="kit-B"))
    db.upsert_match(make_match(match_guid="b2", test_guid="kit-B"))
    assert db.get_match_count("kit-A") == 1
    assert db.get_match_count("kit-B") == 2


def test_get_distinct_relationships(db):
    """get_distinct_relationships returns all non-empty unique relationship strings."""
    db.upsert_match(make_match(match_guid="r1", predicted_relationship="2. Cousin"))
    db.upsert_match(make_match(match_guid="r2", predicted_relationship="3. Cousin"))
    db.upsert_match(make_match(match_guid="r3", predicted_relationship="2. Cousin"))
    db.upsert_match(make_match(match_guid="r4", predicted_relationship=""))
    rels = db.get_distinct_relationships()
    assert "2. Cousin" in rels
    assert "3. Cousin" in rels
    assert "" not in rels
    assert len(rels) == 2


def test_set_endogamy_cluster_marks_match(db):
    """set_endogamy_cluster assigns a cluster label that persists in the DB row."""
    db.upsert_match(make_match(match_guid="endo-01", test_guid="kit-001"))
    db.set_endogamy_cluster("endo-01", "Ostercappeln-Linie")
    results = db.get_matches(test_guid="kit-001")
    assert results[0].endogamy_cluster == "Ostercappeln-Linie"


def test_set_endogamy_cluster_clear_label(db):
    """set_endogamy_cluster with empty string clears the cluster annotation."""
    db.upsert_match(make_match(match_guid="endo-02", test_guid="kit-001"))
    db.set_endogamy_cluster("endo-02", "Alt-Cluster")
    db.set_endogamy_cluster("endo-02", "")
    results = db.get_matches(test_guid="kit-001")
    assert results[0].endogamy_cluster == ""


def test_update_note_persists_in_matches_table(db):
    """update_note writes the note into the matches row and user_notes table."""
    db.upsert_match(make_match(match_guid="note-01", test_guid="kit-001"))
    db.update_note("note-01", "Möglicherweise Linie Wapelhorst/Seymour")
    results = db.get_matches(test_guid="kit-001")
    assert results[0].note == "Möglicherweise Linie Wapelhorst/Seymour"


# ===========================================================================
# 3. get_matches filtering (12 tests)
# ===========================================================================

def _populate_filter_db(db):
    """Insert a varied set of matches for filter tests (all in kit-F)."""
    db.upsert_kit(make_kit(guid="kit-F"))
    entries = [
        # guid, name, cm, rel, has_tree, tree_sz, starred, endo_cluster
        ("f-001", "Müller, Karl",      350.0, "1. Cousin",  True,  120, True,  ""),
        ("f-002", "Wapelhorst, Anna",  180.0, "2. Cousin",  False,   0, False, ""),
        ("f-003", "Finkeldey, Georg",   88.0, "3. Cousin",  True,   50, False, "endo"),
        ("f-004", "Kovermann, Lena",   600.0, "1. Cousin",  False,   0, True,  ""),
        ("f-005", "Zimmermann, Otto",   45.0, "4. Cousin",  False,   0, False, ""),
    ]
    for guid, name, cm, rel, has_tree, tree_sz, starred, endo in entries:
        db.upsert_match(DnaMatch(
            match_guid=guid, test_guid="kit-F", display_name=name,
            shared_cm=cm, shared_segments=5, longest_segment=20.0,
            predicted_relationship=rel,
            has_tree=has_tree, tree_size=tree_sz, starred=starred,
        ))
        if endo:
            db.set_endogamy_cluster(guid, endo)


def test_get_matches_filter_by_search(db):
    """search parameter filters by substring of display_name."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", search="Wapelhorst")
    assert len(results) == 1
    assert results[0].match_guid == "f-002"


def test_get_matches_filter_by_relationship(db):
    """relationship parameter filters to matches with that exact predicted_relationship."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", relationship="1. Cousin")
    guids = {r.match_guid for r in results}
    assert guids == {"f-001", "f-004"}


def test_get_matches_filter_starred_only(db):
    """starred_only=True returns only starred matches."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", starred_only=True)
    guids = {r.match_guid for r in results}
    assert guids == {"f-001", "f-004"}


def test_get_matches_filter_has_tree_only(db):
    """has_tree_only=True returns only matches with a tree."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", has_tree_only=True)
    guids = {r.match_guid for r in results}
    assert guids == {"f-001", "f-003"}


def test_get_matches_filter_min_cm(db):
    """min_cm filters out matches below the threshold."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", min_cm=200.0)
    for r in results:
        assert r.shared_cm >= 200.0
    guids = {r.match_guid for r in results}
    assert "f-005" not in guids   # 45 cM
    assert "f-002" not in guids   # 180 cM


def test_get_matches_filter_hide_endogamy(db):
    """hide_endogamy=True excludes matches with a non-empty endogamy_cluster."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", hide_endogamy=True)
    for r in results:
        assert r.endogamy_cluster == ""
    guids = {r.match_guid for r in results}
    assert "f-003" not in guids   # has endo cluster


def test_get_matches_sort_shared_cm_desc(db):
    """Default sort order is shared_cm DESC (largest cM first)."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", sort_col="shared_cm", sort_asc=False)
    cms = [r.shared_cm for r in results]
    assert cms == sorted(cms, reverse=True)


def test_get_matches_sort_shared_cm_asc(db):
    """sort_asc=True reverses order to ascending."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", sort_col="shared_cm", sort_asc=True)
    cms = [r.shared_cm for r in results]
    assert cms == sorted(cms)


def test_get_matches_limit(db):
    """limit parameter restricts the number of returned rows."""
    _populate_filter_db(db)
    results = db.get_matches(test_guid="kit-F", limit=2)
    assert len(results) == 2


def test_get_matches_offset(db):
    """offset parameter skips the first N rows (combined with limit)."""
    _populate_filter_db(db)
    all_results = db.get_matches(test_guid="kit-F", sort_col="shared_cm", sort_asc=False)
    paged = db.get_matches(test_guid="kit-F", sort_col="shared_cm", sort_asc=False,
                           limit=2, offset=2)
    assert paged[0].match_guid == all_results[2].match_guid


def test_get_matches_relationship_alle_ignored(db):
    """relationship='(alle)' is treated as no filter (returns all matches)."""
    _populate_filter_db(db)
    results_all = db.get_matches(test_guid="kit-F")
    results_alle = db.get_matches(test_guid="kit-F", relationship="(alle)")
    assert len(results_alle) == len(results_all)


def test_get_matches_combined_filters(db):
    """Combining min_cm + has_tree_only + relationship narrows results correctly."""
    _populate_filter_db(db)
    # f-001: 1. Cousin, 350 cM, has_tree=True  → matches all three filters
    # f-004: 1. Cousin, 600 cM, has_tree=False → excluded by has_tree_only
    results = db.get_matches(test_guid="kit-F", relationship="1. Cousin",
                             has_tree_only=True, min_cm=200.0)
    assert len(results) == 1
    assert results[0].match_guid == "f-001"


# ===========================================================================
# 4. Shared matches (10 tests)
# ===========================================================================

def test_upsert_shared_match_stores_record(db):
    """upsert_shared_match persists a SharedMatch row."""
    db.upsert_match(make_match(match_guid="m-A", test_guid="kit-S"))
    sm = make_shared(test_guid="kit-S", match_guid_a="m-A", match_guid_b="m-B",
                     display_name_b="Finkeldey, Heinz", shared_cm_b=75.0)
    db.upsert_shared_match(sm)
    assert db.get_shared_match_count("kit-S") == 1


def test_bulk_upsert_shared_returns_count(db):
    """bulk_upsert_shared returns the number of items processed."""
    db.upsert_match(make_match(match_guid="m-A", test_guid="kit-S2"))
    items = [make_shared(test_guid="kit-S2", match_guid_a="m-A",
                         match_guid_b=f"m-{i}", shared_cm_b=float(50 + i))
             for i in range(5)]
    count = db.bulk_upsert_shared(items)
    assert count == 5


def test_is_shared_fetched_false_before_mark(db):
    """is_shared_fetched returns False before mark_shared_fetched is called."""
    assert db.is_shared_fetched("kit-001", "m-A") is False


def test_mark_shared_fetched_makes_is_shared_true(db):
    """mark_shared_fetched sets the flag; is_shared_fetched returns True afterwards."""
    db.mark_shared_fetched("kit-001", "m-A", "2026-01-15T10:00:00Z")
    assert db.is_shared_fetched("kit-001", "m-A") is True


def test_get_shared_matches_returns_correct_items(db):
    """get_shared_matches returns SharedMatch objects for the given primary match."""
    db.upsert_match(make_match(match_guid="prim-1", test_guid="kit-S3"))
    for i in range(3):
        sm = make_shared(test_guid="kit-S3", match_guid_a="prim-1",
                         match_guid_b=f"sec-{i}", shared_cm_b=float(60 - i * 10))
        db.upsert_shared_match(sm)
    results = db.get_shared_matches("kit-S3", "prim-1")
    assert len(results) == 3
    assert all(isinstance(r, SharedMatch) for r in results)


def test_delete_shared_for_removes_only_primary_rows(db):
    """delete_shared_for removes shared rows for one primary, leaves others intact."""
    db.upsert_match(make_match(match_guid="p1", test_guid="kit-D"))
    db.upsert_match(make_match(match_guid="p2", test_guid="kit-D"))
    db.upsert_shared_match(make_shared(test_guid="kit-D", match_guid_a="p1",
                                       match_guid_b="s1"))
    db.upsert_shared_match(make_shared(test_guid="kit-D", match_guid_a="p2",
                                       match_guid_b="s2"))
    db.delete_shared_for("kit-D", "p1")
    assert db.get_shared_match_count("kit-D", "p1") == 0
    assert db.get_shared_match_count("kit-D", "p2") == 1


def test_reset_shared_matches_clears_all_and_returns_count(db):
    """reset_shared_matches deletes all shared rows and the fetched markers."""
    db.upsert_match(make_match(match_guid="m1", test_guid="kit-R"))
    for i in range(4):
        db.upsert_shared_match(make_shared(test_guid="kit-R", match_guid_a="m1",
                                           match_guid_b=f"s{i}"))
    db.mark_shared_fetched("kit-R", "m1", "2026-01-01T00:00:00Z")
    deleted = db.reset_shared_matches("kit-R")
    assert deleted == 4
    assert db.get_shared_match_count("kit-R") == 0
    assert db.is_shared_fetched("kit-R", "m1") is False


def test_get_shared_match_count_per_primary(db):
    """get_shared_match_count with match_guid_a counts only for that primary."""
    db.upsert_match(make_match(match_guid="pA", test_guid="kit-C"))
    db.upsert_match(make_match(match_guid="pB", test_guid="kit-C"))
    for i in range(3):
        db.upsert_shared_match(make_shared(test_guid="kit-C", match_guid_a="pA",
                                           match_guid_b=f"xA{i}"))
    for i in range(2):
        db.upsert_shared_match(make_shared(test_guid="kit-C", match_guid_a="pB",
                                           match_guid_b=f"xB{i}"))
    assert db.get_shared_match_count("kit-C", "pA") == 3
    assert db.get_shared_match_count("kit-C", "pB") == 2


def test_get_unfetched_match_guids_excludes_fetched(db):
    """get_unfetched_match_guids omits matches whose shared-matches are already fetched."""
    db.upsert_match(make_match(match_guid="u1", test_guid="kit-U", shared_cm=100.0))
    db.upsert_match(make_match(match_guid="u2", test_guid="kit-U", shared_cm=80.0))
    db.mark_shared_fetched("kit-U", "u1", "2026-01-01T00:00:00Z")
    unfetched = db.get_unfetched_match_guids("kit-U")
    guids = [g for g, _ in unfetched]
    assert "u1" not in guids
    assert "u2" in guids


def test_get_unfetched_match_guids_min_cm_filter(db):
    """get_unfetched_match_guids respects the min_cm parameter."""
    db.upsert_match(make_match(match_guid="big", test_guid="kit-U2", shared_cm=150.0))
    db.upsert_match(make_match(match_guid="tiny", test_guid="kit-U2", shared_cm=10.0))
    unfetched = db.get_unfetched_match_guids("kit-U2", min_cm=50.0)
    guids = [g for g, _ in unfetched]
    assert "big" in guids
    assert "tiny" not in guids


# ===========================================================================
# 5. Pedigree methods (8 tests)
# ===========================================================================

def _sample_pedigree_rows():
    """Three ancestors across generations 2 and 3 for use in pedigree tests."""
    return [
        {"generation": 2, "ahnen_path": "F", "person_id": "p1",
         "given_name": "Ernst", "surname": "Kovermann", "is_male": True,
         "birth_year": "1850", "birth_date": "1850-03-01",
         "birth_place": "Ostercappeln", "death_year": "1920",
         "death_date": "1920-07-15", "death_place": "Osnabrück"},
        {"generation": 2, "ahnen_path": "M", "person_id": "p2",
         "given_name": "Maria", "surname": "Wapelhorst", "is_male": False,
         "birth_year": "1855", "birth_date": "1855-05-10",
         "birth_place": "Bohmte", "death_year": "1930",
         "death_date": "1930-01-01", "death_place": ""},
        {"generation": 3, "ahnen_path": "FF", "person_id": "p3",
         "given_name": "Heinrich", "surname": "Kovermann", "is_male": True,
         "birth_year": "1820", "birth_date": "",
         "birth_place": "Osnabrück", "death_year": "1880",
         "death_date": "", "death_place": ""},
    ]


def test_save_match_pedigree_stores_rows(db):
    """save_match_pedigree inserts all ancestor rows into match_pedigree."""
    db.upsert_match(make_match(match_guid="ped-m1", test_guid="kit-P", has_tree=True))
    db.save_match_pedigree("kit-P", "ped-m1", _sample_pedigree_rows())
    rows = db.get_pedigree_for_match("kit-P", "ped-m1")
    assert len(rows) == 3


def test_save_match_pedigree_replaces_on_second_save(db):
    """Calling save_match_pedigree twice replaces the previous data completely."""
    db.upsert_match(make_match(match_guid="ped-m2", test_guid="kit-P2", has_tree=True))
    db.save_match_pedigree("kit-P2", "ped-m2", _sample_pedigree_rows())
    new_rows = [{"generation": 2, "ahnen_path": "F", "person_id": "px",
                 "given_name": "Neu", "surname": "Finkeldey", "is_male": True,
                 "birth_year": "1860", "birth_date": "", "birth_place": "Bielefeld",
                 "death_year": "", "death_date": "", "death_place": ""}]
    db.save_match_pedigree("kit-P2", "ped-m2", new_rows)
    rows = db.get_pedigree_for_match("kit-P2", "ped-m2")
    assert len(rows) == 1
    assert rows[0]["surname"] == "Finkeldey"


def test_get_pedigree_for_match_empty_before_save(db):
    """get_pedigree_for_match returns empty list when nothing was saved."""
    db.upsert_match(make_match(match_guid="ped-m3", test_guid="kit-P3", has_tree=True))
    assert db.get_pedigree_for_match("kit-P3", "ped-m3") == []


def test_get_all_pedigrees_groups_by_match_guid(db):
    """get_all_pedigrees returns a dict keyed by match_guid with correct row counts."""
    db.upsert_match(make_match(match_guid="ped-a", test_guid="kit-A",
                               has_tree=True, shared_cm=200.0))
    db.upsert_match(make_match(match_guid="ped-b", test_guid="kit-A",
                               has_tree=True, shared_cm=150.0))
    db.save_match_pedigree("kit-A", "ped-a", _sample_pedigree_rows())
    db.save_match_pedigree("kit-A", "ped-b", _sample_pedigree_rows()[:1])
    peds = db.get_all_pedigrees("kit-A")
    assert "ped-a" in peds
    assert "ped-b" in peds
    assert len(peds["ped-a"]["rows"]) == 3   # all three rows at generation >= 2
    assert len(peds["ped-b"]["rows"]) == 1


def test_get_matches_needing_pedigree_excludes_already_fetched(db):
    """get_matches_needing_pedigree skips matches whose pedigree_fetched flag is set."""
    db.upsert_match(make_match(match_guid="pn-1", test_guid="kit-NP",
                               has_tree=True, shared_cm=100.0))
    db.upsert_match(make_match(match_guid="pn-2", test_guid="kit-NP",
                               has_tree=True, shared_cm=90.0))
    # Saving a pedigree sets pedigree_fetched=1 for pn-1
    db.save_match_pedigree("kit-NP", "pn-1", _sample_pedigree_rows()[:1])
    needed = db.get_matches_needing_pedigree("kit-NP")
    guids = [g for g, _ in needed]
    assert "pn-1" not in guids
    assert "pn-2" in guids


def test_get_matches_needing_pedigree_force_includes_fetched(db):
    """With force=True, even matches with pedigree_fetched=1 are returned."""
    db.upsert_match(make_match(match_guid="pf-1", test_guid="kit-NP2",
                               has_tree=True, shared_cm=120.0))
    db.save_match_pedigree("kit-NP2", "pf-1", _sample_pedigree_rows()[:1])
    needed = db.get_matches_needing_pedigree("kit-NP2", force=True)
    guids = [g for g, _ in needed]
    assert "pf-1" in guids


def test_get_matches_needing_pedigree_min_cm_filter(db):
    """get_matches_needing_pedigree respects the min_cm threshold."""
    db.upsert_match(make_match(match_guid="hi-cm", test_guid="kit-MC",
                               has_tree=True, shared_cm=200.0))
    db.upsert_match(make_match(match_guid="lo-cm", test_guid="kit-MC",
                               has_tree=True, shared_cm=30.0))
    needed = db.get_matches_needing_pedigree("kit-MC", min_cm=100.0)
    guids = [g for g, _ in needed]
    assert "hi-cm" in guids
    assert "lo-cm" not in guids


def test_get_matches_needing_ancestors_excludes_fetched(db):
    """get_matches_needing_ancestors excludes matches where ancestors_fetched=1."""
    db.upsert_match(make_match(match_guid="anc-1", test_guid="kit-ANC",
                               has_tree=True, shared_cm=150.0))
    db.upsert_match(make_match(match_guid="anc-2", test_guid="kit-ANC",
                               has_tree=True, shared_cm=100.0))
    # Saving ancestors sets ancestors_fetched=1 for anc-1
    db.save_match_ancestors("kit-ANC", "anc-1",
                            [{"ancestor_name": "Müller, Georg", "birth_year": "1800",
                              "death_year": "", "is_male": True,
                              "relationship_to_sample": "3x Urgroßvater",
                              "relationship_to_match": "2x Urgroßvater",
                              "kinship_path_sample": "FFFF",
                              "kinship_path_match": "FFF",
                              "in_match_tree": True, "amt_gid": "g001"}],
                            [])
    needed = db.get_matches_needing_ancestors("kit-ANC")
    guids = [g for g, _ in needed]
    assert "anc-1" not in guids
    assert "anc-2" in guids


# ===========================================================================
# 6. Ancestors (5 tests)
# ===========================================================================

def _sample_ancestors():
    """Two ancestor rows for use in ancestor tests."""
    return [
        {"ancestor_name": "Kovermann, Ernst", "birth_year": "1820",
         "death_year": "1890", "is_male": True,
         "relationship_to_sample": "4x Urgroßvater",
         "relationship_to_match": "3x Urgroßvater",
         "kinship_path_sample": "FFFF", "kinship_path_match": "FFF",
         "in_match_tree": True, "amt_gid": "gid-001"},
        {"ancestor_name": "Wapelhorst, Anna", "birth_year": "1825",
         "death_year": "1895", "is_male": False,
         "relationship_to_sample": "4x Urgroßmutter",
         "relationship_to_match": "3x Urgroßmutter",
         "kinship_path_sample": "FFFM", "kinship_path_match": "FFM",
         "in_match_tree": False, "amt_gid": "gid-002"},
    ]


def test_save_match_ancestors_stores_rows(db):
    """save_match_ancestors persists ancestor data in match_ancestors."""
    db.upsert_match(make_match(match_guid="anc-s1", test_guid="kit-AN",
                               has_tree=True, shared_cm=200.0))
    db.save_match_ancestors("kit-AN", "anc-s1", _sample_ancestors(), [])
    rows = db.get_ancestors_for_match("anc-s1")
    assert len(rows) == 2


def test_save_match_ancestors_replaces_on_second_call(db):
    """Second call to save_match_ancestors replaces the previous ancestors."""
    db.upsert_match(make_match(match_guid="anc-s2", test_guid="kit-AN2",
                               has_tree=True, shared_cm=200.0))
    db.save_match_ancestors("kit-AN2", "anc-s2", _sample_ancestors(), [])
    new_anc = [{"ancestor_name": "Finkeldey, Bertha", "birth_year": "1840",
                "death_year": "1910", "is_male": False,
                "relationship_to_sample": "3x Urgroßmutter",
                "relationship_to_match": "2x Urgroßmutter",
                "kinship_path_sample": "FMM", "kinship_path_match": "MM",
                "in_match_tree": True, "amt_gid": ""}]
    db.save_match_ancestors("kit-AN2", "anc-s2", new_anc, [])
    rows = db.get_ancestors_for_match("anc-s2")
    assert len(rows) == 1
    assert rows[0]["ancestor_name"] == "Finkeldey, Bertha"


def test_get_ancestors_for_match_empty_when_none_saved(db):
    """get_ancestors_for_match returns empty list for a match with no ancestors."""
    db.upsert_match(make_match(match_guid="anc-empty", test_guid="kit-AN3"))
    assert db.get_ancestors_for_match("anc-empty") == []


def test_get_ancestor_groups_groups_shared_ancestors(db):
    """get_ancestor_groups groups ancestor names shared by multiple matches."""
    db.upsert_match(make_match(match_guid="ag1", test_guid="kit-AG", shared_cm=200.0))
    db.upsert_match(make_match(match_guid="ag2", test_guid="kit-AG", shared_cm=180.0))
    db.save_match_ancestors("kit-AG", "ag1", _sample_ancestors(), [])
    db.save_match_ancestors("kit-AG", "ag2", _sample_ancestors(), [])
    groups = db.get_ancestor_groups("kit-AG", min_matches=2)
    names = [g["ancestor_name"] for g in groups]
    assert "Kovermann, Ernst" in names
    assert "Wapelhorst, Anna" in names


def test_get_ancestor_groups_min_matches_filter(db):
    """get_ancestor_groups with min_matches=3 excludes ancestors shared by only 2."""
    db.upsert_match(make_match(match_guid="ag10", test_guid="kit-AGF", shared_cm=200.0))
    db.upsert_match(make_match(match_guid="ag11", test_guid="kit-AGF", shared_cm=180.0))
    # Only 2 matches share these ancestors → min_matches=3 must return empty list
    db.save_match_ancestors("kit-AGF", "ag10", _sample_ancestors(), [])
    db.save_match_ancestors("kit-AGF", "ag11", _sample_ancestors(), [])
    groups = db.get_ancestor_groups("kit-AGF", min_matches=3)
    assert groups == []


# ===========================================================================
# 7. get_pedigree_groups (8 tests)
# ===========================================================================

def _populate_pedigree_groups(db, kit="kit-PG"):
    """Insert three matches with pedigree data; two share common ancestors."""
    db.upsert_match(make_match(match_guid="pg1", test_guid=kit,
                               shared_cm=300.0, has_tree=True))
    db.upsert_match(make_match(match_guid="pg2", test_guid=kit,
                               shared_cm=250.0, has_tree=True))
    db.upsert_match(make_match(match_guid="pg3", test_guid=kit,
                               shared_cm=100.0, has_tree=True))

    common_ancestors = [
        {"generation": 2, "ahnen_path": "F", "person_id": "pid1",
         "given_name": "Johann", "surname": "Müller", "is_male": True,
         "birth_year": "1840", "birth_date": "", "birth_place": "Osnabrück",
         "death_year": "1910", "death_date": "", "death_place": ""},
        {"generation": 3, "ahnen_path": "FM", "person_id": "pid2",
         "given_name": "Katharina", "surname": "Finkeldey", "is_male": False,
         "birth_year": "1815", "birth_date": "", "birth_place": "Bielefeld",
         "death_year": "1880", "death_date": "", "death_place": ""},
    ]
    db.save_match_pedigree(kit, "pg1", common_ancestors)
    db.save_match_pedigree(kit, "pg2", common_ancestors)

    # pg3 has a unique ancestor – only one match for that name
    unique = [{"generation": 2, "ahnen_path": "F", "person_id": "pid9",
               "given_name": "Otto", "surname": "Zimmermann", "is_male": True,
               "birth_year": "1870", "birth_date": "", "birth_place": "Bremen",
               "death_year": "", "death_date": "", "death_place": ""}]
    db.save_match_pedigree(kit, "pg3", unique)


def test_get_pedigree_groups_mode_person(db):
    """mode='person' groups by full name + birth year."""
    _populate_pedigree_groups(db)
    groups = db.get_pedigree_groups("kit-PG", min_matches=2, mode="person")
    labels = [g["label"] for g in groups]
    assert "Johann Müller" in labels


def test_get_pedigree_groups_mode_surname(db):
    """mode='surname' groups by surname only."""
    _populate_pedigree_groups(db)
    groups = db.get_pedigree_groups("kit-PG", min_matches=2, mode="surname")
    labels = [g["label"] for g in groups]
    assert any(lbl in ("Müller", "Finkeldey") for lbl in labels)


def test_get_pedigree_groups_mode_place(db):
    """mode='place' groups by birth_place."""
    _populate_pedigree_groups(db)
    groups = db.get_pedigree_groups("kit-PG", min_matches=2, mode="place")
    labels = [g["label"] for g in groups]
    assert any(lbl in ("Osnabrück", "Bielefeld") for lbl in labels)


def test_get_pedigree_groups_min_matches_1(db):
    """min_matches=1 includes singletons (every ancestor with data appears)."""
    _populate_pedigree_groups(db)
    groups = db.get_pedigree_groups("kit-PG", min_matches=1, mode="person")
    labels = [g["label"] for g in groups]
    assert "Otto Zimmermann" in labels   # seen in only pg3


def test_get_pedigree_groups_min_matches_2_excludes_singletons(db):
    """min_matches=2 excludes ancestors seen in only one match."""
    _populate_pedigree_groups(db)
    groups = db.get_pedigree_groups("kit-PG", min_matches=2, mode="person")
    labels = [g["label"] for g in groups]
    assert "Otto Zimmermann" not in labels


def test_get_pedigree_groups_only_guids_filter(db):
    """only_guids restricts the analysis to the specified match GUIDs."""
    _populate_pedigree_groups(db)
    # Restrict to pg1 alone → no group can reach count>=2
    groups = db.get_pedigree_groups("kit-PG", min_matches=2, mode="person",
                                     only_guids=["pg1"])
    assert groups == []


def test_get_pedigree_groups_empty_result_when_no_data(db):
    """get_pedigree_groups returns empty list when no pedigree data exists."""
    groups = db.get_pedigree_groups("kit-EMPTY", min_matches=2)
    assert groups == []


def test_get_pedigree_groups_sorted_by_count_desc(db):
    """Results are sorted descending by count (largest group first)."""
    _populate_pedigree_groups(db)
    groups = db.get_pedigree_groups("kit-PG", min_matches=1, mode="person")
    counts = [g["count"] for g in groups]
    assert counts == sorted(counts, reverse=True)


# ===========================================================================
# 8. get_shared_clusters (5 tests)
# ===========================================================================

def _build_cluster_data(db, kit="kit-CL"):
    """Insert matches and bi-directional shared-match edges forming a triangle cluster."""
    db.upsert_kit(make_kit(guid=kit, name="Cluster-Kit"))
    match_data = [
        ("cl1", "Müller, Hans",      150.0),
        ("cl2", "Wapelhorst, Fritz", 140.0),
        ("cl3", "Finkeldey, Anna",   130.0),
        ("cl4", "Kovermann, Lena",   120.0),
        ("cl5", "Zimmermann, Otto",   30.0),
    ]
    for guid, name, cm in match_data:
        db.upsert_match(DnaMatch(
            match_guid=guid, test_guid=kit, display_name=name,
            shared_cm=cm, shared_segments=6, longest_segment=25.0,
            predicted_relationship="2. Cousin",
        ))
    # Triangle: cl1–cl2–cl3; cl4 and cl5 are not connected to the triangle
    for a, b in [("cl1", "cl2"), ("cl2", "cl3"), ("cl1", "cl3")]:
        db.upsert_shared_match(make_shared(test_guid=kit, match_guid_a=a,
                                           match_guid_b=b, shared_cm_b=40.0))
        db.upsert_shared_match(make_shared(test_guid=kit, match_guid_a=b,
                                           match_guid_b=a, shared_cm_b=40.0))


def test_get_shared_clusters_empty_db(db):
    """get_shared_clusters returns empty list when no shared matches exist."""
    result = db.get_shared_clusters("kit-NONE")
    assert result == []


def test_get_shared_clusters_single_pair_forms_cluster(db):
    """Two matches sharing DNA form a two-member cluster."""
    db.upsert_kit(make_kit(guid="kit-SP"))
    db.upsert_match(make_match(match_guid="sp1", test_guid="kit-SP", shared_cm=100.0))
    db.upsert_match(make_match(match_guid="sp2", test_guid="kit-SP", shared_cm=90.0))
    db.upsert_shared_match(make_shared(test_guid="kit-SP", match_guid_a="sp1",
                                       match_guid_b="sp2", shared_cm_b=50.0))
    db.upsert_shared_match(make_shared(test_guid="kit-SP", match_guid_a="sp2",
                                       match_guid_b="sp1", shared_cm_b=50.0))
    clusters = db.get_shared_clusters("kit-SP", min_cm=20.0, max_cm=400.0, min_size=2)
    assert len(clusters) == 1
    assert clusters[0]["size"] == 2


def test_get_shared_clusters_small_triangle_cluster(db):
    """Three mutually-shared matches collapse to a single cluster of size 3."""
    _build_cluster_data(db)
    clusters = db.get_shared_clusters("kit-CL", min_cm=20.0, max_cm=400.0, min_size=2)
    sizes = [c["size"] for c in clusters]
    assert 3 in sizes


def test_get_shared_clusters_cm_filter_excludes_small(db):
    """Matches below min_cm are excluded from cluster membership."""
    _build_cluster_data(db)
    # Add edge touching cl5 (30 cM) so it would be included if not filtered
    db.upsert_shared_match(make_shared(test_guid="kit-CL", match_guid_a="cl5",
                                       match_guid_b="cl1", shared_cm_b=25.0))
    db.upsert_shared_match(make_shared(test_guid="kit-CL", match_guid_a="cl1",
                                       match_guid_b="cl5", shared_cm_b=25.0))
    # min_cm=100 excludes cl5 (30 cM)
    clusters = db.get_shared_clusters("kit-CL", min_cm=100.0, max_cm=400.0, min_size=2)
    all_guids = {g for c in clusters for g, _, _ in c["members"]}
    assert "cl5" not in all_guids


def test_get_shared_clusters_min_size_filter(db):
    """min_size=4 excludes clusters with fewer than 4 members."""
    _build_cluster_data(db)
    clusters = db.get_shared_clusters("kit-CL", min_cm=20.0, max_cm=400.0, min_size=4)
    for c in clusters:
        assert c["size"] >= 4


# ===========================================================================
# 9. get_statistics (5 tests)
# NOTE: get_statistics(test_guid=...) has a SQL bug (double WHERE clause) in
# the implementation; we therefore call get_statistics() without test_guid
# and populate only the expected rows in each test's isolated database.
# ===========================================================================

def test_get_statistics_empty_db(db):
    """get_statistics on an empty database returns zero counts without crashing."""
    stats = db.get_statistics()
    assert stats["total"] == 0
    assert stats["shared_total"] == 0
    assert stats["ped_loaded"] == 0


def test_get_statistics_with_data(db):
    """get_statistics reflects correct totals and max_cm after inserting matches."""
    for i in range(5):
        db.upsert_match(make_match(match_guid=f"stat-{i}", test_guid="kit-ST",
                                   shared_cm=float(100 + i * 50)))
    stats = db.get_statistics()
    assert stats["total"] == 5
    assert stats["max_cm"] == pytest.approx(300.0)


def test_get_statistics_with_tree_count(db):
    """with_tree count correctly counts only matches that have has_tree=True."""
    db.upsert_match(make_match(match_guid="t1", test_guid="kit-TC",
                               has_tree=True, tree_size=50))
    db.upsert_match(make_match(match_guid="t2", test_guid="kit-TC",
                               has_tree=False))
    db.upsert_match(make_match(match_guid="t3", test_guid="kit-TC",
                               has_tree=True, tree_size=30))
    stats = db.get_statistics()
    assert stats["with_tree"] == 2


def test_get_statistics_shared_stats(db):
    """shared_total and shared_primary_count are tallied correctly."""
    db.upsert_match(make_match(match_guid="sst1", test_guid="kit-SS"))
    for i in range(4):
        sm = make_shared(test_guid="kit-SS", match_guid_a="sst1",
                         match_guid_b=f"ssb{i}", shared_cm_b=float(50 + i))
        db.upsert_shared_match(sm)
    stats = db.get_statistics()
    assert stats["shared_total"] == 4
    assert stats["shared_primary_count"] == 1


def test_get_statistics_pedigree_stats(db):
    """ped_loaded, ped_surnames and ped_avg_depth are computed from pedigree data."""
    db.upsert_match(make_match(match_guid="pst1", test_guid="kit-PS",
                               has_tree=True, shared_cm=200.0))
    db.upsert_match(make_match(match_guid="pst2", test_guid="kit-PS",
                               has_tree=True, shared_cm=150.0))
    db.save_match_pedigree("kit-PS", "pst1", _sample_pedigree_rows())
    db.save_match_pedigree("kit-PS", "pst2", _sample_pedigree_rows()[:1])
    stats = db.get_statistics()
    assert stats["ped_loaded"] == 2           # two distinct match_guids have gen>=2
    assert stats["ped_surnames"] >= 2         # at least Kovermann + Wapelhorst
    assert stats["ped_avg_depth"] > 0.0


# ===========================================================================
# 10. Edge cases / stress (2 tests)
# ===========================================================================

def test_bulk_upsert_500_matches_performance(db):
    """bulk_upsert 500 matches must complete in under 10 seconds."""
    matches = [
        make_match(
            match_guid=f"stress-{i:05d}",
            test_guid="kit-STRESS",
            display_name=f"Testperson {i} Müller-Kovermann",
            shared_cm=float(20 + (i % 600)),
            shared_segments=max(1, i % 20),
            longest_segment=float(10 + (i % 40)),
            predicted_relationship="2. Cousin",
        )
        for i in range(500)
    ]
    start = time.monotonic()
    count = db.bulk_upsert(matches)
    elapsed = time.monotonic() - start
    assert count == 500
    assert db.get_match_count("kit-STRESS") == 500
    assert elapsed < 10.0, f"bulk_upsert 500 took {elapsed:.1f}s – too slow"


def test_special_chars_in_names(db):
    """Names with German umlauts, apostrophes, and emoji round-trip without corruption."""
    db.upsert_kit(make_kit(guid="kit-UTF", name="Ångström–Ü König 🧬"))
    special_names = [
        ("sc-001", "Müller-Wäßler, Günther Björn"),
        ("sc-002", "O'Brien-Schäfer, Zoë"),
        ("sc-003", "Ü Ö Ä ß ñ ç é à"),
        ("sc-004", "Kovermann 🧬 DNA-Test"),
        ("sc-005", "D'Artagnan van der Waals"),
    ]
    for guid, name in special_names:
        db.upsert_match(make_match(match_guid=guid, test_guid="kit-UTF",
                                   display_name=name, shared_cm=99.0))

    results = db.get_matches(test_guid="kit-UTF")
    stored = {r.match_guid: r.display_name for r in results}
    for guid, name in special_names:
        assert stored[guid] == name, (
            f"Name corruption for {guid}: expected {name!r}, got {stored[guid]!r}"
        )
    # Verify note field also survives special characters
    db.update_note("sc-001", "Notiz: Äpfel & Birnen – 'Cousine' 2×entfernt 🌳")
    after = db.get_matches(test_guid="kit-UTF", search="Wäßler")
    assert after[0].note == "Notiz: Äpfel & Birnen – 'Cousine' 2×entfernt 🌳"
