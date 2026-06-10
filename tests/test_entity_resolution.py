"""Tests for ancestry.core.entity_resolution — pure-logic and DB-layer functions."""
from __future__ import annotations

import sqlite3
import pytest

from ancestry.core.entity_resolution import (
    _ensure_schema,
    _get_or_create_entity,
    _assign,
    _add_candidate,
    _entity_for_source,
    _merge_entities,
    phase1a_bootstrap_persons,
    phase2_transitivity,
    _score_match,
    _extract_year,
    _role_for_entry_type,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


# ── _ensure_schema ─────────────────────────────────────────────────────────────

class TestEnsureSchema:
    def test_creates_required_tables(self, db):
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "entities" in tables
        assert "entity_assignments" in tables
        assert "entity_candidates" in tables

    def test_idempotent_no_error(self, db):
        _ensure_schema(db)  # second call must not raise

    def test_entities_has_merged_into_column(self, db):
        cols = {r[1] for r in db.execute("PRAGMA table_info(entities)").fetchall()}
        assert "merged_into" in cols


# ── _get_or_create_entity ──────────────────────────────────────────────────────

class TestGetOrCreateEntity:
    def test_returns_positive_integer(self, db):
        eid = _get_or_create_entity(db, "Anna Kovermann")
        assert isinstance(eid, int)
        assert eid > 0

    def test_each_call_creates_distinct_entity(self, db):
        e1 = _get_or_create_entity(db, "Max")
        e2 = _get_or_create_entity(db, "Max")
        assert e1 != e2

    def test_label_persisted(self, db):
        eid = _get_or_create_entity(db, "Testperson", notes="some notes")
        row = db.execute("SELECT label, notes FROM entities WHERE entity_id=?", (eid,)).fetchone()
        assert row["label"] == "Testperson"
        assert row["notes"] == "some notes"

    def test_empty_label_allowed(self, db):
        eid = _get_or_create_entity(db)
        assert eid > 0


# ── _assign ────────────────────────────────────────────────────────────────────

class TestAssign:
    def test_returns_true_on_first_insert(self, db):
        eid = _get_or_create_entity(db, "Anna")
        assert _assign(db, eid, "matches", "guid-001") is True

    def test_duplicate_returns_false(self, db):
        eid = _get_or_create_entity(db, "Anna")
        _assign(db, eid, "matches", "guid-001")
        assert _assign(db, eid, "matches", "guid-001") is False

    def test_different_roles_are_independent(self, db):
        eid = _get_or_create_entity(db, "Anna")
        r1 = _assign(db, eid, "matches", "guid-001", person_role="person")
        r2 = _assign(db, eid, "matches", "guid-001", person_role="mother")
        assert r1 and r2

    def test_confidence_stored(self, db):
        eid = _get_or_create_entity(db, "Hans")
        _assign(db, eid, "matches", "g1", confidence=0.85)
        db.commit()
        row = db.execute(
            "SELECT confidence FROM entity_assignments WHERE source_row_id='g1'"
        ).fetchone()
        assert abs(row["confidence"] - 0.85) < 0.01

    def test_assigned_by_stored(self, db):
        eid = _get_or_create_entity(db, "Lisa")
        _assign(db, eid, "matches", "g2", assigned_by="gedmatch_bridge")
        db.commit()
        row = db.execute(
            "SELECT assigned_by FROM entity_assignments WHERE source_row_id='g2'"
        ).fetchone()
        assert row["assigned_by"] == "gedmatch_bridge"


# ── _entity_for_source ─────────────────────────────────────────────────────────

class TestEntityForSource:
    def test_returns_correct_entity_id(self, db):
        eid = _get_or_create_entity(db, "Hans")
        _assign(db, eid, "matches", "guid-abc")
        db.commit()
        assert _entity_for_source(db, "matches", "guid-abc") == eid

    def test_missing_source_returns_none(self, db):
        assert _entity_for_source(db, "matches", "nonexistent") is None

    def test_inactive_assignment_not_returned(self, db):
        eid = _get_or_create_entity(db, "Inactive")
        _assign(db, eid, "matches", "guid-x")
        db.execute(
            "UPDATE entity_assignments SET is_active=0 WHERE entity_id=?", (eid,)
        )
        db.commit()
        assert _entity_for_source(db, "matches", "guid-x") is None

    def test_role_is_respected(self, db):
        eid = _get_or_create_entity(db, "Dual-role")
        _assign(db, eid, "matches", "guid-r", person_role="mother")
        db.commit()
        assert _entity_for_source(db, "matches", "guid-r", "mother") == eid
        assert _entity_for_source(db, "matches", "guid-r", "person") is None


# ── _add_candidate ─────────────────────────────────────────────────────────────

class TestAddCandidate:
    def test_inserts_candidate(self, db):
        result = _add_candidate(
            db,
            ("source_webtrees", "wt1", "person"),
            ("source_matrikula_entries", "m1", "child"),
            0.75,
            {"koeln_code": "4075"},
        )
        assert result is True
        cnt = db.execute("SELECT COUNT(*) FROM entity_candidates").fetchone()[0]
        assert cnt == 1

    def test_duplicate_returns_false(self, db):
        args = (
            ("source_webtrees", "wt1", "person"),
            ("source_matrikula_entries", "m1", "child"),
            0.75,
            {},
        )
        _add_candidate(db, *args)
        assert _add_candidate(db, *args) is False

    def test_canonical_order_applied(self, db):
        _add_candidate(
            db,
            ("z_table", "1", "person"),
            ("a_table", "1", "person"),
            0.8,
            {},
        )
        row = db.execute(
            "SELECT source_table_a, source_table_b FROM entity_candidates"
        ).fetchone()
        assert row["source_table_a"] == "a_table"
        assert row["source_table_b"] == "z_table"

    def test_evidence_stored_as_json(self, db):
        ev = {"type": "name_year_match", "year_a": 1850, "year_b": 1852}
        _add_candidate(
            db,
            ("source_webtrees", "wt2", "person"),
            ("source_matrikula_entries", "m2", "person"),
            0.80,
            ev,
        )
        import json
        row = db.execute("SELECT evidence FROM entity_candidates").fetchone()
        stored = json.loads(row["evidence"])
        assert stored["type"] == "name_year_match"
        assert stored["year_a"] == 1850


# ── _merge_entities ────────────────────────────────────────────────────────────

class TestMergeEntities:
    def test_assignments_transferred_to_keep(self, db):
        e_keep = _get_or_create_entity(db, "Keep")
        e_drop = _get_or_create_entity(db, "Drop")
        _assign(db, e_keep, "matches", "guid-1")
        _assign(db, e_drop, "matches", "guid-2")
        db.commit()
        _merge_entities(db, e_keep, e_drop, reason="test")
        db.commit()
        assert _entity_for_source(db, "matches", "guid-2") == e_keep

    def test_dropped_entity_marked_merged_into(self, db):
        e_keep = _get_or_create_entity(db, "Keep")
        e_drop = _get_or_create_entity(db, "Drop")
        db.commit()
        _merge_entities(db, e_keep, e_drop, reason="test")
        db.commit()
        row = db.execute(
            "SELECT merged_into FROM entities WHERE entity_id=?", (e_drop,)
        ).fetchone()
        assert row["merged_into"] == e_keep

    def test_drop_assignments_deactivated(self, db):
        e_keep = _get_or_create_entity(db, "Keep")
        e_drop = _get_or_create_entity(db, "Drop")
        _assign(db, e_drop, "matches", "guid-old")
        db.commit()
        _merge_entities(db, e_keep, e_drop, reason="test")
        db.commit()
        cnt = db.execute(
            "SELECT COUNT(*) FROM entity_assignments "
            "WHERE entity_id=? AND is_active=1", (e_drop,)
        ).fetchone()[0]
        assert cnt == 0

    def test_conflict_with_existing_keep_assignment_ignored(self, db):
        e_keep = _get_or_create_entity(db, "Keep")
        e_drop = _get_or_create_entity(db, "Drop")
        _assign(db, e_keep, "matches", "shared-guid")
        _assign(db, e_drop, "matches", "shared-guid")
        db.commit()
        _merge_entities(db, e_keep, e_drop, reason="test")
        db.commit()
        assert _entity_for_source(db, "matches", "shared-guid") == e_keep


# ── phase1a_bootstrap_persons ──────────────────────────────────────────────────

def _make_persons_table(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS persons (
            person_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            given_name      TEXT DEFAULT '',
            surname         TEXT DEFAULT '',
            gedcom_id       TEXT DEFAULT '',
            gedmatch_kit_id TEXT DEFAULT ''
        );
    """)


class TestPhase1aBootstrapPersons:
    def test_empty_persons_table(self, db):
        _make_persons_table(db)
        stats = phase1a_bootstrap_persons(db)
        assert stats["persons"] == 0
        assert stats["entities_new"] == 0

    def test_creates_one_entity_per_person(self, db):
        _make_persons_table(db)
        db.execute("INSERT INTO persons (given_name, surname) VALUES ('Anna', 'Kovermann')")
        db.execute("INSERT INTO persons (given_name, surname) VALUES ('Hans', 'Müller')")
        db.commit()
        stats = phase1a_bootstrap_persons(db)
        assert stats["persons"] == 2
        assert stats["entities_new"] == 2

    def test_idempotent_second_run_creates_no_new_entities(self, db):
        _make_persons_table(db)
        db.execute("INSERT INTO persons (given_name, surname) VALUES ('Anna', 'K')")
        db.commit()
        phase1a_bootstrap_persons(db)
        stats2 = phase1a_bootstrap_persons(db)
        assert stats2["entities_new"] == 0

    def test_dry_run_writes_nothing(self, db):
        _make_persons_table(db)
        db.execute("INSERT INTO persons (given_name, surname) VALUES ('Dry', 'Run')")
        db.commit()
        stats = phase1a_bootstrap_persons(db, dry_run=True)
        assert stats["persons"] == 1
        cnt = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        assert cnt == 0

    def test_missing_persons_table_returns_zero_stats(self, db):
        stats = phase1a_bootstrap_persons(db)
        assert stats == {"persons": 0, "entities_new": 0, "assignments": 0}

    def test_entity_label_is_full_name(self, db):
        _make_persons_table(db)
        db.execute("INSERT INTO persons (given_name, surname) VALUES ('Maria', 'Schmidt')")
        db.commit()
        phase1a_bootstrap_persons(db)
        row = db.execute("SELECT label FROM entities LIMIT 1").fetchone()
        assert row["label"] == "Maria Schmidt"

    def test_person_assigned_to_persons_source_table(self, db):
        _make_persons_table(db)
        db.execute("INSERT INTO persons (given_name, surname) VALUES ('Test', 'User')")
        db.commit()
        phase1a_bootstrap_persons(db)
        cnt = db.execute(
            "SELECT COUNT(*) FROM entity_assignments WHERE source_table='persons'"
        ).fetchone()[0]
        assert cnt == 1


# ── phase2_transitivity ────────────────────────────────────────────────────────

class TestPhase2Transitivity:
    def test_merges_two_entities_on_confirmed_candidate(self, db):
        e1 = _get_or_create_entity(db, "E1")
        e2 = _get_or_create_entity(db, "E2")
        _assign(db, e1, "source_webtrees", "wt1")
        _assign(db, e2, "source_matrikula_entries", "m1")
        db.execute("""
            INSERT INTO entity_candidates
            (source_table_a, source_row_id_a, person_role_a,
             source_table_b, source_row_id_b, person_role_b,
             confidence, status)
            VALUES ('source_matrikula_entries','m1','person',
                    'source_webtrees','wt1','person', 0.90, 'confirmed')
        """)
        db.commit()
        stats = phase2_transitivity(db)
        assert stats["merges"] == 1

    def test_no_merge_when_same_entity(self, db):
        e1 = _get_or_create_entity(db, "Solo")
        _assign(db, e1, "source_webtrees", "wt1")
        _assign(db, e1, "source_matrikula_entries", "m1")
        db.execute("""
            INSERT INTO entity_candidates
            (source_table_a, source_row_id_a, person_role_a,
             source_table_b, source_row_id_b, person_role_b,
             confidence, status)
            VALUES ('source_matrikula_entries','m1','person',
                    'source_webtrees','wt1','person', 0.90, 'confirmed')
        """)
        db.commit()
        stats = phase2_transitivity(db)
        assert stats["merges"] == 0

    def test_pending_candidate_not_merged(self, db):
        e1 = _get_or_create_entity(db, "E1")
        e2 = _get_or_create_entity(db, "E2")
        _assign(db, e1, "source_webtrees", "wt1")
        _assign(db, e2, "source_matrikula_entries", "m1")
        db.execute("""
            INSERT INTO entity_candidates
            (source_table_a, source_row_id_a, person_role_a,
             source_table_b, source_row_id_b, person_role_b,
             confidence, status)
            VALUES ('source_matrikula_entries','m1','person',
                    'source_webtrees','wt1','person', 0.90, 'pending')
        """)
        db.commit()
        stats = phase2_transitivity(db)
        assert stats["merges"] == 0

    def test_dry_run_counts_but_does_not_merge(self, db):
        e1 = _get_or_create_entity(db, "E1")
        e2 = _get_or_create_entity(db, "E2")
        _assign(db, e1, "source_webtrees", "wt1")
        _assign(db, e2, "source_matrikula_entries", "m1")
        db.execute("""
            INSERT INTO entity_candidates
            (source_table_a, source_row_id_a, person_role_a,
             source_table_b, source_row_id_b, person_role_b,
             confidence, status)
            VALUES ('source_matrikula_entries','m1','person',
                    'source_webtrees','wt1','person', 0.90, 'confirmed')
        """)
        db.commit()
        stats = phase2_transitivity(db, dry_run=True)
        assert stats["merges"] == 1
        # e2 should still exist separately
        assert _entity_for_source(db, "source_matrikula_entries", "m1") == e2


# ── _score_match ───────────────────────────────────────────────────────────────

class TestScoreMatch:
    def test_no_overlap_returns_zero(self):
        score, ev = _score_match("Anna Müller", None, None, "Hans Schmitt", None, None)
        assert score == 0.0
        assert ev == {}

    def test_substring_name_match_gives_partial_score(self):
        score, _ = _score_match("Anna Kovermann", None, None, "Kovermann", None, None)
        assert score >= 0.20

    def test_same_koeln_code_gives_base_score(self):
        score, ev = _score_match(
            "Müller", "0657", 1850, "Möller", "0657", 1855, max_year_diff=10
        )
        assert score >= 0.55
        assert ev.get("koeln_code") == "0657"

    def test_exact_year_boosts_score(self):
        score, _ = _score_match("Hans", "7650", 1800, "Hans", "7650", 1800)
        assert score >= 0.55 + 0.30

    def test_missing_year_penalizes(self):
        s_no_year, _ = _score_match("Hans", "7650", 1800, "Hans", "7650", None)
        s_with_year, _ = _score_match("Hans", "7650", 1800, "Hans", "7650", 1800)
        assert s_no_year < s_with_year

    def test_score_capped_at_1(self):
        score, _ = _score_match("Peter", "1000", 1750, "Peter", "1000", 1750)
        assert score <= 1.0

    def test_year_diff_beyond_max_no_year_bonus(self):
        s_close, _ = _score_match("Franz", "4075", 1800, "Franz", "4075", 1801, max_year_diff=5)
        s_far, _ = _score_match("Franz", "4075", 1800, "Franz", "4075", 1820, max_year_diff=5)
        assert s_close > s_far

    def test_different_koeln_code_falls_back_to_substring(self):
        score, ev = _score_match("Franz", "4075", None, "Franz Müller", "00", None)
        # "franz" in "franz müller" → substring match
        assert score >= 0.20


# ── _extract_year ──────────────────────────────────────────────────────────────

class TestExtractYear:
    def test_plain_four_digit_year(self):
        assert _extract_year("1850") == 1850

    def test_date_with_day_and_month_name(self):
        assert _extract_year("15 Mar 1892") == 1892

    def test_german_date_format(self):
        assert _extract_year("12. Jan. 1923") == 1923

    def test_none_input_returns_none(self):
        assert _extract_year(None) is None

    def test_empty_string_returns_none(self):
        assert _extract_year("") is None

    def test_no_four_digit_sequence_returns_none(self):
        assert _extract_year("unknown date") is None

    def test_year_at_end(self):
        assert _extract_year("ABT 1745") == 1745

    def test_year_with_slash(self):
        assert _extract_year("1899/1900") == 1899


# ── _role_for_entry_type ───────────────────────────────────────────────────────

class TestRoleForEntryType:
    def test_taufe_is_child(self):
        assert _role_for_entry_type("Taufe") == "child"

    def test_heirat_is_groom(self):
        assert _role_for_entry_type("Heirat") == "groom"

    def test_tod_is_deceased(self):
        assert _role_for_entry_type("Tod") == "deceased"

    def test_unknown_type_is_person(self):
        assert _role_for_entry_type("Geburt") == "person"

    def test_empty_string_is_person(self):
        assert _role_for_entry_type("") == "person"
