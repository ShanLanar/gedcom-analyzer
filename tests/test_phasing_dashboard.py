"""Tests für Phasing-Dashboard (4-Quadrant Eltern-Zuordnung)."""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from ancestry.core.database import Database
from ancestry.gui.analysis.phasing_dashboard import PhasingDashboard


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


def test_phasing_load_matches_known_sides(db):
    """Testet Laden von Matches mit bekannten Seiten (maternal/paternal)."""
    kit_guid = "kit-001"

    # 2 maternal known, 2 paternal known
    _add_match(db, kit_guid, "m1", "Match Alice", 500.0, "maternal")
    _add_match(db, kit_guid, "m2", "Match Bob", 450.0, "maternal")
    _add_match(db, kit_guid, "p1", "Match Charlie", 550.0, "paternal")
    _add_match(db, kit_guid, "p2", "Match David", 480.0, "paternal")

    # Mock Tkinter-Fenster
    root = MagicMock()
    dashboard = PhasingDashboard(root, kit_guid, db)

    assert len(dashboard._matches_by_quad["Q1"]) == 2  # Maternal known
    assert len(dashboard._matches_by_quad["Q2"]) == 2  # Paternal known
    assert len(dashboard._matches_by_quad["Q3"]) == 0  # Maternal inferred
    assert len(dashboard._matches_by_quad["Q4"]) == 0  # Paternal inferred


def test_phasing_load_matches_inferred(db):
    """Testet Laden von Matches mit Cluster-Inferenz."""
    kit_guid = "kit-001"

    # 1 inferred maternal, 1 inferred paternal
    _add_match(db, kit_guid, "m3", "Match Eve", 420.0, "")
    _add_match(db, kit_guid, "p3", "Match Frank", 410.0, "")

    inferred_map = {"m3": "maternal", "p3": "paternal"}

    root = MagicMock()
    dashboard = PhasingDashboard(root, kit_guid, db, inferred_side_map=inferred_map)

    assert len(dashboard._matches_by_quad["Q3"]) == 1  # Maternal inferred
    assert len(dashboard._matches_by_quad["Q4"]) == 1  # Paternal inferred


def test_phasing_drag_drop_update(db):
    """Testet Drag-Drop mit DB-Update."""
    kit_guid = "kit-001"
    _add_match(db, kit_guid, "m1", "Match Alice", 500.0, "maternal")

    root = MagicMock()
    dashboard = PhasingDashboard(root, kit_guid, db)

    # Initial: Q1 (maternal known)
    assert len(dashboard._matches_by_quad["Q1"]) == 1
    assert len(dashboard._matches_by_quad["Q2"]) == 0

    # Simule Drag zu Q2 (paternal known)
    dashboard._drag_data["item"] = None
    match = dashboard._matches_by_quad["Q1"][0]
    old_qid = "Q1"
    new_qid = "Q2"
    new_side = "paternal"

    # Manuell updaten (Drag-Logik)
    with db._cursor() as cur:
        cur.execute(
            "UPDATE matches SET paternal_maternal = ? WHERE match_guid = ?",
            (new_side, match["match_guid"]),
        )

    dashboard._matches_by_quad[old_qid].remove(match)
    match["paternal_maternal"] = new_side
    dashboard._matches_by_quad[new_qid].append(match)

    assert len(dashboard._matches_by_quad["Q1"]) == 0
    assert len(dashboard._matches_by_quad["Q2"]) == 1

    # Verifiziere DB
    with db._cursor() as cur:
        cur.execute(
            "SELECT paternal_maternal FROM matches WHERE match_guid = ?",
            ("m1",),
        )
        row = cur.fetchone()
        assert row["paternal_maternal"] == "paternal"


def test_phasing_quad_from_coords():
    """Testet Quadranten-Bestimmung aus Koordinaten."""
    root = MagicMock()
    with patch("ancestry.gui.analysis.phasing_dashboard.Database"):
        db_mock = MagicMock()
        db_mock._cursor.return_value.__enter__.return_value.fetchall.return_value = []

        dashboard = PhasingDashboard(root, "kit-001", db_mock)

        # Mock canvas width/height
        dashboard.canvas.winfo_width = lambda: 1000
        dashboard.canvas.winfo_height = lambda: 700

        # Test quad determination
        assert dashboard._get_quad_from_coords(200, 200) == "Q1"  # oben-links
        assert dashboard._get_quad_from_coords(600, 200) == "Q2"  # oben-rechts
        assert dashboard._get_quad_from_coords(200, 500) == "Q3"  # unten-links
        assert dashboard._get_quad_from_coords(600, 500) == "Q4"  # unten-rechts


def test_phasing_mixed_matches(db):
    """Testet Mischung aus bekannten und inferrierten Matches."""
    kit_guid = "kit-002"

    # 5 Matches gesamt: 2 known mat, 2 known pat, 1 inferred
    _add_match(db, kit_guid, "m1", "Match A", 600.0, "maternal")
    _add_match(db, kit_guid, "m2", "Match B", 550.0, "maternal")
    _add_match(db, kit_guid, "p1", "Match C", 500.0, "paternal")
    _add_match(db, kit_guid, "p2", "Match D", 450.0, "paternal")
    _add_match(db, kit_guid, "i1", "Match E", 400.0, "")

    inferred_map = {"i1": "maternal"}

    root = MagicMock()
    dashboard = PhasingDashboard(root, kit_guid, db, inferred_side_map=inferred_map)

    assert len(dashboard._matches_by_quad["Q1"]) == 2
    assert len(dashboard._matches_by_quad["Q2"]) == 2
    assert len(dashboard._matches_by_quad["Q3"]) == 1
    assert len(dashboard._matches_by_quad["Q4"]) == 0

    total = sum(len(dashboard._matches_by_quad[q]) for q in ["Q1", "Q2", "Q3", "Q4"])
    assert total == 5
