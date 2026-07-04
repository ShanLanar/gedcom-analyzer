"""Tests für die Familien-Rekonstruktion aus Kirchenbuch-NER (Sprint 8)."""
from ancestry.core.matricula_reconstruct import reconstruct_identities


def _row(name, koeln="", ort="", year=None, rolle=""):
    return {"name_raw": name, "koeln_code": koeln, "name_norm": name.lower(),
            "ort": ort, "event_year": year, "rolle": rolle}


def test_links_same_name_place_and_window():
    rows = [
        _row("Hans Meyer", koeln="0678", ort="Damme", year=1734, rolle="pate"),
        _row("Hans Meyer", koeln="0678", ort="Damme", year=1756, rolle="braeutigam"),
    ]
    out = reconstruct_identities(rows)
    assert len(out) == 1
    cand = out[0]
    assert cand["size"] == 2
    assert cand["places"] == ["damme"]
    assert set(cand["roles"]) == {"pate", "braeutigam"}
    assert cand["year_min"] == 1734
    assert cand["year_max"] == 1756


def test_different_places_not_linked():
    rows = [
        _row("Hans Meyer", koeln="0678", ort="Damme", year=1734),
        _row("Hans Meyer", koeln="0678", ort="Vechta", year=1740),
    ]
    assert reconstruct_identities(rows) == []


def test_year_gap_beyond_window_splits():
    rows = [
        _row("Hans Meyer", koeln="0678", ort="Damme", year=1700),
        _row("Hans Meyer", koeln="0678", ort="Damme", year=1790),  # 90 J. Abstand
    ]
    assert reconstruct_identities(rows, life_window=60) == []


def test_missing_place_still_links_on_name_and_year():
    rows = [
        _row("Anna Schulte", koeln="0648", ort="", year=1720),
        _row("Anna Schulte", koeln="0648", ort="Lohne", year=1745),
    ]
    out = reconstruct_identities(rows)
    assert len(out) == 1
    assert out[0]["places"] == ["lohne"]


def test_singletons_not_reported():
    rows = [_row("Einzel Person", koeln="1234", ort="X", year=1800)]
    assert reconstruct_identities(rows) == []


def test_phonetic_variants_group_together():
    """Gleicher Kölner Code trotz abweichender Schreibweise → eine Identität."""
    rows = [
        _row("Meyer",  koeln="067", ort="Damme", year=1730),
        _row("Meier",  koeln="067", ort="Damme", year=1735),
        _row("Mayer",  koeln="067", ort="Damme", year=1740),
    ]
    out = reconstruct_identities(rows)
    assert len(out) == 1
    assert out[0]["size"] == 3


def test_two_distinct_persons_same_name_different_places():
    rows = [
        _row("Hans Meyer", koeln="0678", ort="Damme",  year=1730),
        _row("Hans Meyer", koeln="0678", ort="Damme",  year=1735),
        _row("Hans Meyer", koeln="0678", ort="Vechta", year=1732),
        _row("Hans Meyer", koeln="0678", ort="Vechta", year=1738),
    ]
    out = reconstruct_identities(rows)
    # zwei getrennte Zweier-Cluster (Damme vs. Vechta)
    assert len(out) == 2
    assert all(c["size"] == 2 for c in out)
    assert {c["places"][0] for c in out} == {"damme", "vechta"}
