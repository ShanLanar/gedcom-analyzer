#!/usr/bin/env python3
"""
MyHeritage Shared-Matches-Scraper

Lädt für alle MH-Matches ab einem cM-Schwellwert die "Gemeinsame DNA-Matches"-CSV
von jeder Match-Seite herunter und importiert sie in shared_matches.

Voraussetzung:
  • Playwright mit Chromium installiert (pip install playwright && playwright install chromium)
  • Eingeloggter MH-Browser (Session wird über --profile oder manuellen Login gehalten)
  • Die Haupt-Match-Liste als CSV (aus MH → DNA → Matches → Download CSV → All Matches)

Start:
    python fetch_mh_shared_matches.py --csv pfad/zur/match_list.csv
    python fetch_mh_shared_matches.py --csv match_list.csv --min-cm 40 --visible
    python fetch_mh_shared_matches.py --csv match_list.csv --min-cm 50 --limit 100

Argumente:
    --csv       Pfad zur MH Match-List-CSV (Pflicht)
    --min-cm    Nur Matches ab dieser cM-Schwelle verarbeiten (default: 50)
    --limit     Maximale Anzahl zu verarbeitender Matches (default: alle)
    --visible   Browser sichtbar anzeigen
    --pause     Pause zwischen Seiten in Sekunden (default: 2.0)
    --skip-done Matches überspringen, die bereits in shared_matches_fetched sind
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ancestry"))

from core.database import Database as AncestryDatabase
from models.match import SharedMatch


def _parse_cm(val: str) -> float:
    """'3.533,5' oder '255.5' → float."""
    if not val:
        return 0.0
    # MH verwendet manchmal Punkt als Tausender und Komma als Dezimal
    val = val.strip().replace("\xa0", "")
    if "," in val and "." in val:
        # z.B. "3.533,5" → 3533.5
        val = val.replace(".", "").replace(",", ".")
    elif "," in val:
        val = val.replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return 0.0


def _extract_guid(url: str) -> str:
    """Extrahiert die Match-GUID aus einer MH-URL."""
    # https://www.myheritage.com/dna/match/D-AAA-D-BBB  → D-BBB
    parts = url.rstrip("/").split("/")
    last = parts[-1] if parts else ""
    # Format: D-XXXXX-D-YYYYY → zweite GUID
    m = re.search(r"(D-[0-9A-F-]{30,})", last, re.I)
    if m:
        return m.group(1).upper()
    return last


def _load_main_csv(path: str, min_cm: float) -> list[dict]:
    """Liest die MH Match-List-CSV und filtert nach min_cm."""
    matches = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        # Debug: Spalten beim ersten Lauf ausgeben
        if not hasattr(_load_main_csv, "_headers_printed"):
            _load_main_csv._headers_printed = True  # type: ignore[attr-defined]
            print(f"CSV-Spalten: {headers}")
        # Flexible Spaltenerkennung (MH ändert manchmal Sprache/Format)
        cm_col   = next((h for h in headers if "cm" in h.lower() and "shared" in h.lower()), None) \
                or next((h for h in headers if "cM" in h or "cm" in h.lower()), None) \
                or "Shared cM"
        name_col = next((h for h in headers if "name" in h.lower() and "match" in h.lower()), None) \
                or next((h for h in headers if "name" in h.lower()), None) \
                or "Match Name"
        url_col  = next((h for h in headers if "url" in h.lower()), None) or "URL"
        guid_col = next((h for h in headers if "guid" in h.lower()), None) or "GUID"
        for row in reader:
            cm = _parse_cm(row.get(cm_col, "0"))
            if cm < min_cm:
                continue
            url  = (row.get(url_col)  or "").strip()
            guid = (row.get(guid_col) or "").strip()
            if not url and not guid:
                continue
            matches.append({
                "name":  (row.get(name_col) or "").strip(),
                "cm":    cm,
                "guid":  guid,
                "url":   url,
            })
    matches.sort(key=lambda x: x["cm"], reverse=True)
    return matches


def _parse_shared_csv(csv_text: str, test_guid: str,
                      match_guid_a: str, fetched_at: str) -> list[SharedMatch]:
    """Parst eine MH Shared-Matches-CSV in SharedMatch-Objekte."""
    results = []
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            guid_b = row.get("GUID", "").strip()
            if not guid_b:
                continue
            cm_b  = _parse_cm(row.get("Shared cM", "0"))
            cm_ab = _parse_cm(row.get("Shared cM with Match", "0"))
            results.append(SharedMatch(
                test_guid       = test_guid,
                match_guid_a    = match_guid_a,
                match_guid_b    = guid_b,
                display_name_b  = row.get("Match Name", "").strip(),
                shared_cm_b     = cm_b,
                shared_cm_ab    = cm_ab,
                shared_segments_b = 0,
                relationship_b  = row.get("Estimated Relationship", "").strip(),
                has_tree_b      = bool(row.get("Tree Size", "0").strip()
                                       not in ("", "0")),
                fetched_at      = fetched_at,
            ))
    except Exception as e:
        print(f"    ⚠ CSV-Parse-Fehler: {e}")
    return results


def _load_cookie_editor_json(path: str) -> list[dict]:
    """Liest Cookie-Editor-JSON und gibt Playwright-kompatible Cookie-Dicts zurück."""
    import json
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    # Cookie Editor exportiert eine Liste von Dicts mit 'name','value','domain',...
    result = []
    for c in raw:
        cookie = {
            "name":   c.get("name", ""),
            "value":  c.get("value", ""),
            "domain": c.get("domain", ""),
            "path":   c.get("path", "/"),
        }
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if "expirationDate" in c:
            cookie["expires"] = int(c["expirationDate"])
        if "sameSite" in c:
            ss = str(c["sameSite"]).capitalize()
            if ss in ("Strict", "Lax", "None"):
                cookie["sameSite"] = ss
        result.append(cookie)
    return result


def scrape(csv_path: str, min_cm: float = 50.0, limit: int = 0,
           headless: bool = True, pause: float = 2.0, skip_done: bool = True,
           profile_dir: str | None = None, cookies_path: str | None = None):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("Playwright nicht installiert:\n"
              "  pip install playwright && playwright install chromium")
        sys.exit(1)

    db = AncestryDatabase()

    # Test-GUID aus CSV-Dateiname oder DB ermitteln
    # Dateiname: Andreas_Kovermann_D44D71405...  → D-44D71405-...
    test_guid = ""
    fname = os.path.basename(csv_path)
    m = re.search(r"_(D[0-9A-F]{8,})[_\.]", fname, re.I)
    if m:
        raw = m.group(1)
        # D44D71405... → D-44D71405-0D71-...  (bereits mit Bindestrichen in DB)
        # Versuche direkt aus DB zu lesen
        try:
            with db._cursor() as cur:
                row = cur.execute(
                    "SELECT guid FROM dna_kits WHERE is_owner=1 LIMIT 1"
                ).fetchone()
                if row:
                    test_guid = row[0]
        except Exception:
            pass
        if not test_guid:
            # Bindestriche einfügen: D44D71405 0D71 4D2B 91F7 337F3344BD17
            raw = raw.upper().lstrip("D")
            if len(raw) >= 32:
                test_guid = f"D-{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"

    print(f"Test-GUID: {test_guid or '(unbekannt — wird aus URL ermittelt)'}")

    # Bereits verarbeitete Matches laden
    done_guids: set[str] = set()
    if skip_done:
        try:
            with db._cursor() as cur:
                rows = cur.execute(
                    "SELECT match_guid_a FROM shared_matches_fetched WHERE test_guid=?",
                    (test_guid,)
                ).fetchall()
                done_guids = {r[0] for r in rows}
            print(f"{len(done_guids)} Matches bereits verarbeitet (--skip-done aktiv).")
        except Exception:
            pass

    matches = _load_main_csv(csv_path, min_cm)
    if limit:
        matches = matches[:limit]

    to_do = [m for m in matches if m["guid"] not in done_guids]
    print(f"\n{len(matches)} Matches ≥ {min_cm} cM geladen, "
          f"{len(to_do)} noch nicht verarbeitet.\n")

    if not to_do:
        print("Nichts zu tun.")
        return

    total_imported = 0
    with sync_playwright() as pw:
        if profile_dir:
            ctx = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=headless,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                locale="de-DE",
                accept_downloads=True,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            browser = pw.chromium.launch(headless=headless)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                locale="de-DE",
                accept_downloads=True,
            )
            page = ctx.new_page()
        page.set_extra_http_headers({"Accept-Language": "de-DE,de;q=0.9"})

        # ── Cookies aus Cookie-Editor-Export injizieren ───────────────────────
        if cookies_path:
            try:
                cookies = _load_cookie_editor_json(cookies_path)
                ctx.add_cookies(cookies)
                print(f"✓ {len(cookies)} Cookies aus {cookies_path} geladen.")
            except Exception as exc:
                print(f"⚠  Cookie-Datei konnte nicht geladen werden: {exc}")

        # ── Einmal einloggen / Session prüfen ─────────────────────────────────
        print("Öffne MyHeritage — bitte ggf. einloggen …")
        try:
            page.goto("https://www.myheritage.de/dna",
                      wait_until="domcontentloaded", timeout=30_000)
        except PWTimeout:
            pass
        time.sleep(2)

        # Prüfen ob Login-Dialog offen
        if page.query_selector("input[name='username'], input[type='email']"):
            if cookies_path:
                print("\n⚠  Cookies wurden geladen, aber Session ist nicht aktiv.")
                print("   Bitte neue Cookies exportieren (MyHeritage neu einloggen → Cookie Editor → Export).")
                ctx.close()
                return
            print("\n⚠  Nicht eingeloggt! Optionen:")
            print("   1. Cookie Editor in Chrome installieren, auf myheritage.de einloggen,")
            print("      alle Cookies exportieren als JSON → --cookies mh_cookies.json")
            print("   2. Oder: --visible starten und 60s Zeit zum Einloggen")
            if headless:
                ctx.close()
                return
            print("Warte 60s auf Login …")
            time.sleep(60)

        # ── Matches verarbeiten ───────────────────────────────────────────────
        for i, match in enumerate(to_do, 1):
            url      = match["url"]
            guid_a   = match["guid"]
            name     = match["name"]
            cm       = match["cm"]
            fetched  = datetime.now(timezone.utc).isoformat()

            print(f"  [{i:4d}/{len(to_do)}] {name:<40} {cm:7.1f} cM … ",
                  end="", flush=True)

            # Test-GUID aus URL ableiten falls noch unbekannt
            if not test_guid and url:
                parts = url.rstrip("/").split("/")[-1].split("-D-")
                if len(parts) >= 2:
                    raw = parts[0].lstrip("D-").replace("-", "")
                    if len(raw) >= 32:
                        test_guid = (f"D-{raw[:8]}-{raw[8:12]}-"
                                     f"{raw[12:16]}-{raw[16:20]}-{raw[20:32]}")

            shared: list[SharedMatch] = []
            intercepted: list[tuple[str, str]] = []

            try:
                # Netzwerk-Intercept: alle MH-API-Antworten mit Match-Daten abfangen
                def _on_resp(response):
                    try:
                        ru = response.url
                        if response.ok and ("shared" in ru or "dna-match" in ru or
                                            "dna_match" in ru or "relatives" in ru):
                            ct = response.headers.get("content-type", "")
                            if "json" in ct or "csv" in ct:
                                try:
                                    intercepted.append((ru, response.text()))
                                except Exception:
                                    pass
                    except Exception:
                        pass
                page.on("response", _on_resp)

                # Match-Seite laden
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=40_000)
                except PWTimeout:
                    page.goto(url, wait_until="commit", timeout=20_000)
                time.sleep(pause)

                # Scrollen damit MH Shared-Matches lazy-lädt
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(pause * 0.6)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(pause * 0.4)

                page.remove_listener("response", _on_resp)

                # Intercept-Antworten auswerten
                csv_text = None
                import json as _json
                for resp_url, resp_body in intercepted:
                    if not resp_body:
                        continue
                    # JSON-Antwort mit Shared-Matches
                    if resp_body.lstrip().startswith("{") or resp_body.lstrip().startswith("["):
                        try:
                            data = _json.loads(resp_body)
                            items = (data if isinstance(data, list) else
                                     data.get("matches") or data.get("data") or
                                     data.get("results") or data.get("relatives") or [])
                            for item in items:
                                g   = (item.get("guid") or item.get("matchGuid") or
                                       item.get("id") or "").upper()
                                cm_val = float(item.get("sharedDna") or
                                               item.get("sharedCm") or
                                               item.get("shared_dna") or 0)
                                if g and cm_val:
                                    shared.append(SharedMatch(
                                        test_guid=test_guid,
                                        match_guid_a=guid_a,
                                        match_guid_b=g,
                                        display_name_b=str(item.get("displayName") or
                                                           item.get("name") or ""),
                                        shared_cm_b=cm_val,
                                        shared_cm_ab=0.0,
                                        shared_segments_b=int(
                                            item.get("sharedSegments") or 0),
                                        relationship_b=str(
                                            item.get("relationship") or ""),
                                        has_tree_b=bool(item.get("hasTree")),
                                        fetched_at=fetched,
                                    ))
                        except Exception:
                            pass
                        if shared:
                            break
                    # CSV-Antwort
                    elif "\n" in resp_body and "," in resp_body:
                        csv_text = resp_body
                        break

                if csv_text:
                    shared = _parse_shared_csv(csv_text, test_guid, guid_a, fetched)

                # Fallback: JSON-Regex im Seiteninhalt
                if not shared:
                    try:
                        html = page.content()
                        json_matches = re.findall(
                            r'"guid"\s*:\s*"(D-[0-9A-F-]{30,})"[^}]{0,300}'
                            r'"sharedDna"\s*:\s*([\d.]+)',
                            html, re.IGNORECASE | re.DOTALL
                        )
                        for guid_b, cm_str in json_matches:
                            try:
                                shared.append(SharedMatch(
                                    test_guid=test_guid,
                                    match_guid_a=guid_a,
                                    match_guid_b=guid_b.upper(),
                                    display_name_b="",
                                    shared_cm_b=float(cm_str),
                                    shared_cm_ab=0.0,
                                    shared_segments_b=0,
                                    relationship_b="",
                                    has_tree_b=False,
                                    fetched_at=fetched,
                                ))
                            except Exception:
                                pass
                    except Exception:
                        pass

                if shared:
                    n = db.bulk_upsert_shared(shared)
                    total_imported += n
                    print(f"✓ {n} Shared")
                else:
                    print("○ 0 Shared")

                # Als verarbeitet markieren
                try:
                    with db._cursor() as cur:
                        cur.execute("""
                            INSERT OR REPLACE INTO shared_matches_fetched
                            (test_guid, match_guid_a, fetched_at)
                            VALUES (?, ?, ?)
                        """, (test_guid, guid_a, fetched))
                except Exception:
                    pass

            except Exception as e:
                print(f"⚠ {e}")

            time.sleep(pause)

        ctx.close()

    print(f"\n✅  {total_imported} Shared Matches importiert "
          f"({len(to_do)} Match-Seiten verarbeitet)")
    print(f"    DB: ancestry_dna.db")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="MH Shared Matches per Match-Seite laden und importieren")
    ap.add_argument("--csv", "-csv", required=True,
                    help="Pfad zur MH Match-List-CSV (alle Matches)")
    ap.add_argument("--min-cm", type=float, default=50.0,
                    help="Nur Matches ab dieser cM-Schwelle (default: 50)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Max. Anzahl Matches (0 = alle)")
    ap.add_argument("--visible", action="store_true",
                    help="Browser sichtbar anzeigen")
    ap.add_argument("--pause", type=float, default=2.0,
                    help="Pause zwischen Seiten in Sekunden (default: 2.0)")
    ap.add_argument("--no-skip", action="store_true",
                    help="Bereits verarbeitete Matches nicht überspringen")
    ap.add_argument("--profile-dir", default="",
                    help="Persistentes Chromium-Profil-Verzeichnis (speichert Login)")
    ap.add_argument("--cookies", default="",
                    help="Cookie-Editor-JSON-Export von myheritage.de (empfohlen bei Google-Login)")
    args = ap.parse_args()

    scrape(
        csv_path     = args.csv,
        min_cm       = args.min_cm,
        limit        = args.limit,
        headless     = not args.visible,
        pause        = args.pause,
        skip_done    = not args.no_skip,
        profile_dir  = args.profile_dir or None,
        cookies_path = args.cookies or None,
    )
