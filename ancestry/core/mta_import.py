"""
MyTrueAncestry (MTA) population-breakdown importer.

Expected CSV format (exported manually from mytrueancestry.com):
  Population,Score,Distance
  Corded_Ware_Germany,89.5,0.0412
  ...

Two sets can be loaded: "self" (your own kit) and optionally "base2"
(e.g. your mother's kit), enabling paternal-component derivation.
"""

import csv
import json
import os
from typing import Optional


MTA_SCHEMA = """
CREATE TABLE IF NOT EXISTS mta_populations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,   -- e.g. "self" or "base2"
    population  TEXT NOT NULL,
    score       REAL NOT NULL DEFAULT 0.0,
    distance    REAL NOT NULL DEFAULT 0.0,
    era         TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def _detect_era(population: str) -> str:
    """Heuristically assign an era label from the population name."""
    p = population.lower()
    if any(k in p for k in ["neolithic", "farmer", "ertebolle", "megalith"]):
        return "Neolithic"
    if any(k in p for k in ["bronze", "corded", "yamnaya", "steppe"]):
        return "Bronze Age"
    if any(k in p for k in ["iron", "roman", "celtic", "germanic", "slavic"]):
        return "Iron Age / Historical"
    if any(k in p for k in ["medieval", "viking", "longobard"]):
        return "Medieval"
    if any(k in p for k in ["modern", "contemporary", "19th", "20th"]):
        return "Modern"
    return "Ancient / Other"


def parse_mta_csv(path: str) -> list[dict]:
    """
    Parse a MyTrueAncestry CSV export.

    Accepts both:
      Population,Score,Distance
      Population,Score          (distance optional)

    Returns list of dicts with keys: population, score, distance, era.
    """
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            pop = (row.get("Population") or row.get("population") or "").strip()
            if not pop:
                continue
            try:
                score = float(row.get("Score") or row.get("score") or 0)
            except ValueError:
                score = 0.0
            try:
                distance = float(row.get("Distance") or row.get("distance") or 0)
            except ValueError:
                distance = 0.0
            rows.append({
                "population": pop,
                "score": score,
                "distance": distance,
                "era": _detect_era(pop),
            })
    return rows


def derive_paternal(self_rows: list[dict], base2_rows: list[dict]) -> list[dict]:
    """
    Derive the paternal component by subtracting maternal (base2) from self.

    Uses the linear approximation: paternal ≈ 2 × self − maternal.
    This assumes each population component is the average of both parents.
    The approximation breaks down when a population component is present in
    only one parent (e.g. an exclusively paternal African component will be
    underestimated). Results should be treated as exploratory estimates.

    Returns list of dicts with keys:
      population, era, self_score, base2_score, paternal_estimate, method.
    ``method`` is always ``"subtraction_approximation"`` as a reminder of the
    derivation approach.
    """
    base2_map = {r["population"]: r["score"] for r in base2_rows}
    result = []
    for r in self_rows:
        pop = r["population"]
        s = r["score"]
        b2 = base2_map.get(pop, 0.0)
        paternal_est = max(0.0, 2 * s - b2)
        result.append({
            "population": pop,
            "era": r["era"],
            "self_score": s,
            "base2_score": b2,
            "paternal_estimate": paternal_est,
            "method": "subtraction_approximation",
        })
    # Normalize paternal estimates to sum 100
    total = sum(r["paternal_estimate"] for r in result)
    if total > 0:
        for r in result:
            r["paternal_estimate"] = round(r["paternal_estimate"] / total * 100, 2)
    return result
