#!/usr/bin/env python3
"""
Matricula-Pfarreiscraper – Bistum Osnabrück

URL-Schema: https://data.matricula-online.eu/de/deutschland/osnabrueck/<slug>/

Scrapt alle Pfarreien des Bistums Osnabrück und speichert:
  - Pfarreiname, Gründungsjahr
  - Abpfarrungen (mit Jahreszahl: wann abgepfarrt)
  - Ortsteile / Bauerschaften des Kirchspiels
  - Elter-Pfarrei-Verlinkung

Ausgabe:
  ancestry/tools/matricula_parishes.db   (SQLite)
  ancestry/tools/matricula_parishes.json (Ort → Pfarrei-Lookup für Viewer)

Start:
    python scrape_matricula_osnabrueck.py
    python scrape_matricula_osnabrueck.py --visible   # Browser sichtbar
    python scrape_matricula_osnabrueck.py --pause 2.0 # langsamer scrapen

Benötigt:
    pip install playwright
    playwright install chromium
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time

ROOT      = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH   = os.path.join(ROOT, "ancestry", "tools", "matricula_parishes.db")
JSON_PATH = os.path.join(ROOT, "ancestry", "tools", "matricula_parishes.json")

# Bistums-Übersichtsseite (listet alle Pfarreien)
DIOCESE_URL = "https://data.matricula-online.eu/de/deutschland/osnabrueck/"

# Regulärausdrücke für strukturierte Felder
_ABPFARR_LINE = re.compile(
    r"(\d{4})\s+(.+)",          # "1667 Bohmte"  oder  "13. Jh. Venne"
)
_JH_YEAR = re.compile(r"(\d+)\.\s*Jh\b")   # "13. Jh." → ca. 1250

_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20\d{2})\b")


def _jh_to_year(text: str) -> int | None:
    """'13. Jh.' → 1250  (Mitte des Jahrhunderts)."""
    m = _JH_YEAR.search(text)
    if m:
        return (int(m.group(1)) - 1) * 100 + 50
    m = _YEAR_RE.search(text)
    return int(m.group()) if m else None


def _norm_village(v: str) -> str:
    return v.strip().rstrip(".,;")


# ── Datenbank ─────────────────────────────────────────────────────────────────

def _init_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS parishes (
        id            TEXT PRIMARY KEY,   -- URL-Slug
        name          TEXT NOT NULL,
        confession    TEXT DEFAULT 'kath',
        founded_year  INTEGER,            -- Gründung / Ersterwähnung
        url           TEXT DEFAULT '',
        scraped_at    TEXT DEFAULT (datetime('now'))
    );

    -- Abpfarrungen: wann wurde welche Tochterkirche abgepfarrt?
    CREATE TABLE IF NOT EXISTS abpfarrungen (
        parent_id     TEXT NOT NULL,      -- Mutterpfarrei
        child_name    TEXT NOT NULL,      -- Name der Tochter (Freitext)
        child_id      TEXT DEFAULT '',    -- aufgelöste ID (zweiter Pass)
        year          INTEGER,            -- Jahr der Abpfarrung
        PRIMARY KEY (parent_id, child_name)
    );

    -- Ortsteile / Bauerschaften pro Kirchspiel
    CREATE TABLE IF NOT EXISTS parish_villages (
        parish_id     TEXT NOT NULL,
        village       TEXT NOT NULL,
        PRIMARY KEY (parish_id, village)
    );
    """)
    return db


# ── Pfarrei-Seite parsen ──────────────────────────────────────────────────────

def _parse_parish_page(page) -> dict:
    """
    Liest strukturierte Felder von einer Pfarrei-Detailseite.
    Erwartet Abschnitte wie:
      Gründung:          um 1200 …
      Abpfarrungen:      1667 Bohmte / 1492 Hunteburg
      Ortsteile:         Arenshorst, Driehausen, …
    """
    result = {
        "founded_text": "",
        "founded_year": None,
        "abpfarrungen": [],   # list of {"name": str, "year": int|None}
        "villages":     [],
    }

    # Versuche, den Seitentext in Abschnitte zu zerlegen
    # Matricula rendert Infos als <dt>/<dd> oder als strukturierte Paragraphen
    full_text = page.inner_text("body")

    # ── Abschnitt-Extraktion via Regex ─────────────────────────────────────
    def _section(label: str) -> str:
        """Extrahiert den Text nach einem Label bis zum nächsten Label."""
        pattern = re.compile(
            rf"{re.escape(label)}\s*:?\s*\n(.*?)(?=\n[A-ZÄÖÜ][a-zäöü]{{3,}}[:\n]|\Z)",
            re.S)
        m = pattern.search(full_text)
        return m.group(1).strip() if m else ""

    # Gründung
    gr = _section("Gründung") or _section("Ersterwähnung") or _section("Errichtung")
    if gr:
        result["founded_text"] = gr.split("\n")[0].strip()
        result["founded_year"] = _jh_to_year(gr)

    # Abpfarrungen – jede Zeile hat Format "JAHR Name" oder "JH. Name"
    abpf_block = _section("Abpfarrungen")
    if abpf_block:
        for line in abpf_block.splitlines():
            line = line.strip()
            if not line:
                continue
            # "1667 Bohmte" oder "13. Jh. Venne"
            year = _jh_to_year(line)
            # Name = alles nach der Jahresangabe
            name_part = re.sub(r"^(\d{4}|\d+\.\s*Jh\.?)\s*", "", line).strip()
            name_part = _norm_village(name_part)
            if name_part:
                result["abpfarrungen"].append({
                    "name": name_part,
                    "year": year,
                })

    # Ortsteile des Kirchspiels
    ort_block = (_section("Ortsteile des Kirchspiels")
                 or _section("Ortsteile")
                 or _section("Zugehörige Orte"))
    if ort_block:
        # Kommagetrennte oder zeilengetrennte Liste
        raw_villages = re.split(r"[,;\n]+", ort_block)
        result["villages"] = [
            _norm_village(v) for v in raw_villages
            if _norm_village(v) and len(_norm_village(v)) > 1
        ]

    return result


# ── Haupt-Scraping ────────────────────────────────────────────────────────────

def scrape(headless: bool = True, pause: float = 1.5):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("Playwright nicht installiert:\n"
              "  pip install playwright && playwright install chromium")
        sys.exit(1)

    db = _init_db(DB_PATH)
    parishes: list[dict] = []

    print(f"Öffne Bistums-Übersicht: {DIOCESE_URL}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            locale="de-DE",
        )
        page = ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "de-DE,de;q=0.9"})

        # ── Übersichtsseite laden ─────────────────────────────────────────
        try:
            page.goto(DIOCESE_URL, wait_until="networkidle", timeout=30_000)
        except PWTimeout:
            page.goto(DIOCESE_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(pause)

        # ── Pfarrei-Links sammeln ─────────────────────────────────────────
        # URLs haben Format: .../de/deutschland/osnabrueck/<slug>/
        pattern = re.compile(r"/de/deutschland/osnabrueck/([^/]+)/?$")
        link_elems = page.query_selector_all("a[href]")
        parish_links: list[dict] = []
        seen_slugs: set[str] = set()

        for el in link_elems:
            href = el.get_attribute("href") or ""
            m = pattern.search(href)
            if not m:
                continue
            slug = m.group(1)
            if slug in seen_slugs or slug == "":
                continue
            seen_slugs.add(slug)
            name = (el.inner_text() or "").strip() or slug.replace("-", " ").title()
            full_url = (f"https://data.matricula-online.eu{href}"
                        if href.startswith("/") else href)
            parish_links.append({"slug": slug, "name": name, "url": full_url})

        print(f"  {len(parish_links)} Pfarreien auf der Übersichtsseite gefunden.\n")

        if not parish_links:
            print("⚠ Keine Pfarrei-Links gefunden. Versuche alternativen Einstieg …")
            # Fallback: Seite als Text dumpen für Diagnose
            print(page.inner_text("body")[:3000])
            browser.close()
            return []

        # ── Detailseiten abrufen ──────────────────────────────────────────
        for i, entry in enumerate(parish_links, 1):
            slug = entry["slug"]
            name = entry["name"]
            url  = entry["url"]
            print(f"  [{i:3d}/{len(parish_links)}] {name:<45}", end=" ", flush=True)

            parsed = {"founded_text": "", "founded_year": None,
                      "abpfarrungen": [], "villages": []}
            try:
                try:
                    page.goto(url, wait_until="networkidle", timeout=20_000)
                except PWTimeout:
                    page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                time.sleep(pause * 0.5)

                # Verfeinerten Namen aus H1/H2 lesen
                for hdr_sel in ("h1", "h2", ".page-title"):
                    el = page.query_selector(hdr_sel)
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
                "id":           slug,
                "name":         name,
                "confession":   "kath",   # Diözesanarchiv Osnabrück
                "founded_year": parsed["founded_year"],
                "url":          url,
                "abpfarrungen": parsed["abpfarrungen"],
                "villages":     parsed["villages"],
            })

            time.sleep(pause * 0.3)

        browser.close()

    # ── Abpfarrungs-IDs auflösen (zweiter Pass) ───────────────────────────────
    slug_by_name: dict[str, str] = {}
    for p in parishes:
        slug_by_name[p["name"].lower()] = p["id"]
        # Auch kurze Namen ohne "St." etc.
        short = re.sub(r"^(st\.|sankt|heilig\w*)\s+", "", p["name"].lower())
        slug_by_name[short] = p["id"]

    for p in parishes:
        for abp in p["abpfarrungen"]:
            raw = abp["name"].lower().strip()
            # Direkter Match
            if raw in slug_by_name:
                abp["child_id"] = slug_by_name[raw]
                continue
            # Partial-Match
            best = ""
            for n, sid in slug_by_name.items():
                if raw in n or n in raw:
                    if not best or len(n) > len(best):
                        best = sid
            abp["child_id"] = best

    # ── In DB schreiben ───────────────────────────────────────────────────────
    with db:
        db.execute("DELETE FROM parishes")
        db.execute("DELETE FROM abpfarrungen")
        db.execute("DELETE FROM parish_villages")

        for p in parishes:
            db.execute("""
                INSERT OR REPLACE INTO parishes
                (id, name, confession, founded_year, url)
                VALUES (:id, :name, :confession, :founded_year, :url)
            """, {k: p[k] for k in ("id","name","confession","founded_year","url")})

            for abp in p["abpfarrungen"]:
                db.execute("""
                    INSERT OR IGNORE INTO abpfarrungen
                    (parent_id, child_name, child_id, year)
                    VALUES (?, ?, ?, ?)
                """, (p["id"], abp["name"],
                      abp.get("child_id", ""), abp.get("year")))

            for v in p["villages"]:
                if v:
                    db.execute("""
                        INSERT OR IGNORE INTO parish_villages (parish_id, village)
                        VALUES (?, ?)
                    """, (p["id"], v))

    # ── JSON-Lookup für Viewer exportieren ────────────────────────────────────
    # Format: { "ortsname_lowercase": {parish_id, parish, confession, parent} }
    lookup: dict = {}
    for p in parishes:
        # Parent-Pfarrei (= erstes Abpfarrungs-Ziel von oben, umgekehrt betrachtet)
        # Für den Lookup brauchen wir: für jede Pfarrei, wer ist ihr Mutter?
        # Das ermitteln wir aus der abpfarrungen-Tabelle: wenn B abgepfarrt wurde
        # von A, dann ist A der parent von B.
        pass  # wird unten via DB gelöst

    # parent_map: child_id → parent_id
    parent_map: dict[str, str] = {}
    for p in parishes:
        for abp in p["abpfarrungen"]:
            cid = abp.get("child_id", "")
            if cid:
                parent_map[cid] = p["id"]

    for p in parishes:
        entry = {
            "parish_id":  p["id"],
            "parish":     p["name"],
            "confession": p["confession"],
            "parent_id":  parent_map.get(p["id"], ""),
            "founded":    p["founded_year"],
        }
        # Pfarrort selbst
        loc_key = p["name"].lower().strip()
        lookup.setdefault(loc_key, entry)
        # Alle Ortsteile
        for v in p["villages"]:
            vk = v.lower().strip()
            if vk:
                lookup.setdefault(vk, entry)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(lookup, f, ensure_ascii=False, indent=2)

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    total_villages = sum(len(p["villages"]) for p in parishes)
    total_abpfarr  = sum(len(p["abpfarrungen"]) for p in parishes)
    linked_abpfarr = sum(
        1 for p in parishes for abp in p["abpfarrungen"] if abp.get("child_id")
    )

    print(f"\n✅  {len(parishes)} Pfarreien")
    print(f"    {total_abpfarr} Abpfarrungen ({linked_abpfarr} verlinkt)")
    print(f"    {total_villages} Ortsteile/Bauerschaften")
    print(f"    {len(lookup)} Einträge im Ort→Pfarrei-Lookup")
    print(f"\n    DB:   {DB_PATH}")
    print(f"    JSON: {JSON_PATH}")

    # ── Hierarchie ausgeben ───────────────────────────────────────────────────
    print("\n── Pfarrei-Baum (Mutterpfarreien mit Abpfarrungen) ──────────────────")
    roots = [p for p in parishes if p["id"] not in parent_map]
    for root in sorted(roots, key=lambda x: x["name"])[:25]:
        fy = f" ({root['founded_year']})" if root["founded_year"] else ""
        print(f"  {root['name']}{fy}")
        for abp in sorted(root["abpfarrungen"], key=lambda a: a.get("year") or 9999):
            yr  = str(abp["year"]) if abp.get("year") else "?"
            cid = abp.get("child_id", "")
            linked = " ✓" if cid else ""
            print(f"    └─ {yr:>5}  {abp['name']}{linked}")

    return parishes


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Matricula Bistum Osnabrück scrapen")
    ap.add_argument("--visible", action="store_true",
                    help="Browser sichtbar anzeigen (nicht headless)")
    ap.add_argument("--pause", type=float, default=1.5,
                    help="Wartezeit zwischen Seiten in Sekunden (default: 1.5)")
    args = ap.parse_args()
    scrape(headless=not args.visible, pause=args.pause)
