"""Tests für assign_grandparent_quadrants (EPIC 3 – Phasing-Dashboard)."""
from ancestry.core.cluster import assign_grandparent_quadrants


def _cluster(n, base_cm=100.0):
    return [{"guid": f"g{i}", "name": f"P{i}", "cm": base_cm - i}
            for i in range(n)]


def test_empty():
    res = assign_grandparent_quadrants({})
    assert res["n_clusters"] == 0
    assert res["quadrants"] == []
    assert res["unassigned"] == []
    assert "Keine Cluster" in res["note"]


def test_exactly_four_quadrants():
    clusters = {1: _cluster(5), 2: _cluster(4), 3: _cluster(3), 4: _cluster(2)}
    res = assign_grandparent_quadrants(clusters)
    assert res["n_clusters"] == 4
    assert len(res["quadrants"]) == 4
    assert res["unassigned"] == []
    # nach Größe sortiert: größter Cluster im ersten Slot
    sizes = [q["size"] for q in res["quadrants"]]
    assert sizes == sorted(sizes, reverse=True)
    assert res["quadrants"][0]["cluster_id"] == 1
    assert res["quadrants"][0]["slot"] == 0
    assert "Leeds" in res["note"]


def test_more_than_four_go_to_unassigned():
    clusters = {i: _cluster(6 - i) for i in range(1, 7)}  # 6 Cluster
    res = assign_grandparent_quadrants(clusters)
    assert len(res["quadrants"]) == 4
    assert len(res["unassigned"]) == 2
    assert "weitere" in res["note"].lower()


def test_fewer_than_four():
    clusters = {1: _cluster(3), 2: _cluster(2)}
    res = assign_grandparent_quadrants(clusters)
    assert len(res["quadrants"]) == 2
    assert "Weniger als 4" in res["note"]


def test_summary_fields():
    clusters = {1: _cluster(3, base_cm=300.0)}
    q = assign_grandparent_quadrants(clusters)["quadrants"][0]
    assert q["max_cm"] == 300.0
    assert q["total_cm"] == 300.0 + 299.0 + 298.0
    assert q["names"] == ["P0", "P1", "P2"]
    assert q["label"] == "Großeltern-Linie A"


def test_quadrant_side_from_phased_matches():
    """Sind Matches per Eltern-Kit gephast (paternal_maternal), bekommt der
    Quadrant die echte Seite ins Label."""
    clusters = {
        1: [{"guid": f"m{i}", "name": f"M{i}", "cm": 100 - i,
             "paternal_maternal": "maternal"} for i in range(5)],
        2: [{"guid": f"p{i}", "name": f"P{i}", "cm": 90 - i,
             "paternal_maternal": "paternal"} for i in range(4)],
        3: [{"guid": "u0", "name": "U0", "cm": 80}],   # ungephast
    }
    quads = {q["slot"]: q for q in assign_grandparent_quadrants(clusters)["quadrants"]}
    assert quads[0]["side"] == "mütterlich"
    assert "mütterlich" in quads[0]["label"]
    assert quads[1]["side"] == "väterlich"
    assert quads[2]["side"] == ""                       # ohne Phasing kein Suffix
    assert "·" not in quads[2]["label"]


def test_leeds_colors_assigned():
    """Jeder der vier Quadranten bekommt eine eindeutige Leeds-Farbe."""
    from ancestry.core.cluster import LEEDS_COLORS
    clusters = {1: _cluster(5), 2: _cluster(4), 3: _cluster(3), 4: _cluster(2)}
    quads = assign_grandparent_quadrants(clusters)["quadrants"]
    colors = [q["color"] for q in quads]
    assert colors == LEEDS_COLORS            # Slot-Reihenfolge A–D
    assert len(set(colors)) == 4             # alle verschieden
    assert quads[0]["color_name"] == "Gelb"


def test_names_truncated():
    clusters = {1: _cluster(20)}
    q = assign_grandparent_quadrants(clusters, top_names=6)["quadrants"][0]
    assert len(q["names"]) == 6
    assert q["size"] == 20


def test_handles_missing_cm():
    clusters = {1: [{"name": "X"}, {"name": "Y", "cm": None}]}
    q = assign_grandparent_quadrants(clusters)["quadrants"][0]
    assert q["max_cm"] == 0.0
    assert q["size"] == 2
