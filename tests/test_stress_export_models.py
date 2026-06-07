"""
Comprehensive pytest test suite for ancestry/core/export.py and ancestry/models/.

Covers:
  - export_csv (10 tests)
  - export_shared_csv (8 tests)
  - export_xlsx (7 tests)
  - DnaMatch model (8 tests)
  - SharedMatch model (4 tests)
  - DnaKit model (3 tests)

Total: 40 tests.
"""

import sys
import os
import types

_ANCESTRY = '/home/user/gedcom-analyzer/ancestry'
if _ANCESTRY not in sys.path:
    sys.path.append(_ANCESTRY)

if 'core' not in sys.modules:
    _core_stub = types.ModuleType('core')
    _core_stub.__path__ = [os.path.join(_ANCESTRY, 'core')]
    _core_stub.__package__ = 'core'
    sys.modules['core'] = _core_stub

import csv
import tempfile

import pytest

openpyxl = pytest.importorskip("openpyxl")

from core.export import export_csv, export_shared_csv, export_xlsx
from models import DnaKit, DnaMatch, SharedMatch


# ---------------------------------------------------------------------------
# Factories / helpers
# ---------------------------------------------------------------------------

def make_match(
    match_guid: str = "m-001",
    test_guid: str = "kit-001",
    display_name: str = "Müller, Hans",
    shared_cm: float = 250.0,
    shared_segments: int = 10,
    longest_segment: float = 45.0,
    starred: bool = False,
    note: str = "",
) -> DnaMatch:
    return DnaMatch(
        match_guid=match_guid,
        test_guid=test_guid,
        display_name=display_name,
        shared_cm=shared_cm,
        shared_segments=shared_segments,
        longest_segment=longest_segment,
        starred=starred,
        note=note,
    )


def make_shared(
    test_guid: str = "kit-001",
    match_guid_a: str = "m-001",
    match_guid_b: str = "m-002",
    display_name_b: str = "Wapelhorst, Fritz",
    shared_cm_b: float = 85.0,
    shared_cm_ab: float = 30.0,
) -> SharedMatch:
    return SharedMatch(
        test_guid=test_guid,
        match_guid_a=match_guid_a,
        match_guid_b=match_guid_b,
        display_name_b=display_name_b,
        shared_cm_b=shared_cm_b,
        shared_cm_ab=shared_cm_ab,
    )


# ===========================================================================
# EXPORT – export_csv  (10 tests)
# ===========================================================================

def test_export_csv_empty_list_returns_zero(tmp_path):
    """Empty match list → returns 0 and creates a file with only the header."""
    out = str(tmp_path / "matches.csv")
    result = export_csv([], out)
    assert result == 0
    assert os.path.exists(out)
    with open(out, encoding="utf-8-sig") as f:
        lines = f.readlines()
    # Only the header row, no data rows
    assert len(lines) == 1


def test_export_csv_single_match_returns_one(tmp_path):
    """One match → returns 1, file exists, file has exactly 2 lines."""
    out = str(tmp_path / "single.csv")
    matches = [make_match()]
    result = export_csv(matches, out)
    assert result == 1
    assert os.path.exists(out)
    with open(out, encoding="utf-8-sig") as f:
        lines = [l for l in f.readlines() if l.strip()]
    assert len(lines) == 2  # header + 1 data row


def test_export_csv_five_matches_returns_five(tmp_path):
    """Five matches → returns 5."""
    out = str(tmp_path / "five.csv")
    matches = [make_match(match_guid=f"m-{i:03d}") for i in range(5)]
    result = export_csv(matches, out)
    assert result == 5


def test_export_csv_german_umlauts_no_encoding_error(tmp_path):
    """Display names with German umlauts are written and read back without error."""
    out = str(tmp_path / "umlauts.csv")
    matches = [
        make_match(display_name="Müller, Öttker", match_guid="m-uml-1"),
        make_match(display_name="Wapelhorst, Björn", match_guid="m-uml-2"),
    ]
    export_csv(matches, out)
    with open(out, encoding="utf-8-sig") as f:
        content = f.read()
    assert "Müller" in content
    assert "Wapelhorst" in content


def test_export_csv_note_with_commas_and_quotes_properly_escaped(tmp_path):
    """Notes containing commas and double-quotes are properly CSV-escaped."""
    out = str(tmp_path / "escaped.csv")
    tricky_note = 'Beziehung unklar, "vielleicht 2. Cousin", weitere Infos'
    matches = [make_match(note=tricky_note)]
    export_csv(matches, out)
    # Re-parse with csv module – if escaping is wrong, the field count differs
    with open(out, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    # The note column must survive the round-trip
    assert tricky_note in rows[0]["Notiz"]


def test_export_csv_starred_match_written_as_ja(tmp_path):
    """A starred=True match is written with the German 'Ja' value."""
    out = str(tmp_path / "starred.csv")
    matches = [make_match(starred=True)]
    export_csv(matches, out)
    with open(out, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows[0]["Markiert"] == "Ja"


def test_export_csv_empty_note_no_crash(tmp_path):
    """Match with note='' exports cleanly and note field is empty."""
    out = str(tmp_path / "empty_note.csv")
    matches = [make_match(note="")]
    export_csv(matches, out)
    with open(out, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows[0]["Notiz"] == ""


def test_export_csv_very_long_display_name_no_crash(tmp_path):
    """A display_name of 200 characters does not crash export."""
    out = str(tmp_path / "long_name.csv")
    long_name = "A" * 200
    matches = [make_match(display_name=long_name)]
    result = export_csv(matches, out)
    assert result == 1
    assert os.path.exists(out)


def test_export_csv_overwrite_same_path_no_crash(tmp_path):
    """Calling export_csv twice with the same path overwrites without error."""
    out = str(tmp_path / "overwrite.csv")
    matches = [make_match()]
    export_csv(matches, out)
    export_csv(matches, out)
    assert os.path.exists(out)


def test_export_csv_zeros_written_correctly(tmp_path):
    """Match with shared_cm=0.0, segments=0, longest=0.0 → zeros in CSV."""
    out = str(tmp_path / "zeros.csv")
    matches = [make_match(shared_cm=0.0, shared_segments=0, longest_segment=0.0)]
    export_csv(matches, out)
    with open(out, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows[0]["Gemeinsame cM"] == "0.0"
    assert rows[0]["Segmente"] == "0"
    assert rows[0]["Längstes Segment (cM)"] == "0.0"


# ===========================================================================
# EXPORT – export_shared_csv  (8 tests)
# ===========================================================================

def test_export_shared_csv_empty_list_returns_zero(tmp_path):
    """Empty shared list → returns 0."""
    out = str(tmp_path / "shared_empty.csv")
    result = export_shared_csv([], out)
    assert result == 0


def test_export_shared_csv_three_shared_returns_three(tmp_path):
    """Three shared matches → returns 3."""
    out = str(tmp_path / "shared3.csv")
    shared = [
        make_shared(match_guid_b=f"m-{i:03d}")
        for i in range(3)
    ]
    result = export_shared_csv(shared, out)
    assert result == 3


def test_export_shared_csv_with_match_name_map_resolves_names(tmp_path):
    """With match_name_map provided, primary match name is resolved in output."""
    out = str(tmp_path / "shared_namemap.csv")
    shared = [make_shared(match_guid_a="m-001")]
    name_map = {"m-001": "Müller, Hans"}
    export_shared_csv(shared, out, match_name_map=name_map)
    with open(out, encoding="utf-8-sig") as f:
        content = f.read()
    assert "Müller" in content


def test_export_shared_csv_without_name_map_uses_empty_string(tmp_path):
    """Without match_name_map (None), the primary name column is empty."""
    out = str(tmp_path / "shared_nomap.csv")
    shared = [make_shared(match_guid_a="m-guid-xyz")]
    export_shared_csv(shared, out, match_name_map=None)
    with open(out, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows[0]["Primärer Match (Name)"] == ""


def test_export_shared_csv_special_chars_in_display_name_b_no_crash(tmp_path):
    """Special characters in display_name_b (umlauts, brackets) do not crash."""
    out = str(tmp_path / "shared_special.csv")
    shared = [make_shared(display_name_b="Schröder, Jürgen [Linie Ä]")]
    result = export_shared_csv(shared, out)
    assert result == 1
    assert os.path.exists(out)


def test_export_shared_csv_shared_cm_ab_zero_written(tmp_path):
    """shared_cm_ab=0 is written as '0.0', not empty."""
    out = str(tmp_path / "shared_zero.csv")
    shared = [make_shared(shared_cm_ab=0.0)]
    export_shared_csv(shared, out)
    with open(out, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows[0]["cM (Primär ↔ Shared)"] == "0.0"


def test_export_shared_csv_file_created_at_given_path(tmp_path):
    """File must exist at the exact path given after export."""
    out = str(tmp_path / "subdir_shared.csv")
    export_shared_csv([], out)
    assert os.path.exists(out)


def test_export_shared_csv_large_set_100_returns_100(tmp_path):
    """100 shared matches → returns 100."""
    out = str(tmp_path / "shared100.csv")
    shared = [
        make_shared(match_guid_b=f"m-{i:04d}")
        for i in range(100)
    ]
    result = export_shared_csv(shared, out)
    assert result == 100


# ===========================================================================
# EXPORT – export_xlsx  (7 tests)
# ===========================================================================

def test_export_xlsx_empty_matches_returns_zero_file_exists(tmp_path):
    """Empty match list → returns 0 and creates a valid XLSX file."""
    out = str(tmp_path / "empty.xlsx")
    result = export_xlsx([], out)
    assert result == 0
    assert os.path.exists(out)


def test_export_xlsx_ten_matches_returns_ten(tmp_path):
    """Ten matches → returns 10 and file exists."""
    out = str(tmp_path / "ten.xlsx")
    matches = [make_match(match_guid=f"m-{i:03d}") for i in range(10)]
    result = export_xlsx(matches, out)
    assert result == 10
    assert os.path.exists(out)


def test_export_xlsx_matches_and_shared_two_sheets(tmp_path):
    """With shared data provided, the XLSX file contains two sheets."""
    out = str(tmp_path / "two_sheets.xlsx")
    matches = [make_match(match_guid="m-001")]
    shared = [make_shared()]
    export_xlsx(matches, out, shared=shared)
    wb = openpyxl.load_workbook(out)
    assert len(wb.sheetnames) == 2


def test_export_xlsx_umlauts_no_encoding_error(tmp_path):
    """XLSX export with umlaut names does not raise and file is readable."""
    out = str(tmp_path / "umlauts.xlsx")
    matches = [make_match(display_name="Schäfer, Günter", match_guid="m-ü")]
    export_xlsx(matches, out)
    wb = openpyxl.load_workbook(out)
    ws = wb.active
    # Find the cell value containing the umlaut name in the data rows
    found = any(
        "Schäfer" in str(cell.value)
        for row in ws.iter_rows(min_row=2)
        for cell in row
        if cell.value
    )
    assert found


def test_export_xlsx_shared_none_no_second_sheet(tmp_path):
    """When shared=None, only one sheet is present in the workbook."""
    out = str(tmp_path / "one_sheet.xlsx")
    matches = [make_match()]
    export_xlsx(matches, out, shared=None)
    wb = openpyxl.load_workbook(out)
    assert len(wb.sheetnames) == 1


def test_export_xlsx_match_name_map_provided_no_crash(tmp_path):
    """Providing match_name_map with shared data does not crash."""
    out = str(tmp_path / "namemap.xlsx")
    matches = [make_match(match_guid="m-001")]
    shared = [make_shared(match_guid_a="m-001")]
    name_map = {"m-001": "Müller, Hans"}
    result = export_xlsx(matches, out, shared=shared, match_name_map=name_map)
    assert result == 1
    assert os.path.exists(out)


def test_export_xlsx_file_is_valid_xlsx(tmp_path):
    """The created file can be re-opened with openpyxl without error."""
    out = str(tmp_path / "valid.xlsx")
    matches = [make_match(match_guid=f"m-{i:03d}") for i in range(5)]
    export_xlsx(matches, out)
    # This must not raise
    wb = openpyxl.load_workbook(out)
    assert wb is not None
    assert wb.active is not None


# ===========================================================================
# MODELS – DnaMatch  (8 tests)
# ===========================================================================

def test_dnamatch_from_db_row_minimal():
    """from_db_row with a minimal row dict creates a valid DnaMatch."""
    row = {
        "match_guid": "m-db-001",
        "test_guid": "kit-db-001",
        "display_name": "Schmidt, Karl",
    }
    m = DnaMatch.from_db_row(row)
    assert m.match_guid == "m-db-001"
    assert m.test_guid == "kit-db-001"
    assert m.display_name == "Schmidt, Karl"


def test_dnamatch_to_dict_has_match_guid_key():
    """to_dict returns a dict containing the 'match_guid' key."""
    m = make_match()
    d = m.to_dict()
    assert isinstance(d, dict)
    assert "match_guid" in d
    assert d["match_guid"] == "m-001"


def test_dnamatch_from_api_response_creates_instance():
    """from_api_response with a minimal API dict creates a DnaMatch."""
    api_data = {
        "sampleId": "api-guid-001",
        "displayName": "Meier, Anna",
        "relationship": {
            "sharedCentimorgans": 350.0,
            "numSharedSegments": 14,
            "longestSegment": 55.0,
            "label": "1. Cousin",
            "confidence": "Medium",
            "range": "250-450",
        },
    }
    m = DnaMatch.from_api_response(api_data, test_guid="kit-001",
                                   fetched_at="2026-01-01T00:00:00Z")
    assert m.match_guid == "api-guid-001"
    assert m.display_name == "Meier, Anna"
    assert m.shared_cm == pytest.approx(350.0)
    assert m.test_guid == "kit-001"


def test_dnamatch_ethnicity_regions_default_empty_list():
    """ethnicity_regions defaults to an empty list, not None."""
    m = make_match()
    assert m.ethnicity_regions == []
    assert m.ethnicity_regions is not None


def test_dnamatch_shared_cm_defaults_to_zero():
    """shared_cm defaults to 0.0 when not explicitly provided."""
    m = DnaMatch(match_guid="x", test_guid="y", display_name="Z")
    assert m.shared_cm == pytest.approx(0.0)


def test_dnamatch_derive_relationship_875_contains_cousin():
    """875 cM → relationship label contains 'Cousin'."""
    from models.match import derive_relationship
    label = derive_relationship(875)
    assert "Cousin" in label


def test_dnamatch_derive_relationship_3500_contains_eltern_or_kind():
    """3500 cM → relationship label contains 'Elternteil' or 'Kind'."""
    from models.match import derive_relationship
    label = derive_relationship(3500)
    assert "Elternteil" in label or "Kind" in label


def test_dnamatch_starred_default_false():
    """starred defaults to False when not explicitly set."""
    m = DnaMatch(match_guid="x", test_guid="y", display_name="Z")
    assert m.starred is False


# ===========================================================================
# MODELS – SharedMatch  (4 tests)
# ===========================================================================

def test_sharedmatch_from_db_row_minimal():
    """from_db_row with minimal row dict creates a valid SharedMatch."""
    row = {
        "test_guid": "kit-001",
        "match_guid_a": "m-001",
        "match_guid_b": "m-002",
    }
    sm = SharedMatch.from_db_row(row)
    assert sm.test_guid == "kit-001"
    assert sm.match_guid_a == "m-001"
    assert sm.match_guid_b == "m-002"


def test_sharedmatch_to_dict_has_match_guid_a_key():
    """to_dict returns a dict containing the 'match_guid_a' key."""
    sm = make_shared()
    d = sm.to_dict()
    assert isinstance(d, dict)
    assert "match_guid_a" in d
    assert d["match_guid_a"] == "m-001"


def test_sharedmatch_shared_cm_ab_default_zero():
    """shared_cm_ab defaults to 0.0."""
    sm = SharedMatch(test_guid="k", match_guid_a="a", match_guid_b="b")
    assert sm.shared_cm_ab == pytest.approx(0.0)


def test_sharedmatch_from_api_response_creates_instance():
    """from_api_response with sample API dict creates a SharedMatch."""
    api_data = {
        "sampleId": "sm-api-002",
        "displayName": "Becker, Fritz",
        "relationship": {
            "sharedCentimorgans": 75.0,
            "numSharedSegments": 4,
            "label": "3. Cousin",
            "matchInCommon": {"sharedCentimorgans": 22.0},
        },
    }
    sm = SharedMatch.from_api_response(
        api_data,
        test_guid="kit-001",
        match_guid_a="m-001",
        fetched_at="2026-01-01T00:00:00Z",
    )
    assert sm.match_guid_b == "sm-api-002"
    assert sm.shared_cm_b == pytest.approx(75.0)
    assert sm.shared_cm_ab == pytest.approx(22.0)
    assert sm.test_guid == "kit-001"
    assert sm.match_guid_a == "m-001"


# ===========================================================================
# MODELS – DnaKit  (3 tests)
# ===========================================================================

def test_dnakit_guid_and_name_set():
    """DnaKit constructor sets guid and name correctly."""
    kit = DnaKit("guid123", "Mein Test")
    assert kit.guid == "guid123"
    assert kit.name == "Mein Test"


def test_dnakit_to_dict_has_guid_key():
    """to_dict returns a dict containing the 'guid' key."""
    kit = DnaKit("guid123", "Mein Test")
    d = kit.to_dict()
    assert isinstance(d, dict)
    assert "guid" in d
    assert d["guid"] == "guid123"


def test_dnakit_is_owner_defaults_false():
    """is_owner defaults to False when not explicitly provided."""
    kit = DnaKit(guid="g", name="n")
    assert kit.is_owner is False
