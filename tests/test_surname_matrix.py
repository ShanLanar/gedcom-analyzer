"""Tests for ancestry.core.surname_matrix."""
from __future__ import annotations

import pytest

from ancestry.core.surname_matrix import (
    _normalize_surname,
    common_surnames,
    compute_surname_pairs,
    get_match_surnames,
    jaccard,
)


# ---------------------------------------------------------------------------
# _normalize_surname
# ---------------------------------------------------------------------------

class TestNormalizeSurname:
    def test_lowercases(self):
        assert _normalize_surname("Müller") == "müller"

    def test_strips_whitespace(self):
        assert _normalize_surname("  Schmidt  ") == "schmidt"

    def test_collapses_internal_whitespace(self):
        assert _normalize_surname("van  den  Berg") == "van den berg"


# ---------------------------------------------------------------------------
# jaccard
# ---------------------------------------------------------------------------

class TestJaccard:
    def test_both_empty_returns_zero(self):
        assert jaccard(frozenset(), frozenset()) == 0.0

    def test_one_empty_returns_zero(self):
        assert jaccard(frozenset({"müller"}), frozenset()) == 0.0

    def test_identical_sets_returns_one(self):
        s = frozenset({"müller", "schmidt", "meier"})
        assert jaccard(s, s) == 1.0

    def test_disjoint_sets_returns_zero(self):
        a = frozenset({"müller"})
        b = frozenset({"schmidt"})
        assert jaccard(a, b) == 0.0

    def test_partial_overlap(self):
        a = frozenset({"a", "b", "c"})
        b = frozenset({"b", "c", "d"})
        # intersection=2, union=4 → 0.5
        assert jaccard(a, b) == 0.5

    def test_result_rounded_to_4_places(self):
        a = frozenset({"a", "b", "c"})
        b = frozenset({"a"})
        # 1/3 = 0.3333…  → rounded to 4 places = 0.3333
        result = jaccard(a, b)
        assert result == round(1 / 3, 4)


# ---------------------------------------------------------------------------
# common_surnames
# ---------------------------------------------------------------------------

class TestCommonSurnames:
    def test_returns_sorted_list(self):
        a = frozenset({"müller", "schmidt", "meier"})
        b = frozenset({"schmidt", "müller", "braun"})
        assert common_surnames(a, b) == ["müller", "schmidt"]

    def test_no_overlap_returns_empty_list(self):
        assert common_surnames(frozenset({"a"}), frozenset({"b"})) == []

    def test_both_empty(self):
        assert common_surnames(frozenset(), frozenset()) == []


# ---------------------------------------------------------------------------
# get_match_surnames
# ---------------------------------------------------------------------------

class TestGetMatchSurnames:
    def _row(self, surname):
        """Simple dict acting as a sqlite3.Row substitute."""
        return {"surname": surname}

    def test_basic(self):
        rows = [self._row("Müller"), self._row("Schmidt")]
        result = get_match_surnames(rows)
        assert result == frozenset({"müller", "schmidt"})

    def test_none_surnames_skipped(self):
        rows = [self._row(None), self._row("Meier")]
        result = get_match_surnames(rows)
        assert result == frozenset({"meier"})

    def test_empty_string_surname_skipped(self):
        rows = [self._row(""), self._row("Braun")]
        result = get_match_surnames(rows)
        assert result == frozenset({"braun"})

    def test_all_empty_or_none(self):
        rows = [self._row(None), self._row(""), self._row(None)]
        assert get_match_surnames(rows) == frozenset()

    def test_normalizes_casing(self):
        rows = [self._row("MÜLLER"), self._row("müller")]
        # both normalize to "müller" → single entry
        assert get_match_surnames(rows) == frozenset({"müller"})


# ---------------------------------------------------------------------------
# compute_surname_pairs
# ---------------------------------------------------------------------------

class TestComputeSurnamePairs:
    def test_empty_input(self):
        assert compute_surname_pairs({}) == []

    def test_single_match_no_pairs(self):
        data = {"g1": frozenset({"müller"})}
        assert compute_surname_pairs(data) == []

    def test_disjoint_surnames_excluded(self):
        data = {
            "g1": frozenset({"müller"}),
            "g2": frozenset({"schmidt"}),
        }
        # no common surnames → empty result
        assert compute_surname_pairs(data) == []

    def test_overlapping_pair(self):
        data = {
            "g1": frozenset({"müller", "schmidt"}),
            "g2": frozenset({"schmidt", "meier"}),
        }
        pairs = compute_surname_pairs(data)
        assert len(pairs) == 1
        p = pairs[0]
        assert set([p["guid_a"], p["guid_b"]]) == {"g1", "g2"}
        assert p["common"] == ["schmidt"]
        assert p["count"] == 1
        # jaccard: intersection=1, union=3 → 0.3333
        assert p["score"] == round(1 / 3, 4)

    def test_min_score_filters_low_scores(self):
        data = {
            "g1": frozenset({"a", "b", "c", "d"}),
            "g2": frozenset({"a", "e", "f", "g"}),
            # jaccard = 1/7 ≈ 0.1429
        }
        pairs_no_filter = compute_surname_pairs(data, min_score=0.0)
        assert len(pairs_no_filter) == 1
        pairs_high_filter = compute_surname_pairs(data, min_score=0.5)
        assert pairs_high_filter == []

    def test_ordering_highest_score_first(self):
        data = {
            "g1": frozenset({"a", "b"}),
            "g2": frozenset({"a", "b"}),       # jaccard 1.0 with g1
            "g3": frozenset({"a", "c", "d"}),  # lower jaccard with g1
        }
        pairs = compute_surname_pairs(data)
        # g1-g2 should be first (score 1.0)
        assert pairs[0]["score"] == 1.0
        assert set([pairs[0]["guid_a"], pairs[0]["guid_b"]]) == {"g1", "g2"}

    def test_pair_keys_present(self):
        data = {
            "g1": frozenset({"x"}),
            "g2": frozenset({"x", "y"}),
        }
        pairs = compute_surname_pairs(data)
        assert len(pairs) == 1
        p = pairs[0]
        for key in ("guid_a", "guid_b", "score", "common", "count"):
            assert key in p

    def test_three_matches_multiple_pairs(self):
        data = {
            "g1": frozenset({"a", "b"}),
            "g2": frozenset({"a", "b"}),
            "g3": frozenset({"a", "b"}),
        }
        pairs = compute_surname_pairs(data)
        # C(3,2) = 3 pairs
        assert len(pairs) == 3
        for p in pairs:
            assert p["score"] == 1.0
            assert p["count"] == 2
