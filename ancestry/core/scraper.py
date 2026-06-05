"""
Orchestriert den Download-Prozess (Matches + Shared Matches).
Läuft in einem eigenen Thread, damit die GUI nicht blockiert.
"""

import logging
import threading
from typing import Callable, Optional

from core.api import AncestryApiClient
from core.database import Database
from models import DnaMatch, SharedMatch
import config as cfg

log = logging.getLogger(__name__)


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

    # ── Öffentlich ────────────────────────────────────────────────────────────

    def start_matches(self, test_guid: str,
                      filter_by: str = "ALL", sort_by: str = "RELATIONSHIP",
                      only_new: bool = False, fetch_names: bool = False):
        """
        Startet den Match-Download.
        only_new=True: stoppt sobald bekannte Matches auftauchen (inkrementell).
        fetch_names=True: lädt pro Match den vollen Vornamen nach (langsam!).
        """
        self._launch("_run_matches", test_guid, filter_by, sort_by,
                     only_new, fetch_names)

    def start_shared(self, test_guid: str,
                     min_cm: float = 0.0, skip_existing: bool = True):
        """
        Startet den Shared-Match-Download für alle bereits gespeicherten Matches.
        min_cm: Nur primäre Matches ab dieser cM-Grenze berücksichtigen.
        skip_existing: Überspringe Matches, die bereits abgefragt wurden.
        """
        self._launch("_run_shared", test_guid, min_cm, skip_existing)

    def stop(self):
        self._stop.set()
        log.info("Stoppanfrage gesendet.")

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── Interne Threads ───────────────────────────────────────────────────────

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
        import time as _t
        result = DownloadResult()
        mode   = "Nur neue" if only_new else "Alle"
        if fetch_names:
            mode += " + volle Namen"
        self._on_status(f"Starte Match-Download ({mode}) …")
        existing   = self._db.get_match_count(test_guid)
        total_est  = max(existing, 100)
        STOP_AFTER = 3   # Seiten in Folge mit nur bekannten Matches → stoppen

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
                        log.info("Nur-neue: %d bekannte Matches in Folge → stoppe.",
                                 consecutive_known_pages)
                        result.message = (f"Nur neue: {result.fetched} neue Matches "
                                          f"gefunden, dann Abbruch bei bekannten.")
                        break
                    continue
                else:
                    consecutive_known_pages = 0

                # Optional: vollen Anzeigenamen pro Match nachladen (langsam).
                # Sobald feststeht, dass Ancestry den Detail-Host blockt, hört
                # der Scraper auf, es weiter zu versuchen (sonst 10.000 Fehlversuche).
                if fetch_names and not self._client.detail_names_blocked():
                    try:
                        full = self._client.get_match_name(test_guid, m.match_guid)
                        if full:
                            # Echten Namen setzen; Bemerkung (tag_surname) bleibt erhalten
                            m.display_name = full
                        elif self._client.detail_names_blocked():
                            self._on_status("Namen nicht abrufbar – "
                                            "Compare-Seite liefert keinen Namen.")
                    except Exception as e:
                        log.debug("Namens-Detail fehlgeschlagen für %s: %s",
                                  m.match_guid[:16], e)
                    if not self._client.detail_names_blocked():
                        _t.sleep(cfg.DETAIL_REQUEST_DELAY)

                batch.append(m)
                result.fetched += 1
                # Sofort nach jeder Seite (20 Matches) speichern
                if len(batch) >= cfg.PAGE_SIZE:
                    first_guid = batch[0].match_guid[:16] if batch else "?"
                    log.debug("Speichere %d Matches | erstes GUID: %s…", len(batch), first_guid)
                    try:
                        saved = self._db.bulk_upsert(batch)
                        result.new += saved
                        total = self._db.get_match_count()
                        log.debug("  ✓ %d gespeichert (gesamt in DB: %d)", saved, total)
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

        self._on_status(result.message)
        self._on_done(result)

    def _run_shared(self, test_guid: str, min_cm: float, skip_existing: bool):
        result = DownloadResult()

        # Alle primären Matches ermitteln
        if skip_existing:
            todo = self._db.get_unfetched_match_guids(test_guid, min_cm)
        else:
            matches = self._db.get_matches(test_guid=test_guid, min_cm=min_cm,
                                            sort_col="shared_cm")
            todo = [(m.match_guid, m.display_name) for m in matches]

        total = len(todo)
        log.info("Shared Matches: %d primäre Matches zu verarbeiten (min_cm=%.0f)",
                 total, min_cm)
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
