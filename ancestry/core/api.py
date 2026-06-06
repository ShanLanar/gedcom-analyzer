"""
Ancestry DNA API-Client – discoveryui-Format (Stand 2026).
Mit adaptivem Rate-Limiting und Jitter.
"""

import time
import math
import random
import logging
import base64
import json
import uuid
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


def _build_ube_header(session) -> str:
    """Baut den ancestry-context-ube Header (base64-JSON) den Ancestry erwartet."""
    session_id = session.cookies.get("ANCSESSIONID") or str(uuid.uuid4())
    payload = {
        "eventId": "00000000-0000-0000-0000-000000000000",
        "correlatedScreenViewedId": str(uuid.uuid4()),
        "correlatedSessionId": session_id,
        "screenNameStandard": "ancestry : global : en : dna-matches-ui : match-list",
        "screenName": "ancestry us : dnamatches-matchlistui : dna-matches-ui : match-list",
        "userConsent": "necessary|preference|performance|analytics1st|analytics3rd|advertising1st|attribution3rd",
        "vendors": "adobemc",
        "vendorConfigurations": json.dumps({"adobemc": {"mid": "", "sdid": ""}}),
    }
    return base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()


def _is_initials_only(name: str) -> bool:
    """True bei initialisierten Privatprofilen wie 'L. S.' oder 'K. F.'."""
    import re
    return bool(re.fullmatch(r"(?:[A-ZÄÖÜ]\.\s*){1,3}", name.strip()))


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
        self._detail_blocked = False   # True wenn Namen-API 401/403 lieferte

    @staticmethod
    def _pick_name(info: dict) -> str:
        """Wählt aus einem profileData-Eintrag den besten Anzeigenamen."""
        if not isinstance(info, dict):
            return ""
        name = (info.get("matchName") or "").strip()
        # "L. S." o.ä. sind initialisierte Privatprofile – managedName ist
        # oft aussagekräftiger (z.B. "kathy_stevers").
        managed = (info.get("managedName") or "").strip()
        if name and not _is_initials_only(name):
            return name
        if managed:
            return managed
        return name

    def get_match_names_bulk(self, test_guid: str,
                             sample_ids: list[str]) -> dict[str, str]:
        """Holt Anzeigenamen für mehrere Matches in einem POST-Request.

        Bestätigter Endpunkt (Juni 2026):
          POST /discoveryui-matches/cluster/api/profileData/{test_guid}
          Body: {"matchSampleIds": [...]}
          Antwort: { "<sampleId>": {"matchName": "...", ...}, ... }

        Gibt {sampleId: name} zurück (nur gefundene Namen).
        """
        if not sample_ids:
            return {}
        if self._detail_blocked:
            return {}

        url = cfg.PROFILE_DATA_URL.format(test_guid=test_guid)
        from urllib.parse import unquote
        csrf = unquote(
            self._s.cookies.get("_dnamatches-matchlistui-x-csrf-token")
            or self._s.cookies.get("_csrf")
            or self._s.cookies.get("XSRF-TOKEN") or ""
        )

        payload = {"matchSampleIds": list(sample_ids)}
        hdrs = {
            "Accept"              : "application/json",
            "Content-Type"        : "application/json",
            "Origin"              : cfg.BASE_URL,
            "Referer"             : f"{cfg.BASE_URL}/discoveryui-matches/list/{test_guid}",
            "X-Requested-With"    : "XMLHttpRequest",
            "Sec-Fetch-Site"      : "same-origin",
            "Sec-Fetch-Mode"      : "cors",
            "Sec-Fetch-Dest"      : "empty",
            "X-CSRF-Token"        : csrf,
            "ancestry-context-ube": _build_ube_header(self._s),
        }

        for attempt in range(MAX_RETRIES):
            try:
                r = self._s.post(url, json=payload, headers=hdrs,
                                 timeout=cfg.REQUEST_TIMEOUT,
                                 allow_redirects=True)
            except Exception as e:
                delay = _jitter(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
                log.warning("profileData Versuch %d/%d Fehler: %s → %.0fs",
                            attempt+1, MAX_RETRIES, e, delay)
                time.sleep(delay)
                continue

            if r.status_code in (301, 302, 303, 307, 308):
                # Cloudflare gibt bei Fingerprint-Mismatch einen neuen __cf_bm Cookie.
                # Session speichert ihn automatisch – nächster Versuch sollte klappen.
                new_bm = r.cookies.get("__cf_bm") or r.headers.get("set-cookie", "")
                log.debug("profileData %s → neuer __cf_bm: %s",
                          r.status_code, bool(new_bm))
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2)
                    continue
                log.error("profileData: nach %d Versuchen weiter 303. "
                          "Bitte ancestry.json neu exportieren.", MAX_RETRIES)
                self._detail_blocked = True
                return {}

            if r.status_code == 429:
                delay = int(r.headers.get("Retry-After", RETRY_DELAYS[attempt]))
                log.warning("profileData 429 → warte %ds", delay)
                time.sleep(delay)
                continue

            if r.status_code in (401, 403):
                log.error("profileData HTTP %s – Cookies abgelaufen.", r.status_code)
                self._detail_blocked = True
                return {}

            if r.status_code in RETRY_STATUSES:
                time.sleep(_jitter(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)]))
                continue

            if r.status_code != 200:
                log.warning("profileData HTTP %s", r.status_code)
                return {}

            try:
                data = r.json()
            except Exception as e:
                log.error("profileData JSON-Fehler: %s | %s", e, r.text[:200])
                return {}

            names = {}
            for sid, info in (data or {}).items():
                name = self._pick_name(info)
                if name:
                    names[sid] = name
            log.debug("profileData: %d/%d Namen erhalten", len(names), len(sample_ids))
            return names

        log.error("profileData: alle %d Versuche fehlgeschlagen.", MAX_RETRIES)
        return {}

    def detail_names_blocked(self) -> bool:
        return self._detail_blocked

    def stop_playwright(self):
        """No-op – Playwright wird nicht mehr genutzt."""
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
