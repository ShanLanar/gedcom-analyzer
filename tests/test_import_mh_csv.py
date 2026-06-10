"""Tests for ancestry.tools.import_mh_csv — pure helper functions."""
from __future__ import annotations

import pytest

from ancestry.tools.import_mh_csv import (
    _float,
    _int,
    _str,
    kit_from_url,
)


class TestFloat:
    def test_normal_string(self):
        assert _float("3.14") == pytest.approx(3.14)

    def test_comma_decimal(self):
        assert _float("3,14") == pytest.approx(3.14)

    def test_integer_string(self):
        assert _float("100") == 100.0

    def test_none_returns_default(self):
        assert _float(None) == 0.0

    def test_invalid_string_returns_default(self):
        assert _float("n/a") == 0.0

    def test_custom_default(self):
        assert _float("bad", -1.0) == -1.0

    def test_already_float(self):
        assert _float(42.5) == pytest.approx(42.5)

    def test_whitespace_stripped(self):
        assert _float("  12.5  ") == pytest.approx(12.5)


class TestInt:
    def test_integer_string(self):
        assert _int("7") == 7

    def test_float_string_truncated(self):
        assert _int("3.9") == 3

    def test_none_returns_default(self):
        assert _int(None) == 0

    def test_invalid_returns_default(self):
        assert _int("abc") == 0

    def test_custom_default(self):
        assert _int("abc", -1) == -1

    def test_already_int(self):
        assert _int(5) == 5


class TestStr:
    def test_normal(self):
        assert _str("hello") == "hello"

    def test_strips_whitespace(self):
        assert _str("  trim  ") == "trim"

    def test_none_returns_default(self):
        assert _str(None) == ""

    def test_custom_default(self):
        assert _str(None, "fallback") == "fallback"

    def test_int_coerced_to_string(self):
        assert _str(42) == "42"


class TestKitFromUrl:
    def test_extracts_first_guid(self):
        url = ("https://www.myheritage.com/dna/match/"
               "D-12345678-1234-1234-1234-123456789ABC/"
               "D-ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB")
        result = kit_from_url(url)
        assert result == "D-12345678-1234-1234-1234-123456789ABC"

    def test_no_guid_returns_empty(self):
        assert kit_from_url("https://www.myheritage.com/dna") == ""

    def test_empty_url_returns_empty(self):
        assert kit_from_url("") == ""

    def test_none_url_returns_empty(self):
        assert kit_from_url(None) == ""

    def test_lowercase_guid(self):
        url = "https://example.com/D-abcdefab-cdef-abcd-efab-cdefabcdefab"
        result = kit_from_url(url)
        assert result.startswith("D-")

    def test_returns_only_first_guid(self):
        url = ("https://example.com/"
               "D-11111111-1111-1111-1111-111111111111/"
               "D-22222222-2222-2222-2222-222222222222")
        result = kit_from_url(url)
        assert result == "D-11111111-1111-1111-1111-111111111111"
