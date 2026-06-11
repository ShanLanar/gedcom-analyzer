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

_MATRICULA_BASE = "https://data.matricula-online.eu"

_YEAR_RE = re.compile(r"\b(\d{4})\b")

# Matricula-Matrikeltyp-Namen → kanonischer Buchtyp
# Quelle: Drop-down-Optionen aus der echten Matricula-HTML
_MATRIKEL_TYPE_MAP: dict[str, str] = {
    "taufen":                    "Taufe",
    "trauungen":                 "Heirat",
    "heiraten":                  "Heirat",
    "beerdigungen":              "Tod",
    "sterbefälle":               "Tod",
    "taufen - trauungen":        "gemischt",
    "taufen heiraten":           "gemischt",
    "firmungen":                 "Firmung",
    "firmung":                   "Firmung",
    "erstkommunion":             "Kommunion",
    "kommunion":                 "Kommunion",
    "familienkatalog":           "Familienkatalog",
    "index":                     "Index",
    "index - taufen":            "Index",
    "index - trauungen":         "Index",
}


def _map_matrikel_type(raw: str) -> str:
    """Mappt einen Matricula-Matrikeltyp-String auf unsere kanonischen Typen."""
    key = raw.strip().lower()
    # Exakter Match
    if key in _MATRIKEL_TYPE_MAP:
        return _MATRIKEL_TYPE_MAP[key]
    # Teilstring-Match für zusammengesetzte Typen
    for pattern, label in _MATRIKEL_TYPE_MAP.items():
        if pattern in key:
            return label
    return raw.strip() or "unbekannt"


def _extract_years(text: str) -> tuple[int | None, int | None]:
    """Extrahiert Start- und Endjahr aus einem Matricula-Datums-String.
    Eingabe: "1681 März - 1697 Sep"  →  (1681, 1697)
    """
    years = _YEAR_RE.findall(text)
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
    # Migration: add slug column if parishes table was created by an older version
    try:
        db.execute("ALTER TABLE parishes ADD COLUMN slug TEXT NOT NULL DEFAULT ''")
        db.commit()
    except Exception:
        pass
    # Backfill slug = last path segment of id, for rows still empty
    rows = db.execute("SELECT id FROM parishes WHERE slug = '' OR slug IS NULL").fetchall()
    if rows:
        for (pid,) in rows:
            slug = pid.rsplit("/", 1)[-1] if "/" in pid else pid
            db.execute("UPDATE parishes SET slug=? WHERE id=?", (slug, pid))
        db.commit()


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
    Gibt alle passenden Bücher zurück (ein Ort kann bei Grenzfällen in mehreren
    Pfarreien liegen — z.B. nach Abpfarrung; Caller entscheidet).
    parish_id in parish_villages ist die volle kanonische ID.
    """
    parish_ids = [
        row[0]
        for row in db.execute(
            "SELECT DISTINCT parish_id FROM parish_villages WHERE lower(village) = lower(?)",
            (village.strip(),),
        ).fetchall()
    ]
    if not parish_ids:
        # Fallback: Slug oder volle ID direkt versuchen
        row = db.execute(
            "SELECT id FROM parishes WHERE lower(slug) = lower(?) OR lower(id) = lower(?)",
            (village.strip(), village.strip()),
        ).fetchone()
        if row:
            parish_ids = [row["id"]]

    results = []
    for pid in parish_ids:
        results.extend(find_kirchenbuch(db, pid, year, book_type))
    return results


# ── Pfarrei-Auflösung mit Disambiguierung ─────────────────────────────────────

def _resolve_parishes(
    db: sqlite3.Connection,
    parish_filter: str | None,
) -> list[sqlite3.Row]:
    """
    Löst einen Parish-Filter auf. Akzeptiert:
      - None              → alle Pfarreien
      - Vollständige ID   → "deutschland/osnabrueck/ostercappeln"
      - Slug (eindeutig)  → "ostercappeln"
      - Slug (mehrdeutig) → zeigt alle Treffer und bricht ab

    Bricht mit exit(1) ab wenn ein Slug auf mehrere Pfarreien passt,
    damit nie stillschweigend das falsche Kirchspiel gescannt wird.
    """
    if parish_filter is None:
        return db.execute("SELECT id, slug, name, url FROM parishes ORDER BY name").fetchall()

    # Exakter Match auf volle ID
    rows = db.execute(
        "SELECT id, slug, name, url FROM parishes WHERE id = ?",
        (parish_filter,),
    ).fetchall()
    if rows:
        return rows

    # Slug-Match (Spalte slug oder letzter Teil der ID)
    rows = db.execute(
        "SELECT id, slug, name, url FROM parishes WHERE slug = ? OR id LIKE ?",
        (parish_filter, f"%/{parish_filter}"),
    ).fetchall()

    if len(rows) == 1:
        return rows

    if len(rows) > 1:
        print(f"⚠ '{parish_filter}' ist mehrdeutig — {len(rows)} Pfarreien gefunden:")
        print()
        for r in rows:
            print(f"  {r['id']:<55} {r['name']}")
        print()
        print("Bitte die vollständige ID angeben, z.B.:")
        print(f"  --parish {rows[0]['id']}")
        sys.exit(1)

    # Teilstring-Suche als Fallback
    rows = db.execute(
        "SELECT id, slug, name, url FROM parishes WHERE id LIKE ? OR name LIKE ?",
        (f"%{parish_filter}%", f"%{parish_filter}%"),
    ).fetchall()
    if len(rows) == 1:
        return rows
    if len(rows) > 1:
        print(f"⚠ '{parish_filter}' passt auf {len(rows)} Pfarreien:")
        print()
        for r in rows:
            print(f"  {r['id']:<55} {r['name']}")
        print()
        print("Bitte präziser angeben.")
        sys.exit(1)

    print(f"⚠ Keine Pfarrei gefunden für '{parish_filter}'.")
    return []


# ── Tabellen-Parser ───────────────────────────────────────────────────────────

_JS_PARSE_BOOK_TABLE = """
() => {
    // Liest alle Buchzeilen aus der Matricula-Matriken-Tabelle.
    // Hauptzeile (<tr>):
    //   td[0]  Kamera-Link → /de/…/D1_001_1/
    //   td[1]  Signatur    → D1_001_1
    //   td[2]  Anzeigetyp  → "Taufen Heiraten Lutheraner …" (variiert)
    //   td[3]  Datum       → "1681 März - 1697 Sep"
    // Detailzeile (<tr class="collapse">):
    //   dt=Matrikeltyp / dd=normalisierter Typ → "Taufen - Trauungen"
    //   dt=Beginn Datumsbereich  / dd="1. Januar 1681"
    //   dt=Ende Datumsbereich    / dd="31. Dezember 1705"
    const rows = [];
    const trs = Array.from(document.querySelectorAll('table.table-bordered tr'));
    for (let idx = 0; idx < trs.length; idx++) {
        const tr = trs[idx];
        const tds = tr.querySelectorAll('td');
        if (tds.length < 4) continue;

        const camLink = tds[0].querySelector('a[href*="/de/"]');
        if (!camLink) continue;
        const href = camLink.getAttribute('href') || '';

        const signatur = tds[1].innerText.trim();
        if (!signatur) continue;

        // Anzeigetyp (3. Spalte) — kann ausführlicher Text sein
        const typDisplay = tds[2].innerText.trim();
        const datum = tds[3].innerText.trim();

        // Normalisierter Matrikeltyp aus Detailzeile (nächste .collapse tr)
        let typNorm = typDisplay;
        let datumVon = '', datumBis = '';
        const nextTr = trs[idx + 1];
        if (nextTr && nextTr.classList.contains('collapse')) {
            for (const dt of nextTr.querySelectorAll('dt')) {
                const label = dt.innerText.trim();
                const dd = dt.nextElementSibling;
                if (!dd) continue;
                const val = dd.innerText.trim();
                if (label === 'Matrikeltyp')       typNorm  = val;
                if (label.includes('Beginn'))       datumVon = val;
                if (label.includes('Ende'))         datumBis = val;
            }
        }

        rows.push({ href, signatur, typDisplay, typNorm, datum, datumVon, datumBis });
    }
    return rows;
}
"""

_JS_NEXT_PAGE = """
() => {
    // Gibt die URL der nächsten Seite zurück, oder null.
    // Matricula-Bücherliste: ?page=2, ?page=3, …
    const next = document.querySelector(
        'ul.pagination a[href*="?page="]:last-of-type, ' +
        '.page-item:not(.disabled) a[href*="?page="]'
    );
    // Nur wenn es wirklich eine "weiter"-Seite gibt (nicht die aktive)
    const active = document.querySelector('.page-item.active');
    if (!next || !active) return null;
    // Aktive Seitennummer
    const activePg = parseInt(active.innerText, 10) || 1;
    // URL der nächsten Seite
    const url = next.getAttribute('href');
    // Seitennummer aus der URL extrahieren
    const m = url.match(/[?&]page=(\\d+)/);
    if (!m) return null;
    const nextPg = parseInt(m[1], 10);
    return nextPg > activePg ? url : null;
}
"""


def _scrape_parish_books(
    page,
    parish_id: str,
    base_url: str,
    pause: float,
) -> list[dict]:
    """
    Scrapt alle Kirchenbücher einer Pfarrei aus der Matricula-Tabelle.

    Matricula zeigt 50 Bücher pro Seite — die Bücherliste selbst ist mit
    ?page=2, ?page=3 … paginiert (nicht zu verwechseln mit ?pg=N für
    die Bilder-Seiten im Viewer).

    Liest Signatur, Matrikeltyp und Datumsbereich direkt aus den <td>-Zellen —
    nicht aus dem Link-Text, da Kamera-Links nur ein Icon enthalten.
    """
    from playwright.sync_api import TimeoutError as PWTimeout  # noqa

    # Erste Seite der Bücherliste
    try:
        page.goto(base_url, wait_until="networkidle", timeout=20_000)
    except PWTimeout:
        page.goto(base_url, wait_until="domcontentloaded", timeout=20_000)
    time.sleep(pause * 0.4)

    all_rows: list[dict] = []
    seen_sigs: set[str] = set()

    while True:
        raw_rows = page.evaluate(_JS_PARSE_BOOK_TABLE)

        for r in raw_rows:
            sig = r["signatur"]
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)

            href     = r["href"]    # /de/deutschland/osnabrueck/ostercappeln-st-lambertus/D1_001_1/
            sub_id   = href.rstrip("/").rsplit("/", 1)[-1]
            full_url = f"{_MATRICULA_BASE}{href}" if href.startswith("/") else href

            # Normalisierter Typ aus Detailzeile bevorzugen (z.B. "Taufen - Trauungen"
            # statt "Taufen Heiraten Lutheraner in Kapelle Arenshorst")
            typ_raw   = r.get("typNorm") or r.get("typDisplay", "")
            book_type = _map_matrikel_type(typ_raw)

            # Präzise Jahresgrenzen aus Detailzeile, Fallback auf Anzeigedatum
            datum_von = r.get("datumVon", "")
            datum_bis = r.get("datumBis", "")
            if datum_von and datum_bis:
                yf, _   = _extract_years(datum_von)
                _, yt   = _extract_years(datum_bis)
                year_from, year_to = yf, yt
            else:
                year_from, year_to = _extract_years(r.get("datum", ""))

            all_rows.append({
                "book_id":   f"{parish_id}/{sub_id}",
                "parish_id": parish_id,
                "book_type": book_type,
                "year_from": year_from,
                "year_to":   year_to,
                # Label = Anzeigetext + Datum — lesbarer als nur Signatur
                "label":     f"{r.get('typDisplay', typ_raw)} {r.get('datum', '')}".strip(),
                "url":       full_url,
            })

        # Nächste Seite?
        next_href = page.evaluate(_JS_NEXT_PAGE)
        if not next_href:
            break

        next_url = (
            f"{_MATRICULA_BASE}{next_href}"
            if next_href.startswith("/") else
            f"{base_url.rstrip('/')}/{next_href.lstrip('/')}"
        )
        try:
            page.goto(next_url, wait_until="networkidle", timeout=15_000)
        except PWTimeout:
            page.goto(next_url, wait_until="domcontentloaded", timeout=15_000)
        time.sleep(pause * 0.3)

    return all_rows


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

    parishes = _resolve_parishes(db, parish_filter)
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
            pid  = parish["id"]   # deutschland/osnabrueck/ostercappeln-st-lambertus
            name = parish["name"]
            base_url = parish["url"] or f"{_MATRICULA_BASE}/de/{pid}/"

            print(f"  [{i:3d}/{len(parishes)}] {name:<45}", end=" ", flush=True)

            try:
                books_found = _scrape_parish_books(page, pid, base_url, pause)

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
