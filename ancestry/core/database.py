"""
SQLite-Datenbankschicht für ancestry_dna_tool.
Schema v3: Shared-Matches-Tabelle hinzugefügt.
"""

import sqlite3
import logging
from contextlib import contextmanager
from typing import Generator, Optional

from models import DnaKit, DnaMatch, SharedMatch

log = logging.getLogger(__name__)


class Database:
    """Verwaltet die SQLite-Datenbank für DNA-Matches und Shared Matches."""

    SCHEMA_VERSION = 8

    def __init__(self, db_file: str = "ancestry_dna.db"):
        import os
        # Absoluter Pfad relativ zum Programmverzeichnis
        if not os.path.isabs(db_file):
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(base, db_file)
        self.db_file = db_file
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = __import__('threading').Lock()
        self._init_db()

    # ── Verbindung ────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=OFF")  # FK manuell verwaltet
        return self._conn

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        with self._lock:
            conn = self._get_conn()
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)
            """)
            cur.execute("SELECT version FROM schema_version LIMIT 1")
            row = cur.fetchone()
            current = row["version"] if row else 0

            if current < 1:
                self._create_schema_v1(cur)
            if current < 2:
                self._migrate_v1_v2(cur)
            if current < 3:
                self._migrate_v2_v3(cur)
            if current < 4:
                self._migrate_v3_v4(cur)
            if current < 6:
                self._migrate_v5_v6(cur)
            if current < 7:
                self._migrate_v6_v7(cur)
            if current < 8:
                self._migrate_v7_v8(cur)

            if row:
                cur.execute("UPDATE schema_version SET version=?", (self.SCHEMA_VERSION,))
            else:
                cur.execute("INSERT INTO schema_version VALUES(?)", (self.SCHEMA_VERSION,))

        log.debug("DB initialisiert: %s (Schema v%d)", self.db_file, self.SCHEMA_VERSION)

    def _create_schema_v1(self, cur):
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS dna_kits (
                guid          TEXT PRIMARY KEY,
                name          TEXT,
                test_type     TEXT,
                created_date  TEXT,
                is_owner      INTEGER DEFAULT 1,
                last_sync     TEXT
            );

            CREATE TABLE IF NOT EXISTS matches (
                match_guid              TEXT PRIMARY KEY,
                test_guid               TEXT NOT NULL,
                display_name            TEXT,
                shared_cm               REAL DEFAULT 0,
                shared_segments         INTEGER DEFAULT 0,
                longest_segment         REAL DEFAULT 0,
                predicted_relationship  TEXT,
                confidence              TEXT,
                relationship_range      TEXT,
                has_hint                INTEGER DEFAULT 0,
                has_tree                INTEGER DEFAULT 0,
                tree_size               INTEGER DEFAULT 0,
                tree_id                 TEXT,
                starred                 INTEGER DEFAULT 0,
                note                    TEXT,
                custom_relationship     TEXT,
                ethnicity_regions       TEXT,
                last_login              TEXT,
                fetched_at              TEXT,
                raw_json                TEXT,
                match_cluster_code      TEXT DEFAULT '',
                created_date            INTEGER DEFAULT 0,
                tag_surname             TEXT DEFAULT '',
                tag_gender              TEXT DEFAULT '',
                tag_path                TEXT DEFAULT '',
                tags_json               TEXT DEFAULT '',
                meiosis                 INTEGER DEFAULT 0,
                ignored                 INTEGER DEFAULT 0,
                tree_status             TEXT    DEFAULT '',
                has_common_ancestor     INTEGER DEFAULT 0,
                match_ucdmid            TEXT    DEFAULT '',
                gender                  TEXT    DEFAULT '',
                ancestors_fetched       INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_matches_test_guid  ON matches(test_guid);
            CREATE INDEX IF NOT EXISTS idx_matches_shared_cm  ON matches(shared_cm DESC);
            CREATE INDEX IF NOT EXISTS idx_matches_relationship ON matches(predicted_relationship);
            CREATE INDEX IF NOT EXISTS idx_matches_starred    ON matches(starred);
        """)

    def _migrate_v1_v2(self, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_notes (
                match_guid  TEXT PRIMARY KEY,
                note        TEXT,
                updated_at  TEXT,
                FOREIGN KEY (match_guid) REFERENCES matches(match_guid)
            )
        """)

    def _migrate_v3_v4(self, cur):
        """Schema v4: matchClusterCode, created_date, tag_surname/gender, meiosis, ignored."""
        new_cols = [
            ("match_cluster_code", "TEXT    DEFAULT ''"),
            ("created_date",       "INTEGER DEFAULT 0"),
            ("tag_surname",        "TEXT    DEFAULT ''"),
            ("tag_gender",         "TEXT    DEFAULT ''"),
            ("meiosis",            "INTEGER DEFAULT 0"),
            ("ignored",            "INTEGER DEFAULT 0"),
        ]
        for col, typedef in new_cols:
            try:
                cur.execute(f"ALTER TABLE matches ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Spalte existiert bereits
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_matches_cluster
                    ON matches(match_cluster_code)
            """)
        except Exception:
            pass

    def _migrate_v5_v6(self, cur):
        """Schema v6: Stammbaum-Status/-Größe, gemeinsamer Vorfahre, ucdmid, Geschlecht."""
        new_cols = [
            ("tree_status",         "TEXT    DEFAULT ''"),
            ("has_common_ancestor", "INTEGER DEFAULT 0"),
            ("match_ucdmid",        "TEXT    DEFAULT ''"),
            ("gender",              "TEXT    DEFAULT ''"),
        ]
        for col, typedef in new_cols:
            try:
                cur.execute(f"ALTER TABLE matches ADD COLUMN {col} {typedef}")
            except Exception:
                pass  # Spalte existiert bereits

    def _migrate_v6_v7(self, cur):
        """Schema v7: gemeinsame Vorfahren + Geburtsorte (Compare-Seite)."""
        try:
            cur.execute("ALTER TABLE matches ADD COLUMN ancestors_fetched INTEGER DEFAULT 0")
        except Exception:
            pass
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS match_ancestors (
                test_guid               TEXT NOT NULL,
                match_guid              TEXT NOT NULL,
                ancestor_name           TEXT,
                birth_year              TEXT,
                death_year              TEXT,
                is_male                 INTEGER DEFAULT 0,
                relationship_to_sample  TEXT,
                relationship_to_match   TEXT,
                kinship_path_sample     TEXT,
                kinship_path_match      TEXT,
                in_match_tree           INTEGER DEFAULT 0,
                amt_gid                 TEXT,
                PRIMARY KEY (test_guid, match_guid, ancestor_name, kinship_path_sample)
            );
            CREATE INDEX IF NOT EXISTS idx_anc_match ON match_ancestors(match_guid);
            CREATE INDEX IF NOT EXISTS idx_anc_name  ON match_ancestors(ancestor_name);

            CREATE TABLE IF NOT EXISTS match_birthplaces (
                test_guid     TEXT NOT NULL,
                match_guid    TEXT NOT NULL,
                side          TEXT,
                place_name    TEXT,
                coords        TEXT,
                person_count  INTEGER DEFAULT 0,
                PRIMARY KEY (test_guid, match_guid, side, place_name)
            );
            CREATE INDEX IF NOT EXISTS idx_bp_match ON match_birthplaces(match_guid);
            CREATE INDEX IF NOT EXISTS idx_bp_place ON match_birthplaces(place_name);
        """)

    # ── Vorfahren / Geburtsorte (Compare) ──────────────────────────────────────

    def _migrate_v7_v8(self, cur):
        """Schema v8: volle Ahnentafel (Pedigree, bis ~5 Generationen) je Match."""
        try:
            cur.execute("ALTER TABLE matches ADD COLUMN pedigree_fetched INTEGER DEFAULT 0")
        except Exception:
            pass
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS match_pedigree (
                test_guid     TEXT NOT NULL,
                match_guid    TEXT NOT NULL,
                generation    INTEGER,        -- 1=Match selbst, 2=Eltern, 3=Großeltern …
                ahnen_path    TEXT,           -- F/M-Pfad ab Fokus, z.B. 'FMF'
                person_id     TEXT,           -- Ancestry-PersonId im Baum
                given_name    TEXT,
                surname       TEXT,
                is_male       INTEGER DEFAULT 0,
                birth_year    TEXT,
                birth_date    TEXT,
                birth_place   TEXT,
                death_year    TEXT,
                death_date    TEXT,
                death_place   TEXT,
                PRIMARY KEY (test_guid, match_guid, ahnen_path)
            );
            CREATE INDEX IF NOT EXISTS idx_ped_match ON match_pedigree(match_guid);
            CREATE INDEX IF NOT EXISTS idx_ped_surname ON match_pedigree(surname);
        """)

    def get_matches_needing_pedigree(self, test_guid: str) -> list:
        """[(match_guid, display_name)] für Matches mit Baum, deren Pedigree noch fehlt."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT match_guid, display_name FROM matches "
                "WHERE test_guid=? AND has_tree=1 "
                "AND COALESCE(pedigree_fetched,0)=0 "
                "ORDER BY shared_cm DESC", (test_guid,))
            return [(r["match_guid"], r["display_name"]) for r in cur.fetchall()]

    def save_match_pedigree(self, test_guid: str, match_guid: str, ancestors: list):
        """Speichert die Ahnentafel eines Matches (ersetzt vorhandene). Setzt Flag immer."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM match_pedigree WHERE test_guid=? AND match_guid=?",
                        (test_guid, match_guid))
            for a in ancestors:
                cur.execute("""
                    INSERT OR REPLACE INTO match_pedigree
                      (test_guid, match_guid, generation, ahnen_path, person_id,
                       given_name, surname, is_male, birth_year, birth_date,
                       birth_place, death_year, death_date, death_place)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (test_guid, match_guid, a.get("generation", 0),
                      a.get("ahnen_path", ""), a.get("person_id", ""),
                      a.get("given_name", ""), a.get("surname", ""),
                      1 if a.get("is_male") else 0,
                      a.get("birth_year", ""), a.get("birth_date", ""),
                      a.get("birth_place", ""), a.get("death_year", ""),
                      a.get("death_date", ""), a.get("death_place", "")))
            cur.execute("UPDATE matches SET pedigree_fetched=1 "
                        "WHERE match_guid=? AND test_guid=?", (match_guid, test_guid))

    def get_pedigree_for_match(self, test_guid: str, match_guid: str) -> list:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM match_pedigree WHERE test_guid=? AND match_guid=? "
                "ORDER BY generation, ahnen_path", (test_guid, match_guid))
            return [dict(r) for r in cur.fetchall()]

    def get_all_pedigrees(self, test_guid: str) -> dict:
        """{match_guid: {"name", "cm", "rows":[...]}} für alle geladenen Ahnentafeln
        (ohne Generation 1 = der Match selbst)."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT p.match_guid, m.display_name, m.shared_cm, p.generation,
                       p.ahnen_path, p.given_name, p.surname, p.birth_year,
                       p.birth_place, p.death_year
                FROM match_pedigree p
                JOIN matches m ON m.match_guid=p.match_guid AND m.test_guid=p.test_guid
                WHERE p.test_guid=? AND p.generation>=2
                ORDER BY m.shared_cm DESC, p.generation, p.ahnen_path
            """, (test_guid,))
            rows = cur.fetchall()
        out: dict = {}
        for r in rows:
            g = out.setdefault(r["match_guid"], {
                "name": r["display_name"], "cm": r["shared_cm"], "rows": []})
            g["rows"].append(dict(r))
        return out

    def get_matches_needing_ancestors(self, test_guid: str) -> list:
        """[(match_guid, display_name)] für Matches mit gemeinsamem Vorfahren,
        die noch nicht abgerufen wurden."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT match_guid, display_name FROM matches "
                "WHERE test_guid=? AND has_common_ancestor=1 "
                "AND COALESCE(ancestors_fetched,0)=0 "
                "ORDER BY shared_cm DESC", (test_guid,))
            return [(r["match_guid"], r["display_name"]) for r in cur.fetchall()]

    def save_match_ancestors(self, test_guid: str, match_guid: str,
                             ancestors: list, birthplaces: list):
        """Speichert Vorfahren + Geburtsorte eines Matches (ersetzt vorhandene)."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM match_ancestors WHERE test_guid=? AND match_guid=?",
                        (test_guid, match_guid))
            for a in ancestors:
                cur.execute("""
                    INSERT OR REPLACE INTO match_ancestors
                      (test_guid, match_guid, ancestor_name, birth_year, death_year,
                       is_male, relationship_to_sample, relationship_to_match,
                       kinship_path_sample, kinship_path_match, in_match_tree, amt_gid)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (test_guid, match_guid,
                      a.get("ancestor_name",""), a.get("birth_year",""),
                      a.get("death_year",""), 1 if a.get("is_male") else 0,
                      a.get("relationship_to_sample",""), a.get("relationship_to_match",""),
                      a.get("kinship_path_sample",""), a.get("kinship_path_match",""),
                      1 if a.get("in_match_tree") else 0, a.get("amt_gid","")))
            cur.execute("DELETE FROM match_birthplaces WHERE test_guid=? AND match_guid=?",
                        (test_guid, match_guid))
            for b in birthplaces:
                cur.execute("""
                    INSERT OR REPLACE INTO match_birthplaces
                      (test_guid, match_guid, side, place_name, coords, person_count)
                    VALUES (?,?,?,?,?,?)
                """, (test_guid, match_guid, b.get("side","match"),
                      b.get("place_name",""), b.get("coords",""),
                      int(b.get("person_count",0) or 0)))
            cur.execute("UPDATE matches SET ancestors_fetched=1 "
                        "WHERE match_guid=? AND test_guid=?", (match_guid, test_guid))

    def get_pedigree_groups(self, test_guid: str, min_matches: int = 2,
                            mode: str = "person") -> list:
        """Pedigree-Überlagerung: Vorfahren, die in mehreren Match-Ahnentafeln
        auftauchen. Generation 1 (=der Match selbst) wird ausgeschlossen.

        mode='person'  → Gruppierung nach Name+Geburtsjahr (echte Personen)
        mode='surname' → Gruppierung nach Nachname allein (Sippen-Cluster)
        mode='place'   → Gruppierung nach Geburtsort

        Liefert [{label, detail, count, matches:[(guid,name,path,gen)]}]."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT p.given_name, p.surname, p.birth_year, p.birth_place,
                       p.generation, p.ahnen_path, p.match_guid,
                       m.display_name, m.shared_cm
                FROM match_pedigree p
                JOIN matches m ON m.match_guid=p.match_guid AND m.test_guid=p.test_guid
                WHERE p.test_guid=? AND p.generation>=2
            """, (test_guid,))
            rows = cur.fetchall()

        groups: dict = {}
        for r in rows:
            given, sur = (r["given_name"] or "").strip(), (r["surname"] or "").strip()
            if mode == "surname":
                if not sur:
                    continue
                key, label, detail = ("S:"+sur.lower(), sur, "Nachname")
            elif mode == "place":
                place = (r["birth_place"] or "").strip()
                if not place:
                    continue
                key, label, detail = ("P:"+place.lower(), place, "Geburtsort")
            else:  # person
                if not (given or sur):
                    continue
                name = (given + " " + sur).strip()
                yr = r["birth_year"] or ""
                key = "N:" + name.lower() + "|" + yr
                label, detail = name, (f"*{yr}" if yr else "")
            g = groups.setdefault(key, {"label": label, "detail": detail,
                                        "_seen": set(), "matches": []})
            if r["match_guid"] in g["_seen"]:
                continue
            g["_seen"].add(r["match_guid"])
            g["matches"].append((r["match_guid"], r["display_name"],
                                 r["ahnen_path"], r["generation"], r["shared_cm"]))
        out = []
        for g in groups.values():
            if len(g["matches"]) >= min_matches:
                g.pop("_seen", None)
                out.append(dict(count=len(g["matches"]), **g))
        out.sort(key=lambda g: g["count"], reverse=True)
        return out

    def get_ancestors_for_match(self, match_guid: str) -> list:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM match_ancestors WHERE match_guid=? "
                        "ORDER BY length(kinship_path_sample), ancestor_name",
                        (match_guid,))
            return [dict(r) for r in cur.fetchall()]

    def get_ancestor_groups(self, test_guid: str, min_matches: int = 2) -> list:
        """Überlagerung: Vorfahren, die von mehreren Matches geteilt werden.
        Liefert [{ancestor_name, birth_year, count, matches:[(guid,name,path)]}]."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT a.ancestor_name, a.birth_year,
                       a.match_guid, m.display_name, a.kinship_path_sample, m.shared_cm
                FROM match_ancestors a
                JOIN matches m ON m.match_guid=a.match_guid AND m.test_guid=a.test_guid
                WHERE a.test_guid=? AND a.ancestor_name<>''
                ORDER BY a.ancestor_name, a.birth_year, m.shared_cm DESC
            """, (test_guid,))
            rows = cur.fetchall()
        groups: dict = {}
        for r in rows:
            key = (r["ancestor_name"], r["birth_year"] or "")
            g = groups.setdefault(key, {"ancestor_name": r["ancestor_name"],
                                        "birth_year": r["birth_year"] or "",
                                        "matches": []})
            g["matches"].append((r["match_guid"], r["display_name"],
                                 r["kinship_path_sample"], r["shared_cm"]))
        out = [dict(count=len(g["matches"]), **g) for g in groups.values()
               if len(g["matches"]) >= min_matches]
        out.sort(key=lambda g: g["count"], reverse=True)
        return out

    def _migrate_v2_v3(self, cur):
        """Schema v3: Shared-Matches-Tabelle."""
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS shared_matches (
                test_guid        TEXT NOT NULL,
                match_guid_a     TEXT NOT NULL,
                match_guid_b     TEXT NOT NULL,
                display_name_b   TEXT,
                shared_cm_b      REAL DEFAULT 0,
                shared_cm_ab     REAL DEFAULT 0,
                shared_segments_b INTEGER DEFAULT 0,
                relationship_b   TEXT,
                has_tree_b       INTEGER DEFAULT 0,
                fetched_at       TEXT,
                PRIMARY KEY (test_guid, match_guid_a, match_guid_b)
            );

            CREATE INDEX IF NOT EXISTS idx_sm_match_a
                ON shared_matches(test_guid, match_guid_a);
            CREATE INDEX IF NOT EXISTS idx_sm_match_b
                ON shared_matches(test_guid, match_guid_b);
            CREATE INDEX IF NOT EXISTS idx_sm_cm_b
                ON shared_matches(shared_cm_b DESC);

            -- Hilfstabelle: welche match_guid_a wurden bereits abgefragt?
            CREATE TABLE IF NOT EXISTS shared_matches_fetched (
                test_guid    TEXT NOT NULL,
                match_guid_a TEXT NOT NULL,
                fetched_at   TEXT,
                PRIMARY KEY (test_guid, match_guid_a)
            );
        """)

    # ── DNA-Kits ──────────────────────────────────────────────────────────────

    def upsert_kit(self, kit: DnaKit, last_sync: str = ""):
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO dna_kits (guid, name, test_type, created_date, is_owner, last_sync)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guid) DO UPDATE SET name=excluded.name, last_sync=excluded.last_sync
            """, (kit.guid, kit.name, kit.test_type, kit.created_date,
                  int(kit.is_owner), last_sync))

    def get_kits(self) -> list[DnaKit]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM dna_kits ORDER BY name")
            return [DnaKit(guid=r["guid"], name=r["name"], test_type=r["test_type"],
                           created_date=r["created_date"], is_owner=bool(r["is_owner"]))
                    for r in cur.fetchall()]

    # ── Matches ───────────────────────────────────────────────────────────────

    def upsert_match(self, m: DnaMatch):
        d = m.to_dict()
        with self._cursor() as cur:
            # Kit automatisch anlegen falls noch nicht vorhanden
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
                    tag_surname, tag_gender, tag_path, tags_json, meiosis, ignored
                ) VALUES (
                    :match_guid, :test_guid, :display_name,
                    :shared_cm, :shared_segments, :longest_segment,
                    :predicted_relationship, :confidence, :relationship_range,
                    :has_hint, :has_tree, :tree_size, :tree_id,
                    :starred, :note, :custom_relationship,
                    :ethnicity_regions, :last_login, :fetched_at, :raw_json,
                    :match_cluster_code, :created_date,
                    :tag_surname, :tag_gender, :tag_path, :tags_json, :meiosis, :ignored
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
                    ignored=excluded.ignored
            """, d)

    def bulk_upsert(self, matches: list[DnaMatch]) -> int:
        saved = 0
        for m in matches:
            self.upsert_match(m)
            saved += 1
        # WAL sofort in Hauptdatei schreiben → kein Datenverlust bei Absturz
        try:
            self._get_conn().execute("PRAGMA wal_checkpoint(PASSIVE)")
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
        sort_col: str               = "shared_cm",
        sort_asc: bool              = False,
        limit: int                  = 0,
        offset: int                 = 0,
    ) -> list[DnaMatch]:
        valid_cols = {"display_name", "shared_cm", "shared_segments",
                      "predicted_relationship", "fetched_at", "starred",
                      "tree_size", "tree_status", "has_common_ancestor", "gender"}
        sort_col  = sort_col if sort_col in valid_cols else "shared_cm"
        direction = "ASC" if sort_asc else "DESC"

        conditions, params = [], []
        if test_guid:
            conditions.append("test_guid = ?"); params.append(test_guid)
        if search:
            conditions.append("display_name LIKE ?"); params.append(f"%{search}%")
        if relationship and relationship != "(alle)":
            conditions.append("predicted_relationship = ?"); params.append(relationship)
        if starred_only:
            conditions.append("starred = 1")
        if has_tree_only:
            conditions.append("has_tree = 1")
        if min_cm > 0:
            conditions.append("shared_cm >= ?"); params.append(min_cm)

        where       = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        limit_clause = f"LIMIT {limit} OFFSET {offset}" if limit else ""
        sql = f"SELECT * FROM matches {where} ORDER BY {sort_col} {direction} {limit_clause}"

        with self._cursor() as cur:
            cur.execute(sql, params)
            return [DnaMatch.from_db_row(dict(r)) for r in cur.fetchall()]

    def match_exists(self, match_guid: str) -> bool:
        """Prüft ob ein Match bereits in der DB vorhanden ist."""
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM matches WHERE match_guid=? LIMIT 1", (match_guid,))
            return cur.fetchone() is not None

    def get_match_count(self, test_guid: Optional[str] = None) -> int:
        with self._cursor() as cur:
            if test_guid:
                cur.execute("SELECT COUNT(*) FROM matches WHERE test_guid=?", (test_guid,))
            else:
                cur.execute("SELECT COUNT(*) FROM matches")
            return cur.fetchone()[0]

    def get_distinct_relationships(self) -> list[str]:
        with self._cursor() as cur:
            cur.execute("""SELECT DISTINCT predicted_relationship FROM matches
                           WHERE predicted_relationship != '' ORDER BY predicted_relationship""")
            return [r[0] for r in cur.fetchall()]

    def update_note(self, match_guid: str, note: str):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._cursor() as cur:
            cur.execute("UPDATE matches SET note=? WHERE match_guid=?", (note, match_guid))
            cur.execute("""
                INSERT INTO user_notes(match_guid, note, updated_at) VALUES(?,?,?)
                ON CONFLICT(match_guid) DO UPDATE SET note=excluded.note, updated_at=excluded.updated_at
            """, (match_guid, note, now))

    # ── Shared Matches ────────────────────────────────────────────────────────

    def upsert_shared_match(self, sm: SharedMatch):
        d = sm.to_dict()
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO shared_matches (
                    test_guid, match_guid_a, match_guid_b, display_name_b,
                    shared_cm_b, shared_cm_ab, shared_segments_b,
                    relationship_b, has_tree_b, fetched_at
                ) VALUES (
                    :test_guid, :match_guid_a, :match_guid_b, :display_name_b,
                    :shared_cm_b, :shared_cm_ab, :shared_segments_b,
                    :relationship_b, :has_tree_b, :fetched_at
                )
                ON CONFLICT(test_guid, match_guid_a, match_guid_b) DO UPDATE SET
                    display_name_b   = excluded.display_name_b,
                    shared_cm_b      = excluded.shared_cm_b,
                    shared_cm_ab     = excluded.shared_cm_ab,
                    shared_segments_b= excluded.shared_segments_b,
                    relationship_b   = excluded.relationship_b,
                    has_tree_b       = excluded.has_tree_b,
                    fetched_at       = excluded.fetched_at
            """, d)

    def bulk_upsert_shared(self, items: list[SharedMatch]) -> int:
        for sm in items:
            self.upsert_shared_match(sm)
        return len(items)

    def mark_shared_fetched(self, test_guid: str, match_guid_a: str, fetched_at: str):
        with self._cursor() as cur:
            cur.execute("""
                INSERT INTO shared_matches_fetched(test_guid, match_guid_a, fetched_at)
                VALUES(?,?,?)
                ON CONFLICT(test_guid, match_guid_a) DO UPDATE SET fetched_at=excluded.fetched_at
            """, (test_guid, match_guid_a, fetched_at))

    def is_shared_fetched(self, test_guid: str, match_guid_a: str) -> bool:
        with self._cursor() as cur:
            cur.execute("""SELECT 1 FROM shared_matches_fetched
                           WHERE test_guid=? AND match_guid_a=?""",
                        (test_guid, match_guid_a))
            return cur.fetchone() is not None

    def get_shared_matches(
        self,
        test_guid: str,
        match_guid_a: str,
        min_cm: float = 0.0,
        sort_asc: bool = False,
    ) -> list[SharedMatch]:
        """Gibt alle shared Matches für einen primären Match zurück."""
        direction = "ASC" if sort_asc else "DESC"
        with self._cursor() as cur:
            cur.execute(f"""
                SELECT * FROM shared_matches
                WHERE test_guid=? AND match_guid_a=?
                  AND shared_cm_b >= ?
                ORDER BY shared_cm_b {direction}
            """, (test_guid, match_guid_a, min_cm))
            return [SharedMatch.from_db_row(dict(r)) for r in cur.fetchall()]

    def get_shared_match_count(self, test_guid: str,
                                match_guid_a: Optional[str] = None) -> int:
        with self._cursor() as cur:
            if match_guid_a:
                cur.execute("""SELECT COUNT(*) FROM shared_matches
                               WHERE test_guid=? AND match_guid_a=?""",
                            (test_guid, match_guid_a))
            else:
                cur.execute("SELECT COUNT(*) FROM shared_matches WHERE test_guid=?",
                            (test_guid,))
            return cur.fetchone()[0]

    def get_unfetched_match_guids(self, test_guid: str,
                                   min_cm: float = 0.0) -> list[tuple[str, str]]:
        """
        Gibt (match_guid, display_name) für alle Matches zurück,
        deren Shared Matches noch nicht heruntergeladen wurden.
        """
        with self._cursor() as cur:
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

    def get_all_shared_for_cluster(self, test_guid: str,
                                    min_cm_primary: float = 20.0,
                                    min_cm_shared: float = 20.0,
                                    max_cm_primary: float = 400.0,
                                    max_cm_shared: float = 400.0) -> list[dict]:
        """
        Gibt alle Shared-Match-Paare zurück, die für Clustering benötigt werden.

        Leeds-Methode: nur primäre Matches im Bereich [min_cm_primary,
        max_cm_primary] (Standard 90–400 cM) und nur Shared-Matches im Bereich
        [min_cm_shared, max_cm_shared]. Die OBERGRENZE ist entscheidend: enge
        Verwandte (>400 cM: Eltern, Geschwister, …) teilen DNA über ALLE
        Großelternlinien hinweg und würden sonst alle Cluster zu einem
        verschmelzen. max_cm <= 0 deaktiviert die jeweilige Obergrenze.
        """
        conds  = ["sm.test_guid = ?", "m_a.shared_cm >= ?", "sm.shared_cm_b >= ?"]
        params = [test_guid, min_cm_primary, min_cm_shared]
        if max_cm_primary and max_cm_primary > 0:
            conds.append("m_a.shared_cm <= ?");   params.append(max_cm_primary)
        if max_cm_shared and max_cm_shared > 0:
            conds.append("sm.shared_cm_b <= ?");  params.append(max_cm_shared)

        with self._cursor() as cur:
            cur.execute(f"""
                SELECT
                    sm.match_guid_a,
                    m_a.display_name    AS name_a,
                    m_a.shared_cm       AS cm_a,
                    m_a.predicted_relationship AS rel_a,
                    sm.match_guid_b,
                    sm.display_name_b   AS name_b,
                    sm.shared_cm_b      AS cm_b,
                    sm.relationship_b   AS rel_b
                FROM shared_matches sm
                JOIN matches m_a ON m_a.match_guid = sm.match_guid_a
                WHERE {" AND ".join(conds)}
                ORDER BY m_a.shared_cm DESC, sm.shared_cm_b DESC
            """, params)
            return [dict(r) for r in cur.fetchall()]

    # ── Statistiken ───────────────────────────────────────────────────────────

    def get_statistics(self, test_guid: Optional[str] = None) -> dict:
        cond = f"WHERE test_guid='{test_guid}'" if test_guid else ""
        with self._cursor() as cur:
            cur.execute(f"""
                SELECT
                    COUNT(*)            AS total,
                    MAX(shared_cm)      AS max_cm,
                    AVG(shared_cm)      AS avg_cm,
                    SUM(CASE WHEN starred=1 THEN 1 ELSE 0 END)      AS starred_count,
                    SUM(CASE WHEN has_tree=1 THEN 1 ELSE 0 END)     AS with_tree,
                    SUM(CASE WHEN note != '' AND note IS NOT NULL THEN 1 ELSE 0 END) AS with_note
                FROM matches {cond}
            """)
            r = dict(cur.fetchone())

            cur.execute(f"""
                SELECT predicted_relationship, COUNT(*) AS cnt
                FROM matches {cond}
                WHERE predicted_relationship != ''
                GROUP BY predicted_relationship
                ORDER BY cnt DESC LIMIT 10
            """)
            r["relationship_breakdown"] = [(row[0], row[1]) for row in cur.fetchall()]

            # Shared-Match-Statistik
            sm_cond = f"WHERE test_guid='{test_guid}'" if test_guid else ""
            cur.execute(f"SELECT COUNT(*) FROM shared_matches {sm_cond}")
            r["shared_total"] = cur.fetchone()[0]

            cur.execute(f"""
                SELECT COUNT(DISTINCT match_guid_a) FROM shared_matches {sm_cond}
            """)
            r["shared_primary_count"] = cur.fetchone()[0]
        return r
