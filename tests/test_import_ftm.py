"""Tests für tasks.import_ftm – FTM SQLite-Import."""
import os
import sqlite3
import tempfile

import pytest

from tasks.import_ftm import is_ftm_file, load_ftm


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _make_ftm_db(path: str) -> None:
    """Erzeugt eine minimale FTM-ähnliche SQLite-Datenbank für Tests."""
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE Individual (
            IndividualID INTEGER PRIMARY KEY,
            Sex TEXT
        );
        CREATE TABLE PersonName (
            PersonNameID INTEGER PRIMARY KEY,
            IndividualID INTEGER,
            NameType     INTEGER DEFAULT 0,
            Prefix       TEXT,
            Given        TEXT,
            Surname      TEXT,
            Suffix       TEXT
        );
        CREATE TABLE FactType (
            FactTypeID INTEGER PRIMARY KEY,
            Tag        TEXT,
            Name       TEXT
        );
        CREATE TABLE Place (
            PlaceID   INTEGER PRIMARY KEY,
            Name      TEXT
        );
        CREATE TABLE Fact (
            FactID      INTEGER PRIMARY KEY,
            OwnerID     INTEGER,
            OwnerType   INTEGER DEFAULT 0,
            FactTypeID  INTEGER,
            Date1       TEXT,
            Place1ID    INTEGER
        );
        CREATE TABLE Family (
            FamilyID   INTEGER PRIMARY KEY,
            HusbandID  INTEGER,
            WifeID     INTEGER
        );
        CREATE TABLE FamilyChild (
            FamilyID   INTEGER,
            ChildID    INTEGER
        );
    """)

    # FactTypes
    cur.executemany("INSERT INTO FactType VALUES (?,?,?)", [
        (1, "BIRT", "Birth"),
        (2, "DEAT", "Death"),
        (3, "MARR", "Marriage"),
        (4, "EMIG", "Emigration"),
        (5, "IMMI", "Immigration"),
    ])

    # Orte
    cur.executemany("INSERT INTO Place VALUES (?,?)", [
        (10, "Osnabrück, Niedersachsen, Deutschland"),
        (20, "Hamburg, Deutschland"),
        (30, "New York, USA"),
    ])

    # Personen
    cur.executemany("INSERT INTO Individual VALUES (?,?)", [
        (1, "M"),   # Vater
        (2, "F"),   # Mutter
        (3, "M"),   # Sohn
        (4, "F"),   # Tochter (mit mig.-Marker)
    ])

    # Namen
    cur.executemany(
        "INSERT INTO PersonName(IndividualID,NameType,Given,Surname) VALUES (?,?,?,?)",
        [
            (1, 0, "Hans",  "Müller"),
            (2, 0, "Anna",  "Schmidt"),
            (3, 0, "Fritz", "Müller"),
            (4, 0, "mig. Else", "Müller"),   # mig.-Marker im Vornamen
        ]
    )

    # Ereignisse: Geburt, Tod, Migration
    cur.executemany(
        "INSERT INTO Fact(OwnerID,OwnerType,FactTypeID,Date1,Place1ID) VALUES (?,?,?,?,?)",
        [
            (1, 0, 1, "15 MAR 1850", 10),   # Hans Geburt
            (1, 0, 2, "20 DEC 1920", 20),   # Hans Tod
            (2, 0, 1, "ABT 1855",    10),   # Anna Geburt
            (3, 0, 1, "1 JAN 1880",  10),   # Fritz Geburt
            (4, 0, 4, "1882",        20),   # Else Emigration
            (4, 0, 5, "1882",        30),   # Else Immigration
        ]
    )

    # Familie
    cur.execute("INSERT INTO Family VALUES (1, 1, 2)")   # Hans + Anna
    cur.executemany("INSERT INTO FamilyChild VALUES (?,?)", [
        (1, 3),   # Fritz
        (1, 4),   # Else
    ])

    # Heirat als Familien-Fact (OwnerType=1)
    cur.execute(
        "INSERT INTO Fact(OwnerID,OwnerType,FactTypeID,Date1,Place1ID) VALUES (?,?,?,?,?)",
        (1, 1, 3, "10 JUN 1875", 10)
    )

    conn.commit()
    conn.close()


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_is_ftm_file_true():
    with tempfile.NamedTemporaryFile(suffix=".ftm", delete=False) as t:
        path = t.name
    try:
        _make_ftm_db(path)
        assert is_ftm_file(path) is True
    finally:
        os.unlink(path)


def test_is_ftm_file_false_on_gedcom(tmp_path):
    ged = tmp_path / "test.ged"
    ged.write_text("0 HEAD\n1 GEDC\n", encoding="utf-8")
    assert is_ftm_file(str(ged)) is False


def test_is_ftm_file_false_on_missing():
    assert is_ftm_file("/nonexistent/path/file.ftm") is False


def test_load_ftm_basic():
    with tempfile.NamedTemporaryFile(suffix=".ftm", delete=False) as t:
        path = t.name
    try:
        _make_ftm_db(path)
        indiv, fams = load_ftm(path)

        assert len(indiv) == 4
        assert len(fams) == 1

        # Hans Müller
        hans = indiv["@I1@"]
        assert hans["SEX"] == "M"
        assert "Hans" in hans["NAME"]
        assert "/Müller/" in hans["NAME"]
        assert hans["BIRT"]["YEAR"] == 1850
        assert hans["DEAT"]["YEAR"] == 1920
        assert "Osnabrück" in hans["BIRT"]["PLAC"]
        assert hans["BIRTH_PLACE"] is not None

        # Anna Schmidt
        anna = indiv["@I2@"]
        assert anna["SEX"] == "F"
        assert anna["BIRT"]["DATE_QUAL"] == "about"

        # Else mit mig.-Marker
        else_ = indiv["@I4@"]
        assert else_["MIGRATED"] is True
        assert else_["EMIG"]["YEAR"] == 1882
        assert else_["IMMI"]["YEAR"] == 1882
    finally:
        os.unlink(path)


def test_load_ftm_family_links():
    with tempfile.NamedTemporaryFile(suffix=".ftm", delete=False) as t:
        path = t.name
    try:
        _make_ftm_db(path)
        indiv, fams = load_ftm(path)

        fam = fams["@F1@"]
        assert fam["HUSB"] == "@I1@"
        assert fam["WIFE"] == "@I2@"
        assert "@I3@" in fam["CHIL"]
        assert "@I4@" in fam["CHIL"]

        # FAMS/FAMC Rückverknüpfungen
        assert "@F1@" in indiv["@I1@"]["FAMS"]
        assert "@F1@" in indiv["@I2@"]["FAMS"]
        assert "@F1@" in indiv["@I3@"]["FAMC"]
        assert "@F1@" in indiv["@I4@"]["FAMC"]
    finally:
        os.unlink(path)


def test_load_ftm_marriage():
    with tempfile.NamedTemporaryFile(suffix=".ftm", delete=False) as t:
        path = t.name
    try:
        _make_ftm_db(path)
        _, fams = load_ftm(path)
        fam = fams["@F1@"]
        assert fam["MARR_DATE"] == "10 JUN 1875"
        assert "Osnabrück" in (fam["MARR_PLACE"] or "")
    finally:
        os.unlink(path)


def test_load_ftm_not_sqlite(tmp_path):
    bad = tmp_path / "not.ftm"
    bad.write_bytes(b"This is not a SQLite file at all!")
    with pytest.raises(ValueError, match="SQLite"):
        load_ftm(str(bad))


def test_load_ftm_missing_file():
    with pytest.raises(FileNotFoundError):
        load_ftm("/no/such/file.ftm")


def test_load_ftm_alternate_schema():
    """Schema-Variante: Spalten heißen anders (FTM MacKiev-Stil)."""
    with tempfile.NamedTemporaryFile(suffix=".ftm", delete=False) as t:
        path = t.name
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.executescript("""
            CREATE TABLE Individual (PersonID INTEGER PRIMARY KEY, Gender TEXT);
            CREATE TABLE PersonName  (PersonID INTEGER, Given TEXT, Surname TEXT,
                                      NameType INTEGER DEFAULT 0);
            CREATE TABLE Family      (FamilyID INTEGER PRIMARY KEY,
                                      FatherID INTEGER, MotherID INTEGER);
            CREATE TABLE FamilyChild (FamilyID INTEGER, ChildID INTEGER);
        """)
        cur.execute("INSERT INTO Individual VALUES (1,'M')")
        cur.execute("INSERT INTO PersonName VALUES (1,'Johann','Braun',0)")
        cur.execute("INSERT INTO Family VALUES (1,1,NULL)")
        conn.commit()
        conn.close()

        indiv, fams = load_ftm(path)
        assert "@I1@" in indiv
        assert indiv["@I1@"]["SEX"] == "M"
        assert "Johann" in (indiv["@I1@"]["NAME"] or "")
        assert len(fams) == 1
    finally:
        os.unlink(path)
