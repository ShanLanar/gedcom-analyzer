"""ancestry/core/cookie_capture.py — Browser-Cookie-Import ohne Browser-Extension.

Two backends, both output the same JSON list that AncestryAuth.login_cookies() expects:
  [{"name": "...", "value": "...", "domain": "...", "path": "/"}]

Backend 1 — Chrome/Playwright (already a project dependency):
    Launches a real Chrome window, user logs in normally,
    polls every 2 s for session cookies, auto-saves and closes.

Backend 2 — Firefox (zero new deps, pure stdlib sqlite3):
    Reads cookies.sqlite from the active Firefox profile,
    extracts matching domain cookies and saves them.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional


# ── Site configuration ────────────────────────────────────────────────────────

SITE_CONFIG: dict[str, dict] = {
    "ancestry": {
        "url":             "https://www.ancestry.com/account/signin",
        "domain_filter":   ".ancestry.com",
        "session_cookies": ["AncestrySessionId", "SecureATT", "authUserId", "UserId"],
        "min_session":     2,
    },
    "myheritage": {
        "url":             "https://www.myheritage.com/login",
        "domain_filter":   ".myheritage.com",
        "session_cookies": ["myheritage_user", "mhSessionId", "mt"],
        "min_session":     1,
    },
}

_DATA_DIR = Path(__file__).parent.parent / "data"


def _default_save_path(site: str) -> Path:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR / f"cookies_{site}.json"


def _save_cookies(cookies: list[dict], path: str | Path) -> None:
    """Normalise to login_cookies() format and write JSON."""
    normalised = [
        {
            "name":   c.get("name", ""),
            "value":  c.get("value", ""),
            "domain": c.get("domain", ""),
            "path":   c.get("path", "/"),
        }
        for c in cookies
        if c.get("name") and c.get("value")
    ]
    Path(path).write_text(json.dumps(normalised, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Backend 1: Chrome via Playwright ─────────────────────────────────────────

async def _capture_chrome_async(
    site: str,
    save_path: str | Path,
    status_cb: Callable[[str], None],
) -> bool:
    """
    Opens a non-headless Chrome window and polls for session cookies.

    Returns True if cookies were captured successfully.
    """
    from playwright.async_api import async_playwright  # type: ignore

    cfg = SITE_CONFIG.get(site)
    if cfg is None:
        status_cb(f"Unbekannte Site: {site}")
        return False

    required = set(cfg["session_cookies"])
    min_count = cfg["min_session"]

    status_cb("🌐 Chrome wird geöffnet — bitte einloggen …")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--window-size=1100,800"])
        context = await browser.new_context()
        page    = await context.new_page()
        await page.goto(cfg["url"])

        deadline = time.time() + 300  # 5-minute timeout
        captured: list[dict] = []

        while time.time() < deadline:
            await asyncio.sleep(2)
            cookies = await context.cookies()
            session = [c for c in cookies if c.get("name") in required]
            if len(session) >= min_count:
                captured = cookies
                break
            remaining = int(deadline - time.time())
            status_cb(f"⏳ Warte auf Login … ({remaining}s verbleibend)")

        await browser.close()

    if not captured:
        status_cb("❌ Timeout — keine Session-Cookies erkannt.")
        return False

    _save_cookies(captured, save_path)
    n = len([c for c in captured if c.get("value")])
    status_cb(f"✅ {n} Cookies gespeichert → {save_path}")
    return True


def capture_from_chrome(
    site: str,
    save_path: Optional[str | Path] = None,
    status_cb: Callable[[str], None] = print,
) -> bool:
    """Synchronous wrapper around _capture_chrome_async."""
    if save_path is None:
        save_path = _default_save_path(site)
    try:
        return asyncio.run(_capture_chrome_async(site, save_path, status_cb))
    except ImportError:
        status_cb("❌ Playwright nicht installiert (pip install playwright).")
        return False
    except Exception as exc:
        status_cb(f"❌ Chrome-Capture Fehler: {exc}")
        return False


# ── Backend 2: Firefox (pure stdlib) ─────────────────────────────────────────

def _find_firefox_cookie_db() -> Optional[Path]:
    """Return path to the most-recently-used Firefox cookies.sqlite, or None."""
    candidates: list[Path] = []

    home = Path.home()
    # Linux
    ff_linux = home / ".mozilla" / "firefox"
    # macOS
    ff_mac = home / "Library" / "Application Support" / "Firefox" / "Profiles"
    # Windows
    ff_win = home / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"

    for base in (ff_linux, ff_mac, ff_win):
        if base.is_dir():
            for profile in base.iterdir():
                db = profile / "cookies.sqlite"
                if db.is_file():
                    candidates.append(db)

    if not candidates:
        return None
    # Return the most recently modified profile
    return max(candidates, key=lambda p: p.stat().st_mtime)


def capture_from_firefox(
    site: str,
    save_path: Optional[str | Path] = None,
    status_cb: Callable[[str], None] = print,
) -> bool:
    """
    Read cookies from the active Firefox profile and save those matching *site*.

    Uses only stdlib (sqlite3, shutil, json) — no new dependencies.
    Firefox must be closed or the DB is locked; we work on a temp copy.
    """
    if save_path is None:
        save_path = _default_save_path(site)

    cfg = SITE_CONFIG.get(site)
    if cfg is None:
        status_cb(f"Unbekannte Site: {site}")
        return False

    domain_filter = cfg["domain_filter"].lstrip(".")

    db_path = _find_firefox_cookie_db()
    if db_path is None:
        status_cb("❌ Kein Firefox-Profil gefunden.")
        return False

    status_cb(f"🦊 Lese Firefox-Cookies aus: {db_path}")

    # Work on a temp copy because Firefox may have a lock on the original
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    try:
        shutil.copy2(db_path, tmp.name)
        con = sqlite3.connect(tmp.name)
        cur = con.execute(
            "SELECT name, value, host, path FROM moz_cookies WHERE host LIKE ?",
            (f"%{domain_filter}%",),
        )
        rows = cur.fetchall()
        con.close()
    except Exception as exc:
        status_cb(f"❌ SQLite-Fehler: {exc}")
        return False
    finally:
        os.unlink(tmp.name)

    if not rows:
        status_cb(f"○ Keine Cookies für {domain_filter} in Firefox gefunden.")
        return False

    cookies = [
        {"name": name, "value": value, "domain": host, "path": path}
        for name, value, host, path in rows
        if value
    ]
    _save_cookies(cookies, save_path)
    status_cb(f"✅ {len(cookies)} Firefox-Cookies gespeichert → {save_path}")
    return True
