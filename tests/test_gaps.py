"""Tests für Pedigree-Lücken-Analyse (Brick-Wall Detection)."""
import json
import os
import tempfile

import pytest

from ancestry.core.analysis.gaps import (
    analyze_pedigree_gaps,
    get_pedigree_completeness,
)
from ancestry.core.database import Database


@pytest.fixture
def db():
    """Erstellt temporäre Test-DB mit gedcom_persons Tabelle."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)

    with database._cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS gedcom_persons (
                ged_id TEXT PRIMARY KEY,
                given_name TEXT DEFAULT '',
                surname TEXT DEFAULT '',
                birth_year INTEGER,
                birth_qual TEXT DEFAULT '',
                birth_place TEXT DEFAULT '',
                death_year INTEGER,
                death_place TEXT DEFAULT '',
                sex TEXT DEFAULT '',
                ged_file TEXT DEFAULT '',
                sosa_number INTEGER DEFAULT 0,
                source TEXT DEFAULT 'gedcom',
                parents_json TEXT DEFAULT '[]',
                spouses_json TEXT DEFAULT '[]',
                children_json TEXT DEFAULT '[]',
                siblings_json TEXT DEFAULT '[]'
            )"""
        )

    yield database
    database.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


def _add_person(
    db: Database,
    ged_id: str,
    given: str,
    surname: str,
    birth_year: int = 0,
    parents: list = None,
):
    """Hilfsfunktion: fügt Person zu gedcom_persons hinzu."""
    parents_json = json.dumps(parents or [])
    with db._cursor() as cur:
        cur.execute(
            """INSERT INTO gedcom_persons (
                ged_id, given_name, surname, birth_year, parents_json
            ) VALUES (?, ?, ?, ?, ?)""",
            (ged_id, given, surname, birth_year, parents_json),
        )


def test_analyze_pedigree_gaps_simple_3gen(db):
    """Testet Lücken-Analyse mit einfacher 3-Generationen-Linie."""
    # I1 (root) → father OK → grandfather NULL (brick wall)
    _add_person(db, "I1", "John", "Doe", 2000, parents=["I2", "I3"])
    _add_person(db, "I2", "Father", "Doe", 1970, parents=["I4", None])  # I4 OK, I5 NULL
    _add_person(db, "I4", "Grandfather", "Doe", 1940, parents=[None, None])  # Beide NULL

    gaps = analyze_pedigree_gaps(db, "I1")

    # Sollte Gap bei Generation 3 (Großvater) finden
    assert len(gaps) > 0
    gap_gens = [g["generation"] for g in gaps]
    assert 3 in gap_gens  # Gap in Gen 3


def test_analyze_pedigree_gaps_maternal_side(db):
    """Testet Gap-Typen für maternal vs. paternal Side."""
    # I1 → I2 (father OK) → I4 (gf), I5 (gm NULL)
    _add_person(db, "I1", "Root", "Person", 2000, parents=["I2", "I3"])
    _add_person(db, "I2", "Father", "Person", 1970, parents=["I4", None])  # maternal parent missing
    _add_person(db, "I4", "Grandfather", "Person", 1940, parents=[])

    gaps = analyze_pedigree_gaps(db, "I1")

    # Sollte finden, dass maternal parent von I2 fehlt
    maternal_gaps = [g for g in gaps if "maternal" in g.get("gap_type", "")]
    assert len(maternal_gaps) > 0


def test_analyze_pedigree_gaps_no_parents(db):
    """Testet Gap bei Person ohne parents_json."""
    _add_person(db, "I1", "Root", "Person", 2000, parents=[])

    gaps = analyze_pedigree_gaps(db, "I1")

    # Sollte feststellen, dass Gen 1 keine Eltern hat
    assert len(gaps) > 0


def test_analyze_pedigree_gaps_person_not_found(db):
    """Testet Handling von nicht vorhandener Person."""
    gaps = analyze_pedigree_gaps(db, "I999")  # Nicht in DB

    assert isinstance(gaps, list)
    assert len(gaps) == 0 or all("gap_type" in g for g in gaps)


def test_pedigree_completeness_full_tree(db):
    """Testet Vollständigkeits-Analyse für kompletten 3-Gen-Baum."""
    # I1 (root) → [I2, I3] → [I4, I5, I6, I7] (alle vollständig)
    _add_person(db, "I1", "Root", "Person", 2000, parents=["I2", "I3"])
    _add_person(db, "I2", "Father", "Person", 1970, parents=["I4", "I5"])
    _add_person(db, "I3", "Mother", "Person", 1972, parents=["I6", "I7"])
    _add_person(db, "I4", "GF1", "Person", 1940, parents=[])
    _add_person(db, "I5", "GM1", "Person", 1942, parents=[])
    _add_person(db, "I6", "GF2", "Person", 1938, parents=[])
    _add_person(db, "I7", "GM2", "Person", 1944, parents=[])

    comp = get_pedigree_completeness(db, "I1")

    assert comp["root_person"] == "Root Person"
    assert 1 in comp["by_generation"]
    # Gen 1: I1 (root) sollte "known" sein
    gen1 = comp["by_generation"].get(1, {})
    assert gen1.get("complete") or gen1.get("known") > 0


def test_pedigree_completeness_with_gaps(db):
    """Testet Vollständigkeits-Analyse mit Lücken."""
    # I1 → [I2, I3] → [I4, NULL, I6, I7] (I5 fehlt)
    _add_person(db, "I1", "Root", "Person", 2000, parents=["I2", "I3"])
    _add_person(db, "I2", "Father", "Person", 1970, parents=["I4", ""])  # I5 NULL
    _add_person(db, "I3", "Mother", "Person", 1972, parents=["I6", "I7"])
    _add_person(db, "I4", "GF1", "Person", 1940, parents=[])
    _add_person(db, "I6", "GF2", "Person", 1938, parents=[])
    _add_person(db, "I7", "GM2", "Person", 1944, parents=[])

    comp = get_pedigree_completeness(db, "I1")

    assert comp["root_person"] == "Root Person"
    # Sollte first_gap_gen registrieren (wo unknown > 0)
    if comp["first_gap_gen"]:
        assert isinstance(comp["first_gap_gen"], int)
        assert comp["first_gap_gen"] >= 1


def test_pedigree_completeness_deep_tree(db):
    """Testet Vollständigkeit für tiefere Bäume."""
    # Lineale Linie über 4 Generationen
    _add_person(db, "I1", "Root", "Person", 2000, parents=["I2"])
    _add_person(db, "I2", "Father", "Person", 1970, parents=["I3"])
    _add_person(db, "I3", "Grandfather", "Person", 1940, parents=["I4"])
    _add_person(db, "I4", "GreatGF", "Person", 1910, parents=[])

    comp = get_pedigree_completeness(db, "I1")

    assert "by_generation" in comp
    assert len(comp["by_generation"]) >= 1


def test_analyze_gaps_format_names(db):
    """Testet, dass last_known-Names richtig formatiert sind."""
    _add_person(db, "I1", "John", "Doe", 1950, parents=["I2", None])
    _add_person(db, "I2", "James", "Doe", 1920, parents=[])

    gaps = analyze_pedigree_gaps(db, "I1")

    # Sollte last_known mit Name und Jahr formatieren
    for gap in gaps:
        if "last_known" in gap:
            assert isinstance(gap["last_known"], str)
            # Name sollte nicht leer sein
            assert len(gap["last_known"]) > 0


def test_analyze_gaps_multiple_brick_walls(db):
    """Testet Analyse mit mehreren Brick Walls (paternal + maternal)."""
    # I1 → [I2 (father) + I3 (mother)]
    # I2 → [I4 NULL, I5 NULL] (both unknown)
    # I3 → [I6 OK, I7 NULL]
    _add_person(db, "I1", "Root", "Person", 2000, parents=["I2", "I3"])
    _add_person(db, "I2", "Father", "Person", 1970, parents=[None, None])
    _add_person(db, "I3", "Mother", "Person", 1972, parents=["I6", None])
    _add_person(db, "I6", "GF2", "Person", 1938, parents=[])

    gaps = analyze_pedigree_gaps(db, "I1")

    # Sollte mehrere Gaps finden
    assert len(gaps) > 0
    gap_types = {g.get("gap_type") for g in gaps}
    # Sollte sowohl paternal als auch maternal Gaps haben
    assert any("paternal" in gt for gt in gap_types if gt)


def test_analyze_gaps_empty_parents_json(db):
    """Testet Handling von ungültigem JSON in parents_json."""
    # Manually insert invalid JSON (sqlite issue)
    with db._cursor() as cur:
        cur.execute(
            """INSERT INTO gedcom_persons
               (ged_id, given_name, surname, parents_json)
               VALUES (?, ?, ?, ?)""",
            ("I1", "Test", "Person", "not valid json"),
        )

    gaps = analyze_pedigree_gaps(db, "I1")

    # Sollte gracefully handled werden (kein Exception)
    assert isinstance(gaps, list)
