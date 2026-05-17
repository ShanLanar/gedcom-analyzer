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
from tasks.context import AnalysisContext

# ── Shared State ───────────────────────────────────────────────────────────────
# Dataclass in tasks/context.py; unterstützt sowohl Attribut- als auch
# dict-Zugriff, damit alle bestehenden _state["x"]-Aufrufe weiterlaufen.
_state: AnalysisContext = AnalysisContext()


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
    from tasks.genetics import clear_genetics_cache

    lg = setup_logging(cfg.FILES.get("log_file"))
    gl_set(lg); pl_set(lg)
    clear_migration_status_cache()
    clear_genetics_cache()

    _p(progress_cb, "Lade Ortsdaten …")
    _state["location_data"] = load_location_data(cfg.DEFAULT_CONFIG["location_data_json"])

    gedfile = cfg.DEFAULT_CONFIG["gedfile"]
    from tasks.import_ftm import is_ftm_file, load_ftm, set_logger as ftm_set
    ftm_set(lg)
    if is_ftm_file(gedfile):
        _p(progress_cb, f"Lade FTM-Datei: {gedfile} …")
        indiv, fams = load_ftm(gedfile, progress_cb=progress_cb)
    else:
        _p(progress_cb, f"Lade GEDCOM: {gedfile} …")
        indiv, fams = robust_load_gedcom(gedfile)
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
                        genetics, history, names, data_quality, network, osnabrueck,
                        anomalies, seasonality, snapshot, spatial,
                        family_structure, lineage, naming, imputation,
                        brickwalls, research_suggestions, sources,
                        onomastics, endogamy_network)

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

        # Neue Analysen (nur wenn Task gelaufen)
        ("Daten-Anomalien", anomalies.ANOMALY_HEADERS,
         _state.get("anomaly_results", [])[:50_000]),

        ("Potenzielle Doubletten", anomalies.DUPLICATE_HEADERS,
         _state.get("duplicate_results", [])[:10_000]),

        ("Unerreichbare Personen", anomalies.ISLAND_HEADERS,
         _state.get("island_results", [])[:50_000]),

        ("DNA-cM-Schätzung", genetics.DNA_CM_HEADERS,
         _state.get("dna_cm_results", [])[:50_000]),

        ("Geschwister-Statistiken", demographics.SIBLING_HEADERS,
         _state.get("sibling_results", [])[:20_000]),

        ("Namensdrift (Vornamen)", demographics.NAMEDRIFT_HEADERS,
         _state.get("namedrift_results", [])[:500]),

        # ── Saisonalität ───────────────────────────────────────────────────────
        ("Geburts-Monate", seasonality.BIRTH_MONTH_HEADERS,
         _state.get("birth_months", [])),
        ("Heirats-Monate", seasonality.MARRIAGE_MONTH_HEADERS,
         _state.get("marriage_months", [])),
        ("Sterbe-Monate", seasonality.DEATH_MONTH_HEADERS,
         _state.get("death_months", [])),
        ("Empfängnis-Monate (geschätzt)", seasonality.CONCEPTION_MONTH_HEADERS,
         _state.get("conception_months", [])),

        # ── Stichjahr-Snapshot + Generationen-Overlap ─────────────────────────
        ("Stichjahr-Snapshot", snapshot.SNAPSHOT_HEADERS,
         _state.get("snapshot_rows", [])),
        ("Lebende Generationen", snapshot.GEN_OVERLAP_HEADERS,
         _state.get("gen_overlap_rows", [])),

        # ── Räumliche Lebensgeschichte ────────────────────────────────────────
        ("Heirats-Migration", spatial.MARRIAGE_MIGRATION_HEADERS,
         _state.get("marriage_migration", [])[:50_000]),
        ("Lebens-Triangulation", spatial.LIFE_TRIANGULATION_HEADERS,
         _state.get("life_triangulation", [])[:50_000]),
        ("Sesshaftigkeit pro Familie", spatial.SEDENTARINESS_HEADERS,
         _state.get("sedentariness", [])[:30_000]),
        ("Nachname × Region", spatial.SURNAME_REGION_HEADERS,
         _state.get("surname_region_matrix", [])[:10_000]),

        # ── Familienstruktur ───────────────────────────────────────────────────
        ("Mehrfach-Ehen", family_structure.MULTIPLE_MARRIAGES_HEADERS,
         _state.get("multiple_marriages", [])[:10_000]),
        ("Alters-Differenz Ehepaare", family_structure.SPOUSE_AGE_GAP_HEADERS,
         _state.get("spouse_age_gap", [])),
        ("Reproduktive Spanne (Mütter)", family_structure.REPRODUCTIVE_SPAN_HEADERS,
         _state.get("reproductive_span", [])[:30_000]),
        ("Kinderlosigkeits-Rate", family_structure.CHILDLESSNESS_HEADERS,
         _state.get("childlessness", [])),
        ("Zwillinge / Mehrfachgeburten", family_structure.TWIN_HEADERS,
         _state.get("twin_results", [])[:10_000]),

        # ── Linien (Y, Mt, Quartile, Aussterben, Verzweigung) ─────────────────
        ("Y-Linie (paternal)", lineage.Y_LINE_HEADERS,
         _state.get("y_line", [])),
        ("Mt-Linie (maternal)", lineage.MT_LINE_HEADERS,
         _state.get("mt_line", [])),
        ("Großeltern-Quartile", lineage.QUARTILE_HEADERS,
         _state.get("quartile_results", [])),
        ("Linien-Aussterben", lineage.EXTINCTION_HEADERS,
         _state.get("extinction_results", [])[:10_000]),
        ("Verzweigungs-Faktor", lineage.BRANCHING_HEADERS,
         _state.get("branching_factor", [])),

        # ── Namens-Soziologie ─────────────────────────────────────────────────
        ("Patronyme", naming.PATRONYM_HEADERS,
         _state.get("patronyms", [])[:30_000]),
        ("Junior-Detektor", naming.JUNIOR_HEADERS,
         _state.get("juniors", [])[:30_000]),
        ("Familien-Vornamen-Pool", naming.FAMILY_NAME_POOL_HEADERS,
         _state.get("family_name_pool", [])[:200]),

        # ── Daten-Imputation ──────────────────────────────────────────────────
        ("Geschätzte fehlende Daten", imputation.IMPUTATION_HEADERS,
         _state.get("imputation_results", [])[:50_000]),

        # ── Krisen-Kohorten + Eltern-Verlust ──────────────────────────────────
        ("Krisen-Kohorten Folge", history.CRISIS_COHORT_HEADERS,
         _state.get("crisis_cohort", [])),
        ("Eltern-Verlust-Alter", history.PARENTAL_LOSS_HEADERS,
         _state.get("parental_loss", [])),

        # ── Forschungs-Helfer (Brickwalls, Vorschläge, Quellen) ──────────────
        ("Brick-Wall-Detektor", brickwalls.BRICKWALL_HEADERS,
         _state.get("brickwall_results", [])[:10_000]),
        ("Forschungs-Vorschläge", research_suggestions.RESEARCH_SUGGESTION_HEADERS,
         _state.get("research_suggestions", [])[:5_000]),
        ("Quellen-Inventar", sources.SOURCE_INVENTORY_HEADERS,
         _state.get("source_inventory", [])[:10_000]),
        ("Quellen-Qualität pro Person", sources.SOURCE_QUALITY_HEADERS,
         _state.get("source_quality", [])[:50_000]),

        # ── Onomastik + Endogamie-Bigraph ─────────────────────────────────────
        ("Onomastik (Namensmuster)", onomastics.ONOMASTICS_HEADERS,
         _state.get("onomastics_results", [])[:1_000]),
        ("Endogamie-Netzwerk (Nachname×Nachname)",
         endogamy_network.ENDOGAMY_NETWORK_HEADERS,
         _state.get("endogamy_network", [])[:500]),
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

def run_export_html(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export import export_html_overview
    export_html_overview(_state, cfg.FILES["interactive_html"],
                          progress_cb=progress_cb)


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


# ── Schritt 16: Anomalien / Doubletten / Inseln ───────────────────────────────

def run_anomalies(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.anomalies import detect_anomalies, detect_duplicates, detect_islands
    _state["anomaly_results"]   = detect_anomalies(
        _state["individuals"], _state["families"], progress_cb=progress_cb)
    _state["duplicate_results"] = detect_duplicates(
        _state["individuals"], progress_cb=progress_cb)
    _state["island_results"]    = detect_islands(
        cfg.DEFAULT_CONFIG["root_id"],
        _state["individuals"], _state["families"], progress_cb=progress_cb)


# ── Schritt 17: DNA-cM-Schätzung ─────────────────────────────────────────────

def run_dna_cm(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.genetics import analyze_dna_cm_estimates
    _state["dna_cm_results"] = analyze_dna_cm_estimates(
        cfg.DEFAULT_CONFIG["root_id"],
        _state["individuals"], _state["families"],
        root_related_ids=_state.get("root_related_ids"),
        progress_cb=progress_cb)


# ── Schritt 18: Geschwister-Statistiken + Namensdrift ────────────────────────

def run_sibling_and_namedrift(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.demographics import analyze_sibling_statistics, analyze_name_drift
    _state["sibling_results"]   = analyze_sibling_statistics(
        _state["individuals"], _state["families"], progress_cb=progress_cb)
    _state["namedrift_results"] = analyze_name_drift(
        _state["individuals"], progress_cb=progress_cb)


# ── Schritt 19: GraphML-Export ────────────────────────────────────────────────

def run_export_graphml(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export_graphml import export_graphml
    export_graphml(
        _state["individuals"], _state["families"],
        cfg.FILES["output_graphml"],
        root_id=cfg.DEFAULT_CONFIG["root_id"],
        root_related_ids=_state.get("root_related_ids"),
        progress_cb=progress_cb)


# ── Schritt 20: Timeline-HTML ────────────────────────────────────────────────

def run_export_timeline(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export import export_timeline_html
    export_timeline_html(
        _state["individuals"], _state["families"],
        cfg.FILES["timeline_html"],
        root_related_ids=_state.get("root_related_ids"),
        progress_cb=progress_cb)


# ── Schritt 21: Saisonalität (Geburts-/Heirats-/Sterbe-/Empfängnis-Monate) ───

def run_seasonality(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.seasonality import (analyze_birth_months, analyze_marriage_months,
                                    analyze_death_months, analyze_conception_months)
    _state["birth_months"]      = analyze_birth_months(_state["individuals"],
                                                        progress_cb=progress_cb)
    _state["marriage_months"]   = analyze_marriage_months(_state["families"],
                                                          progress_cb=progress_cb)
    _state["death_months"]      = analyze_death_months(_state["individuals"],
                                                       progress_cb=progress_cb)
    _state["conception_months"] = analyze_conception_months(_state["individuals"],
                                                            progress_cb=progress_cb)


# ── Schritt 22: Stichjahr-Snapshot + Lebende-Generationen-Overlap ────────────

def run_snapshot(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.snapshot import snapshot_at_years, analyze_living_generations
    _state["snapshot_rows"]    = snapshot_at_years(_state["individuals"],
                                                    progress_cb=progress_cb)
    _state["gen_overlap_rows"] = analyze_living_generations(
        _state["individuals"], _state["families"],
        cfg.DEFAULT_CONFIG["root_id"], progress_cb=progress_cb)


# ── Schritt 23: Räumliche Analysen ────────────────────────────────────────────

def run_spatial(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.spatial import (analyze_marriage_migration, analyze_life_triangulation,
                                analyze_sedentariness, analyze_surname_region_matrix)
    indiv = _state["individuals"]
    fams  = _state["families"]
    ld    = _state["location_data"]
    rid   = cfg.DEFAULT_CONFIG["root_id"]

    _state["marriage_migration"]   = analyze_marriage_migration(
        indiv, fams, ld, progress_cb=progress_cb)
    _state["life_triangulation"]   = analyze_life_triangulation(
        indiv, fams, progress_cb=progress_cb)
    _state["sedentariness"]        = analyze_sedentariness(
        indiv, fams, rid, ld, progress_cb=progress_cb)
    _state["surname_region_matrix"] = analyze_surname_region_matrix(
        indiv, ld, progress_cb=progress_cb)


# ── Schritt 24: Familienstruktur ──────────────────────────────────────────────

def run_family_structure(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.family_structure import (analyze_multiple_marriages,
                                         analyze_spouse_age_gap,
                                         analyze_reproductive_span,
                                         analyze_childlessness, detect_twins)
    indiv = _state["individuals"]
    fams  = _state["families"]
    _state["multiple_marriages"]   = analyze_multiple_marriages(
        indiv, fams, progress_cb=progress_cb)
    _state["spouse_age_gap"]       = analyze_spouse_age_gap(
        indiv, fams, progress_cb=progress_cb)
    _state["reproductive_span"]    = analyze_reproductive_span(
        indiv, fams, progress_cb=progress_cb)
    _state["childlessness"]        = analyze_childlessness(
        indiv, fams, progress_cb=progress_cb)
    _state["twin_results"]         = detect_twins(
        indiv, fams, progress_cb=progress_cb)


# ── Schritt 25: Linien-Analysen (Y/Mt, Quartile, Aussterben, Verzweigung) ───

def run_lineage(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.lineage import (trace_y_line, trace_mt_line,
                                analyze_grandparent_quartiles,
                                detect_lineage_extinction, analyze_branching_factor)
    indiv = _state["individuals"]
    fams  = _state["families"]
    ld    = _state["location_data"]
    rid   = cfg.DEFAULT_CONFIG["root_id"]

    _state["y_line"]             = trace_y_line(rid, indiv, fams,
                                                 progress_cb=progress_cb)
    _state["mt_line"]            = trace_mt_line(rid, indiv, fams,
                                                  progress_cb=progress_cb)
    _state["quartile_results"]   = analyze_grandparent_quartiles(
        rid, indiv, fams, ld, progress_cb=progress_cb)
    _state["extinction_results"] = detect_lineage_extinction(
        indiv, fams, progress_cb=progress_cb)
    _state["branching_factor"]   = analyze_branching_factor(
        rid, indiv, fams, progress_cb=progress_cb)


# ── Schritt 26: Namens-Soziologie (Patronyme, Junioren, Vornamen-Pool) ───────

def run_naming_sociology(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.naming import (detect_patronyms, detect_juniors,
                               analyze_family_name_pool)
    indiv = _state["individuals"]
    fams  = _state["families"]
    _state["patronyms"]         = detect_patronyms(indiv, fams,
                                                    progress_cb=progress_cb)
    _state["juniors"]           = detect_juniors(indiv, fams,
                                                  progress_cb=progress_cb)
    _state["family_name_pool"]  = analyze_family_name_pool(indiv, fams,
                                                            progress_cb=progress_cb)


# ── Schritt 27: Daten-Imputation ──────────────────────────────────────────────

def run_imputation(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.imputation import impute_missing_dates
    _state["imputation_results"] = impute_missing_dates(
        _state["individuals"], _state["families"], progress_cb=progress_cb)


# ── Schritt 28: Krisen-Kohorten + Eltern-Verlust ─────────────────────────────

def run_cohort_extensions(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.history import (analyze_crisis_cohort_followup,
                                analyze_parental_loss_age)
    indiv = _state["individuals"]
    fams  = _state["families"]
    _state["crisis_cohort"] = analyze_crisis_cohort_followup(
        indiv, fams, progress_cb=progress_cb)
    _state["parental_loss"] = analyze_parental_loss_age(
        indiv, fams, progress_cb=progress_cb)


# ── Schritt 29: Brick-Wall-Detektor + Forschungs-Vorschläge + Quellen ───────

def run_research_helpers(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.brickwalls import detect_brickwalls
    from tasks.research_suggestions import generate_research_suggestions
    from tasks.sources import analyze_sources

    indiv = _state["individuals"]
    fams  = _state["families"]
    _state["brickwall_results"]   = detect_brickwalls(indiv, fams,
                                                       progress_cb=progress_cb)
    _state["research_suggestions"] = generate_research_suggestions(
        indiv, fams, progress_cb=progress_cb)
    inv, qual = analyze_sources(
        indiv, fams, cfg.DEFAULT_CONFIG["gedfile"], progress_cb=progress_cb)
    _state["source_inventory"] = inv
    _state["source_quality"]   = qual


# ── Schritt 30: Onomastik + Endogamie-Bigraph ────────────────────────────────

def run_onomastics_and_endogamy_net(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.onomastics import analyze_onomastics
    from tasks.endogamy_network import (analyze_endogamy_bigraph,
                                          export_endogamy_graphml)
    indiv = _state["individuals"]
    fams  = _state["families"]
    _state["onomastics_results"] = analyze_onomastics(indiv,
                                                       progress_cb=progress_cb)
    _state["endogamy_network"]   = analyze_endogamy_bigraph(
        indiv, fams, progress_cb=progress_cb)
    # GraphML-Datei der Endogamie-Bigraph mit ausgeben
    out_path = os.path.join(cfg.DIRS.get("output", "."), "endogamy_network.graphml")
    export_endogamy_graphml(indiv, fams, out_path, progress_cb=progress_cb)


# ── Schritt 31: Visualisierungs-Exporte ──────────────────────────────────────

def run_export_fanchart(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export_fanchart import export_fanchart_svg
    out_path = os.path.join(cfg.DIRS.get("output", "."), "fan_chart.svg")
    export_fanchart_svg(cfg.DEFAULT_CONFIG["root_id"],
                        _state["individuals"], _state["families"],
                        out_path, progress_cb=progress_cb)


def run_export_dashboard(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export_dashboard import export_dashboard_html
    out_path = os.path.join(cfg.DIRS.get("output", "."), "dashboard.html")
    export_dashboard_html(_state, out_path, progress_cb=progress_cb)


def run_export_heatmap(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export_heatmap import export_birth_heatmap
    out_path = os.path.join(cfg.DIRS.get("output", "."), "birth_heatmap.html")
    export_birth_heatmap(_state["individuals"], _state["location_data"],
                          out_path, progress_cb=progress_cb)


def run_export_subtree_descendants(progress_cb=None, stop_event=None):
    """Exportiert die Nachfahren der Root als eigene GEDCOM."""
    _set_stop_event(stop_event)
    from tasks.extract_subtree import extract_descendants, write_gedcom
    indiv_sub, fams_sub = extract_descendants(
        cfg.DEFAULT_CONFIG["root_id"],
        _state["individuals"], _state["families"],
        progress_cb=progress_cb)
    out_path = os.path.join(cfg.DIRS.get("output", "."), "descendants.ged")
    write_gedcom(indiv_sub, fams_sub, out_path, progress_cb=progress_cb)


def run_export_subtree_ancestors(progress_cb=None, stop_event=None):
    """Exportiert die Vorfahren der Root als eigene GEDCOM."""
    _set_stop_event(stop_event)
    from tasks.extract_subtree import extract_ancestors, write_gedcom
    indiv_sub, fams_sub = extract_ancestors(
        cfg.DEFAULT_CONFIG["root_id"],
        _state["individuals"], _state["families"],
        progress_cb=progress_cb)
    out_path = os.path.join(cfg.DIRS.get("output", "."), "ancestors.ged")
    write_gedcom(indiv_sub, fams_sub, out_path, progress_cb=progress_cb)


def run_export_sankey(progress_cb=None, stop_event=None):
    _set_stop_event(stop_event)
    from tasks.export_sankey import export_migration_sankey
    from tasks.migration import DETAIL_HEADERS
    # Spalten-Indizes aus DETAIL_HEADERS suchen (fallback 4/7)
    header_map = {}
    for key, name in (("from_country", "Geburtsland"),
                       ("to_country", "Sterbeland")):
        for i, h in enumerate(DETAIL_HEADERS):
            if name in str(h):
                header_map[key] = i
                break
    out_path = os.path.join(cfg.DIRS.get("output", "."), "migration_sankey.html")
    export_migration_sankey(_state.get("migration_results", []), header_map,
                             out_path, progress_cb=progress_cb)


# ── Schritt 32: State-Cache (Incremental Run) ────────────────────────────────

def _cache_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".ahnen-cache.pkl")


def _gedcom_hash(filepath: str) -> str | None:
    """SHA-256 des GEDCOM-Inhalts; None wenn die Datei fehlt."""
    import hashlib
    if not os.path.exists(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def save_state_cache(progress_cb=None, stop_event=None):
    """Persistiert _state nach ~/.ahnen-cache.pkl. Cache und stop_event werden
    vorher genullt, da sie nicht sinnvoll persistierbar sind."""
    _set_stop_event(stop_event)
    p = progress_cb or (lambda m, **kw: None)
    import pickle
    path = _cache_path()
    indiv_count = len(_state.get("individuals", {}))
    if indiv_count == 0:
        p("Kein State zum Speichern (lade vorher GEDCOM)", tag="warn")
        return
    p(f"Speichere State-Cache: {path} …")
    # Nicht-serialisierbare Felder zwischenspeichern und nullen
    saved_cache = _state.cache
    saved_stop  = _state.stop_event
    _state.cache = None
    _state.stop_event = None
    try:
        gh = _gedcom_hash(cfg.DEFAULT_CONFIG["gedfile"])
        payload = {
            "version":    1,
            "gedcom_hash": gh,
            "gedfile":     cfg.DEFAULT_CONFIG["gedfile"],
            "state":       _state,
        }
        with open(path, "wb") as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        size_mb = os.path.getsize(path) / 1_048_576
        p(f"State-Cache gespeichert ({size_mb:.1f} MB, {indiv_count:,} Personen)",
          tag="ok")
    except Exception as e:
        p(f"State-Cache fehlgeschlagen: {e}", tag="err")
    finally:
        _state.cache = saved_cache
        _state.stop_event = saved_stop


def load_state_cache(progress_cb=None, stop_event=None):
    """Lädt _state aus ~/.ahnen-cache.pkl, wenn der GEDCOM-Hash passt.
    Ersetzt den globalen _state. Macht keine GEDCOM-Re-Analyse, wenn der
    Cache aktuell ist — danach reicht es, nur die Export-Tasks zu wählen."""
    global _state
    _set_stop_event(stop_event)
    p = progress_cb or (lambda m, **kw: None)
    import pickle
    path = _cache_path()
    if not os.path.exists(path):
        p("Kein State-Cache vorhanden", tag="warn")
        return
    try:
        with open(path, "rb") as f:
            payload = pickle.load(f)
    except Exception as e:
        p(f"State-Cache lesen fehlgeschlagen: {e}", tag="err")
        return

    cached_hash = payload.get("gedcom_hash")
    cur_hash    = _gedcom_hash(cfg.DEFAULT_CONFIG["gedfile"])
    if cached_hash and cur_hash and cached_hash != cur_hash:
        p("Cache ist veraltet (GEDCOM hat sich geändert) — bitte voll neu rechnen",
          tag="warn")
        return
    cached_state = payload.get("state")
    if cached_state is None:
        p("Cache ist leer oder beschädigt", tag="err")
        return

    _state = cached_state
    _state.stop_event = stop_event
    indiv = len(_state.get("individuals", {}))
    fams  = len(_state.get("families", {}))
    p(f"State-Cache geladen: {indiv:,} Personen, {fams:,} Familien (GEDCOM unverändert)",
      tag="ok")
