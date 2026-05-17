"""Tests für lib.gedcom – Datum/Jahres-Parser."""
from lib.gedcom import safe_extract_year, safe_parse_gedcom_date


def test_safe_extract_year_basic():
    assert safe_extract_year("1789") == 1789
    assert safe_extract_year("01 JAN 1842") == 1842
    assert safe_extract_year("ABT 1900") == 1900


def test_safe_extract_year_medieval():
    # Mittelalter (vor 1600) muss vom einheitlichen Regex erfasst werden.
    assert safe_extract_year("1234") == 1234
    assert safe_extract_year("BEF 1499") == 1499


def test_safe_extract_year_invalid():
    assert safe_extract_year("") is None
    assert safe_extract_year(None) is None
    assert safe_extract_year("kein Datum") is None
    assert safe_extract_year("2999") is None  # außerhalb 1000-2099


def test_safe_parse_gedcom_date_qualifiers():
    assert safe_parse_gedcom_date("ABT 1850")["DATE_QUAL"] == "about"
    assert safe_parse_gedcom_date("EST 1850")["DATE_QUAL"] == "estimated"
    assert safe_parse_gedcom_date("BEF 1900")["DATE_QUAL"] == "before"
    assert safe_parse_gedcom_date("AFT 1900")["DATE_QUAL"] == "after"
    assert safe_parse_gedcom_date("BET 1800 AND 1820")["DATE_QUAL"] == "between"
    assert safe_parse_gedcom_date("FROM 1800 TO 1810")["DATE_QUAL"] == "range"
    assert safe_parse_gedcom_date("1850")["DATE_QUAL"] == "exact"


def test_safe_parse_gedcom_date_year_consistency():
    # Beide Funktionen müssen denselben Wert liefern (war früher inkonsistent).
    for s in ("1234", "ABT 1543", "1789", "20 JUL 1969"):
        assert safe_parse_gedcom_date(s)["YEAR"] == safe_extract_year(s)
