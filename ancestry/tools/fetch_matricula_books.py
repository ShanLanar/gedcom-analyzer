#!/usr/bin/env python3
"""
Matricula-Kirchenbuch-Inventar – Bistum Osnabrück

Liest die Pfarreien aus matricula_parishes.db (erzeugt von
scrape_matricula_osnabrueck.py) und scrapt für jede Pfarrei die
Kirchenbuch-Liste: Typ (Taufe/Heirat/Tod), Jahresbereich, URL.

Ausgabe in matricula_parishes.db:
  kirchenbuecher  – ein Datensatz pro Buch

Lookup-Funktion für andere Tools:
  from tools.fetch_matricula_books import find_kirchenbuch
  rows = find_kirchenbuch(db, parish_id="ostercappeln", year=1812, book_type="Taufe")

Start:
    python fetch_matricula_books.py
    python fetch_matricula_books.py --visible
    python fetch_matricula_books.py --pause 1.0
    python fetch_matricula_books.py --parish ostercappeln
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(ROOT, "ancestry", "tools", "matricula_parishes.db")

_YEAR_RANGE_RE = re.compile(r"(\d{4})\s*[-–—]\s*(\d{4})")
_SINGLE_YEAR   = re.compile(r"\b(1[0-9]{3}|20\d{2})\b")

# Schlüsselwörter → kanonischer Buchtyp
_BOOK_TYPE_KEYS: list[tuple[str, str]] = [
    ("tauf",     "Taufe"),
    ("getauft",  "Taufe"),
    ("baptis",   "Taufe"),
    ("trauung",  "Heirat"),
    ("heirat",   "Heirat"),
    ("copulat",  "Heirat"),
    ("heiraten", "Heirat"),
    ("ehe",      "Heirat"),
    ("sterb",    "Tod"),
    ("bestat",   "Tod"),
    ("begraben", "Tod"),
    ("begräbn",  "Tod"),
    ("sepultur", "Tod"),
    ("verstorb", "Tod"),
    ("konfirm",  "Konfirmation"),
    ("firmung",  "Firmung"),
    ("komm",     "Kommunion"),
    ("indices",  "Index"),
    ("index",    "Index"),
]


def _detect_type(text: str) -> str:
    t = text.lower()
    for key, label in _BOOK_TYPE_KEYS:
        if key in t:
            return label
    return "unbekannt"


def _extract_years(text: str) -> tuple[int | None, int | None]:
    m = _YEAR_RANGE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    years = _SINGLE_YEAR.findall(text)
    if len(years) >= 2:
        return int(years[0]), int(years[-1])
    if years:
        return int(years[0]), None
    return None, None


# ── Datenbank ──────────────────────────────────────────────────────────────────

def _init_books_table(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS kirchenbuecher (
        book_id     TEXT PRIMARY KEY,   -- "<parish_id>/<matricula_sub_id>"
        parish_id   TEXT NOT NULL,
        book_type   TEXT NOT NULL DEFAULT 'unbekannt',
        year_from   INTEGER,
        year_to     INTEGER,
        label       TEXT DEFAULT '',    -- Original-Text vom Link
        url         TEXT DEFAULT '',
        scraped_at  TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_kb_parish ON kirchenbuecher(parish_id);
    CREATE INDEX IF NOT EXISTS idx_kb_type   ON kirchenbuecher(book_type);
    CREATE INDEX IF NOT EXISTS idx_kb_years  ON kirchenbuecher(year_from, year_to);
    """)


# ── Öffentliche Lookup-Funktion für andere Tools ───────────────────────────────

def find_kirchenbuch(
    db: sqlite3.Connection,
    parish_id: str,
    year: int,
    book_type: str = "Taufe",
) -> list[sqlite3.Row]:
    """
    Gibt alle Kirchenbücher zurück die parish_id + year + book_type abdecken.

    Bücher ohne Jahresangabe werden immer mitgeliefert (konservativ).
    """
    return db.execute(
        """
        SELECT * FROM kirchenbuecher
        WHERE parish_id = ?
          AND book_type  = ?
          AND (year_from IS NULL OR year_from <= ?)
          AND (year_to   IS NULL OR year_to   >= ?)
        ORDER BY year_from
        """,
        (parish_id, book_type, year, year),
    ).fetchall()


def find_kirchenbuch_by_village(
    db: sqlite3.Connection,
    village: str,
    year: int,
    book_type: str = "Taufe",
) -> list[sqlite3.Row]:
    """
    Wie find_kirchenbuch, aber löst den Ortsnamen über parish_villages auf.
    Gibt [] zurück wenn der Ort keiner Pfarrei zugeordnet ist.
    """
    row = db.execute(
        "SELECT parish_id FROM parish_villages WHERE lower(village) = lower(?)",
        (village.strip(),),
    ).fetchone()
    if not row:
        # Fallback: direkt als parish_id versuchen
        row = db.execute(
            "SELECT id AS parish_id FROM parishes WHERE lower(id) = lower(?)",
            (village.strip(),),
        ).fetchone()
    if not row:
        return []
    return find_kirchenbuch(db, row["parish_id"], year, book_type)


# ── Scraping ───────────────────────────────────────────────────────────────────

def scrape_books(
    headless: bool = True,
    pause: float = 1.0,
    parish_filter: str | None = None,
) -> int:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("Playwright nicht installiert:\n"
              "  pip install playwright && playwright install chromium")
        sys.exit(1)

    if not os.path.exists(DB_PATH):
        print(f"⚠ Pfarrei-DB nicht gefunden: {DB_PATH}\n"
              "  Bitte zuerst scrape_matricula_osnabrueck.py ausführen.")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    _init_books_table(db)

    where  = " WHERE id = ?" if parish_filter else ""
    params = [parish_filter] if parish_filter else []
    parishes = db.execute(
        f"SELECT id, name, url FROM parishes{where} ORDER BY name", params
    ).fetchall()

    if not parishes:
        print("Keine Pfarreien in DB. Bitte erst scrape_matricula_osnabrueck.py ausführen.")
        sys.exit(1)

    print(f"{len(parishes)} Pfarreien werden verarbeitet …\n")
    total_books = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
            ),
            locale="de-DE",
        )
        page = ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "de-DE,de;q=0.9"})

        for i, parish in enumerate(parishes, 1):
            pid  = parish["id"]
            name = parish["name"]
            url  = (parish["url"]
                    or f"https://data.matricula-online.eu/de/deutschland/osnabrueck/{pid}/")

            print(f"  [{i:3d}/{len(parishes)}] {name:<45}", end=" ", flush=True)

            try:
                try:
                    page.goto(url, wait_until="networkidle", timeout=20_000)
                except PWTimeout:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                time.sleep(pause * 0.4)

                # Links die auf Kirchenbücher dieser Pfarrei zeigen:
                # .../osnabrueck/<parish-id>/<book-id>/
                book_pattern = re.compile(
                    rf"/de/deutschland/osnabrueck/{re.escape(pid)}/([^/?#]+)/?$"
                )
                books_found: list[dict] = []
                seen: set[str] = set()

                for link in page.query_selector_all("a[href]"):
                    href  = link.get_attribute("href") or ""
                    m     = book_pattern.search(href)
                    if not m:
                        continue
                    sub_id = m.group(1)
                    if sub_id in seen:
                        continue
                    seen.add(sub_id)

                    label    = (link.inner_text() or "").strip()
                    full_url = (
                        f"https://data.matricula-online.eu{href}"
                        if href.startswith("/") else href
                    )

                    # Typ + Jahre aus Label und Sub-ID ableiten
                    hint      = f"{label} {sub_id}"
                    book_type = _detect_type(hint)
                    year_from, year_to = _extract_years(hint)

                    books_found.append({
                        "book_id":   f"{pid}/{sub_id}",
                        "parish_id": pid,
                        "book_type": book_type,
                        "year_from": year_from,
                        "year_to":   year_to,
                        "label":     label,
                        "url":       full_url,
                    })

                with db:
                    for b in books_found:
                        db.execute(
                            """
                            INSERT OR REPLACE INTO kirchenbuecher
                                (book_id, parish_id, book_type,
                                 year_from, year_to, label, url)
                            VALUES
                                (:book_id, :parish_id, :book_type,
                                 :year_from, :year_to, :label, :url)
                            """,
                            b,
                        )

                total_books += len(books_found)
                types  = sorted({b["book_type"] for b in books_found})
                yr_min = min((b["year_from"] for b in books_found if b["year_from"]),
                             default=None)
                yr_max = max((b["year_to"]   for b in books_found if b["year_to"]),
                             default=None)
                yr_str = f"{yr_min}–{yr_max}" if yr_min else "?"
                print(f"✓  {len(books_found):2d} Bücher  {yr_str:>12}  {types}")

            except Exception as e:
                print(f"⚠ {e}")

            time.sleep(pause * 0.3)

        browser.close()

    _print_summary(db, total_books)
    return total_books


def _print_summary(db: sqlite3.Connection, total: int) -> None:
    stats = db.execute(
        """
        SELECT book_type,
               COUNT(*)    AS n,
               MIN(year_from) AS y_min,
               MAX(year_to)   AS y_max
        FROM kirchenbuecher
        GROUP BY book_type
        ORDER BY n DESC
        """
    ).fetchall()

    print(f"\n✅  {total} Kirchenbücher indexiert\n")
    print(f"  {'Typ':<20} {'Anzahl':>6}  {'von':>6}  {'bis':>6}")
    print(f"  {'-'*20} {'-'*6}  {'-'*6}  {'-'*6}")
    for row in stats:
        y_min = str(row["y_min"]) if row["y_min"] else "?"
        y_max = str(row["y_max"]) if row["y_max"] else "?"
        print(f"  {row['book_type']:<20} {row['n']:>6}  {y_min:>6}  {y_max:>6}")

    print(f"\n  DB: {DB_PATH}")


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Matricula Kirchenbuch-Inventar für Bistum Osnabrück scrapen"
    )
    ap.add_argument("--visible",  action="store_true",
                    help="Browser sichtbar anzeigen")
    ap.add_argument("--pause",    type=float, default=1.0,
                    help="Wartezeit zwischen Seiten in Sekunden (default: 1.0)")
    ap.add_argument("--parish",   default=None,
                    help="Nur diese eine Pfarrei (Slug) verarbeiten")
    args = ap.parse_args()
    scrape_books(headless=not args.visible, pause=args.pause,
                 parish_filter=args.parish)
