"""Tests für ancestry/core/gramps_export.py — Gramps-XML-Export."""
import os
import tempfile

import pytest

from ancestry.core.gramps_export import export_gramps


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
