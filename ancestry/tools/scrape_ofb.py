#!/usr/bin/env python3
"""
CompGen Online-Ortsfamilienbücher (OFB) Katalog-Scraper.

Quelle:
    https://ofb.genealogy.net/

Das CompGen-Projekt „Online-Ortsfamilienbücher" stellt digitalisierte
deutsche Ortsfamilienbücher (Town Family Books) frei online bereit. Der
Index listet alle verfügbaren OFBs alphabetisch, gruppiert nach Bundesland
(Nord → Süd, plus deutschsprachige Gemeinden im Ausland). Jedes einzelne
OFB liegt unter einer URL der Form

    https://ofb.genealogy.net/<slug>/

z. B.  https://ofb.genealogy.net/eichhorn/
       https://ofb.genealogy.net/sollnitz/
       https://ofb.genealogy.net/papendorf_brietzig/

Dieser Scraper erstellt ausschließlich einen *Katalog* (Name, Ort, Region,
URL, optional GOV-ID) — kein Personendownload.

────────────────────────────────────────────────────────────────────────────
DATENSICHERHEIT (verbindlich)
────────────────────────────────────────────────────────────────────────────
Dieser Scraper schreibt AUSSCHLIESSLICH in seine eigene, separate SQLite-Datei

    ancestry/tools/ofb_books.db

und exportiert

    ancestry/tools/ofb_books.json

Er öffnet, beschreibt oder LÖSCHT NIEMALS die Hauptdatenbank
(ancestry_dna.db) oder irgendeine andere DB. Es gibt keinerlei DELETE/DROP.
Die voll bestückte Hauptdatenbank des Nutzers (insbesondere die
webtrees-Daten) bleibt unangetastet.

Schreibmodell: idempotent. Alle Schreibvorgänge nutzen INSERT OR REPLACE auf
dem Primärschlüssel (slug), sodass wiederholte Läufe vorhandene Einträge an
Ort und Stelle aktualisieren statt Daten zu verlieren. Der JSON-Export liest
ALLE Zeilen aus der DB, ein Re-Run verliert also nie zuvor gescrapte Bücher.

Ausgabe:
    ancestry/tools/ofb_books.db    (SQLite, eigene DB)
    ancestry/tools/ofb_books.json  (Ort → Bücher, für externe_quellen.py)

Verwendung:
    python -m ancestry.tools.scrape_ofb
    python -m ancestry.tools.scrape_ofb --visible
    python -m ancestry.tools.scrape_ofb --pause 2.0

Benötigt:
    pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import re
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

ROOT      = Path(__file__).resolve().parent.parent.parent
DB_PATH   = ROOT / "ancestry" / "tools" / "ofb_books.db"
JSON_PATH = ROOT / "ancestry" / "tools" / "ofb_books.json"

OFB_BASE  = "https://ofb.genealogy.net"
OFB_INDEX = "https://ofb.genealogy.net/"

# Slugs, die zur Navigation / Infrastruktur gehören und keine OFBs sind.
_NON_BOOK_SLUGS = {
    "", "index", "impressum", "datenschutz", "kontakt", "info", "hilfe",
    "help", "faq", "suche", "search", "login", "register", "registrierung",
    "namelist", "namen", "about", "ueber", "über", "sitemap", "rss",
    "statistik", "stats", "karte", "map", "neu", "neue", "news",
    "ortsfamilienbuecher", "ortsfamilienbuch", "ofb", "compgen",
}

# Region-Überschrift erkennen (Bundesländer / Länder, Nord → Süd gelistet).
_REGION_HINTS = (
    "schleswig", "holstein", "mecklenburg", "vorpommern", "hamburg",
    "bremen", "niedersachsen", "sachsen-anhalt", "brandenburg", "berlin",
    "nordrhein", "westfalen", "hessen", "thüringen", "thuringen", "sachsen",
    "rheinland", "pfalz", "saarland", "baden", "württemberg", "wurttemberg",
    "bayern", "ungarn", "rumänien", "rumanien", "polen", "frankreich",
    "österreich", "osterreich", "schweiz", "tschechien", "russland",
    "ausland", "deutschland",
)

# OFB-Buch-Slug aus einer URL/Href extrahieren:  …/<slug>/  oder  ?ofb=<slug>
_HREF_SLUG  = re.compile(r"(?:^|/)([a-z0-9][a-z0-9_\-]*)/?$", re.I)
_QUERY_SLUG = re.compile(r"[?&]ofb=([a-z0-9][a-z0-9_\-]*)", re.I)
_GOV_ID     = re.compile(r"[?&]gov=([A-Z0-9_]+)", re.I)


# ── Datenbank (eigene DB, niemals die Haupt-DB) ───────────────────────────────

def _init_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS ofb_books (
        id          TEXT PRIMARY KEY,                  -- url-slug, z.B. papendorf_brietzig
        name        TEXT NOT NULL,                     -- Anzeigename des OFB
        place       TEXT,                              -- Ort(e)
        region      TEXT,                              -- Bundesland / Land
        url         TEXT NOT NULL,                     -- https://ofb.genealogy.net/<slug>/
        gov_id      TEXT DEFAULT '',                   -- optionale GOV-Kennung
        scraped_at  TEXT DEFAULT (datetime('now'))
    );
    """)
    return db


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _norm(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "")).strip().strip("·•-–—,;").strip()


def _slug_from_href(href: str) -> str:
    """Liefert den OFB-Slug aus einem Link, sonst ''."""
    href = (href or "").strip()
    if not href:
        return ""
    mq = _QUERY_SLUG.search(href)
    if mq:
        return mq.group(1).lower()
    # Querystring/Fragment entfernen
    clean = href.split("?", 1)[0].split("#", 1)[0]
    # Nur Links innerhalb von ofb.genealogy.net berücksichtigen
    if clean.startswith("http"):
        if "ofb.genealogy.net" not in clean:
            return ""
        clean = re.sub(r"^https?://[^/]*ofb\.genealogy\.net", "", clean, flags=re.I)
    m = _HREF_SLUG.search(clean)
    if not m:
        return ""
    return m.group(1).lower()


def _gov_from_href(href: str) -> str:
    m = _GOV_ID.search(href or "")
    return m.group(1) if m else ""


def _looks_like_region(text: str) -> str:
    """Gibt die Region zurück, wenn der Text wie eine Bundesland-Überschrift aussieht."""
    t = (text or "").strip().lower()
    if not t or len(t) > 40:
        return ""
    for hint in _REGION_HINTS:
        if hint in t:
            return _norm(text)
    return ""


# ── Index scrapen ─────────────────────────────────────────────────────────────

def scrape_ofb(page, db: sqlite3.Connection, pause: float = 1.5) -> list[dict]:
    """
    Lädt den OFB-Index und entdeckt die einzelnen Buch-Links
    (https://ofb.genealogy.net/<slug>/), extrahiert Name + Ort + Region.

    Schreibt jedes Buch mit INSERT OR REPLACE (idempotent) in die eigene DB.
    Gibt die Liste der gescrapten Bücher zurück. Fail-soft: leere Liste, wenn
    der Index nicht erreichbar ist oder keine Buch-Links enthält.
    """
    print(f"Lade OFB-Index: {OFB_INDEX}")
    try:
        page.goto(OFB_INDEX, wait_until="networkidle", timeout=30_000)
    except Exception:
        try:
            page.goto(OFB_INDEX, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"⚠ OFB-Index nicht erreichbar: {e}")
            return []
    time.sleep(pause)

    # Aktuelle Region anhand vorausgehender Überschriften mitführen.
    # Wir laufen das DOM in Dokumentreihenfolge ab: Überschriften setzen die
    # Region, Links erzeugen Buch-Einträge.
    current_region = ""
    seen: set[str] = set()
    books: list[dict] = []

    try:
        nodes = page.query_selector_all(
            "h1, h2, h3, h4, th, strong, a[href]")
    except Exception as e:
        print(f"⚠ Konnte Index-DOM nicht lesen: {e}")
        return []

    for el in nodes:
        try:
            tag = (el.evaluate("e => e.tagName") or "").lower()
        except Exception:
            tag = ""

        if tag != "a":
            # Überschrift / Region-Kandidat
            try:
                txt = el.inner_text()
            except Exception:
                txt = ""
            region = _looks_like_region(txt)
            if region:
                current_region = region
            continue

        # Anker
        try:
            href = el.get_attribute("href") or ""
            label = _norm(el.inner_text() or "")
        except Exception:
            continue

        slug = _slug_from_href(href)
        if not slug or slug in _NON_BOOK_SLUGS:
            continue
        if slug in seen:
            continue

        # Plausibilitätsprüfung: echte OFB-Buchlinks sind interne Slugs auf
        # ofb.genealogy.net (relativ oder absolut). Externe Links ignorieren.
        href_l = href.lower()
        if href_l.startswith("http") and "ofb.genealogy.net" not in href_l:
            continue
        # Mehrteilige Pfade (…/x/y/…) sind keine Buch-Roots.
        path_only = href_l.split("?", 1)[0].split("#", 1)[0]
        path_only = re.sub(r"^https?://[^/]*ofb\.genealogy\.net", "", path_only)
        if path_only.strip("/").count("/") > 0 and "ofb=" not in href_l:
            continue

        seen.add(slug)
        name  = label or slug.replace("_", " ").replace("-", " ").title()
        place = label.split(",")[0].strip() if label else \
            slug.replace("_", " ").replace("-", " ").title()
        url    = f"{OFB_BASE}/{slug}/"
        gov_id = _gov_from_href(href)

        books.append({
            "id": slug,
            "name": name,
            "place": place,
            "region": current_region,
            "url": url,
            "gov_id": gov_id,
        })

    if not books:
        print("⚠ Keine OFB-Buchlinks im Index gefunden — "
              "Seitenstruktur hat sich evtl. geändert.")
        return []

    # Idempotent in die eigene DB schreiben (kein DELETE!).
    with db:
        for b in books:
            db.execute(
                "INSERT OR REPLACE INTO ofb_books "
                "(id, name, place, region, url, gov_id) "
                "VALUES (:id, :name, :place, :region, :url, :gov_id)",
                b)

    print(f"  {len(books)} OFB-Bücher im Index gefunden und gespeichert.")
    return books


# ── JSON-Lookup exportieren (alle Bücher aus der DB) ──────────────────────────

def export_json(db: sqlite3.Connection, path: Path):
    """
    Erzeugt Ort → [Bücher]-Lookup für externe_quellen.py.

    Liest ALLE Zeilen aus der DB (nicht nur den letzten Lauf), sodass ein
    Re-Run nie zuvor gescrapte Bücher verliert. Schlüssel ist der
    klein­geschriebene Ortsname (mirror von matricula_parishes.json).
    """
    lookup: dict[str, list[dict]] = {}
    n = 0
    for row in db.execute(
            "SELECT id, name, place, url FROM ofb_books ORDER BY place, name"):
        place = (row["place"] or row["name"] or "").lower().strip()
        if not place:
            continue
        entry = {"id": row["id"], "name": row["name"], "url": row["url"]}
        bucket = lookup.setdefault(place, [])
        if not any(e["id"] == entry["id"] for e in bucket):
            bucket.append(entry)
            n += 1
    path.write_text(json.dumps(lookup, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"JSON-Lookup exportiert: {path}  "
          f"({n} Bücher, {len(lookup)} Orte)")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="CompGen Online-Ortsfamilienbücher (OFB) Katalog-Scraper")
    ap.add_argument("--visible", action="store_true",
                    help="Browser sichtbar lassen")
    ap.add_argument("--pause", type=float, default=1.5,
                    help="Wartezeit zwischen Seiten (Sek., default: 1.5)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright nicht installiert:\n"
              "  pip install playwright && playwright install chromium")
        sys.exit(1)

    # Eigene DB anlegen — niemals die Haupt-DB anfassen.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = _init_db(DB_PATH)

    books: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.visible)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            locale="de-DE",
        )
        page = ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "de-DE,de;q=0.9"})
        books = scrape_ofb(page, db, pause=args.pause)
        browser.close()

    if not books:
        print("⚠ Keine OFB-Bücher gescrapt — Index nicht erreichbar oder "
              "Struktur geändert. Bestehende DB bleibt unverändert.")
        export_json(db, JSON_PATH)   # vorhandene DB-Inhalte trotzdem exportieren
        db.close()
        sys.exit(1)

    # Per-Region-Zusammenfassung.
    print(f"\n{len(books)} OFB-Bücher in DB gespeichert.")
    regions: dict[str, int] = {}
    for b in books:
        regions[b["region"] or "(ohne Region)"] = \
            regions.get(b["region"] or "(ohne Region)", 0) + 1
    for region in sorted(regions):
        print(f"  {region:<40}  {regions[region]} Bücher")

    export_json(db, JSON_PATH)
    db.close()
    print(f"\nFertig. {len(books)} OFB-Bücher total gescrapt.")


# ── Katalog-Abfrage (für externe_quellen.py) ─────────────────────────────────

def get_books(db_path: Path | None = None) -> list[dict]:
    """
    Lädt den OFB-Katalog aus der eigenen DB.
    Gibt leere Liste zurück, wenn die DB-Datei nicht existiert (fail-soft).
    """
    p = Path(db_path) if db_path else DB_PATH
    if not p.exists():
        return []
    db = sqlite3.connect(str(p))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT id, name, place, region, url, gov_id "
            "FROM ofb_books ORDER BY region, place, name"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()


def get_book_for_place(place: str) -> dict | None:
    """
    Gibt das erste OFB-Buch zurück, dessen Ort/Name zum gesuchten Ort passt.
    Gibt None zurück, wenn nichts passt oder die DB nicht existiert (fail-soft).
    """
    if not place:
        return None
    needle = place.lower().strip()
    if not needle:
        return None
    for b in get_books():
        hay_place = (b.get("place") or "").lower().strip()
        hay_name  = (b.get("name") or "").lower().strip()
        if needle == hay_place or needle == hay_name:
            return b
        if hay_place and (needle in hay_place or hay_place in needle):
            return b
    return None


if __name__ == "__main__":
    main()
