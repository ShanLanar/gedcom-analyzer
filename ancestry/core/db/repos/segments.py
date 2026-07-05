from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ancestry.core.database import Database


class SegmentsRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def bulk_upsert_segments(self, segments: list) -> int:
        if not segments:
            return 0
        rows = []
        for s in segments:
            if isinstance(s, dict):
                rows.append((
                    s.get("test_guid", ""), s.get("match_guid", ""),
                    int(s.get("chromosome", 0)), int(s.get("start_location", 0)),
                    int(s.get("end_location", 0)), float(s.get("length_cm", 0.0)),
                    int(s.get("snp_count", 0)), s.get("fetched_at", ""),
                    int(bool(s.get("is_ibd2", 0))),
                ))
            else:
                rows.append((
                    s.test_guid, s.match_guid, s.chromosome,
                    s.start_location, s.end_location,
                    s.length_cm, s.snp_count, s.fetched_at,
                    int(bool(getattr(s, "is_ibd2", 0))),
                ))
        with self._db._cursor() as cur:
            cur.executemany("""
                INSERT OR REPLACE INTO dna_segments
                    (test_guid, match_guid, chromosome, start_location,
                     end_location, length_cm, snp_count, fetched_at, is_ibd2)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, rows)
        return len(rows)

    def get_segments(self, test_guid: str, min_cm: float = 0.0) -> list[dict]:
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT match_guid, chromosome, start_location, end_location,
                       length_cm, snp_count, is_ibd2
                FROM dna_segments
                WHERE test_guid = ? AND length_cm >= ?
                ORDER BY chromosome, start_location
            """, (test_guid, min_cm))
            return [dict(r) for r in cur.fetchall()]

    # ── X-DNA (S7-US-1) ────────────────────────────────────────────────────────

    def get_x_dna_matches(self, test_guid: str, min_cm: float = 0.0) -> list[dict]:
        """Matches mit X-Chromosom-Segmenten (chromosome = 23), aggregiert.

        Rückgabe je Match: summiertes X-cM, Segmentzahl, längstes X-Segment,
        absteigend nach cM. Dies ist ein ROH-Aggregat — die eigentliche
        Linien-Eingrenzung (ein Mann erbt kein X vom Vater; gültige X-Ahnen
        folgen dem Fibonacci-Fächer) ist NICHT implementiert und bräuchte das
        Geschlecht des Testers. Hinweis: X-cM (X ≈ 180 cM gesamt) sind nicht
        direkt mit autosomalen cM vergleichbar; kleine X-Segmente sind wegen
        geringerer SNP-Dichte unzuverlässiger (ggf. min_cm setzen).
        """
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT match_guid,
                       SUM(length_cm) AS x_cm,
                       COUNT(*)       AS x_segments,
                       MAX(length_cm) AS longest_x_cm
                FROM dna_segments
                WHERE test_guid = ? AND chromosome = 23 AND length_cm >= ?
                GROUP BY match_guid
                ORDER BY x_cm DESC
            """, (test_guid, min_cm))
            return [dict(r) for r in cur.fetchall()]

    # ── IBD2 (S7-US-2) ─────────────────────────────────────────────────────────

    def get_ibd2_matches(self, test_guid: str, min_cm: float = 0.0) -> list[dict]:
        """Matches mit IBD2-Segmenten (fully identical regions).

        Nennenswerte IBD2-Anteile treten praktisch nur bei Vollgeschwistern
        auf — ein starkes Unterscheidungsmerkmal gegenüber Halbgeschwistern
        oder Großeltern (die nur IBD1 teilen). Rückgabe je Match: IBD2-Gesamt-cM
        und Segmentzahl.
        """
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT match_guid,
                       SUM(length_cm) AS ibd2_cm,
                       COUNT(*)       AS ibd2_segments
                FROM dna_segments
                WHERE test_guid = ? AND is_ibd2 = 1 AND length_cm >= ?
                GROUP BY match_guid
                ORDER BY ibd2_cm DESC
            """, (test_guid, min_cm))
            return [dict(r) for r in cur.fetchall()]
