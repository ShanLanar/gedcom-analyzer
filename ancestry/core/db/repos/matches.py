from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING

from ancestry.models import DnaMatch

if TYPE_CHECKING:
    from ancestry.core.database import Database

log = logging.getLogger(__name__)


class MatchesRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def upsert_match(self, m: DnaMatch):
        d = m.to_dict()
        with self._db._cursor() as cur:
            cur.execute("""
                INSERT OR IGNORE INTO dna_kits (guid, name, test_type)
                VALUES (?, ?, ?)
            """, (m.test_guid, m.test_guid[:8] + "…", "AncestryDNA"))
            cur.execute("""
                INSERT INTO matches (
                    match_guid, test_guid, display_name,
                    shared_cm, shared_segments, longest_segment,
                    predicted_relationship, confidence, relationship_range,
                    has_hint, has_tree, tree_size, tree_id,
                    starred, note, custom_relationship,
                    ethnicity_regions, last_login, fetched_at, raw_json,
                    match_cluster_code, created_date,
                    tag_surname, tag_gender, tag_path, tags_json, meiosis, ignored,
                    paternal_maternal, source
                ) VALUES (
                    :match_guid, :test_guid, :display_name,
                    :shared_cm, :shared_segments, :longest_segment,
                    :predicted_relationship, :confidence, :relationship_range,
                    :has_hint, :has_tree, :tree_size, :tree_id,
                    :starred, :note, :custom_relationship,
                    :ethnicity_regions, :last_login, :fetched_at, :raw_json,
                    :match_cluster_code, :created_date,
                    :tag_surname, :tag_gender, :tag_path, :tags_json, :meiosis, :ignored,
                    :paternal_maternal, :source
                )
                ON CONFLICT(match_guid) DO UPDATE SET
                    display_name = CASE
                        WHEN length(excluded.display_name) > 8 THEN excluded.display_name
                        WHEN display_name IS NULL OR display_name = '' OR length(display_name) <= 8
                             THEN excluded.display_name
                        ELSE display_name
                    END,
                    shared_cm=excluded.shared_cm,
                    shared_segments=excluded.shared_segments,
                    longest_segment=excluded.longest_segment,
                    predicted_relationship=excluded.predicted_relationship,
                    confidence=excluded.confidence,
                    relationship_range=excluded.relationship_range,
                    has_hint=excluded.has_hint,
                    -- has_tree/tree_size NICHT überschreiben: matchList liefert
                    -- keine Baum-Daten (immer 0); sie kommen aus treeData und
                    -- würden sonst bei jedem Matches-Download zurückgesetzt.
                    tree_id=excluded.tree_id,
                    starred=excluded.starred,
                    ethnicity_regions=excluded.ethnicity_regions,
                    last_login=excluded.last_login,
                    fetched_at=excluded.fetched_at,
                    raw_json=excluded.raw_json,
                    match_cluster_code=excluded.match_cluster_code,
                    created_date=excluded.created_date,
                    tag_surname=excluded.tag_surname,
                    tag_path=excluded.tag_path,
                    tags_json=excluded.tags_json,
                    meiosis=excluded.meiosis,
                    ignored=excluded.ignored,
                    -- Ancestry-Schätzung nur setzen wenn noch kein Wert (manuell oder per Kit-Overlap) gesetzt
                    paternal_maternal = CASE
                        WHEN paternal_maternal IS NULL OR paternal_maternal = ''
                        THEN excluded.paternal_maternal
                        ELSE paternal_maternal
                    END,
                    -- Preserve non-default source (ftdna, myheritage, …); only overwrite if still default
                    source = CASE
                        WHEN source IS NULL OR source = '' OR source = 'ancestry'
                        THEN excluded.source
                        ELSE source
                    END
            """, d)
            cur.execute(
                "INSERT OR IGNORE INTO match_kit_membership (match_guid, test_guid) VALUES (?,?)",
                (m.match_guid, m.test_guid),
            )

    def bulk_upsert(self, matches: list[DnaMatch]) -> int:
        saved = 0
        for m in matches:
            self.upsert_match(m)
            saved += 1
        try:
            self._db._get_conn().execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception as e:
            log.warning("Checkpoint fehlgeschlagen: %s", e)
        return saved

    def get_matches(
        self,
        test_guid: Optional[str]    = None,
        search: Optional[str]       = None,
        relationship: Optional[str] = None,
        starred_only: bool          = False,
        has_tree_only: bool         = False,
        min_cm: float               = 0.0,
        hide_endogamy: bool         = False,
        sort_col: str               = "shared_cm",
        sort_asc: bool              = False,
        limit: int                  = 0,
        offset: int                 = 0,
        source: Optional[str]       = None,
        all_sources: bool           = False,
    ) -> list[DnaMatch]:
        valid_cols = {"display_name", "shared_cm", "shared_segments",
                      "predicted_relationship", "fetched_at", "starred",
                      "tree_size", "tree_status", "has_common_ancestor", "gender"}
        sort_col  = sort_col if sort_col in valid_cols else "shared_cm"
        direction = "ASC" if sort_asc else "DESC"

        conditions, params = [], []
        use_kit_join = bool(test_guid) and not all_sources
        if use_kit_join:
            conditions.append("mkm.test_guid = ?"); params.append(test_guid)
        if source:
            conditions.append("m.source = ?"); params.append(source)
        if search:
            conditions.append("m.display_name LIKE ?"); params.append(f"%{search}%")
        if relationship and relationship != "(alle)":
            conditions.append("m.predicted_relationship = ?"); params.append(relationship)
        if starred_only:
            conditions.append("m.starred = 1")
        if has_tree_only:
            conditions.append("m.has_tree = 1")
        if min_cm > 0:
            conditions.append("m.shared_cm >= ?"); params.append(min_cm)
        if hide_endogamy:
            conditions.append("(m.endogamy_cluster IS NULL OR m.endogamy_cluster = '')")

        where        = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit_clause = f"LIMIT {limit} OFFSET {offset}" if limit else ""

        _bridge_ok = self._db._table_exists("gedmatch_bridge")
        if _bridge_ok:
            bridge_join = "LEFT JOIN gedmatch_bridge gb ON gb.match_guid = m.match_guid"
            extra_col   = "COALESCE(gb.gedmatch_kit_id,'') AS gedmatch_kit_id"
        else:
            bridge_join = ""
            extra_col   = "'' AS gedmatch_kit_id"

        if use_kit_join:
            sql = (f"SELECT m.*, {extra_col} FROM matches m "
                   f"JOIN match_kit_membership mkm ON mkm.match_guid = m.match_guid "
                   f"{bridge_join} "
                   f"{where} ORDER BY m.{sort_col} {direction} {limit_clause}")
        else:
            sql = (f"SELECT m.*, {extra_col} FROM matches m {bridge_join} {where} "
                   f"ORDER BY m.{sort_col} {direction} {limit_clause}")

        with self._db._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [DnaMatch.from_db_row(dict(r)) for r in rows]

    def match_exists(self, match_guid: str) -> bool:
        with self._db._cursor() as cur:
            cur.execute("SELECT 1 FROM matches WHERE match_guid=? LIMIT 1", (match_guid,))
            return cur.fetchone() is not None

    def match_exists_for_kit(self, match_guid: str, test_guid: str) -> bool:
        with self._db._cursor() as cur:
            cur.execute(
                "SELECT 1 FROM match_kit_membership WHERE match_guid=? AND test_guid=? LIMIT 1",
                (match_guid, test_guid),
            )
            return cur.fetchone() is not None

    def get_match_count(self, test_guid: Optional[str] = None) -> int:
        with self._db._cursor() as cur:
            if test_guid:
                cur.execute(
                    "SELECT COUNT(*) FROM match_kit_membership WHERE test_guid=?", (test_guid,)
                )
            else:
                cur.execute("SELECT COUNT(*) FROM matches")
            return cur.fetchone()[0]

    def get_distinct_relationships(self) -> list[str]:
        with self._db._cursor() as cur:
            cur.execute("""SELECT DISTINCT predicted_relationship FROM matches
                           WHERE predicted_relationship != '' ORDER BY predicted_relationship""")
            return [r[0] for r in cur.fetchall()]

    def update_note(self, match_guid: str, note: str):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET note=? WHERE match_guid=?", (note, match_guid))
            cur.execute("""
                INSERT INTO user_notes(match_guid, note, updated_at) VALUES(?,?,?)
                ON CONFLICT(match_guid) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at
            """, (match_guid, note, now))

    def bump_name_attempts(self, test_guid: str, match_guids: list):
        if not match_guids:
            return
        with self._db._cursor() as cur:
            cur.executemany(
                "UPDATE matches SET name_attempts = COALESCE(name_attempts,0)+1 "
                "WHERE match_guid=? AND test_guid=?",
                [(g, test_guid) for g in match_guids])

    def reset_name_attempts(self, test_guid: str) -> int:
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET name_attempts=0 WHERE test_guid=?", (test_guid,))
            return cur.rowcount

    def set_endogamy_cluster(self, match_guid: str, cluster: str):
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET endogamy_cluster=? WHERE match_guid=?",
                        (cluster.strip(), match_guid))

    def set_probable_origin(self, match_guid: str, origin_json: str):
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET probable_origin=? WHERE match_guid=?",
                        (origin_json, match_guid))

    def set_ml_origin(self, match_guid: str, origin_json: str):
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET ml_origin=? WHERE match_guid=?",
                        (origin_json, match_guid))

    def update_research_flags(self, match_guid: str, flags: int) -> None:
        with self._db._cursor() as cur:
            cur.execute(
                "UPDATE matches SET research_flags=? WHERE match_guid=?",
                (flags, match_guid)
            )

    def get_endogamy_candidates(self, test_guid: str, threshold: float = 0.15) -> list:
        with self._db._cursor() as cur:
            rows = cur.execute(
                """SELECT match_guid, display_name, shared_cm, shared_segments,
                          CAST(shared_segments AS REAL) / (shared_cm + 1.0) AS endo_score
                   FROM matches
                   WHERE test_guid=?
                     AND shared_cm > 0
                     AND CAST(shared_segments AS REAL) / (shared_cm + 1.0) > ?
                   ORDER BY endo_score DESC""",
                (test_guid, threshold)
            ).fetchall()
        return [dict(r) for r in rows]

    def bulk_set_side(self, guids: list, side: str) -> int:
        if not guids:
            return 0
        with self._db._cursor() as cur:
            cur.executemany(
                "UPDATE matches SET paternal_maternal=? WHERE match_guid=?",
                [(side, g) for g in guids]
            )
        return len(guids)

    def get_paternal_maternal_overlap(self, kit_a: str, kit_b: str) -> dict:
        with self._db._cursor() as cur:
            guids_a = {r[0] for r in cur.execute(
                "SELECT match_guid FROM match_kit_membership WHERE test_guid=?",
                (kit_a,)).fetchall()}
            guids_b = {r[0] for r in cur.execute(
                "SELECT match_guid FROM match_kit_membership WHERE test_guid=?",
                (kit_b,)).fetchall()}
        return {
            "shared": guids_a & guids_b,
            "only_a": guids_a - guids_b,
            "only_b": guids_b - guids_a,
        }

    def link_gedmatch_bridges(self, our_kit: str = "CM8449775",
                              cm_tolerance: float = 0.12) -> int:
        from difflib import SequenceMatcher
        with self._db._cursor() as cur:
            gm_rows = [tuple(r) for r in cur.execute(
                "SELECT kit_id, name, shared_cm, source_platform "
                "FROM gedmatch_matches WHERE our_kit=? AND shared_cm > 7",
                (our_kit,)
            ).fetchall()]
            match_rows = [tuple(r) for r in cur.execute(
                "SELECT match_guid, display_name, shared_cm, source "
                "FROM matches WHERE shared_cm > 7"
            ).fetchall()]

        def _sim(a: str, b: str) -> float:
            a, b = (a or "").lower().strip(), (b or "").lower().strip()
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a, b).ratio()

        linked = 0
        rows_to_insert = []
        for gm in gm_rows:
            gm_kit, gm_name, gm_cm, gm_plat = gm
            if not gm_cm:
                continue
            lo, hi = gm_cm * (1 - cm_tolerance), gm_cm * (1 + cm_tolerance)
            best_guid, best_score = None, 0.54
            for mg in match_rows:
                m_guid, m_name, m_cm, m_src = mg
                if not m_cm or not (lo <= m_cm <= hi):
                    continue
                plat_lower = (gm_plat or "").lower()
                if "ancestry" in plat_lower and m_src != "ancestry":
                    continue
                if "myheritage" in plat_lower and m_src not in ("myheritage", "ancestry"):
                    continue
                s = _sim(gm_name, m_name)
                if s > best_score:
                    best_score, best_guid = s, m_guid
            if best_guid:
                rows_to_insert.append((gm_kit, best_guid, round(best_score, 3)))
                linked += 1

        with self._db._cursor() as cur:
            cur.executemany(
                "INSERT OR REPLACE INTO gedmatch_bridge "
                "(gedmatch_kit_id, match_guid, confidence, linked_at) "
                "VALUES (?, ?, ?, datetime('now'))",
                rows_to_insert,
            )
        return linked

    def get_bridge_hit_counts(self, test_guid: str) -> dict:
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    "SELECT match_guid, COUNT(*) FROM gedcom_links "
                    "WHERE test_guid=? GROUP BY match_guid",
                    (test_guid,),
                ).fetchall()
            return {r[0]: r[1] for r in rows}
        except Exception:
            return {}

    def get_unfetched_match_guids(self, test_guid: str,
                                   min_cm: float = 0.0) -> list[tuple[str, str]]:
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT m.match_guid, m.display_name
                FROM matches m
                WHERE m.test_guid = ?
                  AND m.shared_cm >= ?
                  AND NOT EXISTS (
                      SELECT 1 FROM shared_matches_fetched f
                      WHERE f.test_guid = m.test_guid
                        AND f.match_guid_a = m.match_guid
                  )
                ORDER BY m.shared_cm DESC
            """, (test_guid, min_cm))
            return [(r[0], r[1]) for r in cur.fetchall()]
