"""Endogamie-Score-Berechnung für DNA-Matches (F1)."""

from typing import Optional
from ancestry.models import DnaMatch


def calculate_endogamy_score(shared_segments: int, shared_cm: float) -> float:
    """Calculate endogamy score from shared segments and centimorgans.

    The score represents segments per 10cM average segment length.
    Score = (shared_segments / 10) / (shared_cm / 10) if shared_cm > 0 else 0.0
    Which simplifies to: shared_segments / shared_cm

    Higher scores indicate more segments relative to total cM, characteristic
    of endogamous populations with many short segments.

    Parameters
    ----------
    shared_segments : int
        Number of shared DNA segments
    shared_cm : float
        Total shared centimorgans (cM)

    Returns
    -------
    float
        Endogamy score. Returns 0.0 if shared_cm <= 0 (unreliable data).
        Higher scores indicate higher endogamy risk (many short segments).
    """
    cm = float(shared_cm or 0)
    segs = int(shared_segments or 0)

    if cm <= 0:
        return 0.0

    return segs / cm


def flag_endogamy_matches(
    matches: list[DnaMatch],
    threshold: float = 8.0,
) -> list[tuple[str, float]]:
    """Identify matches with high endogamy scores.

    Filters matches where the endogamy score meets or exceeds the threshold,
    excluding matches with shared_cm < 1.0 (unreliable DNA sharing).

    Parameters
    ----------
    matches : list[DnaMatch]
        List of DNA matches to evaluate
    threshold : float, optional
        Endogamy score threshold (default 8.0 = 8 segments per cM average).
        Matches with score >= threshold are flagged.

    Returns
    -------
    list[tuple[str, float]]
        List of (match_guid, endogamy_score) tuples for matches exceeding threshold.
        Sorted by score descending (highest endogamy first).
    """
    results: list[tuple[str, float]] = []

    for match in matches:
        # Skip matches with unreliable cM values
        if match.shared_cm < 1.0:
            continue

        # Calculate score
        score = calculate_endogamy_score(match.shared_segments, match.shared_cm)

        # Flag if above threshold
        if score >= threshold:
            results.append((match.match_guid, score))

    # Sort by score descending (highest first)
    results.sort(key=lambda x: x[1], reverse=True)

    return results
