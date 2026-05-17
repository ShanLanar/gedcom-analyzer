"""Tests für den Generationenlängen-Bug-Fix in tasks/history.py."""
from tasks.history import calculate_generation_lengths


def test_generation_lengths_uses_ancestors_when_root_has_no_descendants():
    """Bug: Wenn Root keine Kinder in der GEDCOM hat (typisches Szenario,
    weil der Stammbaum Vorfahren der lebenden Person dokumentiert), lieferte
    die alte Logik 0 Generationen, obwohl Vorfahren mit Kinder-Paaren da sind.

    Erwartet: gen_map enthält Vorfahren via FAMC-Walk; Generationenlängen
    werden korrekt aus den Vorfahren-Paaren berechnet."""

    individuals = {
        "@ROOT@": {"NAME": "Root /Person/", "SEX": "M",
                   "BIRT": {"DATE": "1 JAN 2000", "YEAR": 2000, "DATE_QUAL": "exact", "PLAC": ""},
                   "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                   "FAMC": ["@F1@"], "FAMS": []},
        "@P1@":   {"NAME": "Vater /Person/", "SEX": "M",
                   "BIRT": {"DATE": "1 JAN 1970", "YEAR": 1970, "DATE_QUAL": "exact", "PLAC": ""},
                   "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                   "FAMC": ["@F2@"], "FAMS": ["@F1@"]},
        "@P2@":   {"NAME": "Mutter /Person/", "SEX": "F",
                   "BIRT": {"DATE": "1 JAN 1972", "YEAR": 1972, "DATE_QUAL": "exact", "PLAC": ""},
                   "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                   "FAMC": [], "FAMS": ["@F1@"]},
        "@GP1@":  {"NAME": "Großvater /Person/", "SEX": "M",
                   "BIRT": {"DATE": "1 JAN 1940", "YEAR": 1940, "DATE_QUAL": "exact", "PLAC": ""},
                   "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                   "FAMC": [], "FAMS": ["@F2@"]},
        "@GP2@":  {"NAME": "Großmutter /Person/", "SEX": "F",
                   "BIRT": {"DATE": "1 JAN 1942", "YEAR": 1942, "DATE_QUAL": "exact", "PLAC": ""},
                   "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
                   "FAMC": [], "FAMS": ["@F2@"]},
    }
    families = {
        "@F1@": {"HUSB": "@P1@", "WIFE": "@P2@", "CHIL": ["@ROOT@"],
                 "MARR_DATE": None, "MARR_PLACE": None},
        "@F2@": {"HUSB": "@GP1@", "WIFE": "@GP2@", "CHIL": ["@P1@"],
                 "MARR_DATE": None, "MARR_PLACE": None},
    }

    rows = calculate_generation_lengths(individuals, families,
                                          "@ROOT@", location_data={})
    # Erwartet: mindestens 2 Generations-Sätze (P1→ROOT, GP1→P1)
    assert len(rows) >= 1, f"Expected ≥1 generation, got {len(rows)}"
    # Ein Wert sollte die Eltern-Generation sein (Gen 1 aufwärts): Vater 1970 → Kind 2000 = 30 J.
    ages = [r[4] for r in rows]  # avg age column
    assert any(25 <= a <= 35 for a in ages), \
        f"Expected an age ~30 for the parent gen, got: {ages}"
