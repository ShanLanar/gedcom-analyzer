"""Tests für den Archion-Fallback-Katalog in matricula_status (Sprint 8)."""
import json
import sqlite3

from ancestry.tools.matricula_status import get_archion_archives


def _make_db(path):
    db = sqlite3.connect(str(path))
    db.execute(
        "CREATE TABLE archion_archives (id TEXT PRIMARY KEY, region TEXT, "
        "name TEXT, url TEXT, confession TEXT DEFAULT 'evang', scraped_at TEXT)"
    )
    db.executemany(
        "INSERT INTO archion_archives (id, region, name, url) VALUES (?,?,?,?)",
        [("nds/lka", "Niedersachsen", "LKA Hannover", "https://archion.de/a"),
         ("by/lkb",  "Bayern",        "LKA Nürnberg", "https://archion.de/b")],
    )
    db.commit()
    db.close()


def test_reads_db_catalog(tmp_path):
    p = tmp_path / "archion_archives.db"
    _make_db(p)
    out = get_archion_archives(p)
    assert len(out) == 2
    assert out[0]["region"] == "Bayern"        # alphabetisch nach region
    assert all(a["source"] == "archion" for a in out)


def test_missing_catalog_returns_empty(tmp_path):
    assert get_archion_archives(tmp_path / "does_not_exist.db") == []


def test_json_fallback(tmp_path, monkeypatch):
    import ancestry.tools.matricula_status as ms
    jf = tmp_path / "archion_archives.json"
    jf.write_text(json.dumps({
        "Niedersachsen": [{"id": "nds/lka", "name": "LKA Hannover",
                           "url": "https://archion.de/a"}],
    }), encoding="utf-8")
    monkeypatch.setattr(ms, "ARCHION_JSON", jf)
    # nicht existierende DB → JSON-Fallback greift
    out = get_archion_archives(tmp_path / "no.db")
    assert len(out) == 1
    assert out[0]["name"] == "LKA Hannover"
    assert out[0]["confession"] == "evang"     # Default gesetzt
