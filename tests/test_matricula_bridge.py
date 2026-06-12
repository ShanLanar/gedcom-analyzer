"""Tests für ancestry/core/matricula_bridge.py — Kirchenbuch ↔ DNA-Match."""

import os
import sqlite3
import tempfile

import pytest

from ancestry.core.database import Database
from ancestry.core.matricula_bridge import (
    find_matricula_for_match,
    find_matricula_for_names,
    _pedigree_surnames,
)
from ancestry.models import DnaMatch


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)
    # Matricula-Tabellen anlegen (normalerweise von scan_matricula_kirchspiel.py)
    with database._cursor() as cur:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS source_matrikula_entries (
                entry_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id    TEXT NOT NULL,
                page_nr    INTEGER,
                entry_type TEXT DEFAULT '',
                event_date TEXT DEFAULT '',
                event_year INTEGER,
                person_name  TEXT DEFAULT '',
                person2_name TEXT DEFAULT '',
                father_name  TEXT DEFAULT '',
                mother_name  TEXT DEFAULT '',
                village      TEXT DEFAULT '',
                notes        TEXT DEFAULT '',
                raw_json     TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS name_index (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id   INTEGER NOT NULL,
                book_id    TEXT NOT NULL,
                page_nr    INTEGER NOT NULL,
                name_raw   TEXT NOT NULL,
                name_norm  TEXT NOT NULL,
                koeln_code TEXT NOT NULL,
                name_role  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ni_koeln ON name_index(koeln_code);
        """)
    yield database
    database.close()
    if os.path.exists(path):
        os.unlink(path)


def _add_entry(db, book_id, year, person_name, father_name="", village="", entry_type="Taufe"):
    with db._cursor() as cur:
        cur.execute("""
            INSERT INTO source_matrikula_entries
              (book_id, page_nr, entry_type, event_year, person_name, father_name, village)
            VALUES (?,1,?,?,?,?,?)
        """, (book_id, entry_type, year, person_name, father_name, village))
        entry_id = cur.lastrowid
        from ancestry.core.bridge._text import _koelner, _norm
        for name, role in [(person_name, "person"), (father_name, "father")]:
            if name:
                cur.execute("""
                    INSERT INTO name_index
                      (entry_id, book_id, page_nr, name_raw, name_norm, koeln_code, name_role)
                    VALUES (?,?,1,?,?,?,?)
                """, (entry_id, book_id, name, _norm(name), _koelner(name), role))
    return entry_id


def test_exact_surname_match(db):
    _add_entry(db, "de/os/ostercappeln/b1", 1812, "Heinrich Kovermann",
               father_name="Johannes Kovermann", village="Ostercappeln")
    hits = find_matricula_for_names(db, ["Kovermann"])
    assert len(hits) == 2  # person + father
    assert any(h["person_name"] == "Heinrich Kovermann" for h in hits)
    assert hits[0]["exact_match"] == 1


def test_phonetic_match(db):
    # Kovermann ↔ Kofermann (Kölner Phonetik: beide 1376)
    _add_entry(db, "de/os/ostercappeln/b1", 1790, "Johann Kofermann")
    hits = find_matricula_for_names(db, ["Kovermann"])
    assert len(hits) >= 1
    assert hits[0]["exact_match"] == 0  # phonetisch, nicht exakt


def test_no_match(db):
    _add_entry(db, "de/os/b1", 1800, "Hans Mustermann")
    hits = find_matricula_for_names(db, ["Schreiber"])
    assert hits == []


def test_find_for_match_via_pedigree(db):
    db.upsert_match(DnaMatch(match_guid="m-1", test_guid="kit-1",
                             display_name="Test Match", shared_cm=50))
    db.save_match_pedigree("kit-1", "m-1", [
        {"given_name": "Heinrich", "surname": "Kovermann", "generation": 2,
         "birth_year": 1780, "birth_place": "Ostercappeln", "ahnen_path": "F"},
        {"given_name": "Anna", "surname": "Meyer", "generation": 3,
         "birth_year": 1760, "birth_place": "", "ahnen_path": "FM"},
    ])
    _add_entry(db, "de/os/b1", 1810, "Maria Kovermann")
    hits = find_matricula_for_match(db, "kit-1", "m-1", min_generation=2)
    assert len(hits) >= 1


def test_pedigree_surnames_min_generation(db):
    db.upsert_match(DnaMatch(match_guid="m-2", test_guid="kit-1",
                             display_name="X", shared_cm=30))
    db.save_match_pedigree("kit-1", "m-2", [
        {"given_name": "Karl", "surname": "Schulz", "generation": 1,
         "birth_year": 1900, "birth_place": "", "ahnen_path": ""},
        {"given_name": "Otto", "surname": "Müller", "generation": 3,
         "birth_year": 1850, "birth_place": "", "ahnen_path": "F"},
    ])
    surnames = _pedigree_surnames(db, "kit-1", "m-2", min_generation=2)
    assert "Müller" in surnames
    assert "Schulz" not in surnames  # generation 1 < 2


def test_empty_pedigree_returns_no_hits(db):
    db.upsert_match(DnaMatch(match_guid="m-3", test_guid="kit-1",
                             display_name="Y", shared_cm=20))
    hits = find_matricula_for_match(db, "kit-1", "m-3")
    assert hits == []


def test_no_matricula_tables_returns_empty(db):
    """Wenn Matricula-Tabellen nicht existieren, kein Crash."""
    with db._cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS name_index")
        cur.execute("DROP TABLE IF EXISTS source_matrikula_entries")
    hits = find_matricula_for_names(db, ["Kovermann"])
    assert hits == []
