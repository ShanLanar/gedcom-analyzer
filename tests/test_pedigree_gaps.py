"""Tests für die Pedigree-Lücken-Analyse (EPIC 3)."""
from ancestry.core.pedigree_gaps import (
    analyze_pedigree_gaps,
    slots_in_generation,
    summarize_match_gaps,
)


def test_slots():
    assert slots_in_generation(1) == 1
    assert slots_in_generation(2) == 2
    assert slots_in_generation(3) == 4
    assert slots_in_generation(5) == 16
    assert slots_in_generation(0) == 0


def test_empty():
    res = analyze_pedigree_gaps({})
    assert res["max_gen"] == 0
    assert res["per_gen"] == []
    assert res["first_gap_gen"] is None
    assert res["pct"] == 0.0


def test_full_through_gen3():
    # Gen2 = 2/2, Gen3 = 4/4 → lückenlos bis Gen 3
    res = analyze_pedigree_gaps({2: 2, 3: 4})
    assert res["max_gen"] == 3
    assert res["complete_through"] == 3
    assert res["first_gap_gen"] is None
    assert res["total_present"] == 6
    assert res["total_possible"] == 6
    assert res["pct"] == 100.0


def test_gap_at_gen4():
    # Gen2 voll, Gen3 voll, Gen4 = 3/8 → erste Lücke bei Gen 4
    res = analyze_pedigree_gaps({2: 2, 3: 4, 4: 3})
    assert res["complete_through"] == 3
    assert res["first_gap_gen"] == 4
    g4 = [p for p in res["per_gen"] if p["generation"] == 4][0]
    assert g4["present"] == 3 and g4["possible"] == 8 and g4["missing"] == 5
    assert g4["complete"] is False


def test_gap_at_gen2():
    # nur ein Elternteil bekannt → schon Gen 2 unvollständig
    res = analyze_pedigree_gaps({2: 1, 3: 2})
    assert res["complete_through"] == 1   # min_gen-1
    assert res["first_gap_gen"] == 2


def test_counts_capped_at_possible():
    # mehr Einträge als Plätze (Duplikate) → auf possible gekappt
    res = analyze_pedigree_gaps({2: 5})
    g2 = res["per_gen"][0]
    assert g2["present"] == 2 and g2["missing"] == 0


def test_string_inputs_and_invalid_ignored():
    res = analyze_pedigree_gaps({"2": "2", "3": "4", "x": "y", 5: 0})
    assert res["max_gen"] == 3
    assert res["complete_through"] == 3


def test_summarize_sorts_deepest_first():
    matches = [
        {"match_guid": "shallow", "display_name": "A", "shared_cm": 100,
         "generations": {2: 2}},
        {"match_guid": "deep", "display_name": "B", "shared_cm": 90,
         "generations": {2: 2, 3: 4, 4: 8}},
    ]
    rows = summarize_match_gaps(matches)
    assert rows[0]["match_guid"] == "deep"
    assert rows[0]["complete_through"] == 4
    assert rows[1]["match_guid"] == "shallow"
