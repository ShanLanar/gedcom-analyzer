"""Tests for ancestry.core.db.repos.shared — SharedRepo."""
from __future__ import annotations

import pytest
from ancestry.models import SharedMatch


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Fresh Database with full schema."""
    from ancestry.core.database import Database
    d = Database(str(tmp_path / "test.db"))
    # Register a kit and two matches so FK constraints are satisfied.
    with d._cursor() as cur:
        cur.execute(
            "INSERT INTO dna_kits (guid, name, source) VALUES (?,?,?)",
            ("kit-T1", "Test Kit", "ancestry"),
        )
        cur.execute(
            """INSERT INTO matches (match_guid, test_guid, display_name, shared_cm)
               VALUES (?,?,?,?)""",
            ("m-A", "kit-T1", "Alice", 120.0),
        )
        cur.execute(
            """INSERT INTO matches (match_guid, test_guid, display_name, shared_cm)
               VALUES (?,?,?,?)""",
            ("m-B", "kit-T1", "Bob", 85.0),
        )
    return d


def _sm(test_guid="kit-T1", guid_a="m-A", guid_b="m-B",
        cm_b=85.0, cm_ab=50.0, **kw) -> SharedMatch:
    return SharedMatch(
        test_guid=test_guid,
        match_guid_a=guid_a,
        match_guid_b=guid_b,
        display_name_b="Bob",
        shared_cm_b=cm_b,
        shared_cm_ab=cm_ab,
        shared_segments_b=2,
        relationship_b="3rd cousin",
        has_tree_b=0,
        fetched_at="2024-01-01T00:00:00+00:00",
        **kw,
    )


# ── upsert_shared_match ────────────────────────────────────────────────────────

class TestUpsertSharedMatch:
    def test_inserts_new_row(self, db):
        db.upsert_shared_match(_sm())
        assert db.get_shared_match_count("kit-T1", "m-A") == 1

    def test_upsert_updates_existing(self, db):
        db.upsert_shared_match(_sm(cm_b=85.0))
        db.upsert_shared_match(_sm(cm_b=90.0))
        result = db.get_shared_matches("kit-T1", "m-A")
        assert len(result) == 1
        assert result[0].shared_cm_b == pytest.approx(90.0)


# ── get_shared_match_count ────────────────────────────────────────────────────

class TestGetSharedMatchCount:
    def test_empty_returns_zero(self, db):
        assert db.get_shared_match_count("kit-T1") == 0

    def test_counts_correct_after_insert(self, db):
        db.upsert_shared_match(_sm())
        assert db.get_shared_match_count("kit-T1") == 1

    def test_counts_by_match_guid_a(self, db):
        db.upsert_shared_match(_sm(guid_a="m-A", guid_b="m-B"))
        # Add a second row with different guid_a; needs another match in DB first
        with db._cursor() as cur:
            cur.execute(
                """INSERT INTO matches (match_guid, test_guid, display_name, shared_cm)
                   VALUES (?,?,?,?)""",
                ("m-C", "kit-T1", "Carol", 60.0),
            )
        db.upsert_shared_match(_sm(guid_a="m-C", guid_b="m-B"))
        assert db.get_shared_match_count("kit-T1", "m-A") == 1
        assert db.get_shared_match_count("kit-T1", "m-C") == 1


# ── get_shared_matches ────────────────────────────────────────────────────────

class TestGetSharedMatches:
    def test_returns_shared_match_objects(self, db):
        db.upsert_shared_match(_sm())
        results = db.get_shared_matches("kit-T1", "m-A")
        assert len(results) == 1
        assert isinstance(results[0], SharedMatch)
        assert results[0].match_guid_b == "m-B"

    def test_min_cm_filter(self, db):
        db.upsert_shared_match(_sm(cm_b=10.0))
        results = db.get_shared_matches("kit-T1", "m-A", min_cm=20.0)
        assert len(results) == 0

    def test_default_sort_descending(self, db):
        with db._cursor() as cur:
            cur.execute(
                """INSERT INTO matches (match_guid, test_guid, display_name, shared_cm)
                   VALUES (?,?,?,?)""",
                ("m-D", "kit-T1", "Dave", 70.0),
            )
        db.upsert_shared_match(_sm(guid_b="m-B", cm_b=80.0))
        db.upsert_shared_match(_sm(guid_b="m-D", cm_b=120.0))
        results = db.get_shared_matches("kit-T1", "m-A")
        cms = [r.shared_cm_b for r in results]
        assert cms == sorted(cms, reverse=True)


# ── mark_shared_fetched / is_shared_fetched ───────────────────────────────────

class TestSharedFetched:
    def test_not_fetched_by_default(self, db):
        assert not db.is_shared_fetched("kit-T1", "m-A")

    def test_mark_and_check(self, db):
        db.mark_shared_fetched("kit-T1", "m-A", "2024-01-01T00:00:00+00:00")
        assert db.is_shared_fetched("kit-T1", "m-A")

    def test_different_guid_not_fetched(self, db):
        db.mark_shared_fetched("kit-T1", "m-A", "2024-01-01T00:00:00+00:00")
        assert not db.is_shared_fetched("kit-T1", "m-B")

    def test_mark_idempotent(self, db):
        db.mark_shared_fetched("kit-T1", "m-A", "2024-01-01")
        db.mark_shared_fetched("kit-T1", "m-A", "2024-06-01")
        assert db.is_shared_fetched("kit-T1", "m-A")


# ── delete_shared_for ─────────────────────────────────────────────────────────

class TestDeleteSharedFor:
    def test_deletes_rows_for_match(self, db):
        db.upsert_shared_match(_sm())
        db.delete_shared_for("kit-T1", "m-A")
        assert db.get_shared_match_count("kit-T1", "m-A") == 0

    def test_other_match_not_affected(self, db):
        with db._cursor() as cur:
            cur.execute(
                """INSERT INTO matches (match_guid, test_guid, display_name, shared_cm)
                   VALUES (?,?,?,?)""",
                ("m-C", "kit-T1", "Carol", 60.0),
            )
        db.upsert_shared_match(_sm(guid_a="m-A"))
        db.upsert_shared_match(_sm(guid_a="m-C"))
        db.delete_shared_for("kit-T1", "m-A")
        assert db.get_shared_match_count("kit-T1", "m-C") == 1


# ── reset_shared_matches ──────────────────────────────────────────────────────

class TestResetSharedMatches:
    def test_returns_count_deleted(self, db):
        db.upsert_shared_match(_sm())
        count = db.reset_shared_matches("kit-T1")
        assert count == 1

    def test_clears_all_shared_for_kit(self, db):
        with db._cursor() as cur:
            cur.execute(
                """INSERT INTO matches (match_guid, test_guid, display_name, shared_cm)
                   VALUES (?,?,?,?)""",
                ("m-C", "kit-T1", "Carol", 60.0),
            )
        db.upsert_shared_match(_sm(guid_a="m-A"))
        db.upsert_shared_match(_sm(guid_a="m-C"))
        db.reset_shared_matches("kit-T1")
        assert db.get_shared_match_count("kit-T1") == 0

    def test_clears_shared_fetched_too(self, db):
        db.mark_shared_fetched("kit-T1", "m-A", "2024-01-01")
        db.reset_shared_matches("kit-T1")
        assert not db.is_shared_fetched("kit-T1", "m-A")

    def test_empty_returns_zero(self, db):
        assert db.reset_shared_matches("kit-T1") == 0


# ── get_shared_pairs_set ──────────────────────────────────────────────────────

class TestGetSharedPairsSet:
    def test_empty_returns_empty_set(self, db):
        assert db.get_shared_pairs_set("kit-T1") == set()

    def test_returns_frozensets(self, db):
        db.upsert_shared_match(_sm())
        pairs = db.get_shared_pairs_set("kit-T1")
        assert len(pairs) == 1
        pair = next(iter(pairs))
        assert isinstance(pair, frozenset)
        assert "m-A" in pair
        assert "m-B" in pair


# ── bulk_upsert_shared ────────────────────────────────────────────────────────

class TestBulkUpsertShared:
    def test_bulk_inserts_multiple(self, db):
        with db._cursor() as cur:
            cur.execute(
                """INSERT INTO matches (match_guid, test_guid, display_name, shared_cm)
                   VALUES (?,?,?,?)""",
                ("m-C", "kit-T1", "Carol", 60.0),
            )
        items = [
            _sm(guid_b="m-B", cm_b=85.0),
            _sm(guid_b="m-C", cm_b=60.0),
        ]
        count = db.bulk_upsert_shared(items)
        assert count == 2
        assert db.get_shared_match_count("kit-T1", "m-A") == 2
