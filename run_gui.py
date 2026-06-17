#!/usr/bin/env python3
"""
Ancestry DNA Analyzer – GUI Startup Script

Nutze:
    python run_gui.py

oder:
    python -m ancestry.gui
"""

import sys

if __name__ == "__main__":
    # Delegiert an den kanonischen Einstiegspunkt (mit Logging-Setup).
    # Identisch zu:  python -m ancestry.main
    from ancestry.main import main

    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown.")
        sys.exit(0)
