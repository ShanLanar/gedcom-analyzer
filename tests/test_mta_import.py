"""Tests for ancestry.core.mta_import — pure functions, no DB needed."""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest

from ancestry.core.mta_import import _detect_era, parse_mta_csv, derive_paternal


# ── _detect_era ────────────────────────────────────────────────────────────────

class TestDetectEra:
    def test_neolithic_keyword(self):
        assert _detect_era("Nordic_Neolithic") == "Neolithic"

    def test_farmer_keyword(self):
        assert _detect_era("Early_European_Farmer") == "Neolithic"

    def test_bronze_age(self):
        assert _detect_era("Corded_Ware_Germany") == "Bronze Age"

    def test_yamnaya(self):
        assert _detect_era("Yamnaya_Samara") == "Bronze Age"

    def test_steppe(self):
        assert _detect_era("Steppe_EMBA") == "Bronze Age"

    def test_iron_age_germanic(self):
        assert _detect_era("Germanic_Iron_Age") == "Iron Age / Historical"

    def test_celtic(self):
        assert _detect_era("Celtic_Britain") == "Iron Age / Historical"

    def test_medieval(self):
        assert _detect_era("Medieval_Germany") == "Medieval"

    def test_viking(self):
        assert _detect_era("Viking_Age_Scandinavia") == "Medieval"

    def test_modern(self):
        assert _detect_era("Modern_German") == "Modern"

    def test_unknown_fallback(self):
        assert _detect_era("Mysterious_Population") == "Ancient / Other"

    def test_case_insensitive(self):
        assert _detect_era("NEOLITHIC_FARMER") == "Neolithic"


# ── parse_mta_csv ──────────────────────────────────────────────────────────────

def _write_csv(content: str) -> Path:
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".csv",
                                     delete=False, encoding="utf-8")
    tf.write(content)
    tf.flush()
    tf.close()
    return Path(tf.name)


class TestParseMtaCsv:
    def test_basic_three_column(self):
        p = _write_csv("Population,Score,Distance\nCorded_Ware_Germany,89.5,0.0412\n")
        rows = parse_mta_csv(str(p))
        assert len(rows) == 1
        assert rows[0]["population"] == "Corded_Ware_Germany"
        assert rows[0]["score"] == pytest.approx(89.5)
        assert rows[0]["distance"] == pytest.approx(0.0412)
        assert rows[0]["era"] == "Bronze Age"

    def test_two_column_no_distance(self):
        p = _write_csv("Population,Score\nNordic_Neolithic,12.3\n")
        rows = parse_mta_csv(str(p))
        assert len(rows) == 1
        assert rows[0]["distance"] == pytest.approx(0.0)

    def test_skips_empty_population(self):
        p = _write_csv("Population,Score,Distance\n,10.0,0.1\nCorded_Ware,5.0,0.2\n")
        rows = parse_mta_csv(str(p))
        assert len(rows) == 1
        assert rows[0]["population"] == "Corded_Ware"

    def test_invalid_score_defaults_to_zero(self):
        p = _write_csv("Population,Score,Distance\nTest_Pop,n/a,0.1\n")
        rows = parse_mta_csv(str(p))
        assert rows[0]["score"] == 0.0

    def test_multiple_rows(self):
        p = _write_csv(
            "Population,Score,Distance\n"
            "Corded_Ware_Germany,45.0,0.04\n"
            "Nordic_Neolithic,30.0,0.07\n"
            "Modern_German,25.0,0.12\n"
        )
        rows = parse_mta_csv(str(p))
        assert len(rows) == 3

    def test_era_assigned_correctly(self):
        p = _write_csv(
            "Population,Score,Distance\n"
            "Viking_Age,10,0.05\n"
            "Yamnaya_Samara,20,0.03\n"
        )
        rows = parse_mta_csv(str(p))
        eras = {r["population"]: r["era"] for r in rows}
        assert eras["Viking_Age"] == "Medieval"
        assert eras["Yamnaya_Samara"] == "Bronze Age"

    def test_lowercase_column_names(self):
        p = _write_csv("population,score,distance\nTest_Pop,5.0,0.1\n")
        rows = parse_mta_csv(str(p))
        assert len(rows) == 1
        assert rows[0]["population"] == "Test_Pop"

    def test_bom_utf8_sig_handled(self):
        tf = tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False)
        content = "Population,Score,Distance\nBOM_Pop,50.0,0.05\n"
        tf.write(b"\xef\xbb\xbf" + content.encode("utf-8"))
        tf.close()
        rows = parse_mta_csv(tf.name)
        assert len(rows) == 1
        assert rows[0]["population"] == "BOM_Pop"


# ── derive_paternal ────────────────────────────────────────────────────────────

class TestDerivePaternal:
    def _rows(self, *pops: tuple[str, float]) -> list[dict]:
        return [{"population": p, "score": s, "era": _detect_era(p)} for p, s in pops]

    def test_basic_derivation(self):
        self_rows = self._rows(("Corded_Ware", 60.0), ("Neolithic", 40.0))
        base2_rows = self._rows(("Corded_Ware", 30.0), ("Neolithic", 70.0))
        result = derive_paternal(self_rows, base2_rows)
        by_pop = {r["population"]: r for r in result}
        # paternal_estimate for Corded_Ware should be higher than for Neolithic
        assert by_pop["Corded_Ware"]["paternal_estimate"] > by_pop["Neolithic"]["paternal_estimate"]

    def test_estimates_sum_to_100(self):
        self_rows = self._rows(("Pop_A", 50.0), ("Pop_B", 50.0))
        base2_rows = self._rows(("Pop_A", 20.0), ("Pop_B", 80.0))
        result = derive_paternal(self_rows, base2_rows)
        total = sum(r["paternal_estimate"] for r in result)
        assert abs(total - 100.0) < 0.01

    def test_clamped_to_zero_not_negative(self):
        self_rows = self._rows(("Pop_A", 10.0))
        base2_rows = self._rows(("Pop_A", 90.0))
        result = derive_paternal(self_rows, base2_rows)
        assert result[0]["paternal_estimate"] >= 0.0

    def test_missing_base2_population_treated_as_zero(self):
        self_rows = self._rows(("Pop_X", 40.0), ("Pop_Y", 60.0))
        base2_rows = self._rows(("Pop_X", 30.0))  # Pop_Y missing
        result = derive_paternal(self_rows, base2_rows)
        by_pop = {r["population"]: r for r in result}
        assert by_pop["Pop_Y"]["base2_score"] == 0.0

    def test_empty_self_rows(self):
        result = derive_paternal([], [])
        assert result == []

    def test_result_contains_all_source_fields(self):
        self_rows = self._rows(("Corded_Ware", 70.0))
        base2_rows = self._rows(("Corded_Ware", 50.0))
        result = derive_paternal(self_rows, base2_rows)
        r = result[0]
        assert "population" in r
        assert "era" in r
        assert "self_score" in r
        assert "base2_score" in r
        assert "paternal_estimate" in r

    def test_result_contains_method_key(self):
        result = derive_paternal(
            self._rows(("Pop_A", 50.0)),
            self._rows(("Pop_A", 30.0)),
        )
        assert result[0]["method"] == "subtraction_approximation"


# ── classify_parental_origin ───────────────────────────────────────────────────

from ancestry.core.mta_import import classify_parental_origin


class TestClassifyParentalOrigin:
    def _self(self):
        return [
            {"population": "Steppe", "score": 40.0, "era": "Bronze Age"},
            {"population": "Farmer", "score": 30.0, "era": "Neolithic"},
            {"population": "Nordic", "score": 20.0, "era": "Modern"},
        ]

    def test_maternal_only(self):
        # self=20, mother=40 -> paternal = max(0, 40-40)=0 -> mütterlich
        res = classify_parental_origin(
            [{"population": "X", "score": 20.0, "era": "Modern"}],
            [{"population": "X", "score": 40.0}])
        assert res[0]["origin"] == "mütterlich"
        assert res[0]["paternal_estimate"] == 0.0
        assert res[0]["maternal_score"] == 40.0

    def test_paternal_only(self):
        # self=30, mother=0 -> paternal=60 -> väterlich
        res = classify_parental_origin(
            [{"population": "Y", "score": 30.0, "era": "Iron Age / Historical"}],
            [])
        assert res[0]["origin"] == "väterlich"
        assert res[0]["paternal_estimate"] == 60.0

    def test_both_sides(self):
        # self=40, mother=40 -> paternal=40 -> beide
        res = classify_parental_origin(
            [{"population": "Z", "score": 40.0, "era": "Bronze Age"}],
            [{"population": "Z", "score": 40.0}])
        assert res[0]["origin"] == "beide"

    def test_noise_filtered(self):
        res = classify_parental_origin(
            [{"population": "tiny", "score": 0.3, "era": ""}],
            [{"population": "tiny", "score": 0.2}], min_score=1.0)
        assert res == []

    def test_sorted_by_self_score(self):
        res = classify_parental_origin(self.__class__()._self(), [])
        scores = [r["self_score"] for r in res]
        assert scores == sorted(scores, reverse=True)

    def test_era_carried_through(self):
        res = classify_parental_origin(
            [{"population": "Steppe", "score": 40.0, "era": "Bronze Age"}], [])
        assert res[0]["era"] == "Bronze Age"
