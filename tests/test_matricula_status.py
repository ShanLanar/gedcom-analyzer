"""Tests für ancestry/tools/matricula_status.py (Pfarrei-Fortschritt)."""

import sqlite3

import pytest

from ancestry.tools import matricula_status as mstat


@pytest.fixture
def parish_db(tmp_path):
    path = tmp_path / "matricula_parishes.db"
    db = sqlite3.connect(str(path))
    db.executescript("""
        CREATE TABLE parishes (
            id TEXT PRIMARY KEY, slug TEXT DEFAULT '', diocese TEXT DEFAULT '',
            name TEXT NOT NULL, confession TEXT DEFAULT 'kath',
            founded_year INTEGER, url TEXT DEFAULT '', scraped_at TEXT DEFAULT ''
        );
        CREATE TABLE kirchenbuecher (
            book_id TEXT PRIMARY KEY, parish_id TEXT NOT NULL,
            book_type TEXT DEFAULT 'unbekannt', year_from INTEGER, year_to INTEGER,
            label TEXT DEFAULT '', url TEXT DEFAULT '', scraped_at TEXT DEFAULT '',
            total_pages INTEGER
        );
        CREATE TABLE matricula_page_scans (
            scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id TEXT NOT NULL, page_nr INTEGER NOT NULL,
            image_url TEXT DEFAULT '', image_path TEXT DEFAULT '',
            status TEXT DEFAULT 'pending', entry_count INTEGER DEFAULT 0,
            scanned_at TEXT DEFAULT '', error_msg TEXT DEFAULT '',
            UNIQUE (book_id, page_nr)
        );
    """)
    db.commit()
    yield db, path
    db.close()


def _add_parish(db, pid, name):
    db.execute("INSERT INTO parishes (id, name) VALUES (?,?)", (pid, name))


def _add_book(db, book_id, parish_id, total_pages=None):
    db.execute("INSERT INTO kirchenbuecher (book_id, parish_id, total_pages) "
               "VALUES (?,?,?)", (book_id, parish_id, total_pages))


def _scan_pages(db, book_id, n, status="done"):
    for p in range(1, n + 1):
        db.execute("INSERT OR REPLACE INTO matricula_page_scans "
                   "(book_id, page_nr, status) VALUES (?,?,?)",
                   (book_id, p, status))


def test_open_parish_is_open(parish_db):
    db, path = parish_db
    _add_parish(db, "p/ostercappeln", "Ostercappeln")
    _add_book(db, "p/ostercappeln/b1", "p/ostercappeln", total_pages=100)
    db.commit()
    res = mstat.get_parish_status(path)
    assert len(res) == 1
    assert res[0]["status"] == mstat.STATUS_OPEN
    assert res[0]["pages_done"] == 0
    assert res[0]["pages_total"] == 100


def test_partial_parish(parish_db):
    db, path = parish_db
    _add_parish(db, "p/bohmte", "Bohmte")
    _add_book(db, "p/bohmte/b1", "p/bohmte", total_pages=50)
    _scan_pages(db, "p/bohmte/b1", 20)
    db.commit()
    res = mstat.get_parish_status(path)
    assert res[0]["status"] == mstat.STATUS_PARTIAL
    assert res[0]["pages_done"] == 20
    assert res[0]["pages_total"] == 50


def test_done_parish(parish_db):
    db, path = parish_db
    _add_parish(db, "p/hunteburg", "Hunteburg")
    _add_book(db, "p/hunteburg/b1", "p/hunteburg", total_pages=10)
    _add_book(db, "p/hunteburg/b2", "p/hunteburg", total_pages=5)
    _scan_pages(db, "p/hunteburg/b1", 10)
    _scan_pages(db, "p/hunteburg/b2", 5)
    db.commit()
    res = mstat.get_parish_status(path)
    assert res[0]["status"] == mstat.STATUS_DONE
    assert res[0]["pages_total"] == 15


def test_unsized_book_blocks_done(parish_db):
    """Buch ohne bekannte Seitenanzahl → Pfarrei kann nicht 'fertig' sein."""
    db, path = parish_db
    _add_parish(db, "p/venne", "Venne")
    _add_book(db, "p/venne/b1", "p/venne", total_pages=10)
    _add_book(db, "p/venne/b2", "p/venne", total_pages=None)  # nie gescannt
    _scan_pages(db, "p/venne/b1", 10)
    db.commit()
    res = mstat.get_parish_status(path)
    assert res[0]["status"] == mstat.STATUS_PARTIAL
    assert res[0]["pages_total"] is None


def test_error_pages_dont_count_as_done(parish_db):
    db, path = parish_db
    _add_parish(db, "p/x", "X")
    _add_book(db, "p/x/b1", "p/x", total_pages=5)
    _scan_pages(db, "p/x/b1", 5, status="error")
    db.commit()
    res = mstat.get_parish_status(path)
    assert res[0]["status"] == mstat.STATUS_OPEN


def test_missing_db_returns_empty(tmp_path):
    assert mstat.get_parish_status(tmp_path / "nope.db") == []


def test_format_labels(parish_db):
    db, path = parish_db
    _add_parish(db, "p/a", "Alpha")
    _add_book(db, "p/a/b1", "p/a", total_pages=10)
    _scan_pages(db, "p/a/b1", 10)
    _add_parish(db, "p/b", "Beta")
    _add_book(db, "p/b/b1", "p/b", total_pages=10)
    _scan_pages(db, "p/b/b1", 4)
    _add_parish(db, "p/c", "Gamma")
    db.commit()
    res = {p["name"]: mstat.format_parish_label(p)
           for p in mstat.get_parish_status(path)}
    assert res["Alpha"].startswith("✓")
    assert res["Beta"].startswith("◐") and "4/10" in res["Beta"]
    assert res["Gamma"].startswith("○")
