"""
shared_cm.py — Beziehungswahrscheinlichkeit aus geteilten Centimorgan (cM).

Basiert auf dem *Shared cM Project 4.0* (Blaine Bettinger, 2020) — dem
Standard-Referenzdatensatz aus >60.000 eingereichten, verifizierten
Verwandtschaften. Für jede cM-Gruppe sind Mittelwert und beobachteter
Bereich öffentlich dokumentiert.

Statt eine einzige Beziehung pro cM-Bereich zurückzugeben (zu grob),
modellieren wir jede Beziehungsgruppe als Normalverteilung und geben für
einen gegebenen cM-Wert die *relative Wahrscheinlichkeit* über alle
plausiblen Beziehungen zurück — analog zum DNA-Painter-Tool.

Funktion:
    relationship_probabilities(cm) -> list[dict]
        [{ "labels": [...], "probability": 0.0..1.0,
           "mean": float, "low": float, "high": float }, ...]
        absteigend nach Wahrscheinlichkeit sortiert.
"""
from __future__ import annotations
import math

# Jede Gruppe: (deutsche Labels, mean_cM, low_cM, high_cM)
# low/high = beobachteter Bereich (näherungsweise 99-Perzentil-Spanne).
# Beziehungen innerhalb einer Gruppe sind statistisch nicht unterscheidbar.
_GROUPS: list[tuple[list[str], float, float, float]] = [
    (["Elternteil / Kind"],                                 3485, 2376, 3720),
    (["Vollgeschwister"],                                   2613, 1613, 3488),
    (["Großelternteil/-kind", "Onkel/Tante", "Nichte/Neffe",
      "Halbgeschwister"],                                   1759, 1160, 2436),
    (["Urgroßelternteil", "Großonkel/-tante", "1. Cousin",
      "Halb-Onkel/Tante"],                                   866,  396, 1397),
    (["Halb-1. Cousin", "1. Cousin 1× entfernt"],            433,  102,  980),
    (["2. Cousin", "1. Cousin 2× entfernt",
      "Halb-1C 1× entfernt"],                                229,   41,  592),
    (["Halb-2. Cousin", "2. Cousin 1× entfernt"],            122,   14,  353),
    (["3. Cousin", "2. Cousin 2× entfernt"],                  73,    0,  217),
    (["Halb-3. Cousin", "3. Cousin 1× entfernt"],             48,    0,  192),
    (["4. Cousin", "3. Cousin 2× entfernt"],                  35,    0,  139),
    (["4. Cousin 1× entfernt", "Halb-4. Cousin"],             28,    0,  126),
    (["5. Cousin"],                                           25,    0,  117),
    (["6. Cousin und weiter"],                               18,    0,  110),
]


def _sigma(low: float, high: float) -> float:
    """Standardabweichung aus beobachtetem Bereich schätzen (≈ 99-Perzentil
    -> Spanne ≈ 6σ). Untergrenze, damit schmale Gruppen nicht entarten."""
    return max((high - low) / 6.0, 8.0)


def _density(cm: float, mean: float, sigma: float) -> float:
    z = (cm - mean) / sigma
    return math.exp(-0.5 * z * z) / sigma


def relationship_probabilities(cm: float, top: int | None = None) -> list[dict]:
    """Wahrscheinlichkeitsverteilung über Beziehungen für einen cM-Wert.

    Gibt nur Gruppen zurück, deren beobachteter Bereich den cM-Wert plausibel
    enthält (mit kleinem Puffer), normalisiert auf Summe 1.
    """
    if cm is None or cm <= 0:
        return []

    raw = []
    for labels, mean, low, high in _GROUPS:
        sigma = _sigma(low, high)
        # Plausibilitätsfilter: außerhalb low-2σ … high+2σ ignorieren
        if cm < low - 2 * sigma or cm > high + 2 * sigma:
            continue
        d = _density(cm, mean, sigma)
        if d <= 1e-9:
            continue
        raw.append((labels, mean, low, high, d))

    if not raw:
        # Fallback: nächstgelegene Gruppe per Mittelwert
        labels, mean, low, high = min(_GROUPS, key=lambda g: abs(cm - g[1]))
        return [{"labels": labels, "probability": 1.0,
                 "mean": mean, "low": low, "high": high}]

    total = sum(d for *_, d in raw)
    out = [{"labels": labels, "probability": d / total,
            "mean": mean, "low": low, "high": high}
           for labels, mean, low, high, d in raw]
    out.sort(key=lambda r: -r["probability"])
    return out[:top] if top else out


def summary_line(cm: float, top: int = 3) -> str:
    """Einzeiler für UI/Status, z.B. '73% 2. Cousin · 18% Halb-2C · 9% …'."""
    probs = relationship_probabilities(cm, top=top)
    if not probs:
        return "—"
    parts = []
    for p in probs:
        lbl = p["labels"][0]
        parts.append(f"{p['probability']*100:.0f}% {lbl}")
    return "  ·  ".join(parts)


if __name__ == "__main__":
    for cm in (3500, 1800, 850, 245, 122, 73, 35, 12):
        print(f"{cm:>5} cM →  {summary_line(cm, top=3)}")
