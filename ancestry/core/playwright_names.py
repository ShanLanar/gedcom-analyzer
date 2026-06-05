"""
Holt Match-Namen via Playwright (headless Chromium).

Der Browser übernimmt die Cookies aus der bestehenden curl_cffi-Session,
navigiert zur Compare-Seite und liest den gerenderten Namen aus dem H1.

Verwendung:
    fetcher = PlaywrightNameFetcher(session)
    fetcher.start()
    name = fetcher.get_name(test_guid, sample_id)
    fetcher.stop()
"""

import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


class PlaywrightNameFetcher:
    """Startet einen einzigen Playwright-Browser und hält ihn offen."""

    # Warten bis dieser Text im H1 erscheint (max. TIMEOUT ms)
    TIMEOUT  = 15_000   # ms
    NAV_TIMEOUT = 20_000

    def __init__(self, session):
        """
        :param session: curl_cffi-Session mit gesetzten Ancestry-Cookies.
        """
        self._session  = session
        self._pw       = None
        self._browser  = None
        self._context  = None
        self._available: Optional[bool] = None   # None = noch nicht geprüft

    # ── Lebenszyklus ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Startet Playwright + Chromium. Gibt False zurück wenn nicht installiert."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.warning("Playwright nicht installiert. "
                        "Bitte: pip install playwright && playwright install chromium")
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
            log.info("Playwright-Browser gestartet.")
            return True
        except Exception as e:
            log.error("Playwright konnte nicht gestartet werden: %s", e)
            self._available = False
            return False

    def stop(self):
        """Schließt Browser und Playwright."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._context = None

    # ── Öffentliche API ───────────────────────────────────────────────────────

    def is_available(self) -> bool:
        return self._available is True

    def get_name(self, test_guid: str, sample_id: str) -> str:
        """
        Öffnet /dna/matches/{test_guid}/compare/{sample_id} und liest den Namen.
        Gibt "" zurück wenn kein Name gefunden.
        """
        if not self.is_available():
            return ""

        url = (f"https://www.ancestry.com/dna/matches/"
               f"{test_guid}/compare/{sample_id}")
        page = None
        try:
            page = self._context.new_page()
            page.set_default_timeout(self.TIMEOUT)

            # Zur Compare-Seite navigieren
            page.goto(url, timeout=self.NAV_TIMEOUT, wait_until="domcontentloaded")

            # Warten bis H1 mit "You and" oder "Du und" erscheint
            try:
                page.wait_for_selector(
                    "h1, [class*='matchName'], [class*='compareHeader']",
                    timeout=self.TIMEOUT,
                )
            except Exception:
                pass   # Timeout – trotzdem versuchen

            # H1-Text auslesen
            for selector in [
                "h1",
                "[class*='matchName']",
                "[class*='compareHeader']",
                "[data-testid*='name']",
            ]:
                try:
                    el = page.query_selector(selector)
                    if el:
                        text = (el.inner_text() or "").strip()
                        name = self._extract_name(text)
                        if name:
                            return name
                except Exception:
                    continue

            # Fallback: gesamten Seitentext nach "You and NAME" durchsuchen
            try:
                body = page.inner_text("body")
                name = self._extract_name(body)
                if name:
                    return name
            except Exception:
                pass

            log.debug("Playwright: kein Name auf %s", url)
            return ""

        except Exception as e:
            log.debug("Playwright-Fehler für %s: %s", sample_id[:8], e)
            return ""
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    # ── Intern ────────────────────────────────────────────────────────────────

    def _inject_cookies(self):
        """Überträgt Cookies aus der curl_cffi-Session in den Playwright-Context."""
        pw_cookies = []
        try:
            for c in self._session.cookies:
                domain = getattr(c, "domain", "") or ".ancestry.com"
                if not domain.startswith(".") and domain:
                    domain = "." + domain
                pw_cookies.append({
                    "name"    : c.name,
                    "value"   : c.value,
                    "domain"  : domain,
                    "path"    : getattr(c, "path", "/") or "/",
                    "secure"  : getattr(c, "secure", True),
                    "httpOnly": False,
                    "sameSite": "None",
                })
        except Exception as e:
            log.debug("Cookie-Übertragung fehlerhaft: %s", e)

        if pw_cookies:
            self._context.add_cookies(pw_cookies)
            log.debug("Playwright: %d Cookies übertragen.", len(pw_cookies))

    @staticmethod
    def _extract_name(text: str) -> str:
        """Extrahiert NAME aus 'You and NAME' oder 'Du und NAME'."""
        if not text:
            return ""
        # "You and Gerda Kovermann" oder "Du und Gerda Kovermann"
        m = re.search(
            r'(?:You and|Du und)\s+([A-ZÄÖÜ][^\n\r]{2,60}?)(?:\n|\r|$)',
            text,
        )
        if m:
            return m.group(1).strip()
        return ""
