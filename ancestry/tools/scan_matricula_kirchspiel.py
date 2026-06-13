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

# Kölner Phonetik aus tasks.names (bereits im Projekt vorhanden)
try:
    from tasks.names import koelner_phonetik as _kp, _levenshtein as _lev
except ImportError:
    _kp = _lev = None  # type: ignore[assignment]

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
    # Migration: alle Spalten nachrüsten die in älteren DB-Versionen fehlen könnten
    for _sql in [
        "ALTER TABLE matricula_page_scans ADD COLUMN image_url   TEXT    DEFAULT ''",
        "ALTER TABLE matricula_page_scans ADD COLUMN image_path  TEXT    DEFAULT ''",
        "ALTER TABLE matricula_page_scans ADD COLUMN entry_count INTEGER DEFAULT 0",
        "ALTER TABLE matricula_page_scans ADD COLUMN scanned_at  TEXT    DEFAULT ''",
        "ALTER TABLE matricula_page_scans ADD COLUMN error_msg   TEXT    DEFAULT ''",
        "ALTER TABLE kirchenbuecher       ADD COLUMN total_pages INTEGER",
    ]:
        try:
            db.execute(_sql)
            db.commit()
        except Exception:
            pass
    return db


def _open_main_db():
    """Öffnet die Haupt-ancestry.db für source_matrikula_entries."""
    from ancestry.paths import DB_PATH as main_db_path
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
        corrected_by TEXT DEFAULT '',
        corrected_at TEXT DEFAULT '',
        created_at   TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_sme_book  ON source_matrikula_entries(book_id);
    CREATE INDEX IF NOT EXISTS idx_sme_year  ON source_matrikula_entries(event_year);
    CREATE INDEX IF NOT EXISTS idx_sme_name  ON source_matrikula_entries(person_name);

    CREATE TABLE IF NOT EXISTS name_index (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id    INTEGER NOT NULL,
        book_id     TEXT NOT NULL,
        page_nr     INTEGER NOT NULL,
        name_raw    TEXT NOT NULL,
        name_norm   TEXT NOT NULL,
        koeln_code  TEXT NOT NULL,
        name_role   TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ni_koeln ON name_index(koeln_code);
    CREATE INDEX IF NOT EXISTS idx_ni_book  ON name_index(book_id);
    CREATE INDEX IF NOT EXISTS idx_ni_role  ON name_index(name_role);
    """)
    return db


# ── OCR-Backends (umschaltbar via MATRICULA_OCR_BACKEND) ────────────────────────
# claude    → Claude Vision: liefert STRUKTURIERTE Einträge (kostenpflichtig).
# tesseract → lokal/gratis: nur ROHTEXT (gut für GEDRUCKTE Register, schwach bei
#             Handschrift). lang via MATRICULA_TESSERACT_LANG (default deu+frak).
# kraken    → lokal/gratis: HTR für Handschrift; braucht ein Modell
#             (MATRICULA_KRAKEN_MODEL=pfad.mlmodel). Liefert ebenfalls ROHTEXT.
OCR_BACKEND = os.environ.get("MATRICULA_OCR_BACKEND", "claude").strip().lower()


def _transcribe_page(image_bytes: bytes, book_type: str, dry_run: bool) -> list[dict]:
    """Dispatcher: transkribiert eine Seite über das gewählte OCR-Backend."""
    if dry_run:
        print(f"  [dry-run: kein OCR-Call · backend={OCR_BACKEND}]")
        return []
    if OCR_BACKEND == "tesseract":
        return _transcribe_tesseract(image_bytes, book_type)
    if OCR_BACKEND == "kraken":
        return _transcribe_kraken(image_bytes, book_type)
    return _transcribe_claude(image_bytes, book_type)


def _raw_entry(book_type: str, text: str, engine: str) -> list[dict]:
    """Verpackt rohen OCR-Text als (un-strukturierten) Eintrag. Das Strukturieren
    in Person/Datum/Eltern erfolgt separat (Lexikon-gestützt) oder manuell."""
    text = (text or "").strip()
    if not text:
        return []
    return [{
        "entry_type": book_type,
        "person_name": "", "person2_name": "",
        "father_name": "", "mother_name": "",
        "event_date": "", "village": "",
        "notes": text,
        "raw_json": json.dumps({"ocr_engine": engine, "raw_text": text},
                               ensure_ascii=False),
    }]


def _transcribe_tesseract(image_bytes: bytes, book_type: str) -> list[dict]:
    try:
        import io
        import pytesseract
        from PIL import Image
    except ImportError:
        print("  ⚠ tesseract-Backend braucht: pip install pytesseract pillow "
              "(+ Tesseract-Binary)")
        return []
    lang = os.environ.get("MATRICULA_TESSERACT_LANG", "deu+frak")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img, lang=lang)
    except Exception as e:
        print(f"  ⚠ Tesseract-Fehler: {e}")
        return []
    return _raw_entry(book_type, text, "tesseract")


def _transcribe_kraken(image_bytes: bytes, book_type: str) -> list[dict]:
    model_path = os.environ.get("MATRICULA_KRAKEN_MODEL", "")
    if not model_path or not os.path.exists(model_path):
        print("  ⚠ kraken-Backend: MATRICULA_KRAKEN_MODEL=<pfad.mlmodel> setzen "
              "(z. B. ein deutsches Kurrent-Modell).")
        return []
    try:
        import io
        from PIL import Image
        from kraken import binarization, pageseg, rpred
        from kraken.lib import models as kraken_models
    except ImportError:
        print("  ⚠ kraken-Backend braucht: pip install kraken pillow")
        return []
    try:
        im = Image.open(io.BytesIO(image_bytes))
        bw = binarization.nlbin(im)
        seg = pageseg.segment(bw)
        model = kraken_models.load_any(model_path)
        lines = [rec.prediction for rec in rpred.rpred(model, bw, seg)]
        text = "\n".join(lines)
    except Exception as e:
        print(f"  ⚠ Kraken-Fehler: {e}")
        return []
    return _raw_entry(book_type, text, "kraken")


# ── Claude Vision ──────────────────────────────────────────────────────────────

def _transcribe_claude(image_bytes: bytes, book_type: str) -> list[dict]:
    """Schickt ein Seiten-Bild an Claude Vision und gibt strukturierte Einträge zurück."""
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


# ── Name-Index ─────────────────────────────────────────────────────────────────

def _index_names(
    db: sqlite3.Connection,
    entry_id: int,
    book_id: str,
    page_nr: int,
    names: list[tuple[str, str]],  # [(name_raw, role), …]
) -> None:
    """Schreibt Name → Kölner-Code Einträge in name_index."""
    if _kp is None:
        return
    for name_raw, role in names:
        if not name_raw or not name_raw.strip():
            continue
        db.execute(
            """INSERT INTO name_index
               (entry_id, book_id, page_nr, name_raw, name_norm, koeln_code, name_role)
               VALUES (?,?,?,?,?,?,?)""",
            (entry_id, book_id, page_nr,
             name_raw,
             name_raw.lower().strip(),
             _kp(name_raw),
             role),
        )


# ── Einträge speichern ─────────────────────────────────────────────────────────

def _save_entries(
    main_db: sqlite3.Connection,
    book_id: str,
    page_nr: int,
    book_type: str,
    entries: list[dict],
) -> int:
    """Speichert transkribierte Einträge in source_matrikula_entries + name_index."""
    if not entries:
        return 0

    with main_db:
        # Vorherige name_index-Einträge dieser Seite löschen (Idempotenz)
        try:
            main_db.execute(
                "DELETE FROM name_index WHERE book_id=? AND page_nr=?",
                (book_id, page_nr),
            )
        except Exception:
            pass

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

            cur = main_db.execute(
                """
                INSERT INTO source_matrikula_entries
                    (book_id, page_nr, entry_type, event_date, event_year,
                     person_name, person2_name, father_name, mother_name,
                     village, notes, raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    book_id, page_nr, book_type,
                    e.get("datum", ""), year,
                    person, person2, father, mother,
                    e.get("ort", "") or e.get("braeutigam_ort", ""),
                    e.get("anmerkungen", ""),
                    json.dumps(e, ensure_ascii=False),
                ),
            )
            _index_names(main_db, cur.lastrowid, book_id, page_nr, [
                (person,  "person"),
                (person2, "person2"),
                (father,  "father"),
                (mother,  "mother"),
            ])
    return len(entries)


# ── Playwright-Seiten-Scanner ──────────────────────────────────────────────────

def _archive_path(
    archive_dir: Path,
    book_id: str,
    page_nr: int,
    label: str | None = None,
) -> Path:
    """
    Kanonischer Archiv-Pfad für eine Buchseite.

    Ohne Label:  <archive_dir>/ostercappeln-st-lambertus/TauBu-1697-1820/0001.jpg
    Mit Label:   <archive_dir>/ostercappeln-st-lambertus/TauBu-1697-1820/
                     ostercappeln-st-lambertus_TauBu-1697-1820_tauf-1628_006.jpg

    Nur die letzten zwei Segmente werden als Verzeichnis verwendet.
    """
    parts       = book_id.split("/")
    parish_slug = parts[-2] if len(parts) >= 2 else book_id
    book_slug   = parts[-1]
    if label:
        fname = f"{parish_slug}_{book_slug}_{label}.jpg"
    else:
        fname = f"{page_nr:04d}.jpg"
    return archive_dir / parish_slug / book_slug / fname


def _count_up(start: int = 1):
    """Unendlicher Zähler: 1, 2, 3, … (Fallback wenn URL-Extraktion fehlschlägt)"""
    n = start
    while True:
        yield n
        n += 1


def _extract_book_image_urls(
    page, book_url: str, pause: float
) -> list[tuple[str, str]]:
    """
    Lädt die Buchhauptseite einmal und liest alle Bild-URLs + Labels aus dem
    MatriculaDocView-JavaScript-Array heraus.

    Gibt [(image_url, label), ...] zurück, z.B.:
        ("https://img.data.matricula-online.eu/image/aHR0...", "tauf-1628_006")
    """
    try:
        page.goto(book_url.rstrip("/") + "/", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(max(0.3, pause * 0.3))
    except Exception as e:
        print(f"  ⚠ Buchseite laden: {e}")
        return []
    try:
        result = page.evaluate("""
        () => {
            for (const s of document.querySelectorAll('script')) {
                const src = s.textContent || '';
                if (!src.includes('MatriculaDocView')) continue;
                const pathM   = src.match(/"path"\\s*:\\s*"([^"]+)"/);
                const filesM  = src.match(/"files"\\s*:\\s*(\\[[\\s\\S]*?\\])/);
                const labelsM = src.match(/"labels"\\s*:\\s*(\\[[\\s\\S]*?\\])/);
                if (pathM && filesM) {
                    try {
                        const files  = JSON.parse(filesM[1]);
                        const labels = labelsM ? JSON.parse(labelsM[1]) : [];
                        if (Array.isArray(files) && files.length > 0)
                            return files.map((f, i) => [pathM[1] + f, labels[i] || String(i + 1)]);
                    } catch(e) {}
                }
            }
            return [];
        }
        """)
        pairs = list(result or [])
        return [(u, lbl) for u, lbl in pairs if u.startswith("http")]
    except Exception as e:
        print(f"  ⚠ Bild-URL-Extraktion: {e}")
    return []


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
    if not book_url:
        book_url = f"{BASE_URL}/de/{book_id}/"

    print(f"\n  Buch: {book_id}  [{book_type}  {book['year_from'] or '?'}–{book['year_to'] or '?'}]")
    print(f"  URL:  {book_url}")

    # ── Seiten bestimmen ─────────────────────────────────────────────────────
    direct_items: list[tuple[str, str]] = []  # (image_url, label) aus Viewer-JS
    archived_by_nr: dict[int, Path]     = {}  # page_nr → Datei (nur retranscribe)

    if retranscribe:
        parts        = book_id.split("/")
        parish_slug  = parts[-2] if len(parts) >= 2 else book_id
        book_slug    = parts[-1]
        book_archive = archive_dir / parish_slug / book_slug
        archived = sorted(book_archive.glob("*.jpg")) if book_archive.exists() else []
        if not archived:
            print("  ⚠ Keine archivierten Bilder — überspringe")
            return 0, 0
        print(f"  {len(archived)} archivierte Seiten (Re-Transkription)")
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
        # enumerate statt int(stem) — funktioniert auch mit Label-basierten Dateinamen
        archived_by_nr = {i: p for i, p in enumerate(archived, 1)}
        page_range: list[int] | None = list(archived_by_nr.keys())
    else:
        done_pages = {
            row[0]
            for row in parish_db.execute(
                "SELECT page_nr FROM matricula_page_scans WHERE book_id=? AND status='done'",
                (book_id,),
            ).fetchall()
        }

        # Alle Bild-URLs + Labels einmalig aus dem Viewer-Skript lesen
        if pw_page is not None:
            direct_items = _extract_book_image_urls(pw_page, book_url, pause)

        if direct_items:
            page_range = list(range(1, len(direct_items) + 1))
            print(f"  {len(direct_items)} Seiten · {len(done_pages)} bereits fertig")
            with parish_db:
                parish_db.execute(
                    "UPDATE kirchenbuecher SET total_pages=? WHERE book_id=?",
                    (len(direct_items), book_id),
                )
        else:
            print("  URL-Extraktion fehlgeschlagen — iteriere ?pg=1, ?pg=2, …")
            print(f"  {len(done_pages)} bereits fertig")
            page_range = None   # offene Iteration als Fallback

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
    last_good_page = 0

    iter_pages = page_range if page_range is not None else _count_up()
    consec_empty = 0

    for page_nr in iter_pages:
        if page_nr in done_pages:
            last_good_page = max(last_good_page, page_nr)
            continue
        if page_nr in corrected_pages:
            continue

        print(f"    Seite {page_nr:4d} ", end="", flush=True)

        # Archivpfad: retranscribe → tatsächliche Datei, direkt → Label-Name, sonst → nr
        if archived_by_nr:
            arch_file = archived_by_nr[page_nr]
        elif direct_items:
            _, _lbl = direct_items[page_nr - 1]
            arch_file = _archive_path(archive_dir, book_id, page_nr, label=_lbl)
        else:
            arch_file = _archive_path(archive_dir, book_id, page_nr)

        image_url: str | None = None
        image_bytes: bytes | None = None

        # Bild holen: erst lokales Archiv, dann via Browser-Navigation
        if arch_file.exists():
            image_bytes = arch_file.read_bytes()
            image_url   = str(arch_file)
            print("📁 ", end="", flush=True)
            consec_empty = 0
        elif pw_page is None:
            print("⚠ kein Browser und kein Archiv — überspringe")
            if page_range is None:
                break
            continue
        else:
            # Browser navigiert zu ?pg=N — Bild wird aus dem Netzwerk abgefangen.
            # CDN blockiert direkte requests.get()-Aufrufe (403); der Browser
            # selbst lädt das Bild erfolgreich, weil er die richtigen Cookies sendet.
            image_url, image_bytes = _load_page_image(pw_page, book_url, page_nr, pause)
            if image_bytes is not None:
                arch_file.parent.mkdir(parents=True, exist_ok=True)
                arch_file.write_bytes(image_bytes)
                print("💾 ", end="", flush=True)
                consec_empty = 0
            else:
                consec_empty += 1
                if page_range is None and consec_empty >= 2:
                    print("⚠ kein Bild — Ende des Buchs")
                    break

        if image_bytes is None:
            print("⚠ kein Bild")
            with parish_db:
                parish_db.execute(
                    """INSERT OR REPLACE INTO matricula_page_scans
                       (book_id, page_nr, image_url, image_path, status, scanned_at, error_msg)
                       VALUES (?, ?, ?, ?, 'error', datetime('now'), ?)""",
                    (book_id, page_nr, image_url or "", "", "kein Bild"),
                )
            continue

        last_good_page = max(last_good_page, page_nr)

        # OCR
        entries = _transcribe_page(image_bytes, book_type, dry_run)
        if OCR_BACKEND in ("tesseract", "kraken") and entries:
            raw = "\n\n".join(e.get("notes", "") for e in entries if e.get("notes"))
            if raw.strip():
                try:
                    arch_file.with_suffix(".txt").write_text(raw, encoding="utf-8")
                    print(f"  📝 {arch_file.with_suffix('.txt').name}")
                except Exception as _e:
                    print(f"  ⚠ .txt-Schreiben: {_e}")
        count = _save_entries(main_db, book_id, page_nr, book_type, entries)
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

    # Bei offener Iteration (Fallback): ermittelte Seitenanzahl in DB speichern
    if page_range is None and last_good_page > 0:
        with parish_db:
            parish_db.execute(
                "UPDATE kirchenbuecher SET total_pages=? WHERE book_id=?",
                (last_good_page, book_id),
            )
        print(f"  → {last_good_page} Seiten gesamt (in DB gespeichert)")

    return scanned, new_entries


def _probe_page_count(page, book_url: str, pause: float, max_probe: int = 9999) -> int | None:
    """Fallback: probiert Seiten 1,2,4,8,… (binäre Suche) bis kein Bild mehr lädt."""
    base = book_url.rstrip("/")

    def _has_image(pg: int) -> bool:
        url = f"{base}/?pg={pg}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            time.sleep(max(0.3, pause * 0.3))
            result = page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('img[src*="image"], canvas, .openseadragon-container');
                return imgs.length > 0;
            }
            """)
            return bool(result)
        except Exception:
            return False

    if not _has_image(1):
        return None
    # Exponential scan: finde eine obere Schranke
    hi = 1
    while hi < max_probe and _has_image(hi * 2):
        hi *= 2
    if hi >= max_probe:
        return max_probe
    lo = hi
    hi = hi * 2
    # Binäre Suche zwischen lo und hi
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if _has_image(mid):
            lo = mid
        else:
            hi = mid
    # Zurück auf Seite 1 navigieren
    try:
        page.goto(f"{base}/?pg=1", wait_until="domcontentloaded", timeout=15_000)
        time.sleep(pause)
    except Exception:
        pass
    print(f"  (Probe-Methode: {lo} Seiten)")
    return lo


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
            // Span/div mit "X / Y" oder "X von Y"-Format (deutsch/englisch)
            const all = document.body.innerText;
            let m = all.match(/\\b(\\d+)\\s*\\/\\s*(\\d+)\\b/);
            if (m) return parseInt(m[2]);
            m = all.match(/\\b\\d+\\s+von\\s+(\\d+)\\b/i);
            if (m) return parseInt(m[1]);
            m = all.match(/\\bof\\s+(\\d+)\\b/i);
            if (m) return parseInt(m[1]);
            // Anzahl ?pg=-Links (Thumbnailleiste)
            const pgs = document.querySelectorAll('a[href*="?pg="]');
            if (pgs.length > 1) return pgs.length;
            // Pagination-Buttons mit data-page
            const btns = document.querySelectorAll('[data-page]');
            if (btns.length > 1) {
                const nums = Array.from(btns)
                    .map(b => parseInt(b.getAttribute('data-page')))
                    .filter(n => !isNaN(n));
                if (nums.length) return Math.max(...nums);
            }
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
    from ancestry.tools.fetch_matricula_books import _resolve_parishes

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
            # CHROME_PATH ist ein Linux-/CI-Default. Nur verwenden, wenn die
            # Datei wirklich existiert; sonst Playwrights eigenes (z. B. unter
            # Windows installiertes) Chromium nutzen.
            launch_kwargs = dict(headless=headless,
                                 args=["--ignore-certificate-errors"])
            if os.path.exists(CHROME_PATH):
                launch_kwargs["executable_path"] = CHROME_PATH
            browser = pw.chromium.launch(**launch_kwargs)
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
