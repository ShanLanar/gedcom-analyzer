from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ancestry.models import DnaKit

if TYPE_CHECKING:
    from ancestry.core.database import Database

log = logging.getLogger(__name__)


class KitsRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def upsert_kit(self, kit: DnaKit, last_sync: str = "") -> None:
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

    def save_kit_ethnicity(self, test_guid: str, data: list) -> None:
        with self._db._cursor() as cur:
            cur.execute(
                "UPDATE dna_kits SET ethnicity_json = ? WHERE guid = ?",
                (json.dumps(data, ensure_ascii=False), test_guid),
            )

    def get_kit_ethnicity(self, test_guid: str) -> list:
        try:
            with self._db._cursor() as cur:
                cur.execute("SELECT ethnicity_json FROM dna_kits WHERE guid = ?", (test_guid,))
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        except Exception as e:
            log.debug("get_kit_ethnicity %s: %s", test_guid, e)
        return []

    def save_kit_traits(self, test_guid: str, data: list) -> None:
        with self._db._cursor() as cur:
            cur.execute(
                "UPDATE dna_kits SET traits_json = ? WHERE guid = ?",
                (json.dumps(data, ensure_ascii=False), test_guid),
            )

    def get_kit_traits(self, test_guid: str) -> list:
        try:
            with self._db._cursor() as cur:
                cur.execute("SELECT traits_json FROM dna_kits WHERE guid = ?", (test_guid,))
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        except Exception as e:
            log.debug("get_kit_traits %s: %s", test_guid, e)
        return []
