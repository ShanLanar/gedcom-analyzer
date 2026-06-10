"""
ancestry.core.treematch – Tree-Matching-Paket.

Re-exportiert alle öffentlichen Namen aus den Untermodulen, damit alle
bestehenden Imports (from ancestry.core.treematch import X) und
(from core.treematch import X) weiterhin funktionieren.
"""

# Text-Normalisierung + Personen-Datenmodell
from ._persons import (
    _strip_accents,
    _norm,
    _tok_ratio,
    _fuzzy_overlap,
    _surname_tokens,
    _canon_given,
    _given_tokens,
    Person,
    fuzzy_score,
    _parse_name,
    _person_from_indi,
)

# GEDCOM-Lader und Ahnenlinien
from .gedcom import (
    load_gedcom_full,
    load_own_tree,
    build_ancestor_map,
    render_kinship,
    mrca_on_direct_line,
)

# Genetische Inferenz und Scoring
from .genetics import (
    endogamy_flag,
    longest_to_generation,
    cluster_confidence,
    pair_relationship,
    cm_to_mrca,
)

# Matching-Algorithmen
from .matching import (
    merge_person_list,
    find_root_candidate,
    TreeIndex,
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
