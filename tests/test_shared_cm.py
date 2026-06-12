"""Tests for ancestry.core.shared_cm — relationship probability modeling.

Reference values from Shared cM Project 4.0 (Blaine Bettinger, 2020).
"""
from __future__ import annotations

import pytest

from ancestry.core.shared_cm import relationship_probabilities, summary_line


# ── relationship_probabilities ─────────────────────────────────────────────────

class TestRelationshipProbabilities:
    def test_returns_list(self):
        result = relationship_probabilities(850)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_zero_cm_returns_empty(self):
        assert relationship_probabilities(0) == []

    def test_negative_cm_returns_empty(self):
        assert relationship_probabilities(-10) == []

    def test_none_cm_returns_empty(self):
        assert relationship_probabilities(None) == []

    def test_probabilities_sum_to_one(self):
        result = relationship_probabilities(245)
        total = sum(r["probability"] for r in result)
        assert abs(total - 1.0) < 1e-9

    def test_sorted_descending(self):
        result = relationship_probabilities(850)
        probs = [r["probability"] for r in result]
        assert probs == sorted(probs, reverse=True)

    def test_top_parameter_limits_results(self):
        result = relationship_probabilities(245, top=2)
        assert len(result) <= 2

    def test_result_dict_keys(self):
        result = relationship_probabilities(850)
        r = result[0]
        assert "labels" in r
        assert "probability" in r
        assert "mean" in r
        assert "low" in r
        assert "high" in r

    def test_labels_is_list_of_strings(self):
        result = relationship_probabilities(850)
        for r in result:
            assert isinstance(r["labels"], list)
            assert all(isinstance(s, str) for s in r["labels"])

    # ── genealogically meaningful reference points ──────────────────────────

    def test_parent_child_3500_cm(self):
        """~3 485 cM mean for parent/child (SCP 4.0 table row 1)."""
        result = relationship_probabilities(3500, top=1)
        assert result[0]["labels"][0] == "Elternteil / Kind"

    def test_sibling_2600_cm(self):
        """~2 613 cM mean for full sibling."""
        result = relationship_probabilities(2600, top=1)
        assert "Vollgeschwister" in result[0]["labels"][0]

    def test_first_cousin_850_cm(self):
        """~866 cM mean for 1st cousin (SCP 4.0)."""
        result = relationship_probabilities(866, top=1)
        labels_combined = " ".join(result[0]["labels"])
        assert "Cousin" in labels_combined or "Onkel" in labels_combined

    def test_second_cousin_229_cm(self):
        """~229 cM mean for 2nd cousin."""
        result = relationship_probabilities(229, top=1)
        labels_combined = " ".join(result[0]["labels"])
        assert "2." in labels_combined or "Cousin" in labels_combined

    def test_third_cousin_73_cm(self):
        """~73 cM mean for 3rd cousin."""
        result = relationship_probabilities(73, top=1)
        labels_combined = " ".join(result[0]["labels"])
        assert "Cousin" in labels_combined

    def test_fallback_for_extreme_high_cm(self):
        """Implausibly high cM (e.g. 5 000) is outside all group ranges;
        the fallback should return exactly one entry with probability 1.0."""
        result = relationship_probabilities(5000)
        assert len(result) == 1
        assert result[0]["probability"] == 1.0

    def test_probability_values_in_range(self):
        for cm in (50, 100, 250, 500, 1000, 2000):
            result = relationship_probabilities(cm)
            for r in result:
                assert 0.0 <= r["probability"] <= 1.0


# ── summary_line ───────────────────────────────────────────────────────────────

class TestSummaryLine:
    def test_returns_string(self):
        assert isinstance(summary_line(850), str)

    def test_zero_cm_returns_dash(self):
        assert summary_line(0) == "—"

    def test_contains_percentage(self):
        line = summary_line(850)
        assert "%" in line

    def test_separator_between_entries(self):
        line = summary_line(245, top=3)
        # multiple entries are joined with " · "
        assert "·" in line

    def test_top_limits_number_of_entries(self):
        line = summary_line(245, top=2)
        # at most 2 percentage entries
        assert line.count("%") <= 2

    def test_top_1_no_separator(self):
        line = summary_line(850, top=1)
        assert "·" not in line

    def test_parent_child_label_in_summary(self):
        line = summary_line(3500, top=1)
        assert "Elternteil" in line or "Kind" in line

    def test_second_cousin_label_in_summary(self):
        line = summary_line(229, top=1)
        assert "Cousin" in line
