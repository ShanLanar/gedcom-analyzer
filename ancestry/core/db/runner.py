"""Führt nummerierte SQL-Migrations-Dateien gegen eine SQLite-Verbindung aus."""
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
TARGET_VERSION = 42


def _split_statements(sql: str) -> list[str]:
    """Zerlegt eine SQL-Datei in Einzel-Statements — komment- und string-bewusst.

    Splittet nur an top-level ';', nicht an ';' innerhalb von '…'-Strings,
    ``--``-Zeilen- oder ``/* */``-Blockkommentaren (das naive re.split(';')
    zerbrach genau daran, z. B. bei Semikolon in einem Kommentar). Hinweis:
    CREATE TRIGGER mit internem ';' wird NICHT unterstützt — bislang nutzt keine
    Migration Trigger; falls doch, muss dieser Splitter erweitert werden."""
    stmts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    in_str = False
    while i < n:
        c = sql[i]
        if in_str:
            buf.append(c)
            if c == "'":
                if i + 1 < n and sql[i + 1] == "'":   # '' = Escape
                    buf.append(sql[i + 1]); i += 2; continue
                in_str = False
            i += 1; continue
        if c == "'":
            in_str = True; buf.append(c); i += 1; continue
        if c == "-" and i + 1 < n and sql[i + 1] == "-":   # Zeilenkommentar
            while i < n and sql[i] != "\n":
                buf.append(sql[i]); i += 1
            continue
        if c == "/" and i + 1 < n and sql[i + 1] == "*":   # Blockkommentar
            buf.append("/*"); i += 2
            while i < n and not (sql[i] == "*" and i + 1 < n and sql[i + 1] == "/"):
                buf.append(sql[i]); i += 1
            if i < n:
                buf.append("*/"); i += 2
            continue
        if c == ";":
            s = "".join(buf).strip()
            if s:
                stmts.append(s)
            buf = []; i += 1; continue
        buf.append(c); i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def _strip_leading_comments(stmt: str) -> str:
    """Entfernt führende ``--``-Kommentarzeilen, damit die Statement-Erkennung
    (CREATE INDEX/VIEW) auch greift, wenn ein Kommentar vorangestellt ist."""
    lines = stmt.splitlines()
    while lines and lines[0].lstrip().startswith("--"):
        lines.pop(0)
    return "\n".join(lines).lstrip()


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
        for stmt in _split_statements(sql):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "duplicate column name" in msg or "already exists" in msg:
                    log.debug("Migration: übersprungen (idempotent): %s", e)
                    continue
                # Index/View auf noch nicht vorhandene Tabelle überspringen
                # (z. B. gedcom_persons vor erstem GEDCOM-Import). Führende
                # SQL-Kommentare zuerst entfernen, sonst greift die Erkennung nicht.
                stmt_upper = _strip_leading_comments(stmt).upper()
                if "no such table" in msg and stmt_upper.startswith(("CREATE INDEX", "CREATE VIEW")):
                    log.debug("Migration: Index/View übersprungen (Tabelle fehlt): %s", e)
                    continue
                log.warning("Migration %s: %s", sql_path.name, e)
                raise   # nicht-idempotenter Fehler → Lauf abbrechen
        log.info("Migration %s angewendet", sql_path.name)

    if row:
        conn.execute("UPDATE schema_version SET version=?", (TARGET_VERSION,))
    else:
        conn.execute("INSERT INTO schema_version VALUES(?)", (TARGET_VERSION,))
    conn.commit()
    log.debug("DB auf Schema v%d gebracht", TARGET_VERSION)
    return TARGET_VERSION
