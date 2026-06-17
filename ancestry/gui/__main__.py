"""
Ancestry GUI Main Entry Point

Erlaubt: python -m ancestry.gui
"""

import sys

if __name__ == "__main__":
    # Delegiert an den kanonischen Einstiegspunkt (mit Logging-Setup).
    from ancestry.main import main

    try:
        main()
    except KeyboardInterrupt:
        print("\nShutdown.")
        sys.exit(0)
