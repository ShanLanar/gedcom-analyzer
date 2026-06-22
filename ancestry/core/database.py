"""
SQLite-Datenbankschicht für ancestry_dna_tool.
Fassade über ancestry.core.db.* — alle öffentlichen Methoden delegieren an Repos.
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Generator, Optional

from ancestry.core.db.repos.cluster_hypotheses import ClusterHypothesesRepo
from ancestry.core.db.repos.kits import KitsRepo
from ancestry.core.db.repos.matches import MatchesRepo
from ancestry.core.db.repos.pedigree import PedigreeRepo
from ancestry.core.db.repos.research_tasks import ResearchTasksRepo
from ancestry.core.db.repos.segments import SegmentsRepo
from ancestry.core.db.repos.shared import SharedRepo
from ancestry.core.db.repos.stats import StatsRepo
from ancestry.models import DnaKit, DnaMatch, SharedMatch

log = logging.getLogger(__name__)


class Database:
    """Verwaltet die SQLite-Datenbank für DNA-Matches und Shared Matches."""

    SCHEMA_VERSION = 36

    def __init__(self, db_file: str = "ancestry_dna.db"):
        import os
        if not os.path.isabs(db_file):
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(base, db_file)
        self.db_file = db_file
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._init_db()
        self._kits    = KitsRepo(self)
        self._matches = MatchesRepo(self)
        self._ped     = PedigreeRepo(self)
        self._shared  = SharedRepo(self)
        self._stats   = StatsRepo(self)
        self._segs    = SegmentsRepo(self)
        self._tasks   = ResearchTasksRepo(self)
        self._hypos   = ClusterHypothesesRepo(self)

    # ── Verbindung ────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_file, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=OFF")
            self._conn.execute("PRAGMA synchronous=NORMAL")   # sicherer als OFF, schneller als FULL
            self._conn.execute("PRAGMA cache_size=-65536")    # 64 MB Cache (KB-denominiert)
            self._conn.execute("PRAGMA temp_store=MEMORY")    # Temp-Tabellen im RAM
            self._conn.execute("PRAGMA mmap_size=268435456")  # 256 MB Memory-Mapped I/O
            self._conn.execute("PRAGMA busy_timeout=5000")    # 5s auf Lock warten statt SQLITE_BUSY
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

    def _table_exists(self, name: str) -> bool:
        try:
            with self._cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (name,)
                )
                return cur.fetchone() is not None
        except Exception:
            return False

    def close(self):
        if self._conn:
            try:
                self._conn.execute("PRAGMA optimize")   # Planner-Statistiken aktuell halten
            except Exception:
                pass
            self._conn.close()
            self._conn = None

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_db(self):
        from ancestry.core.db.runner import run
        conn = self._get_conn()
        run(conn)
        # Stellt sicher, dass match_kit_membership alle Matches kennt.
        # Läuft nur wenn mkm leer aber matches befüllt (einmalige Reparatur).
        try:
            m_cnt   = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            mkm_cnt = conn.execute("SELECT COUNT(*) FROM match_kit_membership").fetchone()[0]
            if m_cnt > 0 and mkm_cnt < m_cnt:
                conn.execute(
                    "INSERT OR IGNORE INTO match_kit_membership (match_guid, test_guid) "
                    "SELECT match_guid, test_guid FROM matches"
                )
                conn.commit()
                log.info("match_kit_membership repariert: %d Einträge ergänzt", m_cnt - mkm_cnt)
        except Exception as e:
            log.debug("mkm-Reparatur: %s", e)
        # Waisenzeilen bereinigen (FK=OFF → manuelle Integrität).
        # Läuft im Hintergrund und NUR wenn tatsächlich Waisen vorhanden sind
        # (EXISTS-Check zuerst — verhindert unnötige DELETEs auf gefüllten DBs).
        def _fk_cleanup():
            try:
                from ancestry.core.db.connection import _open
                bg = _open(self.db_file)
                for tbl, col in (("shared_matches", "match_guid"),
                                 ("match_pedigree", "match_guid")):
                    has_orphan = bg.execute(
                        f"SELECT 1 FROM {tbl} t "
                        f"WHERE NOT EXISTS (SELECT 1 FROM matches m WHERE m.match_guid=t.{col}) "
                        "LIMIT 1"
                    ).fetchone()
                    if has_orphan:
                        bg.execute(
                            f"DELETE FROM {tbl} t "
                            f"WHERE NOT EXISTS (SELECT 1 FROM matches m WHERE m.match_guid=t.{col})"
                        )
                        log.info("FK-Cleanup: Waisenzeilen in %s bereinigt", tbl)
                bg.commit()
                bg.close()
            except Exception as e:
                log.debug("FK-Cleanup übersprungen: %s", e)
        threading.Thread(target=_fk_cleanup, daemon=True, name="fk_cleanup").start()
        log.debug("DB initialisiert: %s (Schema v%d)", self.db_file, self.SCHEMA_VERSION)

    # ── Kits ──────────────────────────────────────────────────────────────────

    def upsert_kit(self, *a, **kw) -> None:              return self._kits.upsert_kit(*a, **kw)
    def get_kits(self, *a, **kw) -> list:                return self._kits.get_kits(*a, **kw)
    def save_kit_ethnicity(self, *a, **kw) -> None:      return self._kits.save_kit_ethnicity(*a, **kw)
    def get_kit_ethnicity(self, *a, **kw) -> list:       return self._kits.get_kit_ethnicity(*a, **kw)
    def save_kit_traits(self, *a, **kw) -> None:         return self._kits.save_kit_traits(*a, **kw)
    def get_kit_traits(self, *a, **kw) -> list:          return self._kits.get_kit_traits(*a, **kw)

    # ── Matches ───────────────────────────────────────────────────────────────

    def upsert_match(self, *a, **kw) -> None:            return self._matches.upsert_match(*a, **kw)
    def bulk_upsert(self, *a, **kw) -> int:              return self._matches.bulk_upsert(*a, **kw)
    def get_matches(self, *a, **kw) -> list:             return self._matches.get_matches(*a, **kw)
    def match_exists(self, *a, **kw) -> bool:            return self._matches.match_exists(*a, **kw)
    def match_exists_for_kit(self, *a, **kw) -> bool:    return self._matches.match_exists_for_kit(*a, **kw)
    def get_match_count(self, *a, **kw) -> int:          return self._matches.get_match_count(*a, **kw)
    def get_distinct_relationships(self, *a, **kw) -> list:  return self._matches.get_distinct_relationships(*a, **kw)
    def update_note(self, *a, **kw) -> None:             return self._matches.update_note(*a, **kw)
    def bump_name_attempts(self, *a, **kw) -> None:      return self._matches.bump_name_attempts(*a, **kw)
    def reset_name_attempts(self, *a, **kw) -> int:      return self._matches.reset_name_attempts(*a, **kw)
    def set_endogamy_cluster(self, *a, **kw) -> None:    return self._matches.set_endogamy_cluster(*a, **kw)
    def set_probable_origin(self, *a, **kw) -> None:     return self._matches.set_probable_origin(*a, **kw)
    def set_ml_origin(self, *a, **kw) -> None:           return self._matches.set_ml_origin(*a, **kw)
    def update_research_flags(self, *a, **kw) -> None:   return self._matches.update_research_flags(*a, **kw)
    def get_endogamy_candidates(self, *a, **kw) -> list: return self._matches.get_endogamy_candidates(*a, **kw)
    def auto_flag_endogamy(self, *a, **kw) -> int:       return self._matches.auto_flag_endogamy(*a, **kw)
    def bulk_set_side(self, *a, **kw) -> int:            return self._matches.bulk_set_side(*a, **kw)
    def get_paternal_maternal_overlap(self, *a, **kw) -> dict: return self._matches.get_paternal_maternal_overlap(*a, **kw)
    def link_gedmatch_bridges(self, *a, **kw) -> int:    return self._matches.link_gedmatch_bridges(*a, **kw)
    def get_bridge_hit_counts(self, *a, **kw) -> dict:   return self._matches.get_bridge_hit_counts(*a, **kw)
    def get_unfetched_match_guids(self, *a, **kw) -> list: return self._matches.get_unfetched_match_guids(*a, **kw)

    # ── Research-Tasks (B1) ─────────────────────────────────────────────────────

    def add_task(self, *a, **kw) -> int:                 return self._tasks.add_task(*a, **kw)
    def update_task(self, *a, **kw) -> None:             return self._tasks.update_task(*a, **kw)
    def set_task_status(self, *a, **kw) -> None:         return self._tasks.set_status(*a, **kw)
    def delete_task(self, *a, **kw) -> None:             return self._tasks.delete_task(*a, **kw)
    def get_tasks(self, *a, **kw) -> list:               return self._tasks.get_tasks(*a, **kw)
    def count_open_tasks(self, *a, **kw) -> int:         return self._tasks.count_open(*a, **kw)

    # ── Cluster-Hypothesen (B3) ─────────────────────────────────────────────────

    def set_cluster_hypothesis(self, *a, **kw) -> None:  return self._hypos.set_hypothesis(*a, **kw)
    def get_cluster_hypothesis(self, *a, **kw):          return self._hypos.get_hypothesis(*a, **kw)
    def get_cluster_hypotheses(self, *a, **kw) -> list:  return self._hypos.get_all_for_kit(*a, **kw)
    def delete_cluster_hypothesis(self, *a, **kw) -> None: return self._hypos.delete_hypothesis(*a, **kw)
    def suggest_cluster_mrca(self, *a, **kw) -> list:    return self._hypos.suggest_mrca(*a, **kw)

    # ── Pedigree ──────────────────────────────────────────────────────────────

    def get_matches_needing_pedigree(self, *a, **kw) -> list:    return self._ped.get_matches_needing_pedigree(*a, **kw)
    def save_match_pedigree(self, *a, **kw) -> None:             return self._ped.save_match_pedigree(*a, **kw)
    def get_pedigree_for_match(self, *a, **kw) -> list:          return self._ped.get_pedigree_for_match(*a, **kw)
    def get_all_pedigrees(self, *a, **kw) -> dict:               return self._ped.get_all_pedigrees(*a, **kw)
    def get_matches_needing_ancestors(self, *a, **kw) -> list:   return self._ped.get_matches_needing_ancestors(*a, **kw)
    def save_match_ancestors(self, *a, **kw) -> None:            return self._ped.save_match_ancestors(*a, **kw)
    def get_ancestors_for_match(self, *a, **kw) -> list:         return self._ped.get_ancestors_for_match(*a, **kw)
    def get_pedigree_groups(self, *a, **kw) -> list:             return self._ped.get_pedigree_groups(*a, **kw)
    def get_ancestor_groups(self, *a, **kw) -> list:             return self._ped.get_ancestor_groups(*a, **kw)
    def get_pedigree_summary_for_match(self, *a, **kw) -> str:   return self._ped.get_pedigree_summary_for_match(*a, **kw)
    def get_pedigree_completeness_per_match(self, *a, **kw) -> list: return self._ped.get_pedigree_completeness_per_match(*a, **kw)
    def get_cluster_ancestor_years(self, *a, **kw) -> list:      return self._ped.get_cluster_ancestor_years(*a, **kw)
    def get_match_birthplaces(self, *a, **kw) -> list:          return self._ped.get_match_birthplaces(*a, **kw)

    # ── Shared Matches ────────────────────────────────────────────────────────

    def upsert_shared_match(self, *a, **kw) -> None:     return self._shared.upsert_shared_match(*a, **kw)
    def bulk_upsert_shared(self, *a, **kw) -> int:       return self._shared.bulk_upsert_shared(*a, **kw)
    def register_shared_stubs(self, *a, **kw) -> None:   return self._shared.register_shared_stubs(*a, **kw)
    def mark_shared_fetched(self, *a, **kw) -> None:     return self._shared.mark_shared_fetched(*a, **kw)
    def is_shared_fetched(self, *a, **kw) -> bool:       return self._shared.is_shared_fetched(*a, **kw)
    def get_shared_clusters(self, *a, **kw) -> list:     return self._shared.get_shared_clusters(*a, **kw)
    def get_pairwise_shared(self, *a, **kw) -> list:     return self._shared.get_pairwise_shared(*a, **kw)
    def get_shared_matches(self, *a, **kw) -> list:      return self._shared.get_shared_matches(*a, **kw)
    def delete_shared_for(self, *a, **kw) -> None:       return self._shared.delete_shared_for(*a, **kw)
    def reset_shared_matches(self, *a, **kw) -> int:     return self._shared.reset_shared_matches(*a, **kw)
    def get_shared_match_count(self, *a, **kw) -> int:   return self._shared.get_shared_match_count(*a, **kw)
    def get_all_shared_for_cluster(self, *a, **kw) -> list:  return self._shared.get_all_shared_for_cluster(*a, **kw)
    def get_shared_pairs_set(self, *a, **kw) -> set:         return self._shared.get_shared_pairs_set(*a, **kw)

    # ── Statistiken ───────────────────────────────────────────────────────────

    def get_statistics(self, *a, **kw) -> dict:          return self._stats.get_statistics(*a, **kw)
    def invalidate_stats_cache(self) -> None:            self._stats.invalidate_stats_cache()

    # ── Segmente ──────────────────────────────────────────────────────────────

    def bulk_upsert_segments(self, *a, **kw) -> int:     return self._segs.bulk_upsert_segments(*a, **kw)
    def get_segments(self, *a, **kw) -> list:            return self._segs.get_segments(*a, **kw)
