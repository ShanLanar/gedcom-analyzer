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

# Windows-Konsole auf UTF-8 setzen damit Sonderzeichen funktionieren
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

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
    """Liest Cookie-Editor-JSON und gibt Playwright-kompatible Cookie-Dicts zurück.

    Dupliziert Session-Cookies für .com UND .de, da MH je nach Browser-Sprache
    auf verschiedenen TLDs landet, aber die gleichen Session-Tokens nutzt.
    """
    import json
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    def _make(c: dict, domain_override: str | None = None) -> dict:
        domain = (domain_override or c.get("domain", "")).lstrip(".")
        if "myheritage" in domain and not domain.startswith("."):
            domain = "." + domain
        ss = str(c.get("sameSite", "Lax")).capitalize()
        cookie: dict = {
            "name":     c.get("name", ""),
            "value":    c.get("value", ""),
            "domain":   domain,
            "path":     c.get("path", "/"),
            "sameSite": ss if ss in ("Strict", "Lax", "None") else "Lax",
        }
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if "expirationDate" in c:
            cookie["expires"] = int(c["expirationDate"])
        return cookie

    result = []
    for c in raw:
        orig = _make(c)
        result.append(orig)
        # Für MH-Cookies: auch für die jeweils andere TLD eintragen
        # (.com ↔ .de) damit DNA-Seiten egal welche TLD den Login akzeptieren
        d = orig["domain"]  # z.B. ".myheritage.com" oder ".myheritage.de"
        if "myheritage.com" in d:
            alt = d.replace("myheritage.com", "myheritage.de")
            result.append(_make(c, alt))
        elif "myheritage.de" in d:
            alt = d.replace("myheritage.de", "myheritage.com")
            result.append(_make(c, alt))
    return result


def scrape(csv_path: str, min_cm: float = 50.0, limit: int = 0,
           headless: bool = True, pause: float = 2.0, skip_done: bool = True,
           profile_dir: str | None = None, cookies_path: str | None = None,
           debug: bool = False):
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

    # Anti-Bot-Detection: realistischer Chrome-User-Agent + keine Automation-Flags
    _UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
           "AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/124.0.0.0 Safari/537.36")
    _LAUNCH_ARGS = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    _CTX_OPTS = dict(
        user_agent=_UA,
        locale="de-DE",
        viewport={"width": 1366, "height": 768},
        accept_downloads=True,
        java_script_enabled=True,
    )

    total_imported = 0
    with sync_playwright() as pw:
        if profile_dir:
            ctx = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=headless,
                args=_LAUNCH_ARGS,
                **_CTX_OPTS,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            browser = pw.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
            ctx = browser.new_context(**_CTX_OPTS)
            page = ctx.new_page()

        # navigator.webdriver auf false setzen (wichtigster Anti-Bot-Trick)
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page.set_extra_http_headers({
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-Ch-Ua-Platform": '"Windows"',
        })

        # ── Cookies aus Cookie-Editor-Export injizieren ───────────────────────
        if cookies_path:
            try:
                cookies = _load_cookie_editor_json(cookies_path)
                ctx.add_cookies(cookies)
                print(f"✓ {len(cookies)} Cookies aus {cookies_path} geladen.")
            except Exception as exc:
                print(f"⚠  Cookie-Datei konnte nicht geladen werden: {exc}")

        # ── Session aufwärmen: erst Startseite, dann DNA-Bereich ─────────────
        # .com nutzen: DNA-Features laufen primär auf myheritage.com
        print("Öffne MyHeritage — Session aufwärmen …")
        for warmup_url in ["https://www.myheritage.com/",
                           "https://www.myheritage.com/dna/matches"]:
            try:
                resp = page.goto(warmup_url, wait_until="domcontentloaded", timeout=30_000)
                if debug:
                    print(f"    [DBG] Warmup {warmup_url[:60]} → {page.url[:80]}"
                          f" (status={getattr(resp,'status','?')})")
                time.sleep(1.5)
            except PWTimeout:
                if debug:
                    print(f"    [DBG] Warmup Timeout: {warmup_url}")
        time.sleep(1)

        final_url = page.url
        on_dna = "myheritage" in final_url and (
            "/dna" in final_url or "match" in final_url)
        if debug:
            print(f"    [DBG] Nach Warmup: {final_url}")
            print(f"    [DBG] DNA-Seite erreicht: {on_dna}")

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

            # DNA-URLs immer auf .com normalisieren
            url = url.replace("myheritage.de/", "myheritage.com/")

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
            _gql_req_info: dict = {}   # speichert headers+body des SM-GraphQL-Requests

            try:
                # Request-Body aus Response-Objekt holen (zuverlässiger als on("request"))
                _SM_KEY = "dna_single_match_get_shared_matches"
                def _capture_gql_req(request):
                    pass  # wird jetzt über Response-Handler befüllt
                page.on("request", _capture_gql_req)  # Dummy, wird unten entfernt

                # Netzwerk-Intercept: ALLE JSON-Antworten von MH abfangen
                def _on_resp(response):
                    try:
                        ru = response.url
                        ct = response.headers.get("content-type", "")
                        is_mh = ("myheritage" in ru or "mhcache.com" in ru
                                 or "mhc-static" in ru)
                        if debug and is_mh:
                            print(f"    [NET] {response.status} {ct[:25]:25} {ru[:110]}")
                        if response.ok and is_mh and ("json" in ct or "csv" in ct):
                            try:
                                body = response.text()
                                intercepted.append((ru, body))
                                # Body des SM-Requests für Pagination merken
                                if _SM_KEY in ru and not _gql_req_info:
                                    req = response.request
                                    _gql_req_info["url"]     = req.url
                                    _gql_req_info["headers"] = dict(req.headers)
                                    _gql_req_info["body"]    = req.post_data or ""
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

                # React/Redux braucht Zeit zum Hydratisieren + GraphQL-Calls abwarten
                wait_total = max(pause, 8.0)
                time.sleep(wait_total * 0.4)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(wait_total * 0.3)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(wait_total * 0.3)

                page.remove_listener("response", _on_resp)
                page.remove_listener("request", _capture_gql_req)

                if debug:
                    print(f"    [DBG] {len(intercepted)} Antworten abgefangen:")
                    for ru, rb in intercepted:
                        print(f"      {ru[:120]}")
                        print(f"      → {rb[:200]!r}")

                # Intercept-Antworten auswerten
                csv_text = None
                import json as _json

                def _parse_mh_item(item: dict) -> SharedMatch | None:
                    """Parst ein MH-GraphQL-Match-Item aus dna_shared_matches.

                    Item-Shape:
                    {
                      dna_matches_cluster_shared_segments_count: N,
                      shared_member: { name, id: "user-XXX", ... },
                      dna_match: {
                        id: "dnamatch-D-OWNER-D-MATCH",
                        total_shared_segments_length_in_cm: 116.32,
                        link: "https://...match/D-OWNER-D-MATCH/...",
                        refined_dna_relationships: [...],
                      }
                    }
                    """
                    if not isinstance(item, dict):
                        return None
                    member   = item.get("shared_member") or {}
                    dna_info = item.get("dna_match") or {}

                    # cM aus dna_match.total_shared_segments_length_in_cm
                    cm_val = float(dna_info.get("total_shared_segments_length_in_cm") or
                                   dna_info.get("shared_dna") or
                                   item.get("shared_dna") or
                                   item.get("sharedDna") or 0)

                    # GUID: zweite D-xxx aus dna_match.id oder .link extrahieren
                    # "dnamatch-D-OWNER-D-MATCH" → D-MATCH
                    g = ""
                    raw_id = str(dna_info.get("id") or dna_info.get("link") or
                                 member.get("id") or "")
                    m_guid = re.findall(r'D-[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}',
                                        raw_id.upper())
                    if len(m_guid) >= 2:
                        g = m_guid[1]           # zweite GUID = der shared Match
                    elif len(m_guid) == 1:
                        g = m_guid[0]
                    if not g:
                        g = (member.get("id") or "").upper()  # "user-OYYV65..." als Fallback
                    if not g or not cm_val:
                        return None
                    name = str(member.get("name") or member.get("display_name") or
                               item.get("displayName") or item.get("name") or "")
                    segs = int(item.get("dna_matches_cluster_shared_segments_count") or
                               item.get("shared_segments") or
                               item.get("sharedSegments") or 0)
                    # Beziehung aus refined_dna_relationships[0]
                    rels = dna_info.get("refined_dna_relationships") or []
                    rel = str(rels[0].get("relationship_degree") if rels else
                              item.get("relationship") or "")
                    tree = bool(item.get("hasTree") or member.get("has_tree"))
                    return SharedMatch(
                        test_guid=test_guid,
                        match_guid_a=guid_a,
                        match_guid_b=g,
                        display_name_b=str(name),
                        shared_cm_b=cm_val,
                        shared_cm_ab=0.0,
                        shared_segments_b=segs,
                        relationship_b=rel,
                        has_tree_b=tree,
                        fetched_at=fetched,
                    )

                def _items_from_json(data) -> list:
                    """Sucht rekursiv nach Listen von Match-Objekten in MH-JSON."""
                    if isinstance(data, list):
                        return data
                    if not isinstance(data, dict):
                        return []
                    # MH GraphQL bekannte Schlüssel (Priorität: spezifischste zuerst)
                    for key in ("dna_shared_matches", "sharedMatches", "shared_matches",
                                "matches", "results", "relatives", "items",
                                "nodes", "edges"):
                        v = data.get(key)
                        if isinstance(v, list) and v:
                            return v
                        if isinstance(v, dict):
                            # MH GraphQL: {"count": N, "data": [...]}
                            inner_list = v.get("data")
                            if isinstance(inner_list, list) and inner_list:
                                return inner_list
                            inner = _items_from_json(v)
                            if inner:
                                return inner
                    # "data" als generischer Wrapper
                    v = data.get("data")
                    if isinstance(v, list) and v:
                        return v
                    if isinstance(v, dict):
                        inner = _items_from_json(v)
                        if inner:
                            return inner
                    # Alle anderen Dict-Werte rekursiv durchsuchen
                    for v in data.values():
                        if isinstance(v, (dict, list)):
                            inner = _items_from_json(v)
                            if inner:
                                return inner
                    return []

                # Erst gezielt den Shared-Matches-Endpoint auswerten
                _SM_URL = "dna_single_match_get_shared_matches"
                total_sm_count = 0
                for resp_url, resp_body in intercepted:
                    if not resp_body or _SM_URL not in resp_url:
                        continue
                    try:
                        data = _json.loads(resp_body)
                        items = _items_from_json(data)
                        # Gesamtanzahl für Pagination merken
                        try:
                            sm_node = (data.get("data") or {}).get("dna_match") or {}
                            total_sm_count = int(
                                (sm_node.get("dna_shared_matches") or {}).get("count") or 0)
                        except Exception:
                            pass
                        if debug:
                            print(f"    [DBG] GraphQL shared_matches Items: {len(items)}"
                                  f" (gesamt: {total_sm_count})")
                        for item in items:
                            sm = _parse_mh_item(item)
                            if sm:
                                shared.append(sm)
                        if shared:
                            if debug:
                                print(f"    [DBG] {len(shared)} Matches aus: {resp_url[:80]}")
                            break
                    except Exception as exc:
                        if debug:
                            print(f"    [DBG] Parse-Fehler: {exc}")

                # Pagination: weitere Seiten per direkter GraphQL-API holen
                PAGE_SIZE = 10
                if debug:
                    print(f"    [DBG] GQL-Request erfasst: {bool(_gql_req_info)}"
                          f" | total_sm_count={total_sm_count}")
                if shared and total_sm_count > PAGE_SIZE and _gql_req_info:
                    try:
                        import json as _pjson
                        gql_url = _gql_req_info["url"]
                        gql_hdrs = {k: v for k, v in _gql_req_info["headers"].items()
                                    if k.lower() not in ("content-length",)}
                        base_body = _pjson.loads(_gql_req_info["body"])
                        offset = PAGE_SIZE
                        while offset < total_sm_count:
                            # offset in GraphQL-Variablen setzen
                            body_page = _pjson.loads(_pjson.dumps(base_body))
                            vars_ = body_page.get("variables") or {}
                            vars_["offset"] = offset
                            body_page["variables"] = vars_
                            resp_p = ctx.request.post(
                                gql_url,
                                headers=gql_hdrs,
                                data=_pjson.dumps(body_page),
                            )
                            if not resp_p.ok:
                                if debug:
                                    print(f"    [DBG] Pagination {offset}: HTTP {resp_p.status}")
                                break
                            data_p = _pjson.loads(resp_p.text())
                            items_p = _items_from_json(data_p)
                            if not items_p:
                                break
                            for item in items_p:
                                sm = _parse_mh_item(item)
                                if sm:
                                    shared.append(sm)
                            if debug:
                                print(f"    [DBG] Seite offset={offset}: "
                                      f"{len(items_p)} Items → {len(shared)} gesamt")
                            offset += PAGE_SIZE
                            time.sleep(0.5)
                    except Exception as exc:
                        if debug:
                            print(f"    [DBG] Pagination-Fehler: {exc}")

                # Fallback: alle anderen JSON-Antworten durchsuchen
                if not shared:
                    for resp_url, resp_body in intercepted:
                        if not resp_body or _SM_URL in resp_url:
                            continue
                        stripped = resp_body.lstrip()
                        if stripped.startswith("{") or stripped.startswith("["):
                            try:
                                data = _json.loads(resp_body)
                                items = _items_from_json(data)
                                for item in items:
                                    sm = _parse_mh_item(item)
                                    if sm:
                                        shared.append(sm)
                                if shared:
                                    if debug:
                                        print(f"    [DBG] Match-Daten aus Fallback: {resp_url[:80]}")
                                    break
                            except Exception:
                                pass
                        elif "\n" in resp_body and "," in resp_body:
                            csv_text = resp_body
                            break

                if csv_text:
                    shared = _parse_shared_csv(csv_text, test_guid, guid_a, fetched)

                # Fallback A: dnaAppData Redux-State aus dem HTML parsen
                if not shared:
                    try:
                        html = page.content()
                        # Redux-Preloaded-State suchen: var dnaAppData = {...}
                        m_app = re.search(
                            r'var\s+dnaAppData\s*=\s*(\{.*?\});\s*(?:var|</script>)',
                            html, re.DOTALL)
                        if not m_app:
                            # Alternativ: window.__INITIAL_STATE__ o.ä.
                            m_app = re.search(
                                r'__(?:INITIAL|REDUX)_STATE__\s*=\s*(\{.*?\});\s*',
                                html, re.DOTALL)
                        if m_app:
                            try:
                                app_data = _json.loads(m_app.group(1))
                                items = _items_from_json(app_data)
                                if debug:
                                    print(f"    [DBG] dnaAppData Items: {len(items)}")
                                for item in items:
                                    if not isinstance(item, dict):
                                        continue
                                    g = (item.get("guid") or item.get("matchGuid") or "")
                                    if isinstance(g, str):
                                        g = g.upper()
                                    cm_val = float(item.get("sharedDna") or
                                                   item.get("sharedCm") or 0)
                                    if g and cm_val:
                                        shared.append(SharedMatch(
                                            test_guid=test_guid,
                                            match_guid_a=guid_a,
                                            match_guid_b=g,
                                            display_name_b=str(
                                                item.get("displayName") or ""),
                                            shared_cm_b=cm_val,
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

                # Fallback B: GUID+sharedDna per Regex im HTML
                if not shared:
                    try:
                        html = page.content() if "html" not in dir() else html
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

                # DNA-Segmente aus dna_single_match_get_shared_segments parsen
                _SEG_URL = "dna_single_match_get_shared_segments"
                seg_count = 0
                for resp_url, resp_body in intercepted:
                    if not resp_body or _SEG_URL not in resp_url:
                        continue
                    try:
                        seg_data = _json.loads(resp_body)
                        if debug:
                            print(f"    [DBG] Segment-Response: {resp_body[:800]}")
                        dm_node = ((seg_data.get("data") or {})
                                   .get("dna_match") or {})
                        if debug:
                            can_view = dm_node.get("can_view_shared_segments")
                            print(f"    [DBG] can_view_shared_segments={can_view}"
                                  f" | dm_node keys: {list(dm_node.keys())}")
                        # MH GraphQL: dna_shared_segments (korrekter Schlüssel)
                        raw_segs = (dm_node.get("dna_shared_segments") or
                                    dm_node.get("shared_segments") or
                                    dm_node.get("segments") or [])
                        if isinstance(raw_segs, str):
                            try:
                                raw_segs = _json.loads(raw_segs)
                            except Exception:
                                raw_segs = []
                        if isinstance(raw_segs, dict):
                            raw_segs = raw_segs.get("data") or []
                        seg_rows = []
                        for seg in raw_segs:
                            if not isinstance(seg, dict):
                                continue
                            chrom = int(seg.get("chromosome") or seg.get("chr") or
                                        seg.get("id") or 0)
                            start = int(seg.get("start_location") or
                                        seg.get("startLocation") or 0)
                            end   = int(seg.get("end_location") or
                                        seg.get("endLocation") or 0)
                            lcm   = float(seg.get("length_in_cm") or
                                          seg.get("length_cm") or
                                          seg.get("lengthCm") or
                                          seg.get("length") or 0.0)
                            snps  = int(seg.get("snp_count") or
                                        seg.get("snpCount") or 0)
                            if chrom and (start or end):
                                seg_rows.append({
                                    "test_guid": test_guid,
                                    "match_guid": guid_a,
                                    "chromosome": chrom,
                                    "start_location": start,
                                    "end_location": end,
                                    "length_cm": lcm,
                                    "snp_count": snps,
                                    "fetched_at": fetched,
                                })
                        if seg_rows:
                            seg_count = db.bulk_upsert_segments(seg_rows)
                        elif debug:
                            print(f"    [DBG] Keine Segmente in dm_node-Keys: "
                                  f"{list(dm_node.keys())}")
                    except Exception as exc:
                        if debug:
                            print(f"    [DBG] Segment-Parse-Fehler: {exc}")
                    break

                if shared:
                    n = db.bulk_upsert_shared(shared)
                    total_imported += n
                    seg_str = f" + {seg_count} Seg" if seg_count else ""
                    print(f"✓ {n} Shared{seg_str}")
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
    ap.add_argument("--debug", action="store_true",
                    help="Netzwerk-Requests und abgefangene API-Antworten ausgeben")
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
        debug        = args.debug,
    )
