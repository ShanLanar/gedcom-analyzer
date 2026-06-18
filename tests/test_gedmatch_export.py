"""Tests für den GEDmatch-One-to-Many-Export (EPIC 4)."""
from ancestry.core.gedmatch_export import (
    GEDMATCH_COLUMNS,
    export_gedmatch_matches,
)


def _m(**kw):
    base = {"match_guid": "K1", "display_name": "Müller, Hans",
            "shared_cm": 100.0, "longest_segment": 20.0, "source": "ancestry"}
    base.update(kw)
    return base


def test_header_and_columns():
    out = export_gedmatch_matches([_m()])
    header = out.splitlines()[0].split("\t")
    assert header == GEDMATCH_COLUMNS
    assert header[0] == "Kit_Number" and header[5] == "Total_cM"


def test_row_values():
    out = export_gedmatch_matches([_m(shared_cm=123.45, longest_segment=15.6)])
    cells = out.splitlines()[1].split("\t")
    assert cells[0] == "K1"
    assert cells[1] == "Müller, Hans"
    assert cells[5] == "123.5"        # auf 1 Nachkommastelle
    assert cells[6] == "15.6"
    assert cells[10] == "Ancestry"    # Quelle gemappt


def test_sorted_desc_and_min_cm():
    matches = [_m(match_guid="A", shared_cm=50),
               _m(match_guid="B", shared_cm=300),
               _m(match_guid="C", shared_cm=10)]
    out = export_gedmatch_matches(matches, min_cm=20)
    kits = [ln.split("\t")[0] for ln in out.splitlines()[1:]]
    assert kits == ["B", "A"]          # C (<20 cM) gefiltert, absteigend


def test_empty():
    out = export_gedmatch_matches([])
    assert out.splitlines() == ["\t".join(GEDMATCH_COLUMNS)]


def test_accepts_objects():
    class Obj:
        match_guid = "X1"
        display_name = "Test"
        shared_cm = 80.0
        longest_segment = 0.0
        source = "myheritage"
    out = export_gedmatch_matches([Obj()])
    cells = out.splitlines()[1].split("\t")
    assert cells[0] == "X1"
    assert cells[6] == ""             # kein longest_segment → leer
    assert cells[10] == "MyHeritage"


def test_roundtrip_columns_match_importer_doc():
    # Die Spaltenanzahl entspricht dem im Importer dokumentierten Format
    assert len(GEDMATCH_COLUMNS) == 15
