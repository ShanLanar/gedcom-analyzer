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
        # Gemerkter funktionierender Endpunkt (None=unbekannt, "__none__"=keiner)
        self._working_detail_url: Optional[str] = None

    # ── Match-Detail: voller Anzeigename ──────────────────────────────────────

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

    @staticmethod
    def _extract_name_from_html(html: str) -> str:
        """Extrahiert den Match-Namen aus der Compare-Seiten-HTML (Fallback)."""
        import re, json as _j

        # Next.js: <script id="__NEXT_DATA__" type="application/json">
        m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                      html, re.S)
        if m:
            try:
                data = _j.loads(m.group(1))
                # Rekursiv nach displayName suchen
                def find_name(d):
                    if isinstance(d, dict):
                        for k in ("displayName", "matchTestDisplayName",
                                  "adminDisplayName", "name"):
                            v = d.get(k, "")
                            if isinstance(v, str) and 2 < len(v) < 80:
                                if not any(x in v.lower() for x in
                                           ("ancestry", "login", "loading", "sign")):
                                    return v
                        for v in d.values():
                            r = find_name(v)
                            if r:
                                return r
                    elif isinstance(d, list):
                        for item in d:
                            r = find_name(item)
                            if r:
                                return r
                    return ""
                name = find_name(data)
                if name:
                    return name
            except Exception:
                pass

        # window.__INITIAL_STATE__
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;',
                      html, re.S)
        if m:
            try:
                data = _j.loads(m.group(1))
                name = AncestryApiClient._extract_name_from_detail(data)
                if name:
                    return name
            except Exception:
                pass

        # "You and NAME" (case-insensitive, auch Kleinbuchstaben)
        m = re.search(
            r'[Yy]ou and ([A-Za-zÄÖÜäöüß0-9][^<"]{2,60}?)'
            r'(?:\s*<|\s*"|\s*\||\s*\n)',
            html)
        if m:
            candidate = m.group(1).strip().rstrip('"').strip()
            if candidate and len(candidate) > 2 and "aren" not in candidate:
                return candidate

        # displayName direkt im HTML
        for pat in [
            r'"displayName"\s*:\s*"([^"]{2,80})"',
            r'"matchTestDisplayName"\s*:\s*"([^"]{2,80})"',
            r'"adminDisplayName"\s*:\s*"([^"]{2,80})"',
        ]:
            m = re.search(pat, html)
            if m:
                candidate = m.group(1).strip()
                if candidate and not any(x in candidate.lower() for x in
                                         ("ancestry", "dna", "login", "sign in",
                                          "loading", "null", "undefined")):
                    return candidate

        return ""

    def get_match_name_curl(self, test_guid: str, sample_id: str) -> str:
        """Holt den Match-Namen via curl_cffi.

        Strategie:
        1. Probiert die bekannten matchesservice JSON-Endpunkte (schnell, direkt).
           Beim ersten Treffer wird der Endpunkt gemerkt.
        2. Fällt zurück auf HTML-Parsen der Compare-Seite (mit Diagnose-Log).
        """
        # ── 1. JSON-API-Endpunkte ─────────────────────────────────────────────
        api_headers = dict(cfg.MATCHESSERVICE_HEADERS)
        api_headers["Referer"] = cfg.MATCHESSERVICE_REFERER.format(
            test_guid=test_guid)

        # Wenn bereits ein funktionierender Endpunkt bekannt ist, nur den probieren
        candidates = (
            [self._working_detail_url.format(
                test_guid=test_guid, sample_id=sample_id)]
            if self._working_detail_url and self._working_detail_url != "__none__"
            else [
                t.format(test_guid=test_guid, sample_id=sample_id)
                for t in cfg.MATCH_DETAIL_CANDIDATES
            ]
        )

        for url in candidates:
            try:
                r = self._s.get(url, headers=api_headers, timeout=20)
                if r.status_code == 200:
                    try:
                        data = r.json()
                        name = self._extract_name_from_detail(data)
                        if name:
                            # Endpunkt-Template merken
                            if self._working_detail_url is None:
                                tmpl = url.replace(test_guid, "{test_guid}") \
                                           .replace(sample_id, "{sample_id}")
                                self._working_detail_url = tmpl
                                log.info("Matchesservice-Endpunkt gefunden: %s",
                                         tmpl.split("/api/", 1)[-1])
                            log.debug("API Name %s → %r", sample_id[:8], name)
                            return name
                        log.debug("API %s HTTP 200 aber kein Name: %s",
                                  sample_id[:8], str(data)[:200])
                    except Exception as e:
                        log.debug("API JSON-Fehler %s: %s", sample_id[:8], e)
                else:
                    log.debug("API %s HTTP %s",
                              url.rsplit("/", 1)[-1][:20], r.status_code)
            except Exception as e:
                log.debug("API-Request %s: %s", sample_id[:8], e)

        # Alle Kandidaten erfolglos → Template als nicht verfügbar merken
        if self._working_detail_url is None:
            self._working_detail_url = "__none__"
            log.info("Matchesservice-Endpunkte alle ohne Treffer – "
                     "nutze HTML-Fallback.")

        # ── 2. HTML-Fallback: Compare-Seite parsen ────────────────────────────
        if self._working_detail_url == "__none__":
            url = (f"https://www.ancestry.com/dna/matches/"
                   f"{test_guid}/compare/{sample_id}")
            try:
                r = self._s.get(url, timeout=20, headers={
                    "Accept"  : "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Referer" : "https://www.ancestry.com/dna/matches/",
                })
                if r.status_code == 200:
                    name = self._extract_name_from_html(r.text)
                    if name:
                        log.debug("HTML Name %s → %r", sample_id[:8], name)
                        return name
                    # Einmalige Struktur-Diagnose für erste fehlgeschlagene Seite
                    if not getattr(self, "_html_diag_done", False):
                        self._html_diag_done = True
                        log.info("HTML-Diagnose %s (%d Bytes) – Anfang: %r",
                                 sample_id[:8], len(r.text), r.text[:800])
            except Exception as e:
                log.debug("HTML-Fallback %s: %s", sample_id[:8], e)

        return ""

    def detail_names_blocked(self) -> bool:
        return False

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
                log.debug("  tags=%s",
                          _dbgj.dumps(sample.get("tags"), ensure_ascii=False)[:500])
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
