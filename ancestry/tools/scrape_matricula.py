#!/usr/bin/env python3
"""
Universeller Matricula-Pfarreiscraper — alle Bistümer/Archive.

Entdeckt verfügbare Bistümer ab der Bestandsübersicht:
  https://data.matricula-online.eu/de/bestande/

Scrapt Pfarreien eines Bistums (Übersichtsseite + Detailseiten) und schreibt
Ergebnisse in die gemeinsame matricula_parishes.db.  Bestehende Daten anderer
Bistümer bleiben erhalten (diözesen-selektiver DELETE).

Verwendung:
    python -m ancestry.tools.scrape_matricula                        # Bistümer auflisten
    python -m ancestry.tools.scrape_matricula --diocese osnabrueck   # Bistum Osnabrück
    python -m ancestry.tools.scrape_matricula --diocese muenster     # Bistum Münster
    python -m ancestry.tools.scrape_matricula --diocese paderborn    # Bistum Paderborn
    python -m ancestry.tools.scrape_matricula --all                  # alle Bistümer
    python -m ancestry.tools.scrape_matricula --visible              # Browser sichtbar
    python -m ancestry.tools.scrape_matricula --pause 2.0            # langsamer scrapen

Benötigt:
    pip install playwright && playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import os
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
DB_PATH   = ROOT / "ancestry" / "tools" / "matricula_parishes.db"
JSON_PATH = ROOT / "ancestry" / "tools" / "matricula_parishes.json"

BESTANDE_URL  = "https://data.matricula-online.eu/de/bestande/"
MATRICULA_BASE = "https://data.matricula-online.eu"

_ABPFARR_LINE = re.compile(r"(\d{4})\s+(.+)")
_JH_YEAR      = re.compile(r"(\d+)\.\s*Jh\b")
_YEAR_RE      = re.compile(r"\b(1[0-9]{3}|20\d{2})\b")


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _jh_to_year(text: str) -> int | None:
    m = _JH_YEAR.search(text)
    if m:
        return (int(m.group(1)) - 1) * 100 + 50
    m = _YEAR_RE.search(text)
    return int(m.group()) if m else None


def _norm(v: str) -> str:
    return v.strip().rstrip(".,;")


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _init_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS dioceses (
        path        TEXT PRIMARY KEY,   -- z.B. deutschland/osnabrueck
        slug        TEXT NOT NULL,      -- osnabrueck
        country     TEXT NOT NULL,      -- deutschland
        name        TEXT NOT NULL DEFAULT '',
        url         TEXT NOT NULL DEFAULT '',
        scraped_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS parishes (
        id            TEXT PRIMARY KEY,
        slug          TEXT NOT NULL DEFAULT '',
        diocese       TEXT NOT NULL DEFAULT '',
        name          TEXT NOT NULL,
        confession    TEXT DEFAULT 'kath',
        founded_year  INTEGER,
        url           TEXT DEFAULT '',
        scraped_at    TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS abpfarrungen (
        parent_id   TEXT NOT NULL,
        child_name  TEXT NOT NULL,
        child_id    TEXT DEFAULT '',
        year        INTEGER,
        PRIMARY KEY (parent_id, child_name)
    );

    CREATE TABLE IF NOT EXISTS parish_villages (
        parish_id  TEXT NOT NULL,
        village    TEXT NOT NULL,
        PRIMARY KEY (parish_id, village)
    );
    """)
    return db


# ── Bestandsübersicht — alle Diözesen entdecken ───────────────────────────────

_NAV_SLUGS = frozenset(
    ("suche", "bestande", "info", "kontakt", "impressum", "datenschutz",
     "login", "logout", "register", "account", "hilfe", "faq", "news",
     "de", "en", "hu", "pl", "sk", "cz", "hr", "at", "si")
)


def discover_dioceses(page) -> list[dict]:
    """Liest alle verfügbaren Diözesen/Archive von der Bestandsübersicht.

    Probiert zuerst die REST-API (JSON), fällt bei Fehler auf HTML-Scraping zurück.
    Wartet bis zu 8 Sekunden auf dynamisch gerenderte Links.
    """
    # ── Versuch 1: JSON-API ──────────────────────────────────────────────────
    api_url = "https://data.matricula-online.eu/api/v1/dioceses/?format=json&limit=500"
    try:
        import json as _json
        page.goto(api_url, wait_until="domcontentloaded", timeout=15_000)
        body = page.inner_text("body") or ""
        data = _json.loads(body)
        results = data.get("results") or (data if isinstance(data, list) else [])
        dioceses: list[dict] = []
        seen: set[str] = set()
        for item in results:
            # Felder können je nach API-Version variieren
            slug    = (item.get("slug") or item.get("identifier") or "").strip()
            country = (item.get("country") or item.get("land") or "").strip().lower()
            name    = (item.get("name") or item.get("bezeichnung") or slug).strip()
            url     = item.get("url") or item.get("link") or ""
            if not slug or not country:
                continue
            path = f"{country}/{slug}"
            if path in seen:
                continue
            seen.add(path)
            if not url:
                url = f"{MATRICULA_BASE}/de/{path}/"
            dioceses.append({
                "path": path, "country": country, "slug": slug,
                "name": name, "url": url,
            })
        if dioceses:
            return sorted(dioceses, key=lambda d: (d["country"], d["slug"]))
    except Exception:
        pass

    # ── Versuch 2: HTML-Scraping der Bestandsübersicht ───────────────────────
    try:
        page.goto(BESTANDE_URL, wait_until="networkidle", timeout=30_000)
    except Exception:
        page.goto(BESTANDE_URL, wait_until="domcontentloaded", timeout=30_000)

    # Mehrere Selektoren versuchen (Seite ist JS-gerendert, Klasse kann variieren)
    _candidates = [
        "div.list-group a[href]",
        "a.list-group-item[href]",
        ".col-lg-5 a[href]",
        "a[href*='/de/deutschland/']",
        "a[href*='/de/']",
    ]
    for _sel in _candidates:
        try:
            page.wait_for_selector(_sel, timeout=8_000)
            break
        except Exception:
            continue
    else:
        time.sleep(4.0)   # letzter Ausweg

    # Seite scrollen → Lazy-Load triggern
    try:
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.0)
    except Exception:
        pass

    pattern = re.compile(r"/de/([^/]+)/([^/?#]+)/?$")

    # Diagnose-Ausgabe: hilft bei Debugging auf dem Zielsystem
    _all = page.query_selector_all("a[href]")
    _matching = [el for el in _all
                 if pattern.search(el.get_attribute("href") or "")]
    print(f"  [Diagnose] {len(_all)} Links auf Seite, "
          f"{len(_matching)} passen /de/…/…/-Muster.", flush=True)

    seen2: set[str] = set()
    dioceses2: list[dict] = []
    # Breit suchen: alle Links auf der Seite, nicht nur div.list-group
    for el in page.query_selector_all("a[href]"):
        href = el.get_attribute("href") or ""
        m = pattern.search(href)
        if not m:
            continue
        country, slug = m.group(1), m.group(2)
        if slug in _NAV_SLUGS or country in _NAV_SLUGS:
            continue
        path = f"{country}/{slug}"
        if path in seen2:
            continue
        seen2.add(path)
        name = (el.inner_text() or "").strip() or slug.replace("-", " ").title()
        full_url = (MATRICULA_BASE + href) if href.startswith("/") else href
        dioceses2.append({
            "path": path, "country": country, "slug": slug,
            "name": name, "url": full_url,
        })

    return sorted(dioceses2, key=lambda d: (d["country"], d["slug"]))


# ── Detailseite einer Pfarrei parsen ──────────────────────────────────────────

def _parse_parish_page(page) -> dict:
    result = {
        "founded_text": "", "founded_year": None,
        "abpfarrungen": [], "villages": [],
    }
    full_text = page.inner_text("body")

    def _section(label: str) -> str:
        pat = re.compile(
            rf"{re.escape(label)}\s*:?\s*\n(.*?)(?=\n[A-ZÄÖÜ][a-zäöü]{{3,}}[:\n]|\Z)",
            re.S)
        m = pat.search(full_text)
        return m.group(1).strip() if m else ""

    gr = _section("Gründung") or _section("Ersterwähnung") or _section("Errichtung")
    if gr:
        result["founded_text"] = gr.split("\n")[0].strip()
        result["founded_year"] = _jh_to_year(gr)

    abpf_block = _section("Abpfarrungen")
    if abpf_block:
        for line in abpf_block.splitlines():
            line = line.strip()
            if not line:
                continue
            year     = _jh_to_year(line)
            name_part = re.sub(r"^(\d{4}|\d+\.\s*Jh\.?)\s*", "", line).strip()
            name_part = _norm(name_part)
            if name_part:
                result["abpfarrungen"].append({"name": name_part, "year": year})

    ort_block = (_section("Ortsteile des Kirchspiels")
                 or _section("Ortsteile")
                 or _section("Zugehörige Orte"))
    if ort_block:
        result["villages"] = [
            _norm(v) for v in re.split(r"[,;\n]+", ort_block)
            if _norm(v) and len(_norm(v)) > 1
        ]
    return result


# ── Ein Bistum scrapen ────────────────────────────────────────────────────────

def scrape_diocese(page, db: sqlite3.Connection,
                   diocese: dict, pause: float = 1.5) -> list[dict]:
    """Scrapt alle Pfarreien eines Bistums. Gibt Liste der gescrapten Pfarreien zurück."""
    diocese_path = diocese["path"]
    diocese_url  = diocese["url"]
    confession   = "evang" if any(k in diocese_url.lower()
                                  for k in ("evangelisch", "evang", "protestant")) else "kath"

    print(f"\n{'─'*60}")
    print(f"Bistum: {diocese['name']}  ({diocese_path})")
    print(f"URL:    {diocese_url}")
    print(f"{'─'*60}")

    try:
        page.goto(diocese_url, wait_until="networkidle", timeout=30_000)
    except Exception:
        page.goto(diocese_url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(pause)

    # Pfarrei-Links auf der Übersichtsseite sammeln
    url_pattern = re.compile(re.escape(f"/de/{diocese_path}/") + r"([^/]+)/?$")
    seen_slugs: set[str] = set()
    parish_links: list[dict] = []

    for el in page.query_selector_all("a[href]"):
        href = el.get_attribute("href") or ""
        m    = url_pattern.search(href)
        if not m:
            continue
        slug = m.group(1)
        if slug in seen_slugs or not slug:
            continue
        seen_slugs.add(slug)
        name     = (el.inner_text() or "").strip() or slug.replace("-", " ").title()
        full_url = (MATRICULA_BASE + href) if href.startswith("/") else href
        parish_links.append({
            "slug": slug,
            "parish_id": f"{diocese_path}/{slug}",
            "name": name,
            "url": full_url,
        })

    print(f"  {len(parish_links)} Pfarreien auf der Übersichtsseite gefunden.")
    if not parish_links:
        print("  ⚠ Keine Pfarrei-Links gefunden — Seite hat evtl. anderes Layout.")
        return []

    parishes: list[dict] = []
    for i, entry in enumerate(parish_links, 1):
        slug = entry["slug"]; parish_id = entry["parish_id"]
        name = entry["name"]; url = entry["url"]
        print(f"  [{i:3d}/{len(parish_links)}] {name:<50}", end=" ", flush=True)

        parsed = {"founded_text": "", "founded_year": None,
                  "abpfarrungen": [], "villages": []}
        try:
            try:
                page.goto(url, wait_until="networkidle", timeout=20_000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            time.sleep(pause * 0.5)

            for hdr in ("h1", "h2", ".page-title"):
                el = page.query_selector(hdr)
                if el:
                    t = (el.inner_text() or "").strip()
                    if t:
                        name = t
                    break

            parsed = _parse_parish_page(page)
            n_ort = len(parsed["villages"])
            n_abp = len(parsed["abpfarrungen"])
            print(f"✓  {n_ort} Orte  {n_abp} Abpfarrungen")
        except Exception as e:
            print(f"⚠ {e}")

        parishes.append({
            "id": parish_id, "slug": slug, "diocese": diocese_path,
            "name": name, "confession": confession,
            "founded_year": parsed["founded_year"], "url": url,
            "abpfarrungen": parsed["abpfarrungen"],
            "villages": parsed["villages"],
        })
        time.sleep(pause * 0.3)

    # Abpfarrungs-IDs auflösen
    id_by_name: dict[str, str] = {}
    for p in parishes:
        id_by_name[p["name"].lower()] = p["id"]
        short = re.sub(r"^(st\.|sankt|heilig\w*)\s+", "", p["name"].lower())
        id_by_name[short] = p["id"]

    for p in parishes:
        for abp in p["abpfarrungen"]:
            raw = abp["name"].lower().strip()
            if raw in id_by_name:
                abp["child_id"] = id_by_name[raw]
                continue
            best = ""
            for n, pid in id_by_name.items():
                if raw in n or n in raw:
                    if not best or len(n) > len(best):
                        best = pid
            abp["child_id"] = best

    # In DB schreiben — nur dieses Bistum ersetzen
    with db:
        db.execute("INSERT OR REPLACE INTO dioceses (path, slug, country, name, url) VALUES (?,?,?,?,?)",
                   (diocese_path, diocese["slug"], diocese["country"],
                    diocese["name"], diocese_url))
        db.execute("DELETE FROM parishes WHERE diocese=?", (diocese_path,))
        db.execute("DELETE FROM abpfarrungen WHERE parent_id LIKE ?", (f"{diocese_path}/%",))
        db.execute("DELETE FROM parish_villages WHERE parish_id LIKE ?", (f"{diocese_path}/%",))

        for p in parishes:
            db.execute(
                "INSERT OR REPLACE INTO parishes "
                "(id, slug, diocese, name, confession, founded_year, url) "
                "VALUES (:id,:slug,:diocese,:name,:confession,:founded_year,:url)",
                {k: p[k] for k in ("id","slug","diocese","name","confession","founded_year","url")})
            for abp in p["abpfarrungen"]:
                db.execute(
                    "INSERT OR IGNORE INTO abpfarrungen (parent_id,child_name,child_id,year) "
                    "VALUES (?,?,?,?)",
                    (p["id"], abp["name"], abp.get("child_id",""), abp.get("year")))
            for v in p["villages"]:
                if v:
                    db.execute(
                        "INSERT OR IGNORE INTO parish_villages (parish_id,village) VALUES (?,?)",
                        (p["id"], v))

    print(f"  → {len(parishes)} Pfarreien in DB gespeichert ({diocese_path})")
    return parishes


# ── JSON-Lookup exportieren (alle Bistümer) ───────────────────────────────────

def export_json(db: sqlite3.Connection, path: Path):
    """Erzeugt Ortsname→Pfarrei-Lookup über alle Bistümer."""
    parent_map: dict[str, str] = {}
    for r in db.execute("SELECT parent_id, child_id FROM abpfarrungen WHERE child_id!=''"):
        parent_map[r[0]] = r[1]   # child → parent

    # Ältere DBs (scrape_matricula_osnabrueck.py) haben keine diocese-Spalte
    has_diocese = any(
        r[1] == "diocese"
        for r in db.execute("PRAGMA table_info(parishes)")
    )
    diocese_col = "p.diocese" if has_diocese else "''"

    lookup: dict = {}
    for row in db.execute(f"""
        SELECT p.id, p.name, {diocese_col}, p.confession,
               pv.village
        FROM parishes p
        LEFT JOIN parish_villages pv ON pv.parish_id = p.id
    """):
        if not row[4]:
            continue
        v_norm = row[4].lower().strip()
        if not v_norm:
            continue
        if v_norm not in lookup:
            lookup[v_norm] = {
                "parish_id": row[0], "parish": row[1],
                "diocese": row[2], "confession": row[3],
                "parent": parent_map.get(row[0], ""),
            }

    path.write_text(json.dumps(lookup, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON-Lookup exportiert: {path}  ({len(lookup)} Ortseinträge)")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Universeller Matricula-Pfarreiscraper (alle Bistümer)")
    ap.add_argument("--diocese", metavar="SLUG",
                    help="Bistum-Slug, z.B. osnabrueck, muenster, paderborn")
    ap.add_argument("--all", dest="all_dioceses", action="store_true",
                    help="Alle verfügbaren Bistümer scrapen")
    ap.add_argument("--visible", action="store_true",
                    help="Browser sichtbar lassen")
    ap.add_argument("--pause", type=float, default=1.5,
                    help="Wartezeit zwischen Seiten (Sek., default: 1.5)")
    args = ap.parse_args()

    try:
        from playwright.sync_api import TimeoutError as PWTimeout  # noqa: F401
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
        page.set_extra_http_headers({"Accept-Language": "de-DE,de;q=0.9"})

        print(f"Lade Bestandsübersicht: {BESTANDE_URL}")
        dioceses = discover_dioceses(page)
        print(f"  {len(dioceses)} Bistümer/Archive entdeckt.")

        if not args.diocese and not args.all_dioceses:
            # Nur auflisten
            print("\nVerfügbare Bistümer (--diocese <slug> oder --all):\n")
            for d in dioceses:
                print(f"  {d['slug']:<35}  {d['name']:<50}  {d['path']}")
            browser.close()
            return

        # Ziel-Bistümer bestimmen
        if args.all_dioceses:
            targets = dioceses
        else:
            slug = args.diocese.lower().strip()
            targets = [d for d in dioceses if d["slug"] == slug]
            if not targets:
                # Teilübereinstimmung versuchen
                targets = [d for d in dioceses if slug in d["slug"] or slug in d["path"]]
            if not targets:
                print(f"Bistum '{slug}' nicht gefunden. Verfügbar:")
                for d in dioceses:
                    print(f"  {d['slug']}")
                browser.close()
                sys.exit(1)

        all_parishes: list[dict] = []
        for diocese in targets:
            parishes = scrape_diocese(page, db, diocese, pause=args.pause)
            all_parishes.extend(parishes)

        browser.close()

    export_json(db, JSON_PATH)
    db.close()
    print(f"\nFertig. {len(all_parishes)} Pfarreien total gescrapt.")


if __name__ == "__main__":
    main()
