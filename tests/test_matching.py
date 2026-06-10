"""Tests für ancestry/core/bridge/matching.py."""
import os
import tempfile

import pytest

from ancestry.core.bridge.matching import (
    _parse_ancestor_name,
    path_to_sosa,
    infer_side_from_links,
    run_match_all,
)
from ancestry.core.bridge.gedcom_import import ensure_tables
from ancestry.core.database import Database


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)
    ensure_tables(database)
    yield database
    database.close()


def _insert_link(db, test_guid, match_guid, ahnen_path, ged_id,
                 ged_given="", ged_surname="", total_score=0.9):
    with db._cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO gedcom_links
               (test_guid, match_guid, ahnen_path,
                ped_given, ped_surname, ped_year,
                ged_id, ged_given, ged_surname, ged_year,
                match_method, total_score)
               VALUES (?, ?, ?, '', '', NULL, ?, ?, ?, NULL, 'exact', ?)""",
            (test_guid, match_guid, ahnen_path,
             ged_id, ged_given, ged_surname, total_score),
        )


def _insert_person(db, ged_id, given="", surname="", sosa_number=0):
    with db._cursor() as cur:
        cur.execute(
            """INSERT OR REPLACE INTO gedcom_persons
               (ged_id, given_name, surname, surname_norm,
                koelner_code, sosa_number)
               VALUES (?, ?, ?, ?, '', ?)""",
            (ged_id, given, surname, surname.lower(), sosa_number),
        )


# ── _parse_ancestor_name ──────────────────────────────────────────────────────

def test_parse_ancestor_name_firstname_last():
    given, sur = _parse_ancestor_name("Johann Kovermann")
    assert given == "Johann"
    assert sur == "Kovermann"


def test_parse_ancestor_name_comma_format():
    given, sur = _parse_ancestor_name("Kovermann, Johann")
    assert given == "Johann"
    assert sur == "Kovermann"


def test_parse_ancestor_name_single_word():
    given, sur = _parse_ancestor_name("Kovermann")
    assert sur == "Kovermann"


def test_parse_ancestor_name_multi_given():
    given, sur = _parse_ancestor_name("Johann Heinrich Kovermann")
    assert sur == "Kovermann"
    assert "Johann" in given


def test_parse_ancestor_name_strips_whitespace():
    given, sur = _parse_ancestor_name("  Anna  Müller  ")
    assert sur == "Müller"


# ── path_to_sosa ──────────────────────────────────────────────────────────────

def test_path_to_sosa_root():
    assert path_to_sosa("") == 1


def test_path_to_sosa_father():
    assert path_to_sosa("F") == 2


def test_path_to_sosa_mother():
    assert path_to_sosa("M") == 3


def test_path_to_sosa_paternal_grandfather():
    assert path_to_sosa("FF") == 4


def test_path_to_sosa_paternal_grandmother():
    assert path_to_sosa("FM") == 5


def test_path_to_sosa_maternal_grandfather():
    assert path_to_sosa("MF") == 6


def test_path_to_sosa_maternal_grandmother():
    assert path_to_sosa("MM") == 7


def test_path_to_sosa_gen4_ffff():
    assert path_to_sosa("FFF") == 8


def test_path_to_sosa_consistency():
    # Father's father's mother = Sosa 9
    assert path_to_sosa("FFM") == 9


def test_path_to_sosa_8gen_depth():
    # 8 steps deep: result must be between 2^8=256 and 2^9-1=511
    sosa = path_to_sosa("FFFFFFFF")
    assert 256 <= sosa <= 511


# ── infer_side_from_links ─────────────────────────────────────────────────────

def test_infer_side_paternal(db):
    _insert_person(db, "I001", "Hans", "Kovermann", sosa_number=4)
    _insert_link(db, "TEST", "MATCH1", "FF", "I001")
    amap = {"I001": "FF"}
    assert infer_side_from_links(db, "TEST", "MATCH1", amap) == "paternal"


def test_infer_side_maternal(db):
    _insert_person(db, "I002", "Maria", "Müller", sosa_number=5)
    _insert_link(db, "TEST", "MATCH2", "MF", "I002")
    amap = {"I002": "MF"}
    assert infer_side_from_links(db, "TEST", "MATCH2", amap) == "maternal"


def test_infer_side_both(db):
    _insert_person(db, "I003", "Johann", "Schmidt")
    _insert_person(db, "I004", "Anna", "Meyer")
    _insert_link(db, "TEST", "MATCH3", "FF", "I003")
    _insert_link(db, "TEST", "MATCH3", "MF", "I004")
    amap = {"I003": "FF", "I004": "MF"}
    assert infer_side_from_links(db, "TEST", "MATCH3", amap) == "both"


def test_infer_side_no_links_returns_empty(db):
    assert infer_side_from_links(db, "TEST", "NOMATCH", {}) == ""


def test_infer_side_ged_id_not_in_amap(db):
    # Link exists in DB but ged_id not in amap → side unknown
    _insert_link(db, "TEST", "MATCH4", "FF", "I_ORPHAN")
    assert infer_side_from_links(db, "TEST", "MATCH4", {}) == ""


def test_infer_side_deep_paternal(db):
    # Great-great-grandfather on paternal side: path FFFF
    _insert_person(db, "I005", "Rolf", "Brinkmann")
    _insert_link(db, "TEST", "MATCH5", "FFFF", "I005")
    amap = {"I005": "FFFF"}
    assert infer_side_from_links(db, "TEST", "MATCH5", amap) == "paternal"


# ── run_match_all ─────────────────────────────────────────────────────────────

def test_run_match_all_empty_returns_zero(db):
    total = run_match_all(db, "TEST_NO_DATA")
    assert total == 0
