"""Tests für den druckbaren Triangulations-HTML-Bericht (EPIC 3)."""
from ancestry.core.triangulation_report import build_triangulation_report_html


def _tg(chrom, members):
    return {"chromosome": chrom, "chromosome_label": str(chrom),
            "region_start": 10_000_000, "region_end": 25_000_000,
            "members": members}


def _m(guid, cm, start=10_000_000, end=25_000_000):
    return {"match_guid": guid, "length_cm": cm, "start": start, "end": end}


def test_empty():
    html = build_triangulation_report_html([])
    assert "<!DOCTYPE html>" in html
    assert "Keine Triangulationsgruppen" in html
    assert "0 Triangulationsgruppen" in html


def test_basic_report():
    tgs = [_tg(3, [_m("A", 30.0), _m("B", 20.0)])]
    html = build_triangulation_report_html(
        tgs, name_by_guid={"A": "Müller, Hans"}, kit_label="KIT1")
    assert "Triangulations-Bericht" in html
    assert "Müller, Hans" in html          # Name aufgelöst
    assert "B" in html                      # GUID-Fallback
    assert "1 Triangulationsgruppen" in html
    assert "2 Mitglieder" in html
    assert "10.0–25.0 Mbp" in html
    assert "30.0" in html and "20.0" in html


def test_sorted_largest_first():
    tgs = [_tg(5, [_m("x", 8.0)]), _tg(1, [_m("a", 10.0), _m("b", 9.0), _m("c", 8.0)])]
    html = build_triangulation_report_html(tgs)
    # die 3-köpfige TG (Chr 1) muss vor der 1-köpfigen (Chr 5) stehen
    assert html.index("Chr&nbsp;1") < html.index("Chr&nbsp;5")


def test_html_escaping():
    tgs = [_tg(2, [_m("g", 12.0)])]
    html = build_triangulation_report_html(tgs, name_by_guid={"g": "<script>x</script>"})
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_handles_missing_fields():
    tgs = [{"chromosome": 7, "members": [{"match_guid": "z"}]}]  # keine cM/Region
    html = build_triangulation_report_html(tgs)
    assert "TG" in html and "Chr&nbsp;7" in html
