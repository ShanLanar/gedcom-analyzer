import pytest
from ancestry.core.db.connection import open_ro, open_entity, open_admin
from ancestry.core.db.runner import run


def _fresh_db(tmp_path):
    conn = open_admin(str(tmp_path / "test.db"))
    run(conn)
    conn.execute("INSERT OR IGNORE INTO dna_kits (guid,name) VALUES ('T1','Test')")
    conn.commit()
    return conn


def test_open_ro_cannot_write_matches(tmp_path):
    _fresh_db(tmp_path).close()
    conn = open_ro(str(tmp_path / "test.db"))
    with pytest.raises(Exception):
        conn.execute("INSERT INTO matches (match_guid,test_guid) VALUES ('X','T1')")
        conn.commit()
    conn.close()


def test_open_entity_cannot_write_matches(tmp_path):
    _fresh_db(tmp_path).close()
    conn = open_entity(str(tmp_path / "test.db"))
    with pytest.raises(Exception):
        conn.execute("INSERT INTO matches (match_guid,test_guid) VALUES ('X','T1')")
        conn.commit()
    conn.close()


def test_open_entity_can_write_entities(tmp_path):
    _fresh_db(tmp_path).close()
    conn = open_entity(str(tmp_path / "test.db"))
    conn.execute("INSERT INTO entities (label) VALUES ('Test Person')")
    conn.commit()
    row = conn.execute("SELECT label FROM entities WHERE label='Test Person'").fetchone()
    assert row is not None
    conn.close()
