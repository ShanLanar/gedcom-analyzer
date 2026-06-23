#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI: Kern-GEDCOM-Analysen mit Fortschrittsanzeige.

Verwendung (aus dem Projektverzeichnis):
    python -u -m ancestry.tools.run_analysis

Gibt Schritt-Marker der Form  [1/4] …  aus, die vom Werkzeuge-Tab des
Ancestry-DNA-Tools im Live-Log angezeigt werden.
"""
import sys
from pathlib import Path

# Projektwurzel zum sys.path hinzufügen, damit das Skript auch direkt
# aufgerufen werden kann (nicht nur als Modul).
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config as cfg

cfg.apply_overrides()

import tasks._runner as runner  # noqa: E402  (nach sys.path-Anpassung)

runner.load_gedcom(
    progress_cb=lambda m, **_: print(m, flush=True),
)


def _cb(msg: str, **_kw) -> None:
    print(msg, flush=True)


runner.run_all_with_progress(progress_cb=_cb)
