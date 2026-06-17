"""
Integration Tests für App-Struktur und Lazy-Loading.

Note: GUI-Tests werden skipped, wenn tkinter nicht verfügbar ist.
"""

import pytest


def test_lazy_import_framework():
    """Testet Lazy-Import-Framework (ohne tkinter)."""
    pytest.importorskip("tkinter")
    from ancestry.gui.app import _lazy_import

    StatsTab = _lazy_import("ancestry.gui.tabs.stats", "StatsTab")
    assert StatsTab is not None


def test_core_imports_fast():
    """Testet, dass Core-Imports ohne tkinter schnell gehen."""
    import time

    start = time.time()
    from ancestry.core.database import Database
    from ancestry.core.cluster import build_clusters
    from ancestry.core.export import export_csv

    elapsed = time.time() - start
    assert elapsed < 1.0, f"Core import zu langsam: {elapsed:.2f}s"
