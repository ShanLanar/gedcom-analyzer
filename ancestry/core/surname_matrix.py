"""surname_matrix.py – pure functions for surname-overlap similarity analysis.

No tkinter imports; no side effects. All functions operate on plain Python
data structures so they can be unit-tested without a running database.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_surname(s: str) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    return " ".join(s.lower().split())


def get_match_surnames(rows: list[Any]) -> frozenset[str]:
    """Given pedigree rows (each with a ``'surname'`` field), return the set
    of normalized surnames.  Rows where *surname* is falsy are skipped."""
    return frozenset(
        _normalize_surname(r["surname"])
        for r in rows
        if r["surname"]
    )


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity: |a ∩ b| / |a ∪ b|.  Returns 0.0 if both empty."""
    union = a | b
    if not union:
        return 0.0
    return round(len(a & b) / len(union), 4)


def common_surnames(a: frozenset[str], b: frozenset[str]) -> list[str]:
    """Sorted list of surnames present in both sets."""
    return sorted(a & b)


# ---------------------------------------------------------------------------
# Pair computation
# ---------------------------------------------------------------------------

def compute_surname_pairs(
    match_surnames: dict[str, frozenset[str]],
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Compute all unique match pairs with non-zero surname overlap.

    Parameters
    ----------
    match_surnames:
        Mapping ``{match_guid: frozenset_of_normalized_surnames}``.
    min_score:
        Only include pairs whose Jaccard score is >= this threshold.

    Returns
    -------
    List of dicts with keys ``guid_a``, ``guid_b``, ``score``, ``common``,
    ``count``, sorted by *score* descending (ties broken by *count*).
    """
    guids = list(match_surnames.keys())
    pairs: list[dict[str, Any]] = []
    for i in range(len(guids)):
        for j in range(i + 1, len(guids)):
            a, b = guids[i], guids[j]
            score = jaccard(match_surnames[a], match_surnames[b])
            if score >= min_score:
                common = common_surnames(match_surnames[a], match_surnames[b])
                if common:
                    pairs.append(
                        {
                            "guid_a": a,
                            "guid_b": b,
                            "score": score,
                            "common": common,
                            "count": len(common),
                        }
                    )
    pairs.sort(key=lambda x: (-x["score"], -x["count"]))
    return pairs
