"""
Holt Match-Namen via Playwright: lädt einmalig die Match-Listenseite
(kein Akamai-Block), dann fetch() an matchesservice aus dem Browser heraus.

Der Browser hat valide Cloudflare-Cookies (cf_clearance, __cf_bm) nach dem
Laden der Listenseite. fetch() aus diesem Kontext passiert Cloudflare.
"""

import asyncio
import logging
import threading
from typing import Optional

import config as cfg

log = logging.getLogger(__name__)

NAV_TIMEOUT   = 30_000
FETCH_TIMEOUT = 15_000


class PlaywrightNameFetcher:

    def __init__(self, session):
        self._session   = session
        self._loop      : Optional[asyncio.AbstractEventLoop] = None
        self._thread    : Optional[threading.Thread]          = None
        self._browser   = None
        self._context   = None
        self._page      = None
        self._available : Optional[bool]                      = None
        self._started   = threading.Event()

    # ── Lebenszyklus ─────────────────────────────────────────────────────────

    def start(self, test_guid: str) -> bool:
        try:
            import playwright  # noqa
        except ImportError:
            log.warning("Playwright nicht installiert.\n"
                        "  pip install playwright\n"
                        "  python -m playwright install chromium")
            self._available = False
            return False

        self._test_guid = test_guid
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="pw-names")
        self._thread.start()
        self._started.wait(timeout=60)
        return self._available is True

    def stop(self):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
        if self._thread:
            self._thread.join(timeout=10)

    def get_name(self, test_guid: str, sample_id: str) -> str:
        if not self._available:
            return ""
        fut = asyncio.run_coroutine_threadsafe(
            self._fetch_name(test_guid, sample_id), self._loop)
        try:
            return fut.result(timeout=30)
        except Exception as e:
            log.debug("get_name %s: %s", sample_id[:8], e)
            return ""

    # ── Event-Loop ───────────────────────────────────────────────────────────

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_start())
        if self._available:
            self._loop.run_forever()

    async def _async_start(self):
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()

            try:
                self._browser = await pw.chromium.launch(
                    channel="chrome", headless=True)
                log.debug("Playwright: System-Chrome gestartet.")
            except Exception:
                self._browser = await pw.chromium.launch(headless=True)
                log.debug("Playwright: Chromium gestartet.")

            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                viewport={"width": 1280, "height": 800},
            )
            await self._inject_cookies()

            # Listenseite laden → Cloudflare setzt cf_clearance + __cf_bm
            list_url = f"{cfg.BASE_URL}/dna/matches/{self._test_guid}/list"
            self._page = await self._context.new_page()
            log.debug("Playwright: lade Listenseite %s", list_url)
            try:
                await self._page.goto(
                    list_url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
                log.debug("Playwright: Listenseite geladen.")
            except Exception as e:
                log.warning("Playwright: Listenseite-Fehler: %s", e)

            self._available = True
            log.info("Playwright bereit – fetch() an matchesservice.")
        except Exception as e:
            log.error("Playwright Start fehlgeschlagen: %s", e)
            self._available = False
        finally:
            self._started.set()

    async def _async_stop(self):
        try:
            if self._page:    await self._page.close()
            if self._context: await self._context.close()
            if self._browser: await self._browser.close()
        except Exception:
            pass
        self._loop.stop()

    # ── Name via fetch() aus Browser-Kontext ─────────────────────────────────

    async def _fetch_name(self, test_guid: str, sample_id: str) -> str:
        if not self._page:
            return ""
        candidates = [
            t.format(test_guid=test_guid, sample_id=sample_id)
            for t in cfg.MATCH_DETAIL_CANDIDATES
            if "matchesservice" in t   # nur matchesservice, rest ist 404
        ]
        for url in candidates:
            try:
                result = await self._page.evaluate(
                    """async (url) => {
                        try {
                            const r = await fetch(url, {
                                credentials: 'include',
                                headers: {
                                    'Accept': 'application/json',
                                    'sec-fetch-mode': 'cors',
                                    'sec-fetch-site': 'same-origin',
                                }
                            });
                            if (!r.ok) return {status: r.status, data: null};
                            return {status: r.status, data: await r.json()};
                        } catch(e) {
                            return {status: 0, error: String(e)};
                        }
                    }""",
                    url,
                )
                status = result.get("status", 0)
                log.debug("PW fetch %s → HTTP %s", url.split("/api/", 1)[-1][:40], status)

                if status == 200:
                    data = result.get("data") or {}
                    name = self._extract_name(data)
                    if name:
                        return name
                elif status in (401, 403):
                    log.warning("Playwright: %s → HTTP %s (Session abgelaufen?)",
                                sample_id[:8], status)
                    return ""
            except Exception as e:
                log.debug("PW fetch %s: %s", sample_id[:8], e)

        return ""

    @staticmethod
    def _extract_name(data: dict) -> str:
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
                or nested(data, "matchTestDisplayName")
                or nested(data, "userDisplayName")
                or nested(data, "match", "displayName")
                or "")

    # ── Cookie-Injection ─────────────────────────────────────────────────────

    async def _inject_cookies(self):
        pw_cookies = []
        try:
            jar = self._session.cookies
            try:
                items = list(jar)
                if items and hasattr(items[0], "name"):
                    for c in items:
                        domain = getattr(c, "domain", "") or ".ancestry.com"
                        if domain and not domain.startswith("."):
                            domain = "." + domain
                        pw_cookies.append({
                            "name"    : c.name,
                            "value"   : c.value,
                            "domain"  : domain,
                            "path"    : getattr(c, "path", "/") or "/",
                            "secure"  : True,
                            "httpOnly": False,
                            "sameSite": "None",
                        })
                else:
                    raise ValueError
            except Exception:
                for name, value in jar.items():
                    pw_cookies.append({
                        "name": name, "value": str(value),
                        "domain": ".ancestry.com", "path": "/",
                        "secure": True, "httpOnly": False, "sameSite": "None",
                    })
        except Exception as e:
            log.debug("Cookie-Übertragung: %s", e)

        if pw_cookies:
            await self._context.add_cookies(pw_cookies)
            log.debug("%d Cookies an Playwright übergeben.", len(pw_cookies))
        else:
            log.warning("Playwright: keine Cookies.")
