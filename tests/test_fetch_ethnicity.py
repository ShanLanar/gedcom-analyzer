"""Tests for ancestry.tools.fetch_ethnicity — pure functions only (no network)."""
from __future__ import annotations

import json
import pytest

from ancestry.tools.fetch_ethnicity import (
    _shorten,
    _is_region,
    _find_regions,
    _normalize,
    _find_traits,
    _normalize_trait,
    _parse_html,
)


# ── _shorten ───────────────────────────────────────────────────────────────────

class TestShorten:
    def test_known_label_lowercase(self):
        assert _shorten("germanic europe") == "Germanisch"

    def test_known_label_mixed_case(self):
        assert _shorten("Germany") == "Deutschland"

    def test_scandinavia(self):
        assert _shorten("scandinavia") == "Skandinavien"

    def test_unknown_passthrough(self):
        assert _shorten("Nordic Lands") == "Nordic Lands"

    def test_strips_leading_trailing_whitespace(self):
        assert _shorten("  scandinavia  ") == "Skandinavien"

    def test_ashkenazi_jewish(self):
        assert _shorten("ashkenazi jewish") == "Aschkenasisch-Jüdisch"


# ── _is_region ─────────────────────────────────────────────────────────────────

class TestIsRegion:
    def test_valid_name_and_percentage(self):
        assert _is_region({"name": "Germany", "percentage": 45.0})

    def test_valid_categoryname_and_pct(self):
        assert _is_region({"categoryName": "Germanic Europe", "pct": 35})

    def test_missing_percentage_key(self):
        assert not _is_region({"name": "Germany"})

    def test_missing_name_key(self):
        assert not _is_region({"percentage": 45})

    def test_non_dict_string(self):
        assert not _is_region("not a dict")

    def test_non_dict_integer(self):
        assert not _is_region(42)

    def test_non_dict_list(self):
        assert not _is_region([{"name": "X", "percentage": 10}])

    def test_all_name_key_variants(self):
        for key in ("name", "categoryName", "label", "ethnicity", "regionName"):
            assert _is_region({key: "X", "percentage": 10})

    def test_all_pct_key_variants(self):
        for key in ("percentage", "pct", "percent", "value"):
            assert _is_region({"name": "X", key: 10})

    def test_empty_dict(self):
        assert not _is_region({})


# ── _find_regions ──────────────────────────────────────────────────────────────

class TestFindRegions:
    def test_direct_region_key(self):
        regions = [{"name": "Germany", "percentage": 50}, {"name": "France", "percentage": 30}]
        result = _find_regions({"ethnicities": regions})
        assert result == regions

    def test_categories_key(self):
        regions = [{"name": "Germanic", "percentage": 60}]
        result = _find_regions({"categories": regions})
        assert result == regions

    def test_nested_two_levels(self):
        regions = [{"name": "Germany", "percentage": 50}]
        result = _find_regions({"page": {"data": {"ethnicities": regions}}})
        assert result == regions

    def test_empty_dict_returns_empty(self):
        assert _find_regions({}) == []

    def test_non_region_list_skipped(self):
        regions = [{"name": "X", "percentage": 10}]
        data = {"items": [1, 2, 3], "ethnicities": regions}
        assert _find_regions(data) == regions

    def test_depth_limit_15_returns_empty(self):
        data: dict = {}
        d = data
        for _ in range(15):
            d["child"] = {}
            d = d["child"]
        d["ethnicities"] = [{"name": "X", "percentage": 5}]
        assert _find_regions(data) == []

    def test_list_input_returns_empty(self):
        # _find_regions iterates list items looking for nested structures;
        # a bare list of region dicts is not returned directly.
        regions = [{"name": "Germany", "percentage": 50}]
        result = _find_regions(regions)
        assert result == []

    def test_categories_key_has_priority_over_ethnicities(self):
        # _REGION_KEYS = ("categories", "ethnicities", ...) — categories is checked first.
        r1 = [{"name": "A", "percentage": 10}]
        r2 = [{"name": "B", "percentage": 20}]
        data = {"categories": r1, "ethnicities": r2}
        result = _find_regions(data)
        assert result == r1

    def test_finds_via_arbitrary_dict_traversal(self):
        regions = [{"categoryName": "Ashkenazi Jewish", "pct": 12}]
        data = {"ssr": {"props": {"pageProps": {"ethnicComposition": regions}}}}
        result = _find_regions(data)
        assert result == regions


# ── _normalize ─────────────────────────────────────────────────────────────────

class TestNormalize:
    def test_basic_name_and_percentage(self):
        result = _normalize({"name": "Germany", "percentage": 35.5}, "ancestry")
        assert result == {"label": "Deutschland", "pct": 35.5, "source": "ancestry"}

    def test_zero_pct_returns_none(self):
        assert _normalize({"name": "X", "percentage": 0}, "ancestry") is None

    def test_negative_pct_returns_none(self):
        assert _normalize({"name": "X", "percentage": -5}, "ancestry") is None

    def test_over_100_pct_returns_none(self):
        assert _normalize({"name": "X", "percentage": 101}, "ancestry") is None

    def test_empty_label_returns_none(self):
        assert _normalize({"name": "", "percentage": 10}, "ancestry") is None

    def test_whitespace_only_label_returns_none(self):
        assert _normalize({"name": "   ", "percentage": 10}, "ancestry") is None

    def test_invalid_pct_string_returns_none(self):
        assert _normalize({"name": "X", "percentage": "not-a-number"}, "ancestry") is None

    def test_none_pct_returns_none(self):
        assert _normalize({"name": "X", "percentage": None}, "ancestry") is None

    def test_categoryname_used_over_name(self):
        item = {"categoryName": "Germanic Europe", "name": "Should not use", "pct": 20}
        result = _normalize(item, "ancestry")
        assert result["label"] == "Germanisch"

    def test_source_field_preserved(self):
        result = _normalize({"name": "Italy", "percentage": 5}, "myheritage")
        assert result["source"] == "myheritage"

    def test_pct_rounded_to_one_decimal(self):
        result = _normalize({"name": "X", "percentage": 12.3456}, "test")
        assert result["pct"] == 12.3

    def test_integer_pct_converted_to_float(self):
        result = _normalize({"name": "Baltic", "percentage": 10}, "ancestry")
        assert isinstance(result["pct"], float)


# ── _parse_html ────────────────────────────────────────────────────────────────

class TestParseHtml:
    def _make_next_data(self, regions):
        payload = json.dumps({"props": {"pageProps": {"ethnicities": regions}}})
        return f'<script id="__NEXT_DATA__">{payload}</script>'

    def test_next_data_script_tag(self):
        regions = [
            {"name": "Germany", "percentage": 45},
            {"name": "France", "percentage": 30},
        ]
        result = _parse_html(self._make_next_data(regions))
        assert len(result) == 2
        assert result[0]["name"] == "Germany"

    def test_window_initial_state_pattern(self):
        regions = [{"name": "Scandinavia", "percentage": 20}]
        payload = json.dumps({"ethnicities": regions})
        html = f"window.__INITIAL_STATE__ = {payload};"
        result = _parse_html(html)
        assert len(result) == 1
        assert result[0]["name"] == "Scandinavia"

    def test_window_ancestry_pattern(self):
        regions = [{"categoryName": "Germanic Europe", "percentage": 60}]
        payload = json.dumps({"ethnicity": regions})
        html = f"window.Ancestry = {payload};"
        result = _parse_html(html)
        assert len(result) == 1

    def test_empty_html_returns_empty_list(self):
        assert _parse_html("") == []

    def test_html_without_ethnicity_data(self):
        assert _parse_html("<html><body><p>Hello world</p></body></html>") == []

    def test_invalid_json_in_next_data_returns_empty(self):
        html = '<script id="__NEXT_DATA__">{invalid_json</script>'
        assert _parse_html(html) == []

    def test_window_app_state_pattern(self):
        regions = [{"name": "Eastern Europe", "percentage": 25}]
        payload = json.dumps({"categories": regions})
        html = f"window.__APP_STATE__ = {payload};"
        result = _parse_html(html)
        assert len(result) == 1

    def test_application_json_script_tag(self):
        regions = [{"name": "Baltic", "percentage": 8}]
        payload = json.dumps({"ethnicities": regions})
        html = f'<script type="application/json">{payload}</script>'
        result = _parse_html(html)
        assert len(result) == 1


# ── _find_traits ───────────────────────────────────────────────────────────────

class TestFindTraits:
    def test_finds_traits_key(self):
        traits = [{"traitName": "Eye Color", "result": "Blue", "percentage": 75}]
        result = _find_traits({"traits": traits})
        assert result == traits

    def test_finds_trait_results_key(self):
        traits = [{"name": "Hair Color", "result": "Brown"}]
        result = _find_traits({"traitResults": traits})
        assert result == traits

    def test_nested_traits(self):
        traits = [{"traitName": "Height", "result": "Tall"}]
        result = _find_traits({"page": {"traitResults": traits}})
        assert result == traits

    def test_empty_returns_empty(self):
        assert _find_traits({}) == []

    def test_depth_limit_returns_empty(self):
        data: dict = {}
        d = data
        for _ in range(15):
            d["child"] = {}
            d = d["child"]
        d["traits"] = [{"traitName": "X", "result": "Y"}]
        assert _find_traits(data) == []

    def test_non_trait_list_skipped(self):
        traits = [{"traitName": "Eye Color", "result": "Blue"}]
        data = {"other": [1, 2, 3], "traits": traits}
        result = _find_traits(data)
        assert result == traits


# ── _normalize_trait ───────────────────────────────────────────────────────────

class TestNormalizeTrait:
    def test_basic_with_all_fields(self):
        item = {"traitName": "Eye Color", "result": "Blue", "percentage": 80}
        result = _normalize_trait(item)
        assert result == {"name": "Eye Color", "result": "Blue", "pct": 80.0}

    def test_traitname_key(self):
        assert _normalize_trait({"traitName": "T", "result": "V"})["name"] == "T"

    def test_name_key_fallback(self):
        assert _normalize_trait({"name": "N", "result": "V"})["name"] == "N"

    def test_trait_key_fallback(self):
        assert _normalize_trait({"trait": "T2", "result": "V"})["name"] == "T2"

    def test_label_key_fallback(self):
        assert _normalize_trait({"label": "L", "result": "V"})["name"] == "L"

    def test_empty_name_returns_none(self):
        assert _normalize_trait({"traitName": "", "result": "Blue"}) is None

    def test_no_pct_field_valid_result(self):
        result = _normalize_trait({"name": "Height", "result": "Tall"})
        assert result is not None
        assert "pct" not in result

    def test_invalid_pct_string_omitted(self):
        result = _normalize_trait({"name": "X", "result": "Y", "percentage": "n/a"})
        assert result is not None
        assert "pct" not in result

    def test_probability_key_used(self):
        result = _normalize_trait({"name": "X", "result": "Y", "probability": 0.75})
        assert result["pct"] == 0.8  # round(0.75, 1)

    def test_result_uses_prediction_fallback(self):
        result = _normalize_trait({"name": "X", "prediction": "Brown"})
        assert result["result"] == "Brown"

    def test_whitespace_only_name_returns_none(self):
        assert _normalize_trait({"name": "   ", "result": "X"}) is None
