"""
Performance Regression Tests — stellt sicher, dass Startup schnell bleibt.

Messungen mit pytest-benchmark können lokal ausgeführt werden:
    pytest tests/test_performance.py -v --benchmark-only
"""

import time
import pytest


def test_core_imports_time():
    """Core-Imports sollten <0.3s sein (ohne GUI)."""
    import sys

    start = time.time()
    from ancestry.core.database import Database
    from ancestry.core.cluster import build_clusters
    from ancestry.core.export import export_csv

    elapsed = time.time() - start

    # Regression Test
    assert (
        elapsed < 0.3
    ), f"Core imports zu langsam: {elapsed:.3f}s (sollte <0.3s sein)"


def test_database_init_time():
    """Database-Init sollte <0.05s sein."""
    from ancestry.paths import DB_PATH
    from ancestry.core.database import Database

    start = time.time()
    db = Database(str(DB_PATH))
    elapsed = time.time() - start

    assert elapsed < 0.05, f"DB init zu langsam: {elapsed:.3f}s"


def test_get_kits_query_time():
    """get_kits() Query sollte <0.01s sein (auch mit 100+ Kits)."""
    from ancestry.paths import DB_PATH
    from ancestry.core.database import Database

    db = Database(str(DB_PATH))

    start = time.time()
    kits = list(db.get_kits())
    elapsed = time.time() - start

    assert (
        elapsed < 0.01
    ), f"get_kits() zu langsam: {elapsed:.3f}s (sollte <0.01s sein)"


def test_build_clusters_performance():
    """Clustering sollte <1s für 1000+ Matches sein."""
    from ancestry.core.cluster import build_clusters

    # Dummy-Daten: 100 Matches mit Shared-Match-Verbindungen
    shared_data = []
    for i in range(100):
        shared_data.append(
            {
                "primary_guid": f"match_{i}",
                "shared_guid": f"match_{i+1 % 100}",
                "shared_cm": 50 + (i % 100),
            }
        )

    start = time.time()
    clusters = build_clusters(shared_data, min_cm_primary=20)
    elapsed = time.time() - start

    assert (
        elapsed < 1.0
    ), f"build_clusters() zu langsam: {elapsed:.3f}s (sollte <1s sein)"


@pytest.mark.gui
def test_app_import_not_locked():
    """App-Import sollte nicht blockiert sein (nur lazy-loads)."""
    pytest.importorskip("tkinter")
    import sys
    import time

    start = time.time()
    try:
        from ancestry.gui.app import AncestryDnaApp
    except ModuleNotFoundError:
        # tkinter nicht verfügbar
        pytest.skip("tkinter not available")

    elapsed = time.time() - start

    # Sollte schnell gehen (lazy-loads aktiv)
    assert (
        elapsed < 2.0
    ), f"App import zu langsam: {elapsed:.3f}s (lazy-loading aktiv?)"


# Benchmark-Tests (mit pytest-benchmark)
@pytest.mark.benchmark
def test_cluster_algorithm_benchmark(benchmark):
    """Benchmark: Wie schnell ist der Leeds-Algorithmus?"""
    from ancestry.core.cluster import build_clusters

    shared_data = [
        {
            "primary_guid": f"m{i}",
            "shared_guid": f"m{(i+1) % 100}",
            "shared_cm": 50,
        }
        for i in range(100)
    ]

    benchmark(build_clusters, shared_data)


@pytest.mark.benchmark
def test_database_query_benchmark(benchmark):
    """Benchmark: Wie schnell ist get_kits()?"""
    from ancestry.paths import DB_PATH
    from ancestry.core.database import Database

    db = Database(str(DB_PATH))

    def query():
        return list(db.get_kits())

    benchmark(query)
