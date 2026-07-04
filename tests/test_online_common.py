"""Tests für die zentralisierten Online-Helfer (tasks/_online_common.py)."""
from tasks._online_common import first_place, split_name, year_of


def test_split_name_gedcom_slashes():
    assert split_name("Hans Peter /Müller/") == ("Hans Peter", "Müller")


def test_split_name_no_slashes_last_word_is_surname():
    assert split_name("Anna Maria Schulte") == ("Anna Maria", "Schulte")


def test_split_name_strips_symbols_and_migration_marker():
    assert split_name("✠ Johann mig.1852 /Kovermann/") == ("Johann", "Kovermann")


def test_split_name_single_word():
    assert split_name("Meyer") == ("Meyer", "")


def test_split_name_empty():
    assert split_name("") == ("", "")


def test_year_of_prefers_year_field():
    assert year_of({"YEAR": 1823, "DATE": "1900"}) == 1823


def test_year_of_extracts_from_date():
    assert year_of({"DATE": "ABT 1756"}) == 1756


def test_year_of_none():
    assert year_of(None) is None
    assert year_of({}) is None


def test_first_place():
    assert first_place("Damme, Osnabrück, Niedersachsen") == "Damme"
    assert first_place("") == ""


def test_helpers_match_legacy_behaviour():
    """Zentralisierte Helfer verhalten sich wie die alten Modul-Aliase."""
    from tasks.externe_quellen import _first, _split_name, _yr
    assert _split_name is split_name
    assert _yr is year_of
    assert _first is first_place
