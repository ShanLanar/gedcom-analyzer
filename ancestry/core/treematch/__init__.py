"""
ancestry.core.treematch – Tree-Matching-Paket.

Re-exportiert alle öffentlichen Namen aus den Untermodulen, damit alle
bestehenden Imports (from ancestry.core.treematch import X) und
(from core.treematch import X) weiterhin funktionieren.
"""

# Text-Normalisierung + Personen-Datenmodell
from ._persons import (
    Person,
    _canon_given,
    _fuzzy_overlap,
    _given_tokens,
    _norm,
    _parse_name,
    _person_from_indi,
    _strip_accents,
    _surname_tokens,
    _tok_ratio,
    fuzzy_score,
)

# GEDCOM-Lader und Ahnenlinien
from .gedcom import (
    build_ancestor_map,
    load_gedcom_full,
    load_own_tree,
    mrca_on_direct_line,
    render_kinship,
)

# Genetische Inferenz und Scoring
from .genetics import (
    cluster_confidence,
    cm_to_mrca,
    endogamy_flag,
    longest_to_generation,
    pair_relationship,
)

# Matching-Algorithmen
from .matching import (
    TreeIndex,
    find_root_candidate,
    merge_person_list,
)

__all__ = [
    # _persons
    "_strip_accents",
    "_norm",
    "_tok_ratio",
    "_fuzzy_overlap",
    "_surname_tokens",
    "_canon_given",
    "_given_tokens",
    "Person",
    "fuzzy_score",
    "_parse_name",
    "_person_from_indi",
    # gedcom
    "load_gedcom_full",
    "load_own_tree",
    "build_ancestor_map",
    "render_kinship",
    "mrca_on_direct_line",
    # genetics
    "endogamy_flag",
    "longest_to_generation",
    "cluster_confidence",
    "pair_relationship",
    "cm_to_mrca",
    # matching
    "merge_person_list",
    "find_root_candidate",
    "TreeIndex",
]
