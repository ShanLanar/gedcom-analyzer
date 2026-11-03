"""Tests für lib.gedcom – Datum/Jahres-Parser."""
from lib.gedcom import julian_to_gregorian, safe_extract_year, safe_parse_gedcom_date


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


# ── Julianischer Kalender (@#DJULIAN@) ────────────────────────────────────────


def test_julian_to_gregorian_1582_calendar_switch():
    # Letzter julianischer Tag (katholisch) vor dem 10-Tage-Sprung 1582.
    assert julian_to_gregorian(1582, 10, 4) == (1582, 10, 14)
    # Folgetag (JDN+1) landet direkt auf dem ersten gregorianischen Tag.
    assert julian_to_gregorian(1582, 10, 5) == (1582, 10, 15)


def test_julian_to_gregorian_1700_leap_year_divergence():
    # 1700 ist im julianischen Kalender ein Schaltjahr, im gregorianischen
    # NICHT (nicht durch 400 teilbar) — Standard-Testfall für Kalenderfehler.
    assert julian_to_gregorian(1700, 2, 29) == (1700, 3, 11)


def test_julian_to_gregorian_1918_russian_calendar_decree():
    # Russland: auf den 31. Januar (julianisch) folgte der 14. Februar
    # (gregorianisch) — belegter historischer Kalenderwechsel, 13-Tage-Sprung.
    assert julian_to_gregorian(1918, 1, 31) == (1918, 2, 13)
    assert julian_to_gregorian(1918, 2, 1) == (1918, 2, 14)


def test_julian_to_gregorian_1731_day_shift_without_year_start_convention():
    # Reiner 11-Tage-Verschub für das 18. Jh. — bewusst OHNE die englische
    # Neujahrs-Konvention (die zusätzlich den Jahreswechsel verschieben würde).
    assert julian_to_gregorian(1731, 2, 11) == (1731, 2, 22)


def test_safe_parse_gedcom_date_julian_escape_converts():
    parsed = safe_parse_gedcom_date("@#DJULIAN@ 31 JAN 1918")
    assert parsed["DATE"] == "13 FEB 1918"
    assert parsed["YEAR"] == 1918
    assert parsed["DATE_QUAL"] == "exact"


def test_safe_parse_gedcom_date_julian_escape_without_day_strips_escape_only():
    # Ohne Tagesgenauigkeit wird NICHT geraten — nur der Escape entfernt.
    parsed = safe_parse_gedcom_date("@#DJULIAN@ FEB 1700")
    assert parsed["DATE"] == "FEB 1700"
    assert parsed["YEAR"] == 1700


def test_safe_parse_gedcom_date_gregorian_escape_is_stripped():
    parsed = safe_parse_gedcom_date("@#DGREGORIAN@ 15 OCT 1582")
    assert parsed["DATE"] == "15 OCT 1582"
    assert parsed["YEAR"] == 1582
    assert parsed["DATE_QUAL"] == "exact"


def test_safe_parse_gedcom_date_without_escape_unchanged():
    # Regressionsschutz: der häufige Fall (kein Escape) darf sich nicht ändern.
    assert safe_parse_gedcom_date("11 FEB 1850")["DATE"] == "11 FEB 1850"
