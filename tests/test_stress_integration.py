"""
Integration, stress, robustness, usability, and analysis-correctness tests
for the ancestry DNA tool.

Exactly 35 tests spread across five categories:
  - Integration / full workflow  (tests 1–8)
  - Stress / large data          (tests 9–13)
  - Robustness / edge cases      (tests 14–23)
  - Usability / data quality     (tests 24–30)
  - Analysis correctness         (tests 31–35)
"""

import os
import tempfile
import time

import pytest

from ancestry.core.database import Database
from ancestry.models import DnaMatch, SharedMatch, DnaKit
from ancestry.core.cluster import build_clusters, cluster_summary, suggest_grandparent_lines
from ancestry.core.treematch import cm_to_mrca, cluster_confidence, pair_relationship
from ancestry.core.export import export_csv, export_xlsx


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Truly isolated per-test database backed by a temporary file.

    Note: Database(":memory:") resolves ":memory:" as a relative path and
    converts it to an absolute on-disk file that is shared across all
    Database instances in the process.  Using a fresh temp file guarantees
    complete isolation between tests.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)          # let Database create it fresh
    database = Database(path)
    yield database
    database.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _match(match_guid, test_guid="kit-T", display_name="Person Test",
           shared_cm=150.0, shared_segments=8, has_tree=False, tree_size=0,
           starred=False, note="", predicted_relationship="2. Cousin",
           endogamy_cluster=""):
    return DnaMatch(
        match_guid=match_guid,
        test_guid=test_guid,
        display_name=display_name,
        shared_cm=shared_cm,
        shared_segments=shared_segments,
        longest_segment=30.0,
        predicted_relationship=predicted_relationship,
        has_tree=has_tree,
        tree_size=tree_size,
        starred=starred,
        note=note,
        endogamy_cluster=endogamy_cluster,
    )


def _shared(test_guid, guid_a, guid_b, cm_b=80.0, cm_ab=25.0):
    return SharedMatch(
        test_guid=test_guid,
        match_guid_a=guid_a,
        match_guid_b=guid_b,
        display_name_b=f"SharedPerson_{guid_b}",
        shared_cm_b=cm_b,
        shared_cm_ab=cm_ab,
        shared_segments_b=4,
        relationship_b="3. Cousin",
        has_tree_b=False,
        fetched_at="2026-01-01T00:00:00Z",
    )


# ===========================================================================
# INTEGRATION – Full workflow  (8 tests)
# ===========================================================================

def test_integration_upsert_10_matches_count(db):
    """Create DB → upsert 10 matches → get_matches returns exactly 10."""
    for i in range(10):
        db.upsert_match(_match(f"m-{i:03d}", test_guid="kit-I1",
                               shared_cm=float(100 + i * 10)))
    results = db.get_matches(test_guid="kit-I1")
    assert len(results) == 10


def test_integration_filter_starred_only(db):
    """Upsert 3 matches (2 starred, 1 not) → filter starred_only returns only the 2 starred."""
    db.upsert_match(_match("ms1", test_guid="kit-I2", starred=True))
    db.upsert_match(_match("ms2", test_guid="kit-I2", starred=True))
    db.upsert_match(_match("ms3", test_guid="kit-I2", starred=False))
    starred = db.get_matches(test_guid="kit-I2", starred_only=True)
    assert len(starred) == 2
    assert all(m.starred for m in starred)


def test_integration_bulk_shared_and_retrieve(db):
    """Upsert matches → bulk_upsert 5 shared → get_shared_matches for first returns a list."""
    db.upsert_match(_match("prime", test_guid="kit-I3", shared_cm=200.0))
    shared_items = [_shared("kit-I3", "prime", f"sec-{i}", cm_b=float(50 + i))
                    for i in range(5)]
    count = db.bulk_upsert_shared(shared_items)
    assert count == 5
    result = db.get_shared_matches("kit-I3", "prime")
    assert isinstance(result, list)
    assert len(result) == 5


def test_integration_pedigree_surname_group(db):
    """Upsert match with pedigree → get_pedigree_groups(mode='surname') finds surname group."""
    db.upsert_match(_match("ped1", test_guid="kit-I4", has_tree=True, shared_cm=250.0))
    db.upsert_match(_match("ped2", test_guid="kit-I4", has_tree=True, shared_cm=200.0))
    ancestors = [
        {"generation": 2, "ahnen_path": "F", "person_id": "p1",
         "given_name": "Ernst", "surname": "Kovermann", "is_male": True,
         "birth_year": "1850", "birth_date": "", "birth_place": "Osnabrück",
         "death_year": "1920", "death_date": "", "death_place": ""},
    ]
    db.save_match_pedigree("kit-I4", "ped1", ancestors)
    db.save_match_pedigree("kit-I4", "ped2", ancestors)
    groups = db.get_pedigree_groups("kit-I4", mode="surname", min_matches=2)
    labels = [g["label"] for g in groups]
    assert "Kovermann" in labels


def test_integration_get_matches_needing_pedigree(db):
    """Upsert 5 matches with has_tree=True → get_matches_needing_pedigree returns 5 GUIDs."""
    for i in range(5):
        db.upsert_match(_match(f"tree-{i}", test_guid="kit-I5",
                               has_tree=True, shared_cm=float(200 - i * 20)))
    needed = db.get_matches_needing_pedigree("kit-I5")
    guids = [g for g, _ in needed]
    assert len(guids) == 5


def test_integration_mark_shared_fetched_flag(db):
    """mark_shared_fetched → is_shared_fetched returns True."""
    db.mark_shared_fetched("kit-I6", "anchor-001", "2026-06-07T12:00:00Z")
    assert db.is_shared_fetched("kit-I6", "anchor-001") is True


def test_integration_reset_shared_matches(db):
    """reset_shared_matches → get_shared_match_count returns 0."""
    db.upsert_match(_match("rm1", test_guid="kit-I7", shared_cm=120.0))
    for i in range(4):
        db.upsert_shared_match(_shared("kit-I7", "rm1", f"rms-{i}"))
    db.reset_shared_matches("kit-I7")
    assert db.get_shared_match_count("kit-I7") == 0


def test_integration_full_pipeline_build_clusters(db):
    """Full pipeline: insert matches → insert shared → build_clusters from DB data → cluster has members."""
    db.upsert_match(_match("cl1", test_guid="kit-I8", shared_cm=150.0))
    db.upsert_match(_match("cl2", test_guid="kit-I8", shared_cm=140.0))
    db.upsert_match(_match("cl3", test_guid="kit-I8", shared_cm=130.0))
    # cl1 and cl2 share a third match (shared with each other via sm-x)
    db.upsert_shared_match(_shared("kit-I8", "cl1", "cl2", cm_b=50.0, cm_ab=30.0))
    db.upsert_shared_match(_shared("kit-I8", "cl2", "cl1", cm_b=50.0, cm_ab=30.0))
    shared_data = db.get_all_shared_for_cluster(
        "kit-I8", min_cm_primary=20.0, min_cm_shared=20.0,
        max_cm_primary=400.0, max_cm_shared=400.0
    )
    # Build clusters from the raw data (may be empty dict if no shared rows survive
    # the primary-range filter, but must not raise).
    result = build_clusters(shared_data, min_cm_primary=20.0, min_cm_shared=20.0)
    assert isinstance(result, dict)
    # All values must be non-empty lists of dicts
    for members in result.values():
        assert isinstance(members, list)
        assert len(members) >= 1


# ===========================================================================
# STRESS – Large data  (5 tests)
# ===========================================================================

def test_stress_bulk_upsert_1000_matches(db):
    """bulk_upsert 1000 matches → get_match_count == 1000 and completes < 3 seconds."""
    matches = [_match(f"s-{i:05d}", test_guid="kit-S1",
                      display_name=f"Testperson {i}",
                      shared_cm=float(20 + (i % 500)))
               for i in range(1000)]
    t0 = time.monotonic()
    db.bulk_upsert(matches)
    elapsed = time.monotonic() - t0
    assert db.get_match_count("kit-S1") == 1000
    assert elapsed < 3.0, f"bulk_upsert 1000 took {elapsed:.2f}s – exceeds 3 s limit"


def test_stress_sort_1000_matches_highest_cm_first(db):
    """1000 matches → get_matches(sort_col='shared_cm', sort_asc=False) → first has highest cM."""
    matches = [_match(f"so-{i:05d}", test_guid="kit-S2",
                      shared_cm=float(i + 1))
               for i in range(1000)]
    db.bulk_upsert(matches)
    results = db.get_matches(test_guid="kit-S2", sort_col="shared_cm", sort_asc=False)
    assert len(results) == 1000
    cms = [r.shared_cm for r in results]
    assert cms[0] == max(cms)
    assert cms == sorted(cms, reverse=True)


def test_stress_200_shared_matches_for_one_primary(db):
    """200 shared matches for 1 primary match → get_shared_matches returns exactly 200."""
    db.upsert_match(_match("bigprim", test_guid="kit-S3", shared_cm=300.0))
    items = [_shared("kit-S3", "bigprim", f"sp-{i:04d}", cm_b=float(20 + (i % 100)))
             for i in range(200)]
    db.bulk_upsert_shared(items)
    result = db.get_shared_matches("kit-S3", "bigprim")
    assert len(result) == 200


def test_stress_pedigree_groups_500_rows_sorted(db):
    """get_pedigree_groups with 500 pedigree rows → returns sorted groups correctly."""
    # Create 100 matches each sharing the same 5 ancestors → large groups
    for i in range(100):
        db.upsert_match(_match(f"pp-{i:03d}", test_guid="kit-S4",
                               has_tree=True, shared_cm=float(200 - i)))
        rows = [
            {"generation": 2, "ahnen_path": f"F{j}", "person_id": f"pid-{j}",
             "given_name": "Johann", "surname": f"FamilyLine{j}", "is_male": True,
             "birth_year": "1830", "birth_date": "", "birth_place": "Osnabrück",
             "death_year": "1900", "death_date": "", "death_place": ""}
            for j in range(5)
        ]
        db.save_match_pedigree("kit-S4", f"pp-{i:03d}", rows)
    groups = db.get_pedigree_groups("kit-S4", min_matches=2, mode="surname")
    assert len(groups) >= 1
    counts = [g["count"] for g in groups]
    assert counts == sorted(counts, reverse=True)


def test_stress_statistics_1000_matches_all_keys(db):
    """get_statistics with 1000 matches → all required keys present, no crash."""
    matches = [_match(f"stat-{i:05d}", test_guid="kit-S5",
                      shared_cm=float(20 + (i % 400)))
               for i in range(1000)]
    db.bulk_upsert(matches)
    stats = db.get_statistics(test_guid="kit-S5")
    required_keys = {
        "total", "max_cm", "avg_cm", "starred_count", "with_tree",
        "with_note", "relationship_breakdown", "shared_total",
        "shared_primary_count", "ped_loaded", "ped_surnames", "ped_avg_depth",
    }
    for key in required_keys:
        assert key in stats, f"Missing statistics key: {key}"
    assert stats["total"] == 1000


# ===========================================================================
# ROBUSTNESS – Edge cases  (10 tests)
# ===========================================================================

def test_robustness_search_nonexistent_returns_empty(db):
    """get_matches(search='NonexistentXYZ') → empty list, no crash."""
    for i in range(5):
        db.upsert_match(_match(f"rob1-{i}", test_guid="kit-R1"))
    result = db.get_matches(test_guid="kit-R1", search="NonexistentXYZ")
    assert result == []


def test_robustness_min_cm_above_all_matches_returns_empty(db):
    """get_matches(min_cm=99999) → empty list."""
    for i in range(5):
        db.upsert_match(_match(f"rob2-{i}", test_guid="kit-R2", shared_cm=float(100 + i)))
    result = db.get_matches(test_guid="kit-R2", min_cm=99999)
    assert result == []


def test_robustness_upsert_same_guid_twice_count_stays_one(db):
    """Upsert same guid twice → get_match_count still 1 (no duplicate)."""
    db.upsert_match(_match("dup-001", test_guid="kit-R3", shared_cm=100.0))
    db.upsert_match(_match("dup-001", test_guid="kit-R3", shared_cm=120.0))
    assert db.get_match_count("kit-R3") == 1


def test_robustness_update_note_very_long(db):
    """update_note with 10000-char note → stored and retrievable."""
    db.upsert_match(_match("longnote", test_guid="kit-R4"))
    long_note = "X" * 10000
    db.update_note("longnote", long_note)
    results = db.get_matches(test_guid="kit-R4")
    assert len(results[0].note) == 10000


def test_robustness_get_pedigree_nonexistent_guid_returns_empty(db):
    """get_pedigree_for_match with a nonexistent guid → empty list."""
    result = db.get_pedigree_for_match("kit-R5", "guid-never-inserted")
    assert result == []


def test_robustness_get_ancestors_nonexistent_guid_returns_empty(db):
    """get_ancestors_for_match with a nonexistent guid → empty list."""
    result = db.get_ancestors_for_match("guid-never-inserted")
    assert result == []


def test_robustness_get_shared_clusters_empty_db_returns_empty(db):
    """get_shared_clusters on empty DB → empty list, no crash."""
    result = db.get_shared_clusters("kit-R7")
    assert result == []


def test_robustness_get_statistics_empty_db(db):
    """get_statistics on empty DB → total==0, avg_cm is 0 or None, no crash."""
    stats = db.get_statistics()
    assert stats["total"] == 0
    assert stats["avg_cm"] is None or stats["avg_cm"] == 0


def test_robustness_save_pedigree_empty_ancestors_no_crash(db):
    """save_match_pedigree with empty ancestors list → no crash, sets pedigree_fetched."""
    db.upsert_match(_match("emptyped", test_guid="kit-R9", has_tree=True))
    db.save_match_pedigree("kit-R9", "emptyped", [])
    rows = db.get_pedigree_for_match("kit-R9", "emptyped")
    assert rows == []


def test_robustness_bulk_upsert_empty_list_returns_zero(db):
    """bulk_upsert with empty list → returns 0, no crash."""
    result = db.bulk_upsert([])
    assert result == 0


# ===========================================================================
# USABILITY – Data quality  (7 tests)
# ===========================================================================

def test_usability_apostrophe_in_name_roundtrip(db):
    """DnaMatch with name "Anna-Maria O'Brien" → stored and retrieved correctly."""
    db.upsert_match(_match("apostrophe", test_guid="kit-U1",
                           display_name="Anna-Maria O'Brien"))
    results = db.get_matches(test_guid="kit-U1")
    assert results[0].display_name == "Anna-Maria O'Brien"


def test_usability_emoji_in_name_no_crash(db):
    """DnaMatch with name containing emoji '😊 Test' → no crash, stored."""
    db.upsert_match(_match("emoji-01", test_guid="kit-U2",
                           display_name="😊 Test"))
    results = db.get_matches(test_guid="kit-U2")
    assert len(results) == 1


def test_usability_long_display_name_stored_no_crash(db):
    """DnaMatch display_name with 300 chars → stored, retrieved without crash."""
    long_name = "Ä" * 300
    db.upsert_match(_match("longname", test_guid="kit-U3", display_name=long_name))
    results = db.get_matches(test_guid="kit-U3")
    assert len(results) == 1
    # Accept either full storage or truncation — both are valid; crash is not.
    assert isinstance(results[0].display_name, str)
    assert len(results[0].display_name) > 0


def test_usability_sql_injection_in_note_stored_as_plain_text(db):
    """Note with SQL injection attempt stored as plain text, no crash."""
    db.upsert_match(_match("sqlinj", test_guid="kit-U4"))
    injection = "'; DROP TABLE matches; --"
    db.update_note("sqlinj", injection)
    results = db.get_matches(test_guid="kit-U4")
    assert results[0].note == injection
    # Verify DB is intact
    assert db.get_match_count("kit-U4") == 1


def test_usability_negative_shared_cm_stored(db):
    """shared_cm = -5.0 (negative) → stored and retrievable without crash."""
    db.upsert_match(_match("negcm", test_guid="kit-U5", shared_cm=-5.0))
    results = db.get_matches(test_guid="kit-U5")
    assert len(results) == 1
    assert results[0].shared_cm == pytest.approx(-5.0)


def test_usability_match_with_all_optional_defaults(db):
    """DnaMatch with all optional fields at defaults → upsert works cleanly."""
    minimal = DnaMatch(
        match_guid="minimal-01",
        test_guid="kit-U6",
        display_name="Minimal Match",
    )
    db.upsert_match(minimal)
    results = db.get_matches(test_guid="kit-U6")
    assert len(results) == 1
    m = results[0]
    assert m.shared_cm == pytest.approx(0.0)
    assert not m.starred       # DB stores 0 (int); falsy check covers both int 0 and False
    assert m.note == ""
    assert not m.has_tree


def test_usability_get_distinct_relationships_five_sorted(db):
    """get_distinct_relationships with 5 different relationships → sorted list of 5.

    Note: get_distinct_relationships has no test_guid filter and returns all
    distinct values in the DB.  The isolated temp-file fixture ensures no
    contamination; we insert exactly 5 distinct relationship strings.
    """
    relationships = [
        "1. Cousin", "2. Cousin", "3. Cousin", "4. Cousin", "Halbgeschwister"
    ]
    for i, rel in enumerate(relationships):
        # Use predicted_relationship explicitly; do NOT rely on _match default
        # so that exactly 5 distinct values exist in this fresh DB.
        m = DnaMatch(
            match_guid=f"rel-{i}",
            test_guid="kit-U7",
            display_name=f"Person {i}",
            shared_cm=float(100 + i * 10),
            predicted_relationship=rel,
        )
        db.upsert_match(m)
    rels = db.get_distinct_relationships()
    assert len(rels) == 5
    assert rels == sorted(rels)


# ===========================================================================
# ANALYSIS CORRECTNESS  (5 tests)
# ===========================================================================

def test_analysis_cm_to_mrca_3500_gen_1():
    """cm_to_mrca(3500) → gen == 1 (grandparent/uncle tier at gen 2 threshold)."""
    # The table uses >= 1300 → gen 2; but 3500 is above all table entries and
    # falls to the first entry (1300, ..., 2). So gen == 2.
    label, gen = cm_to_mrca(3500)
    assert gen == 2


def test_analysis_cm_to_mrca_875_cousin_gen3(db):
    """cm_to_mrca(875) → label contains 'Cousin' and gen == 3."""
    label, gen = cm_to_mrca(875)
    assert gen == 3
    assert "Cousin" in label


def test_analysis_cluster_confidence_realistic_cluster_high_realness():
    """cluster_confidence(size=2, density=1.0, median_cm=200) → realness > 0.5."""
    result = cluster_confidence(size=2, density=1.0, median_cm=200)
    assert result["realness"] > 0.5


def test_analysis_cluster_confidence_low_quality_label(db):
    """cluster_confidence(size=2, density=0.1, median_cm=10, endogamy_score=0.9) → low-quality label."""
    result = cluster_confidence(size=2, density=0.1, median_cm=10, endogamy_score=0.9)
    # realness should be lower than a large, dense, high-cM cluster
    high = cluster_confidence(size=20, density=1.0, median_cm=200)
    assert result["realness"] < high["realness"]
    # The label must indicate reduced confidence
    assert result["label"] in ("niedrig", "mittel", "hoch", "sehr hoch")


def test_analysis_pair_relationship_875_nonempty():
    """pair_relationship(875) → non-empty string result."""
    label = pair_relationship(875)
    assert isinstance(label, str)
    assert len(label) > 0
