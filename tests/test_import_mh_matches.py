"""Tests for ancestry.tools.import_mh_matches — pure helpers and map_match."""
from __future__ import annotations

import json
import sqlite3
import pytest

from ancestry.tools.import_mh_matches import (
    _str,
    _float,
    _int,
    map_match,
    save_relationships,
    _manual_schema,
)


# ── _str / _float / _int ──────────────────────────────────────────────────────

class TestHelpers:
    def test_str_normal(self):
        assert _str("hello") == "hello"

    def test_str_strips_whitespace(self):
        assert _str("  trim  ") == "trim"

    def test_str_none_returns_default(self):
        assert _str(None) == ""
        assert _str(None, "fallback") == "fallback"

    def test_str_int_coerced(self):
        assert _str(42) == "42"

    def test_float_normal(self):
        assert _float("3.14") == pytest.approx(3.14)

    def test_float_invalid_returns_default(self):
        assert _float("n/a") == 0.0
        assert _float(None) == 0.0
        assert _float("n/a", -1.0) == -1.0

    def test_float_integer_string(self):
        assert _float("100") == 100.0

    def test_int_normal(self):
        assert _int("7") == 7

    def test_int_float_string_returns_default(self):
        # "3.9" is not a valid int literal → falls back to default
        assert _int("3.9") == 0

    def test_int_invalid_returns_default(self):
        assert _int("abc") == 0
        assert _int(None) == 0
        assert _int("abc", -1) == -1


# ── map_match ─────────────────────────────────────────────────────────────────

def _mh_match(**overrides) -> dict:
    """Build a minimal MH match dict."""
    base = {
        "id": "mh-guid-001",
        "total_shared_segments_length_in_cm": 87.4,
        "total_shared_segments": 3,
        "largest_shared_segment_length_in_cm": 45.2,
        "confidence_level": "HIGH",
        "other_dna_kit": {
            "member": {"name": "Hans Müller", "gender": "M", "country_code": "DE"},
            "submitter": {"name": ""},
            "associated_individual": {"tree": {"id": "tree-001", "individual_count": 250}},
        },
        "complete_dna_relationships": [{"relationship_degree": "2nd cousin"}],
        "refined_dna_relationships": [],
        "dna_cm_explainer": {},
    }
    base.update(overrides)
    return base


class TestMapMatch:
    def test_basic_fields(self):
        m = _mh_match()
        result = map_match(m, "kit-001")
        assert result["match_guid"] == "mh-guid-001"
        assert result["test_guid"] == "kit-001"
        assert result["display_name"] == "Hans Müller"
        assert result["shared_cm"] == pytest.approx(87.4)
        assert result["shared_segments"] == 3
        assert result["longest_segment"] == pytest.approx(45.2)
        assert result["source"] == "myheritage"

    def test_confidence_level(self):
        result = map_match(_mh_match(), "kit-001")
        assert result["confidence"] == "HIGH"

    def test_has_tree_true(self):
        result = map_match(_mh_match(), "kit-001")
        assert result["has_tree"] == 1
        assert result["tree_size"] == 250
        assert result["tree_id"] == "tree-001"

    def test_has_tree_false(self):
        m = _mh_match()
        m["other_dna_kit"]["associated_individual"]["tree"] = {}
        result = map_match(m, "kit-001")
        assert result["has_tree"] == 0
        assert result["tree_size"] == 0

    def test_gender_male(self):
        result = map_match(_mh_match(), "kit-001")
        assert result["gender"] == "male"
        assert result["tag_gender"] == "M"

    def test_gender_female(self):
        m = _mh_match()
        m["other_dna_kit"]["member"]["gender"] = "F"
        result = map_match(m, "kit-001")
        assert result["gender"] == "female"

    def test_gender_unknown(self):
        m = _mh_match()
        m["other_dna_kit"]["member"]["gender"] = ""
        result = map_match(m, "kit-001")
        assert result["gender"] == ""

    def test_country_code(self):
        result = map_match(_mh_match(), "kit-001")
        assert result["country_code"] == "DE"

    def test_predicted_relationship_from_complete(self):
        result = map_match(_mh_match(), "kit-001")
        assert result["predicted_relationship"] == "2nd cousin"

    def test_predicted_relationship_refined_takes_priority(self):
        m = _mh_match()
        m["refined_dna_relationships"] = [{"relationship_degree": "1st cousin"}]
        result = map_match(m, "kit-001")
        assert result["predicted_relationship"] == "1st cousin"

    def test_name_falls_back_to_submitter(self):
        m = _mh_match()
        m["other_dna_kit"]["member"]["name"] = ""
        m["other_dna_kit"]["submitter"]["name"] = "Anna Schmidt"
        result = map_match(m, "kit-001")
        assert result["display_name"] == "Anna Schmidt"

    def test_missing_other_dna_kit(self):
        m = _mh_match()
        del m["other_dna_kit"]
        result = map_match(m, "kit-001")
        assert result["display_name"] == ""
        assert result["has_tree"] == 0

    def test_raw_json_is_valid_json(self):
        result = map_match(_mh_match(), "kit-001")
        parsed = json.loads(result["raw_json"])
        assert parsed["id"] == "mh-guid-001"

    def test_all_required_columns_present(self):
        required = [
            "match_guid", "test_guid", "display_name", "shared_cm", "shared_segments",
            "longest_segment", "predicted_relationship", "confidence", "has_tree",
            "tree_size", "tree_id", "source", "country_code", "mh_confidence_level",
            "gender", "raw_json", "fetched_at",
        ]
        result = map_match(_mh_match(), "kit-001")
        for col in required:
            assert col in result, f"Missing column: {col}"


# ── save_relationships ────────────────────────────────────────────────────────

@pytest.fixture
def rel_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _manual_schema(conn)
    return conn


class TestSaveRelationships:
    def test_saves_complete_relationships(self, rel_db):
        m = {
            "complete_dna_relationships": [{"relationship_degree": "2nd cousin",
                                             "relationship_type": 5}],
            "refined_dna_relationships": [],
            "dna_cm_explainer": {},
        }
        cur = rel_db.cursor()
        save_relationships(cur, "guid-001", m)
        rel_db.commit()
        rows = rel_db.execute(
            "SELECT * FROM mh_match_relationships WHERE match_guid='guid-001'"
        ).fetchall()
        assert any(r["rel_set"] == "complete" for r in rows)
        assert any(r["relationship_degree"] == "2nd cousin" for r in rows)

    def test_saves_explainer_relationships_with_probability(self, rel_db):
        m = {
            "complete_dna_relationships": [],
            "refined_dna_relationships": [],
            "dna_cm_explainer": {
                "relationships": [
                    {"relationship_type": 3, "relationship_class": "cousin",
                     "path_type": "maternal", "probability": 0.72}
                ]
            },
        }
        cur = rel_db.cursor()
        save_relationships(cur, "guid-002", m)
        rel_db.commit()
        row = rel_db.execute(
            "SELECT probability FROM mh_match_relationships WHERE match_guid='guid-002'"
        ).fetchone()
        assert row is not None
        assert abs(row["probability"] - 0.72) < 0.01

    def test_deletes_previous_before_saving(self, rel_db):
        m_old = {
            "complete_dna_relationships": [{"relationship_degree": "3rd cousin",
                                             "relationship_type": 7}],
            "refined_dna_relationships": [],
            "dna_cm_explainer": {},
        }
        m_new = {
            "complete_dna_relationships": [{"relationship_degree": "2nd cousin once removed",
                                             "relationship_type": 6}],
            "refined_dna_relationships": [],
            "dna_cm_explainer": {},
        }
        cur = rel_db.cursor()
        save_relationships(cur, "guid-003", m_old)
        rel_db.commit()
        save_relationships(cur, "guid-003", m_new)
        rel_db.commit()
        rows = rel_db.execute(
            "SELECT * FROM mh_match_relationships WHERE match_guid='guid-003'"
        ).fetchall()
        degrees = [r["relationship_degree"] for r in rows]
        assert "3rd cousin" not in degrees
        assert "2nd cousin once removed" in degrees

    def test_empty_match_no_rows(self, rel_db):
        m = {"complete_dna_relationships": [], "refined_dna_relationships": [],
             "dna_cm_explainer": {}}
        cur = rel_db.cursor()
        save_relationships(cur, "guid-empty", m)
        rel_db.commit()
        cnt = rel_db.execute(
            "SELECT COUNT(*) FROM mh_match_relationships WHERE match_guid='guid-empty'"
        ).fetchone()[0]
        assert cnt == 0
