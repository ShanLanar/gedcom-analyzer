"""Regressionstest: robuste JSON-Array-Extraktion aus Claude-Antworten (P0-3).

Der frühere greedy-Regex re.search(r"\\[.*\\]") matchte bei Begleittext vom
ersten '[' bis zum letzten ']' → ungültiges JSON → Seite still verworfen.
"""
from ancestry.tools.scan_matricula_kirchspiel import _parse_json_array


def test_direct_array():
    assert _parse_json_array('[{"a": 1}]') == [{"a": 1}]


def test_markdown_fence():
    assert _parse_json_array('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_surrounding_text():
    assert _parse_json_array('Hier die Daten: [{"nr": "1"}] fertig') == [{"nr": "1"}]


def test_greedy_trap_skips_pseudo_bracket():
    # '[Hinweis]' ist ein balanciertes, aber ungültiges Array → überspringen,
    # das nächste gültige Array liefern (früher: alles verworfen).
    assert _parse_json_array('[Hinweis] Text [ {"x": 2} ]') == [{"x": 2}]


def test_bracket_inside_string_not_confused():
    assert _parse_json_array('[{"s": "hat ] klammer"}]') == [{"s": "hat ] klammer"}]


def test_empty_array_is_valid_empty_page():
    # [] = echte leere Seite (→ 'done'), NICHT None (Parse-Fehler → 'error')
    assert _parse_json_array("[]") == []


def test_unparseable_returns_none():
    assert _parse_json_array("kein array hier") is None
    assert _parse_json_array("[unbalanced") is None
    assert _parse_json_array("") is None


def test_object_not_list_returns_none():
    # Ein einzelnes Objekt statt Array ist kein gültiges Seiten-Ergebnis.
    assert _parse_json_array('{"a": 1}') is None
