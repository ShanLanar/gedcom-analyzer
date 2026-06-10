"""Führt nummerierte SQL-Migrations-Dateien gegen eine SQLite-Verbindung aus."""
import re
import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
TARGET_VERSION = 22


def run(conn: sqlite3.Connection) -> int:
    """Wendet alle fehlenden Migrationen an. Gibt neue Schema-Version zurück.

    Alle Schritte laufen in einer einzigen Transaktion — identisches Verhalten
    zum früheren _init_db (ein Commit am Ende statt N Commits je Datei).
    """
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    conn.commit()
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    current = row[0] if row else 0
    if current >= TARGET_VERSION:
        return current

    # Alles in einer Transaktion
    conn.execute("BEGIN")
    for n in range(1, TARGET_VERSION + 1):
        if n <= current:
            continue
        sql_path = MIGRATIONS_DIR / f"{n:04d}.sql"
        if not sql_path.exists():
            continue   # Lücke (z. B. 0005) – bewusst
        log.debug("Migrations-Schritt %04d: %s", n, sql_path.name)
        sql = sql_path.read_text(encoding="utf-8")
        statements = [s.strip() for s in re.split(r';', sql) if s.strip()]
        for stmt in statements:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "duplicate column name" in msg or "already exists" in msg:
                    log.debug("Migration: übersprungen (idempotent): %s", e)
                    continue
                raise

    if row:
        conn.execute("UPDATE schema_version SET version=?", (TARGET_VERSION,))
    else:
        conn.execute("INSERT INTO schema_version VALUES(?)", (TARGET_VERSION,))
    conn.commit()
    log.debug("DB auf Schema v%d gebracht", TARGET_VERSION)
    return TARGET_VERSION
