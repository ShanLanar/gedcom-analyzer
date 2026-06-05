"""
Holt Match-Namen via Playwright (headless Chromium).

Nutzt async_playwright in einem dedizierten Thread mit eigenem Event-Loop,
damit Playwright nicht über mehrere Threads geteilt wird (nicht thread-safe).
Requests werden sequenziell mit kurzem Delay abgesetzt, um Akamai nicht zu
triggern. Bei Error 54 automatische Pause (AKAMAI_COOLDOWN Sekunden).
"""

import asyncio
import logging
import re
import threading
from typing import Optional

log = logging.getLogger(__name__)

PARALLEL_TABS    = 1       # Sequenziell – Akamai blockt bei parallelen Requests
TIMEOUT          = 15_000
NAV_TIMEOUT      = 20_000
REQUEST_DELAY    = 1.5     # Sekunden zwischen Requests
AKAMAI_COOLDOWN  = 45      # Sekunden Pause nach Error 54


class PlaywrightNameFetcher:

    def __init__(self, session, parallel: int = PARALLEL_TABS):
        self._session        = session
        self._parallel       = parallel
        self._loop           : Optional[asyncio.AbstractEventLoop] = None
        self._thread         : Optional[threading.Thread]          = None
        self._browser        = None
        self._context        = None
        self._stealth        = None
        self._available      : Optional[bool] = None
        self._started        = threading.Event()
        self._akamai_blocked = False   # globale Sperre nach Error 54

    # ── Lebenszyklus ──────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Startet einen dedizierten Event-Loop-Thread mit Playwright."""
        try:
            import playwright  # noqa – nur prüfen ob installiert
        except ImportError:
            log.warning("Playwright nicht installiert.\n"
                        "  pip install playwright\n"
                        "  python -m playwright install chromium")
            self._available = False
            return False

        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="playwright-loop")
        self._thread.start()
        self._started.wait(timeout=30)
        return self._available is True

    def stop(self):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_stop(), self._loop)
        if self._thread:
            self._thread.join(timeout=10)
        self._loop = self._thread = None

    def is_available(self) -> bool:
        return self._available is True

    # ── Einzelner Name ──────────────────────────────────────────────────────────────

    def get_name(self, test_guid: str, sample_id: str) -> str:
        if not self.is_available():
            return ""
        fut = asyncio.run_coroutine_threadsafe(
            self._fetch_one(test_guid, sample_id), self._loop)
        try:
            return fut.result(timeout=60)
        except Exception as e:
            log.debug("get_name Fehler %s: %s", sample_id[:8], e)
            return ""

    # ── Batch ────────────────────────────────────────────────────────────────────

    def get_names_batch(
        self,
        pairs: list[tuple[str, str]],
        on_progress=None,
        stop_event=None,
    ) -> dict[str, str]:
        if not self.is_available():
            return {}
        fut = asyncio.run_coroutine_threadsafe(
            self._batch(pairs, on_progress, stop_event), self._loop)
        try:
            return fut.result(timeout=len(pairs) * 60 + 120)
        except Exception as e:
            log.error("Batch-Fehler: %s", e)
            return {}

    # ── Interner Event-Loop-Thread ──────────────────────────────────────────────────

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
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="de-DE",
                viewport={"width": 1280, "height": 800},
            )
            await self._inject_cookies()

            try:
                from playwright_stealth import stealth_async
                self._stealth = stealth_async
                log.debug("playwright-stealth geladen.")
            except ImportError:
                self._stealth = None

            self._available = True
            log.info("Playwright bereit (sequenziell, %.1fs Delay).", REQUEST_DELAY)
        except Exception as e:
            log.error("Playwright Start fehlgeschlagen: %s", e)
            self._available = False
        finally:
            self._started.set()

    async def _async_stop(self):
        try:
            if self._context: await self._context.close()
            if self._browser: await self._browser.close()
        except Exception:
            pass
        self._loop.stop()

    # ── Fetch-Logik ───────────────────────────────────────────────────────────────

    async def _fetch_one(self, test_guid: str, sample_id: str) -> str:
        """Lädt den Namen für ein Match. Gibt \"\" zurück wenn kein Name gefunden."""
        if self._akamai_blocked:
            return ""

        url  = (f"https://www.ancestry.com/dna/matches/"
                f"{test_guid}/compare/{sample_id}")
        page = None
        try:
            page = await self._context.new_page()
            if self._stealth:
                await self._stealth(page)
            page.set_default_timeout(TIMEOUT)
            await page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")

            # Warten bis etwas Verwertbares gerendert ist
            try:
                await page.wait_for_function(
                    "() => {"
                    "  const h = document.querySelector('h1');"
                    "  if (h && h.innerText.trim()) return true;"
                    "  const b = document.body && document.body.innerText || '';"
                    "  return b.includes('Match list') || b.includes(\"aren't matches\");"
                    "}",
                    timeout=TIMEOUT,
                )
            except Exception:
                pass

            # ── Akamai Error 54 erkennen ────────────────────────────────────────
            try:
                h1el = await page.query_selector("h1")
                h1tx = (await h1el.inner_text()) if h1el else ""
                if "Browser Validation" in h1tx or "Error 54" in h1tx:
                    log.warning("Akamai Error 54 – Pause %ds …", AKAMAI_COOLDOWN)
                    self._akamai_blocked = True
                    await asyncio.sleep(AKAMAI_COOLDOWN)
                    self._akamai_blocked = False
                    log.info("Akamai-Pause beendet, fahre fort.")
                    # Einmal neu versuchen
                    await page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
                    try:
                        await page.wait_for_function(
                            "() => { const h = document.querySelector('h1');"
                            " return h && h.innerText.trim().length > 0; }",
                            timeout=TIMEOUT,
                        )
                    except Exception:
                        pass
                    h1el = await page.query_selector("h1")
                    h1tx = (await h1el.inner_text()) if h1el else ""
                    if "Browser Validation" in h1tx or "Error 54" in h1tx:
                        return ""  # Auch nach Pause geblockt
            except Exception:
                pass

            # ── Normaler Compare-Pfad ─────────────────────────────────────────────────
            for selector in ["h1", "[class*='matchName']", "[class*='compareHeader']"]:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        name = self._extract_name(await el.inner_text() or "")
                        if name:
                            return name
                except Exception:
                    continue

            body = ""
            try:
                body = await page.inner_text("body")
                name = self._extract_name(body)
                if name:
                    return name
            except Exception:
                pass

            # ── Fallback: "aren't matches" → userId via JavaScript extrahieren ─
            if "aren't matches" in body:
                profile_path = await self._extract_profile_path(page)
                if profile_path:
                    try:
                        profile_url = "https://www.ancestry.com" + profile_path
                        await page.goto(profile_url, timeout=NAV_TIMEOUT,
                                        wait_until="domcontentloaded")
                        try:
                            await page.wait_for_function(
                                "() => { const h = document.querySelector('h1');"
                                " return h && h.innerText.trim().length > 0; }",
                                timeout=TIMEOUT,
                            )
                        except Exception:
                            pass
                        h1el = await page.query_selector("h1")
                        if h1el:
                            raw = (await h1el.inner_text() or "").strip()
                            name = self._extract_name(raw) or raw
                            if name and len(name) > 1:
                                return name
                    except Exception as e:
                        log.debug("Profil-Fallback %s: %s", sample_id[:8], e)
                else:
                    log.debug("Playwright %s – aren't matches, kein Profil-Link gefunden",
                              sample_id[:8])

            return ""
        except Exception as e:
            log.debug("Playwright %s: %s", sample_id[:8], e)
            return ""
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _extract_profile_path(self, page) -> str:
        """
        Sucht den /profile/{userId}-Link auf der aktuellen Seite.
        Ancestry rendert ihn nicht als <a>-Tag im HTML, sondern speichert
        die userId im eingebetteten JSON oder im React-State.
        """
        try:
            result = await page.evaluate(r"""
                () => {
                    // 1. <a href="/profile/..."> – manchmal vorhanden
                    const a = document.querySelector('a[href*="/profile/"]');
                    if (a) {
                        const m = a.href.match(/\/profile\/([0-9a-f-]{36})/i);
                        if (m) return '/profile/' + m[1];
                    }

                    // 2. <script> – Ancestry-SPA-Daten
                    for (const s of document.querySelectorAll('script')) {
                        const t = s.textContent || '';
                        const m = t.match(/"(?:userId|subjectId|personId|profileId)"\s*:\s*"([0-9a-f-]{36})"/i);
                        if (m) return '/profile/' + m[1];
                    }

                    // 3. window globals
                    for (const key of ['__initialState__', '__state__', '__APP_STATE__',
                                       '__PRELOADED_STATE__', 'initialData']) {
                        try {
                            const s = JSON.stringify(window[key] || {});
                            const m = s.match(/"(?:userId|subjectId|personId|profileId)"\s*:\s*"([0-9a-f-]{36})"/i);
                            if (m) return '/profile/' + m[1];
                        } catch {}
                    }

                    // 4. data-Attribute
                    for (const el of document.querySelectorAll('[data-user-id],[data-subject-id],[data-profile-id]')) {
                        const uid = el.dataset.userId || el.dataset.subjectId || el.dataset.profileId;
                        if (uid && /^[0-9a-f-]{36}$/i.test(uid)) return '/profile/' + uid;
                    }

                    return null;
                }
            """)
            return result or ""
        except Exception as e:
            log.debug("_extract_profile_path: %s", e)
            return ""

    async def _batch(self, pairs, on_progress, stop_event) -> dict[str, str]:
        sem     = asyncio.Semaphore(self._parallel)
        results : dict[str, str] = {}
        done    = [0]
        total   = len(pairs)

        async def fetch_limited(tg, sid):
            if stop_event and stop_event.is_set():
                return sid, ""
            async with sem:
                if done[0] > 0:
                    await asyncio.sleep(REQUEST_DELAY)
                name = await self._fetch_one(tg, sid)
            results[sid] = name
            done[0] += 1
            if on_progress:
                on_progress(done[0], total, name or sid[:8])
            return sid, name

        await asyncio.gather(*[fetch_limited(tg, sid) for tg, sid in pairs])
        return results

    # ── Cookies ───────────────────────────────────────────────────────────────────

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
            log.warning("Playwright: keine Cookies – landet auf Login-Seite.")

    @staticmethod
    def _extract_name(text: str) -> str:
        if not text:
            return ""
        # "You and NAME" / "Du und NAME"
        m = re.search(
            r'(?:You and|Du und)\s+([A-Za-zÄÖÜäöüß0-9][^\n\r]{1,60}?)(?:\s*\n|\r|$)',
            text,
        )
        if m:
            name = m.group(1).strip()
            if not name.lower().startswith("this person"):
                return name

        # Breadcrumb "Match list\nNAME"
        m = re.search(r'Match list\s*\n\s*([^\n]{2,80})', text)
        if m:
            name = m.group(1).strip()
            if name and not name.lower().startswith(("match list", "dna match")):
                return name

        return ""
