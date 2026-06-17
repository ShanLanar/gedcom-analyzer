"""
Ancestry GUI Main Entry Point

Erlaubt: python -m ancestry.gui
"""

import sys

if __name__ == "__main__":
    from .app import AncestryDnaApp

    try:
        app = AncestryDnaApp()
        app.mainloop()
    except KeyboardInterrupt:
        print("\nShutdown.")
        sys.exit(0)
    except Exception as e:
        import logging
        logging.exception(f"Fatal error: {e}")
        sys.exit(1)
