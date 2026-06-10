from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ancestry.core.database import Database


class StatsRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def get_statistics(self, test_guid: Optional[str] = None) -> dict:
        where = "WHERE test_guid=?" if test_guid else ""
        params = (test_guid,) if test_guid else ()
        and_tg = "AND test_guid=?" if test_guid else ""
        with self._db._cursor() as cur:
            cur.execute(f"""
                SELECT
                    COUNT(*)            AS total,
                    MAX(shared_cm)      AS max_cm,
                    AVG(shared_cm)      AS avg_cm,
                    SUM(CASE WHEN starred=1 THEN 1 ELSE 0 END)      AS starred_count,
                    SUM(CASE WHEN has_tree=1 THEN 1 ELSE 0 END)     AS with_tree,
                    SUM(CASE WHEN note != '' AND note IS NOT NULL THEN 1 ELSE 0 END) AS with_note
                FROM matches {where}
            """, params)
            r = dict(cur.fetchone())

            cur.execute(f"""
                SELECT predicted_relationship, COUNT(*) AS cnt
                FROM matches
                WHERE predicted_relationship != '' {and_tg}
                GROUP BY predicted_relationship
                ORDER BY cnt DESC LIMIT 10
            """, params)
            r["relationship_breakdown"] = [(row[0], row[1]) for row in cur.fetchall()]

            cur.execute(f"SELECT COUNT(*) FROM shared_matches {where}", params)
            r["shared_total"] = cur.fetchone()[0]

            cur.execute(f"""
                SELECT COUNT(DISTINCT match_guid_a) FROM shared_matches {where}
            """, params)
            r["shared_primary_count"] = cur.fetchone()[0]

            ped_cond = "AND test_guid=?" if test_guid else ""
            cur.execute(f"""
                SELECT COUNT(DISTINCT match_guid) FROM match_pedigree
                WHERE generation >= 2 {ped_cond}
            """, params)
            r["ped_loaded"] = cur.fetchone()[0]

            cur.execute(f"""
                SELECT COUNT(DISTINCT surname) FROM match_pedigree
                WHERE surname != '' AND surname IS NOT NULL {ped_cond}
            """, params)
            r["ped_surnames"] = cur.fetchone()[0]

            cur.execute(f"""
                SELECT AVG(max_gen) FROM (
                    SELECT match_guid, MAX(generation) AS max_gen
                    FROM match_pedigree WHERE 1=1 {ped_cond}
                    GROUP BY match_guid
                )
            """, params)
            row = cur.fetchone()
            r["ped_avg_depth"] = round(row[0], 1) if row and row[0] else 0.0

            try:
                cur.execute("SELECT COUNT(*) FROM gedcom_persons")
                r["gedcom_persons"] = cur.fetchone()[0]
                cur.execute(f"""
                    SELECT COUNT(DISTINCT match_guid) FROM gedcom_links {where}
                """, params)
                r["gedcom_linked"] = cur.fetchone()[0]
            except Exception:
                r["gedcom_persons"] = 0
                r["gedcom_linked"] = 0

            cur.execute(f"""
                SELECT paternal_maternal, COUNT(*) FROM matches {where}
                GROUP BY paternal_maternal
            """, params)
            sides = {"paternal": 0, "maternal": 0, "": 0}
            for row in cur.fetchall():
                sides[row[0] or ""] = row[1]
            r["side_paternal"] = sides.get("paternal", 0)
            r["side_maternal"] = sides.get("maternal", 0)
            r["side_unset"] = sides.get("", 0)

            try:
                cur.execute("""
                    SELECT k.name, k.guid, COUNT(m.match_guid) AS cnt
                    FROM kits k
                    LEFT JOIN match_kit_membership m ON m.test_guid = k.guid
                    GROUP BY k.guid ORDER BY cnt DESC
                """)
                r["kit_breakdown"] = [(row[0] or row[1][:16], row[2])
                                      for row in cur.fetchall()]
            except Exception:
                r["kit_breakdown"] = []

            # ── Generation length (avg years per generation in match pedigrees) ──
            # For each pair of consecutive generations in the same match-pedigree,
            # compute the average birth-year gap.  Only years in a plausible range
            # (15–55 years per generation) are included to filter noise.
            try:
                cur.execute(f"""
                    SELECT AVG(gap) FROM (
                        SELECT
                            CAST(p1.birth_year AS INTEGER)
                            - CAST(p2.birth_year AS INTEGER) AS gap
                        FROM match_pedigree p1
                        JOIN match_pedigree p2
                          ON  p2.test_guid  = p1.test_guid
                          AND p2.match_guid = p1.match_guid
                          AND p2.generation = p1.generation + 1
                        WHERE p1.birth_year != '' AND p1.birth_year IS NOT NULL
                          AND p2.birth_year != '' AND p2.birth_year IS NOT NULL
                          AND CAST(p1.birth_year AS INTEGER) BETWEEN 1500 AND 2024
                          AND CAST(p2.birth_year AS INTEGER) BETWEEN 1500 AND 2024
                          {ped_cond.replace('AND test_guid=?', 'AND p1.test_guid=?')}
                    ) WHERE gap BETWEEN 15 AND 55
                """, params)
                row = cur.fetchone()
                r["gen_length"] = round(row[0], 1) if row and row[0] else None
            except Exception:
                r["gen_length"] = None

        return r
