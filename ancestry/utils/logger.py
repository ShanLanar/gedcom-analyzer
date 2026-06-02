"""
Logging-Konfiguration für ancestry_dna_tool.
"""

import logging
import logging.handlers
import os
import sys

_configured = False


def setup_logging(log_file: str = "ancestry_dna.log", level: str = "DEBUG") -> None:
    """Richtet Root-Logger mit File- und Console-Handler ein (idempotent)."""
    global _configured
    if _configured:
        return
    _configured = True

    numeric_level = getattr(logging, level.upper(), logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Datei-Handler (rotierende Logs, max. 5 × 2 MB)
    try:
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as e:
        print(f"[WARN] Log-Datei konnte nicht erstellt werden: {e}", file=sys.stderr)

    # Konsolen-Handler (nur INFO+)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """Gibt einen benannten Logger zurück."""
    return logging.getLogger(name)
