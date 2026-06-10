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
                ))
            else:
                rows.append((
                    s.test_guid, s.match_guid, s.chromosome,
                    s.start_location, s.end_location,
                    s.length_cm, s.snp_count, s.fetched_at,
                ))
        with self._db._cursor() as cur:
            cur.executemany("""
                INSERT OR REPLACE INTO dna_segments
                    (test_guid, match_guid, chromosome, start_location,
                     end_location, length_cm, snp_count, fetched_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, rows)
        return len(rows)
