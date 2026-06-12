"""Zentrale Pfade der Genealogie-Suite (M3 im ARCHITEKTUR-KONZEPT).

Laufzeit-Artefakte liegen unter DATA_DIR (gitignored); alles per
Umgebungsvariable überschreibbar. Die Verzeichnisse werden beim Import
angelegt, damit ein frisches Clone ohne manuelle Schritte startfähig ist.

    GENEA_DATA_DIR     Wurzel für Laufzeitdaten   (default: <repo>/data)
    ANCESTRY_DB        SQLite-Hauptdatenbank      (default: <repo>/ancestry_dna.db)
    MATRICULA_ARCHIVE  Kirchenbuch-Scans          (default: ~/matricula_images)
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR     = Path(os.environ.get("GENEA_DATA_DIR", str(ROOT / "data")))
SNAPSHOT_DIR = DATA_DIR / "snapshots"
EXPORT_DIR   = DATA_DIR / "exports"
LOG_DIR      = DATA_DIR / "logs"
CACHE_DIR    = DATA_DIR / "cache"

# Die Haupt-DB bleibt im Repo-Root — bestehende Installationen erwarten sie
# dort; ein Umzug nach data/db/ bekäme eine eigene Migration (s. Konzept M3).
DB_PATH = Path(os.environ.get("ANCESTRY_DB", str(ROOT / "ancestry_dna.db")))

MATRICULA_ARCHIVE = Path(os.environ.get(
    "MATRICULA_ARCHIVE", str(Path.home() / "matricula_images")))

for _d in (DATA_DIR, SNAPSHOT_DIR, EXPORT_DIR, LOG_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
