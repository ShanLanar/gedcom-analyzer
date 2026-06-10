"""
Ancestry-Authentifizierung via Cookie-Import.
Nutzt curl_cffi um Cloudflare-Bot-Detection zu umgehen
(Chrome-TLS-Fingerprint statt Python-requests).
"""

import json
import re
import logging
from typing import Optional

try:
    from curl_cffi import requests as cfr
    CURL_AVAILABLE = True
except ImportError:
    import requests as cfr
    CURL_AVAILABLE = False

import ancestry.endpoints as cfg

log = logging.getLogger(__name__)

CHROME_VERSIONS = ["chrome136", "chrome131", "chrome127", "chrome124"]

def _best_chrome_version() -> str:
    """Gibt die neueste tatsächlich funktionierende curl_cffi Chrome-Version zurück."""
    if not CURL_AVAILABLE:
        return "chrome124"
    for ver in CHROME_VERSIONS:
        try:
            s = cfr.Session(impersonate=ver)
            # Session-Erstellung allein reicht nicht – echten Request testen
            s.head("https://www.ancestry.com/", timeout=8)
            return ver
        except Exception as e:
            if "not supported" in str(e).lower() or "impersonat" in str(e).lower():
                log.debug("curl_cffi: %s nicht unterstützt, versuche nächste Version", ver)
                continue
            # Netzwerkfehler o.ä. – Version selbst ist ok
            return ver
    return "chrome124"

CHROME_VERSION = _best_chrome_version()
SESSION_COOKIES = [
    "SecureATT", "AncestrySessionId", "ASP.NET_SessionId",
    "authUserId", "UserId", "uid", "global_login_at",
]
MIN_COOKIES_WARNING = 10

DNA_PAGE_URLS = [
    f"{cfg.BASE_URL}/dna/insights",
    f"{cfg.BASE_URL}/dna/home",
    f"{cfg.BASE_URL}/dna/tests",
    f"{cfg.BASE_URL}/dna/",
]


def _make_session():
    """Erstellt eine curl_cffi-Session die Chrome imitiert."""
    if CURL_AVAILABLE:
        s = cfr.Session(impersonate=CHROME_VERSION)
        log.debug("curl_cffi-Session erstellt (impersonate=%s)", CHROME_VERSION)
    else:
        log.warning("curl_cffi nicht installiert – Cloudflare-Bypass nicht aktiv!")
        s = cfr.Session()
    s.headers.update(cfg.DEFAULT_HEADERS)
    return s


class AncestryAuth:

    def __init__(self):
        self.session    = _make_session()
        self.authenticated = False
        self._uid: Optional[str] = None

    @property
    def uid(self) -> Optional[str]:
        return self._uid

    # ── Login ─────────────────────────────────────────────────────────────────

    def login_password(self, username: str, password: str) -> bool:
        log.info("Starte automatischen Login für '%s' …", username)
        try:
            r = self.session.get(cfg.SIGNIN_PAGE, timeout=cfg.REQUEST_TIMEOUT)
            csrf = self._extract_csrf(r.text)
            headers = {
                "Content-Type"    : "application/x-www-form-urlencoded",
                "X-CSRF-Token"    : csrf,
                "Referer"         : cfg.SIGNIN_PAGE,
                "X-Requested-With": "XMLHttpRequest",
            }
            payload = {"username": username, "password": password,
                       "remember": "true", "_csrf": csrf}
            r2 = self.session.post(cfg.AUTH_ENDPOINT, data=payload, headers=headers,
                                   timeout=cfg.REQUEST_TIMEOUT)
            log.debug("Auth-Response: %s %s", r2.status_code, r2.url)
            if r2.status_code in (200, 302):
                return self._verify_session()
            log.error("Auth-Endpunkt antwortete mit %s", r2.status_code)
            return False
        except Exception as e:
            log.error("Netzwerkfehler beim Login: %s", e)
            return False

    def login_cookies(self, cookie_file: str) -> bool:
        log.info("Lade Cookies aus '%s' …", cookie_file)
        try:
            with open(cookie_file, encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            log.error("Cookie-Datei '%s' nicht gefunden.", cookie_file)
            return False
        except json.JSONDecodeError as e:
            log.error("Fehler beim Parsen der Cookie-Datei: %s", e)
            return False

        cookies = raw if isinstance(raw, list) else raw.get("cookies", [])
        loaded = 0
        for c in cookies:
            try:
                name   = c["name"]
                value  = c["value"]
                domain = c.get("domain", ".ancestry.com")
                # Add dot prefix only for bare second-level domains (ancestry.com → .ancestry.com).
                # Subdomains like www.ancestry.com must stay unchanged — adding a dot would
                # create .www.ancestry.com which conflicts with fresh warmup cookies.
                if domain and not domain.startswith(".") and domain.count(".") == 1:
                    domain = "." + domain
                self.session.cookies.set(name, value, domain=domain,
                                         path=c.get("path", "/"))
                loaded += 1
            except KeyError:
                pass

        log.info("%d Cookie(s) geladen.", loaded)
        if loaded == 0:
            log.error("Keine Cookies geladen – Datei leer oder falsches Format?")
            return False
        if loaded < MIN_COOKIES_WARNING:
            log.warning(
                "Nur %d Cookie(s) – wahrscheinlich zu wenig.\n"
                "  → Auf ancestry.com einloggen → Cookie-Editor → 'Export All'",
                loaded
            )

        return self._verify_session()

    def get_session(self):
        return self.session

    # ── Session-Verifikation ─────────────────────────────────────────────────

    def _verify_session(self) -> bool:
        log.debug("Starte Session-Verifikation …")

        # 1. API-Endpunkte
        for url in [
            f"{cfg.BASE_URL}/api/uhura/v2/userprivate",
            f"{cfg.BASE_URL}/dna/api/uhura/v2/users/self",
            f"{cfg.BASE_URL}/api/uhura/v2/people/self",
            f"{cfg.BASE_URL}/api/v2/user",
        ]:
            uid = self._try_api_endpoint(url)
            if uid:
                self._uid = uid
                self.authenticated = True
                log.info("Session verifiziert via API. UID=%s…", uid[:16])
                return True

        # 2. DNA-Seiten
        uid = self._extract_uid_from_pages()
        if uid:
            self._uid = uid
            self.authenticated = True
            log.info("Session verifiziert via Seiteninhalt. UID=%s…", uid[:16])
            return True

        # 3. UID aus Cookie
        uid = self._uid_from_cookies()
        if uid:
            self._uid = uid
            self.authenticated = True
            log.info("UID aus Cookie: %s…", uid[:16])
            return True

        # 4. Genug Cookies vorhanden → optimistisch weitermachen
        present = [c for c in SESSION_COOKIES if self.session.cookies.get(c)]
        n = len(self.session.cookies)
        if present and n >= MIN_COOKIES_WARNING:
            log.warning(
                "UID nicht ermittelbar, aber %d Cookies vorhanden (%s u.a.).\n"
                "  → Kit-GUID manuell im Login-Tab eingeben.\n"
                "  → Download funktioniert trotzdem – Cloudflare-Bypass aktiv.",
                n, present[0]
            )
            self.authenticated = True
            return True

        log.error(
            "Session ungültig (%d Cookies).\n"
            "  → Auf ancestry.com einloggen → F12 → Application → Cookies → Alle kopieren\n"
            "  → Cookie-Editor: 'Export All' (nicht 'Export Selected')",
            n
        )
        return False

    def _try_api_endpoint(self, url: str) -> Optional[str]:
        try:
            r = self.session.get(url, timeout=cfg.REQUEST_TIMEOUT)
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    return None
                for key in ("uid", "guid", "id", "userId", "personId"):
                    val = data.get(key)
                    if val and isinstance(val, str) and len(val) > 4:
                        return val
                for sub in data.values():
                    if isinstance(sub, dict):
                        for key in ("uid", "guid", "id"):
                            val = sub.get(key)
                            if val and isinstance(val, str) and len(val) > 4:
                                return val
        except Exception as e:
            log.debug("API-Endpunkt %s: %s", url, e)
        return None

    def _extract_uid_from_pages(self) -> Optional[str]:
        patterns = [
            r'"testGuid"\s*:\s*"([0-9A-Fa-f\-]{32,})"',
            r'"guid"\s*:\s*"([0-9A-Fa-f\-]{32,})"',
            r'"uid"\s*:\s*"([0-9A-Za-z\-]{8,})"',
            r'/dna/tests/([0-9A-Fa-f\-]{32,})/',
        ]
        for url in DNA_PAGE_URLS:
            try:
                r = self.session.get(url, timeout=cfg.REQUEST_TIMEOUT)
                if "signin" in r.url or "login" in r.url:
                    continue
                if r.status_code == 200:
                    for pat in patterns:
                        m = re.search(pat, r.text)
                        if m:
                            return m.group(1)
            except Exception as e:
                log.debug("Seite %s: %s", url, e)
        return None

    def _uid_from_cookies(self) -> Optional[str]:
        for name in ("authUserId", "UserId", "uid", "GUID", "personId"):
            val = self.session.cookies.get(name)
            if val and len(val) > 4:
                return val
        return None

    def _extract_csrf(self, html: str) -> str:
        for pat in [
            r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
            r'<input[^>]+name=["\']_csrf["\'][^>]+value=["\']([^"\']+)["\']',
            r'["\']csrfToken["\']\s*:\s*["\']([^"\']+)["\']',
        ]:
            m = re.search(pat, html, re.I)
            if m:
                return m.group(1)
        return self.session.cookies.get("_csrf", "")
