"""Tests for endogamy score calculation (F1)."""

import pytest
from ancestry.core.analysis.endogamy import (
    calculate_endogamy_score,
    flag_endogamy_matches,
)
from ancestry.models import DnaMatch


class TestCalculateEndogamyScore:
    """Test endogamy score calculation."""

    def test_zero_cm(self):
        """Score should be 0 when shared_cm is 0."""
        assert calculate_endogamy_score(80, 0) == 0.0

    def test_negative_cm(self):
        """Score should be 0 when shared_cm is negative."""
        assert calculate_endogamy_score(80, -10) == 0.0

    def test_low_endogamy(self):
        """Low endogamy: 5 segments / 100 cM = 0.05 score."""
        score = calculate_endogamy_score(5, 100)
        assert score == 0.05

    def test_threshold_endogamy(self):
        """Threshold endogamy: 80 segments / 100 cM = 0.8 score."""
        score = calculate_endogamy_score(80, 100)
        assert score == 0.8

    def test_high_endogamy(self):
        """High endogamy: 100 segments / 100 cM = 1.0 score."""
        score = calculate_endogamy_score(100, 100)
        assert score == 1.0

    def test_small_values(self):
        """Score should handle small values correctly."""
        score = calculate_endogamy_score(1, 10)
        assert score == 0.1  # 1 / 10 = 0.1

    def test_large_values(self):
        """Score should handle large values correctly."""
        score = calculate_endogamy_score(1000, 1000)
        assert score == 1.0  # 1000 / 1000 = 1.0


class TestFlagEndogamyMatches:
    """Test endogamy match flagging."""

    def test_empty_list(self):
        """Empty match list should return empty results."""
        assert flag_endogamy_matches([]) == []

    def test_no_matches_flagged(self):
        """Matches below threshold should not be flagged."""
        match = DnaMatch(
            match_guid="guid1",
            test_guid="test1",
            display_name="Test Match",
            shared_cm=100,
            shared_segments=5,  # 0.05 score < 0.08 threshold
        )
        flagged = flag_endogamy_matches([match], threshold=0.08)
        assert len(flagged) == 0

    def test_single_match_flagged(self):
        """Match above threshold should be flagged."""
        match = DnaMatch(
            match_guid="guid1",
            test_guid="test1",
            display_name="Test Match",
            shared_cm=100,
            shared_segments=80,  # 0.8 score >= 0.8 threshold
        )
        flagged = flag_endogamy_matches([match], threshold=0.8)
        assert len(flagged) == 1
        assert flagged[0] == ("guid1", 0.8)

    def test_multiple_matches_mixed(self):
        """Should flag only matches above threshold."""
        matches = [
            DnaMatch(
                match_guid="guid1", test_guid="test1", display_name="Low",
                shared_cm=100, shared_segments=5
            ),
            DnaMatch(
                match_guid="guid2", test_guid="test1", display_name="High",
                shared_cm=100, shared_segments=80
            ),
            DnaMatch(
                match_guid="guid3", test_guid="test1", display_name="Very High",
                shared_cm=100, shared_segments=100
            ),
        ]
        flagged = flag_endogamy_matches(matches, threshold=0.8)
        assert len(flagged) == 2
        assert ("guid2", 0.8) in flagged
        assert ("guid3", 1.0) in flagged

    def test_min_cm_filter(self):
        """Matches below min_cm should be excluded."""
        match = DnaMatch(
            match_guid="guid1",
            test_guid="test1",
            display_name="Too Small",
            shared_cm=0.5,  # Below internal min_cm of 1.0
            shared_segments=80,  # High score but too small
        )
        flagged = flag_endogamy_matches([match], threshold=8.0)
        assert len(flagged) == 0

    def test_custom_threshold(self):
        """Should respect custom threshold."""
        match = DnaMatch(
            match_guid="guid1",
            test_guid="test1",
            display_name="Test",
            shared_cm=100,
            shared_segments=50,  # 0.5 score
        )
        # With threshold 0.8, should not flag
        flagged = flag_endogamy_matches([match], threshold=0.8)
        assert len(flagged) == 0

        # With threshold 0.4, should flag
        flagged = flag_endogamy_matches([match], threshold=0.4)
        assert len(flagged) == 1
        assert flagged[0] == ("guid1", 0.5)
