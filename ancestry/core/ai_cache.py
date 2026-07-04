"""
Persistenter SQLite-Cache + Usage-Log für Claude-Aufrufe.

Ersetzt den früheren prozess-lokalen In-Memory-dict: Antworten überleben jetzt
Neustarts (Massenläufe wie Brick-Wall-Hypothesen oder Berufs-Normalisierung
profitieren über Sitzungen hinweg) und jeder API-Call wird mit Token-Verbrauch
protokolliert — Grundlage für Kostenkontrolle.

Der Schlüssel wird vom Aufrufer gebildet (sha256 aus model + max_tokens +
prompt), sodass verschiedene Modelle sich nicht gegenseitig verdrängen.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger(__name__)

_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def _db_path() -> str:
    env = os.environ.get("AI_CACHE_DB")
    if env:
        return env
    try:
        from ancestry.paths import CACHE_DIR
        return str(Path(CACHE_DIR) / "ai_cache.db")
    except Exception:
        return str(Path.home() / ".ahnen-ai-cache.db")


def _conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        path = _db_path()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        _CONN = sqlite3.connect(path, check_same_thread=False)
        _CONN.execute("""
            CREATE TABLE IF NOT EXISTS ai_cache (
                key         TEXT PRIMARY KEY,
                model       TEXT NOT NULL DEFAULT '',
                response    TEXT NOT NULL DEFAULT '',
                tokens_in   INTEGER NOT NULL DEFAULT 0,
                tokens_out  INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        _CONN.commit()
    return _CONN


def get(key: str) -> str | None:
    """Gecachte Antwort für den Schlüssel oder None."""
    try:
        with _LOCK:
            row = _conn().execute(
                "SELECT response FROM ai_cache WHERE key=?", (key,)
            ).fetchone()
        return row[0] if row else None
    except Exception as e:
        log.debug("ai_cache.get: %s", e)
        return None


def put(key: str, model: str, response: str,
        tokens_in: int = 0, tokens_out: int = 0) -> None:
    """Antwort + Token-Verbrauch persistieren (idempotent je Schlüssel)."""
    try:
        with _LOCK:
            c = _conn()
            c.execute(
                "INSERT OR REPLACE INTO ai_cache "
                "(key, model, response, tokens_in, tokens_out) "
                "VALUES (?,?,?,?,?)",
                (key, model, response, int(tokens_in), int(tokens_out)),
            )
            c.commit()
    except Exception as e:
        log.debug("ai_cache.put: %s", e)


def usage_summary() -> dict:
    """Aggregierter Token-Verbrauch über alle gecachten Aufrufe."""
    try:
        with _LOCK:
            row = _conn().execute(
                "SELECT COUNT(*), COALESCE(SUM(tokens_in),0), "
                "COALESCE(SUM(tokens_out),0) FROM ai_cache"
            ).fetchone()
        return {"calls": row[0], "tokens_in": row[1], "tokens_out": row[2]}
    except Exception as e:
        log.debug("ai_cache.usage_summary: %s", e)
        return {"calls": 0, "tokens_in": 0, "tokens_out": 0}


def clear() -> None:
    """Cache leeren (v. a. für Tests)."""
    try:
        with _LOCK:
            c = _conn()
            c.execute("DELETE FROM ai_cache")
            c.commit()
    except Exception as e:
        log.debug("ai_cache.clear: %s", e)


def _reset_for_test() -> None:
    """Schließt die Verbindung, damit ein neuer AI_CACHE_DB-Pfad greift."""
    global _CONN
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
            _CONN = None
