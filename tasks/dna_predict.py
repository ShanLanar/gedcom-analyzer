# -*- coding: utf-8 -*-
"""tasks/dna_predict.py – DNA-basierte Verwandtschaftsschätzung.

Zwei Werkzeuge:

1. `predict_relationship_from_cm(cm)` – Ohne Stammbaum: liefert die
   wahrscheinlichsten Verwandtschaftsgrade zu einem gemessenen cM-Wert
   anhand einer Gauß-Approximation der bekannten Verteilungen.

2. `match_dna_to_tree(observed_cm, root_id, individuals, families)` –
   Vergleicht den gemessenen cM-Wert mit den aus dem Stammbaum berechneten
   Erwartungswerten (Φ × 2 × 7000 cM) und gibt die besten Treffer aus.
"""

import math

from lib.gedcom import safe_extract_year
from tasks.genetics import _kinship_coefficient


# ── Verteilungen ──────────────────────────────────────────────────────────────

# (Label, mean_cM, std_cM)
_RELATIONSHIP_DIST = [
    ("Elternteil/Kind",            3485, 100),
    ("Geschwister voll",           2629, 400),
    ("Halbgeschwister",            1759, 250),
    ("Großelternteil",             1766, 250),
    ("Onkel/Tante",                1759, 250),
    ("Cousin 1. Grades",            866, 200),
    ("Cousin 1. einmal entfernt",   433, 130),
    ("Cousin 2. Grades",            229,  90),
    ("Cousin 2. einmal entfernt",   122,  50),
    ("Cousin 3. Grades",             73,  30),
    ("Cousin 4. Grades",             35,  15),
]


PREDICT_HEADERS = ["Beziehung", "Wahrscheinlichkeit %"]


def _gauss_pdf(x, mu, sigma):
    """Standard-Gauß-Dichte (Normalisierung wird gleich rausnormiert,
    aber sigma im Vorfaktor ist wichtig fürs Verhältnis der Klassen)."""
    if sigma <= 0:
        return 0.0
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


def predict_relationship_from_cm(target_cm):
    """Top-5 Verwandtschaftsbeziehungen für einen gemessenen cM-Wert.

    Returns
    -------
    list[tuple[str, float]]
        Liste (Label, Wahrscheinlichkeit) absteigend, summiert auf 1.0.
    """
    try:
        target = float(target_cm)
    except (TypeError, ValueError):
        return []

    densities = []
    for label, mu, sigma in _RELATIONSHIP_DIST:
        d = _gauss_pdf(target, mu, sigma)
        densities.append((label, d))

    total = sum(d for _, d in densities)
    if total <= 0:
        # Weit außerhalb aller Verteilungen – alle gleich unwahrscheinlich.
        return []

    normalized = [(lbl, d / total) for lbl, d in densities]
    normalized.sort(key=lambda kv: kv[1], reverse=True)
    return normalized[:5]


def predict_relationship_rows(target_cm):
    """Sheet-Generator-Variante: liefert Rows passend zu PREDICT_HEADERS."""
    rows = []
    for lbl, prob in predict_relationship_from_cm(target_cm):
        rows.append([lbl, round(prob * 100.0, 2)])
    return rows


# ── Match gegen Stammbaum ─────────────────────────────────────────────────────

DNA_MATCH_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr",
    "Geschätztes cM (aus Stammbaum)", "Match-Score (0-1)",
    "Erläuterung",
]

_MATCH_SIGMA = 200.0  # cM, fest gem. Spezifikation


def match_dna_to_tree(observed_cm, root_id, individuals, families,
                      progress_cb=None):
    """Vergleicht einen gemessenen cM-Wert mit allen Stammbaum-Verwandten.

    Für jede Person mit Φ > 0 wird das erwartete cM = Φ × 2 × 7000 berechnet
    und ein Match-Score = exp(-((observed - expected)^2) / (2 · 200²))
    bestimmt.  Es werden die Top-50 Treffer (nach Score absteigend) ausgegeben.
    """
    p = progress_cb or (lambda m, **kw: None)
    p(f"DNA-Match gegen Stammbaum (observed = {observed_cm} cM) …")

    try:
        obs = float(observed_cm)
    except (TypeError, ValueError):
        p("Ungültiger cM-Wert.", tag="err")
        return []

    if root_id not in individuals:
        p(f"Wurzel {root_id} nicht im Individuen-Dict.", tag="err")
        return []

    sigma_sq2 = 2.0 * (_MATCH_SIGMA ** 2)
    results = []

    total = len(individuals)
    for i, (pid, pdata) in enumerate(individuals.items()):
        if i % 2000 == 0 and i > 0:
            p(f"  DNA-Match: {i:,}/{total:,} …")

        if pid == root_id or not pdata:
            continue

        phi = _kinship_coefficient(root_id, pid, individuals, families,
                                    max_depth=10)
        if phi <= 0.0:
            continue

        expected = phi * 2.0 * 7000.0
        diff = obs - expected
        score = math.exp(-(diff * diff) / sigma_sq2)

        name = pdata.get("NAME") or ""
        birt = pdata.get("BIRT") or {}
        byr = birt.get("YEAR") or safe_extract_year(birt.get("DATE")) or ""

        erlaeut = (f"Beobachtet: {round(obs, 1)}, "
                   f"Stammbaum-Schätzung: {round(expected, 1)}, "
                   f"Δ: {round(diff, 1)}")

        results.append([
            pid, name, byr,
            round(expected, 1), round(score, 4),
            erlaeut,
        ])

    results.sort(key=lambda r: r[4], reverse=True)
    results = results[:50]
    p(f"DNA-Match: {len(results)} Treffer (Top 50)", tag="ok")
    return results
