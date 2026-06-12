"""
Comprehensive tests for MatchesRepo accessed through the Database facade.

Covers:
1.  upsert_match          – insert a new match, upsert again with updated fields
2.  bulk_upsert           – insert 5 matches at once, verify count returned
3.  get_matches           – filter by test_guid, min_cm, source
4.  match_exists          – true/false cases
5.  match_exists_for_kit  – correct kit isolation
6.  get_match_count       – total and per-kit
7.  update_note           – save and read back a note
8.  set_endogamy_cluster  – persists correctly
9.  set_probable_origin   – persists correctly
10. set_ml_origin         – persists correctly
11. bulk_set_side         – sets paternal_maternal on multiple matches
12. reset_name_attempts   – bumps attempts, then reset returns to 0
"""

import os
import tempfile

import pytest

from ancestry.core.database import Database
from ancestry.models import DnaMatch


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

KIT_GUID   = "TEST_KIT_001"
KIT_GUID_B = "TEST_KIT_002"


def make_match(
    match_guid: str = "MATCH_001",
    test_guid:  str = KIT_GUID,
    display_name: str = "Müller, Hans",
    shared_cm: float = 250.0,
    shared_segments: int = 12,
    longest_segment: float = 45.0,
    predicted_relationship: str = "2. Cousin",
    source: str = "ancestry",
    paternal_maternal: str = "",
    note: str = "",
    starred: bool = False,
) -> DnaMatch:
    return DnaMatch(
        match_guid=match_guid,
        test_guid=test_guid,
        display_name=display_name,
        shared_cm=shared_cm,
        shared_segments=shared_segments,
        longest_segment=longest_segment,
        predicted_relationship=predicted_relationship,
        source=source,
        paternal_maternal=paternal_maternal,
        note=note,
        starred=starred,
    )


# ---------------------------------------------------------------------------
# Fixture – fresh isolated database per test (tempfile, not :memory:)
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)   # let Database create it fresh
    database = Database(path)
    yield database
    database.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Helper: ensure a dna_kits row exists (some queries join on it)
# ---------------------------------------------------------------------------

def _ensure_kit(database: Database, guid: str = KIT_GUID):
    """Insert a minimal kit row so FK / join queries don't break."""
    from ancestry.models import DnaKit
    kit = DnaKit(guid=guid, name=f"Kit-{guid[:8]}", test_type="AncestryDNA")
    database.upsert_kit(kit)


# ===========================================================================
# 1. upsert_match – insert and idempotent update
# ===========================================================================

class TestUpsertMatch:

    def test_insert_new_match_roundtrip(self, db):
        """A freshly inserted match can be retrieved with correct field values."""
        _ensure_kit(db)
        m = make_match(match_guid="MATCH_001", display_name="Schmidt, Anna",
                       shared_cm=123.4, shared_segments=7)
        db.upsert_match(m)

        results = db.get_matches(test_guid=KIT_GUID)
        assert len(results) == 1
        r = results[0]
        assert r.match_guid == "MATCH_001"
        assert r.display_name == "Schmidt, Anna"
        assert r.shared_cm == pytest.approx(123.4)
        assert r.shared_segments == 7
        assert r.test_guid == KIT_GUID

    def test_upsert_updates_numeric_fields(self, db):
        """Re-upserting an existing match updates shared_cm and shared_segments."""
        _ensure_kit(db)
        m = make_match(match_guid="MATCH_002", shared_cm=100.0, shared_segments=5)
        db.upsert_match(m)

        m_updated = make_match(match_guid="MATCH_002", shared_cm=200.0, shared_segments=10)
        db.upsert_match(m_updated)

        results = db.get_matches(test_guid=KIT_GUID)
        assert len(results) == 1, "upsert must not create a duplicate row"
        assert results[0].shared_cm == pytest.approx(200.0)
        assert results[0].shared_segments == 10

    def test_upsert_updates_display_name_when_longer(self, db):
        """
        The ON CONFLICT logic updates display_name only when the new name
        is longer than 8 chars (Ancestry sometimes sends stub names first).
        """
        _ensure_kit(db)
        # First insert with a short (<=8 chars) stub name
        m1 = make_match(match_guid="MATCH_003", display_name="StubName")  # 8 chars
        db.upsert_match(m1)
        # Second upsert with a longer real name
        m2 = make_match(match_guid="MATCH_003", display_name="Musterfrau, Karoline")
        db.upsert_match(m2)

        results = db.get_matches(test_guid=KIT_GUID)
        assert results[0].display_name == "Musterfrau, Karoline"

    def test_upsert_preserves_paternal_maternal_when_set(self, db):
        """
        paternal_maternal set by a first upsert must NOT be overwritten
        by a subsequent upsert that sends an empty string.
        """
        _ensure_kit(db)
        m = make_match(match_guid="MATCH_004", paternal_maternal="maternal")
        db.upsert_match(m)

        m_no_side = make_match(match_guid="MATCH_004", paternal_maternal="")
        db.upsert_match(m_no_side)

        results = db.get_matches(test_guid=KIT_GUID)
        assert results[0].paternal_maternal == "maternal"

    def test_upsert_creates_kit_membership_row(self, db):
        """upsert_match must also insert a match_kit_membership record."""
        _ensure_kit(db)
        m = make_match(match_guid="MATCH_005")
        db.upsert_match(m)

        assert db.match_exists_for_kit("MATCH_005", KIT_GUID) is True

    def test_upsert_auto_creates_dna_kits_row(self, db):
        """
        upsert_match inserts a dna_kits stub when the kit doesn't exist yet,
        so we don't need to call upsert_kit first.
        """
        # Deliberately do NOT call _ensure_kit
        m = make_match(test_guid="AUTO_KIT_X99", match_guid="MATCH_X01")
        db.upsert_match(m)

        assert db.match_exists("MATCH_X01")


# ===========================================================================
# 2. bulk_upsert – insert 5 matches, verify count
# ===========================================================================

class TestBulkUpsert:

    def test_bulk_upsert_returns_correct_count(self, db):
        """bulk_upsert should return the number of matches processed."""
        _ensure_kit(db)
        matches = [
            make_match(match_guid=f"BULK_{i:03d}", shared_cm=float(100 + i * 10))
            for i in range(5)
        ]
        count = db.bulk_upsert(matches)
        assert count == 5

    def test_bulk_upsert_all_rows_persisted(self, db):
        """All 5 matches inserted via bulk_upsert can be retrieved."""
        _ensure_kit(db)
        matches = [
            make_match(match_guid=f"BULK_{i:03d}", shared_cm=float(50 + i))
            for i in range(5)
        ]
        db.bulk_upsert(matches)
        results = db.get_matches(test_guid=KIT_GUID)
        assert len(results) == 5

    def test_bulk_upsert_idempotent(self, db):
        """Calling bulk_upsert twice with the same list must not duplicate rows."""
        _ensure_kit(db)
        matches = [make_match(match_guid=f"BU_{i}", shared_cm=10.0) for i in range(3)]
        db.bulk_upsert(matches)
        db.bulk_upsert(matches)
        results = db.get_matches(test_guid=KIT_GUID)
        assert len(results) == 3


# ===========================================================================
# 3. get_matches – filtering
# ===========================================================================

class TestGetMatches:

    def _insert_sample_set(self, db):
        """Insert 4 matches with varying properties for filter tests."""
        _ensure_kit(db, KIT_GUID)
        _ensure_kit(db, KIT_GUID_B)
        matches = [
            make_match("M_HIGH",    KIT_GUID,   "Richter, Berta",  shared_cm=800.0,
                       source="ancestry"),
            make_match("M_MED",     KIT_GUID,   "Weber, Klaus",    shared_cm=350.0,
                       source="ancestry"),
            make_match("M_LOW",     KIT_GUID,   "Braun, Liesel",   shared_cm=50.0,
                       source="ancestry"),
            make_match("M_OTHER",   KIT_GUID_B, "Schulz, Werner",  shared_cm=200.0,
                       source="myheritage"),
        ]
        db.bulk_upsert(matches)

    def test_filter_by_test_guid(self, db):
        self._insert_sample_set(db)
        results = db.get_matches(test_guid=KIT_GUID)
        guids = {m.match_guid for m in results}
        assert guids == {"M_HIGH", "M_MED", "M_LOW"}
        assert "M_OTHER" not in guids

    def test_filter_by_other_test_guid(self, db):
        self._insert_sample_set(db)
        results = db.get_matches(test_guid=KIT_GUID_B)
        assert len(results) == 1
        assert results[0].match_guid == "M_OTHER"

    def test_no_filter_returns_all(self, db):
        self._insert_sample_set(db)
        results = db.get_matches()
        assert len(results) == 4

    def test_filter_by_min_cm(self, db):
        self._insert_sample_set(db)
        results = db.get_matches(test_guid=KIT_GUID, min_cm=300.0)
        guids = {m.match_guid for m in results}
        assert "M_HIGH" in guids
        assert "M_MED" in guids
        assert "M_LOW" not in guids

    def test_filter_by_min_cm_exact_boundary(self, db):
        """min_cm filter uses >=, so boundary value must be included."""
        self._insert_sample_set(db)
        results = db.get_matches(test_guid=KIT_GUID, min_cm=350.0)
        guids = {m.match_guid for m in results}
        assert "M_MED" in guids
        assert "M_LOW" not in guids

    def test_filter_by_source_ancestry(self, db):
        """upsert_match now persists DnaMatch.source. Filtering source='ancestry'
        returns only the three rows that were inserted with source='ancestry'."""
        self._insert_sample_set(db)
        results = db.get_matches(source="ancestry")
        guids = {m.match_guid for m in results}
        assert guids == {"M_HIGH", "M_MED", "M_LOW"}
        assert "M_OTHER" not in guids  # M_OTHER has source='myheritage'

    def test_filter_by_source_nonexistent_returns_empty(self, db):
        """upsert_match persists source; filtering 'nonexistent' returns no rows."""
        self._insert_sample_set(db)
        results = db.get_matches(source="nonexistent")
        assert results == []

    def test_filter_by_source_myheritage(self, db):
        """M_OTHER was inserted with source='myheritage'; filter should find it."""
        self._insert_sample_set(db)
        results = db.get_matches(source="myheritage")
        assert len(results) == 1
        assert results[0].match_guid == "M_OTHER"

    def test_filter_by_source_directly_written(self, db):
        """
        When source is written directly to the DB (bypassing upsert_match),
        the source filter works as expected.
        """
        self._insert_sample_set(db)
        # Directly update one row's source so we can test the filter path
        with db._cursor() as cur:
            cur.execute(
                "UPDATE matches SET source='myheritage' WHERE match_guid='M_OTHER'"
            )
        results_mh = db.get_matches(source="myheritage")
        assert len(results_mh) == 1
        assert results_mh[0].match_guid == "M_OTHER"

        results_anc = db.get_matches(source="ancestry")
        mh_guid_in_anc = "M_OTHER" in {m.match_guid for m in results_anc}
        assert not mh_guid_in_anc

    def test_results_sorted_by_shared_cm_desc_by_default(self, db):
        self._insert_sample_set(db)
        results = db.get_matches(test_guid=KIT_GUID)
        cms = [m.shared_cm for m in results]
        assert cms == sorted(cms, reverse=True)

    def test_filter_returns_empty_list_when_no_match(self, db):
        self._insert_sample_set(db)
        results = db.get_matches(test_guid="NONEXISTENT_KIT")
        assert results == []

    def test_filter_min_cm_higher_than_all(self, db):
        self._insert_sample_set(db)
        results = db.get_matches(test_guid=KIT_GUID, min_cm=9999.0)
        assert results == []


# ===========================================================================
# 4. match_exists – true/false cases
# ===========================================================================

class TestMatchExists:

    def test_returns_true_for_existing_match(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="EX_001"))
        assert db.match_exists("EX_001") is True

    def test_returns_false_for_nonexistent_match(self, db):
        assert db.match_exists("GHOST_999") is False

    def test_false_after_only_other_matches_inserted(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="EX_002"))
        assert db.match_exists("EX_001") is False


# ===========================================================================
# 5. match_exists_for_kit – kit isolation
# ===========================================================================

class TestMatchExistsForKit:

    def test_returns_true_for_correct_kit(self, db):
        _ensure_kit(db, KIT_GUID)
        db.upsert_match(make_match(match_guid="KIT_M_001", test_guid=KIT_GUID))
        assert db.match_exists_for_kit("KIT_M_001", KIT_GUID) is True

    def test_returns_false_for_wrong_kit(self, db):
        _ensure_kit(db, KIT_GUID)
        _ensure_kit(db, KIT_GUID_B)
        db.upsert_match(make_match(match_guid="KIT_M_001", test_guid=KIT_GUID))
        # match exists, but not for KIT_GUID_B
        assert db.match_exists_for_kit("KIT_M_001", KIT_GUID_B) is False

    def test_returns_false_for_nonexistent_match(self, db):
        assert db.match_exists_for_kit("GHOST_777", KIT_GUID) is False

    def test_same_match_in_two_kits(self, db):
        """If the same match_guid is upserted under two different kits, both should be found."""
        _ensure_kit(db, KIT_GUID)
        _ensure_kit(db, KIT_GUID_B)
        db.upsert_match(make_match(match_guid="SHARED_M", test_guid=KIT_GUID))
        db.upsert_match(make_match(match_guid="SHARED_M", test_guid=KIT_GUID_B))
        assert db.match_exists_for_kit("SHARED_M", KIT_GUID) is True
        assert db.match_exists_for_kit("SHARED_M", KIT_GUID_B) is True


# ===========================================================================
# 6. get_match_count – total and per-kit
# ===========================================================================

class TestGetMatchCount:

    def _seed(self, db):
        _ensure_kit(db, KIT_GUID)
        _ensure_kit(db, KIT_GUID_B)
        for i in range(3):
            db.upsert_match(make_match(f"CNT_A_{i}", test_guid=KIT_GUID))
        for i in range(2):
            db.upsert_match(make_match(f"CNT_B_{i}", test_guid=KIT_GUID_B))

    def test_total_count(self, db):
        self._seed(db)
        assert db.get_match_count() == 5

    def test_per_kit_count_kit_a(self, db):
        self._seed(db)
        assert db.get_match_count(test_guid=KIT_GUID) == 3

    def test_per_kit_count_kit_b(self, db):
        self._seed(db)
        assert db.get_match_count(test_guid=KIT_GUID_B) == 2

    def test_count_empty_db(self, db):
        assert db.get_match_count() == 0

    def test_per_kit_count_nonexistent_kit(self, db):
        self._seed(db)
        assert db.get_match_count(test_guid="NO_SUCH_KIT") == 0


# ===========================================================================
# 7. update_note – save and read back
# ===========================================================================

class TestUpdateNote:

    def test_note_is_persisted_on_match(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="NOTE_001"))
        db.update_note("NOTE_001", "My test note")

        results = db.get_matches(test_guid=KIT_GUID)
        assert results[0].note == "My test note"

    def test_note_can_be_overwritten(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="NOTE_002"))
        db.update_note("NOTE_002", "First note")
        db.update_note("NOTE_002", "Updated note")

        results = db.get_matches(test_guid=KIT_GUID)
        assert results[0].note == "Updated note"

    def test_note_written_to_user_notes_table(self, db):
        """update_note also persists a row in user_notes for audit trail."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="NOTE_003"))
        db.update_note("NOTE_003", "Audit note")

        # Directly query the user_notes table
        with db._cursor() as cur:
            cur.execute("SELECT note FROM user_notes WHERE match_guid='NOTE_003'")
            row = cur.fetchone()
        assert row is not None
        assert row[0] == "Audit note"

    def test_note_upsert_in_user_notes(self, db):
        """Calling update_note twice must not create duplicate rows in user_notes."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="NOTE_004"))
        db.update_note("NOTE_004", "v1")
        db.update_note("NOTE_004", "v2")

        with db._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user_notes WHERE match_guid='NOTE_004'")
            count = cur.fetchone()[0]
        assert count == 1

    def test_initial_note_empty_string(self, db):
        """Before update_note is called, note should be empty."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="NOTE_005", note=""))
        results = db.get_matches(test_guid=KIT_GUID)
        assert results[0].note == ""


# ===========================================================================
# 8. set_endogamy_cluster – persists correctly
# ===========================================================================

class TestSetEndogamyCluster:

    def test_sets_endogamy_cluster(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ENDO_001"))
        db.set_endogamy_cluster("ENDO_001", "Ostercappeln/Seymour")

        with db._cursor() as cur:
            cur.execute("SELECT endogamy_cluster FROM matches WHERE match_guid='ENDO_001'")
            row = cur.fetchone()
        assert row[0] == "Ostercappeln/Seymour"

    def test_endogamy_cluster_stripped(self, db):
        """Leading/trailing whitespace should be stripped."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ENDO_002"))
        db.set_endogamy_cluster("ENDO_002", "  cluster-X  ")

        with db._cursor() as cur:
            cur.execute("SELECT endogamy_cluster FROM matches WHERE match_guid='ENDO_002'")
            row = cur.fetchone()
        assert row[0] == "cluster-X"

    def test_endogamy_cluster_overwrite(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ENDO_003"))
        db.set_endogamy_cluster("ENDO_003", "first-cluster")
        db.set_endogamy_cluster("ENDO_003", "second-cluster")

        with db._cursor() as cur:
            cur.execute("SELECT endogamy_cluster FROM matches WHERE match_guid='ENDO_003'")
            row = cur.fetchone()
        assert row[0] == "second-cluster"

    def test_hide_endogamy_filter(self, db):
        """get_matches(hide_endogamy=True) should exclude matches with a cluster."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ENDO_010"))
        db.upsert_match(make_match(match_guid="ENDO_011"))
        db.set_endogamy_cluster("ENDO_010", "EastEurope")

        results = db.get_matches(test_guid=KIT_GUID, hide_endogamy=True)
        guids = {m.match_guid for m in results}
        assert "ENDO_011" in guids
        assert "ENDO_010" not in guids


# ===========================================================================
# 9. set_probable_origin – persists correctly
# ===========================================================================

class TestSetProbableOrigin:

    def test_sets_probable_origin(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ORIG_001"))
        db.set_probable_origin("ORIG_001", '{"region": "Germany"}')

        with db._cursor() as cur:
            cur.execute("SELECT probable_origin FROM matches WHERE match_guid='ORIG_001'")
            row = cur.fetchone()
        assert row[0] == '{"region": "Germany"}'

    def test_probable_origin_overwrite(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ORIG_002"))
        db.set_probable_origin("ORIG_002", '{"region": "Poland"}')
        db.set_probable_origin("ORIG_002", '{"region": "Austria"}')

        with db._cursor() as cur:
            cur.execute("SELECT probable_origin FROM matches WHERE match_guid='ORIG_002'")
            row = cur.fetchone()
        assert row[0] == '{"region": "Austria"}'

    def test_probable_origin_empty_string(self, db):
        """Setting an empty string should work without errors."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ORIG_003"))
        db.set_probable_origin("ORIG_003", "")

        with db._cursor() as cur:
            cur.execute("SELECT probable_origin FROM matches WHERE match_guid='ORIG_003'")
            row = cur.fetchone()
        assert row[0] == ""


# ===========================================================================
# 10. set_ml_origin – persists correctly
# ===========================================================================

class TestSetMlOrigin:

    def test_sets_ml_origin(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ML_001"))
        db.set_ml_origin("ML_001", '{"confidence": 0.92, "label": "Central European"}')

        with db._cursor() as cur:
            cur.execute("SELECT ml_origin FROM matches WHERE match_guid='ML_001'")
            row = cur.fetchone()
        assert row[0] == '{"confidence": 0.92, "label": "Central European"}'

    def test_ml_origin_overwrite(self, db):
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ML_002"))
        db.set_ml_origin("ML_002", '{"label": "v1"}')
        db.set_ml_origin("ML_002", '{"label": "v2"}')

        with db._cursor() as cur:
            cur.execute("SELECT ml_origin FROM matches WHERE match_guid='ML_002'")
            row = cur.fetchone()
        assert row[0] == '{"label": "v2"}'

    def test_ml_origin_independent_from_probable_origin(self, db):
        """ml_origin and probable_origin are separate columns."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ML_003"))
        db.set_probable_origin("ML_003", '{"region": "Spain"}')
        db.set_ml_origin("ML_003", '{"region": "France"}')

        with db._cursor() as cur:
            cur.execute(
                "SELECT probable_origin, ml_origin FROM matches WHERE match_guid='ML_003'"
            )
            row = cur.fetchone()
        assert row[0] == '{"region": "Spain"}'
        assert row[1] == '{"region": "France"}'


# ===========================================================================
# 11. bulk_set_side – sets paternal_maternal, returns affected count
# ===========================================================================

class TestBulkSetSide:

    def _insert_five(self, db):
        _ensure_kit(db)
        guids = [f"SIDE_{i:03d}" for i in range(5)]
        for g in guids:
            db.upsert_match(make_match(match_guid=g))
        return guids

    def test_sets_paternal_on_all_specified_guids(self, db):
        guids = self._insert_five(db)
        affected = db.bulk_set_side(guids[:3], "paternal")
        assert affected == 3

        with db._cursor() as cur:
            cur.execute(
                "SELECT match_guid, paternal_maternal FROM matches "
                "WHERE match_guid IN ('SIDE_000','SIDE_001','SIDE_002')"
            )
            rows = {r[0]: r[1] for r in cur.fetchall()}
        assert all(v == "paternal" for v in rows.values())

    def test_sets_maternal_on_specified_guids(self, db):
        guids = self._insert_five(db)
        db.bulk_set_side(guids[2:], "maternal")

        with db._cursor() as cur:
            cur.execute(
                "SELECT paternal_maternal FROM matches WHERE match_guid='SIDE_002'"
            )
            row = cur.fetchone()
        assert row[0] == "maternal"

    def test_unspecified_guids_are_unchanged(self, db):
        guids = self._insert_five(db)
        db.bulk_set_side(guids[:2], "paternal")

        with db._cursor() as cur:
            cur.execute(
                "SELECT paternal_maternal FROM matches WHERE match_guid='SIDE_004'"
            )
            row = cur.fetchone()
        # SIDE_004 was not in the list → should still be empty/null
        assert row[0] in (None, "")

    def test_empty_list_returns_zero(self, db):
        affected = db.bulk_set_side([], "paternal")
        assert affected == 0

    def test_returns_length_of_input_list(self, db):
        guids = self._insert_five(db)
        result = db.bulk_set_side(guids, "both")
        assert result == len(guids)

    def test_side_readable_via_get_matches(self, db):
        guids = self._insert_five(db)
        db.bulk_set_side([guids[0]], "paternal")

        results = db.get_matches(test_guid=KIT_GUID)
        match = next(m for m in results if m.match_guid == "SIDE_000")
        assert match.paternal_maternal == "paternal"


# ===========================================================================
# 12. reset_name_attempts – bump then reset
# ===========================================================================

class TestResetNameAttempts:

    def test_reset_returns_row_count(self, db):
        """reset_name_attempts returns the number of rows updated."""
        _ensure_kit(db)
        guids = [f"ATT_{i}" for i in range(4)]
        for g in guids:
            db.upsert_match(make_match(match_guid=g, test_guid=KIT_GUID))

        # Bump attempts on all 4
        db.bump_name_attempts(KIT_GUID, guids)

        # Reset should touch all 4 rows with test_guid=KIT_GUID
        count = db.reset_name_attempts(KIT_GUID)
        assert count == 4

    def test_name_attempts_are_zero_after_reset(self, db):
        _ensure_kit(db)
        guids = ["ATT_X1", "ATT_X2"]
        for g in guids:
            db.upsert_match(make_match(match_guid=g, test_guid=KIT_GUID))

        db.bump_name_attempts(KIT_GUID, guids)

        # Verify attempts were bumped
        with db._cursor() as cur:
            cur.execute(
                "SELECT name_attempts FROM matches WHERE match_guid='ATT_X1'"
            )
            before = cur.fetchone()[0]
        assert before >= 1

        # Now reset
        db.reset_name_attempts(KIT_GUID)

        with db._cursor() as cur:
            cur.execute(
                "SELECT name_attempts FROM matches WHERE match_guid IN ('ATT_X1','ATT_X2')"
            )
            rows = cur.fetchall()
        assert all(r[0] == 0 for r in rows)

    def test_reset_does_not_affect_other_kit(self, db):
        """reset_name_attempts for KIT_A must not touch matches of KIT_B."""
        _ensure_kit(db, KIT_GUID)
        _ensure_kit(db, KIT_GUID_B)
        db.upsert_match(make_match(match_guid="ATT_A1", test_guid=KIT_GUID))
        db.upsert_match(make_match(match_guid="ATT_B1", test_guid=KIT_GUID_B))

        db.bump_name_attempts(KIT_GUID,   ["ATT_A1"])
        db.bump_name_attempts(KIT_GUID_B, ["ATT_B1"])

        db.reset_name_attempts(KIT_GUID)   # only resets KIT_GUID

        with db._cursor() as cur:
            cur.execute(
                "SELECT name_attempts FROM matches WHERE match_guid='ATT_B1'"
            )
            row = cur.fetchone()
        assert row[0] >= 1, "ATT_B1 should still have a non-zero attempt count"

    def test_multiple_bumps_accumulate(self, db):
        """bump_name_attempts adds 1 each call; multiple calls must accumulate."""
        _ensure_kit(db)
        db.upsert_match(make_match(match_guid="ATT_ACC", test_guid=KIT_GUID))

        for _ in range(3):
            db.bump_name_attempts(KIT_GUID, ["ATT_ACC"])

        with db._cursor() as cur:
            cur.execute(
                "SELECT name_attempts FROM matches WHERE match_guid='ATT_ACC'"
            )
            row = cur.fetchone()
        assert row[0] == 3

    def test_reset_on_empty_kit_returns_zero(self, db):
        """reset_name_attempts for a kit with no matches should return 0."""
        count = db.reset_name_attempts("EMPTY_KIT_XYZ")
        assert count == 0
