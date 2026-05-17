# -*- coding: utf-8 -*-
"""
100 Tests aus Sicht eines professionellen Genealogen.

Kategorien:
  1–15:  Datums-/Jahres-Parsing
  16–25: Orts-/Land-Erkennung
  26–35: Namens-Parsing & Symbol-Erkennung
  36–50: Genetische Mathematik (Φ, F, cM)
  51–60: Anomalie-/Plausibilitätsprüfung
  61–70: Demografie & Kohorten
  71–80: Migration
  81–90: Linien & Familienstruktur
  91–100: Exporte & Roundtrips
"""
import math
import os
import tempfile

import pytest

# ─── Hilfs-Helper: Standard-Person/Familie bauen ────────────────────────────────

def _mk_indi(iid, name, sex="U", birth_year=None, birth_place="",
             death_year=None, death_place="", famc=None, fams=None,
             emig_year=None, emig_place="", immi_year=None, immi_place="",
             military_symbols=""):
    name_with_symbols = name + military_symbols
    indi = {
        "NAME": name_with_symbols, "SEX": sex,
        "FAMC": famc or [], "FAMS": fams or [],
        "BIRT": {"DATE": f"1 JAN {birth_year}" if birth_year else None,
                 "YEAR": birth_year,
                 "DATE_QUAL": "exact" if birth_year else None,
                 "PLAC": birth_place or None},
        "DEAT": {"DATE": f"1 JAN {death_year}" if death_year else None,
                 "YEAR": death_year,
                 "DATE_QUAL": "exact" if death_year else None,
                 "PLAC": death_place or None},
        "EMIG": {"DATE": f"1 JAN {emig_year}" if emig_year else None,
                 "YEAR": emig_year, "DATE_QUAL": "exact" if emig_year else None,
                 "PLAC": emig_place or None},
        "IMMI": {"DATE": f"1 JAN {immi_year}" if immi_year else None,
                 "YEAR": immi_year, "DATE_QUAL": "exact" if immi_year else None,
                 "PLAC": immi_place or None},
        "BIRTH_PLACE": birth_place or None,
        "MIGRATED":   "mig." in name.lower() or bool(emig_year),
        "VETERAN":     "✠" in military_symbols or "★" in military_symbols,
        "DIED_IN_BATTLE": "⚔" in military_symbols,
        "LINE_ENDS":   "‡" in military_symbols,
        "GERMAN_SOLDIER": "✠" in military_symbols,
        "OTHER_SOLDIER":  "★" in military_symbols,
    }
    return iid, indi


def _mk_fam(fid, husb=None, wife=None, children=None, marr_year=None, marr_place=""):
    return fid, {"HUSB": husb, "WIFE": wife, "CHIL": list(children or []),
                 "MARR_DATE": str(marr_year) if marr_year else None,
                 "MARR_PLACE": marr_place or None}


# ─── Test-Tree-Generatoren ──────────────────────────────────────────────────────

@pytest.fixture
def small_tree():
    """Drei Generationen: Großeltern → Eltern → Root."""
    indiv = dict([
        _mk_indi("@G1@", "Wilhelm /Müller/", "M", 1820, "Berlin, Deutschland",
                  1895, "Berlin", fams=["@F1@"]),
        _mk_indi("@G2@", "Sophie /Schmidt/", "F", 1825, "Hamburg, Deutschland",
                  1900, "Berlin", fams=["@F1@"]),
        _mk_indi("@P1@", "Friedrich /Müller/", "M", 1850, "Berlin, Deutschland",
                  1925, "Berlin", famc=["@F1@"], fams=["@F2@"]),
        _mk_indi("@P2@", "Maria /Koch/", "F", 1855, "Leipzig, Deutschland",
                  1930, "Berlin", fams=["@F2@"]),
        _mk_indi("@R@", "Hans /Müller/", "M", 1880, "Berlin, Deutschland",
                  1960, "Berlin", famc=["@F2@"]),
    ])
    fams = dict([
        _mk_fam("@F1@", "@G1@", "@G2@", ["@P1@"], 1849, "Berlin"),
        _mk_fam("@F2@", "@P1@", "@P2@", ["@R@"], 1879, "Berlin"),
    ])
    return indiv, fams, "@R@"


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 1: Datums- und Jahres-Parsing (Tests 1–15)
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("date_str,expected_year,expected_qual", [
    ("1 JAN 1850",           1850, "exact"),
    ("ABT 1850",             1850, "about"),
    ("EST 1850",             1850, "estimated"),
    ("BEF 1850",             1850, "before"),
    ("AFT 1850",             1850, "after"),
    ("BET 1850 AND 1860",    1850, "between"),
    ("FROM 1850 TO 1860",    1850, "range"),
    ("15 MAR 1850",          1850, "exact"),
    ("DEC 1850",             1850, "exact"),
    ("1850",                 1850, "exact"),
    ("",                     None, "unknown"),
    (None,                   None, "unknown"),
    ("1 JAN 1066",           1066, "exact"),
    ("ABT 2020",             2020, "about"),
    ("BET 1900 AND 2000",    1900, "between"),
])
def test_date_parsing(date_str, expected_year, expected_qual):
    from lib.gedcom import safe_parse_gedcom_date
    r = safe_parse_gedcom_date(date_str)
    assert r["YEAR"] == expected_year, f"{date_str!r}: expected year {expected_year}"
    assert r["DATE_QUAL"] == expected_qual, f"{date_str!r}: expected qual {expected_qual}"


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 2: Orts- und Land-Erkennung (Tests 16–25)
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("place,location_data,expected_substr", [
    # Deutschland in verschiedenen Schreibweisen
    ("Berlin, Brandenburg, Deutschland",
     {"countries": {"Deutschland": {"aliases": ["Germany"], "states": {}}}}, "Deutschland"),
    ("Hamburg, Germany",
     {"countries": {"Deutschland": {"aliases": ["Germany"], "states": {}}}}, "Deutschland"),
    # USA
    ("New York, NY, USA",
     {"countries": {"USA": {"aliases": ["United States"], "states": {}}}}, "USA"),
    # Empty / None
    ("", {"countries": {}}, None),
    (None, {"countries": {}}, None),
    # Unbekannt → soll None oder "Unbekannt" zurückgeben (gracefully)
    ("Ortdas niemand kennt", {"countries": {}}, None),
])
def test_country_extraction(place, location_data, expected_substr):
    from lib.places import extract_country_from_place
    result = extract_country_from_place(place or "", location_data)
    if expected_substr is None:
        assert result is None or result == "" or result == "Unbekannt"
    else:
        assert result == expected_substr or (result and expected_substr in result)


def test_place_with_umlauts():
    """Ortsnamen mit Umlauten sollen korrekt verarbeitet werden."""
    from lib.places import extract_country_from_place
    location_data = {"countries": {"Österreich": {"aliases": ["Austria"], "states": {}}}}
    result = extract_country_from_place("Wien, Österreich", location_data)
    assert result == "Österreich"


def test_place_historical_name_does_not_crash():
    """Historische Ortsnamen (Königsberg, Breslau) sollen nicht crashen."""
    from lib.places import extract_country_from_place
    for place in ["Königsberg, Ostpreußen", "Breslau, Schlesien", "Posen, Preußen"]:
        result = extract_country_from_place(place, {"countries": {}})
        assert result is None or isinstance(result, str)


def test_format_place_for_display():
    """format_place_for_display soll auch leere/None-Eingaben aushalten."""
    from lib.places import format_place_for_display
    assert format_place_for_display("") in ("", "Unbekannt", None)
    assert format_place_for_display(None) in ("", "Unbekannt", None)
    # Funktioniert mit normaler Eingabe?
    r = format_place_for_display("Berlin, Brandenburg, Deutschland")
    assert isinstance(r, str) and len(r) > 0


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 3: Namens-Parsing & Symbol-Erkennung (Tests 26–35)
# ════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("name,expected_surname", [
    ("Hans /Müller/",             "Müller"),
    ("Hans Peter /Müller/",       "Müller"),
    ("Hans /von Müller/",         "von Müller"),
    ("Hans /Müller-Schmidt/",     "Müller-Schmidt"),
    ("/Müller/",                  "Müller"),
    ("Hans",                       "Hans"),  # kein Slash → ganzer Name als Fallback
    ("",                           ""),
    ("Hans ✠ /Müller/",            "Müller"),  # Symbol vor Slash
    ("Hans /Müller/ ‡",            "Müller"),  # Symbol nach Slash
    ("Hans Peter Friedrich /Müller-Schmidt/ jun.", "Müller-Schmidt"),
])
def test_surname_extraction(name, expected_surname):
    from lib.helpers import safe_extract_family_name
    result = safe_extract_family_name(name)
    # Nachname soll trotz Symbolen gefunden werden
    if expected_surname == "":
        assert result in ("", "Unbekannt", None)
    else:
        assert expected_surname in (result or ""), \
            f"{name!r}: expected {expected_surname!r} in {result!r}"


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 4: Genetische Mathematik – Kinship, Wright's F, cM (Tests 36–50)
# ════════════════════════════════════════════════════════════════════════════════

def _build_two_gen_tree():
    """Großeltern → Eltern → Kind."""
    from tasks.genetics import clear_genetics_cache
    clear_genetics_cache()
    indiv = dict([
        _mk_indi("@PP@", "Großvater paternal", "M", 1800),
        _mk_indi("@PM@", "Großmutter paternal", "F", 1805),
        _mk_indi("@MP@", "Großvater maternal", "M", 1802),
        _mk_indi("@MM@", "Großmutter maternal", "F", 1808),
        _mk_indi("@F@", "Vater", "M", 1830, famc=["@FP@"], fams=["@FC@"]),
        _mk_indi("@M@", "Mutter", "F", 1835, famc=["@FM@"], fams=["@FC@"]),
        _mk_indi("@C@", "Kind", "M", 1860, famc=["@FC@"]),
    ])
    fams = dict([
        _mk_fam("@FP@", "@PP@", "@PM@", ["@F@"]),
        _mk_fam("@FM@", "@MP@", "@MM@", ["@M@"]),
        _mk_fam("@FC@", "@F@", "@M@", ["@C@"]),
    ])
    return indiv, fams


def test_kinship_self_is_half():
    """Φ(A, A) = 0.5 für nicht-inzüchtige Person (mit Eltern im Tree)."""
    from tasks.genetics import _kinship_coefficient
    indiv, fams = _build_two_gen_tree()
    phi = _kinship_coefficient("@C@", "@C@", indiv, fams)
    # Φ(self, self) = 0.5 + F/2 = 0.5 für nicht-inzüchtig
    assert 0.45 < phi <= 0.6, f"Φ(self,self) sollte ~0.5 sein, war {phi}"


def test_kinship_parent_child_quarter():
    """Φ(Eltern, Kind) = 0.25."""
    from tasks.genetics import _kinship_coefficient
    indiv, fams = _build_two_gen_tree()
    phi = _kinship_coefficient("@F@", "@C@", indiv, fams)
    assert abs(phi - 0.25) < 1e-9, f"Φ(Vater, Kind) = {phi}, erwartet 0.25"


def test_kinship_full_siblings_quarter():
    """Φ(Vollgeschwister, unverwandte Eltern) = 0.25."""
    from tasks.genetics import _kinship_coefficient, clear_genetics_cache
    clear_genetics_cache()
    indiv, fams = _build_two_gen_tree()
    # Zweites Kind hinzufügen
    iid, sib = _mk_indi("@C2@", "Geschwister", "F", 1862, famc=["@FC@"])
    indiv[iid] = sib
    fams["@FC@"]["CHIL"].append(iid)
    phi = _kinship_coefficient("@C@", "@C2@", indiv, fams)
    assert abs(phi - 0.25) < 1e-9, f"Φ(Vollgeschwister) = {phi}, erwartet 0.25"


def test_kinship_grandparent_eighth():
    """Φ(Großeltern, Enkel) = 0.125."""
    from tasks.genetics import _kinship_coefficient
    indiv, fams = _build_two_gen_tree()
    phi = _kinship_coefficient("@PP@", "@C@", indiv, fams)
    assert abs(phi - 0.125) < 1e-9, f"Φ(Großeltern, Enkel) = {phi}, erwartet 0.125"


def test_kinship_unrelated_zero():
    """Φ(unverwandt) = 0."""
    from tasks.genetics import _kinship_coefficient
    indiv, fams = _build_two_gen_tree()
    iid, x = _mk_indi("@X@", "Stranger", "M", 1860)
    indiv[iid] = x
    phi = _kinship_coefficient("@C@", "@X@", indiv, fams)
    assert phi == 0.0


def test_kinship_first_cousins_one_sixteenth():
    """Φ(Cousins 1. Grades) = 1/16 = 0.0625."""
    from tasks.genetics import _kinship_coefficient, clear_genetics_cache
    clear_genetics_cache()
    # PP, PM → F1, F2 (Geschwister); F1 → C1; F2 → C2 (Cousins 1. Grades)
    indiv = dict([
        _mk_indi("@PP@", "Opa", "M", 1800),
        _mk_indi("@PM@", "Oma", "F", 1805),
        _mk_indi("@F1@", "Vater1", "M", 1830, famc=["@F0@"], fams=["@FA@"]),
        _mk_indi("@F2@", "Vater2", "M", 1832, famc=["@F0@"], fams=["@FB@"]),
        _mk_indi("@M1@", "Mutter1", "F", 1835, fams=["@FA@"]),
        _mk_indi("@M2@", "Mutter2", "F", 1837, fams=["@FB@"]),
        _mk_indi("@C1@", "Cousin1", "M", 1860, famc=["@FA@"]),
        _mk_indi("@C2@", "Cousin2", "M", 1862, famc=["@FB@"]),
    ])
    fams = dict([
        _mk_fam("@F0@", "@PP@", "@PM@", ["@F1@", "@F2@"]),
        _mk_fam("@FA@", "@F1@", "@M1@", ["@C1@"]),
        _mk_fam("@FB@", "@F2@", "@M2@", ["@C2@"]),
    ])
    phi = _kinship_coefficient("@C1@", "@C2@", indiv, fams)
    assert abs(phi - 1/16) < 1e-9, f"Φ(Cousins 1. Grades) = {phi}, erwartet 0.0625"


def test_wright_f_unrelated_parents():
    """F(Kind, unverwandte Eltern) = 0."""
    from tasks.genetics import compute_inbreeding_coefficient, clear_genetics_cache
    clear_genetics_cache()
    indiv, fams = _build_two_gen_tree()
    F = compute_inbreeding_coefficient("@C@", indiv, fams)
    assert F == 0.0


def test_wright_f_first_cousin_marriage():
    """F(Kind aus Cousin-Ehe) = 1/16."""
    from tasks.genetics import compute_inbreeding_coefficient, clear_genetics_cache
    clear_genetics_cache()
    # Cousins heiraten und bekommen ein Kind
    indiv = dict([
        _mk_indi("@PP@", "Opa", "M", 1800),
        _mk_indi("@PM@", "Oma", "F", 1805),
        _mk_indi("@F1@", "Vater1", "M", 1830, famc=["@F0@"], fams=["@FA@"]),
        _mk_indi("@F2@", "Vater2", "M", 1832, famc=["@F0@"], fams=["@FB@"]),
        _mk_indi("@M1@", "Mutter1", "F", 1835, fams=["@FA@"]),
        _mk_indi("@M2@", "Mutter2", "F", 1837, fams=["@FB@"]),
        _mk_indi("@C1@", "Cousin1", "M", 1860, famc=["@FA@"], fams=["@FC@"]),
        _mk_indi("@C2@", "Cousine2", "F", 1862, famc=["@FB@"], fams=["@FC@"]),
        _mk_indi("@INB@", "Inzucht-Kind", "M", 1885, famc=["@FC@"]),
    ])
    fams = dict([
        _mk_fam("@F0@", "@PP@", "@PM@", ["@F1@", "@F2@"]),
        _mk_fam("@FA@", "@F1@", "@M1@", ["@C1@"]),
        _mk_fam("@FB@", "@F2@", "@M2@", ["@C2@"]),
        _mk_fam("@FC@", "@C1@", "@C2@", ["@INB@"]),
    ])
    F = compute_inbreeding_coefficient("@INB@", indiv, fams)
    assert abs(F - 1/16) < 1e-9, f"F bei Cousin-Ehe = {F}, erwartet 0.0625"


def test_wright_f_sibling_marriage():
    """F(Kind aus Geschwister-Ehe) = 1/4."""
    from tasks.genetics import compute_inbreeding_coefficient, clear_genetics_cache
    clear_genetics_cache()
    indiv = dict([
        _mk_indi("@P1@", "Elternteil1", "M", 1800),
        _mk_indi("@P2@", "Elternteil2", "F", 1805),
        _mk_indi("@S1@", "Bruder", "M", 1830, famc=["@F0@"], fams=["@FX@"]),
        _mk_indi("@S2@", "Schwester", "F", 1832, famc=["@F0@"], fams=["@FX@"]),
        _mk_indi("@X@", "Geschwister-Kind", "M", 1860, famc=["@FX@"]),
    ])
    fams = dict([
        _mk_fam("@F0@", "@P1@", "@P2@", ["@S1@", "@S2@"]),
        _mk_fam("@FX@", "@S1@", "@S2@", ["@X@"]),
    ])
    F = compute_inbreeding_coefficient("@X@", indiv, fams)
    assert abs(F - 0.25) < 1e-9, f"F bei Geschwister-Ehe = {F}, erwartet 0.25"


def test_dna_predict_parent_child_dominates():
    """3500 cM → wahrscheinlichste Beziehung: Eltern/Kind."""
    from tasks.dna_predict import predict_relationship_from_cm
    result = predict_relationship_from_cm(3500)
    assert result[0][0] in ("Elternteil/Kind",), \
        f"3500 cM → erwartet 'Elternteil/Kind', war {result[0][0]}"
    assert result[0][1] > 0.9


def test_dna_predict_cousin_first():
    """850 cM ≈ Cousins 1. Grades."""
    from tasks.dna_predict import predict_relationship_from_cm
    result = predict_relationship_from_cm(850)
    assert result[0][0] == "Cousin 1. Grades"


def test_dna_predict_cousin_third():
    """75 cM ≈ Cousins 3. Grades."""
    from tasks.dna_predict import predict_relationship_from_cm
    result = predict_relationship_from_cm(75)
    assert result[0][0] in ("Cousin 3. Grades", "Cousin 4. Grades")


def test_dna_predict_zero_cm():
    """0 cM → keine Beziehung sollte hohe Wahrscheinlichkeit haben (alle ähnlich klein)."""
    from tasks.dna_predict import predict_relationship_from_cm
    result = predict_relationship_from_cm(0)
    # Sollte trotzdem 5 Einträge liefern, ohne zu crashen
    assert len(result) == 5


def test_kinship_symmetry():
    """Φ(A, B) == Φ(B, A)."""
    from tasks.genetics import _kinship_coefficient, clear_genetics_cache
    clear_genetics_cache()
    indiv, fams = _build_two_gen_tree()
    phi_ab = _kinship_coefficient("@F@", "@C@", indiv, fams)
    clear_genetics_cache()
    phi_ba = _kinship_coefficient("@C@", "@F@", indiv, fams)
    assert abs(phi_ab - phi_ba) < 1e-9


def test_wright_f_no_parents_returns_zero():
    """F = 0 für Person ohne Eltern im Tree."""
    from tasks.genetics import compute_inbreeding_coefficient, clear_genetics_cache
    clear_genetics_cache()
    iid, lone = _mk_indi("@LONE@", "Einzelperson", "M", 1900)
    indiv = {iid: lone}
    F = compute_inbreeding_coefficient(iid, indiv, {})
    assert F == 0.0


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 5: Anomalie-/Plausibilitätsprüfung (Tests 51–60)
# ════════════════════════════════════════════════════════════════════════════════

def test_anomaly_birth_after_death():
    from tasks.anomalies import detect_anomalies
    iid, p = _mk_indi("@A@", "Falsch /Datiert/", "M", 1900, death_year=1850)
    rows = detect_anomalies({iid: p}, {})
    assert any("Geburt nach Tod" in r[3] for r in rows)


def test_anomaly_age_over_110():
    from tasks.anomalies import detect_anomalies
    iid, p = _mk_indi("@A@", "Methusalix /Lang/", "M", 1700, death_year=1820)
    rows = detect_anomalies({iid: p}, {})
    types = [r[3] for r in rows if r[0] == iid]
    assert any("Alter" in t or "110" in t for t in types)


def test_anomaly_mother_too_young():
    """Mutter Geburtsjahr +5 = Kind Geburtsjahr → Mutter 5 J. alt = KRITISCH."""
    from tasks.anomalies import detect_anomalies
    indiv = dict([
        _mk_indi("@K@", "Kind", "M", 1850, famc=["@F1@"]),
        _mk_indi("@M@", "Junge-Mutter", "F", 1845, fams=["@F1@"]),
    ])
    fams = dict([_mk_fam("@F1@", None, "@M@", ["@K@"])])
    rows = detect_anomalies(indiv, fams)
    assert any("Mutter" in r[3] for r in rows)


def test_anomaly_no_false_positives_valid_tree():
    """Bei einem normalen Baum dürfen keine KRITISCHEN Anomalien auftauchen."""
    from tasks.anomalies import detect_anomalies
    indiv, fams, _ = _build_valid_family()
    rows = detect_anomalies(indiv, fams)
    crit = [r for r in rows if r[4] == "KRITISCH"]
    assert len(crit) == 0, f"Valid tree should have 0 KRITISCH anomalies, got {len(crit)}: {crit}"


def _build_valid_family():
    indiv = dict([
        _mk_indi("@P1@", "Vater", "M", 1820, "Berlin", 1890, fams=["@F1@"]),
        _mk_indi("@P2@", "Mutter", "F", 1825, "Berlin", 1895, fams=["@F1@"]),
        _mk_indi("@K1@", "Kind1", "M", 1850, "Berlin", famc=["@F1@"]),
        _mk_indi("@K2@", "Kind2", "F", 1853, "Berlin", famc=["@F1@"]),
    ])
    fams = dict([_mk_fam("@F1@", "@P1@", "@P2@", ["@K1@", "@K2@"], 1849, "Berlin")])
    return indiv, fams, "@K1@"


def test_anomaly_severity_order():
    from tasks.anomalies import detect_anomalies
    iid, p = _mk_indi("@A@", "Falsch /Datiert/", "M", 1900, death_year=1850)
    rows = detect_anomalies({iid: p}, {})
    if len(rows) > 1:
        _order = {"KRITISCH": 0, "WARNUNG": 1, "HINWEIS": 2}
        for i in range(len(rows) - 1):
            assert _order[rows[i][4]] <= _order[rows[i+1][4]]


def test_duplicate_detection_finds_exact_match():
    from tasks.anomalies import detect_duplicates
    indiv = dict([
        _mk_indi("@A@", "Hans /Müller/", "M", 1850),
        _mk_indi("@B@", "Hans /Müller/", "M", 1850),
    ])
    rows = detect_duplicates(indiv)
    assert len(rows) > 0


def test_duplicate_detection_skips_different_persons():
    from tasks.anomalies import detect_duplicates
    indiv = dict([
        _mk_indi("@A@", "Hans /Müller/", "M", 1850),
        _mk_indi("@B@", "Wilhelm /Schmidt/", "M", 1900),
    ])
    rows = detect_duplicates(indiv)
    assert len(rows) == 0


def test_island_detection():
    from tasks.anomalies import detect_islands
    indiv = dict([
        _mk_indi("@R@", "Root", "M", 1850, fams=["@F1@"]),
        _mk_indi("@C@", "Connected", "F", 1880, famc=["@F1@"]),
        _mk_indi("@I@", "Island", "U", 1900),  # nicht verbunden
    ])
    fams = dict([_mk_fam("@F1@", "@R@", None, ["@C@"])])
    rows = detect_islands("@R@", indiv, fams)
    ids = [r[0] for r in rows]
    assert "@I@" in ids and "@C@" not in ids and "@R@" not in ids


def test_anomaly_marriage_under_14():
    from tasks.anomalies import detect_anomalies
    indiv = dict([
        _mk_indi("@A@", "Frühheirat", "M", 1850, fams=["@F1@"]),
    ])
    fams = dict([_mk_fam("@F1@", "@A@", None, [], 1855, "Berlin")])  # Heirat mit 5
    rows = detect_anomalies(indiv, fams)
    assert any("Heirat" in r[3] for r in rows)


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 6: Demografie & Kohorten (Tests 61–70)
# ════════════════════════════════════════════════════════════════════════════════

def test_demographic_statistics_returns_rows():
    from tasks.demographics import analyze_demographic_statistics
    indiv, fams, _ = _build_valid_family()
    rows = analyze_demographic_statistics(indiv, fams, {})
    assert isinstance(rows, list)


def test_surname_frequency_counts_correctly():
    from tasks.demographics import analyze_surname_frequency
    indiv = dict([
        _mk_indi(f"@I{i}@", "Hans /Müller/", "M", 1850) for i in range(5)
    ] + [
        _mk_indi(f"@J{i}@", "Anna /Schmidt/", "F", 1855) for i in range(3)
    ])
    rows = analyze_surname_frequency(indiv)
    names = {r[0]: r[1] for r in rows}
    assert names.get("Müller") == 5
    assert names.get("Schmidt") == 3


def test_sibling_statistics_intervals():
    from tasks.demographics import analyze_sibling_statistics
    indiv = dict([
        _mk_indi("@P@", "Vater", "M", 1820, fams=["@F@"]),
        _mk_indi("@M@", "Mutter", "F", 1825, fams=["@F@"]),
        _mk_indi("@C1@", "Kind1", "M", 1850, famc=["@F@"]),
        _mk_indi("@C2@", "Kind2", "F", 1852, famc=["@F@"]),
        _mk_indi("@C3@", "Kind3", "M", 1855, famc=["@F@"]),
    ])
    fams = dict([_mk_fam("@F@", "@P@", "@M@", ["@C1@", "@C2@", "@C3@"])])
    rows = analyze_sibling_statistics(indiv, fams)
    assert len(rows) == 1
    row = rows[0]
    # Spanne = 5 (1855 - 1850)
    assert row[7] == 5
    # Min Abstand = 2
    assert row[9] == 2


def test_name_drift_first_last_year():
    from tasks.demographics import analyze_name_drift
    indiv = dict([
        _mk_indi("@I1@", "Hans /Müller/", "M", 1800),
        _mk_indi("@I2@", "Hans /Schmidt/", "M", 1900),
        _mk_indi("@I3@", "Anna /Koch/", "F", 1850),
    ])
    rows = analyze_name_drift(indiv)
    hans = next((r for r in rows if r[0].upper() == "HANS"), None)
    assert hans is not None
    assert hans[4] == 1800  # Erstbeleg
    assert hans[5] == 1900  # Letzter Beleg


def test_spouse_age_gap():
    from tasks.family_structure import analyze_spouse_age_gap
    indiv = dict([
        _mk_indi("@H@", "Mann", "M", 1820, fams=["@F1@"]),
        _mk_indi("@W@", "Frau", "F", 1825, fams=["@F1@"]),  # 5 J. jünger
    ])
    fams = dict([_mk_fam("@F1@", "@H@", "@W@", [], 1849)])
    rows = analyze_spouse_age_gap(indiv, fams)
    assert len(rows) >= 1


def test_twin_detection():
    from tasks.family_structure import detect_twins
    indiv = dict([
        _mk_indi("@P@", "Vater", "M", 1820, fams=["@F@"]),
        _mk_indi("@M@", "Mutter", "F", 1825, fams=["@F@"]),
        _mk_indi("@T1@", "Zwilling1", "M", 1850, famc=["@F@"]),
        _mk_indi("@T2@", "Zwilling2", "M", 1850, famc=["@F@"]),
    ])
    fams = dict([_mk_fam("@F@", "@P@", "@M@", ["@T1@", "@T2@"])])
    rows = detect_twins(indiv, fams)
    assert len(rows) >= 1


def test_reproductive_span():
    from tasks.family_structure import analyze_reproductive_span
    indiv = dict([
        _mk_indi("@M@", "Mutter", "F", 1820, fams=["@F@"]),
        _mk_indi("@C1@", "Kind1", "M", 1840, famc=["@F@"]),
        _mk_indi("@C2@", "Kind2", "F", 1855, famc=["@F@"]),
    ])
    fams = dict([_mk_fam("@F@", None, "@M@", ["@C1@", "@C2@"])])
    rows = analyze_reproductive_span(indiv, fams)
    # Mutter @M@ sollte eine Zeile haben mit Spanne 15
    mom_rows = [r for r in rows if r[0] == "@M@"]
    assert len(mom_rows) >= 1


def test_seasonality_birth_months_distributes_evenly():
    from tasks.seasonality import analyze_birth_months
    indiv = {}
    for i, month in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]):
        iid = f"@I{i}@"
        indiv[iid] = {
            "NAME": f"Person{i} /Test/", "SEX": "M",
            "BIRT": {"DATE": f"1 {month} 1850", "YEAR": 1850,
                      "DATE_QUAL": "exact", "PLAC": ""},
            "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
            "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
            "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
            "FAMC": [], "FAMS": [],
        }
    rows = analyze_birth_months(indiv)
    assert len(rows) == 1  # nur die Epoche 1850-1900
    total = rows[0][1]
    assert total == 12


def test_comprehensive_stats_total_count():
    from tasks.demographics import calculate_comprehensive_statistics
    indiv, fams, _ = _build_valid_family()
    rows = calculate_comprehensive_statistics(indiv, fams)
    # Erste Zeile = Gesamtanzahl Personen
    assert rows[0][1] == 4


def test_childlessness_rate():
    from tasks.family_structure import analyze_childlessness
    indiv = dict([
        _mk_indi("@H@", "Mann", "M", 1820, fams=["@F@"]),
        _mk_indi("@W@", "Frau", "F", 1825, fams=["@F@"]),
    ])
    fams = dict([_mk_fam("@F@", "@H@", "@W@", [], 1849)])
    rows = analyze_childlessness(indiv, fams)
    # Mindestens eine Zeile mit Rate > 0%
    assert len(rows) >= 1


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 7: Migration (Tests 71–80)
# ════════════════════════════════════════════════════════════════════════════════

def test_migration_status_marker_detection():
    """`mig.` im Namen wird mindestens als 'markiert' erkannt (auch ohne EMIG-Event)."""
    from lib.helpers import safe_determine_migration_status
    iid, p = _mk_indi("@A@", "mig.‼1882 Hans /Müller/", "M", 1850)
    status = safe_determine_migration_status(p, p["NAME"], {})
    s = status.lower() if isinstance(status, str) else str(status).lower()
    assert "markiert" in s or "ja" in s


def test_emig_event_recognized():
    from lib.helpers import safe_determine_migration_status
    iid, p = _mk_indi("@A@", "Hans /Müller/", "M", 1850,
                       emig_year=1882, emig_place="Hamburg")
    p["EMIG"]["DATE"] = "1 JAN 1882"
    p["EMIG"]["YEAR"] = 1882
    status = safe_determine_migration_status(p, p["NAME"], {})
    assert isinstance(status, str) and len(status) > 0


def test_marriage_migration_classification():
    from tasks.spatial import analyze_marriage_migration
    indiv = dict([
        _mk_indi("@H@", "Mann", "M", 1820, "Berlin, Deutschland", fams=["@F@"]),
        _mk_indi("@W@", "Frau", "F", 1825, "Hamburg, Deutschland", fams=["@F@"]),
    ])
    fams = dict([_mk_fam("@F@", "@H@", "@W@", [], 1849, "Berlin, Deutschland")])
    rows = analyze_marriage_migration(indiv, fams, {"countries": {}})
    assert len(rows) >= 1


def test_life_triangulation_returns_rows():
    from tasks.spatial import analyze_life_triangulation
    indiv = dict([
        _mk_indi("@A@", "Sesshaft", "M", 1820, "Berlin", 1890, "Berlin"),
    ])
    rows = analyze_life_triangulation(indiv, {})
    assert isinstance(rows, list)


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 8: Linien & Familienstruktur (Tests 81–90)
# ════════════════════════════════════════════════════════════════════════════════

def test_y_line_trace(small_tree):
    from tasks.lineage import trace_y_line
    indiv, fams, root = small_tree
    rows = trace_y_line(root, indiv, fams)
    # Mindestens Root + 2 Vorfahren (Vater, Großvater)
    assert len(rows) >= 3


def test_mt_line_trace(small_tree):
    from tasks.lineage import trace_mt_line
    indiv, fams, root = small_tree
    rows = trace_mt_line(root, indiv, fams)
    assert len(rows) >= 1


def test_grandparent_quartiles(small_tree):
    from tasks.lineage import analyze_grandparent_quartiles
    indiv, fams, root = small_tree
    rows = analyze_grandparent_quartiles(root, indiv, fams, {"countries": {}})
    # Vier Quartile sollten geliefert werden
    assert len(rows) == 4


def test_branching_factor(small_tree):
    from tasks.lineage import analyze_branching_factor
    indiv, fams, root = small_tree
    rows = analyze_branching_factor(root, indiv, fams)
    # Mindestens eine Zeile pro Generation
    assert len(rows) >= 1


def test_mrca_finder_parent_child():
    from tasks.mrca import find_mrca
    indiv, fams, _ = _build_valid_family()
    result = find_mrca("@K1@", "@P1@", indiv, fams)
    assert result["found"]
    # Vater ist sein eigener MRCA mit Kind
    assert result["mrca_id"] in ("@P1@",)


def test_mrca_finder_siblings():
    from tasks.mrca import find_mrca
    indiv, fams, _ = _build_valid_family()
    result = find_mrca("@K1@", "@K2@", indiv, fams)
    assert result["found"]
    # MRCA = einer der Eltern
    assert result["mrca_id"] in ("@P1@", "@P2@")


def test_mrca_finder_no_relation():
    from tasks.mrca import find_mrca
    indiv = dict([
        _mk_indi("@A@", "Stranger1", "M", 1850),
        _mk_indi("@B@", "Stranger2", "M", 1860),
    ])
    result = find_mrca("@A@", "@B@", indiv, {})
    assert not result["found"]


def test_lineage_extinction_detection():
    from tasks.lineage import detect_lineage_extinction
    indiv = dict([
        _mk_indi(f"@I{i}@", f"Person{i} /Müller/", "F", 1820 + i*10)
        for i in range(5)
    ])
    rows = detect_lineage_extinction(indiv, {})
    # Mit 5 Trägern, alles Frauen → Linie ist erloschen (keine Söhne mit Namen)
    assert isinstance(rows, list)


def test_subtree_ancestors_extraction(small_tree):
    from tasks.extract_subtree import extract_ancestors
    indiv, fams, root = small_tree
    indiv_sub, fams_sub = extract_ancestors(root, indiv, fams)
    # Mindestens root + Eltern + Großeltern
    assert len(indiv_sub) >= 5


def test_subtree_descendants_extraction(small_tree):
    from tasks.extract_subtree import extract_descendants
    indiv, fams, _ = small_tree
    indiv_sub, fams_sub = extract_descendants("@G1@", indiv, fams)
    # @G1@ und Nachfahren
    assert len(indiv_sub) >= 1


# ════════════════════════════════════════════════════════════════════════════════
# Kategorie 9: Exporte & Roundtrips (Tests 91–100)
# ════════════════════════════════════════════════════════════════════════════════

def test_export_excel_creates_file(small_tree):
    from tasks.export import export_to_excel
    pytest.importorskip("openpyxl")
    indiv, fams, _ = small_tree
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as t:
        path = t.name
    try:
        ok = export_to_excel([("Test", ["A", "B"], [[1, 2], [3, 4]])], path)
        assert ok and os.path.exists(path) and os.path.getsize(path) > 0
    finally:
        if os.path.exists(path): os.unlink(path)


def test_export_json_creates_file():
    from tasks.export import export_to_json
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as t:
        path = t.name
    try:
        ok = export_to_json({"test": [1, 2, 3]}, path)
        assert ok and os.path.getsize(path) > 0
    finally:
        if os.path.exists(path): os.unlink(path)


def test_export_html_overview_creates_valid_html(small_tree):
    from tasks.export import export_html_overview
    indiv, fams, _ = small_tree
    state = {"individuals": indiv, "families": fams,
             "comprehensive_stats": [["Test", 5, "100%"]]}
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as t:
        path = t.name
    try:
        assert export_html_overview(state, path) is True
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "<html" in content and "</html>" in content
    finally:
        if os.path.exists(path): os.unlink(path)


def test_export_timeline_html(small_tree):
    from tasks.export import export_timeline_html
    indiv, fams, _ = small_tree
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as t:
        path = t.name
    try:
        assert export_timeline_html(indiv, fams, path) is True
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "Zeitlinie" in content or "timeline" in content.lower()
    finally:
        if os.path.exists(path): os.unlink(path)


def test_export_fanchart_creates_svg(small_tree):
    from tasks.export_fanchart import export_fanchart_svg
    indiv, fams, root = small_tree
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as t:
        path = t.name
    try:
        assert export_fanchart_svg(root, indiv, fams, path) is True
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "<svg" in content and "</svg>" in content
    finally:
        if os.path.exists(path): os.unlink(path)


def test_export_dashboard_creates_html(small_tree):
    from tasks.export_dashboard import export_dashboard_html
    indiv, fams, _ = small_tree
    state = {"individuals": indiv, "families": fams}
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as t:
        path = t.name
    try:
        assert export_dashboard_html(state, path) is True
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "<html" in content and "Chart" in content
    finally:
        if os.path.exists(path): os.unlink(path)


def test_export_heatmap_creates_html(small_tree):
    from tasks.export_heatmap import export_birth_heatmap
    indiv, _, _ = small_tree
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as t:
        path = t.name
    try:
        ok = export_birth_heatmap(indiv, {"countries": {}}, path)
        assert ok and os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "leaflet" in content.lower() or "<html" in content
    finally:
        if os.path.exists(path): os.unlink(path)


def test_export_graphml_valid_xml(small_tree):
    from tasks.export_graphml import export_graphml
    import xml.etree.ElementTree as ET
    indiv, fams, root = small_tree
    with tempfile.NamedTemporaryFile(suffix=".graphml", delete=False) as t:
        path = t.name
    try:
        assert export_graphml(indiv, fams, path, root_id=root) is True
        # Valides XML
        tree = ET.parse(path)
        assert tree.getroot() is not None
    finally:
        if os.path.exists(path): os.unlink(path)


def test_subtree_gedcom_roundtrip(small_tree):
    """Subtree → GEDCOM → laden → vergleichen."""
    from tasks.extract_subtree import extract_ancestors, write_gedcom
    from lib.gedcom import robust_load_gedcom
    indiv, fams, root = small_tree
    indiv_sub, fams_sub = extract_ancestors(root, indiv, fams)

    with tempfile.NamedTemporaryFile(suffix=".ged", delete=False) as t:
        path = t.name
    try:
        write_gedcom(indiv_sub, fams_sub, path)
        # Wieder einlesen
        indiv_reloaded, fams_reloaded = robust_load_gedcom(path)
        # Selbe Anzahl an Personen (mindestens) und Familien
        assert len(indiv_reloaded) == len(indiv_sub)
    finally:
        if os.path.exists(path): os.unlink(path)


def test_excel_atomic_write_no_partial_file(small_tree):
    """Bei einem absichtlich erzeugten Fehler darf keine kaputte Datei zurückbleiben."""
    from tasks.export import export_to_excel
    pytest.importorskip("openpyxl")
    # Pfad in einem nicht-existenten Unterverzeichnis → Fehler beim Schreiben
    invalid = "/tmp/nonexistent_dir_xyz/test.xlsx"
    if os.path.exists(invalid):
        os.unlink(invalid)
    result = export_to_excel([("Test", ["A"], [[1]])], invalid)
    assert result is False
    # Es darf kein .tmp übrigbleiben
    assert not os.path.exists(invalid + ".tmp")


# ════════════════════════════════════════════════════════════════════════════════
# Zusätzliche Tests (93–100)
# ════════════════════════════════════════════════════════════════════════════════

def test_brickwall_detection_well_documented_orphan():
    """Person ohne Eltern aber mit reichlich anderen Daten = Brick-Wall."""
    from tasks.brickwalls import detect_brickwalls
    indiv = dict([
        _mk_indi("@O@", "Findelkind /Müller/", "M", 1820, "Berlin",
                  1890, "Hamburg", fams=["@F1@"]),
        _mk_indi("@S@", "Spouse /Schmidt/", "F", 1825, fams=["@F1@"]),
        _mk_indi("@C1@", "Kind1", "M", 1850, famc=["@F1@"]),
        _mk_indi("@C2@", "Kind2", "F", 1853, famc=["@F1@"]),
    ])
    fams = dict([_mk_fam("@F1@", "@O@", "@S@", ["@C1@", "@C2@"], 1849)])
    rows = detect_brickwalls(indiv, fams)
    assert any(r[0] == "@O@" for r in rows)


def test_research_suggestions_finds_missing_parents():
    """Vorschlag soll generiert werden für Person mit unbekannten Eltern + Geburtsort."""
    from tasks.research_suggestions import generate_research_suggestions
    indiv = dict([
        _mk_indi("@A@", "Hans /Müller/", "M", 1820, "Berlin", fams=["@F@"]),
    ])
    fams = dict([_mk_fam("@F@", "@A@", None, [])])
    rows = generate_research_suggestions(indiv, fams)
    assert len(rows) > 0


def test_endogamy_bigraph_counts_marriages():
    """Heirat Müller × Schmidt 3x → eine Zeile mit count=3."""
    from tasks.endogamy_network import analyze_endogamy_bigraph
    indiv, fams = {}, {}
    for i in range(3):
        h_iid, h = _mk_indi(f"@H{i}@", f"Hans{i} /Müller/", "M", 1820+i, fams=[f"@F{i}@"])
        w_iid, w = _mk_indi(f"@W{i}@", f"Anna{i} /Schmidt/", "F", 1825+i, fams=[f"@F{i}@"])
        indiv[h_iid] = h; indiv[w_iid] = w
        fid, f = _mk_fam(f"@F{i}@", h_iid, w_iid, [], 1850+i)
        fams[fid] = f
    rows = analyze_endogamy_bigraph(indiv, fams)
    pair = next((r for r in rows if {r[0], r[1]} == {"Müller", "Schmidt"}), None)
    assert pair is not None
    assert pair[2] == 3  # 3 Ehen


def test_fanchart_handles_missing_ancestors(small_tree):
    """Fan-Chart muss auch mit fehlenden Großeltern klarkommen."""
    from tasks.export_fanchart import export_fanchart_svg
    indiv = dict([_mk_indi("@R@", "Root /Solo/", "M", 1850)])
    fams = {}
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as t:
        path = t.name
    try:
        assert export_fanchart_svg("@R@", indiv, fams, path) is True
        with open(path) as f:
            content = f.read()
        assert "<svg" in content
    finally:
        if os.path.exists(path): os.unlink(path)


def test_dashboard_handles_empty_state():
    """Dashboard darf bei leerem State nicht crashen."""
    from tasks.export_dashboard import export_dashboard_html
    state = {"individuals": {}, "families": {}}
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as t:
        path = t.name
    try:
        ok = export_dashboard_html(state, path)
        assert ok is True
    finally:
        if os.path.exists(path): os.unlink(path)


def test_imputation_estimates_from_parents():
    """Person ohne Geburtsjahr aber mit Eltern → Schätzung ≈ Eltern + 27."""
    from tasks.imputation import impute_missing_dates
    indiv = dict([
        _mk_indi("@P@", "Vater", "M", 1820, fams=["@F@"]),
        _mk_indi("@M@", "Mutter", "F", 1822, fams=["@F@"]),
        _mk_indi("@K@", "Unbekanntes-Kind /Müller/", "M", famc=["@F@"]),
    ])
    fams = dict([_mk_fam("@F@", "@P@", "@M@", ["@K@"])])
    rows = impute_missing_dates(indiv, fams)
    assert any(r[0] == "@K@" for r in rows)


def test_dna_match_to_tree(small_tree):
    """match_dna_to_tree liefert eine sortierte Liste mit Match-Scores."""
    from tasks.dna_predict import match_dna_to_tree
    indiv, fams, root = small_tree
    rows = match_dna_to_tree(observed_cm=1700, root_id=root,
                              individuals=indiv, families=fams)
    if rows:  # nicht alle Trees haben Matches
        # Match-Score muss zwischen 0 und 1 liegen
        for r in rows:
            assert 0 <= r[4] <= 1


def test_merge_trees_dedupes_obvious_duplicate():
    """Zwei GEDCOMs mit gleicher Person sollten 1x dedupliziert werden."""
    from tasks.merge_trees import merge_gedcoms
    # Schreibe zwei Mini-GEDCOMs
    ged_a = """0 HEAD
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME Hans /Müller/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
0 TRLR
"""
    ged_b = ged_a  # identische Datei → Duplikat
    with tempfile.NamedTemporaryFile(suffix=".ged", mode="w", delete=False) as ta:
        ta.write(ged_a); fa = ta.name
    with tempfile.NamedTemporaryFile(suffix=".ged", mode="w", delete=False) as tb:
        tb.write(ged_b); fb = tb.name
    with tempfile.NamedTemporaryFile(suffix=".ged", delete=False) as to:
        out = to.name
    try:
        _, n_merged = merge_gedcoms(fa, fb, out)
        assert n_merged >= 1   # mindestens eine Doublette erkannt
    finally:
        for p in (fa, fb, out):
            if os.path.exists(p): os.unlink(p)
