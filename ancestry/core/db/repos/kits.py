from __future__ import annotations
from typing import TYPE_CHECKING

from ancestry.models import DnaKit

if TYPE_CHECKING:
    from ancestry.core.database import Database


class KitsRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def upsert_kit(self, kit: DnaKit, last_sync: str = ""):
        with self._db._cursor() as cur:
            cur.execute("""
                INSERT INTO dna_kits (guid, name, test_type, created_date, is_owner, last_sync)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guid) DO UPDATE SET name=excluded.name, last_sync=excluded.last_sync
            """, (kit.guid, kit.name, kit.test_type, kit.created_date,
                  int(kit.is_owner), last_sync))

    def get_kits(self) -> list[DnaKit]:
        with self._db._cursor() as cur:
            cur.execute("SELECT * FROM dna_kits ORDER BY name")
            return [DnaKit(guid=r["guid"], name=r["name"], test_type=r["test_type"],
                           created_date=r["created_date"], is_owner=bool(r["is_owner"]))
                    for r in cur.fetchall()]
