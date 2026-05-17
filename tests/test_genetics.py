"""Tests für tasks.genetics – Wright's F."""
from tasks.genetics import (compute_inbreeding_coefficient,
                              clear_genetics_cache, _F_CACHE)


def test_F_unrelated_parents_is_zero():
    indi = {"F": {}, "M": {}, "C": {"FAMC": ["x"]}}
    fams = {"x": {"HUSB": "F", "WIFE": "M"}}
    clear_genetics_cache()
    assert compute_inbreeding_coefficient("C", indi, fams) == 0.0


def test_F_full_siblings_quarter():
    # Lehrbuchfall: Kind aus Geschwisterehe → F = 0.25
    indi = {
        "GP1": {}, "GP2": {},
        "F": {"FAMC": ["fGP"]},
        "M": {"FAMC": ["fGP"]},
        "C": {"FAMC": ["fFM"]},
    }
    fams = {
        "fGP": {"HUSB": "GP1", "WIFE": "GP2", "CHIL": ["F", "M"]},
        "fFM": {"HUSB": "F",   "WIFE": "M",   "CHIL": ["C"]},
    }
    clear_genetics_cache()
    F = compute_inbreeding_coefficient("C", indi, fams)
    assert abs(F - 0.25) < 1e-6


def test_F_first_cousins_one_sixteenth():
    # 1st-Cousin-Ehe: F = 1/16 = 0.0625
    indi = {
        "GP1": {}, "GP2": {},
        "U1": {"FAMC": ["fGP"]},   # Onkel
        "U2": {"FAMC": ["fGP"]},   # Tante
        "S1": {},                  # unverwandter Partner von U1
        "S2": {},                  # unverwandter Partner von U2
        "F":  {"FAMC": ["fU1S1"]}, # Vater (Cousin)
        "M":  {"FAMC": ["fU2S2"]}, # Mutter (Cousine)
        "C":  {"FAMC": ["fFM"]},
    }
    fams = {
        "fGP":  {"HUSB": "GP1", "WIFE": "GP2", "CHIL": ["U1", "U2"]},
        "fU1S1":{"HUSB": "U1",  "WIFE": "S1",  "CHIL": ["F"]},
        "fU2S2":{"HUSB": "S2",  "WIFE": "U2",  "CHIL": ["M"]},
        "fFM":  {"HUSB": "F",   "WIFE": "M",   "CHIL": ["C"]},
    }
    clear_genetics_cache()
    F = compute_inbreeding_coefficient("C", indi, fams)
    assert abs(F - 0.0625) < 1e-6


def test_F_cached():
    indi = {"F": {}, "M": {}, "C": {"FAMC": ["x"]}}
    fams = {"x": {"HUSB": "F", "WIFE": "M"}}
    clear_genetics_cache()
    compute_inbreeding_coefficient("C", indi, fams)
    assert "C" in _F_CACHE
