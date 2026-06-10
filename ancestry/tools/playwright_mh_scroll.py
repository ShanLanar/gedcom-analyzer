#!/usr/bin/env python3
"""
MyHeritage DNA-Matches via Playwright (echter Browser, unerkennbar von Mensch).

Startet deinen echten Chrome/Edge mit gespeichertem Profil (Cookies + Login
bereits vorhanden), navigiert zur DNA-Matches-Seite und scrollt langsam durch
die Liste – exakt wie ein menschlicher Nutzer.

INSTALLATION (einmalig):
  pip install playwright
  playwright install chromium   # oder: playwright install chrome

AUFRUF:
  python playwright_mh_scroll.py

AUSGABE:
  ancestry/data/mh_playwright_matches.json
"""
import asyncio
import json
import random
import time
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Bitte installieren: pip install playwright && playwright install chromium")
    raise

OUT_FILE   = Path(__file__).parent.parent / "data" / "mh_playwright_matches.json"
TOTAL      = 11145
KIT_ID_INT = "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2"
SITE_KIT   = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
URL        = f"https://www.myheritage.com/dna/matches/{SITE_KIT}"

# Playwright Chromium-Profil-Pfad (Standard-Orte)
import os
import sys
import platform
def default_profile():
    s = platform.system()
    if s == "Windows":
        return Path(os.environ.get("LOCALAPPDATA","")) / "Google/Chrome/User Data"
    elif s == "Darwin":
        return Path.home() / "Library/Application Support/Google/Chrome"
    else:
        return Path.home() / ".config/google-chrome"

# JavaScript: XHR-Spy in Seite injizieren
SPY_JS = """
(function() {
  if (window._mhSpyInstalled) return;
  window._mhSpyInstalled = true;
  window._mhMatches = new Map();

  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this._mhUrl = String(url || "");
    return _open.apply(this, [method, url, ...rest]);
  };

  XMLHttpRequest.prototype.send = function(body) {
    const xhr = this;
    if ((xhr._mhUrl||"").includes("web-family-graphql") ||
        (xhr._mhUrl||"").includes("familygraphql")) {
      xhr.addEventListener("readystatechange", function() {
        if (xhr.readyState !== 4 || xhr.status !== 200) return;
        try {
          const j = JSON.parse(xhr.responseText);
          const arr = j?.data?.dna_kit?.dna_matches?.data;
          if (Array.isArray(arr) && arr.length > 0) {
            arr.forEach(m => { if (m?.id) window._mhMatches.set(m.id, m); });
          }
        } catch(_) {}
      });
    }
    return _send.apply(this, arguments);
  };
})();
"""

GET_COUNT_JS = "() => window._mhMatches ? window._mhMatches.size : 0"
GET_DATA_JS  = "() => window._mhMatches ? Array.from(window._mhMatches.values()) : []"


async def main():
    profile = default_profile()
    print(f"Chrome-Profil: {profile}")
    if not profile.exists():
        print("⚠️  Chrome-Profil nicht gefunden. Nutze frischen Browser ohne Login.")
        profile = None

    async with async_playwright() as p:
        # Echten Chrome-Browser mit bestehender Profil-Session starten
        launch_args = dict(
            headless=False,    # sichtbar – sieht aus wie normaler User
            slow_mo=50,        # kleine Verzögerungen für menschlichen Look
        )
        if profile:
            ctx = await p.chromium.launch_persistent_context(
                str(profile),
                channel="chrome",   # nutzt installierten Chrome, nicht Chromium
                **launch_args,
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        else:
            browser = await p.chromium.launch(**launch_args)
            ctx  = await browser.new_context(locale="de-DE",
                                             viewport={"width": 1280, "height": 900})
            page = await ctx.new_page()
            print("→ Bitte manuell einloggen, dann Enter drücken …")
            await page.goto("https://www.myheritage.com/login")
            input("Nach dem Login Enter drücken …")

        # Spy frühzeitig injizieren (vor Seitennavigation)
        await page.add_init_script(SPY_JS)

        print(f"Navigiere zu: {URL}")
        await page.goto(URL, wait_until="domcontentloaded")

        # Warten bis erste Matches geladen
        print("Warte auf erste Matches …")
        for _ in range(30):
            await asyncio.sleep(2)
            count = await page.evaluate(GET_COUNT_JS)
            if count > 0:
                print(f"✓ Erste Matches geladen: {count}")
                break
        else:
            print("❌ Keine Matches geladen. Session ggf. abgelaufen.")
            await ctx.close()
            return

        # Sanftes Scrollen
        last_count = 0
        stable     = 0
        scrolls    = 0

        print(f"Starte Scroll-Loop (Ziel: {TOTAL} Matches) …")

        while stable < 12 and await page.evaluate(GET_COUNT_JS) < TOTAL:
            # Zufälliger Scroll-Betrag
            amount = random.randint(800, 1200)
            await page.evaluate(f"window.scrollBy(0, {amount})")
            await page.evaluate("document.dispatchEvent(new Event('scroll', {bubbles: true}))")

            # Menschenähnliche Pause
            pause = 2.5 + random.random() * 2.0
            await asyncio.sleep(pause)
            scrolls += 1

            # Gelegentliche längere Pause
            if scrolls % 20 == 0:
                long_p = 4 + random.random() * 3
                print(f"  Pause {long_p:.1f}s …")
                await asyncio.sleep(long_p)

            current = await page.evaluate(GET_COUNT_JS)
            if current > last_count:
                last_count = current
                stable = 0
                pct = current / TOTAL * 100
                print(f"  [{scrolls:4d} Scrolls] {current:5d}/{TOTAL} ({pct:.1f}%)")
            else:
                stable += 1

            # Zwischenspeichern alle 1000 Matches
            if current > 0 and current % 1000 < 5 and current != last_count:
                arr = await page.evaluate(GET_DATA_JS)
                _save(arr, current, "backup")

        # Finale Extraktion
        print("Extrahiere alle Matches aus dem Spy …")
        arr = await page.evaluate(GET_DATA_JS)
        _save(arr, len(arr), "final")

        await ctx.close()
        print("✅ Fertig!")


def _save(arr: list, count: int, label: str):
    OUT_FILE.parent.mkdir(exist_ok=True)
    obj = {
        "meta": {
            "kit_id":           KIT_ID_INT,
            "site_id":          SITE_KIT,
            "total_count":      TOTAL,
            "downloaded_count": len(arr),
            "downloaded_at":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method":           f"playwright_{label}",
        },
        "matches": arr,
    }
    out = OUT_FILE.parent / f"mh_playwright_{count}_{label}.json"
    out.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    print(f"  Gespeichert: {out} ({len(arr)} Matches)")


if __name__ == "__main__":
    asyncio.run(main())
