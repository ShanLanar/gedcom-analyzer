"""Testet, dass alle DB-Migrationen in Folge ohne Fehler durchlaufen.

Wichtig: source_webtrees-Tabelle muss nach jeder Migration erhalten bleiben.
"""
import re
import sqlite3
import pytest
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent / "ancestry" / "core" / "db" / "migrations"


def _get_migration_files():
    """Gibt alle .sql-Dateien in der richtigen Reihenfolge zurück."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return files


def _apply_migration(conn: sqlite3.Connection, sql_path: Path) -> None:
    """Wendet eine einzelne Migration an — ignoriert idempotente Fehler.

    Repliziert die Fehlertoleranz des production runners (runner.run()):
    - duplicate column name  → überspringen
    - already exists         → überspringen
    - no such table bei CREATE INDEX/VIEW → überspringen
    """
    sql = sql_path.read_text(encoding="utf-8")
    statements = [s.strip() for s in re.split(r";", sql) if s.strip()]
    for stmt in statements:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column name" in msg or "already exists" in msg:
                continue
            # Remove leading comment lines before checking statement type
            lines = stmt.splitlines()
            while lines and lines[0].lstrip().startswith("--"):
                lines.pop(0)
            stmt_upper = "\n".join(lines).lstrip().upper()
            if "no such table" in msg and stmt_upper.startswith(
                ("CREATE INDEX", "CREATE VIEW")
            ):
                continue
            raise
    conn.commit()


@pytest.fixture
def fresh_db(tmp_path):
    """Erzeugt eine frische In-Memory- (oder Temp-File-)SQLite-DB."""
    db_path = tmp_path / "test_migration.db"
    conn = sqlite3.connect(str(db_path))
    yield conn
    conn.close()


def test_migration_files_exist():
    """Mindestens eine Migration muss vorhanden sein."""
    files = _get_migration_files()
    assert len(files) > 0, "Keine Migrations-Dateien gefunden"


def test_all_migrations_apply_without_error(fresh_db):
    """Alle Migrationen können nacheinander auf eine leere DB angewendet werden."""
    files = _get_migration_files()
    for f in files:
        try:
            _apply_migration(fresh_db, f)
        except Exception as e:
            pytest.fail(f"Migration {f.name} fehlgeschlagen: {e}")


def test_source_webtrees_survives_all_migrations(fresh_db):
    """source_webtrees-Tabelle muss nach allen Migrationen noch existieren."""
    files = _get_migration_files()
    # Check if source_webtrees is ever created
    webtrees_created = any(
        "source_webtrees" in f.read_text(encoding="utf-8") for f in files
    )
    if not webtrees_created:
        pytest.skip("source_webtrees wird in keiner Migration angelegt")

    for f in files:
        _apply_migration(fresh_db, f)

    # Verify table still exists
    cursor = fresh_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='source_webtrees'"
    )
    assert cursor.fetchone() is not None, \
        "source_webtrees wurde durch eine Migration gelöscht!"


def test_no_drop_table_in_migrations():
    """Keine Migration darf DROP TABLE verwenden (additive-only policy)."""
    files = _get_migration_files()
    violations = []
    for f in files:
        content = f.read_text(encoding="utf-8").upper()
        if "DROP TABLE" in content and "IF EXISTS" not in content:
            violations.append(f.name)
        elif "DROP TABLE" in content:
            # DROP TABLE IF EXISTS is also not allowed per policy
            violations.append(f"{f.name} (DROP TABLE IF EXISTS)")
    if violations:
        pytest.fail(
            "Folgende Migrationen verwenden DROP TABLE (verboten):\n"
            + "\n".join(violations)
        )


def test_migration_ordering_is_numeric():
    """Migrationen müssen numerisch geordnet sein (0001, 0002, …)."""
    files = _get_migration_files()
    names = [f.stem for f in files]
    # Each name should start with digits
    for name in names:
        prefix = name.split("_")[0] if "_" in name else name
        assert prefix.isdigit(), f"Migration {name!r} beginnt nicht mit Ziffern"
