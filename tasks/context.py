# -*- coding: utf-8 -*-
"""
tasks/context.py – Shared-State zwischen Tasks als Dataclass.

`AnalysisContext` ist heute die kanonische Form des Run-State. Aus
Backward-Compat-Gründen unterstützt sie weiterhin den dict-Zugriff
(`ctx["individuals"]`, `ctx.get("foo", default)`), den die existierenden
Tasks gewohnt sind — neue Aufrufer können direkt die Attribute nutzen
(`ctx.individuals`).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AnalysisContext:
    """Run-State, der zwischen Tasks geteilt wird."""

    # ── Stammdaten ─────────────────────────────────────────────────────────────
    individuals:           dict = field(default_factory=dict)
    families:              dict = field(default_factory=dict)
    location_data:         dict = field(default_factory=dict)
    cache:                 Optional[Any] = None
    stop_event:            Optional[threading.Event] = None

    # ── Vorberechnete Ahnenpfade / Verwandtenmenge ─────────────────────────────
    root_paths:            dict = field(default_factory=dict)
    root_related_ids:      Optional[set] = None

    # ── Analyse-Ergebnisse ─────────────────────────────────────────────────────
    output_rows:           list = field(default_factory=list)   # Cousins
    endogamy_results:      list = field(default_factory=list)
    top_ancestors:         list = field(default_factory=list)
    migration_results:     list = field(default_factory=list)
    compressed_migration:  list = field(default_factory=list)
    migration_waves:       list = field(default_factory=list)
    correlation_results:   list = field(default_factory=list)
    military_results:      list = field(default_factory=list)
    demographic_results:   list = field(default_factory=list)
    surname_results:       list = field(default_factory=list)
    country_dist_results:  list = field(default_factory=list)
    comprehensive_stats:   list = field(default_factory=list)
    inbreeding_results:    list = field(default_factory=list)
    pedigree_gen_rows:     list = field(default_factory=list)
    pedigree_multi_rows:   list = field(default_factory=list)
    hist_event_rows:       list = field(default_factory=list)
    hist_person_rows:      list = field(default_factory=list)
    completeness_rows:     list = field(default_factory=list)
    completeness_surname:  list = field(default_factory=list)
    completeness_epoch:    list = field(default_factory=list)
    soundex_variant_rows:  list = field(default_factory=list)
    soundex_person_rows:   list = field(default_factory=list)
    survival_curve_rows:   list = field(default_factory=list)
    survival_summary_rows: list = field(default_factory=list)
    survival_cohort_names: list = field(default_factory=list)
    network_results:       list = field(default_factory=list)
    osnabrueck_results:    dict = field(default_factory=dict)
    osnabrueck_summaries:  dict = field(default_factory=dict)
    historical_trends:     dict = field(default_factory=dict)
    generation_lengths:    list = field(default_factory=list)

    # ── Dict-API für Backward-Compat ───────────────────────────────────────────
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)
