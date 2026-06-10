#!/usr/bin/env python3
"""
Matricula-Kirchspiel-Scanner

Scannt alle Kirchenbücher eines Kirchspiels komplett durch:
  1. Playwright öffnet jede Buchseite, fängt Bild-Requests ab
  2. Seiten-Bilder werden lokal archiviert (für spätere Re-Transkription)
  3. Bilder werden als Base64 an Claude Vision geschickt
  4. Claude transkribiert alle Einträge auf der Seite als JSON
  5. Ergebnisse landen in source_matrikula_entries + Fortschritt in matricula_page_scans

Bild-Archiv:
    <archive_dir>/<parish_id>/<book_sub_id>/<page_nr:04d>.jpg
    Standard: ~/matricula_images/ (überschreibbar mit --archive-dir oder MATRICULA_ARCHIVE)
    Vorhandene Bilder werden beim Re-Scan direkt geladen (kein Re-Download).

Setzt voraus:
  - scrape_matricula_osnabrueck.py wurde ausgeführt (Pfarrei-DB existiert)
  - fetch_matricula_books.py wurde ausgeführt (Buchverzeichnis existiert)
  - ANTHROPIC_API_KEY ist gesetzt

Start:
    python scan_matricula_kirchspiel.py --parish ostercappeln
    python scan_matricula_kirchspiel.py --parish ostercappeln --book-type Taufe
    python scan_matricula_kirchspiel.py --parish ostercappeln --year-from 1780 --year-to 1850
    python scan_matricula_kirchspiel.py --parish ostercappeln --visible --pause 2.0
    python scan_matricula_kirchspiel.py --parish ostercappeln --dry-run   # ohne API-Calls

Re-Transkription (Bilder bereits lokal vorhanden):
    python scan_matricula_kirchspiel.py --parish ostercappeln --retranscribe
    Löscht die alten Einträge für das Kirchspiel und transkribiert alle archivierten
    Bilder neu — kein erneuter Web-Zugriff auf Matricula nötig.

Fortsetzen nach Unterbrechung:
    Bereits gescannte Seiten werden übersprungen (Status 'done' in matricula_page_scans).
    Einfach denselben Befehl erneut ausführen.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT         = Path(__file__).resolve().parent.parent.parent
PARISH_DB    = ROOT / "ancestry" / "tools" / "matricula_parishes.db"
CHROME_PATH  = os.environ.get(
    "PLAYWRIGHT_CHROMIUM",
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
)
DEFAULT_ARCHIVE = Path(os.environ.get(
    "MATRICULA_ARCHIVE",
    os.path.expanduser("~/matricula_images"),
))

# Matricula-Basis-URL
BASE_URL = "https://data.matricula-online.eu"

# Wie viele Sekunden zwischen Seiten-Requests
DEFAULT_PAUSE = 1.5

# Claude-Modell für Transkription: Haiku ist günstiger, Sonnet besser bei
# schwer lesbarer Kurrentschrift
VISION_MODEL = os.environ.get("MATRICULA_VISION_MODEL", "claude-haiku-4-5-20251001")


# ── Prompts ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "Du bist ein Experte für historische deutsche Kirchenbücher aus dem Bistum Osnabrück "
    "(18.–19. Jahrhundert). Du liest Kurrentschrift und erkennst die typischen Eintragsformate "
    "für Taufen, Heiraten und Sterbefälle. Antworte ausschließlich mit validem JSON."
)

_TAUFE_PROMPT = """Lies alle Taufeinträge auf dieser Kirchenbuchseite.
Gib ein JSON-Array zurück. Jedes Element hat folgende Felder (leer lassen wenn nicht lesbar):
{
  "nr":            "laufende Nummer im Buch (falls vorhanden)",
  "datum":         "Taufdatum (TT.MM.JJJJ oder Freitext)",
  "jahr":          1812,
  "kind_name":     "Vorname des Täuflings",
  "kind_geschlecht": "m/w",
  "vater_name":    "Vorname Nachname des Vaters",
  "mutter_name":   "Vorname (Geburtsname) der Mutter",
  "taufpaten":     ["Name1", "Name2"],
  "ort":           "Ort / Bauerschaft",
  "anmerkungen":   "sonstige Angaben"
}
Antworte nur mit dem JSON-Array, ohne Erklärung."""

_HEIRAT_PROMPT = """Lies alle Heiratseinträge auf dieser Kirchenbuchseite.
Gib ein JSON-Array zurück. Jedes Element:
{
  "nr":              "laufende Nummer",
  "datum":           "Heiratsdatum",
  "jahr":            1812,
  "braeutigam_name": "Vorname Nachname",
  "braeutigam_vater": "Name des Vaters des Bräutigams",
  "braeutigam_ort":  "Wohnort Bräutigam",
  "braut_name":      "Vorname Geburtsname",
  "braut_vater":     "Name des Vaters der Braut",
  "braut_ort":       "Wohnort Braut",
  "zeugen":          ["Name1", "Name2"],
  "anmerkungen":     "sonstige Angaben"
}
Antworte nur mit dem JSON-Array."""

_TOD_PROMPT = """Lies alle Sterbe-/Beerdigungseinträge auf dieser Kirchenbuchseite.
Gib ein JSON-Array zurück. Jedes Element:
{
  "nr":           "laufende Nummer",
  "datum":        "Sterbedatum oder Begräbnisdatum",
  "jahr":         1812,
  "name":         "Vorname Nachname",
  "geschlecht":   "m/w",
  "alter":        "Alter oder Geburtsjahr falls angegeben",
  "stand":        "ledig/verheiratet/verwitwet",
  "eltern":       "Elternteil(e) falls angegeben",
  "ort":          "Ort / Bauerschaft",
  "todesursache": "falls angegeben",
  "anmerkungen":  "sonstige Angaben"
}
Antworte nur mit dem JSON-Array."""

_PROMPTS = {
    "Taufe":  _TAUFE_PROMPT,
    "Heirat": _HEIRAT_PROMPT,
    "Tod":    _TOD_PROMPT,
}
_DEFAULT_PROMPT = _TAUFE_PROMPT  # Fallback für unbekannte Buchtypen


# ── Datenbank ──────────────────────────────────────────────────────────────────

def _open_parish_db() -> sqlite3.Connection:
    if not PARISH_DB.exists():
        print(f"⚠ Pfarrei-DB nicht gefunden: {PARISH_DB}")
        print("  Bitte zuerst ausführen:")
        print("    python scrape_matricula_osnabrueck.py")
        print("    python fetch_matricula_books.py")
        sys.exit(1)
    db = sqlite3.connect(str(PARISH_DB))
    db.row_factory = sqlite3.Row
    # Fortschritts-Tabelle anlegen falls nicht vorhanden
    db.executescript("""
    CREATE TABLE IF NOT EXISTS matricula_page_scans (
        scan_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id     TEXT NOT NULL,
        page_nr     INTEGER NOT NULL,
        image_url   TEXT DEFAULT '',
        image_path  TEXT DEFAULT '',   -- lokaler Archivpfad
        status      TEXT DEFAULT 'pending',  -- pending | done | error | skip
        entry_count INTEGER DEFAULT 0,
        scanned_at  TEXT DEFAULT '',
        error_msg   TEXT DEFAULT '',
        UNIQUE (book_id, page_nr)
    );
    CREATE INDEX IF NOT EXISTS idx_mps_book   ON matricula_page_scans(book_id);
    CREATE INDEX IF NOT EXISTS idx_mps_status ON matricula_page_scans(status);
    """)
    # Migration: image_path-Spalte nachrüsten falls Tabelle aus alter Version
    try:
        db.execute("ALTER TABLE matricula_page_scans ADD COLUMN image_path TEXT DEFAULT ''")
        db.commit()
    except Exception:
        pass
    return db


def _open_main_db():
    """Öffnet die Haupt-ancestry.db für source_matrikula_entries."""
    main_db_path = ROOT / "ancestry.db"
    if not main_db_path.exists():
        # Fallback: neben PARISH_DB
        main_db_path = PARISH_DB.parent / "matricula_entries.db"

    db = sqlite3.connect(str(main_db_path))
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS source_matrikula_entries (
        entry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id      TEXT NOT NULL,
        page_nr      INTEGER,
        entry_type   TEXT NOT NULL,
        event_date   TEXT DEFAULT '',
        event_year   INTEGER,
        person_name  TEXT DEFAULT '',
        person2_name TEXT DEFAULT '',
        father_name  TEXT DEFAULT '',
        mother_name  TEXT DEFAULT '',
        village      TEXT DEFAULT '',
        notes        TEXT DEFAULT '',
        raw_json     TEXT DEFAULT '',
        created_at   TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_sme_book  ON source_matrikula_entries(book_id);
    CREATE INDEX IF NOT EXISTS idx_sme_year  ON source_matrikula_entries(event_year);
    CREATE INDEX IF NOT EXISTS idx_sme_name  ON source_matrikula_entries(person_name);
    """)
    return db


# ── Claude Vision ──────────────────────────────────────────────────────────────

def _transcribe_page(image_bytes: bytes, book_type: str, dry_run: bool) -> list[dict]:
    """Schickt ein Seiten-Bild an Claude Vision und gibt strukturierte Einträge zurück."""
    if dry_run:
        print("  [dry-run: kein API-Call]")
        return []

    try:
        import anthropic
    except ImportError:
        print("  ⚠ anthropic nicht installiert: pip install anthropic")
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  ⚠ ANTHROPIC_API_KEY nicht gesetzt")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    prompt = _PROMPTS.get(book_type, _DEFAULT_PROMPT)
    b64    = base64.standard_b64encode(image_bytes).decode()

    try:
        response = client.messages.create(
            model=VISION_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        raw = response.content[0].text.strip()
        # JSON aus der Antwort extrahieren (manchmal kommt Markdown drumrum)
        m = re.search(r"\[.*\]", raw, re.S)
        if m:
            return json.loads(m.group())
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON-Parse-Fehler: {e}")
        return []
    except Exception as e:
        print(f"  ⚠ API-Fehler: {e}")
        return []


# ── Einträge speichern ─────────────────────────────────────────────────────────

def _save_entries(
    main_db: sqlite3.Connection,
    book_id: str,
    page_nr: int,
    book_type: str,
    entries: list[dict],
) -> int:
    """Speichert transkribierte Einträge in source_matrikula_entries."""
    if not entries:
        return 0

    rows = []
    for e in entries:
        if book_type == "Taufe":
            person  = e.get("kind_name", "")
            person2 = ""
            father  = e.get("vater_name", "")
            mother  = e.get("mutter_name", "")
        elif book_type == "Heirat":
            person  = e.get("braeutigam_name", "")
            person2 = e.get("braut_name", "")
            father  = e.get("braeutigam_vater", "")
            mother  = e.get("braut_vater", "")
        else:  # Tod
            person  = e.get("name", "")
            person2 = ""
            father  = e.get("eltern", "")
            mother  = ""

        year = e.get("jahr")
        if isinstance(year, str):
            m = re.search(r"\d{4}", year)
            year = int(m.group()) if m else None

        rows.append((
            book_id, page_nr, book_type,
            e.get("datum", ""), year,
            person, person2, father, mother,
            e.get("ort", "") or e.get("braeutigam_ort", ""),
            e.get("anmerkungen", ""),
            json.dumps(e, ensure_ascii=False),
        ))

    with main_db:
        main_db.executemany(
            """
            INSERT INTO source_matrikula_entries
                (book_id, page_nr, entry_type, event_date, event_year,
                 person_name, person2_name, father_name, mother_name,
                 village, notes, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
    return len(rows)


# ── Playwright-Seiten-Scanner ──────────────────────────────────────────────────

def _archive_path(archive_dir: Path, book_id: str, page_nr: int) -> Path:
    """
    Kanonischer Archiv-Pfad für eine Buchseite.

    book_id = "deutschland/osnabrueck/ostercappeln-st-lambertus/TauBu-1697-1820"
    →  <archive_dir>/ostercappeln-st-lambertus/TauBu-1697-1820/0001.jpg

    Nur die letzten zwei Segmente werden als Verzeichnis verwendet —
    die Diözese-Präfixe sind im Archiv redundant, da Matriculas eigene
    Slugs bereits global eindeutig sind.
    """
    parts      = book_id.split("/")
    parish_slug = parts[-2] if len(parts) >= 2 else book_id
    book_slug   = parts[-1]
    return archive_dir / parish_slug / book_slug / f"{page_nr:04d}.jpg"


def _scan_book(
    book: sqlite3.Row,
    parish_db: sqlite3.Connection,
    main_db: sqlite3.Connection,
    pw_page,            # Playwright page-Objekt (None bei --retranscribe)
    pause: float,
    dry_run: bool,
    archive_dir: Path = DEFAULT_ARCHIVE,
    retranscribe: bool = False,
) -> tuple[int, int]:
    """Scannt ein Kirchenbuch. Gibt (gescannte Seiten, neue Einträge) zurück."""
    book_id   = book["book_id"]
    book_type = book["book_type"]
    book_url  = book["url"]
    # book_id already contains the full path incl. diocese prefix
    if not book_url:
        book_url = f"{BASE_URL}/de/{book_id}/"

    print(f"\n  Buch: {book_id}  [{book_type}  {book['year_from'] or '?'}–{book['year_to'] or '?'}]")
    print(f"  URL:  {book_url}")

    # Buchseite laden — direkt ?pg=1 damit der Viewer und sein Pagination-UI
    # vollständig geladen sind (nötig für _detect_page_count)
    pg1_url = f"{book_url.rstrip('/')}/?pg=1"
    try:
        pw_page.goto(pg1_url, wait_until="networkidle", timeout=30_000)
    except Exception:
        pw_page.goto(pg1_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(pause)

    # ── Seitenanzahl ermitteln ────────────────────────────────────────────────
    total_pages = _detect_page_count(pw_page)
    if total_pages is None:
        print("  ⚠ Konnte Seitenanzahl nicht ermitteln — überspringe Buch")
        return 0, 0

    # ── Seiten bestimmen ─────────────────────────────────────────────────────
    if retranscribe:
        # Alle lokal archivierten Seiten dieses Buchs scannen
        parts        = book_id.split("/")
        parish_slug  = parts[-2] if len(parts) >= 2 else book_id
        book_slug    = parts[-1]
        book_archive = archive_dir / parish_slug / book_slug
        archived = sorted(book_archive.glob("*.jpg")) if book_archive.exists() else []
        total_pages = len(archived)
        if not total_pages:
            print("  ⚠ Keine archivierten Bilder — überspringe")
            return 0, 0
        print(f"  {total_pages} archivierte Seiten (Re-Transkription)")
        # Alte Einträge löschen
        with main_db:
            main_db.execute(
                "DELETE FROM source_matrikula_entries WHERE book_id=?", (book_id,)
            )
        with parish_db:
            parish_db.execute(
                "UPDATE matricula_page_scans SET status='pending' WHERE book_id=?",
                (book_id,),
            )
        done_pages: set[int] = set()
        page_range = [int(p.stem) for p in archived]
    else:
        print(f"  {total_pages} Seiten gefunden")
        done_pages = {
            row[0]
            for row in parish_db.execute(
                "SELECT page_nr FROM matricula_page_scans WHERE book_id=? AND status='done'",
                (book_id,),
            ).fetchall()
        }
        remaining = total_pages - len(done_pages)
        print(f"  {len(done_pages)} bereits fertig, {remaining} verbleibend")
        page_range = list(range(1, total_pages + 1))

    # Seiten mit manuellen Viewer-Korrekturen nie überschreiben
    try:
        corrected_pages = {
            row[0]
            for row in main_db.execute(
                "SELECT DISTINCT page_nr FROM source_matrikula_entries "
                "WHERE book_id=? AND corrected_by='human'",
                (book_id,),
            ).fetchall()
        }
    except Exception:
        corrected_pages = set()
    if corrected_pages:
        print(f"  {len(corrected_pages)} manuell korrigierte Seiten werden übersprungen")

    scanned = 0
    new_entries = 0

    for page_nr in page_range:
        if page_nr in done_pages:
            continue
        if page_nr in corrected_pages:
            continue

        print(f"    Seite {page_nr:4d}/{total_pages} ", end="", flush=True)

        arch_file = _archive_path(archive_dir, book_id, page_nr)

        # Bild holen: erst lokales Archiv, dann Matricula
        if arch_file.exists():
            image_bytes = arch_file.read_bytes()
            image_url   = str(arch_file)
            print("📁 ", end="", flush=True)
        else:
            if pw_page is None:
                print("⚠ kein Bild (kein Browser und kein Archiv)")
                continue
            # Seite 1 wurde bereits für _detect_page_count geladen — Screenshot
            # direkt machen ohne erneutes goto (Netzwerk sparen).
            if page_nr == 1 and not retranscribe:
                image_url, image_bytes = _capture_current_page(pw_page, book_url, 1)
            else:
                image_url, image_bytes = _load_page_image(pw_page, book_url, page_nr, pause)
            if image_bytes is not None:
                # Archivieren
                arch_file.parent.mkdir(parents=True, exist_ok=True)
                arch_file.write_bytes(image_bytes)
                print("💾 ", end="", flush=True)

        if image_bytes is None:
            print("⚠ kein Bild")
            with parish_db:
                parish_db.execute(
                    """INSERT OR REPLACE INTO matricula_page_scans
                       (book_id, page_nr, image_url, image_path, status, scanned_at, error_msg)
                       VALUES (?,?,?,?,'error',datetime('now'),'kein Bild')""",
                    (book_id, page_nr, image_url or "", ""),
                )
            continue

        # Claude Vision
        entries = _transcribe_page(image_bytes, book_type, dry_run)
        count   = _save_entries(main_db, book_id, page_nr, book_type, entries)

        print(f"→ {count:3d} Einträge")

        with parish_db:
            parish_db.execute(
                """INSERT OR REPLACE INTO matricula_page_scans
                   (book_id, page_nr, image_url, image_path, status, entry_count, scanned_at)
                   VALUES (?,?,?,?,'done',?,datetime('now'))""",
                (book_id, page_nr, image_url or "", str(arch_file), count),
            )

        scanned     += 1
        new_entries += count
        time.sleep(pause * 0.5)

    return scanned, new_entries


def _detect_page_count(page) -> int | None:
    """
    Liest die Gesamtseitenanzahl aus dem Matricula-Viewer.
    URL-Schema: .../D1_001_1/?pg=1  → Viewer zeigt z.B. "1 / 248"
    """
    # Direkt aus DOM — Matricula rendert die Seitenzahl in einem
    # Pagination-Element (Input-Feld oder Text-Span)
    try:
        result = page.evaluate("""
        () => {
            // Input[max] — häufigste Form
            const inp = document.querySelector('input[max]');
            if (inp && inp.max) return parseInt(inp.max);
            // Span/div mit "X / Y"-Format
            const all = document.body.innerText;
            const m = all.match(/\\b(\\d+)\\s*\\/\\s*(\\d+)\\b/);
            if (m) return parseInt(m[2]);
            // Anzahl ?pg=-Links (Thumbnailleiste)
            const pgs = document.querySelectorAll('a[href*="?pg="]');
            if (pgs.length > 1) return pgs.length;
            return null;
        }
        """)
        if result:
            return int(result)
    except Exception:
        pass
    return None


def _capture_current_page(
    page,
    book_url: str,
    page_nr: int,
) -> tuple[str | None, bytes | None]:
    """
    Fängt das Bild der *bereits geladenen* Viewer-Seite ab — kein erneutes goto.
    Wird für Seite 1 verwendet, die schon für _detect_page_count geladen wurde.
    """
    page_url = f"{book_url.rstrip('/')}/?pg={page_nr}"
    # Letztes großes Bild aus dem Cache versuchen (Request API)
    try:
        # Das Viewer-Bild ist oft in der OpenSeadragon-Canvas — Screenshot reicht
        viewer_el = (
            page.query_selector(".openseadragon-container")
            or page.query_selector("#viewer")
            or page.query_selector("[class*=viewer]")
            or page.query_selector("canvas")
        )
        if viewer_el:
            screenshot = viewer_el.screenshot(type="jpeg", quality=90)
        else:
            screenshot = page.screenshot(type="jpeg", quality=90, full_page=False)
        return page_url, screenshot
    except Exception as e:
        print(f"[Screenshot-Fehler: {e}] ", end="")
    return None, None


def _load_page_image(
    page,
    book_url: str,
    page_nr: int,
    pause: float,
) -> tuple[str | None, bytes | None]:
    """
    Lädt Seite page_nr aus dem Matricula-Viewer und gibt (image_url, image_bytes) zurück.

    Matricula URL-Schema: .../D1_001_1/?pg=1
    Strategie:
      1. ?pg=N laden, Bild-Response aus Netzwerk abfangen
      2. Fallback: Screenshot des Viewer-Bereichs (für Kachel-Viewer)
    """
    captured: list[str] = []

    def on_response(resp):
        url = resp.url
        # Große Bilder aus dem Matricula-Media-Server abfangen
        if resp.status != 200:
            return
        ct = resp.headers.get("content-type", "")
        is_image = ct.startswith("image/") or any(
            url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")
        )
        if not is_image:
            return
        try:
            size = int(resp.headers.get("content-length", "0"))
        except ValueError:
            size = 0
        # >30 KB → Kirchenbuch-Seite, kein Icon/Thumbnail
        if size == 0 or size > 30_000:
            captured.append(url)

    page.on("response", on_response)

    # Matricula-Seite direkt per ?pg=N aufrufen
    page_url = f"{book_url.rstrip('/')}/?pg={page_nr}"
    try:
        page.goto(page_url, wait_until="networkidle", timeout=25_000)
    except Exception:
        page.goto(page_url, wait_until="domcontentloaded", timeout=25_000)
    time.sleep(pause * 0.7)

    page.remove_listener("response", on_response)

    # Bestes Bild auswählen: letzter großer Response = aktuelle Seite
    image_url = captured[-1] if captured else None

    if image_url:
        try:
            resp = page.request.get(image_url, timeout=30_000)
            if resp.ok:
                return image_url, resp.body()
        except Exception as e:
            print(f"[Download {e}] ", end="")

    # Fallback: Screenshot des sichtbaren Viewer-Bereichs
    # (für Kachel-Viewer / OpenSeadragon wo kein einzelnes Bild-Request kommt)
    try:
        viewer_el = (
            page.query_selector(".openseadragon-container")
            or page.query_selector("#viewer")
            or page.query_selector("[class*=viewer]")
            or page.query_selector("canvas")
        )
        if viewer_el:
            screenshot = viewer_el.screenshot(type="jpeg", quality=90)
        else:
            screenshot = page.screenshot(type="jpeg", quality=90, full_page=False)
        print("[Screenshot] ", end="", flush=True)
        return page_url, screenshot
    except Exception as e:
        print(f"[Screenshot-Fehler: {e}] ", end="")

    return None, None


# ── Haupt-Scan ─────────────────────────────────────────────────────────────────

def scan_kirchspiel(
    parish_id: str,
    book_type_filter: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    headless: bool = True,
    pause: float = DEFAULT_PAUSE,
    dry_run: bool = False,
    archive_dir: Path = DEFAULT_ARCHIVE,
    retranscribe: bool = False,
) -> dict:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # noqa
    except ImportError:
        print("Playwright nicht installiert:\n"
              "  pip install playwright && playwright install chromium")
        sys.exit(1)

    parish_db = _open_parish_db()
    main_db   = _open_main_db()

    # Pfarrei-Auflösung mit Disambiguierung
    try:
        from tools.fetch_matricula_books import _resolve_parishes  # type: ignore[import]
    except ImportError:
        sys.path.insert(0, str(ROOT / "ancestry"))
        from tools.fetch_matricula_books import _resolve_parishes  # type: ignore[import]

    resolved = _resolve_parishes(parish_db, parish_id)
    if not resolved:
        sys.exit(1)
    if len(resolved) > 1:
        # _resolve_parishes hat schon eine Liste ausgegeben und exit(1) aufgerufen
        sys.exit(1)
    parish = resolved[0]
    # Kanonische parish_id für alle weiteren Abfragen
    parish_id = parish["id"]  # z.B. "deutschland/osnabrueck/ostercappeln-st-lambertus"

    print(f"Kirchspiel: {parish['name']} ({parish_id})")
    if dry_run:
        print("MODUS: dry-run (kein Claude-API-Call)")

    # Bücher laden
    conditions = ["parish_id = ?"]
    params: list = [parish_id]
    if book_type_filter:
        conditions.append("book_type = ?")
        params.append(book_type_filter)
    if year_from:
        conditions.append("(year_to IS NULL OR year_to >= ?)")
        params.append(year_from)
    if year_to:
        conditions.append("(year_from IS NULL OR year_from <= ?)")
        params.append(year_to)

    books = parish_db.execute(
        f"SELECT * FROM kirchenbuecher WHERE {' AND '.join(conditions)} ORDER BY year_from",
        params,
    ).fetchall()

    if not books:
        print(f"⚠ Keine Kirchenbücher für '{parish_id}' in der DB.")
        print("  Bitte zuerst fetch_matricula_books.py ausführen.")
        sys.exit(1)

    archive_dir.mkdir(parents=True, exist_ok=True)
    print(f"Bild-Archiv: {archive_dir}")
    if retranscribe:
        print("MODUS: Re-Transkription (lokale Bilder, kein Web-Zugriff)")
    print(f"{len(books)} Kirchenbücher zu verarbeiten:\n")
    for b in books:
        done = parish_db.execute(
            "SELECT COUNT(*) FROM matricula_page_scans WHERE book_id=? AND status='done'",
            (b["book_id"],),
        ).fetchone()[0]
        print(f"  {b['book_id']:<50} {b['book_type']:<12} "
              f"{b['year_from'] or '?'}–{b['year_to'] or '?'}  "
              f"({done} Seiten fertig)")

    total_scanned = 0
    total_entries = 0

    if retranscribe:
        # Kein Browser nötig — alle Bilder kommen aus dem Archiv
        for book in books:
            scanned, entries = _scan_book(
                book, parish_db, main_db, None, pause, dry_run,
                archive_dir=archive_dir, retranscribe=True,
            )
            total_scanned += scanned
            total_entries += entries
    else:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=CHROME_PATH,
                headless=headless,
                args=["--ignore-certificate-errors"],
            )
            ctx = browser.new_context(
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                ),
                locale="de-DE",
            )
            pw_page = ctx.new_page()

            for book in books:
                scanned, entries = _scan_book(
                    book, parish_db, main_db, pw_page, pause, dry_run,
                    archive_dir=archive_dir,
                )
                total_scanned += scanned
                total_entries += entries

            browser.close()

    result = {
        "parish_id":    parish_id,
        "books":        len(books),
        "pages_scanned": total_scanned,
        "entries_new":   total_entries,
    }

    print(f"\n{'='*60}")
    print(f"Fertig: {parish['name']}")
    print(f"  {len(books)} Bücher  |  {total_scanned} Seiten gescannt  "
          f"|  {total_entries} neue Einträge")
    return result


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Matricula-Kirchspiel komplett scannen und transkribieren"
    )
    ap.add_argument("--parish",    required=True,
                    help="Pfarrei-Slug (z.B. ostercappeln)")
    ap.add_argument("--book-type", default=None,
                    choices=["Taufe", "Heirat", "Tod", "Konfirmation"],
                    help="Nur diesen Buchtyp scannen")
    ap.add_argument("--year-from", type=int, default=None,
                    help="Nur Bücher ab diesem Jahr")
    ap.add_argument("--year-to",   type=int, default=None,
                    help="Nur Bücher bis zu diesem Jahr")
    ap.add_argument("--visible",   action="store_true",
                    help="Browser sichtbar anzeigen")
    ap.add_argument("--pause",     type=float, default=DEFAULT_PAUSE,
                    help=f"Wartezeit zwischen Seiten in Sekunden (default: {DEFAULT_PAUSE})")
    ap.add_argument("--dry-run",     action="store_true",
                    help="Keine Claude-API-Calls – nur Seiten-Navigation testen")
    ap.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE),
                    help=f"Verzeichnis für Bild-Archiv (default: {DEFAULT_ARCHIVE})")
    ap.add_argument("--retranscribe", action="store_true",
                    help="Nur Re-Transkription: lokale Bilder neu durch Claude schicken, "
                         "kein Web-Zugriff auf Matricula")
    args = ap.parse_args()

    scan_kirchspiel(
        parish_id=args.parish,
        book_type_filter=args.book_type,
        year_from=args.year_from,
        year_to=args.year_to,
        headless=not args.visible,
        pause=args.pause,
        dry_run=args.dry_run,
        archive_dir=Path(args.archive_dir),
        retranscribe=args.retranscribe,
    )
