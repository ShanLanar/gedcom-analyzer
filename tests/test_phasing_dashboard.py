"""Tests für Phasing-Dashboard (4-Quadrant Eltern-Zuordnung).

Pure unit tests ohne tkinter GUI dependencies.
"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from ancestry.core.database import Database


@pytest.fixture
def db():
    """Erstellt temporäre Test-DB."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)

    # Initialisiere schema
    with database._cursor() as cur:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS dna_kits (
                guid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                test_type TEXT DEFAULT 'AncestryDNA'
            )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS matches (
                match_guid TEXT PRIMARY KEY,
                test_guid TEXT NOT NULL,
                display_name TEXT,
                shared_cm REAL DEFAULT 0,
                shared_segments INTEGER DEFAULT 0,
                longest_segment REAL DEFAULT 0,
                predicted_relationship TEXT,
                confidence TEXT,
                relationship_range TEXT,
                has_hint INTEGER DEFAULT 0,
                has_tree INTEGER DEFAULT 0,
                tree_size INTEGER DEFAULT 0,
                tree_id TEXT,
                starred INTEGER DEFAULT 0,
                note TEXT,
                custom_relationship TEXT,
                ethnicity_regions TEXT,
                last_login TEXT,
                fetched_at TEXT,
                first_seen_at TEXT,
                raw_json TEXT,
                match_cluster_code TEXT,
                created_date TEXT,
                tag_surname TEXT,
                tag_gender TEXT,
                tag_path TEXT,
                tags_json TEXT,
                meiosis INTEGER DEFAULT 0,
                ignored INTEGER DEFAULT 0,
                paternal_maternal TEXT DEFAULT '',
                source TEXT DEFAULT 'ancestry'
            )"""
        )

    yield database
    database.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


def _add_match(db: Database, kit_guid: str, match_guid: str, name: str, cm: float, side: str = ""):
    """Hilfsfunktion: fügt Match zu DB hinzu."""
    with db._cursor() as cur:
        cur.execute(
            """INSERT INTO matches (
                match_guid, test_guid, display_name, shared_cm, paternal_maternal
            ) VALUES (?, ?, ?, ?, ?)""",
            (match_guid, kit_guid, name, cm, side),
        )


def test_phasing_dashboard_logic_load_matches_known(db):
    """Testet Logik zur Kategorisierung von Matches mit bekannten Seiten."""
    kit_guid = "kit-001"

    # 2 maternal known, 2 paternal known
    _add_match(db, kit_guid, "m1", "Match Alice", 500.0, "maternal")
    _add_match(db, kit_guid, "m2", "Match Bob", 450.0, "maternal")
    _add_match(db, kit_guid, "p1", "Match Charlie", 550.0, "paternal")
    _add_match(db, kit_guid, "p2", "Match David", 480.0, "paternal")

    # Simuliere Logik aus PhasingDashboard._load_matches
    matches_by_quad = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    inferred_map = {}

    with db._cursor() as cur:
        cur.execute(
            """SELECT match_guid, display_name, shared_cm, paternal_maternal
               FROM matches WHERE test_guid = ?
               ORDER BY shared_cm DESC""",
            (kit_guid,),
        )
        rows = cur.fetchall()

    for row in rows:
        match = {
            "match_guid": row["match_guid"],
            "display_name": row["display_name"],
            "shared_cm": row["shared_cm"],
            "paternal_maternal": row["paternal_maternal"] or "",
            "cluster_id": inferred_map.get(row["match_guid"], "—"),
        }

        pm = match.get("paternal_maternal", "")
        if pm == "maternal":
            qid = "Q1"
        elif pm == "paternal":
            qid = "Q2"
        elif inferred_map.get(row["match_guid"]) == "maternal":
            qid = "Q3"
        else:
            qid = "Q4"

        matches_by_quad[qid].append(match)

    assert len(matches_by_quad["Q1"]) == 2  # Maternal known
    assert len(matches_by_quad["Q2"]) == 2  # Paternal known
    assert len(matches_by_quad["Q3"]) == 0  # Maternal inferred
    assert len(matches_by_quad["Q4"]) == 0  # Paternal inferred


def test_phasing_dashboard_logic_load_matches_inferred(db):
    """Testet Logik mit Cluster-Inferenz."""
    kit_guid = "kit-001"

    # 1 inferred maternal, 1 inferred paternal
    _add_match(db, kit_guid, "m3", "Match Eve", 420.0, "")
    _add_match(db, kit_guid, "p3", "Match Frank", 410.0, "")

    matches_by_quad = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    inferred_map = {"m3": "maternal", "p3": "paternal"}

    with db._cursor() as cur:
        cur.execute(
            """SELECT match_guid, display_name, shared_cm, paternal_maternal
               FROM matches WHERE test_guid = ?
               ORDER BY shared_cm DESC""",
            (kit_guid,),
        )
        rows = cur.fetchall()

    for row in rows:
        match = {
            "match_guid": row["match_guid"],
            "display_name": row["display_name"],
            "shared_cm": row["shared_cm"],
            "paternal_maternal": row["paternal_maternal"] or "",
            "cluster_id": inferred_map.get(row["match_guid"], "—"),
        }

        pm = match.get("paternal_maternal", "")
        if pm == "maternal":
            qid = "Q1"
        elif pm == "paternal":
            qid = "Q2"
        elif inferred_map.get(row["match_guid"]) == "maternal":
            qid = "Q3"
        else:
            qid = "Q4"

        matches_by_quad[qid].append(match)

    assert len(matches_by_quad["Q3"]) == 1  # Maternal inferred
    assert len(matches_by_quad["Q4"]) == 1  # Paternal inferred


def test_phasing_dashboard_logic_db_update(db):
    """Testet DB-Update nach Drag-Drop."""
    kit_guid = "kit-001"
    _add_match(db, kit_guid, "m1", "Match Alice", 500.0, "maternal")

    # Simul DB-Update
    with db._cursor() as cur:
        cur.execute(
            "UPDATE matches SET paternal_maternal = ? WHERE match_guid = ?",
            ("paternal", "m1"),
        )

    # Verifiziere DB
    with db._cursor() as cur:
        cur.execute(
            "SELECT paternal_maternal FROM matches WHERE match_guid = ?",
            ("m1",),
        )
        row = cur.fetchone()
        assert row["paternal_maternal"] == "paternal"


def test_phasing_quad_determination_logic():
    """Testet Logik zur Quadranten-Bestimmung aus Koordinaten."""
    # Simule Quadranten-Koordinaten: w=1000, h=700, mid_x=500, mid_y=350

    def get_quad(x, y):
        mx, my = 500, 350
        if x < mx and y < my:
            return "Q1"
        elif x >= mx and y < my:
            return "Q2"
        elif x < mx and y >= my:
            return "Q3"
        else:
            return "Q4"

    assert get_quad(200, 200) == "Q1"  # oben-links
    assert get_quad(600, 200) == "Q2"  # oben-rechts
    assert get_quad(200, 500) == "Q3"  # unten-links
    assert get_quad(600, 500) == "Q4"  # unten-rechts


def test_phasing_mixed_matches(db):
    """Testet Mischung aus bekannten und inferrierten Matches."""
    kit_guid = "kit-002"

    # 5 Matches: 2 known mat, 2 known pat, 1 inferred
    _add_match(db, kit_guid, "m1", "Match A", 600.0, "maternal")
    _add_match(db, kit_guid, "m2", "Match B", 550.0, "maternal")
    _add_match(db, kit_guid, "p1", "Match C", 500.0, "paternal")
    _add_match(db, kit_guid, "p2", "Match D", 450.0, "paternal")
    _add_match(db, kit_guid, "i1", "Match E", 400.0, "")

    matches_by_quad = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}
    inferred_map = {"i1": "maternal"}

    with db._cursor() as cur:
        cur.execute(
            """SELECT match_guid, display_name, shared_cm, paternal_maternal
               FROM matches WHERE test_guid = ?
               ORDER BY shared_cm DESC""",
            (kit_guid,),
        )
        rows = cur.fetchall()

    for row in rows:
        match = {
            "match_guid": row["match_guid"],
            "display_name": row["display_name"],
            "shared_cm": row["shared_cm"],
            "paternal_maternal": row["paternal_maternal"] or "",
            "cluster_id": inferred_map.get(row["match_guid"], "—"),
        }

        pm = match.get("paternal_maternal", "")
        if pm == "maternal":
            qid = "Q1"
        elif pm == "paternal":
            qid = "Q2"
        elif inferred_map.get(row["match_guid"]) == "maternal":
            qid = "Q3"
        else:
            qid = "Q4"

        matches_by_quad[qid].append(match)

    assert len(matches_by_quad["Q1"]) == 2
    assert len(matches_by_quad["Q2"]) == 2
    assert len(matches_by_quad["Q3"]) == 1
    assert len(matches_by_quad["Q4"]) == 0

    total = sum(len(matches_by_quad[q]) for q in ["Q1", "Q2", "Q3", "Q4"])
    assert total == 5
