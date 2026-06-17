#!/usr/bin/env python3
"""
Schnelles Startup-Diagnostik-Tool.

Nutze periodisch, um sicherzustellen, dass die App nicht langsamer wird:

    python measure_startup.py

Zeigt: Import-Zeiten, DB-Query-Zeiten, und Bottlenecks.
"""

import sys
import time
from pathlib import Path

def measure(label: str, func, warn_threshold: float = 0.5):
    """Misst eine Funktion und warnt, wenn zu langsam."""
    start = time.time()
    try:
        result = func()
        elapsed = time.time() - start

        status = "✓"
        if elapsed > warn_threshold * 2:
            status = "🔴"  # Viel zu langsam
        elif elapsed > warn_threshold:
            status = "⚠️"  # Langsam

        print(f"  {status} {label:40} {elapsed:.3f}s")
        return elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ {label:40} {elapsed:.3f}s ({type(e).__name__})")
        return None

def main():
    print("=" * 70)
    print("ANCESTRY ANALYZER – STARTUP DIAGNOSTICS")
    print("=" * 70)

    times = {}

    # 1. Database
    print("\n1. DATABASE")
    print("-" * 70)

    def init_db():
        from ancestry.paths import DB_PATH
        from ancestry.core.database import Database
        return Database(str(DB_PATH))

    times['db_init'] = measure("Database.__init__()", init_db, warn_threshold=0.1)

    # 2. Core Imports
    print("\n2. CORE IMPORTS")
    print("-" * 70)

    def import_cluster():
        from ancestry.core.cluster import build_clusters

    def import_export():
        from ancestry.core.export import export_csv

    def import_bridge():
        from ancestry.core.bridge.matching import match_to_dict

    times['import_cluster'] = measure("Import cluster", import_cluster, warn_threshold=0.05)
    times['import_export'] = measure("Import export (openpyxl lazy)", import_export, warn_threshold=0.01)
    times['import_bridge'] = measure("Import bridge.matching", import_bridge, warn_threshold=0.05)

    # 3. Heavy Modules (that are now lazy-loaded)
    print("\n3. HEAVY MODULES (now lazy-loaded)")
    print("-" * 70)

    def import_stats():
        from ancestry.gui.tabs.stats import StatsTab

    def import_matricula():
        from ancestry.gui.tabs.matricula import MatriculaTab

    times['lazy_stats'] = measure("Import StatsTab (lazy, on demand)", import_stats, warn_threshold=0.5)
    times['lazy_matricula'] = measure("Import MatriculaTab (lazy, on demand)", import_matricula, warn_threshold=0.5)

    # 4. Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total = sum(t for t in times.values() if t is not None)
    print(f"\nTotal Measured Time: {total:.3f}s")

    print("\nBottleneck Analysis:")
    print("-" * 70)

    sorted_times = sorted([(k, v) for k, v in times.items() if v is not None], key=lambda x: x[1], reverse=True)

    for label, elapsed in sorted_times[:3]:
        pct = (elapsed / total) * 100 if total > 0 else 0
        print(f"  {label:30} {elapsed:.3f}s ({pct:.0f}%)")

    # Performance thresholds
    print("\nPerformance Targets:")
    print("-" * 70)

    targets = {
        'db_init': (0.1, 'Should be <100ms'),
        'total': (1.0, 'Total startup should be <1s (Core only)'),
    }

    if times.get('db_init') and times['db_init'] < 0.1:
        print("  ✓ Database init: <100ms")

    if total < 1.0:
        print("  ✓ Core startup: <1s")
    else:
        print(f"  ⚠️  Core startup: {total:.3f}s (target: <1s)")

    print("\nNote: GUI rendering (tkinter) will add ~500-800ms on top of these times.")
    print("With async Match-Table loading, total startup should be ~1-2s.")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
