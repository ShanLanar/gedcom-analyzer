"""Tests für die MRCA-Karten-Logik (EPIC 3)."""
from ancestry.core.mrca_map import (
    aggregate_mrca_places,
    build_mrca_map_html,
    parse_coords,
)


def test_parse_coords_string():
    assert parse_coords("52.5,13.4") == (52.5, 13.4)
    assert parse_coords("52.5, 13.4") == (52.5, 13.4)
    assert parse_coords("52.5;13.4") == (52.5, 13.4)


def test_parse_coords_dict_and_list():
    assert parse_coords({"lat": 48.1, "lon": 11.6}) == (48.1, 11.6)
    assert parse_coords({"latitude": 48.1, "longitude": 11.6}) == (48.1, 11.6)
    assert parse_coords([48.1, 11.6]) == (48.1, 11.6)


def test_parse_coords_invalid():
    assert parse_coords("") is None
    assert parse_coords("abc") is None
    assert parse_coords("52.5") is None
    assert parse_coords("999,999") is None        # out of range
    assert parse_coords("0,0") is None            # Null-Insel
    assert parse_coords(None) is None


def test_aggregate_basic():
    rows = [
        {"match_guid": "a", "place_name": "Berlin", "coords": "52.5,13.4",
         "person_count": 2, "side": "match"},
        {"match_guid": "b", "place_name": "Berlin", "coords": "52.5,13.4",
         "person_count": 1, "side": "sample"},
        {"match_guid": "a", "place_name": "München", "coords": "48.1,11.6",
         "person_count": 1, "side": "match"},
    ]
    places = aggregate_mrca_places(rows)
    assert places[0]["place"] == "Berlin"        # meiste Matches zuerst
    assert places[0]["match_count"] == 2
    assert places[0]["person_count"] == 3
    assert places[0]["sides"] == ["match", "sample"]
    assert places[1]["place"] == "München"
    assert places[1]["match_count"] == 1


def test_aggregate_drops_invalid_coords():
    rows = [
        {"match_guid": "a", "place_name": "NoCoord", "coords": ""},
        {"match_guid": "a", "place_name": "BadCoord", "coords": "x,y"},
        {"match_guid": "a", "place_name": "Good", "coords": "10,10"},
    ]
    places = aggregate_mrca_places(rows)
    assert [p["place"] for p in places] == ["Good"]


def test_build_html_contains_markers():
    places = aggregate_mrca_places([
        {"match_guid": "a", "place_name": "Berlin", "coords": "52.5,13.4",
         "person_count": 2, "side": "match"}])
    html = build_mrca_map_html(places, title="Test-Karte")
    assert "<!DOCTYPE html>" in html
    assert "leaflet" in html
    assert "Berlin" in html
    assert "52.5" in html and "13.4" in html
    assert "Test-Karte" in html


def test_build_html_empty_places():
    html = build_mrca_map_html([])
    assert "0 Orte" in html
    assert "L.map" in html   # Karte wird trotzdem erzeugt (zentriert auf EU)


def test_db_get_match_birthplaces_roundtrip(tmp_path):
    """End-to-End: Geburtsorte speichern und für die MRCA-Karte zurücklesen."""
    from ancestry.core.database import Database
    from ancestry.models import DnaKit, DnaMatch

    db = Database(str(tmp_path / "t.db"))
    db.upsert_kit(DnaKit(guid="KIT", name="K", test_type="AncestryDNA"))
    db.upsert_match(DnaMatch(match_guid="M1", test_guid="KIT",
                             display_name="X", shared_cm=100, has_tree=True))
    db.save_match_ancestors("KIT", "M1", ancestors=[], birthplaces=[
        {"side": "match", "place_name": "Berlin", "coords": "52.5,13.4",
         "person_count": 2},
        {"side": "match", "place_name": "Ohne", "coords": "",
         "person_count": 1},   # ohne Koordinaten → von der Query gefiltert
    ])
    rows = db.get_match_birthplaces("KIT")
    db.close()
    assert {r["place_name"] for r in rows} == {"Berlin"}
    places = aggregate_mrca_places(rows)
    assert places[0]["place"] == "Berlin"
    assert places[0]["match_count"] == 1
