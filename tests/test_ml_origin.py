"""Tests for ancestry.core.ml_origin — pure helper functions (no sklearn needed)."""
from __future__ import annotations

import pytest

from ancestry.core.ml_origin import _year_bucket, _featurize, predict_region, load


# ── _year_bucket ───────────────────────────────────────────────────────────────

class TestYearBucket:
    def test_exact_century(self):
        assert _year_bucket(1800) == "y1800"

    def test_rounds_down_to_50(self):
        assert _year_bucket(1850) == "y1850"
        assert _year_bucket(1875) == "y1850"
        assert _year_bucket(1899) == "y1850"

    def test_second_half_of_century(self):
        assert _year_bucket(1923) == "y1900"

    def test_year_1900(self):
        assert _year_bucket(1900) == "y1900"

    def test_year_2000(self):
        assert _year_bucket(2000) == "y2000"

    def test_ancient_year(self):
        assert _year_bucket(1650) == "y1650"

    def test_none_returns_yna(self):
        assert _year_bucket(None) == "yNA"

    def test_empty_string_returns_yna(self):
        assert _year_bucket("") == "yNA"

    def test_non_numeric_string_returns_yna(self):
        assert _year_bucket("unknown") == "yNA"

    def test_string_year_parsed(self):
        assert _year_bucket("1850") == "y1850"

    def test_float_year_truncated(self):
        assert _year_bucket(1875.9) == "y1850"


# ── _featurize ─────────────────────────────────────────────────────────────────

class TestFeaturize:
    def test_basic_surname_and_year(self):
        result = _featurize("Kovermann", 1850)
        assert "kovermann" in result
        assert "y1850" in result

    def test_surname_lowercased(self):
        result = _featurize("MÜLLER", 1900)
        assert "müller" in result

    def test_no_birth_year(self):
        result = _featurize("Schmidt")
        assert "schmidt" in result
        assert "yNA" in result

    def test_none_surname(self):
        result = _featurize(None)
        assert "yNA" in result

    def test_empty_surname(self):
        result = _featurize("")
        assert isinstance(result, str)

    def test_returns_string(self):
        assert isinstance(_featurize("Test", 1750), str)

    def test_year_bucket_appended(self):
        r1 = _featurize("Müller", 1850)
        r2 = _featurize("Müller", 1900)
        assert r1 != r2


# ── predict_region / load ─────────────────────────────────────────────────────

class TestPredictRegion:
    def test_no_model_returns_empty_list(self):
        # In the test environment there is no trained model file present.
        # predict_region should return [] rather than raising.
        import ancestry.core.ml_origin as ml
        ml._MODEL = None  # ensure not loaded
        result = predict_region("Kovermann", 1850)
        assert isinstance(result, list)
        assert len(result) == 0


class TestLoad:
    def test_load_without_model_file_returns_false(self, tmp_path, monkeypatch):
        import ancestry.core.ml_origin as ml
        monkeypatch.setattr(ml, "MODEL_PATH", tmp_path / "nonexistent.pkl")
        ml._MODEL = None
        assert load() is False
