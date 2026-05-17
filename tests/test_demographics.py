"""Tests für tasks.demographics – B2-Regression (Slot-Doppelzählung)."""
from tasks.demographics import analyze_demographic_statistics


def test_within_slot_dedupe_when_both_parents_same_slot():
    """Wenn beide Eltern in denselben (Geschlecht, Epoche)-Slot fallen
    (z.B. Sex=Unbekannt, beide 1850-1900 geboren), darf das Kind
    innerhalb dieses Slots nicht zweimal in total_children/child_mortality
    auftauchen."""
    indi = {
        "P1": {"SEX": "U", "BIRT": {"DATE": "1860"}, "FAMS": ["F1"]},
        "P2": {"SEX": "U", "BIRT": {"DATE": "1865"}, "FAMS": ["F1"]},
        "K1": {"SEX": "M", "BIRT": {"DATE": "1888"},
                "DEAT": {"DATE": "1890"}, "FAMC": ["F1"]},  # stirbt <5J.
        "K2": {"SEX": "F", "BIRT": {"DATE": "1890"},
                "DEAT": {"DATE": "1950"}, "FAMC": ["F1"]},
    }
    fams = {"F1": {"HUSB": "P1", "WIFE": "P2", "CHIL": ["K1", "K2"]}}
    rows = analyze_demographic_statistics(indi, fams, {})
    # Slot (1850-1900, Unbekannt) sollte total_children = 2 haben, nicht 4.
    target = [r for r in rows if r[0] == "1850-1900" and r[1] == "Unbekannt"]
    assert target, "Slot fehlt"
    _ep, _sex, count, _avg_ls, _ls_str, _avg_m, _avg_ch, _fr, child_mort, _rate, _parents, total_children = target[0]
    assert total_children == 2
    assert child_mort == 1


def test_different_slots_count_independently():
    """Eltern in verschiedenen (Sex, Epoche)-Slots: jeder Slot zählt
    die Kinder einmal — kein artifizielles Halbieren."""
    indi = {
        "P1": {"SEX": "M", "BIRT": {"DATE": "1860"}, "FAMS": ["F1"]},
        "P2": {"SEX": "F", "BIRT": {"DATE": "1865"}, "FAMS": ["F1"]},
        "K1": {"BIRT": {"DATE": "1888"}, "FAMC": ["F1"]},
    }
    fams = {"F1": {"HUSB": "P1", "WIFE": "P2", "CHIL": ["K1"]}}
    rows = analyze_demographic_statistics(indi, fams, {})
    m_row = next(r for r in rows if r[0] == "1850-1900" and r[1] == "Männlich")
    f_row = next(r for r in rows if r[0] == "1850-1900" and r[1] == "Weiblich")
    assert m_row[-1] == 1
    assert f_row[-1] == 1
