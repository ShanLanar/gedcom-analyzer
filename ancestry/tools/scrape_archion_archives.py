#!/usr/bin/env python3
"""
Archion-Archiv-Katalog-Scraper.

Entdeckt alle verfügbaren Archive auf:
  https://www.archion.de/de/alle-archive

Archion hostet evangelische Kirchenbücher aus Deutschland, Schweiz, Österreich
und Polen. Vollständige Buchansicht erfordert ein Abonnement. Dieser Scraper
erstellt ausschließlich einen Archiv-Katalog (Name, Bundesland/Land, URL) —
kein Bilderdownload.

Das Katalog-DB-Schema ist so gewählt, dass eine spätere Erweiterung um
Pfarrei-/Buchebene (analog zu Matricula) nahtlos möglich ist.

Ausgabe:
    ancestry/tools/archion_archives.db    (SQLite)
    ancestry/tools/archion_archives.json  (Bundesland/Land → Archive, für externe_quellen)

Verwendung:
    python -m ancestry.tools.scrape_archion_archives
    python -m ancestry.tools.scrape_archion_archives --visible
    python -m ancestry.tools.scrape_archion_archives --pause 2.0
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
    except Exception:
        pass

import re

ROOT       = Path(__file__).resolve().parent.parent.parent
DB_PATH    = ROOT / "ancestry" / "tools" / "archion_archives.db"
JSON_PATH  = ROOT / "ancestry" / "tools" / "archion_archives.json"

ARCHION_BASE       = "https://www.archion.de"
ALLE_ARCHIVE_URL   = "https://www.archion.de/de/alle-archive"


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _init_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS archion_archives (
        id          TEXT PRIMARY KEY,   -- url-slug, z.B. niedersachsen/lka-hannover
        region      TEXT NOT NULL,      -- Bundesland / Land
        name        TEXT NOT NULL,
        url         TEXT NOT NULL,      -- Archiv-Übersichtsseite auf archion.de
        confession  TEXT DEFAULT 'evang',
        scraped_at  TEXT DEFAULT (datetime('now'))
    );

    -- Zukünftige Erweiterung: Pfarreien auf Archion (analog zu Matricula parishes)
    CREATE TABLE IF NOT EXISTS archion_parishes (
        id         TEXT PRIMARY KEY,
        archive_id TEXT NOT NULL,
        name       TEXT NOT NULL,
        url        TEXT NOT NULL,
        scraped_at TEXT DEFAULT (datetime('now'))
    );

    -- Zukünftige Erweiterung: Kirchenbücher auf Archion
    CREATE TABLE IF NOT EXISTS archion_books (
        id         TEXT PRIMARY KEY,
        parish_id  TEXT NOT NULL,
        book_type  TEXT,
        year_from  INTEGER,
        year_to    INTEGER,
        url        TEXT NOT NULL,
        scraped_at TEXT DEFAULT (datetime('now'))
    );
    """)
    return db


# ── Archiv-Übersicht scrapen ──────────────────────────────────────────────────

def scrape_archives(page, pause: float = 1.5) -> list[dict]:
    """Scrapt alle Archive von der Archion-Übersichtsseite."""
    print(f"Lade Archion-Archivübersicht: {ALLE_ARCHIVE_URL}")
    try:
        page.goto(ALLE_ARCHIVE_URL, wait_until="networkidle", timeout=30_000)
    except Exception:
        page.goto(ALLE_ARCHIVE_URL, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(pause)

    # Links mit Format /de/alle-archive/<region>/<archiv-slug>
    pattern = re.compile(r"/de/alle-archive/([^/]+)/([^/]+)/?$")
    seen: set[str] = set()
    archives: list[dict] = []

    for el in page.query_selector_all("a[href]"):
        href = el.get_attribute("href") or ""
        m    = pattern.search(href)
        if not m:
            continue
        region, slug = m.group(1), m.group(2)
        archive_id   = f"{region}/{slug}"
        if archive_id in seen:
            continue
        seen.add(archive_id)
        name     = (el.inner_text() or "").strip() or slug.replace("-", " ").title()
        full_url = (ARCHION_BASE + href) if href.startswith("/") else href
        archives.append({
            "id": archive_id, "region": region, "name": name,
            "url": full_url, "confession": "evang",
        })

    archives.sort(key=lambda a: (a["region"], a["name"]))
    return archives


# ── JSON-Lookup exportieren ───────────────────────────────────────────────────

def export_json(db: sqlite3.Connection, path: Path):
    """Erzeugt Region → Archive Lookup für externe_quellen.py."""
    lookup: dict[str, list[dict]] = {}
    for row in db.execute(
            "SELECT id, region, name, url, confession FROM archion_archives ORDER BY region, name"):
        region = row["region"]
        if region not in lookup:
            lookup[region] = []
        lookup[region].append({
            "id": row["id"], "name": row["name"],
            "url": row["url"], "confession": row["confession"],
        })
    path.write_text(json.dumps(lookup, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON-Lookup exportiert: {path}  ({sum(len(v) for v in lookup.values())} Archive)")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Archion-Archiv-Katalog-Scraper")
    ap.add_argument("--visible", action="store_true", help="Browser sichtbar")
    ap.add_argument("--pause", type=float, default=1.5,
                    help="Wartezeit zwischen Seiten (Sek., default: 1.5)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright nicht installiert:\n"
              "  pip install playwright && playwright install chromium")
        sys.exit(1)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = _init_db(DB_PATH)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.visible)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            locale="de-DE",
        )
        page = ctx.new_page()
        archives = scrape_archives(page, pause=args.pause)
        browser.close()

    if not archives:
        print("⚠ Keine Archive gefunden — Seitenstruktur hat sich möglicherweise geändert.")
        db.close()
        sys.exit(1)

    with db:
        for a in archives:
            db.execute(
                "INSERT OR REPLACE INTO archion_archives (id, region, name, url, confession) "
                "VALUES (:id, :region, :name, :url, :confession)", a)

    print(f"\n{len(archives)} Archive in DB gespeichert.")
    for r in sorted({a["region"] for a in archives}):
        n = sum(1 for a in archives if a["region"] == r)
        print(f"  {r:<40}  {n} Archive")

    export_json(db, JSON_PATH)
    db.close()


# ── Katalog-Abfrage (für externe_quellen.py) ─────────────────────────────────

def get_archives(db_path: Path | None = None) -> list[dict]:
    """Lädt den Archion-Katalog aus der DB. Gibt leere Liste wenn nicht vorhanden."""
    p = Path(db_path) if db_path else DB_PATH
    if not p.exists():
        return []
    db = sqlite3.connect(str(p))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT id, region, name, url FROM archion_archives ORDER BY region, name"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()


def get_archive_for_region(region_slug: str) -> dict | None:
    """Gibt das erste Archiv für eine Bundesland-Kennung zurück (Fallback: None)."""
    archives = get_archives()
    for a in archives:
        if a["region"] == region_slug:
            return a
    return None


if __name__ == "__main__":
    main()
