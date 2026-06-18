"""Testet jede DB-Migration EINZELN (v_n→v_{n+1}), nicht nur End-to-End.

Bisher prüfte test_db_migrations.py nur den Gesamtlauf v1→vN. Hier wird jede
Migrationsdatei für sich angewendet — so fällt eine kaputte/fehlerhafte
Einzelmigration sofort auf und nicht erst als undurchsichtiger Sammelfehler.
"""
import re
import sqlite3

import pytest

from ancestry.core.db.runner import MIGRATIONS_DIR, TARGET_VERSION, run

# Tatsächlich vorhandene Migrationsnummern (Lücken wie 0005 sind bewusst erlaubt)
EXISTING = sorted(int(p.stem) for p in MIGRATIONS_DIR.glob("*.sql"))


def _apply_file(conn: sqlite3.Connection, n: int) -> None:
    """Wendet eine einzelne Migrationsdatei an – identisch zur Runner-Logik
    (Statement-Split, idempotentes Überspringen von 'duplicate column'/'exists')."""
    sql_path = MIGRATIONS_DIR / f"{n:04d}.sql"
    sql = sql_path.read_text(encoding="utf-8")
    for stmt in (s.strip() for s in re.split(r";", sql) if s.strip()):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column name" in msg or "already exists" in msg:
                continue
            raise


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _schema(conn):
    # schema_version wird nur vom Runner (run()) angelegt, nicht von den
    # Migrationsdateien selbst → für den Vergleich ausklammern.
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','index','view') "
        "AND name NOT LIKE 'sqlite_%'").fetchall()} - {"schema_version"}


@pytest.mark.parametrize("n", EXISTING)
def test_single_migration_applies(n):
    """Migration n lässt sich anwenden, nachdem 1..n-1 angewendet wurden."""
    conn = sqlite3.connect(":memory:")
    for prev in EXISTING:
        if prev >= n:
            break
        _apply_file(conn, prev)
    _apply_file(conn, n)   # darf nicht werfen
    conn.close()


@pytest.mark.parametrize("n", EXISTING)
def test_single_migration_idempotent(n):
    """Migration n zweimal hintereinander → kein Fehler (idempotent)."""
    conn = sqlite3.connect(":memory:")
    for prev in EXISTING:
        if prev > n:
            break
        _apply_file(conn, prev)
    _apply_file(conn, n)   # zweite Anwendung
    conn.close()


def test_stepwise_matches_bulk():
    """Schema nach Schritt-für-Schritt == Schema nach Gesamtlauf run()."""
    step = sqlite3.connect(":memory:")
    for n in EXISTING:
        _apply_file(step, n)
    step_schema = _schema(step)
    step.close()

    bulk = sqlite3.connect(":memory:")
    assert run(bulk) == TARGET_VERSION
    bulk_schema = _schema(bulk)
    bulk.close()

    assert step_schema == bulk_schema


def test_known_columns_added_in_expected_migration():
    """Stichprobe: pedigree_fetched (0008) und der neue Zeitstempel (0023)."""
    conn = sqlite3.connect(":memory:")
    for n in EXISTING:
        if n > 8:
            break
        _apply_file(conn, n)
    assert "pedigree_fetched" in _columns(conn, "matches")
    assert "pedigree_fetched_at" not in _columns(conn, "matches")

    for n in EXISTING:
        if n <= 8:
            continue
        if n > 23:
            break
        _apply_file(conn, n)
    assert "pedigree_fetched_at" in _columns(conn, "matches")
    conn.close()


def test_all_expected_migrations_present():
    """Keine erwartete Migrationsdatei fehlt bis TARGET_VERSION (außer Lücken)."""
    assert EXISTING, "keine Migrationsdateien gefunden"
    assert max(EXISTING) == TARGET_VERSION
