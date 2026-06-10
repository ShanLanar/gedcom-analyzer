"""
Session-Hilfsfunktionen und HTTP-Mixin für den Ancestry-API-Client.
"""

import time
import random
import logging
import base64
import json
import uuid
from typing import Optional

try:
    from curl_cffi import requests as cfr
except ImportError:
    import requests as cfr

import ancestry.endpoints as cfg

log = logging.getLogger(__name__)

RETRY_STATUSES  = {429, 500, 502, 503, 504}
MAX_RETRIES     = 5
RETRY_DELAYS    = [30, 60, 90, 120, 180]

BURST_LIMIT     = 3
BURST_PAUSE     = 20.0
JWT_REFRESH_INTERVAL = 25 * 60  # Sekunden zwischen JWT-Erneuerungen


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
    # DNA-Match-UI braucht seinen eigenen CSRF-Token; _csrf als Fallback
    try:
        csrf = session.cookies.get("_dnamatches-matchlistui-x-csrf-token",
                                   domain="www.ancestry.com")
    except Exception:
        csrf = None
    if not csrf:
        csrf = (session.cookies.get("_csrf")
                or session.cookies.get("XSRF-TOKEN") or "")
    if csrf:
        headers["X-CSRF-Token"] = csrf

    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, headers=headers, timeout=cfg.REQUEST_TIMEOUT,
                            allow_redirects=False)

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


class _ApiSessionMixin:
    """JWT, CSRF und HTTP-Hilfsmethoden."""

    def _jwt_remaining(self) -> int:
        """Verbleibende Gültigkeit des SecureATT JWT in Sekunden (negativ = abgelaufen)."""
        import base64 as _b64
        import json as _j
        try:
            jwt = self._s.cookies.get("SecureATT", domain="www.ancestry.com") or ""
            if not jwt:
                jwt = self._s.cookies.get("SecureATT") or ""
            if not jwt:
                return 0
            parts = jwt.split(".")
            if len(parts) < 2:
                return 0
            pad = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = _j.loads(_b64.urlsafe_b64decode(pad))
            return int(payload.get("exp", 0)) - int(time.time())
        except Exception:
            return 0

    def _refresh_jwt(self, test_guid: str) -> None:
        """Besucht die DNA-Matches-Seite, damit Ancestry einen frischen SecureATT-Cookie setzt."""
        warmup = f"{cfg.BASE_URL}/discoveryui-matches/list/{test_guid}"
        try:
            r = self._s.get(warmup, timeout=cfg.REQUEST_TIMEOUT)
            remaining = self._jwt_remaining()
            if remaining > 0:
                log.info("JWT erneuert – noch %.0f min gültig", remaining / 60)
            else:
                log.warning("JWT-Erneuerung: SecureATT immer noch abgelaufen")
        except Exception as e:
            log.warning("JWT-Erneuerung fehlgeschlagen: %s", e)
        self._last_jwt_refresh = time.time()

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
