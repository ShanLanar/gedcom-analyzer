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
        self._csrf_mode = None         # gecachte CSRF-Form sobald eine 200 lieferte

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

    # ── Signierte POSTs (profileData / commonAncestors / treeData) ────────────

    def _csrf_value(self, mode: str) -> str:
        """Liefert das CSRF-Token in der gewünschten Form ('raw'/'decoded'/'prefix')."""
        from urllib.parse import unquote
        raw = (self._s.cookies.get("_dnamatches-matchlistui-x-csrf-token")
               or self._s.cookies.get("_csrf")
               or self._s.cookies.get("XSRF-TOKEN") or "")
        if mode == "raw":
            return raw
        if mode == "decoded":
            return unquote(raw)
        if mode == "prefix":
            # nur der Teil vor dem Trenner (Token ohne Signatur)
            return unquote(raw).split("|", 1)[0]
        return ""  # 'none'

    def _post_once(self, url: str, payload: dict, test_guid: str, mode: str):
        """Ein POST-Versuch mit der angegebenen CSRF-Form. Gibt Response/None."""
        hdrs = {
            "Accept"              : "application/json",
            "Content-Type"        : "application/json",
            "Origin"              : cfg.BASE_URL,
            "Referer"             : f"{cfg.BASE_URL}/discoveryui-matches/list/{test_guid}",
            "X-Requested-With"    : "XMLHttpRequest",
            "Sec-Fetch-Site"      : "same-origin",
            "Sec-Fetch-Mode"      : "cors",
            "Sec-Fetch-Dest"      : "empty",
            "ancestry-context-ube": _build_ube_header(self._s),
        }
        if mode != "none":
            tok = self._csrf_value(mode)
            if tok:
                hdrs["X-CSRF-Token"] = tok

        for attempt in range(MAX_RETRIES):
            try:
                r = self._s.post(url, json=payload, headers=hdrs,
                                 timeout=cfg.REQUEST_TIMEOUT,
                                 allow_redirects=False)
            except Exception as e:
                delay = _jitter(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
                log.warning("POST-Fehler (%s) %d/%d: %s → %.0fs",
                            mode, attempt+1, MAX_RETRIES, e, delay)
                time.sleep(delay)
                continue
            if r.status_code == 429:
                delay = int(r.headers.get("Retry-After", RETRY_DELAYS[attempt]))
                log.warning("429 → warte %ds", delay)
                time.sleep(delay)
                continue
            if r.status_code in RETRY_STATUSES:
                time.sleep(_jitter(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)]))
                continue
            return r
        return None

    def _signed_post(self, url: str, payload: dict, test_guid: str, label: str):
        """Signierter POST mit automatischer CSRF-Form-Erkennung + Caching.

        Beim ersten Aufruf werden alle CSRF-Formen durchprobiert; die erste mit
        HTTP 200 wird für alle weiteren Aufrufe gecacht (self._csrf_mode).
        Gibt das geparste JSON (dict/list) zurück – oder None bei Fehler.
        """
        if self._detail_blocked:
            return None

        # Form bereits bekannt → direkt nutzen.
        if self._csrf_mode is not None:
            r = self._post_once(url, payload, test_guid, self._csrf_mode)
            return self._parse_json(r, label)

        # Erststart: Formen der Reihe nach testen.
        for mode in ("raw", "decoded", "prefix", "none"):
            tok = self._csrf_value(mode)
            if mode in ("raw", "decoded", "prefix") and not tok:
                continue
            r = self._post_once(url, payload, test_guid, mode)
            log.info("%s CSRF-Form '%s': HTTP %s",
                     label, mode, getattr(r, "status_code", "—"))
            if r is not None and r.status_code == 200:
                self._csrf_mode = mode
                log.info("%s OK mit CSRF-Form '%s'", label, mode)
                return self._parse_json(r, label)
            if r is not None and r.status_code in (401, 403):
                log.error("%s HTTP %s – Session abgelaufen.", label, r.status_code)
                self._detail_blocked = True
                return None

        log.error("%s: keine CSRF-Form erfolgreich (alle 303/Redirect). "
                  "→ Browser-Export nutzen (siehe ancestry/tools/NAMEN_LADEN.md).",
                  label)
        self._detail_blocked = True
        return None

    @staticmethod
    def _parse_json(r, label: str):
        if r is None or r.status_code != 200:
            return None
        if "html" in r.headers.get("Content-Type", ""):
            log.warning("%s: HTML statt JSON (Login-Redirect?)", label)
            return None
        try:
            return r.json()
        except Exception as e:
            log.error("%s JSON-Fehler: %s | %s", label, e, r.text[:200])
            return None

    # ── Namen / Profil-Details ─────────────────────────────────────────────────

    def get_profile_details_bulk(self, test_guid: str,
                                 sample_ids: list[str]) -> dict[str, dict]:
        """profileData → {sampleId: {"name":.., "ucdmid":.., "gender":..}}."""
        if not sample_ids or self._detail_blocked:
            return {}
        url  = cfg.PROFILE_DATA_URL.format(test_guid=test_guid)
        data = self._signed_post(url, {"matchSampleIds": list(sample_ids)},
                                 test_guid, "profileData")
        out = {}
        for sid, info in (data or {}).items():
            if not isinstance(info, dict):
                continue
            out[sid] = {
                "name"  : self._pick_name(info),
                "ucdmid": info.get("matchUcdmid") or "",
                "gender": info.get("displayGender") or "",
            }
        return out

    def get_match_names_bulk(self, test_guid: str,
                             sample_ids: list[str]) -> dict[str, str]:
        """Rückwärtskompatibel: nur {sampleId: name}."""
        details = self.get_profile_details_bulk(test_guid, sample_ids)
        return {sid: d["name"] for sid, d in details.items() if d.get("name")}

    # ── Gemeinsamer Vorfahre ────────────────────────────────────────────────────

    def get_common_ancestors(self, test_guid: str,
                             sample_ids: list[str]) -> set:
        """commonAncestors → Set der sampleIds, die einen gemeinsamen Vorfahren haben."""
        if not sample_ids or self._detail_blocked:
            return set()
        url  = cfg.COMMON_ANCESTORS_URL.format(test_guid=test_guid)
        data = self._signed_post(url, {"sampleIds": list(sample_ids)},
                                 test_guid, "commonAncestors")
        return set(data) if isinstance(data, list) else set()

    # ── Stammbaum-Daten ──────────────────────────────────────────────────────────

    @staticmethod
    def _tree_status(info: dict) -> dict:
        """Wandelt treeData-Flags in {tree_status, tree_size, has_tree}."""
        size = int(info.get("treeSize") or 0)
        if info.get("hasNoTrees"):
            status, has = "Kein Baum", False
        elif info.get("isTreeUnavailable"):
            status, has = "Nicht verfügbar", False
        elif info.get("isUnlinkedTree"):
            status, has = "Unverknüpft", False
        elif info.get("isPrivateTree"):
            status, has = "Privat", True
        elif info.get("isPublicTree"):
            status, has = "Öffentlich", True
        else:
            status, has = "", False
        return {"tree_status": status, "tree_size": size, "has_tree": has}

    def get_tree_data_bulk(self, test_guid: str,
                           sid_to_ucdmid: dict) -> dict[str, dict]:
        """treeData → {sampleId: {tree_status, tree_size, has_tree}}.

        Braucht pro Match die userId (== matchUcdmid aus profileData).
        """
        match_list = [{"sampleId": sid, "matchProfile": {"userId": uc}}
                      for sid, uc in sid_to_ucdmid.items() if uc]
        if not match_list or self._detail_blocked:
            return {}
        url  = cfg.TREE_DATA_URL.format(test_guid=test_guid)
        data = self._signed_post(url, {"matchList": match_list},
                                 test_guid, "treeData")
        out = {}
        for sid, info in (data or {}).items():
            if isinstance(info, dict):
                out[sid] = self._tree_status(info)
        return out

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
                log.info("matchList-FELDER: %s", sorted(sample.keys()))
                log.info("matchList-BEISPIEL: %s",
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
