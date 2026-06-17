"""
bridge — Verknüpft den eigenen GEDCOM-Stammbaum mit der Ancestry-DNA-Datenbank.

Phase 1: Importiert GEDCOM-Personen in zwei neue SQLite-Tabellen
(gedcom_persons, gedcom_links) und sucht Kandidaten-Übereinstimmungen
zwischen Vorfahren aus DNA-Match-Ahnentafeln und dem eigenen Baum.

Ähnlichkeits-Hierarchie:
  1. Exact surname match             → score 1.0
  2. Kölner Phonetik match           → score 0.55–0.85
  3. Levenshtein ≤ 2 (≥ 4 Zeichen)  → score 0.40–0.50
  Bonus: Vorname ähnlich             → +0.10
  Bonus: Geburtsjahr ± 10 / ± 15    → +0.0–0.20

Minimaler Link-Score: 0.45

Aufgeteilt in Submodule (öffentliche Import-Oberfläche unverändert):
  _text          — Normalisierung, Kölner Phonetik, String-Distanzen
  scoring        — compute_link_score, MIN_LINK_SCORE
  gedcom_import  — Schema, GEDCOM-/Extern-Import, Sosa, Xref-Deduplikation
  matching       — Match-Abgleich, Seiten-Ableitung, Endogamie, Herkunft
  wikitree       — WikiTree-Anreicherung
"""

# Stdlib-Namen, die historisch über `ancestry.core.bridge` erreichbar waren
# (Rückwärtskompatibilität für `from ... import os` u. Ä.).
import json
import logging
import os
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Optional

log = logging.getLogger(__name__)

from ._text import (
    _extract_region,
    _koelner,
    _lev,
    _levenshtein,
    _name_sim,
    _norm,
    _place_sim,
    _strip_accents,
)
from .gedcom_import import (
    BRIDGE_SCHEMA,
    _build_sosa_map,
    _parse_name_from_indi,
    ensure_tables,
    get_gedcom_person_count,
    get_xref_pairs,
    import_external_persons,
    import_gedcom_persons,
    iter_unique_persons,
    link_duplicates,
    set_xref_status,
)
from .matching import (
    _parse_ancestor_name,
    apply_gedcom_endogamy_to_matches,
    get_gedcom_relationship_summary,
    infer_match_origins,
    infer_side_from_links,
    path_to_sosa,
    run_match_all,
    run_match_for_match,
)
from .scoring import (
    MIN_LINK_SCORE,
    compute_link_score,
)
from .wikitree import wikitree_extend_match

__all__ = [
    # scoring
    "MIN_LINK_SCORE",
    "compute_link_score",
    # gedcom_import
    "BRIDGE_SCHEMA",
    "ensure_tables",
    "import_gedcom_persons",
    "import_external_persons",
    "link_duplicates",
    "get_xref_pairs",
    "set_xref_status",
    "iter_unique_persons",
    "get_gedcom_person_count",
    # matching
    "run_match_for_match",
    "run_match_all",
    "path_to_sosa",
    "infer_side_from_links",
    "get_gedcom_relationship_summary",
    "apply_gedcom_endogamy_to_matches",
    "infer_match_origins",
    # wikitree
    "wikitree_extend_match",
]
