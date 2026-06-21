"""Repo für Cluster→Ahn-Hypothesen (Tabelle cluster_hypotheses, Feature B3).

Strukturierte, an einen GEDCOM-Ahn (ged_id) gebundene Hypothese je Cluster:
"von welchem gemeinsamen Vorfahren stammt dieser DNA-Cluster ab?"
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ancestry.core.database import Database


class ClusterHypothesesRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def set_hypothesis(self, kit_guid: str, cluster_id: int,
                       mrca_ged_id: str = "", mrca_label: str = "",
                       confidence: str = "", evidence: str = "") -> None:
        with self._db._cursor() as cur:
            cur.execute(
                """INSERT INTO cluster_hypotheses
                   (kit_guid, cluster_id, mrca_ged_id, mrca_label,
                    confidence, evidence, updated_at)
                   VALUES (?,?,?,?,?,?, datetime('now'))
                   ON CONFLICT(kit_guid, cluster_id) DO UPDATE SET
                       mrca_ged_id=excluded.mrca_ged_id,
                       mrca_label =excluded.mrca_label,
                       confidence =excluded.confidence,
                       evidence   =excluded.evidence,
                       updated_at =datetime('now')""",
                (kit_guid or "", int(cluster_id), mrca_ged_id or "",
                 mrca_label or "", confidence or "", evidence or ""))

    def get_hypothesis(self, kit_guid: str, cluster_id: int) -> Optional[dict]:
        try:
            with self._db._cursor() as cur:
                row = cur.execute(
                    "SELECT * FROM cluster_hypotheses WHERE kit_guid=? AND cluster_id=?",
                    (kit_guid or "", int(cluster_id))).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def get_all_for_kit(self, kit_guid: str) -> list[dict]:
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    "SELECT * FROM cluster_hypotheses WHERE kit_guid=? ORDER BY cluster_id",
                    (kit_guid or "",)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def delete_hypothesis(self, kit_guid: str, cluster_id: int) -> None:
        with self._db._cursor() as cur:
            cur.execute(
                "DELETE FROM cluster_hypotheses WHERE kit_guid=? AND cluster_id=?",
                (kit_guid or "", int(cluster_id)))

    def suggest_mrca(self, test_guid: str, member_guids: list[str]) -> list[dict]:
        """Schlägt aus gedcom_links den/die wahrscheinlichsten gemeinsamen Ahnen
        der Cluster-Mitglieder vor: ged_id, an den ≥2 Mitglieder andocken.
        Rein lesend. Rückgabe sortiert nach Mitgliederzahl, dann Ø-Score."""
        if not (test_guid and member_guids):
            return []
        out: dict[str, dict] = {}
        try:
            ph = ",".join("?" * len(member_guids))
            with self._db._cursor() as cur:
                rows = cur.execute(
                    f"""SELECT ged_id, ged_given, ged_surname, ged_year,
                               match_guid, total_score
                        FROM gedcom_links
                        WHERE test_guid=? AND match_guid IN ({ph})""",
                    [test_guid, *member_guids]).fetchall()
            for r in rows:
                gid = r["ged_id"]
                if not gid:
                    continue
                e = out.setdefault(gid, {
                    "ged_id": gid,
                    "name": f"{(r['ged_given'] or '').strip()} {(r['ged_surname'] or '').strip()}".strip(),
                    "year": r["ged_year"] or "",
                    "_members": set(), "_scores": []})
                e["_members"].add(r["match_guid"])
                e["_scores"].append(r["total_score"] or 0)
        except Exception:
            return []
        result = []
        for e in out.values():
            mc = len(e["_members"])
            if mc < 2:
                continue
            result.append({
                "ged_id": e["ged_id"], "name": e["name"], "year": e["year"],
                "member_count": mc,
                "avg_score": round(sum(e["_scores"]) / len(e["_scores"]), 2),
            })
        result.sort(key=lambda x: (-x["member_count"], -x["avg_score"]))
        return result[:5]
