#!/usr/bin/env python3
"""
Startup-Profiling: Wo verbraucht die App Zeit beim Laden?
Misst:
  1. Import-Zeit (ancestry-Module)
  2. Database-Initialisierung
  3. GUI-Konstruktion (Tabs)
"""

import sys
import time
import cProfile
import pstats
from io import StringIO

def profile_imports():
    """Misst Import-Zeit"""
    print("=" * 60)
    print("IMPORT-PROFILING")
    print("=" * 60)

    start = time.time()
    import ancestry
    elapsed = time.time() - start
    print(f"import ancestry: {elapsed:.3f}s")

    start = time.time()
    from ancestry.core.database import Database
    from ancestry.paths import DB_PATH
    elapsed = time.time() - start
    print(f"import Database + DB_PATH: {elapsed:.3f}s")

    start = time.time()
    from ancestry.gui.state import AppState
    elapsed = time.time() - start
    print(f"import AppState: {elapsed:.3f}s")

    start = time.time()
    from ancestry.gui.tabs import (
        StatsTab, ClusterTab, DownloadTab, MatchesTab, MatriculaTab, PersonsTab, ToolsTab
    )
    elapsed = time.time() - start
    print(f"import all Tabs: {elapsed:.3f}s")

    print()

def profile_app_init():
    """Misst App-Initialisierung mit cProfile"""
    print("=" * 60)
    print("APP INIT PROFILING (cProfile)")
    print("=" * 60)

    # Stub GUI (kein Display, nur Initialisierung messen)
    def init_stub():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()  # Fenster verstecken

        from ancestry.paths import DB_PATH
        from ancestry.core.database import Database
        from ancestry.gui.state import AppState

        start = time.time()
        state = AppState(db=Database(str(DB_PATH)), startup_gedcom_path="")
        elapsed = time.time() - start
        print(f"AppState init: {elapsed:.3f}s")

        root.destroy()

    pr = cProfile.Profile()
    pr.enable()
    init_stub()
    pr.disable()

    s = StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(20)  # Top 20 Functions
    print(s.getvalue())

if __name__ == "__main__":
    profile_imports()
    profile_app_init()
