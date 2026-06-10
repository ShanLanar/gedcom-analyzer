"""Flask-Viewer-Smoke-Tests gegen Fixture-DBs.

Prüft, dass die Root-Routen (/) beider Viewer HTTP 200 antworten.
Matricula-Viewer braucht eine Parish-DB — fehlt sie, antwortet er 503
(erwartet, kein Fehler im Test).
"""
import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def entity_db(tmp_path):
    """Leere ancestry_dna.db bis Schema v21."""
    db_path = tmp_path / "ancestry_dna.db"
    from ancestry.core.db.runner import run
    conn = sqlite3.connect(str(db_path))
    run(conn)
    conn.close()
    return db_path


def test_entity_browser_root_ok(entity_db):
    from ancestry.tools.entity_browser import app
    app.config["DB_PATH"] = str(entity_db)
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200


def test_entity_browser_candidates_route(entity_db):
    from ancestry.tools.entity_browser import app
    app.config["DB_PATH"] = str(entity_db)
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get("/candidates")
    assert resp.status_code == 200


def test_matricula_viewer_root_expected_response():
    """Ohne Parish-DB antwortet der Viewer 503 — das ist der definierte Pfad."""
    from ancestry.tools.matricula_viewer import app
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code in (200, 503)
