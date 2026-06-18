"""Endogamie-Heuristik für DNA-Matches.

Endogame Populationen erzeugen viele *kurze* gemeinsame Segmente (IBD-Rauschen)
statt weniger langer. Kennzeichen eines Verdachtsfalls:
  - hohe Segmentzahl, aber
  - kleine durchschnittliche Segmentlänge (cM/Segment).

Der Score ``Segmente / (cM + 1)`` ist hoch, wenn viele Segmente auf wenig cM
entfallen – konsistent mit der bestehenden SQL-Auswertung
(MatchesRepo.get_endogamy_candidates).
"""
from __future__ import annotations


def endogamy_score(shared_cm, shared_segments) -> float:
    """Segmente pro (cM+1). Hoch = viele kurze Segmente = Endogamie-Verdacht."""
    cm = float(shared_cm or 0)
    segs = int(shared_segments or 0)
    return segs / (cm + 1.0)


def avg_segment_cm(shared_cm, shared_segments) -> float:
    """Durchschnittliche Segmentlänge in cM (0 wenn keine Segmente)."""
    segs = int(shared_segments or 0)
    return (float(shared_cm or 0) / segs) if segs else 0.0


def is_endogamy_suspect(shared_cm, shared_segments,
                        score_threshold: float = 0.15,
                        min_segments: int = 5,
                        max_avg_cm: float = 12.0) -> bool:
    """True, wenn ein Match nach Heuristik Endogamie-verdächtig ist:
    genügend Segmente (``min_segments``), kleine Durchschnittslänge
    (< ``max_avg_cm``) und Score über ``score_threshold``."""
    cm = float(shared_cm or 0)
    segs = int(shared_segments or 0)
    if cm <= 0 or segs < min_segments:
        return False
    return (endogamy_score(cm, segs) > score_threshold
            and avg_segment_cm(cm, segs) < max_avg_cm)
