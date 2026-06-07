"""
Tests für ancestry/core/bridge.py — GEDCOM↔DNA-Verknüpfungsmodul.

Testet Kölner Phonetik, Levenshtein, Scoring-Funktion, GEDCOM-Import
und Match-Abgleich (ohne echte API-Verbindung).
"""
import os
import sys
import tempfile
import types
import pytest

# ── ancestry/ in sys.path (ohne core/__init__.py zu triggern) ───────────────
_ANCESTRY = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ancestry")
if _ANCESTRY not in sys.path:
    sys.path.append(_ANCESTRY)
if "core" not in sys.modules:
    _stub = types.ModuleType("core")
    _stub.__path__ = [os.path.join(_ANCESTRY, "core")]
    _stub.__package__ = "core"
    sys.modules["core"] = _stub

from core.bridge import (
    _koelner, _levenshtein, _norm, _parse_name_from_indi,
    compute_link_score, import_gedcom_persons,
    run_match_for_match, ensure_tables, get_gedcom_person_count,
    MIN_LINK_SCORE,
)
from core.database import Database


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)
    ensure_tables(database)
    yield database
    database.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


# ── Kölner Phonetik ──────────────────────────────────────────────────────────
# Hinweis: diese Implementierung entfernt interne Nullen NICHT (wie in
# tasks/names.py). Dadurch entstehen andere Codes als im Lehrbuch, aber
# alle Schreibvarianten eines Namens liefern denselben Code (Konsistenz).

def test_koelner_empty():
    assert _koelner("") == ""


def test_koelner_meyervariants_all_same():
    variants = ["Meyer", "Maier", "Mayer", "Meier"]
    codes = {_koelner(_norm(v)) for v in variants}
    assert len(codes) == 1, f"Unterschiedliche Codes: {codes}"
    assert list(codes)[0] == "607"


def test_koelner_muellervariants_all_same():
    codes = {_koelner(_norm(v)) for v in ["Müller", "Mueller"]}
    assert len(codes) == 1
    assert list(codes)[0] == "60507"


def test_koelner_schmidt_variants_same():
    codes = {_koelner(_norm(v)) for v in ["Schmidt", "Schmitt"]}
    assert len(codes) == 1


def test_koelner_hoffmann_variants_same():
    codes = {_koelner(_norm(v)) for v in ["Hoffmann", "Hofmann"]}
    assert len(codes) == 1


def test_koelner_schulz_umlaut_same():
    codes = {_koelner(_norm(v)) for v in ["Schulz", "Schülz"]}
    assert len(codes) == 1


def test_koelner_groups_variants():
    # Alle Schreibvarianten von Meyer müssen denselben Code ergeben
    variants = ["Meyer", "Maier", "Mayer", "Meier"]
    codes = {_koelner(_norm(v)) for v in variants}
    assert len(codes) == 1, f"Unterschiedliche Codes: {codes}"


# ── Levenshtein ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b,expected", [
    ("müller", "muller", 1),
    ("schmidt", "schmitt", 1),
    ("hoffmann", "hofmann", 1),
    ("abc", "abc", 0),
    ("", "abc", 3),
    ("abc", "", 3),
    ("maier", "mayer", 1),
])
def test_levenshtein(a, b, expected):
    assert _levenshtein(a, b) == expected


# ── Normalisierung ───────────────────────────────────────────────────────────

def test_norm_umlaut():
    assert _norm("Müller") == "muller"
    assert _norm("Schütz") == "schutz"
    assert _norm("Weiß")   == "weiss"


def test_norm_accents():
    assert _norm("Léon") == "leon"


# ── GEDCOM-Namen parsen ──────────────────────────────────────────────────────

@pytest.mark.parametrize("ind,expected_given,expected_sur", [
    ({"NAME": "Hans /Müller/"},      "Hans",  "Müller"),
    ({"NAME": "Anna Maria /Bauer/"}, "Anna Maria", "Bauer"),
    ({"NAME": "Johann"},             "Johann", ""),
    ({"_GIVN": "Karl", "_SURN": "Schmidt"}, "Karl", "Schmidt"),
    ({"GIVN": "Maria", "SURN": "Weber"},    "Maria", "Weber"),
    ({"NAME": ""},                   "", ""),
])
def test_parse_name_from_indi(ind, expected_given, expected_sur):
    given, sur = _parse_name_from_indi(ind)
    assert given == expected_given
    assert sur   == expected_sur


# ── Scoring ──────────────────────────────────────────────────────────────────

def _ged(surname, given="", birth_year=None, birth_qual=""):
    sn = _norm(surname)
    return {
        "surname":      surname,
        "surname_norm": sn,
        "koelner_code": _koelner(sn),
        "given_name":   given,
        "birth_year":   birth_year,
        "birth_qual":   birth_qual,
    }


def test_score_exact_match():
    score, method = compute_link_score("Hans", "Müller", 1850, _ged("Müller", "Hans", 1850))
    assert score >= 0.9
    assert method == "exact"


def test_score_phonetic_match():
    # Meyer vs. Maier → phonetisch gleich
    score, method = compute_link_score("Karl", "Meyer", 1870, _ged("Maier", "Karl", 1870))
    assert score >= MIN_LINK_SCORE
    assert method == "phonetic"


def test_score_levenshtein_match():
    # Hoffmann vs. Hofmann (lev=1)
    score, method = compute_link_score("Anna", "Hoffmann", None, _ged("Hofmann", "Anna"))
    assert score >= MIN_LINK_SCORE
    assert method in ("phonetic", "levenshtein")


def test_score_no_match_different_name():
    score, method = compute_link_score("Hans", "Müller", 1850, _ged("Becker", "Hans", 1850))
    assert score == 0.0


def test_score_year_hard_disqualifier_phonetic():
    # Phonetisch ähnlich, aber 30 Jahre Unterschied + kein hoher Name-Score
    # → Treffer unter Schwellenwert oder kein Treffer
    score, _ = compute_link_score("Hans", "Maier", 1850, _ged("Meyer", "Klaus", 1880))
    # name_score < 0.85 (phonetisch, verschiedener Vorname) + Jahr weit → 0
    assert score < MIN_LINK_SCORE or score == 0.0


def test_score_year_bonus_phonetic():
    # Phonetischer Treffer: Jahr-Bonus macht Unterschied
    score_with, _    = compute_link_score("", "Maier", 1870, _ged("Meyer", "", 1870))
    score_without, _ = compute_link_score("", "Maier", None,  _ged("Meyer", "", None))
    assert score_with > score_without


def test_score_given_name_bonus():
    # Gleicher Nachname, Vorname unterschiedlich – ohne Vorname-Bonus vs. mit
    score_match, _    = compute_link_score("Heinrich", "Müller", None, _ged("Müller", "Heinrich"))
    score_nomatch, _  = compute_link_score("Xzqwy",   "Müller", None, _ged("Müller", "Zander"))
    assert score_match >= score_nomatch


def test_score_about_year_wider_tolerance():
    # "ABT 1850" in GEDCOM → 15 Jahre Toleranz
    score, _ = compute_link_score("Hans", "Müller", 1860, _ged("Müller", "Hans", 1850, "about"))
    assert score >= MIN_LINK_SCORE


# ── GEDCOM-Import ─────────────────────────────────────────────────────────────

_SAMPLE_INDIVIDUALS = {
    "@I1@": {"NAME": "Johann /Müller/", "SEX": "M",
              "BIRT": {"YEAR": 1820, "PLAC": "Osnabrück", "DATE_QUAL": "exact"},
              "DEAT": {"YEAR": 1890, "PLAC": ""}},
    "@I2@": {"NAME": "Maria /Hoffmann/", "SEX": "F",
              "BIRT": {"YEAR": 1825, "PLAC": "Hamburg", "DATE_QUAL": ""},
              "DEAT": {}},
    "@I3@": {"NAME": "Franz /Schmidt/", "SEX": "M",
              "BIRT": {"YEAR": 1800, "PLAC": "", "DATE_QUAL": "about"},
              "DEAT": {}},
    "@I4@": {"NAME": "", "SEX": ""},  # kein Name → soll übersprungen werden
}


def test_import_gedcom_persons(db):
    n = import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "test.ged")
    assert n == 3  # @I4@ hat keinen Namen → übersprungen
    assert get_gedcom_person_count(db) == 3


def test_import_gedcom_clears_old(db):
    import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "test.ged")
    # Zweiter Import löscht alten Bestand
    import_gedcom_persons(db, {"@I99@": {"NAME": "Test /Person/", "SEX": ""}}, "neu.ged")
    assert get_gedcom_person_count(db) == 1


def test_import_stores_koelner(db):
    import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "t.ged")
    with db._cursor() as cur:
        rows = {r["ged_id"]: dict(r) for r in cur.execute(
            "SELECT ged_id, koelner_code FROM gedcom_persons").fetchall()}
    assert rows["@I1@"]["koelner_code"] == _koelner("muller")
    assert rows["@I2@"]["koelner_code"] == _koelner("hoffmann")


def test_import_stores_birth_qual(db):
    import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "t.ged")
    with db._cursor() as cur:
        row = dict(cur.execute(
            "SELECT birth_qual FROM gedcom_persons WHERE ged_id=?",
            ("@I3@",)).fetchone())
    assert row["birth_qual"] == "about"


# ── Matching gegen DB ─────────────────────────────────────────────────────────

def _insert_pedigree(db, test_guid, match_guid, rows):
    """Hilfsfunktion: fügt match_pedigree-Zeilen ein."""
    with db._cursor() as cur:
        cur.executemany(
            """INSERT OR IGNORE INTO match_pedigree
               (test_guid, match_guid, given_name, surname, birth_year,
                birth_place, generation, ahnen_path)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(test_guid, match_guid,
              r.get("given_name",""), r.get("surname",""),
              r.get("birth_year"), r.get("birth_place",""),
              r.get("generation",2), r.get("ahnen_path",""))
             for r in rows],
        )


def test_run_match_finds_exact(db):
    import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "t.ged")
    _insert_pedigree(db, "TG1", "M1", [
        {"given_name": "Johann", "surname": "Müller", "birth_year": "1820",
         "generation": 2, "ahnen_path": "F"},
    ])
    # Auch match_guid in matches eintragen (FK-locker, aber sicherer)
    with db._cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO matches (match_guid, test_guid, display_name)"
            " VALUES (?,?,?)", ("M1", "TG1", "Test Match"))
    result = run_match_for_match(db, "TG1", "M1")
    assert len(result) == 1
    hit = result[0]
    assert hit["icon"] in ("✓", "~")
    assert hit["ged_name"] == "Johann Müller"


def test_run_match_finds_phonetic(db):
    import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "t.ged")
    _insert_pedigree(db, "TG2", "M2", [
        # "Hoffmann" vs. "Hofmann" → phonetisch gleich
        {"given_name": "Maria", "surname": "Hofmann", "birth_year": "1825",
         "generation": 2, "ahnen_path": "M"},
    ])
    with db._cursor() as cur:
        cur.execute("INSERT OR IGNORE INTO matches (match_guid, test_guid, display_name)"
                    " VALUES (?,?,?)", ("M2", "TG2", "Test Match 2"))
    result = run_match_for_match(db, "TG2", "M2")
    hits = [r for r in result if r["icon"]]
    assert len(hits) >= 1
    assert "Hoffmann" in hits[0]["ged_name"]


def test_run_match_no_hit_for_unknown_name(db):
    import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "t.ged")
    _insert_pedigree(db, "TG3", "M3", [
        {"given_name": "Franz", "surname": "Xylophon", "birth_year": None,
         "generation": 2, "ahnen_path": "F"},
    ])
    with db._cursor() as cur:
        cur.execute("INSERT OR IGNORE INTO matches (match_guid, test_guid, display_name)"
                    " VALUES (?,?,?)", ("M3", "TG3", "Test Match 3"))
    result = run_match_for_match(db, "TG3", "M3")
    assert len(result) == 1
    assert result[0]["icon"] == ""
    assert result[0]["ged_name"] == "—"


def test_run_match_empty_pedigree(db):
    import_gedcom_persons(db, _SAMPLE_INDIVIDUALS, "t.ged")
    result = run_match_for_match(db, "TG4", "M4_no_ped")
    assert result == []


def test_run_match_empty_gedcom(db):
    # Kein GEDCOM importiert → leere Ergebnisliste
    _insert_pedigree(db, "TG5", "M5", [
        {"given_name": "Hans", "surname": "Müller", "generation": 2, "ahnen_path": "F"},
    ])
    with db._cursor() as cur:
        cur.execute("INSERT OR IGNORE INTO matches (match_guid, test_guid, display_name)"
                    " VALUES (?,?,?)", ("M5", "TG5", "Test Match 5"))
    result = run_match_for_match(db, "TG5", "M5")
    assert result == []


def test_score_threshold():
    # Weit-entfernte Nachnamen sollen unter dem Schwellenwert bleiben
    low, _ = compute_link_score("Hans", "Abc", 1850, _ged("Xyz", "Hans", 1850))
    assert low < MIN_LINK_SCORE
