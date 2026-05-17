"""Tests für tasks.migration._rel_distance (deutscher Label-Parser)."""
from tasks.migration import _rel_distance
from lib.helpers import relationship_label


def test_rel_distance_root_and_direct():
    assert _rel_distance("Selbst") == 0
    assert _rel_distance("root") == 0
    assert _rel_distance("Elternteil") == 1
    assert _rel_distance("Großelternteil") == 2
    assert _rel_distance("Urgroßelternteil") == 3
    assert _rel_distance("2-fach Urgroßelternteil") == 4


def test_rel_distance_siblings_uncles():
    assert _rel_distance("Geschwister") == 1
    assert _rel_distance("Onkel/Tante") == 2
    assert _rel_distance("Großonkel/-tante") == 3


def test_rel_distance_cousins():
    # Cousin 1. Grades = 1*2 + 0 + 3 = 5 (im Code)
    assert _rel_distance("Cousin 1. Grades") == 5
    assert _rel_distance("Cousin 2. Grades") == 7
    assert _rel_distance("Cousin 1. Grades, 1x entfernt") == 6


def test_rel_distance_consumes_relationship_label_output():
    """Vertraglich: jeder Output von relationship_label muss von
    _rel_distance ohne 999-Fallback verarbeitet werden."""
    cases = [
        relationship_label(1, 0, True),
        relationship_label(2, 0, True),
        relationship_label(3, 0, True),
        relationship_label(1, 1, False),
        relationship_label(2, 1, False),
        relationship_label(2, 2, False),
        relationship_label(3, 3, False),
        relationship_label(2, 3, False),
    ]
    for label in cases:
        assert _rel_distance(label) < 999, f"unparsed: {label!r}"
