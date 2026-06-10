import sqlite3
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Quelldaten-Tabellen: niemals von Tools/Viewern schreibbar
_READONLY_TABLES = frozenset({
    "matches", "dna_kits", "shared_matches", "shared_matches_fetched",
    "match_ancestors", "match_birthplaces", "match_pedigree",
    "match_kit_membership", "persons", "match_person_links",
    "person_shared_dna", "mh_match_relationships", "gedmatch_matches",
    "gedmatch_bridge", "dna_segments", "user_notes",
    "source_webtrees", "source_anverwandte",
})

# Tabellen die im entity-layer beschreibbar sind
_ENTITY_WRITABLE = frozenset({
    "entities", "entity_assignments", "entity_candidates",
    "source_matrikula_entries", "name_index",
})


def _make_authorizer(writable: Optional[frozenset]):
    """Gibt eine set_authorizer-Funktion zurück. writable=None = alles erlaubt."""
    def authorizer(action, arg1, arg2, db_name, trigger_name):
        if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
            table = arg1
            if writable is not None and table not in writable:
                log.warning("Authorizer: DENY write auf %s", table)
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return authorizer


def _open(path: str, writable: Optional[frozenset] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    if writable is not None:
        conn.set_authorizer(_make_authorizer(writable))
    return conn


def open_ro(path: str) -> sqlite3.Connection:
    """Nur lesen — für Analyse, Statistik."""
    return _open(path, writable=frozenset())


def open_entity(path: str) -> sqlite3.Connection:
    """Schreibt: entities, entity_assignments, entity_candidates, source_matrikula_entries."""
    return _open(path, writable=_ENTITY_WRITABLE)


def open_source(path: str, source: str = "") -> sqlite3.Connection:
    """Schreibt: Quelltabellen der angegebenen Quelle (ancestry/mh/gedmatch/webtrees)."""
    # Für jetzt: gleicher Scope wie open_entity (in M5 weiter aufgeteilt)
    return _open(path, writable=_ENTITY_WRITABLE | _READONLY_TABLES)


def open_admin(path: str) -> sqlite3.Connection:
    """Vollen Schreibzugriff — nur für Migrationen und Importer."""
    return _open(path, writable=None)
