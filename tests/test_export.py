"""Tests für tasks.export – Sheet-Name-Eindeutigkeit + HTML-Übersicht."""
import os
import tempfile
import pytest

openpyxl = pytest.importorskip("openpyxl")

from tasks.export import export_to_excel, export_html_overview


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


def test_html_overview_renders_with_partial_state():
    """HTML-Export soll auch funktionieren, wenn nur ein Teil der
    Analyseergebnisse im State liegt — keine Tasks abhängig voneinander."""
    state = {
        "individuals": {f"@I{i}@": {"NAME": f"Test {i}"} for i in range(5)},
        "families":    {},
        "comprehensive_stats": [
            ["Gesamtanzahl Personen", 5, ""],
            ["Männer", 3, "60.0%"],
        ],
        "surname_results":  [["Müller", 3, "1800-1900", 100, 1850,
                              2, 1, "66.7% / 33.3%", 0, 0, "..."]],
    }
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as t:
        path = t.name
    try:
        assert export_html_overview(state, path) is True
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "Ahnen-Analyse" in content
        assert "Gesamtanzahl Personen" in content
        assert "Müller" in content
        # Escape muss greifen
        assert "<script>" not in content.lower()
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_html_overview_empty_state():
    state = {"individuals": {}, "families": {}}
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as t:
        path = t.name
    try:
        assert export_html_overview(state, path) is True
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "Keine Analyseergebnisse" in content
    finally:
        if os.path.exists(path):
            os.unlink(path)
