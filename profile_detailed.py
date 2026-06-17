#!/usr/bin/env python3
"""
Detailliertes Startup-Profiling: Findet echte Bottlenecks
"""

import sys
import time
import cProfile
import pstats
from io import StringIO


def measure(label: str, func):
    """Misst die Zeit einer Funktion."""
    start = time.time()
    result = func()
    elapsed = time.time() - start
    print(f"  {label}: {elapsed:.3f}s")
    return result, elapsed


def profile_startup():
    print("=" * 70)
    print("DETAILLIERTES STARTUP-PROFILING (ohne GUI)")
    print("=" * 70)

    # 1. Database Init
    print("\n1. DATABASE INITIALIZATION")
    def init_db():
        from ancestry.paths import DB_PATH
        from ancestry.core.database import Database
        return Database(str(DB_PATH))

    db, db_time = measure("Database()", init_db)

    # 2. Load kits from DB
    print("\n2. DATABASE QUERIES (on startup)")
    def load_kits():
        kits = list(db.get_kits())
        return len(kits)

    kit_count, kit_time = measure("get_kits()", load_kits)

    # 3. Load matches (if kits exist)
    print("\n3. MATCH DATA LOADING")
    def load_matches():
        if kit_count > 0:
            matches = list(db.get_matches(None))
            return len(matches)
        return 0

    match_count, match_time = measure("get_matches()", load_matches)

    # 4. Check imports from app.py (OHNE tkinter laden)
    print("\n4. IMPORT-PROFILING")
    def check_imports():
        import sys
        # Vermeide tkinter
        sys.modules['tkinter'] = None
        try:
            from ancestry.core.auth import AncestryAuth
            from ancestry.core.api import AncestryApiClient
            return True
        except:
            return False

    imports_ok, import_time = measure("Core/API Imports", check_imports)

    # Summary
    print("\n" + "=" * 70)
    print("ZEITEN-ZUSAMMENFASSUNG")
    print("=" * 70)
    total = db_time + kit_time + match_time + import_time
    print(f"Database Init:  {db_time:.3f}s ({db_time/total*100:.0f}%)")
    print(f"Load Kits:      {kit_time:.3f}s ({kit_time/total*100:.0f}%) — {kit_count} Kits")
    print(f"Load Matches:   {match_time:.3f}s ({match_time/total*100:.0f}%) — {match_count} Matches")
    print(f"Core Imports:   {import_time:.3f}s ({import_time/total*100:.0f}%)")
    print("-" * 70)
    print(f"TOTAL (Core):   {total:.3f}s")
    print()
    print("🔍 BOTTLENECK ANALYSE:")
    print("-" * 70)
    if match_time > kit_time * 2:
        print("⚠️  Matches-Laden ist langsam! Überprüfe DB-Indexierung.")
    if db_time > 0.5:
        print("⚠️  Database-Init ist langsam! Überprüfe DB-Größe/Migrations.")
    print()
    print("Hinweis: Die echte Slowness (~Minuten) kommt wahrscheinlich von:")
    print("  1. GUI-Rendering (tkinter) — kann lokal profilt werden")
    print("  2. GEDCOM-Import (beim Startup laden)")
    print("  3. Large-Data Queries (Match-Clustering, Triangulation)")
    print()


if __name__ == "__main__":
    profile_startup()
