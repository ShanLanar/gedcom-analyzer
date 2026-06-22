"""Pedigree-Lücken-Analyse: Brick-Wall Detection durch GEDCOM-Traversal.

Durchläuft Ahnenlinie von einer Person bis zu NULL-Eltern,
identifiziert Generationen mit fehlenden Daten.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ancestry.core.database import Database

log = logging.getLogger(__name__)


def analyze_pedigree_gaps(db: Database, ged_id: str) -> list[dict]:
    """Traversiert GEDCOM-Ahnenlinie, stoppt bei NULL-Eltern, gibt Lücken zurück.

    Args:
        db: Database-Instanz
        ged_id: Gedcom Person ID (z.B. "I1")

    Returns:
        Liste von Gap-Dicts:
        [
            {
                "generation": 2,
                "gap_type": "maternal_parent",  # maternal_parent | paternal_parent
                "last_known": "Name (1950)",
                "last_known_ged_id": "I123"
            },
            ...
        ]
    """
    gaps: list[dict] = []

    try:
        with db._cursor() as cur:
            # Laden der Root-Person
            cur.execute(
                """SELECT ged_id, given_name, surname, birth_year, parents_json
                   FROM gedcom_persons WHERE ged_id = ?""",
                (ged_id,),
            )
            root_row = cur.fetchone()

            if not root_row:
                log.warning("Person %s nicht in gedcom_persons", ged_id)
                return gaps

            # BFS-Traversal: Generation → Personen in dieser Gen
            current_gen = [(root_row["ged_id"], root_row, None)]  # (ged_id, row, side)
            generation = 1

            while current_gen and generation <= 10:  # Limit 10 Generationen
                next_gen = []

                for person_ged_id, person_row, _ in current_gen:
                    parents_json = person_row.get("parents_json", "[]")
                    try:
                        parents = json.loads(parents_json)
                    except (json.JSONDecodeError, TypeError):
                        parents = []

                    if not parents:
                        # Keine Parents in JSON → brick wall
                        name = _format_person_name(person_row)
                        gaps.append({
                            "generation": generation + 1,
                            "gap_type": "both_parents",
                            "last_known": name,
                            "last_known_ged_id": person_ged_id,
                        })
                        continue

                    # Laden der Eltern
                    for i, parent_ged_id in enumerate(parents):
                        if not parent_ged_id:
                            # Ein Elternteil fehlt
                            side = "paternal_parent" if i == 0 else "maternal_parent"
                            name = _format_person_name(person_row)
                            gaps.append({
                                "generation": generation + 1,
                                "gap_type": side,
                                "last_known": name,
                                "last_known_ged_id": person_ged_id,
                            })
                            continue

                        cur.execute(
                            """SELECT ged_id, given_name, surname, birth_year, parents_json
                               FROM gedcom_persons WHERE ged_id = ?""",
                            (parent_ged_id,),
                        )
                        parent_row = cur.fetchone()

                        if parent_row:
                            side_label = "paternal" if i == 0 else "maternal"
                            next_gen.append((parent_ged_id, parent_row, side_label))

                current_gen = next_gen
                generation += 1

        return gaps

    except Exception as e:
        log.exception("Fehler bei Pedigree-Lücken-Analyse: %s", e)
        return gaps


def _format_person_name(row) -> str:
    """Formatiert Person zu "Given Surname (Year)" String."""
    given = (row.get("given_name") or "").strip()
    surname = (row.get("surname") or "").strip()
    year = row.get("birth_year")

    name = f"{given} {surname}".strip() or "?"
    if year:
        name = f"{name} ({year})"
    return name


def get_pedigree_completeness(db: Database, ged_id: str) -> dict:
    """Analysiert Vollständigkeit der Ahnenlinie pro Generation.

    Args:
        db: Database-Instanz
        ged_id: Root Person GED-ID

    Returns:
        {
            "root_person": "Name",
            "by_generation": {
                1: {"known": 1, "unknown": 0, "complete": True},
                2: {"known": 2, "unknown": 0, "complete": True},
                3: {"known": 3, "unknown": 1, "complete": False},
            },
            "first_gap_gen": 3
        }
    """
    completeness = {"root_person": "", "by_generation": {}, "first_gap_gen": None}

    try:
        with db._cursor() as cur:
            # Root
            cur.execute(
                """SELECT given_name, surname FROM gedcom_persons WHERE ged_id = ?""",
                (ged_id,),
            )
            root = cur.fetchone()
            if root:
                completeness["root_person"] = (
                    f"{root['given_name']} {root['surname']}".strip()
                )

            # BFS-Traversal
            current_gen = [ged_id]
            generation = 1

            while current_gen and generation <= 10:
                known, unknown = 0, 0
                next_gen = set()

                for person_ged_id in current_gen:
                    cur.execute(
                        """SELECT parents_json FROM gedcom_persons WHERE ged_id = ?""",
                        (person_ged_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        unknown += 1
                        continue

                    parents_json = row.get("parents_json", "[]")
                    try:
                        parents = json.loads(parents_json)
                    except (json.JSONDecodeError, TypeError):
                        parents = []

                    if not parents:
                        unknown += 1
                        continue

                    known += 1
                    for parent_id in parents:
                        if parent_id:
                            next_gen.add(parent_id)

                completeness["by_generation"][generation] = {
                    "known": known,
                    "unknown": unknown,
                    "complete": unknown == 0 and len(next_gen) > 0,
                }

                if unknown > 0 and completeness["first_gap_gen"] is None:
                    completeness["first_gap_gen"] = generation

                current_gen = list(next_gen)
                generation += 1

        return completeness

    except Exception as e:
        log.exception("Fehler bei Pedigree-Vollständigkeits-Analyse: %s", e)
        return completeness
