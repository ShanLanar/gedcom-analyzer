"""
Ancestry DNA API-Client – discoveryui-Format (Stand 2026).
Mit adaptivem Rate-Limiting und Jitter.
"""

import time
import math
import random
import logging
from typing import Iterator, Optional

try:
    from curl_cffi import requests as cfr
except ImportError:
    import requests as cfr

import config as cfg
from models import DnaKit, DnaMatch, SharedMatch

log = logging.getLogger(__name__)

RETRY_STATUSES  = {429, 500, 502, 503, 504}
MAX_RETRIES     = 5
RETRY_DELAYS    = [30, 60, 90, 120, 180]

BURST_LIMIT     = 3
BURST_PAUSE     = 20.0


def _jitter(base: float) -> float:
    return base * (0.8 + random.random() * 0.4)


def _api_get(session, url: str, extra_headers: dict = None) -> Optional[object]:
    headers = {
        "Accept"          : "application/json, text/plain, */*",
        "Accept-Language" : "de-DE,de;q=0.9,en-US;q=0.8",
        "Referer"         : cfg.BASE_URL + "/discoveryui-matches/",
        "X-Requested-With": "XMLHttpRequest",
    }
    if extra_headers:
        headers.update(extra_headers)
    csrf = session.cookies.get("_csrf") or session.cookies.get("XSRF-TOKEN") or ""
    if csrf:
        headers["X-CSRF-Token"] = csrf

    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, headers=headers, timeout=cfg.REQUEST_TIMEOUT)

            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", 0))
                delay = max(retry_after, RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
                log.warning("429 Rate-Limit → warte %ds …", delay)
                time.sleep(delay)
                continue

            if r.status_code in RETRY_STATUSES:
                delay = _jitter(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
                log.warning("HTTP %s Versuch %d/%d → warte %.1fs …",
                            r.status_code, attempt+1, MAX_RETRIES, delay)
                time.sleep(delay)
                continue

            return r

        except Exception as e:
            delay = _jitter(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
            log.warning("Fehler Versuch %d/%d: %s → warte %.1fs …",
                        attempt+1, MAX_RETRIES, e, delay)
            time.sleep(delay)

    log.error("Alle %d Versuche fehlgeschlagen: %s", MAX_RETRIES, url)
    return None


class AncestryApiClient:

    def __init__(self, session):
        self._s = session
        self._working_detail_url: Optional[str] = None
        self._session_warmed_up = False
        self._consecutive_520 = 0         # Zähler: 520-Antworten in Folge

    def _warm_up_session(self, test_guid: str):
        """Öffnet die Match-Listenseite und extrahiert Namen aus SSR-Daten (falls vorhanden)."""
        if self._session_warmed_up:
            return
        self._session_warmed_up = True
        url = f"{cfg.BASE_URL}/dna/matches/{test_guid}/list"
        try:
            r = self._s.get(url, timeout=cfg.REQUEST_TIMEOUT)
            log.debug("Warm-up list → HTTP %s (%d Bytes)", r.status_code, len(r.content))
            if r.status_code == 200:
                # Ersten 5000 Zeichen loggen um HTML-Struktur zu erkennen
                snippet = r.text[:5000]
                log.debug("Warm-up HTML Anfang:\n%s", snippet)
        except Exception as e:
            log.debug("Warm-up fehlgeschlagen: %s", e)

    @staticmethod
    def _extract_name_from_detail(data: dict) -> str:
        """Sucht in einer JSON-Antwort nach dem vollen Anzeigenamen."""
        if not isinstance(data, dict):
            return ""

        def nested(d, *path):
            cur = d
            for k in path:
                if not isinstance(cur, dict):
                    return ""
                cur = cur.get(k)
            return cur if isinstance(cur, str) else ""

        return (nested(data, "displayName")
                or nested(data, "matchProfile", "displayName")
                or nested(data, "matchProfile", "name")
                or nested(data, "adminDisplayName")
                or nested(data, "admin", "displayName")
                or nested(data, "matchTestDisplayName")
                or nested(data, "userDisplayName")
                or nested(data, "match", "displayName")
                or nested(data, "testDisplayName")
                or nested(data, "name")
                or "")

    def get_match_name_curl(self, test_guid: str, sample_id: str) -> str:
        """Holt den Match-Namen via matchesservice JSON-API (curl_cffi).

        Verwendet _api_get für eingebautes 429-Handling (Retry-After).
        Merkt sich den ersten funktionierenden Endpunkt-Template.
        Setzt __none__ nur bei echten 404-Antworten, nicht bei Rate-Limiting.
        """
        if self._working_detail_url == "__none__":
            return ""
        if self._consecutive_520 >= 3:
            # Nach 3x 520 in Folge aufgeben – Akamai blockiert dauerhaft
            self._working_detail_url = "__none__"
            log.info("Matchesservice: 3× HTTP 520 in Folge – Akamai blockiert, "
                     "Namen-Download gestoppt.")
            return ""

        # Einmalig Listenseite besuchen → Akamai-Session-Cookie setzen
        self._warm_up_session(test_guid)

        api_headers = {
            **cfg.MATCHESSERVICE_HEADERS,
            "Referer": cfg.MATCHESSERVICE_REFERER.format(test_guid=test_guid),
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

        # Wenn bereits ein funktionierender Endpunkt bekannt: nur den probieren
        if self._working_detail_url:
            candidates = [self._working_detail_url.format(
                test_guid=test_guid, sample_id=sample_id)]
        else:
            candidates = [
                t.format(test_guid=test_guid, sample_id=sample_id)
                for t in cfg.MATCH_DETAIL_CANDIDATES
            ]

        not_found_count = 0
        for url in candidates:
            r = _api_get(self._s, url, extra_headers=api_headers)

            if r is None:
                log.debug("Namen-API %s: alle Retries erschöpft", url.split("/api/", 1)[-1][:40])
                continue

            log.debug("Namen-API %-45s → HTTP %s",
                      url.split("/api/", 1)[-1][:45], r.status_code)

            if r.status_code == 200:
                self._consecutive_520 = 0
                try:
                    data = r.json()
                    name = self._extract_name_from_detail(data)
                    if name:
                        if not self._working_detail_url:
                            tmpl = (url
                                    .replace(test_guid, "{test_guid}")
                                    .replace(sample_id, "{sample_id}"))
                            self._working_detail_url = tmpl
                            log.info("Matchesservice-Endpunkt aktiv: %s",
                                     tmpl.split("/api/", 1)[-1])
                        log.debug("API Name %s → %r", sample_id[:8], name)
                        return name
                    log.debug("API %s HTTP 200, kein Name: %s",
                              sample_id[:8], str(data)[:200])
                except Exception as e:
                    log.debug("API JSON %s: %s", sample_id[:8], e)

            elif r.status_code in (404, 410):
                not_found_count += 1

            elif r.status_code == 520:
                # 520 nur für matchesservice zählen (Akamai-Pfad)
                if "matchesservice" in url:
                    self._consecutive_520 += 1
                else:
                    not_found_count += 1

        if self._working_detail_url is None and not_found_count == len(candidates):
            self._working_detail_url = "__none__"
            log.info("Matchesservice: alle Endpunkte liefern 404 – "
                     "Namen-Download nicht möglich.")

        return ""

    def detail_names_blocked(self) -> bool:
        return self._working_detail_url == "__none__"

    def stop_playwright(self):
        pass

    # ── DNA-Kits ──────────────────────────────────────────────────────────────

    def get_dna_kits(self, uid: str) -> list[DnaKit]:
        r = _api_get(self._s, cfg.MANAGE_TESTS_URL.format(uid=uid))
        if not r or r.status_code != 200:
            return []
        try:
            data = r.json()
        except Exception:
            return []
        kits = []
        for item in (data if isinstance(data, list) else data.get("kits", [])):
            kits.append(DnaKit(
                guid        = item.get("testGuid") or item.get("guid", ""),
                name        = item.get("displayName") or item.get("name", ""),
                test_type   = item.get("testType", "AncestryDNA"),
                created_date= item.get("createDate", ""),
                is_owner    = item.get("isOwner", True),
            ))
        log.info("%d DNA-Kit(s) gefunden.", len(kits))
        return kits

    def detect_kit_from_uid(self, uid: str) -> Optional[str]:
        r = _api_get(self._s, cfg.MANAGE_TESTS_URL.format(uid=uid))
        if r and r.status_code == 200:
            try:
                data  = r.json()
                items = data if isinstance(data, list) else data.get("kits", [])
                for item in items:
                    guid = item.get("testGuid") or item.get("guid")
                    if guid:
                        return guid
            except Exception:
                pass
        return None

    def get_match_count(self, test_guid: str) -> int:
        url = cfg.MATCH_COUNT_URL.format(test_guid=test_guid)
        r   = _api_get(self._s, url)
        if r and r.status_code == 200:
            try:
                data = r.json()
                if isinstance(data, (int, float)):
                    return int(data)
                return int(data.get("count") or data.get("totalCount") or 0)
            except Exception:
                pass
        return 0

    # ── Matches ───────────────────────────────────────────────────────────────

    def iter_matches(
        self,
        test_guid  : str,
        filter_by  : str = "ALL",
        sort_by    : str = "RELATIONSHIP",
        stop_event = None,
    ) -> Iterator[DnaMatch]:
        from datetime import datetime, timezone
        fetched_at  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        page        = 1
        total_pages = None
        fetched     = 0
        pages_since_burst_pause = 0
        start_time  = time.time()

        total_count = self.get_match_count(test_guid)
        if total_count:
            log.info("Gesamtzahl Matches: %d (→ ca. %d Seiten)",
                     total_count, math.ceil(total_count / cfg.PAGE_SIZE))

        while True:
            if stop_event and stop_event.is_set():
                return

            if pages_since_burst_pause >= BURST_LIMIT:
                pause = _jitter(BURST_PAUSE)
                log.debug("Burst-Pause %.1fs nach %d Seiten …", pause, BURST_LIMIT)
                time.sleep(pause)
                pages_since_burst_pause = 0

            url = (cfg.MATCHES_URL.format(test_guid=test_guid)
                   + f"?currentPage={page}&itemsPerPage={cfg.PAGE_SIZE}")
            if sort_by and sort_by != "RELATIONSHIP":
                url += f"&sortBy={sort_by}"
            if filter_by and filter_by != "ALL":
                url += f"&filterBy={filter_by}"

            log.debug("GET Seite %d  %s", page, url)
            r = _api_get(self._s, url)

            if r is None:
                log.error("Seite %d: kein Response.", page)
                break
            if r.status_code in (401, 403):
                log.error("HTTP %s – Cookies abgelaufen.", r.status_code)
                break
            if r.status_code == 404:
                log.error("HTTP 404 – Endpunkt nicht gefunden.")
                break
            if r.status_code != 200:
                log.error("HTTP %s auf Seite %d.", r.status_code, page)
                break

            try:
                data = r.json()
            except Exception as e:
                log.error("JSON-Fehler: %s", e)
                break

            if total_pages is None:
                tp = data.get("totalPages") or data.get("paging", {}).get("totalPages")
                if tp:
                    total_pages = tp
                elif total_count:
                    total_pages = math.ceil(total_count / max(cfg.PAGE_SIZE, 1))
                else:
                    total_pages = 9999

            raw = (data.get("matchList")
                   or data.get("matchGroups")
                   or data.get("matches")
                   or data.get("data") or [])
            if raw and isinstance(raw[0], dict) and "matches" in raw[0]:
                raw = [m for grp in raw for m in grp.get("matches", [])]

            if not raw:
                log.info("Keine weiteren Matches auf Seite %d.", page)
                break

            api_page = data.get("currentPage", "?")
            api_total = data.get("totalPages", "?")
            first_sid = raw[0].get("sampleId","?")[:16] if raw else "leer"
            log.debug("  API: currentPage=%s/%s | erster sampleId=%s",
                      api_page, api_total, first_sid)
            if page == 1 and raw and not getattr(self, "_logged_fields", False):
                self._logged_fields = True
                import json as _dbgj
                sample = raw[0]
                log.debug("Match-Felder: top-level=%s", sorted(sample.keys()))
                log.debug("  RAW (1. Match): %s",
                          _dbgj.dumps(sample, ensure_ascii=False)[:2000])
            for item in raw:
                m = DnaMatch.from_api_response(item, test_guid, fetched_at)
                if m.match_guid:
                    fetched += 1
                    yield m

            pages_since_burst_pause += 1
            elapsed  = time.time() - start_time
            rate     = fetched / elapsed if elapsed > 0 else 0
            total_est = (total_pages or 1) * cfg.PAGE_SIZE
            remaining = max(0, total_est - fetched)
            eta_min   = (remaining / rate / 60) if rate > 0 else 0

            if page % 10 == 0 or len(raw) < cfg.PAGE_SIZE:
                log.info("Seite %d/%s | %d Matches | %.0f/min | ETA ~%.0f min",
                         page, total_pages or "?", fetched, rate*60, eta_min)

            if page >= (total_pages or 9999):
                break
            if cfg.MAX_PAGES and page >= cfg.MAX_PAGES:
                break

            page += 1
            time.sleep(_jitter(cfg.REQUEST_DELAY))

        elapsed = time.time() - start_time
        log.info("Download abgeschlossen: %d Matches in %.1f min",
                 fetched, elapsed / 60)

    # ── Shared Matches ────────────────────────────────────────────────────────

    def iter_shared_matches(
        self,
        test_guid   : str,
        match_guid_a: str,
        stop_event  = None,
    ) -> Iterator[SharedMatch]:
        from datetime import datetime, timezone
        fetched_at  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base_url    = cfg.SHARED_MATCHES_URL.format(test_guid=test_guid)
        page        = 1
        total_pages = None
        fetched     = 0

        while True:
            if stop_event and stop_event.is_set():
                return

            url = (base_url
                   + f"?matchSampleId={match_guid_a}"
                   + f"&currentPage={page}&itemsPerPage={cfg.PAGE_SIZE}")

            r = _api_get(self._s, url)
            if r is None:
                return
            if r.status_code in (401, 403, 404):
                log.debug("Shared Matches HTTP %s für %s", r.status_code, match_guid_a[:16])
                return
            if r.status_code != 200:
                return

            try:
                data = r.json()
            except Exception:
                return

            if total_pages is None:
                total_pages = data.get("totalPages") or 1
                log.debug("Shared Matches für %s: %d Seiten",
                          match_guid_a[:16], total_pages)

            raw = data.get("matchList") or []
            if not raw:
                break

            for item in raw:
                if item.get("sampleId") == match_guid_a:
                    continue
                sm = SharedMatch.from_api_response(
                    item, test_guid, match_guid_a, fetched_at)
                if sm.match_guid_b:
                    fetched += 1
                    yield sm

            if page >= total_pages or data.get("isLastPage"):
                break
            page += 1
            time.sleep(_jitter(cfg.REQUEST_DELAY))

        log.debug("Shared Matches %s: %d gesamt", match_guid_a[:16], fetched)

    # ── Notizen ─────────────────────────────────────────────────────────────────

    def save_match_note(self, test_guid: str, match_guid: str, note: str) -> bool:
        url = f"{cfg.DNA_LIST_BASE}/note/{test_guid}/{match_guid}"
        try:
            r = self._s.put(url, json={"note": note}, timeout=cfg.REQUEST_TIMEOUT)
            return r.status_code in (200, 204)
        except Exception as e:
            log.error("Notiz-Fehler: %s", e)
            return False
