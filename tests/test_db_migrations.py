import sqlite3
import pytest
from ancestry.core.db.runner import run, TARGET_VERSION


def test_fresh_install_reaches_v21(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    version = run(conn)
    conn.close()
    assert version == TARGET_VERSION


def test_idempotent(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    run(conn)
    version = run(conn)  # zweites Mal
    conn.close()
    assert version == TARGET_VERSION


def test_all_entity_tables_exist(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    run(conn)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for t in ("entities", "entity_assignments", "entity_candidates",
              "source_webtrees", "source_matrikula_entries"):
        assert t in tables, f"Tabelle fehlt: {t}"
    conn.close()
