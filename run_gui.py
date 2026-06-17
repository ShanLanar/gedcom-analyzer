#!/usr/bin/env python3
"""
Ancestry DNA Analyzer – GUI Startup Script

Nutze:
    python run_gui.py

oder:
    python -m ancestry.gui
"""

import sys
import logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    # Avoid circular import issues
    from ancestry.gui.app import AncestryDnaApp

    try:
        app = AncestryDnaApp()
        app.mainloop()
    except KeyboardInterrupt:
        print("\nShutdown.")
        sys.exit(0)
    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        sys.exit(1)
