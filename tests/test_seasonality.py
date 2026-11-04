# -*- coding: utf-8 -*-
"""Tests für tasks/seasonality.py – Epochen-Trennung für die Sterbemonats-Analyse."""
from tasks.seasonality import (
    DEATH_EPOCHS, EPOCHS, _death_epoch, _epoch, analyze_death_months,
)


def _indi(iid, birth_year, death_year, death_month="JUN"):
    return iid, {
        "NAME": f"Person {iid}", "SEX": "M",
        "BIRT": {"DATE": f"1 JAN {birth_year}", "YEAR": birth_year,
                 "DATE_QUAL": "exact", "PLAC": ""},
        "DEAT": {"DATE": f"1 {death_month} {death_year}", "YEAR": death_year,
                 "DATE_QUAL": "exact", "PLAC": ""},
        "FAMC": [], "FAMS": [],
    }


def test_death_epochs_split_world_wars_out_of_1900_1950():
    """Scrum Sprint 8 (Historiker): die alte 'EPOCHS'-Bucket '1900-1950'
    mischte Vorkriegszeit, beide Weltkriege und die Weimarer Republik — für
    die Sterbemonats-Analyse (Kriegstote verzerren saisonale Muster) gibt es
    jetzt eigene Weltkriegs-Epochen."""
    assert _death_epoch(1916) == "1.Weltkrieg"
    assert _death_epoch(1942) == "2.Weltkrieg"
    assert _death_epoch(1916) != _death_epoch(1905)
    assert _death_epoch(1942) != _death_epoch(1930)


def test_birth_marriage_epochs_unchanged():
    """Die gröberen EPOCHS (Geburt/Heirat/Empfängnis) bleiben unverändert —
    nur die Sterbemonats-Analyse bekommt die feinere Aufteilung."""
    assert _epoch(1916) == "1900-1950"
    assert _epoch(1942) == "1900-1950"
    assert set(EPOCHS) == {"vor_1800", "1800-1850", "1850-1900",
                            "1900-1950", "nach_1950"}


def test_analyze_death_months_uses_death_epochs_not_generic_epochs():
    """analyze_death_months() muss die feineren DEATH_EPOCHS-Schlüssel in der
    Ausgabe verwenden, nicht die groben EPOCHS-Schlüssel."""
    individuals = dict(
        _indi(f"@I{i}@", 1880 + (i % 20), 1915 + (i % 3))
        for i in range(10)
    )
    rows = analyze_death_months(individuals)
    epochs_in_output = {r[1] for r in rows}
    assert epochs_in_output <= set(DEATH_EPOCHS)
    assert "1900-1950" not in epochs_in_output
    if epochs_in_output:
        assert epochs_in_output <= {"1.Weltkrieg"}
