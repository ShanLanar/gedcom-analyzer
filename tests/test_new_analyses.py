"""Tests für die neuen Analysemodule: anomalies, demographics (sibling/namedrift), genetics (cM)."""
import pytest
from tasks.anomalies import detect_anomalies, detect_duplicates, detect_islands
from tasks.demographics import analyze_sibling_statistics, analyze_name_drift
from tasks.genetics import _kinship_coefficient, analyze_dna_cm_estimates, clear_genetics_cache


# ── Fixtures ────────────────────────────────────────────────────────────────────

def _make_tree():
    """Kleiner Stammbaum für Tests: Root → Eltern → Großeltern."""
    individuals = {
        "@I1@": {"NAME": "Hans /Müller/", "SEX": "M",
                 "BIRT": {"DATE": "1 JAN 1850", "YEAR": 1850, "DATE_QUAL": "exact", "PLAC": "Berlin"},
                 "DEAT": {"DATE": "1 JAN 1920", "YEAR": 1920, "DATE_QUAL": "exact", "PLAC": ""},
                 "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "FAMC": ["@F1@"], "FAMS": ["@F2@"],
                 "MIGRATED": False, "VETERAN": False, "DIED_IN_BATTLE": False,
                 "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False},
        "@I2@": {"NAME": "Anna /Schmidt/", "SEX": "F",
                 "BIRT": {"DATE": "1 MAY 1855", "YEAR": 1855, "DATE_QUAL": "exact", "PLAC": "Berlin"},
                 "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "FAMC": ["@F1@"], "FAMS": ["@F2@"],
                 "MIGRATED": False, "VETERAN": False, "DIED_IN_BATTLE": False,
                 "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False},
        "@I3@": {"NAME": "Fritz /Müller/", "SEX": "M",
                 "BIRT": {"DATE": "1 JAN 1820", "YEAR": 1820, "DATE_QUAL": "exact", "PLAC": "Leipzig"},
                 "DEAT": {"DATE": "1 JAN 1880", "YEAR": 1880, "DATE_QUAL": "exact", "PLAC": ""},
                 "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "FAMC": [], "FAMS": ["@F1@"],
                 "MIGRATED": False, "VETERAN": False, "DIED_IN_BATTLE": False,
                 "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False},
        "@I4@": {"NAME": "Maria /Koch/", "SEX": "F",
                 "BIRT": {"DATE": "1 JAN 1825", "YEAR": 1825, "DATE_QUAL": "exact", "PLAC": "Leipzig"},
                 "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                 "FAMC": [], "FAMS": ["@F1@"],
                 "MIGRATED": False, "VETERAN": False, "DIED_IN_BATTLE": False,
                 "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False},
        # Insel-Person: nicht mit dem Baum verbunden
        "@I99@": {"NAME": "Insel /Person/", "SEX": "U",
                  "BIRT": {"DATE": "1 JAN 1900", "YEAR": 1900, "DATE_QUAL": "exact", "PLAC": ""},
                  "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                  "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                  "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                  "FAMC": [], "FAMS": [],
                  "MIGRATED": False, "VETERAN": False, "DIED_IN_BATTLE": False,
                  "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False},
    }
    families = {
        "@F1@": {"HUSB": "@I3@", "WIFE": "@I4@", "CHIL": ["@I1@", "@I2@"],
                 "MARR_DATE": "1845", "MARR_PLACE": "Leipzig"},
        "@F2@": {"HUSB": "@I1@", "WIFE": "@I2@", "CHIL": [],
                 "MARR_DATE": "1875", "MARR_PLACE": "Berlin"},
    }
    return individuals, families


# ── detect_anomalies ────────────────────────────────────────────────────────────

def test_detect_anomalies_no_errors_in_valid_tree():
    indiv, fams = _make_tree()
    rows = detect_anomalies(indiv, fams)
    # Kein KRITISCH in diesem normalen Baum
    kritisch = [r for r in rows if r[4] == "KRITISCH"]
    assert len(kritisch) == 0


def test_detect_anomalies_birth_after_death():
    indiv, fams = _make_tree()
    # DEAT vor BIRT (1820) setzen — DATE ist der primäre Wert
    indiv["@I3@"]["DEAT"]["DATE"] = "1 JAN 1810"
    indiv["@I3@"]["DEAT"]["YEAR"] = 1810
    rows = detect_anomalies(indiv, fams)
    types = [r[3] for r in rows if r[0] == "@I3@"]
    assert "Geburt nach Tod" in types


def test_detect_anomalies_future_birth():
    indiv, fams = _make_tree()
    indiv["@I99@"]["BIRT"]["DATE"] = "1 JAN 2099"
    indiv["@I99@"]["BIRT"]["YEAR"] = 2099
    rows = detect_anomalies(indiv, fams)
    types = [r[3] for r in rows if r[0] == "@I99@"]
    assert "Geburtsjahr in der Zukunft" in types


def test_detect_anomalies_mother_too_young():
    indiv, fams = _make_tree()
    # Kind 1850 geboren, Mutter 1848 → Alter 2 Jahre
    indiv["@I4@"]["BIRT"]["DATE"] = "1 JAN 1848"
    indiv["@I4@"]["BIRT"]["YEAR"] = 1848
    rows = detect_anomalies(indiv, fams)
    child_anomalies = [r for r in rows if "Mutter" in r[3]]
    assert len(child_anomalies) > 0


def test_detect_anomalies_severity_order():
    indiv, fams = _make_tree()
    indiv["@I3@"]["DEAT"]["YEAR"] = 1810  # KRITISCH
    rows = detect_anomalies(indiv, fams)
    if len(rows) >= 2:
        # KRITISCH soll vor WARNUNG kommen
        severities = [r[4] for r in rows]
        _order = {"KRITISCH": 0, "WARNUNG": 1, "HINWEIS": 2}
        for i in range(len(severities) - 1):
            assert _order[severities[i]] <= _order[severities[i + 1]]


# ── detect_duplicates ───────────────────────────────────────────────────────────

def test_detect_duplicates_finds_obvious_pair():
    indiv = {
        "@I1@": {"NAME": "Hans /Müller/",
                 "BIRT": {"DATE": "1 JAN 1850", "YEAR": 1850, "DATE_QUAL": "exact", "PLAC": ""}},
        "@I2@": {"NAME": "Hans /Müller/",  # exakte Kopie
                 "BIRT": {"DATE": "1 JAN 1850", "YEAR": 1850, "DATE_QUAL": "exact", "PLAC": ""}},
        "@I3@": {"NAME": "Fritz /Müller/",  # anderer Vorname
                 "BIRT": {"DATE": "1 JAN 1850", "YEAR": 1850, "DATE_QUAL": "exact", "PLAC": ""}},
    }
    rows = detect_duplicates(indiv)
    # Exaktes Paar muss gefunden werden
    ids_found = {(r[0], r[2]) for r in rows} | {(r[2], r[0]) for r in rows}
    assert ("@I1@", "@I2@") in ids_found or ("@I2@", "@I1@") in ids_found


def test_detect_duplicates_no_false_positives_unrelated():
    indiv = {
        "@I1@": {"NAME": "Hans /Müller/",
                 "BIRT": {"DATE": "1 JAN 1850", "YEAR": 1850, "DATE_QUAL": "exact", "PLAC": ""}},
        "@I2@": {"NAME": "Josef /Schmidt/",  # komplett anderer Name
                 "BIRT": {"DATE": "1 JAN 1750", "YEAR": 1750, "DATE_QUAL": "exact", "PLAC": ""}},
    }
    rows = detect_duplicates(indiv)
    assert len(rows) == 0


# ── detect_islands ──────────────────────────────────────────────────────────────

def test_detect_islands_finds_disconnected():
    indiv, fams = _make_tree()
    rows = detect_islands("@I1@", indiv, fams)
    island_ids = {r[0] for r in rows}
    assert "@I99@" in island_ids
    # Verbundene Personen dürfen NICHT in der Liste sein
    assert "@I1@" not in island_ids
    assert "@I3@" not in island_ids


def test_detect_islands_empty_when_all_connected():
    indiv = {
        "@I1@": {"NAME": "A", "FAMC": [], "FAMS": ["@F1@"],
                 "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None}},
        "@I2@": {"NAME": "B", "FAMC": ["@F1@"], "FAMS": [],
                 "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None}},
    }
    fams = {"@F1@": {"HUSB": "@I1@", "WIFE": None, "CHIL": ["@I2@"],
                     "MARR_DATE": None, "MARR_PLACE": None}}
    rows = detect_islands("@I1@", indiv, fams)
    assert len(rows) == 0


# ── analyze_sibling_statistics ──────────────────────────────────────────────────

def test_sibling_statistics_basic():
    indiv, fams = _make_tree()
    # F1 hat 2 Kinder: @I1@ (1850) und @I2@ (1855)
    rows = analyze_sibling_statistics(indiv, fams)
    assert len(rows) >= 1
    row = next(r for r in rows if r[0] == "@F1@")
    # Spanne = 1855 - 1850 = 5
    assert row[7] == 5  # Spanne (J.)


def test_sibling_statistics_skips_single_child():
    indiv, fams = _make_tree()
    fams["@F1@"]["CHIL"] = ["@I1@"]  # nur ein Kind
    rows = analyze_sibling_statistics(indiv, fams)
    f1_rows = [r for r in rows if r[0] == "@F1@"]
    assert len(f1_rows) == 0  # Keine Zeile für Einzelkind


# ── analyze_name_drift ──────────────────────────────────────────────────────────

def test_name_drift_basic():
    indiv, _ = _make_tree()
    rows = analyze_name_drift(indiv)
    names = [r[0] for r in rows]
    assert "Hans" in names or "HANS" in names


def test_name_drift_counts_correctly():
    indiv = {
        "@I1@": {"NAME": "Hans /Müller/", "SEX": "M",
                 "BIRT": {"DATE": "1850", "YEAR": 1850, "DATE_QUAL": "exact", "PLAC": ""}},
        "@I2@": {"NAME": "Hans /Schmidt/", "SEX": "M",
                 "BIRT": {"DATE": "1860", "YEAR": 1860, "DATE_QUAL": "exact", "PLAC": ""}},
        "@I3@": {"NAME": "Anna /Müller/", "SEX": "F",
                 "BIRT": {"DATE": "1855", "YEAR": 1855, "DATE_QUAL": "exact", "PLAC": ""}},
    }
    rows = analyze_name_drift(indiv)
    hans = next((r for r in rows if r[0].upper() == "HANS"), None)
    assert hans is not None
    assert hans[1] == 2   # Gesamt-Count
    assert hans[2] == 2   # Männer


# ── _kinship_coefficient ────────────────────────────────────────────────────────

def _minimal_tree():
    """Vater @P@, Mutter @M@, Kind @C@."""
    clear_genetics_cache()
    indiv = {
        "@P@": {"NAME": "Vater", "SEX": "M",
                "FAMC": [], "FAMS": ["@F1@"],
                "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None}},
        "@M@": {"NAME": "Mutter", "SEX": "F",
                "FAMC": [], "FAMS": ["@F1@"],
                "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None}},
        "@C@": {"NAME": "Kind", "SEX": "M",
                "FAMC": ["@F1@"], "FAMS": [],
                "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None}},
    }
    fams = {"@F1@": {"HUSB": "@P@", "WIFE": "@M@", "CHIL": ["@C@"],
                     "MARR_DATE": None, "MARR_PLACE": None}}
    return indiv, fams


def test_kinship_parent_child():
    indiv, fams = _minimal_tree()
    phi = _kinship_coefficient("@P@", "@C@", indiv, fams)
    assert abs(phi - 0.25) < 1e-9, f"Φ(parent, child) should be 0.25, got {phi}"


def test_kinship_full_siblings():
    indiv, fams = _minimal_tree()
    # Zweites Kind hinzufügen
    indiv["@C2@"] = {"NAME": "Kind2", "SEX": "F",
                     "FAMC": ["@F1@"], "FAMS": [],
                     "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                     "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None}}
    fams["@F1@"]["CHIL"].append("@C2@")
    phi = _kinship_coefficient("@C@", "@C2@", indiv, fams)
    assert abs(phi - 0.25) < 1e-9, f"Φ(full siblings) should be 0.25, got {phi}"


def test_kinship_unrelated_zero():
    indiv, fams = _minimal_tree()
    indiv["@X@"] = {"NAME": "Unrelated", "SEX": "M",
                    "FAMC": [], "FAMS": [],
                    "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                    "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None}}
    phi = _kinship_coefficient("@P@", "@X@", indiv, fams)
    assert phi == 0.0


def test_dna_cm_estimates_returns_list():
    indiv, fams = _minimal_tree()
    rows = analyze_dna_cm_estimates("@P@", indiv, fams)
    # Mutter hat Φ=0 zur Root (keine gemeinsamen Ahnen), Kind hat Φ=0.25
    assert any(r[0] == "@C@" for r in rows)
    child_row = next(r for r in rows if r[0] == "@C@")
    assert child_row[5] == pytest.approx(3500.0, abs=1.0)  # 0.25 * 2 * 7000
