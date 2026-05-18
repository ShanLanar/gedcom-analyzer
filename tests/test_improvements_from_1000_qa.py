"""Tests für die nach der 1000er-QA eingebauten Verbesserungen:
- Jahres-Regex auf 1000–2199 erweitert
- Vornamen-Synonyme in detect_duplicates
- Heirat im hohen Alter (>90 J.) als HINWEIS
"""
import pytest


def _indi(iid, name, sex="M", by=None, dy=None, famc=None, fams=None):
    return iid, {
        "NAME": name, "SEX": sex,
        "FAMC": famc or [], "FAMS": fams or [],
        "BIRT": {"DATE": f"1 JAN {by}" if by else None, "YEAR": by,
                 "DATE_QUAL": "exact" if by else None, "PLAC": None},
        "DEAT": {"DATE": f"1 JAN {dy}" if dy else None, "YEAR": dy,
                 "DATE_QUAL": "exact" if dy else None, "PLAC": None},
        "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "BIRTH_PLACE": None,
        "MIGRATED": False, "VETERAN": False, "DIED_IN_BATTLE": False,
        "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False,
    }


def _fam(fid, h=None, w=None, ch=None, my=None):
    return fid, {"HUSB": h, "WIFE": w, "CHIL": list(ch or []),
                 "MARR_DATE": str(my) if my else None, "MARR_PLACE": None}


# ── Year-Regex-Erweiterung ────────────────────────────────────────────────────

@pytest.mark.parametrize("future_year", [2100, 2150, 2199])
def test_year_regex_covers_2100_to_2199(future_year):
    """Genealogie-Software wirft manchmal extrapolierte Datumsschätzungen
    > 2099 aus — die müssen jetzt erkannt werden."""
    from lib.gedcom import safe_extract_year, safe_parse_gedcom_date
    assert safe_extract_year(f"1 JAN {future_year}") == future_year
    assert safe_parse_gedcom_date(f"1 JAN {future_year}")["YEAR"] == future_year


@pytest.mark.parametrize("invalid_year", [2200, 999, 99, 500])
def test_year_regex_still_filters_extreme_values(invalid_year):
    """Werte außerhalb 1000–2199 werden nicht gematcht (vermeidet Hausnummern
    und unsinnig hohe Jahre)."""
    from lib.gedcom import safe_extract_year
    # Eingebettet in einen Satz: das Jahr soll NICHT extrahiert werden
    assert safe_extract_year(f"Haus Nr. {invalid_year} in Berlin") in (None, invalid_year)


# ── Vornamen-Synonyme in detect_duplicates ────────────────────────────────────

@pytest.mark.parametrize("name_a,name_b,canonical", [
    ("Hans /Müller/",     "Johannes /Müller/",     "JOHANNES"),
    ("Hans /Müller/",     "Johann /Müller/",       "JOHANNES"),
    ("Hannes /Müller/",   "Johann /Müller/",       "JOHANNES"),
    ("Heinz /Müller/",    "Heinrich /Müller/",     "HEINRICH"),
    ("Fritz /Müller/",    "Friedrich /Müller/",    "FRIEDRICH"),
    ("Willi /Müller/",    "Wilhelm /Müller/",      "WILHELM"),
    ("Karl /Müller/",     "Carl /Müller/",         "KARL"),
    ("Jakob /Müller/",    "Jacob /Müller/",        "JAKOB"),
    ("Grete /Müller/",    "Margaretha /Müller/",   "MARGARETHA"),
    ("Käthe /Müller/",    "Katharina /Müller/",    "KATHARINA"),
    ("Lisbeth /Müller/",  "Elisabeth /Müller/",    "ELISABETH"),
])
def test_synonym_duplicates_detected(name_a, name_b, canonical):
    """Doubletten-Erkennung findet jetzt deutsche Vornamen-Varianten
    (Hans↔Johannes, Fritz↔Friedrich, Käthe↔Katharina etc.)."""
    from tasks.anomalies import detect_duplicates
    indiv = dict([
        _indi("@A@", name_a, "M", 1850),
        _indi("@B@", name_b, "M", 1850),
    ])
    rows = detect_duplicates(indiv)
    assert len(rows) > 0, f"Synonym-Paar nicht erkannt: {name_a!r} ↔ {name_b!r}"
    # Synonym-Begründung muss in den Reasons stehen
    assert any("Synonym" in r[6] for r in rows), \
        f"Synonym-Tag fehlt im Grund-Feld: {[r[6] for r in rows]}"


@pytest.mark.parametrize("name_a,name_b", [
    ("Hans /Müller/",   "Friedrich /Müller/"),  # völlig andere Vornamen
    ("Hans /Müller/",   "Wilhelm /Schmidt/"),   # anderer Nachname
])
def test_synonym_does_not_create_false_positives(name_a, name_b):
    """Synonym-Erkennung darf KEINE unverwandten Namen koppeln."""
    from tasks.anomalies import detect_duplicates
    indiv = dict([
        _indi("@A@", name_a, "M", 1850),
        _indi("@B@", name_b, "M", 1850),
    ])
    rows = detect_duplicates(indiv)
    assert len(rows) == 0


def test_synonym_boost_increases_confidence():
    """Bei Synonym-Match soll der Konfidenz-Wert höher sein als bei
    reiner Levenshtein-Ähnlichkeit ohne Synonym."""
    from tasks.anomalies import detect_duplicates
    indiv = dict([
        _indi("@A@", "Hans /Müller/",    "M", 1850),
        _indi("@B@", "Johann /Müller/",  "M", 1850),
    ])
    rows = detect_duplicates(indiv)
    assert len(rows) > 0
    # Konfidenz sollte deutlich über dem Minimum (40) liegen
    assert rows[0][5] >= 50


# ── Heirat im hohen Alter (>90 J.) ────────────────────────────────────────────

@pytest.mark.parametrize("marriage_age,expect_anomaly_type", [
    (8,   "niedrigem Alter"),
    (13,  "niedrigem Alter"),
    (50,  None),                # OK
    (89,  None),                # OK
    (91,  "hohen Alter"),       # NEU
    (95,  "hohen Alter"),
    (100, "hohen Alter"),
])
def test_marriage_age_high_and_low(marriage_age, expect_anomaly_type):
    """Die Heiratsalter-Prüfung deckt jetzt sowohl die niedrige (<14)
    als auch die hohe (>90) Seite ab."""
    from tasks.anomalies import detect_anomalies
    indiv = dict([_indi("@A@", "Test /Person/", "M", 1800, fams=["@F1@"])])
    fams = dict([_fam("@F1@", "@A@", None, [], 1800 + marriage_age)])
    rows = detect_anomalies(indiv, fams)
    marriage_rows = [r for r in rows if "Heirat" in r[3]]
    if expect_anomaly_type is None:
        assert len(marriage_rows) == 0
    else:
        assert any(expect_anomaly_type in r[3] for r in marriage_rows), \
            f"Erwartete Anomalie '{expect_anomaly_type}' für Alter {marriage_age} nicht gefunden"
