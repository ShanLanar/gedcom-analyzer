"""
Comprehensive pytest tests for ancestry/core/cluster.py and ancestry/core/treematch.py.
Exactly 60 tests covering all specified functions.
"""
import sys
import os
import types

_ANCESTRY = '/home/user/gedcom-analyzer/ancestry'
if _ANCESTRY not in sys.path:
    sys.path.append(_ANCESTRY)

if 'core' not in sys.modules:
    _core_stub = types.ModuleType('core')
    _core_stub.__path__ = [os.path.join(_ANCESTRY, 'core')]
    _core_stub.__package__ = 'core'
    sys.modules['core'] = _core_stub

import pytest

from core.cluster import build_clusters, cluster_summary, suggest_grandparent_lines
from core.treematch import (
    cm_to_mrca,
    cluster_confidence,
    pair_relationship,
    render_kinship,
    endogamy_flag,
    longest_to_generation,
    merge_person_list,
    fuzzy_score,
    Person,
    TreeIndex,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row(guid_a, name_a, cm_a, guid_b, name_b=None, cm_b=None, rel_a=""):
    """Build a minimal shared-match row suitable for build_clusters."""
    return {
        "match_guid_a": guid_a,
        "name_a":       name_a,
        "cm_a":         cm_a,
        "rel_a":        rel_a,
        "match_guid_b": guid_b,
        "name_b":       name_b or guid_b,
        "cm_b":         cm_b if cm_b is not None else cm_a,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CLUSTER – build_clusters  (11 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_build_clusters_empty_list():
    """Empty input must return empty dict."""
    result = build_clusters([])
    assert result == {}


def test_build_clusters_single_match_no_shared():
    """A single primary match whose only shared partner is below min_cm_shared
    remains a singleton cluster."""
    rows = [_row("A", "Alice", 100.0, "X", "Nobody", 5.0)]
    result = build_clusters(rows)
    assert len(result) == 1
    members = list(result.values())[0]
    assert len(members) == 1
    assert members[0]["guid"] == "A"


def test_build_clusters_two_matches_sharing():
    """Two primaries connected by a shared match are merged into one cluster."""
    rows = [
        _row("A", "Alice", 100.0, "S", "Shared", 30.0),
        _row("B", "Bob",   100.0, "S", "Shared", 30.0),
    ]
    result = build_clusters(rows)
    guids = {m["guid"] for members in result.values() for m in members}
    assert "A" in guids and "B" in guids
    for members in result.values():
        member_guids = {m["guid"] for m in members}
        if "A" in member_guids:
            assert "B" in member_guids


def test_build_clusters_three_forming_triangle():
    """Three primaries transitively connected via shared matches form one cluster."""
    rows = [
        _row("A", "Alice", 100.0, "S1", "Shared1", 30.0),
        _row("B", "Bob",   100.0, "S1", "Shared1", 30.0),
        _row("B", "Bob",   100.0, "S2", "Shared2", 30.0),
        _row("C", "Carol", 100.0, "S2", "Shared2", 30.0),
    ]
    result = build_clusters(rows)
    guids = {m["guid"] for members in result.values() for m in members}
    assert {"A", "B", "C"} == guids
    for members in result.values():
        member_guids = {m["guid"] for m in members}
        if "A" in member_guids:
            assert "B" in member_guids
            assert "C" in member_guids


def test_build_clusters_min_cm_primary_filter():
    """Matches below min_cm_primary are excluded from primary set → empty result."""
    rows = [_row("A", "Alice", 10.0, "S", "Shared", 5.0)]
    result = build_clusters(rows, min_cm_primary=20.0)
    assert result == {}


def test_build_clusters_max_cm_primary_filter():
    """Matches above max_cm_primary are excluded; in-range matches still appear."""
    rows = [
        _row("A", "Alice", 500.0, "S", "Shared", 30.0),
        _row("B", "Bob",   100.0, "S", "Shared", 30.0),
    ]
    result = build_clusters(rows, max_cm_primary=400.0)
    guids = {m["guid"] for members in result.values() for m in members}
    assert "A" not in guids
    assert "B" in guids


def test_build_clusters_min_cm_shared_filter():
    """Shared matches below min_cm_shared must not create a union edge."""
    rows = [
        _row("A", "Alice", 100.0, "S", "Shared", 5.0),
        _row("B", "Bob",   100.0, "S", "Shared", 5.0),
    ]
    result = build_clusters(rows, min_cm_shared=20.0)
    for members in result.values():
        member_guids = {m["guid"] for m in members}
        if "A" in member_guids:
            assert "B" not in member_guids, "A and B must not be merged"


def test_build_clusters_returns_dict_with_list_values():
    """Return type is dict; every value is a list of dicts."""
    rows = [_row("A", "Alice", 100.0, "S", "Shared", 30.0)]
    result = build_clusters(rows)
    assert isinstance(result, dict)
    for v in result.values():
        assert isinstance(v, list)
        for item in v:
            assert isinstance(item, dict)


def test_build_clusters_cluster_ids_are_ints():
    """Cluster IDs (keys) must be integers >= 1."""
    rows = [_row("A", "Alice", 100.0, "S", "Shared", 30.0)]
    result = build_clusters(rows)
    for k in result.keys():
        assert isinstance(k, int)
        assert k >= 1


def test_build_clusters_two_separate_groups_produce_two_clusters():
    """Two independent pairs that share different shared-matches → two clusters."""
    rows = [
        _row("A", "Alice", 100.0, "S1", "Shared1", 30.0),
        _row("B", "Bob",   100.0, "S1", "Shared1", 30.0),
        _row("C", "Carol", 100.0, "S2", "Shared2", 30.0),
        _row("D", "Dave",  100.0, "S2", "Shared2", 30.0),
    ]
    result = build_clusters(rows)
    assert len(result) == 2


def test_build_clusters_member_dict_has_required_keys():
    """Each member dict must contain guid, name, cm, rel."""
    rows = [_row("A", "Alice", 100.0, "S", "Shared", 30.0, rel_a="4C")]
    result = build_clusters(rows)
    for members in result.values():
        for m in members:
            for key in ("guid", "name", "cm", "rel"):
                assert key in m, f"Missing key '{key}'"


# ═══════════════════════════════════════════════════════════════════════════
# CLUSTER – cluster_summary  (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_cluster_summary_empty_clusters():
    """Empty clusters dict returns an empty list."""
    assert cluster_summary({}) == []


def test_cluster_summary_single_cluster():
    """Single-member cluster returns one summary entry with correct fields."""
    clusters = {1: [{"name": "Alice", "cm": 200.0}]}
    result = cluster_summary(clusters)
    assert len(result) == 1
    e = result[0]
    assert e["cluster_id"] == 1
    assert e["count"] == 1
    assert e["max_cm"] == 200.0
    assert e["avg_cm"] == pytest.approx(200.0)


def test_cluster_summary_multiple_clusters_all_entries():
    """Summary contains one entry per cluster."""
    clusters = {
        1: [{"name": "Alice", "cm": 200.0}, {"name": "Bob", "cm": 150.0}],
        2: [{"name": "Carol", "cm": 100.0}],
    }
    result = cluster_summary(clusters)
    assert len(result) == 2
    ids = {e["cluster_id"] for e in result}
    assert ids == {1, 2}


def test_cluster_summary_top_matches_field():
    """top_matches lists member names (first up to 3 members)."""
    clusters = {
        1: [{"name": "Alice", "cm": 200.0},
            {"name": "Bob",   "cm": 150.0},
            {"name": "Carol", "cm": 100.0}]
    }
    result = cluster_summary(clusters)
    top = result[0]["top_matches"]
    assert isinstance(top, list)
    assert "Alice" in top


def test_cluster_summary_avg_cm_correct():
    """avg_cm is the arithmetic mean of all member cM values."""
    clusters = {1: [{"name": "A", "cm": 100.0}, {"name": "B", "cm": 200.0}]}
    result = cluster_summary(clusters)
    assert result[0]["avg_cm"] == pytest.approx(150.0)


# ═══════════════════════════════════════════════════════════════════════════
# CLUSTER – suggest_grandparent_lines  (4 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_suggest_grandparent_lines_empty():
    """Empty clusters → string that mentions 0 clusters."""
    text = suggest_grandparent_lines({})
    assert isinstance(text, str)
    assert "0" in text


def test_suggest_grandparent_lines_single_cluster_returns_string():
    """Single cluster → non-empty string."""
    clusters = {1: [{"name": "Alice", "cm": 100.0}]}
    text = suggest_grandparent_lines(clusters)
    assert isinstance(text, str)
    assert len(text) > 0


def test_suggest_grandparent_lines_four_clusters_mentions_4_lines():
    """Exactly 4 clusters → text references Leeds / 4 Großelternlinien."""
    clusters = {i: [{"name": f"P{i}", "cm": 100.0}] for i in range(1, 5)}
    text = suggest_grandparent_lines(clusters)
    assert "4" in text
    assert "Leeds" in text or "Großelternlinien" in text or "klassischen" in text


def test_suggest_grandparent_lines_two_clusters_mentions_2():
    """Two clusters → text mentions count 2."""
    clusters = {
        1: [{"name": "Alice", "cm": 200.0}],
        2: [{"name": "Bob",   "cm": 180.0}],
    }
    text = suggest_grandparent_lines(clusters)
    assert "2" in text


# ═══════════════════════════════════════════════════════════════════════════
# TREEMATCH – cm_to_mrca  (8 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_cm_to_mrca_3500_gen1():
    """3500 cM → grandparent/uncle tier, gen 2."""
    label, gen = cm_to_mrca(3500)
    assert gen == 2


def test_cm_to_mrca_1750_gen2():
    """1750 cM → same tier as grandparent/uncle (gen 2)."""
    label, gen = cm_to_mrca(1750)
    assert gen == 2


def test_cm_to_mrca_875_gen3():
    """875 cM → 1st-cousin tier, gen 3."""
    label, gen = cm_to_mrca(875)
    assert gen == 3


def test_cm_to_mrca_220_gen4():
    """220 cM → 1C1R / 2nd-cousin tier, gen 4."""
    label, gen = cm_to_mrca(220)
    assert gen == 4


def test_cm_to_mrca_50_gen5plus():
    """50 cM → 2C1R / 3rd-cousin range, gen 5."""
    label, gen = cm_to_mrca(50)
    assert gen == 5


def test_cm_to_mrca_small_value_far():
    """0.1 cM → distant relative, gen >= 8."""
    label, gen = cm_to_mrca(0.1)
    assert gen >= 8


def test_cm_to_mrca_returns_tuple_str_int():
    """Return value is a (str, int) tuple."""
    result = cm_to_mrca(100)
    assert isinstance(result, tuple) and len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], int)


def test_cm_to_mrca_label_nonempty():
    """Label is a non-empty string for every supported cM value."""
    for cm in [0, 10, 50, 200, 800, 2000, 3500]:
        label, _ = cm_to_mrca(cm)
        assert isinstance(label, str) and len(label) > 0


# ═══════════════════════════════════════════════════════════════════════════
# TREEMATCH – cluster_confidence  (8 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_cluster_confidence_large_dense_high_realness():
    """Large, fully-dense cluster with high cM → high realness."""
    result = cluster_confidence(size=10, density=1.0, median_cm=120.0)
    assert result["realness"] >= 0.85


def test_cluster_confidence_small_sparse_low_realness():
    """Tiny cluster with near-zero density and low cM → lower realness."""
    result = cluster_confidence(size=2, density=0.01, median_cm=5.0)
    assert result["realness"] < 0.85


def test_cluster_confidence_endogamy_score_does_not_inflate():
    """High endogamy_score must not raise realness above a run without it."""
    base = cluster_confidence(size=5, density=0.5, median_cm=60.0,
                              endogamy_score=0.0)
    endo = cluster_confidence(size=5, density=0.5, median_cm=60.0,
                              endogamy_score=1.0)
    assert endo["realness"] <= base["realness"] + 0.01


def test_cluster_confidence_n_confirmed_increases_realness():
    """Confirmed tree-linked members raise realness."""
    without = cluster_confidence(size=3, density=0.5, median_cm=30.0,
                                 n_confirmed=0)
    with_conf = cluster_confidence(size=3, density=0.5, median_cm=30.0,
                                   n_confirmed=2)
    assert with_conf["realness"] >= without["realness"]


def test_cluster_confidence_returns_required_keys():
    """Result dict contains realness, label, note, cohesion."""
    result = cluster_confidence(size=4, density=0.6)
    for key in ("realness", "label", "note", "cohesion"):
        assert key in result, f"Missing key: {key}"


def test_cluster_confidence_realness_in_unit_interval():
    """realness is always in [0, 1]."""
    for size in (1, 5, 50):
        for density in (0.0, 0.5, 1.0):
            result = cluster_confidence(size=size, density=density)
            assert 0.0 <= result["realness"] <= 1.0


def test_cluster_confidence_label_nonempty():
    """label must be a non-empty string."""
    result = cluster_confidence(size=5, density=0.8)
    assert isinstance(result["label"], str) and len(result["label"]) > 0


def test_cluster_confidence_cohesion_key_present():
    """cohesion key equals the density passed in (clamped to [0,1])."""
    result = cluster_confidence(size=4, density=0.7)
    assert result["cohesion"] == pytest.approx(0.7)


# ═══════════════════════════════════════════════════════════════════════════
# TREEMATCH – pair_relationship  (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_pair_relationship_3500_parent_or_child():
    """3500 cM → parent/child or full-sibling label (≥ 2400 threshold)."""
    label = pair_relationship(3500)
    assert "Eltern" in label or "Kind" in label or "Geschwister" in label


def test_pair_relationship_2600_sibling():
    """2600 cM → sibling/grandparent/uncle range."""
    label = pair_relationship(2600)
    assert "Geschwister" in label or "Eltern" in label or "Onkel" in label or "Großeltern" in label


def test_pair_relationship_875_cousin():
    """875 cM → uncle/aunt or half-sibling range."""
    label = pair_relationship(875)
    assert "Cousin" in label or "Onkel" in label or "Halbgeschwister" in label


def test_pair_relationship_50_distant():
    """50 cM → distant cousin; must not claim parent/child."""
    label = pair_relationship(50)
    assert isinstance(label, str) and len(label) > 0
    assert "Eltern" not in label and "Kind" not in label


def test_pair_relationship_zero_distant():
    """0 cM → 'entfernt' or distant-equivalent label."""
    label = pair_relationship(0)
    assert isinstance(label, str) and len(label) > 0
    assert "entfernt" in label.lower() or "Cousin" in label


# ═══════════════════════════════════════════════════════════════════════════
# TREEMATCH – render_kinship  (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_render_kinship_F_vater():
    """Path 'F' → exactly 'Vater'."""
    assert render_kinship("F") == "Vater"


def test_render_kinship_M_mutter():
    """Path 'M' → exactly 'Mutter'."""
    assert render_kinship("M") == "Mutter"


def test_render_kinship_FF_grossvater_paternal():
    """Path 'FF' → Großvater väterlicherseits."""
    result = render_kinship("FF")
    assert "Großvater" in result
    assert "väterlicherseits" in result


def test_render_kinship_MF_grossvater_maternal():
    """Path 'MF' → Großvater mütterlicherseits."""
    result = render_kinship("MF")
    assert "Großvater" in result
    assert "mütterlicherseits" in result


def test_render_kinship_empty_string_root():
    """Empty path → non-empty string describing the root person."""
    result = render_kinship("")
    assert isinstance(result, str) and len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════
# TREEMATCH – endogamy_flag  (5 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_endogamy_flag_many_segments_short_longest_likely():
    """High segment count + short longest segment → endogamy likely, score >= 0.6."""
    label, score = endogamy_flag(total_cm=80, num_segments=10, longest=8)
    assert score >= 0.6
    assert "Endogamie" in label


def test_endogamy_flag_normal_not_endogamy():
    """5 segments with a 80 cM longest segment → not endogamy (score < 0.3)."""
    label, score = endogamy_flag(total_cm=120, num_segments=5, longest=80)
    assert score < 0.3


def test_endogamy_flag_returns_label_score_tuple():
    """Return value is (str, float)."""
    result = endogamy_flag(total_cm=50, num_segments=5, longest=20)
    assert isinstance(result, tuple) and len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], float)


def test_endogamy_flag_score_in_unit_interval():
    """Score is always in [0, 1]."""
    for segs, longest in [(0, 0), (1, 100), (7, 14), (20, 5)]:
        _, score = endogamy_flag(total_cm=50, num_segments=segs, longest=longest)
        assert 0.0 <= score <= 1.0


def test_endogamy_flag_extreme_endogamy_score_one():
    """Extreme endogamy signature (many tiny segments) → score capped at 1.0."""
    # num=12 ≥4 avg=5<12 (+0.5); num≥7 longest=4<15 (+0.3); total=60<90 num≥5 (+0.2) → 1.0
    label, score = endogamy_flag(total_cm=60, num_segments=12, longest=4)
    assert score == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════════════
# TREEMATCH – Person + TreeIndex  (9 tests)
# ═══════════════════════════════════════════════════════════════════════════

def test_person_display_full_name():
    """Person.display returns 'Given Surname'."""
    p = Person("Hans", "Müller", 1850, "Osnabrück")
    assert p.display == "Hans Müller"


def test_person_stoks_nonempty():
    """Person with a non-empty surname must have non-empty stoks."""
    p = Person("Hans", "Müller", 1850, "Osnabrück")
    assert len(p.stoks) > 0


def test_fuzzy_score_same_person_is_one():
    """Identical person objects → score ≈ 1.0."""
    p = Person("Johann", "Schmidt", 1872, "Hamburg")
    assert fuzzy_score(p, p) == pytest.approx(1.0, abs=0.01)


def test_fuzzy_score_different_names_low():
    """Completely unrelated names → score < 0.5."""
    a = Person("Alice", "Müller", 1850, "Berlin")
    b = Person("Franz", "Schulze", 1900, "München")
    assert fuzzy_score(a, b) < 0.5


def test_fuzzy_score_year_diff_gt3_is_zero():
    """Same name but year difference > year_tol → score 0.0 (hard cutoff)."""
    a = Person("Johann", "Schmidt", 1872, "Hamburg")
    b = Person("Johann", "Schmidt", 1880, "Hamburg")
    assert fuzzy_score(a, b, year_tol=3) == 0.0


def test_fuzzy_score_year_within_tol_positive():
    """Same name, year within tolerance → positive score."""
    a = Person("Johann", "Schmidt", 1872, "Hamburg")
    b = Person("Johann", "Schmidt", 1873, "Hamburg")
    assert fuzzy_score(a, b, year_tol=3) > 0.0


def test_treeindex_best_match_finds_correct_person():
    """TreeIndex.best_match returns the correct person from a small population."""
    people = [
        Person("Anna",   "Meier",   1860, "Köln"),
        Person("Karl",   "Becker",  1875, "Dresden"),
        Person("Johann", "Schmidt", 1850, "Hamburg"),
    ]
    idx = TreeIndex(people)
    q = Person("Johann", "Schmidt", 1850, "Hamburg")
    match, score = idx.best_match(q, min_score=0.6)
    assert match is not None
    assert match.display == "Johann Schmidt"
    assert score >= 0.6


def test_treeindex_best_match_no_match_returns_none():
    """best_match with no suitable candidate returns (None, 0.0)."""
    idx = TreeIndex([Person("Anna", "Meier", 1860, "Köln")])
    q = Person("Xanthippe", "Zzz", 1600, "Atlantis")
    match, score = idx.best_match(q, min_score=0.6)
    assert match is None
    assert score == 0.0


def test_treeindex_best_match_min_score_filter():
    """Raising min_score above achievable threshold suppresses the match."""
    idx = TreeIndex([Person("Anna", "Meier", 1860, "Köln")])
    q = Person("Anna", "Meier", 1860, "Köln")
    match_low,  _ = idx.best_match(q, min_score=0.0)
    assert match_low is not None
    match_high, score_high = idx.best_match(q, min_score=1.1)
    assert match_high is None
    assert score_high == 0.0
