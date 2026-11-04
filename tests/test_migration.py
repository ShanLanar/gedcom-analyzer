"""Tests für tasks.migration._rel_distance (deutscher Label-Parser)."""
from tasks.migration import _rel_distance, _HIST_CONTEXT, CORRELATION_HEADERS
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


def test_rel_distance_consumes_half_cousin_label():
    """Scrum Sprint 8: relationship_label() liefert jetzt auch 'Halb-Cousin
    N. Grades' (full_share=False) — _rel_distance muss das genauso wie den
    Voll-Cousin parsen (Regex matcht "cousin" als Teilstring, Präfix egal)."""
    assert _rel_distance("Halb-Cousin 1. Grades") == 5
    assert _rel_distance("Halb-Cousin 1. Grades, 1x entfernt") == 6


# ── Historischer Kontext (Scrum Sprint 8, Historiker) ─────────────────────────

def test_hist_context_no_us_civil_war_in_1870s_bucket():
    """Der US-Bürgerkrieg endete 1865, nicht 1870-1880 (das ist die
    Reconstruction-/Gilded-Age-Periode) — die 1870-1880-Bucket-Beschreibung
    durfte den Bürgerkrieg nicht mehr erwähnen."""
    text = next(v for (s, e), v in _HIST_CONTEXT.items() if (s, e) == (1870, 1880))
    assert "Bürgerkrieg" not in text
    assert "Gründerkrise" in text


def test_hist_context_covers_both_world_wars():
    """Vorher fehlten 1914-1918 (zwischen 1900-1914 und 1919-1933) und
    1939-1945 (zwischen 1933-1939 und 1945-1955) komplett — ausgerechnet
    die Jahre mit der stärksten Verzerrung der Migrationsmuster."""
    assert any(s <= 1916 <= e for (s, e) in _HIST_CONTEXT), \
        "1916 (Erster Weltkrieg) fällt in keine _HIST_CONTEXT-Bucket"
    assert any(s <= 1942 <= e for (s, e) in _HIST_CONTEXT), \
        "1942 (Zweiter Weltkrieg) fällt in keine _HIST_CONTEXT-Bucket"
    ww1 = next(v for (s, e), v in _HIST_CONTEXT.items() if s <= 1916 <= e)
    ww2 = next(v for (s, e), v in _HIST_CONTEXT.items() if s <= 1942 <= e)
    assert "Weltkrieg" in ww1
    assert "Weltkrieg" in ww2


def test_correlation_header_not_claiming_historical_social_mobility():
    """Scrum Sprint 8 (Historiker): die DEVELOPED-Länderliste ist eine
    HEUTIGE Klassifikation, auf Migrationen des 19. Jh. angewendet ein
    Kategoriefehler (1850 nach Iowa war damals Siedlungsgebiet, nicht
    'entwickelt'). Die Spalte heißt jetzt ehrlich nach heutiger
    Länderklassifikation, nicht mehr 'Soziale Mobilität'."""
    assert "Soziale Mobilität" not in CORRELATION_HEADERS
    assert any("heutige" in h.lower() for h in CORRELATION_HEADERS)
