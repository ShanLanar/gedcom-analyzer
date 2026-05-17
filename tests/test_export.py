"""Tests für tasks.export – Sheet-Name-Eindeutigkeit."""
import os
import tempfile
import pytest

openpyxl = pytest.importorskip("openpyxl")

from tasks.export import export_to_excel


def test_sheet_names_dedupe_on_31_char_collision():
    # Zwei Namen mit identischem 31-Zeichen-Präfix: openpyxl trunkiert auf 31
    # und würde sonst einen DuplicateSheetError werfen.
    long1 = "Osnabrück Gemeinde Sehr Lang Name AAA"
    long2 = "Osnabrück Gemeinde Sehr Lang Name BBB"
    sheets = [
        (long1, ["a", "b"], [[1, 2], [3, 4]]),
        (long2, ["a", "b"], [[5, 6]]),
    ]
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as t:
        path = t.name
    try:
        ok = export_to_excel(sheets, path)
        assert ok
        wb = openpyxl.load_workbook(path)
        # Beide Sheets erreicht — Title-Länge ≤ 31 und unterschiedlich.
        assert len(wb.sheetnames) == 2
        assert wb.sheetnames[0] != wb.sheetnames[1]
        for name in wb.sheetnames:
            assert len(name) <= 31
    finally:
        if os.path.exists(path):
            os.unlink(path)
