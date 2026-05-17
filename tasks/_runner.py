# -*- coding: utf-8 -*-
"""
tasks/_runner.py
Zentrale Ausführungsschicht für die GUI.

Jede Funktion wird per tasks._runner:<fn> aus TASKS aufgerufen.
Der Shared-State (_state) überträgt GEDCOM-Daten zwischen Tasks.
"""

import os
import config as cfg
from lib.logger import setup_logging
from lib import gedcom as _gedcom_mod
from lib import places as _places_mod

# ── Shared State ───────────────────────────────────────────────────────────────
# Wird zwischen den Funktionen dieses Moduls geteilt.
_state = {
    "individuals":   {},
    "families":      {},
    "location_data": {},
    "cache":         None,

    # Analyseergebnisse
    "output_rows":            [],   # Cousins
    "endogamy_results":       [],
    "top_ancestors":          [],
    "migration_results":      [],
    "compressed_migration":   [],
    "migration_waves":        [],
    "correlation_results":    [],
    "military_results":       [],
    "demographic_results":    [],
    "surname_results":        [],
    "country_dist_results":   [],
    "comprehensive_stats":    [],
    "inbreeding_results":     [],
    "pedigree_gen_rows":      [],
    "pedigree_multi_rows":    [],
    "hist_event_rows":        [],
    "hist_person_rows":       [],
    "completeness_rows":      [],
    "completeness_surname":   [],
    "completeness_epoch":     [],
    "soundex_variant_rows":   [],
    "soundex_person_rows":    [],
    "survival_curve_rows":    [],
    "survival_summary_rows":  [],
    "survival_cohort_names":  [],
    "network_results":        [],
    "osnabrueck_results":     {},
    "osnabrueck_summaries":   {},
    "historical_trends":      {},
    "generation_lengths":     [],
    "root_paths":             {},
    "root_related_ids":       None,
    "stop_event":             None,
}


def _p(progress_cb, msg, tag=""):
    if progress_cb:
        progress_cb(msg, tag=tag)


def is_aborted() -> bool:
    """True wenn der Benutzer Stop gedrückt hat. Tasks mit langen
    Schleifen sollen das periodisch prüfen."""
    ev = _state.get("stop_event")
    return ev is not None and ev.is_set()


class AbortedError(Exception):
    """Wird geworfen, wenn ein Task wegen User-Stop abgebrochen wird."""


def _set_stop_event(stop_event):
    _state["stop_event"] = stop_event


# ── Schritt 1: GEDCOM + Ortsdaten ──────────────────────────────────────────────

def load_gedcom(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from lib.cache import GenealogyCache
    from lib.gedcom import robust_load_gedcom, set_logger as gl_set
    from lib.places import load_location_data, set_logger as pl_set
    from lib.helpers import clear_migration_status_cache

    lg = setup_logging(cfg.FILES.get("log_file"))
    gl_set(lg); pl_set(lg)
    clear_migration_status_cache()

    _p(progress_cb, "Lade Ortsdaten …")
    _state["location_data"] = load_location_data(cfg.DEFAULT_CONFIG["location_data_json"])

    _p(progress_cb, f"Lade GEDCOM: {cfg.DEFAULT_CONFIG['gedfile']} …")
    indiv, fams = robust_load_gedcom(cfg.DEFAULT_CONFIG["gedfile"])
    _state["individuals"] = indiv
    _state["families"]    = fams

    cache = GenealogyCache(cfg.DEFAULT_CONFIG["max_cache_size"])
    _state["cache"] = cache

    _p(progress_cb,
       f"GEDCOM geladen: {len(indiv):,} Personen, {len(fams):,} Familien",
       tag="ok")


# ── Schritt 2: Cousins ────────────────────────────────────────────────────────

def run_cousins(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.cousins import run as _run
    from lib.helpers import get_ancestor_paths

    root_id = cfg.DEFAULT_CONFIG["root_id"]
    rows = _run(
        _state["individuals"], _state["families"],
        _state["location_data"], root_id,
        cache=_state["cache"],
        progress_cb=progress_cb,
    )
    _state["output_rows"] = rows

    # Root-Verwandte vorberechnen
    rp = get_ancestor_paths(root_id, _state["individuals"],
                             _state["families"], _state["cache"])
    _state["root_paths"] = rp
    rids = set(r[0] for r in rows)
    rids.add(root_id)
    _state["root_related_ids"] = rids


# ── Schritt 3: Endogamie & Top-Ahnen ──────────────────────────────────────────

def run_endogamy(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.endogamy import (compute_endogamy_with_detailed_places,
                                 get_top_ancestors_with_info)
    _state["endogamy_results"] = compute_endogamy_with_detailed_places(
        _state["individuals"], _state["families"],
        cfg.DEFAULT_CONFIG["root_id"],
        _state["location_data"], progress_cb=progress_cb)
    _state["top_ancestors"] = get_top_ancestors_with_info(
        _state["individuals"], _state["families"],
        _state["location_data"],
        cfg.DEFAULT_CONFIG["root_id"],
        cfg.DEFAULT_CONFIG["exclude_id"],
        cache=_state["cache"],
        progress_cb=progress_cb)


# ── Schritt 4: Migration ───────────────────────────────────────────────────────

def run_migration(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.migration import (
        analyze_detailed_migration_routes,
        create_compressed_migration_routes,
        detect_migration_waves,
        analyze_migration_correlations,
    )
    indiv = _state["individuals"]; fams = _state["families"]
    ld    = _state["location_data"]
    rid   = cfg.DEFAULT_CONFIG["root_id"]

    mr = analyze_detailed_migration_routes(
        indiv, fams, rid, ld,
        root_related_ids=_state.get("root_related_ids"),
        root_paths=_state.get("root_paths"),
        cache=_state.get("cache"),
        progress_cb=progress_cb)
    _state["migration_results"] = mr

    _state["compressed_migration"] = create_compressed_migration_routes(
        mr, indiv, fams, rid, ld, progress_cb=progress_cb)
    _state["migration_waves"]     = detect_migration_waves(
        mr, indiv, progress_cb=progress_cb)
    _state["correlation_results"] = analyze_migration_correlations(
        indiv, fams, mr, ld, progress_cb=progress_cb)


# ── Schritt 5: Militär ────────────────────────────────────────────────────────

def run_military(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.military import analyze_military_service_detailed
    _state["military_results"] = analyze_military_service_detailed(
        _state["individuals"], _state["families"], progress_cb=progress_cb)


# ── Schritt 6: Demografie ─────────────────────────────────────────────────────

def run_demographics(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.demographics import (
        analyze_demographic_statistics,
        calculate_comprehensive_statistics,
    )
    _state["demographic_results"] = analyze_demographic_statistics(
        _state["individuals"], _state["families"],
        _state["location_data"], progress_cb=progress_cb)
    _state["comprehensive_stats"] = calculate_comprehensive_statistics(
        _state["individuals"], _state["families"], progress_cb=progress_cb)


# ── Schritt 7: Nachnamen & Geburtsländer ──────────────────────────────────────

def run_surnames_and_countries(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.demographics import (analyze_surname_frequency,
                                     analyze_birth_country_distribution)
    _state["surname_results"] = analyze_surname_frequency(
        _state["individuals"], progress_cb=progress_cb)
    _state["country_dist_results"] = analyze_birth_country_distribution(
        _state["individuals"], _state["location_data"], progress_cb=progress_cb)


# ── Schritt 8: Genetik ────────────────────────────────────────────────────────

def run_genetics(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.genetics import analyze_inbreeding_all, analyze_pedigree_collapse
    _state["inbreeding_results"] = analyze_inbreeding_all(
        _state["individuals"], _state["families"],
        root_related_ids=_state.get("root_related_ids"),
        progress_cb=progress_cb)
    gr, mr = analyze_pedigree_collapse(
        cfg.DEFAULT_CONFIG["root_id"],
        _state["individuals"], _state["families"],
        progress_cb=progress_cb)
    _state["pedigree_gen_rows"]  = gr
    _state["pedigree_multi_rows"] = mr


# ── Schritt 9: Historischer Kontext + Überlebenszeit + Generationen + Trends ──

def run_history(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.history import (analyze_historical_context, analyze_survival_curves,
                                calculate_generation_lengths,
                                analyze_historical_trends)
    er, pr = analyze_historical_context(
        _state["individuals"], _state["families"], progress_cb=progress_cb)
    _state["hist_event_rows"]  = er
    _state["hist_person_rows"] = pr

    cr, sr, cn = analyze_survival_curves(_state["individuals"], progress_cb=progress_cb)
    _state["survival_curve_rows"]   = cr
    _state["survival_summary_rows"] = sr
    _state["survival_cohort_names"] = cn

    _state["generation_lengths"] = calculate_generation_lengths(
        _state["individuals"], _state["families"],
        cfg.DEFAULT_CONFIG["root_id"],
        _state["location_data"], progress_cb=progress_cb)

    _state["historical_trends"] = analyze_historical_trends(
        _state["individuals"], _state["families"],
        _state["location_data"], progress_cb=progress_cb)


# ── Schritt 10: Namensmorphologie ─────────────────────────────────────────────

def run_names(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.names import analyze_name_morphology
    vr, pr = analyze_name_morphology(_state["individuals"], progress_cb=progress_cb)
    _state["soundex_variant_rows"] = vr
    _state["soundex_person_rows"]  = pr


# ── Schritt 11: Datenvollständigkeit ──────────────────────────────────────────

def run_data_quality(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.data_quality import analyze_data_completeness
    cr, sr, er = analyze_data_completeness(
        _state["individuals"], _state["families"], progress_cb=progress_cb)
    _state["completeness_rows"]    = cr
    _state["completeness_surname"] = sr
    _state["completeness_epoch"]   = er


# ── Schritt 12: Netzwerk ──────────────────────────────────────────────────────

def run_network(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.network import run as _run
    _state["network_results"] = _run(
        _state["individuals"], _state["families"],
        cfg.DEFAULT_CONFIG["root_id"], progress_cb=progress_cb)


# ── Schritt 13: Osnabrück ─────────────────────────────────────────────────────

def run_osnabrueck(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.osnabrueck import (analyze_persons_by_municipality,
                                   create_municipality_summary)
    res = analyze_persons_by_municipality(
        _state["individuals"], _state["families"],
        _state["location_data"], progress_cb=progress_cb)
    _state["osnabrueck_results"]   = res
    _state["osnabrueck_summaries"] = create_municipality_summary(res)


# ── Schritt 14: Excel-Export ──────────────────────────────────────────────────

def run_export_excel(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks import export as _exp
    from tasks import (cousins, endogamy, migration, military, demographics,
                        genetics, history, names, data_quality, network, osnabrueck)

    _p(progress_cb, "Baue Sheet-Liste …")
    indiv = _state["individuals"]
    ld    = _state["location_data"]
    ht    = _state.get("historical_trends", {})
    scn   = _state.get("survival_cohort_names", [])

    all_sheets = [
        ("Cousin Beziehungen", cousins.HEADERS,
         _state["output_rows"][:200_000]),

        ("Endogamie Scores", endogamy.ENDOGAMY_HEADERS,
         _state["endogamy_results"][:5000]),

        ("Top Ahnen", endogamy.TOP_ANCESTOR_HEADERS,
         _state["top_ancestors"]),

        ("Migrationsrouten Detail", migration.DETAIL_HEADERS,
         _state["migration_results"][:10_000]),

        ("Migrationsrouten Compressed", migration.COMPRESSED_HEADERS,
         _state["compressed_migration"][:10_000]),

        ("Generationen Längen", history.GENERATION_HEADERS,
         _state["generation_lengths"][:200]),

        ("Migrationswellen", migration.WAVES_HEADERS,
         _state["migration_waves"][:100]),

        ("Korrelation Migration-Demografie", migration.CORRELATION_HEADERS,
         _state["correlation_results"][:10_000]),

        ("Familiennetzwerkanalyse", network.NETWORK_HEADERS_FAST,
         _state["network_results"][:10_000]),

        ("Historische Trends (Jahrhunderte)", history.CENTURY_HEADERS,
         ht.get("century_trends", [])[:100]),

        ("Historische Trends (Jahrzehnte)", history.DECADE_HEADERS,
         ht.get("decade_trends", [])[:200]),

        ("Demografische Statistik", demographics.DEMOGRAPHIC_HEADERS,
         _state["demographic_results"][:200]),

        ("Familiennamen Häufigkeit", demographics.SURNAME_HEADERS,
         _state["surname_results"][:500]),

        ("Geburtsland Verteilung", demographics.COUNTRY_HEADERS,
         _state["country_dist_results"][:200]),

        ("Umfassende Statistiken", demographics.STATS_HEADERS,
         _state["comprehensive_stats"]),

        ("Inzuchtkoeffizient", genetics.INBREEDING_HEADERS,
         _state["inbreeding_results"][:50_000]),

        ("Pedigree Collapse Generationen", genetics.PEDIGREE_GEN_HEADERS,
         _state["pedigree_gen_rows"]),

        ("Pedigree Collapse Mehrfach", genetics.PEDIGREE_MULTI_HEADERS,
         _state["pedigree_multi_rows"][:10_000]),

        ("Hist. Kontext Ereignisse", history.HIST_EVENT_HEADERS,
         _state["hist_event_rows"]),

        ("Hist. Kontext Personen", history.HIST_PERSON_HEADERS,
         _state["hist_person_rows"][:10_000]),

        ("Datenvollständigkeit Personen", data_quality.PERSON_HEADERS,
         _state["completeness_rows"][:50_000]),

        ("Datenvollständigkeit Nachnamen", data_quality.SURNAME_HEADERS,
         _state["completeness_surname"][:500]),

        ("Datenvollständigkeit Epochen", data_quality.EPOCH_HEADERS,
         _state["completeness_epoch"]),

        ("Namensvarianten (Kölner Phonetik)", names.VARIANT_HEADERS,
         _state["soundex_variant_rows"][:2000]),

        ("Namensvarianten Personen", names.PERSON_VARIANT_HEADERS,
         _state["soundex_person_rows"][:50_000]),

        (["Überlebenskurven",
          history.SURVIVAL_CURVE_HEADERS + scn,
          _state["survival_curve_rows"]]
         if scn else None),

        ("Überleben Kohorten", history.SURVIVAL_SUMMARY_HEADERS,
         _state["survival_summary_rows"]),

        ("Militärdienst Details", military.MILITARY_HEADERS,
         _state["military_results"][:10_000]),

        _exp.build_symbol_sheet(indiv),
        _exp.build_gedcom_events_sheet(indiv),
        _exp.build_location_info_sheet(ld),
    ]

    # Osnabrück-Sheets
    os_res = _state.get("osnabrueck_results", {})
    os_sum = _state.get("osnabrueck_summaries", {})
    if os_sum:
        from tasks.osnabrueck import (build_overview_rows, build_detail_rows,
                                       OVERVIEW_HEADERS, DETAIL_HEADERS,
                                       MUNICIPALITIES)
        all_sheets.append(("Osnabrück Übersicht", OVERVIEW_HEADERS,
                            build_overview_rows(os_sum)))
        for mkey, persons in os_res.items():
            if not persons: continue
            mname = MUNICIPALITIES[mkey]["name"][:25]
            all_sheets.append((mname, DETAIL_HEADERS, build_detail_rows(persons)))

    # Überlebenskurven-Sonderbehandlung (dynamischer Header)
    if scn:
        all_sheets = [s for s in all_sheets if s is not None
                      and not (isinstance(s, list))]
        all_sheets.append(("Überlebenskurven",
                            history.SURVIVAL_CURVE_HEADERS + scn,
                            _state["survival_curve_rows"]))

    # None-Einträge filtern
    all_sheets = [s for s in all_sheets if s is not None]

    _exp.export_to_excel(all_sheets, cfg.DEFAULT_CONFIG["output_xlsx"],
                          progress_cb=progress_cb)


# ── Schritt 15: JSON-Export ───────────────────────────────────────────────────

def run_export_json(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export import export_to_json
    from datetime import datetime
    summary = {
        "metadata": {
            "version":       "9.0",
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "gedfile":       cfg.DEFAULT_CONFIG["gedfile"],
            "root_id":       cfg.DEFAULT_CONFIG["root_id"],
        },
        "statistics": {
            "individuals":    len(_state["individuals"]),
            "families":       len(_state["families"]),
            "relationships":  len(_state["output_rows"]),
            "migrations":     len(_state["migration_results"]),
        },
        "top_surnames_sample": [r[:2] for r in _state["surname_results"][:20]],
        "top_countries_sample": [r[:2] for r in _state["country_dist_results"][:10]],
    }
    export_to_json(summary, cfg.DEFAULT_CONFIG["output_json"],
                   progress_cb=progress_cb)
