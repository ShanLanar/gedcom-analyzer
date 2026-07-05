"""Tests für den X-Vererbungs-Fächer (ancestry/core/x_inheritance.py)."""
from ancestry.core.x_inheritance import (
    is_x_ancestor, x_ancestor_count_per_gen, x_ancestor_sosa,
)


# ── Bekannte Einzelfälle (Sosa) ───────────────────────────────────────────────

def test_man_no_x_from_father():
    assert is_x_ancestor(2, "M") is False          # Vater
    assert is_x_ancestor(3, "M") is True           # Mutter


def test_man_paternal_grandparents_none():
    assert is_x_ancestor(4, "M") is False          # Vater-Vater
    assert is_x_ancestor(5, "M") is False          # Vater-Mutter (Vater trägt kein X)


def test_man_maternal_grandfather_contributes():
    assert is_x_ancestor(6, "M") is True           # Mutter-Vater
    assert is_x_ancestor(7, "M") is True           # Mutter-Mutter


def test_woman_gets_x_from_father():
    assert is_x_ancestor(2, "F") is True           # Vater
    assert is_x_ancestor(3, "F") is True           # Mutter


def test_woman_paternal_grandmother_only():
    assert is_x_ancestor(4, "F") is False          # Vater-Vater (bricht)
    assert is_x_ancestor(5, "F") is True           # Vater-Mutter (Großmutter väterl.)


def test_self_is_always_x():
    assert is_x_ancestor(1, "M") is True
    assert is_x_ancestor(1, "F") is True


def test_no_two_consecutive_fathers():
    # Sosa 8 = Vater-Vater-Vater → nie X
    assert is_x_ancestor(8, "M") is False
    assert is_x_ancestor(8, "F") is False


# ── Fibonacci-Eigenschaft ─────────────────────────────────────────────────────

def test_counts_follow_fibonacci():
    # Mann: 1,1,2,3,5,8 ; Frau: 1,2,3,5,8,13
    assert x_ancestor_count_per_gen("M", 6) == [1, 1, 2, 3, 5, 8]
    assert x_ancestor_count_per_gen("F", 6) == [1, 2, 3, 5, 8, 13]


def test_sex_synonyms_accepted():
    assert is_x_ancestor(2, "männlich") is False
    assert is_x_ancestor(2, "male") is False
    assert is_x_ancestor(2, "W") is True           # weiblich
    assert is_x_ancestor(2, "weiblich") is True
    assert is_x_ancestor(2, "female") is True


def test_fan_set_matches_counts():
    fan = x_ancestor_sosa("F", 5)
    # Gen 5 = Sosa 16..31; Anzahl X-Ahnen dort = 8 (Fibonacci)
    assert sum(1 for s in fan if 16 <= s < 32) == 8


# ── DB-Helfer get_x_ancestors ─────────────────────────────────────────────────

def test_get_x_ancestors_filters_by_sex(tmp_path):
    import os

    from ancestry.core.database import Database
    db = Database(str(tmp_path / "x.db"))
    try:
        # gedcom_persons minimal anlegen + Ahnen mit Sosa-Nummern setzen
        with db._cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS gedcom_persons (
                ged_id TEXT PRIMARY KEY, given_name TEXT, surname TEXT,
                birth_year INTEGER, sex TEXT, sosa_number INTEGER DEFAULT 0)""")
            for sosa, name in [(2, "Vater"), (3, "Mutter"), (4, "VaVa"),
                               (5, "VaMu"), (6, "MuVa"), (7, "MuMu")]:
                cur.execute(
                    "INSERT INTO gedcom_persons (ged_id, given_name, surname, "
                    "sosa_number) VALUES (?,?,?,?)",
                    (f"@I{sosa}@", name, "Test", sosa))

        male = {a["sosa"] for a in db.get_x_ancestors("männlich")}
        # Mann: nur Mutter(3), MuVa(6), MuMu(7) tragen X (Vater/VaVa/VaMu nicht)
        assert male == {3, 6, 7}

        female = {a["sosa"] for a in db.get_x_ancestors("weiblich")}
        # Frau: Vater(2), Mutter(3), VaMu(5), MuVa(6), MuMu(7); VaVa(4) nicht
        assert female == {2, 3, 5, 6, 7}
    finally:
        db.close()
        for suf in ("", "-wal", "-shm"):
            try:
                os.unlink(str(tmp_path / "x.db") + suf)
            except FileNotFoundError:
                pass


def test_get_x_ancestors_empty_without_table(tmp_path):
    from ancestry.core.database import Database
    db = Database(str(tmp_path / "x2.db"))
    try:
        assert db.get_x_ancestors("M") == []      # keine gedcom_persons → leer
    finally:
        db.close()
