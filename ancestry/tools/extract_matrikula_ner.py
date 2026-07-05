#!/usr/bin/env python3
"""
Matricula NER – Personen-Extraktion aus raw_json

Liest alle source_matrikula_entries und extrahiert benannte Personen
(Täuflinge, Väter, Mütter, Paten, Bräutigame, Bräute, Zeugen, Verstorbene)
aus dem raw_json-Feld in die Tabelle matrikula_ner.

Nutzt Kölner Phonetik für phonetisch-unscharfe Namenssuche.

Anwendung:
    python extract_matrikula_ner.py                      # alle Einträge
    python extract_matrikula_ner.py --parish ostercappeln
    python extract_matrikula_ner.py --book-type Taufe
    python extract_matrikula_ner.py --force              # überschreibt vorhandene NER
    python extract_matrikula_ner.py --stats              # nur Statistik, kein Schreiben
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from tasks.names import koelner_phonetik as _kp
except ImportError:
    _kp = None  # type: ignore[assignment]

try:
    from ancestry.paths import DB_PATH
except ImportError:
    DB_PATH = ROOT / "data" / "ancestry_dna.db"

# Geburtsname-Muster: "geb. Müller", "geboren Müller", "née Müller"
_GEB_RE = re.compile(r'\b(?:geb\.?|geboren|née?)\s+([A-ZÄÖÜ][a-zäöüß\-]+)', re.I)
# Klammernotation: "Anna Maria (Müller)"
_PAREN_RE = re.compile(r'\(([A-ZÄÖÜ][a-zäöüß\-]+)\)')


def _split_geburtsname(name: str) -> tuple[str, str]:
    """Gibt (bereinigter_name, geburtsname) zurück."""
    m = _GEB_RE.search(name)
    if m:
        return _GEB_RE.sub('', name).strip().rstrip(',').strip(), m.group(1)
    m = _PAREN_RE.search(name)
    if m:
        return _PAREN_RE.sub('', name).strip(), m.group(1)
    return name, ''


def _phonetik(name: str) -> str:
    if not name or _kp is None:
        return ''
    parts = name.strip().split()
    return _kp(parts[-1]) if parts else ''


def _persons_from_entry(
    entry_id: int,
    book_id: str,
    event_year: int | None,
    entry_type: str,
    raw_json: str,
) -> list[dict]:
    """Extrahiert alle benannten Personen aus einem Kirchenbuch-Eintrag."""
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    persons: list[dict] = []

    def _add(name_raw: str, rolle: str, ort: str = '', beruf: str = '') -> None:
        name_raw = (name_raw or '').strip()
        if not name_raw:
            return
        name_clean, geb = _split_geburtsname(name_raw)
        persons.append({
            'entry_id':   entry_id,
            'book_id':    book_id,
            'event_year': event_year,
            'name_raw':   name_raw,
            'name_norm':  name_clean.lower().strip(),
            'koeln_code': _phonetik(name_clean),
            'rolle':      rolle,
            'beruf':      beruf,
            'ort':        (ort or '').strip(),
            'geburtsname': geb,
        })

    def _add_list(items, rolle: str) -> None:
        for item in (items or []):
            if isinstance(item, str):
                _add(item, rolle)
            elif isinstance(item, dict):
                _add(item.get('name', ''), rolle, ort=item.get('ort', ''))

    if entry_type == 'Taufe':
        ort = data.get('ort', '')
        _add(data.get('kind_name', ''),   'kind',   ort=ort)
        _add(data.get('vater_name', ''),  'vater',  ort=ort)
        _add(data.get('mutter_name', ''), 'mutter', ort=ort)
        _add_list(data.get('taufpaten', []), 'pate')

    elif entry_type == 'Heirat':
        _add(data.get('braeutigam_name', ''),  'braeutigam',      ort=data.get('braeutigam_ort', ''))
        _add(data.get('braeutigam_vater', ''), 'braeutigam_vater')
        _add(data.get('braut_name', ''),       'braut',           ort=data.get('braut_ort', ''))
        _add(data.get('braut_vater', ''),      'braut_vater')
        _add_list(data.get('zeugen', []), 'zeuge')

    elif entry_type == 'Tod':
        ort = data.get('ort', '')
        _add(data.get('name', ''),   'verstorbener', ort=ort)
        _add(data.get('eltern', ''), 'elternteil',   ort=ort)
        _add_list(data.get('zeugen', []), 'zeuge')

    return persons


def _ensure_table(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS matrikula_ner (
        ner_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id    INTEGER NOT NULL,
        book_id     TEXT NOT NULL,
        event_year  INTEGER,
        name_raw    TEXT NOT NULL,
        name_norm   TEXT DEFAULT '',
        koeln_code  TEXT DEFAULT '',
        rolle       TEXT NOT NULL,
        beruf       TEXT DEFAULT '',
        ort         TEXT DEFAULT '',
        geburtsname TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_mner_entry  ON matrikula_ner(entry_id);
    CREATE INDEX IF NOT EXISTS idx_mner_koeln  ON matrikula_ner(koeln_code);
    CREATE INDEX IF NOT EXISTS idx_mner_rolle  ON matrikula_ner(rolle);
    CREATE INDEX IF NOT EXISTS idx_mner_year   ON matrikula_ner(event_year);
    CREATE INDEX IF NOT EXISTS idx_mner_book   ON matrikula_ner(book_id);
    """)
    db.commit()
    _ensure_fts(db)


def _ensure_fts(db: sqlite3.Connection) -> None:
    """FTS5-Volltextindex über Namen/Orte/Berufe (external content).

    Trigger halten den Index bei INSERT/UPDATE/DELETE synchron. Fehlt FTS5
    im SQLite-Build, wird der Index still übersprungen — die Suche fällt
    dann auf LIKE zurück."""
    try:
        db.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS matrikula_ner_fts USING fts5(
            name_raw, name_norm, ort, beruf,
            content='matrikula_ner', content_rowid='ner_id'
        );
        CREATE TRIGGER IF NOT EXISTS mner_fts_ai AFTER INSERT ON matrikula_ner BEGIN
            INSERT INTO matrikula_ner_fts(rowid, name_raw, name_norm, ort, beruf)
            VALUES (new.ner_id, new.name_raw, new.name_norm, new.ort, new.beruf);
        END;
        CREATE TRIGGER IF NOT EXISTS mner_fts_ad AFTER DELETE ON matrikula_ner BEGIN
            INSERT INTO matrikula_ner_fts(matrikula_ner_fts, rowid, name_raw, name_norm, ort, beruf)
            VALUES ('delete', old.ner_id, old.name_raw, old.name_norm, old.ort, old.beruf);
        END;
        CREATE TRIGGER IF NOT EXISTS mner_fts_au AFTER UPDATE ON matrikula_ner BEGIN
            INSERT INTO matrikula_ner_fts(matrikula_ner_fts, rowid, name_raw, name_norm, ort, beruf)
            VALUES ('delete', old.ner_id, old.name_raw, old.name_norm, old.ort, old.beruf);
            INSERT INTO matrikula_ner_fts(rowid, name_raw, name_norm, ort, beruf)
            VALUES (new.ner_id, new.name_raw, new.name_norm, new.ort, new.beruf);
        END;
        """)
        # Bestandsdaten nachindizieren, falls der Index neu/leer ist
        n_src = db.execute("SELECT COUNT(*) FROM matrikula_ner").fetchone()[0]
        n_fts = db.execute("SELECT COUNT(*) FROM matrikula_ner_fts").fetchone()[0]
        if n_src > 0 and n_fts == 0:
            db.execute("INSERT INTO matrikula_ner_fts(matrikula_ner_fts) VALUES('rebuild')")
        db.commit()
    except sqlite3.OperationalError as e:
        print(f"⚠ FTS5 nicht verfügbar, Volltextindex übersprungen: {e}")


def print_stats(db: sqlite3.Connection) -> None:
    total = db.execute("SELECT COUNT(*) FROM matrikula_ner").fetchone()[0]
    print(f"\nmatrikula_ner: {total} Einträge gesamt")
    if total == 0:
        return
    print("\nNach Rolle:")
    for row in db.execute(
        "SELECT rolle, COUNT(*) AS n FROM matrikula_ner GROUP BY rolle ORDER BY n DESC"
    ).fetchall():
        print(f"  {row[0]:<20} {row[1]:>6}")
    print("\nNach Buchtyp (via entry_id):")
    for row in db.execute("""
        SELECT e.entry_type, COUNT(*) AS n
        FROM matrikula_ner n
        JOIN source_matrikula_entries e ON e.entry_id = n.entry_id
        GROUP BY e.entry_type ORDER BY n DESC
    """).fetchall():
        print(f"  {row[0]:<20} {row[1]:>6}")
    earliest = db.execute("SELECT MIN(event_year) FROM matrikula_ner WHERE event_year > 0").fetchone()[0]
    latest   = db.execute("SELECT MAX(event_year) FROM matrikula_ner WHERE event_year > 0").fetchone()[0]
    print(f"\nZeitraum: {earliest} – {latest}")


def extract_ner(
    parish_filter: str | None = None,
    book_type_filter: str | None = None,
    force: bool = False,
    stats_only: bool = False,
) -> dict:
    if not DB_PATH.exists():
        print(f"⚠ Haupt-DB nicht gefunden: {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(str(DB_PATH), timeout=30.0)  # 30s busy-timeout gg. Locks
    db.row_factory = sqlite3.Row
    _ensure_table(db)

    if stats_only:
        print_stats(db)
        db.close()
        return {}

    # Bereits verarbeitete entry_ids überspringen (außer bei --force)
    done_ids: set[int] = set()
    if not force:
        done_ids = {
            row[0]
            for row in db.execute("SELECT DISTINCT entry_id FROM matrikula_ner").fetchall()
        }

    # Einträge filtern
    conditions = ["raw_json != ''"]
    params: list = []
    if parish_filter:
        conditions.append("book_id LIKE ?")
        params.append(f'%{parish_filter}%')
    if book_type_filter:
        conditions.append("entry_type = ?")
        params.append(book_type_filter)

    rows = db.execute(
        f"SELECT entry_id, book_id, event_year, entry_type, raw_json "
        f"FROM source_matrikula_entries WHERE {' AND '.join(conditions)}",
        params,
    ).fetchall()

    if not rows:
        print("Keine Einträge gefunden.")
        return {'entries': 0, 'persons': 0, 'skipped': 0}

    total_entries = len(rows)
    skipped = 0
    total_persons = 0

    print(f"{total_entries} Einträge zu verarbeiten ...")

    if force:
        # Alte NER-Daten für den gefilterten Bereich löschen
        if parish_filter:
            db.execute("DELETE FROM matrikula_ner WHERE book_id LIKE ?", (f'%{parish_filter}%',))
        elif book_type_filter:
            pass  # entry_type-Filter: selektives Löschen nicht trivial, skip
        else:
            db.execute("DELETE FROM matrikula_ner")
        db.commit()

    batch: list[dict] = []
    BATCH_SIZE = 200

    def _flush(batch: list[dict]) -> None:
        if not batch:
            return
        with db:
            db.executemany(
                """INSERT INTO matrikula_ner
                   (entry_id, book_id, event_year, name_raw, name_norm, koeln_code,
                    rolle, beruf, ort, geburtsname)
                   VALUES (:entry_id, :book_id, :event_year, :name_raw, :name_norm,
                           :koeln_code, :rolle, :beruf, :ort, :geburtsname)""",
                batch,
            )

    for i, row in enumerate(rows):
        entry_id = row['entry_id']
        if entry_id in done_ids:
            skipped += 1
            continue

        persons = _persons_from_entry(
            entry_id, row['book_id'], row['event_year'],
            row['entry_type'], row['raw_json'],
        )
        batch.extend(persons)
        total_persons += len(persons)

        if len(batch) >= BATCH_SIZE:
            _flush(batch)
            batch = []

        if (i + 1) % 500 == 0 or (i + 1) == total_entries:
            _flush(batch)
            batch = []
            print(f"  {i + 1}/{total_entries} · {total_persons} Personen", flush=True)

    _flush(batch)

    print("\nFertig:")
    print(f"  {total_entries - skipped} Einträge verarbeitet")
    print(f"  {skipped} übersprungen (bereits in NER-Tabelle)")
    print(f"  {total_persons} Personen-Einträge neu geschrieben")
    print_stats(db)
    db.close()

    return {'entries': total_entries, 'persons': total_persons, 'skipped': skipped}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(
        description='Personen-Rollen aus Matricula-OCR-JSON in matrikula_ner extrahieren'
    )
    ap.add_argument('--parish',    default=None, help='Nur dieses Kirchspiel (Teil-Match)')
    ap.add_argument('--book-type', default=None, choices=['Taufe', 'Heirat', 'Tod'],
                    help='Nur diesen Buchtyp verarbeiten')
    ap.add_argument('--force',     action='store_true',
                    help='Vorhandene NER-Einträge überschreiben')
    ap.add_argument('--stats',     action='store_true',
                    help='Nur Statistik anzeigen, nichts schreiben')
    args = ap.parse_args()

    extract_ner(
        parish_filter=args.parish,
        book_type_filter=args.book_type,
        force=args.force,
        stats_only=args.stats,
    )
