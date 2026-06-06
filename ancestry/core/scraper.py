"""
Orchestiert den Download-Prozess (Matches + Shared Matches).
Läuft in einem eigenen Thread, damit die GUI nicht blockiert.
"""

import logging
import threading
import time as _time
from typing import Callable, Optional

from core.api import AncestryApiClient
from core.database import Database
from models import DnaMatch, SharedMatch
import config as cfg

log = logging.getLogger(__name__)

# Pause zwischen Name-Requests: großzügig um Rate-Limiting zu vermeiden.
# Bei 10.000 Matches = ca. 11h overnight-Lauf.
NAME_REQUEST_DELAY = 4.0


class DownloadResult:
    def __init__(self):
        self.fetched : int  = 0
        self.new     : int  = 0
        self.errors  : int  = 0
        self.success : bool = True
        self.message : str  = ""


class Scraper:
    """
    Steuert den Download von Matches und Shared Matches.

    Callbacks:
      on_progress(fetched, total_estimate, label)
      on_status(message)
      on_done(DownloadResult)
    """

    def __init__(
        self,
        client     : AncestryApiClient,
        db         : Database,
        on_progress: Optional[Callable] = None,
        on_status  : Optional[Callable] = None,
        on_done    : Optional[Callable] = None,
    ):
        self._client      = client
        self._db          = db
        self._on_progress = on_progress or (lambda *a: None)
        self._on_status   = on_status   or (lambda m: None)
        self._on_done     = on_done     or (lambda r: None)
        self._stop        = threading.Event()
        self._thread      : Optional[threading.Thread] = None

    # ── Öffentlich ──────────────────────────────────────────────────────────────

    def start_matches(self, test_guid: str,
                      filter_by: str = "ALL", sort_by: str = "RELATIONSHIP",
                      only_new: bool = False, fetch_names: bool = False):
        self._launch("_run_matches", test_guid, filter_by, sort_by,
                     only_new, fetch_names)

    def start_fetch_names(self, test_guid: str, min_cm: float = 0.0):
        """Lädt Namen für Matches ohne Namen via curl_cffi nach (kein Playwright)."""
        self._launch("_run_fetch_names", test_guid, min_cm)

    def start_shared(self, test_guid: str,
                     min_cm: float = 0.0, skip_existing: bool = True):
        self._launch("_run_shared", test_guid, min_cm, skip_existing)

    def stop(self):
        self._stop.set()
        log.info("Stoppanfrage gesendet.")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── Interne Threads ────────────────────────────────────────────────────────────

    def _launch(self, method_name: str, *args):
        if self._thread and self._thread.is_alive():
            log.warning("Download läuft bereits.")
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=getattr(self, method_name),
            args=args,
            daemon=True,
            name=f"scraper-{method_name}",
        )
        self._thread.start()

    def _run_matches(self, test_guid: str, filter_by: str, sort_by: str,
                     only_new: bool = False, fetch_names: bool = False):
        result = DownloadResult()
        mode   = "Nur neue" if only_new else "Alle"
        self._on_status(f"Starte Match-Download ({mode}) …")
        existing   = self._db.get_match_count(test_guid)
        total_est  = max(existing, 100)
        STOP_AFTER = 3

        consecutive_known_pages = 0
        batch: list[DnaMatch] = []
        try:
            for m in self._client.iter_matches(test_guid, filter_by, sort_by, self._stop):
                if self._stop.is_set():
                    break

                is_new = not self._db.match_exists(m.match_guid)

                if only_new and not is_new:
                    consecutive_known_pages += 1
                    if consecutive_known_pages >= STOP_AFTER * 20:
                        log.info("Nur-neue: %d bekannte Matches → stoppe.",
                                 consecutive_known_pages)
                        result.message = (f"Nur neue: {result.fetched} neue Matches "
                                          f"gefunden, dann Abbruch bei bekannten.")
                        break
                    continue
                else:
                    consecutive_known_pages = 0

                batch.append(m)
                result.fetched += 1
                if len(batch) >= cfg.PAGE_SIZE:
                    try:
                        saved = self._db.bulk_upsert(batch)
                        result.new += saved
                    except Exception as e:
                        log.error("bulk_upsert FEHLER: %s", e, exc_info=True)
                        result.errors += 1
                    batch.clear()
                self._on_progress(result.fetched, total_est, m.display_name)
                if result.fetched % 100 == 0:
                    self._on_status(f"{result.fetched} Matches geladen …")

            if batch:
                self._db.bulk_upsert(batch)
                result.new += len(batch)

            if not result.message:
                result.message = (f"Abgebrochen nach {result.fetched} Matches."
                                  if self._stop.is_set()
                                  else f"Fertig: {result.fetched} Matches gespeichert.")
            result.success = not self._stop.is_set()
        except Exception as e:
            log.exception("Fehler im Match-Download")
            result.success = False
            result.errors += 1
            result.message = f"Fehler: {e}"

        # Optional: Namen direkt im Anschluss nachladen (profileData-Bulk)
        if fetch_names and not self._stop.is_set():
            self._on_status(result.message + " – lade jetzt Namen …")
            self._run_fetch_names(test_guid, 0.0)
            return

        self._on_status(result.message)
        self._on_done(result)

    def _run_shared(self, test_guid: str, min_cm: float, skip_existing: bool):
        result = DownloadResult()

        if skip_existing:
            todo = self._db.get_unfetched_match_guids(test_guid, min_cm)
        else:
            matches = self._db.get_matches(test_guid=test_guid, min_cm=min_cm,
                                            sort_col="shared_cm")
            todo = [(m.match_guid, m.display_name) for m in matches]

        total = len(todo)
        log.info("Shared Matches: %d primäre Matches (min_cm=%.0f)", total, min_cm)
        self._on_status(f"Shared Matches: {total} primäre Matches …")

        from datetime import datetime, timezone

        for idx, (guid_a, name_a) in enumerate(todo):
            if self._stop.is_set():
                result.message = f"Abgebrochen nach {idx} / {total} primären Matches."
                result.success = False
                break

            self._on_progress(idx + 1, total, name_a)
            self._on_status(f"[{idx+1}/{total}] Shared Matches für: {name_a[:40]} …")

            batch: list[SharedMatch] = []
            try:
                for sm in self._client.iter_shared_matches(test_guid, guid_a, self._stop):
                    batch.append(sm)
                    result.fetched += 1

                self._db.bulk_upsert_shared(batch)
                result.new += len(batch)

                fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                self._db.mark_shared_fetched(test_guid, guid_a, fetched_at)

                if batch:
                    log.debug("  %s → %d shared matches", name_a[:30], len(batch))

            except Exception as e:
                log.error("Fehler bei Shared Matches für %s: %s", guid_a[:16], e)
                result.errors += 1

        if not result.message:
            result.success = True
            result.message = (f"Shared Matches fertig: "
                              f"{result.fetched} Einträge für {len(todo)} primäre Matches.")

        log.info(result.message)
        self._on_status(result.message)
        self._on_done(result)

    @staticmethod
    def _is_placeholder(name: str) -> bool:
        """True, wenn display_name nur ein Platzhalter ist (leer/Anonym/GUID-Kürzel)."""
        if not name:
            return True
        n = name.strip()
        if n in ("Anonym", "?") or len(n) <= 8:
            return True
        return n.endswith(" (m.)") or n.endswith(" (w.)")

    def _run_fetch_names(self, test_guid: str, min_cm: float):
        """Lädt pro Batch (20) Name + Geschlecht, gemeinsamen Vorfahren und
        Stammbaum-Status/-Größe via profileData / commonAncestors / treeData."""
        result = DownloadResult()

        all_matches = self._db.get_matches(test_guid=test_guid, min_cm=min_cm,
                                           sort_col="shared_cm")
        # Zu erledigen: Name fehlt ODER Stammbaum-Status noch nicht geladen.
        todo = [
            m for m in all_matches
            if self._is_placeholder(m.display_name)
               or not getattr(m, "tree_status", "")
        ]
        total = len(todo)
        self._on_status(f"Details nachladen: {total} Matches …")
        log.info("Detail-Download: %d Matches (min_cm=%.0f)", total, min_cm)

        if not todo:
            result.message = "Alle Matches sind bereits vollständig."
            result.success = True
            self._on_status(result.message)
            self._on_done(result)
            return

        batch_size = cfg.PROFILE_DATA_BATCH
        processed  = 0

        for start in range(0, total, batch_size):
            if self._stop.is_set():
                result.message = f"Abgebrochen nach {processed}/{total}."
                result.success = False
                break

            if self._client.detail_names_blocked():
                result.message = (
                    f"Detail-Download gestoppt: API nicht verfügbar – bitte "
                    f"ancestry.json neu exportieren ({result.new}/{processed})."
                )
                result.success = False
                break

            batch = todo[start:start + batch_size]
            sample_ids = [m.match_guid for m in batch]

            try:
                details = self._client.get_profile_details_bulk(test_guid, sample_ids)
            except Exception as e:
                log.debug("Bulk-Detail-Fehler: %s", e)
                details = {}

            try:
                common = self._client.get_common_ancestors(test_guid, sample_ids)
            except Exception as e:
                log.debug("commonAncestors-Fehler: %s", e)
                common = set()

            sid_to_ucdmid = {sid: d.get("ucdmid")
                             for sid, d in details.items() if d.get("ucdmid")}
            try:
                trees = self._client.get_tree_data_bulk(test_guid, sid_to_ucdmid)
            except Exception as e:
                log.debug("treeData-Fehler: %s", e)
                trees = {}

            try:
                with self._db._cursor() as cur:
                    for m in batch:
                        sid  = m.match_guid
                        d    = details.get(sid, {})
                        t    = trees.get(sid, {})
                        name = (d.get("name") or "").strip()

                        # Name nur setzen, wenn echt UND aktuell Platzhalter
                        if name and self._is_placeholder(m.display_name):
                            cur.execute(
                                "UPDATE matches SET display_name=? "
                                "WHERE match_guid=? AND test_guid=?",
                                (name, sid, test_guid))
                            result.new += 1

                        cur.execute(
                            "UPDATE matches SET "
                            "  gender=?, match_ucdmid=?, has_common_ancestor=?, "
                            "  tree_status=?, tree_size=?, has_tree=? "
                            "WHERE match_guid=? AND test_guid=?",
                            (
                                d.get("gender", "") or "",
                                d.get("ucdmid", "") or "",
                                1 if sid in common else 0,
                                t.get("tree_status", ""),
                                int(t.get("tree_size", 0) or 0),
                                1 if t.get("has_tree") else 0,
                                sid, test_guid,
                            ))
            except Exception as e:
                log.error("DB-Update Detail-Batch: %s", e)
                result.errors += 1

            processed += len(batch)
            result.fetched = processed
            last = batch[-1]
            self._on_progress(processed, total,
                              details.get(last.match_guid, {}).get(
                                  "name", last.match_guid[:8]))
            self._on_status(
                f"Details: {processed}/{total} verarbeitet, "
                f"{result.new} Namen, {len(common)}× Vorfahre im Batch …"
            )

            _time.sleep(NAME_REQUEST_DELAY)

        if not result.message:
            result.success = True
            result.message = (
                f"Details geladen: {processed}/{total} verarbeitet, "
                f"{result.new} neue Namen "
                f"({'abgebrochen' if self._stop.is_set() else 'fertig'})."
            )

        log.info(result.message)
        self._on_status(result.message)
        self._on_done(result)
