"""
Holt Match-Namen via Playwright (headless Chromium), parallel.

Verwendet einen Thread-Pool mit mehreren Browser-Tabs gleichzeitig.
Standardmäßig 5 parallele Tabs → ~3h statt ~14h für 10.000 Matches.
"""

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

log = logging.getLogger(__name__)

PARALLEL_TABS = 5     # gleichzeitige Browser-Tabs
TIMEOUT       = 15_000
NAV_TIMEOUT   = 20_000


class PlaywrightNameFetcher:

    def __init__(self, session, parallel: int = PARALLEL_TABS):
        self._session   = session
        self._parallel  = parallel
        self._pw        = None
        self._browser   = None
        self._context   = None
        self._available: Optional[bool] = None
        self._lock      = threading.Lock()   # für Context-Zugriff

    # ── Lebenszyklus ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning("Playwright nicht installiert.\n"
                        "  pip install playwright\n"
                        "  playwright install chromium")
            self._available = False
            return False
        try:
            self._pw      = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._context = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="de-DE",
                viewport={"width": 1280, "height": 800},
            )
            self._inject_cookies()
            self._available = True
            log.info("Playwright bereit (%d parallele Tabs).", self._parallel)
            return True
        except Exception as e:
            log.error("Playwright konnte nicht gestartet werden: %s", e)
            self._available = False
            return False

    def stop(self):
        try:
            if self._context: self._context.close()
            if self._browser: self._browser.close()
            if self._pw:      self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._context = None

    # ── Einzelner Name ────────────────────────────────────────────────────────

    def get_name(self, test_guid: str, sample_id: str) -> str:
        """Öffnet eine Compare-Seite und liest den Namen – thread-safe."""
        if not self.is_available():
            return ""
        return self._fetch_one(test_guid, sample_id)

    # ── Batch: Liste von (test_guid, sample_id) → dict {sample_id: name} ─────

    def get_names_batch(
        self,
        pairs: list[tuple[str, str]],
        on_progress=None,
        stop_event=None,
    ) -> dict[str, str]:
        """
        Lädt Namen für viele Matches parallel.

        :param pairs:        Liste von (test_guid, sample_id)
        :param on_progress:  Callback(done, total, name) für Fortschrittsanzeige
        :param stop_event:   threading.Event – wenn gesetzt, Abbruch
        :return:             {sample_id: name}
        """
        results: dict[str, str] = {}
        total   = len(pairs)
        done    = 0

        with ThreadPoolExecutor(max_workers=self._parallel) as pool:
            futures = {
                pool.submit(self._fetch_one, tg, sid): sid
                for tg, sid in pairs
            }
            for fut in as_completed(futures):
                if stop_event and stop_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                sid  = futures[fut]
                name = ""
                try:
                    name = fut.result()
                except Exception as e:
                    log.debug("Playwright-Fehler %s: %s", sid[:8], e)
                results[sid] = name
                done += 1
                if on_progress:
                    on_progress(done, total, name or sid[:8])

        return results

    def is_available(self) -> bool:
        return self._available is True

    # ── Intern ────────────────────────────────────────────────────────────────

    def _fetch_one(self, test_guid: str, sample_id: str) -> str:
        url  = (f"https://www.ancestry.com/dna/matches/"
                f"{test_guid}/compare/{sample_id}")
        page = None
        try:
            with self._lock:
                page = self._context.new_page()
            page.set_default_timeout(TIMEOUT)
            page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")

            # Warten bis H1 mit "You and" oder "Du und" gerendert ist
            try:
                page.wait_for_function(
                    "() => document.querySelector('h1') && "
                    "(/You and|Du und/.test(document.querySelector('h1').innerText))",
                    timeout=TIMEOUT,
                )
            except Exception:
                pass  # Timeout – trotzdem versuchen was da ist

            for selector in ["h1", "[class*='matchName']",
                             "[class*='compareHeader']", "[data-testid*='name']"]:
                try:
                    el = page.query_selector(selector)
                    if el:
                        name = self._extract_name(el.inner_text() or "")
                        if name:
                            return name
                except Exception:
                    continue

            # Fallback: gesamten Body-Text durchsuchen
            try:
                name = self._extract_name(page.inner_text("body"))
                if name:
                    return name
            except Exception:
                pass

            # Debug: was steht wirklich auf der Seite?
            try:
                h1 = page.query_selector("h1")
                h1_text = h1.inner_text() if h1 else "(kein H1)"
                body_snippet = (page.inner_text("body") or "")[:300].replace("\n", " ")
                log.debug("Playwright %s – H1: %r | Body: %r",
                          sample_id[:8], h1_text, body_snippet)
            except Exception:
                pass
            log.debug("Kein Name auf Compare-Seite: %s", sample_id[:8])
            return ""
        except Exception as e:
            log.debug("Playwright %s: %s", sample_id[:8], e)
            return ""
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def _inject_cookies(self):
        pw_cookies = []
        try:
            jar = self._session.cookies
            # curl_cffi: jar ist ein requests.cookies.RequestsCookieJar
            # Iteration liefert Cookie-Objekte mit .name/.value/.domain/.path
            try:
                items = list(jar)   # liefert Cookie-Objekte
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
                    raise ValueError("keine Cookie-Objekte")
            except Exception:
                # Fallback: als dict iterieren
                for name, value in jar.items():
                    pw_cookies.append({
                        "name"    : name,
                        "value"   : str(value),
                        "domain"  : ".ancestry.com",
                        "path"    : "/",
                        "secure"  : True,
                        "httpOnly": False,
                        "sameSite": "None",
                    })
        except Exception as e:
            log.debug("Cookie-Übertragung fehlgeschlagen: %s", e)
        if pw_cookies:
            self._context.add_cookies(pw_cookies)
            log.debug("%d Cookies an Playwright übergeben.", len(pw_cookies))
        else:
            log.warning("Playwright: keine Cookies übertragen – "
                        "Seite landet möglicherweise auf Login.")

    @staticmethod
    def _extract_name(text: str) -> str:
        if not text:
            return ""
        m = re.search(
            r'(?:You and|Du und)\s+([A-ZÄÖÜ][^\n\r]{2,60}?)(?:\n|\r|$)',
            text,
        )
        if m:
            return m.group(1).strip()
        return ""
