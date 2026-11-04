"""Tests für ancestry/core/gramps_export.py — Gramps-XML-Export."""
import os
import tempfile
import xml.etree.ElementTree as ET

import pytest

from ancestry.core.gramps_export import export_gramps

_NS = {"g": "https://gramps-project.org/xml/1.7.1/"}


@pytest.fixture
def tmp_gramps():
    fd, path = tempfile.mkstemp(suffix=".gramps")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_export_death_event_written(tmp_gramps):
    groups = [{
        "label":       "Heinrich Finkeldey",
        "detail":      "*1832",
        "count":       1,
        "death_year":  "1890",
        "death_place": "Osnabrück",
        "matches":     [("G1", "Match A", "FF", 4, 75.0)],
    }]
    export_gramps(groups, tmp_gramps)
    content = open(tmp_gramps, encoding="utf-8").read()
    assert '<type>Death</type>' in content
    assert 'val="1890"' in content
    assert '<eventref hlink="_' in content and 'type="Death"' in content


def test_export_no_death_event_when_death_data_absent(tmp_gramps):
    groups = [{
        "label":   "Anna Müller",
        "detail":  "*1850",
        "count":   1,
        "matches": [("G1", "Match B", "MF", 4, 60.0)],
    }]
    export_gramps(groups, tmp_gramps)
    content = open(tmp_gramps, encoding="utf-8").read()
    assert '<type>Death</type>' not in content
    assert 'type="Death"' not in content


def test_export_place_objects_created_and_resolvable(tmp_gramps):
    """Scrum Sprint 8 (Archivar): <place hlink="..."> in einem Event verwies
    vorher auf einen Hash des Ortsnamens, OHNE dass je ein <placeobj>-Record
    mit diesem Handle existierte — ein unauflösbarer (dangling) Verweis, der
    den Ortsnamen beim Import nach Gramps komplett verloren gehen ließ."""
    groups = [{
        "label":       "Heinrich Finkeldey",
        "detail":      "*1832",
        "count":       1,
        "birth_place": "Bramsche, Niedersachsen",
        "death_year":  "1890",
        "death_place": "Osnabrück, Niedersachsen",
        "matches":     [("G1", "Match A", "FF", 4, 75.0)],
    }]
    export_gramps(groups, tmp_gramps)
    root = ET.parse(tmp_gramps).getroot()

    places = root.find("g:places", _NS)
    assert places is not None, "<places>-Element fehlt komplett"
    placeobjs = places.findall("g:placeobj", _NS)
    assert len(placeobjs) == 2, "Geburts- und Sterbeort müssen je einen placeobj ergeben"

    handle_to_name = {}
    for po in placeobjs:
        pname = po.find("g:pname", _NS)
        assert pname is not None and pname.get("value"), \
            "placeobj ohne pname/value ist für Gramps nicht auflösbar"
        handle_to_name[po.get("handle")] = pname.get("value")

    # Jeder <place hlink="..."> in den Events muss auf einen echten placeobj zeigen.
    place_refs = root.findall(".//g:event/g:place", _NS)
    assert place_refs, "Keine <place>-Referenzen in den Events gefunden"
    referenced_names = set()
    for ref in place_refs:
        hlink = ref.get("hlink")
        assert hlink in handle_to_name, \
            f"<place hlink='{hlink}'> zeigt auf keinen existierenden placeobj"
        referenced_names.add(handle_to_name[hlink])
    assert referenced_names == {"Bramsche, Niedersachsen", "Osnabrück, Niedersachsen"}


def test_export_same_place_deduplicated(tmp_gramps):
    """Gleicher Ortsname (Geburt == Sterbeort) erzeugt nur EINEN placeobj."""
    groups = [{
        "label":       "Anna Finkeldey",
        "detail":      "*1832",
        "count":       1,
        "birth_place": "Osnabrück",
        "death_year":  "1890",
        "death_place": "Osnabrück",
        "matches":     [("G1", "Match A", "FF", 4, 75.0)],
    }]
    export_gramps(groups, tmp_gramps)
    root = ET.parse(tmp_gramps).getroot()
    placeobjs = root.find("g:places", _NS).findall("g:placeobj", _NS)
    assert len(placeobjs) == 1


def test_export_death_event_omitted_for_masked_living_person(tmp_gramps):
    groups = [{
        "label":      "Peter Beispiel",
        "detail":     "*1955",
        "count":      1,
        "matches":    [("G1", "Match C", "F", 2, 1750.0)],
    }]
    export_gramps(groups, tmp_gramps, mask_living=True)
    content = open(tmp_gramps, encoding="utf-8").read()
    assert "[privat]" in content
    assert '<type>Death</type>' not in content
