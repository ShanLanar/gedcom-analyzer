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
from ancestry.core.treematch.genetics import (
    endogamy_flag, resolve_endogamy_factor,
)


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


PREDICT_HEADERS = ["Beziehung", "Wahrscheinlichkeit %", "95%-KI (cM)", "Ø cM"]


def _ci95(mu, sigma):
    """95%-Konfidenzintervall (μ ± 1,96·σ), unten bei 0 gekappt."""
    lo = max(0.0, mu - 1.96 * sigma)
    hi = mu + 1.96 * sigma
    return lo, hi


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


# Segmentform-Heuristik → Endogamie-Faktor. Konservativ und transparent aus
# dem vorhandenen endogamy_flag()-Score (0..1, viele kleine Segmente = hoch)
# abgeleitet, KEIN literaturbasierter Wert wie ENDOGAMY_FACTORS — deshalb
# bewusst gedeckelt auf max. 1.5 statt der bis zu 1.8 bekannter Populationen.
_AUTO_ENDOGAMY_CAP = 1.5


def predict_relationship_detailed(target_cm, shared_segments=None,
                                  longest_segment=None,
                                  population: str = "",
                                  endogamy_factor: float = 1.0):
    """Wie predict_relationship_from_cm, aber mit Konfidenzintervall je Grad
    und optionaler Endogamie-Korrektur.

    Endogamie (Verwandtenehen, isolierte Populationen) lässt zwei Personen
    MEHR cM teilen, als ihre wahre Verwandtschaft erwarten ließe — die rohe
    cM-Zahl würde die Beziehung sonst systematisch zu NAH einordnen. Zwei
    unabhängige Korrekturwege, beide optional:

    population / endogamy_factor:
        Wie ``ancestry.core.treematch.genetics.cm_to_mrca`` — ein bekannter
        Populationsfaktor (``ENDOGAMY_FACTORS``) oder ein expliziter Wert.
        Gewinnt, wenn gesetzt.
    shared_segments / longest_segment:
        Ohne expliziten Faktor wird aus der Segmentform (viele kurze Segmente
        = typische Endogamie-Signatur, siehe ``endogamy_flag``) automatisch
        ein konservativer Faktor (≤ 1.5) abgeleitet, FALLS beide Werte
        übergeben werden. Das ist eine Heuristik aus der Segmentform dieses
        EINEN Matches, kein literaturbasierter Populationswert.

    Die 95%-KI-Bänder (ci_low/ci_high) bleiben die unkorrigierten
    Literaturwerte je Beziehungsgrad — korrigiert wird nur, welcher Grad zum
    beobachteten cM-Wert passt (target_cm wird vor dem Dichte-Vergleich durch
    den Faktor geteilt).

    Returns
    -------
    list[dict]
        Absteigend nach Wahrscheinlichkeit, je Eintrag:
        ``{label, probability, mean_cm, ci_low, ci_high, raw_cm,
        effective_cm, endogamy_factor}``. Das 95%-KI zeigt die beobachtete
        cM-Streuung dieses Grades (Shared cM Project) — so ist sichtbar, dass
        etwa 1.750 cM sowohl Halbgeschwister als auch Großelternteil sein
        kann statt einer trügerischen Punktschätzung.
    """
    try:
        target = float(target_cm)
    except (TypeError, ValueError):
        return []

    factor = resolve_endogamy_factor(endogamy_factor, population)
    if factor == 1.0 and shared_segments is not None and longest_segment is not None:
        _label, score = endogamy_flag(target, shared_segments, longest_segment)
        factor = 1.0 + min(score, 1.0) * (_AUTO_ENDOGAMY_CAP - 1.0)

    effective = target / max(factor, 0.5)

    dist_by_label = {lbl: (mu, sigma) for lbl, mu, sigma in _RELATIONSHIP_DIST}
    detailed = []
    for lbl, prob in predict_relationship_from_cm(effective):
        mu, sigma = dist_by_label[lbl]
        lo, hi = _ci95(mu, sigma)
        detailed.append({
            "label":            lbl,
            "probability":      prob,
            "mean_cm":          mu,
            "ci_low":           round(lo, 0),
            "ci_high":          round(hi, 0),
            "raw_cm":           round(target, 1),
            "effective_cm":     round(effective, 1),
            "endogamy_factor":  round(factor, 3),
        })
    return detailed


def predict_relationship_rows(target_cm):
    """Sheet-Generator-Variante: liefert Rows passend zu PREDICT_HEADERS."""
    rows = []
    for d in predict_relationship_detailed(target_cm):
        rows.append([
            d["label"],
            round(d["probability"] * 100.0, 2),
            f"{d['ci_low']:.0f}–{d['ci_high']:.0f}",
            round(d["mean_cm"], 0),
        ])
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
