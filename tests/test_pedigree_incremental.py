"""Tests für den inkrementellen Pedigree-/Ancestors-Refresh (EPIC 2).

Prüft, dass get_matches_needing_pedigree / _needing_ancestors einen Match
- erneut einplant, wenn er nie geholt wurde,
- erneut einplant, wenn der letzte Abruf älter als max_age_days ist,
- überspringt, wenn der Abruf jung genug ist,
- bei force=True immer einplant,
und dass save_match_pedigree/_ancestors den Zeitstempel setzt.
"""
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from ancestry.core.database import Database
from ancestry.core.db.runner import TARGET_VERSION
from ancestry.models import DnaKit, DnaMatch

KIT = "KIT_INCR_001"


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)
    database.upsert_kit(DnaKit(guid=KIT, name="Kit", test_type="AncestryDNA"))
    yield database
    database.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _add_match(db, guid, *, fetched=0, fetched_at="", has_tree=1, cm=100.0):
    db.upsert_match(DnaMatch(
        match_guid=guid, test_guid=KIT, display_name=f"M-{guid}",
        shared_cm=cm, has_tree=bool(has_tree)))
    with db._cursor() as cur:
        cur.execute(
            "UPDATE matches SET has_tree=?, pedigree_fetched=?, pedigree_fetched_at=? "
            "WHERE match_guid=? AND test_guid=?",
            (has_tree, fetched, fetched_at, guid, KIT))


def _guids(rows):
    return {g for g, _ in rows}


def test_migration_adds_timestamp_columns(db):
    cols = {r[1] for r in db._cursor().__enter__().execute(
        "PRAGMA table_info(matches)").fetchall()}
    assert "pedigree_fetched_at" in cols
    assert "ancestors_fetched_at" in cols


def test_never_fetched_is_included(db):
    _add_match(db, "NEW", fetched=0, fetched_at="")
    res = db.get_matches_needing_pedigree(KIT)
    assert "NEW" in _guids(res)


def test_already_fetched_skipped_by_default(db):
    _add_match(db, "DONE", fetched=1, fetched_at=_iso(5))
    res = db.get_matches_needing_pedigree(KIT)
    assert "DONE" not in _guids(res)


def test_stale_included_with_max_age(db):
    _add_match(db, "STALE", fetched=1, fetched_at=_iso(45))
    _add_match(db, "FRESH", fetched=1, fetched_at=_iso(5))
    res = db.get_matches_needing_pedigree(KIT, max_age_days=30)
    g = _guids(res)
    assert "STALE" in g      # älter als 30 Tage → erneuern
    assert "FRESH" not in g  # jung genug → überspringen


def test_fetched_without_timestamp_is_stale(db):
    # Altbestand: pedigree_fetched=1, aber Zeitstempel leer → muss erneuert werden
    _add_match(db, "LEGACY", fetched=1, fetched_at="")
    res = db.get_matches_needing_pedigree(KIT, max_age_days=30)
    assert "LEGACY" in _guids(res)


def test_force_includes_everything(db):
    _add_match(db, "FRESH", fetched=1, fetched_at=_iso(1))
    res = db.get_matches_needing_pedigree(KIT, force=True)
    assert "FRESH" in _guids(res)


def test_save_pedigree_sets_timestamp(db):
    _add_match(db, "X", fetched=0, fetched_at="")
    db.save_match_pedigree(KIT, "X", [
        {"generation": 2, "ahnen_path": "MF", "given_name": "Anna",
         "surname": "Test", "birth_year": "1850"}])
    with db._cursor() as cur:
        row = cur.execute(
            "SELECT pedigree_fetched, pedigree_fetched_at FROM matches "
            "WHERE match_guid='X' AND test_guid=?", (KIT,)).fetchone()
    assert row["pedigree_fetched"] == 1
    assert row["pedigree_fetched_at"]  # nicht leer
    # nach frischem Abruf nicht mehr in der Default-Liste
    assert "X" not in _guids(db.get_matches_needing_pedigree(KIT))


def test_target_version_bumped():
    assert TARGET_VERSION >= 23
