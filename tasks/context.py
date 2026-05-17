# -*- coding: utf-8 -*-
"""
tasks/context.py – Schema des Shared-State zwischen Tasks.

Die Datenstruktur lebt als modul-globaler `_state` in tasks/_runner.py
und wird heute als plain dict benutzt. Dieses Schema fasst alle Felder
typisiert zusammen — `mypy` / `pyright` können damit jeden Zugriff
prüfen, ohne dass die Laufzeitsemantik sich ändert.

Langfristig sollte `_state` durch eine echte Klasse mit Dependency-
Injection ersetzt werden; bis dahin ist diese TypedDict-Definition die
einzige Quelle der Wahrheit für die Feldnamen.
"""

from __future__ import annotations

import threading
from typing import Any, Optional, TypedDict


class AnalysisContext(TypedDict, total=False):
    """Schema des Shared-State zwischen Tasks (`tasks._runner._state`)."""

    # ── Stammdaten ─────────────────────────────────────────────────────────────
    individuals:           dict
    families:              dict
    location_data:         dict
    cache:                 Optional[Any]
    stop_event:            Optional[threading.Event]

    # ── Vorberechnete Ahnenpfade / Verwandtenmenge ─────────────────────────────
    root_paths:            dict
    root_related_ids:      Optional[set]

    # ── Analyse-Ergebnisse ─────────────────────────────────────────────────────
    output_rows:           list   # Cousins
    endogamy_results:      list
    top_ancestors:         list
    migration_results:     list
    compressed_migration:  list
    migration_waves:       list
    correlation_results:   list
    military_results:      list
    demographic_results:   list
    surname_results:       list
    country_dist_results:  list
    comprehensive_stats:   list
    inbreeding_results:    list
    pedigree_gen_rows:     list
    pedigree_multi_rows:   list
    hist_event_rows:       list
    hist_person_rows:      list
    completeness_rows:     list
    completeness_surname:  list
    completeness_epoch:    list
    soundex_variant_rows:  list
    soundex_person_rows:   list
    survival_curve_rows:   list
    survival_summary_rows: list
    survival_cohort_names: list
    network_results:       list
    osnabrueck_results:    dict
    osnabrueck_summaries:  dict
    historical_trends:     dict
    generation_lengths:    list
