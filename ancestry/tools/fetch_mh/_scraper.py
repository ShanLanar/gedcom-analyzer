"""Main Playwright scraper for MyHeritage shared matches."""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone

from ancestry.core.database import Database as AncestryDatabase
from ancestry.models.match import SharedMatch

from ._csv import _load_main_csv, _parse_shared_csv
from ._browser import _load_cookie_editor_json, _resolve_extension_dir


def scrape(csv_path: str, min_cm: float = 50.0, limit: int = 0,
           headless: bool = True, pause: float = 2.0, skip_done: bool = True,
           profile_dir: str | None = None, cookies_path: str | None = None,
           debug: bool = False, extension_dir: str | None = None,
           wait_login: bool = False, cdp_url: str | None = None,
           repair_threshold: int = 0, max_per_run: int = 0):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("Playwright nicht installiert:\n"
              "  pip install playwright && playwright install chromium")
        sys.exit(1)

    db = AncestryDatabase()

    # Sicherstellen, dass repair_attempted-Spalte existiert (einmalige Live-Migration)
    try:
        with db._cursor() as cur:
            cur.execute(
                "ALTER TABLE shared_matches_fetched ADD COLUMN repair_attempted INTEGER DEFAULT 0"
            )
    except Exception:
        pass  # Spalte existiert bereits

    # Test-GUID aus CSV-Dateiname oder DB ermitteln
    # Dateiname: Andreas_Kovermann_D44D71405...  → D-44D71405-...
    test_guid = ""
    fname = os.path.basename(csv_path)
    m = re.search(r"[\s_](D[-0-9A-F]{8,})", fname, re.I)
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
                # Alle verarbeiteten match_guid_a laden (test_guid-unabhängig,
                # da MH-GUID D-... und Ancestry-GUID verschieden sind)
                rows = cur.execute(
                    "SELECT match_guid_a FROM shared_matches_fetched"
                ).fetchall()
                all_fetched = {r[0] for r in rows}

            if repair_threshold > 0:
                # Reparatur-Modus (einmalig pro Match):
                # Nur Matches mit ≤ N Shared Matches UND repair_attempted = 0 werden
                # erneut geladen. Nach dem Reparatur-Lauf wird repair_attempted = 1 gesetzt
                # → bei künftigen Läufen niemals mehr angerührt, auch wenn der Zähler
                # weiterhin ≤ N ist (genuine sparse match).
                try:
                    with db._cursor() as cur:
                        count_rows = cur.execute(
                            "SELECT smf.match_guid_a, smf.repair_attempted, "
                            "COUNT(sm.match_guid_b) AS cnt "
                            "FROM shared_matches_fetched smf "
                            "LEFT JOIN shared_matches sm "
                            "  ON sm.match_guid_a = smf.match_guid_a "
                            "GROUP BY smf.match_guid_a, smf.repair_attempted"
                        ).fetchall()
                    # Bereits repariert oder ausreichend Daten → überspringen
                    done_guids = {
                        r[0] for r in count_rows
                        if r[1] == 1          # repair_attempted = 1 → schon repariert
                        or r[2] > repair_threshold  # genügend Shared Matches vorhanden
                    }
                    repair_count = len(all_fetched) - len(done_guids)
                    already_repaired = sum(1 for r in count_rows if r[1] == 1)
                    print(f"{len(all_fetched)} Matches bereits verarbeitet; "
                          f"{repair_count} davon haben ≤{repair_threshold} Shared Matches "
                          f"und wurden noch nicht repariert "
                          f"→ werden einmalig erneut geladen.\n"
                          f"   ({already_repaired} bereits repariert – werden übersprungen.)")
                except Exception as _re:
                    done_guids = all_fetched
                    print(f"Repair-Threshold-Abfrage fehlgeschlagen ({_re}), "
                          f"verwende Standard --skip-done.")
            else:
                done_guids = all_fetched
                print(f"{len(done_guids)} Matches bereits verarbeitet (--skip-done aktiv).")
        except Exception:
            pass

    matches = _load_main_csv(csv_path, min_cm)
    if limit:
        matches = matches[:limit]

    to_do = [m for m in matches if m["guid"] not in done_guids]
    _run_limit = min(max_per_run, len(to_do)) if max_per_run else len(to_do)
    print(f"\n{len(matches)} Matches ≥ {min_cm} cM geladen, "
          f"{len(to_do)} noch nicht/unvollständig verarbeitet.")
    if max_per_run and len(to_do) > max_per_run:
        _days_left = -(-len(to_do) // max_per_run)  # ceiling division
        print(f"--max-per-run {max_per_run}: dieser Lauf verarbeitet "
              f"{max_per_run} von {len(to_do)} → noch ca. {_days_left - 1} weitere Läufe nötig.")
    print()

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

    # ── Browser-Extension (z.B. Genealogy Assistant) vorbereiten ──────────────
    # Erweiterungen brauchen einen persistenten Kontext und werden im alten
    # Headless-Modus NICHT geladen → "--headless=new" verwenden.
    _ext_args: list[str] = []
    if extension_dir:
        _resolved = _resolve_extension_dir(extension_dir)
        if not _resolved:
            print(f"⚠  Extension nicht gefunden (Pfad/ID): {extension_dir}")
            extension_dir = None
        else:
            extension_dir = _resolved
        if extension_dir:
            _ext_args = [
                f"--disable-extensions-except={extension_dir}",
                f"--load-extension={extension_dir}",
            ]
            if not profile_dir:
                import tempfile
                profile_dir = tempfile.mkdtemp(prefix="mh_ext_profile_")
                print("⚠  Kein --profile-dir gesetzt → Temp-Profil. Die Anmeldung in "
                      "der Erweiterung bleibt NICHT erhalten und muss bei jedem Lauf "
                      "neu erfolgen.\n"
                      "   Empfehlung: festes Verzeichnis via --profile-dir, dann nur "
                      "EINMAL im Genealogy Assistant verifizieren.")
            print(f"✓ Lade Extension: {extension_dir}")

    total_imported = 0
    with sync_playwright() as pw:
        _via_cdp = bool(cdp_url)
        if _via_cdp:
            # An laufendes Chrome anhängen (mit bereits installierter, verifizierter
            # Erweiterung). Chrome muss mit Remote-Debugging gestartet sein:
            #   chrome.exe --remote-debugging-port=9222 --user-data-dir="..."
            print(f"Verbinde mit laufendem Chrome via CDP: {cdp_url} …")
            browser = pw.chromium.connect_over_cdp(cdp_url)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            # Eigene Seite öffnen (vorhandene Tabs unangetastet lassen)
            page = ctx.new_page()
        elif profile_dir:
            _args = list(_LAUNCH_ARGS) + _ext_args
            # Mit Extension: neuer Headless-Modus (lädt Erweiterungen)
            _launch_headless = headless
            if _ext_args and headless:
                _args.append("--headless=new")
                _launch_headless = False
            ctx = pw.chromium.launch_persistent_context(
                profile_dir,
                headless=_launch_headless,
                args=_args,
                **_CTX_OPTS,
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        else:
            browser = pw.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
            ctx = browser.new_context(**_CTX_OPTS)
            page = ctx.new_page()

        # ── Prüfen, ob die Erweiterung wirklich geladen wurde ─────────────────
        if _ext_args:
            time.sleep(2)
            _loaded = False
            try:
                # MV3: Service-Worker; MV2: Background-Page
                _sws = list(getattr(ctx, "service_workers", []) or [])
                _bgs = list(getattr(ctx, "background_pages", []) or [])
                _ext_origins = [w.url for w in _sws] + [b.url for b in _bgs]
                _loaded = any(u.startswith("chrome-extension://") for u in _ext_origins)
                if debug:
                    print(f"    [DBG] Extension-Worker: {_ext_origins}")
            except Exception as _ee:
                if debug:
                    print(f"    [DBG] Extension-Check-Fehler: {_ee}")
            if _loaded:
                print("✓ Erweiterung ist aktiv (Service-Worker geladen).")
            else:
                print("⚠  Erweiterung scheint NICHT geladen. Mögliche Ursachen:\n"
                      "   • Pfad/ID falsch (kein manifest.json gefunden)\n"
                      "   • Im echten Chrome erst öffnen, damit der Ordner existiert\n"
                      "   • Headless: nur '--headless=new' lädt Extensions (oder --visible)")

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
        # Bei CDP nutzt das echte Chrome bereits die aktive Session → nicht nötig.
        if cookies_path and not _via_cdp:
            try:
                cookies = _load_cookie_editor_json(cookies_path)
                ctx.add_cookies(cookies)
                print(f"✓ {len(cookies)} Cookies aus {cookies_path} geladen.")
            except Exception as exc:
                print(f"⚠  Cookie-Datei konnte nicht geladen werden: {exc}")
        elif _via_cdp:
            print("✓ CDP-Modus: bestehende Chrome-Session + Erweiterung werden genutzt.")

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

        # ── Pause zum Einloggen/Verifizieren der Erweiterung ──────────────────
        # Gibt dir Zeit, im sichtbaren Browser den Genealogy Assistant zu
        # verifizieren. Dank festem --profile-dir nur EINMAL nötig.
        if wait_login:
            print("\n" + "=" * 66)
            print("  PAUSE: Bitte jetzt im geöffneten Browser den Genealogy")
            print("  Assistant aktivieren/verifizieren (einloggen).")
            print("  Wenn fertig: hier im Terminal ENTER drücken …")
            print("=" * 66)
            try:
                input()
            except EOFError:
                time.sleep(90)
            print("Weiter geht's …")

        # ── Konto-Sperre/Rate-Limit erkennen und SOFORT abbrechen ─────────────
        def _check_lockout(pg) -> bool:
            try:
                _txt = pg.content()
            except Exception:
                return False
            _markers = [
                "vorübergehend deaktiviert",
                "unregelmäßiger Aktivitäten",
                "temporarily deactivated",
                "irregular activity",
                "try again in 24",
                "in 24 Stunden erneut",
            ]
            return any(m.lower() in _txt.lower() for m in _markers)

        if _check_lockout(page):
            print("\n🛑 MyHeritage hat den Zugang vorübergehend gesperrt "
                  "(unregelmäßige Aktivität / Rate-Limit).")
            print("   Bitte ~24 Stunden warten und danach mit größerem --pause "
                  "und wenigen Läufen erneut versuchen.")
            if _via_cdp:
                try: page.close()
                except Exception: pass
            else:
                ctx.close()
            return

        # Prüfen ob Login-Dialog offen (im CDP-Modus übersprungen — echte Session)
        if not _via_cdp and page.query_selector(
                "input[name='username'], input[type='email']"):
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
        processed_this_run = 0
        _stopped_early = False
        for i, match in enumerate(to_do, 1):
            if max_per_run and processed_this_run >= max_per_run:
                _stopped_early = True
                remaining_after = len(to_do) - i + 1
                print(f"\n⏹  --max-per-run {max_per_run} erreicht. "
                      f"{remaining_after} Matches verbleiben → morgen erneut starten.")
                break

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
            _route_bodies: dict = {}   # via page.route() abgefangene GQL-Request-Bodies

            try:
                _SM_KEY  = "dna_single_match_get_shared_matches"
                _SEG_KEY = "dna_single_match_get_shared_segments"

                # ── Route-Handler: GQL POST-Body zuverlässig abfangen ────────────
                # page.route() liefert request.post_data korrekt (anders als response.request)
                def _route_capture(route):
                    req = route.request
                    for _k in (_SM_KEY, _SEG_KEY):
                        if _k in req.url and _k not in _route_bodies:
                            # post_data kann binär/komprimiert sein → post_data_buffer + decompress
                            _b = ""
                            try:
                                raw = req.post_data_buffer  # bytes
                                if raw:
                                    if raw[:2] == b'\x1f\x8b':  # gzip magic
                                        import gzip as _gz
                                        raw = _gz.decompress(raw)
                                    _b = raw.decode("utf-8", errors="replace")
                            except Exception:
                                _b = req.post_data or ""
                            if len(_b) > 5:
                                _route_bodies[_k] = {
                                    "url": req.url,
                                    "headers": dict(req.headers),
                                    "body": _b,
                                }
                                if debug:
                                    print(f"    [DBG] route captured {_k[-20:]}: "
                                          f"len={len(_b)} start={_b[:40]!r}")
                    route.continue_()
                if not _via_cdp:  # CDP: CSV liefert alle Daten, kein Route-Intercepting nötig
                    page.route("**/web-family-graphql/**", _route_capture)

                # Netzwerk-Intercept: JSON-Antworten abfangen
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
                                intercepted.append((ru, response.text()))
                            except Exception:
                                pass
                    except Exception:
                        pass
                page.on("response", _on_resp)

                try:
                    page.evaluate("window.stop()")
                except Exception:
                    pass
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=40_000)
                except PWTimeout:
                    page.goto(url, wait_until="commit", timeout=20_000)

                # React/Redux braucht Zeit zum Hydratisieren + GraphQL-Calls abwarten
                wait_total = max(pause, 8.0)
                time.sleep(wait_total * 0.4)

                # Sperre auch mitten im Lauf erkennen → sofort abbrechen
                if _check_lockout(page):
                    _remaining = len(to_do) - i
                    print(f"\n🛑 MyHeritage-Sperre erkannt nach {processed_this_run} "
                          f"verarbeiteten Matches. Bitte ~24 h warten.\n"
                          f"   Noch ausstehend: {_remaining} Matches "
                          f"→ morgen erneut mit --skip-done starten.")
                    _stopped_early = True
                    break

                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(wait_total * 0.3)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(wait_total * 0.3)

                # ── Pagination via "Download CSV" (all pages) ────────────────────
                # MH bietet im Shared-Matches-Bereich einen "Download CSV"-Button mit
                # "all pages"-Auswahl. MH lädt dann SELBST alle Seiten (Modal
                # "Loading all pages – Page N loaded…") und liefert eine fertige CSV
                # mit ALLEN Shared Matches. Wir setzen die Auswahl auf "all", klicken
                # Download und fangen den Datei-Download via Playwright ab. Das umgeht
                # das fragile "Show more"-Klicken komplett.
                _SM_URL_KEY = "dna_single_match_get_shared_matches"
                _dl_csv_text = None
                try:
                    # Auswahl-Dropdown neben "Download CSV" auf "all" stellen (best effort).
                    # MH-Spinbox: <select> oder Custom-Spinner mit "all"/Zahl.
                    try:
                        for _sel in page.locator("select").all():
                            try:
                                _opts = [o.strip().lower()
                                         for o in _sel.locator("option").all_inner_texts()]
                                if any("all" in o for o in _opts):
                                    _sel.select_option(label=re.compile(r"all", re.I))
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # Auf das Erscheinen des (von der Erweiterung injizierten)
                    # "Download CSV"-Buttons warten — die Extension braucht ggf. ein
                    # paar Sekunden bzw. eine erfolgte Verifizierung.
                    _dl_loc = page.get_by_text(re.compile(r"download\s+csv", re.I)).first
                    try:
                        _dl_loc.wait_for(state="visible", timeout=15_000)
                        _btn_present = True
                    except PWTimeout:
                        _btn_present = False

                    if not _btn_present:
                        print("    ⚠  'Download CSV'-Button nicht gefunden. Ist die "
                              "Genealogy-Assistant-Erweiterung geladen UND verifiziert? "
                              "(Einmalig mit --visible + festem --profile-dir einloggen.)")
                    else:
                        if debug:
                            print("    [DBG] Klicke 'Download CSV' (all pages) …")
                        # Download kann lange dauern (alle Seiten laden) → großzügig
                        with page.expect_download(timeout=300_000) as _dl_info:
                            _dl_loc.scroll_into_view_if_needed(timeout=5000)
                            _dl_loc.click(timeout=5000)
                        _dl = _dl_info.value
                        _dl_path = _dl.path()
                        with open(_dl_path, encoding="utf-8-sig", errors="replace") as _f:
                            _dl_csv_text = _f.read()
                        if debug:
                            _hdr = _dl_csv_text.split("\n", 1)[0]
                            _rows = _dl_csv_text.count("\n")
                            print(f"    [DBG] CSV geladen: {_rows} Zeilen | Header: {_hdr[:200]}")
                        # Close-Button klicken (ohne auf den dadurch ausgelösten
                        # Seiten-Reload zu warten — das nächste page.goto() bricht ihn ab)
                        try:
                            _close_btn = page.get_by_role(
                                "button", name=re.compile(r"^close$", re.I))
                            _close_btn.click(timeout=3000, no_wait_after=True)
                        except Exception:
                            pass
                        # Extra-Tabs schließen die die Erweiterung evtl. geöffnet hat
                        try:
                            for _p in ctx.pages:
                                if _p != page:
                                    _p.close()
                        except Exception:
                            pass
                except PWTimeout:
                    if debug:
                        print("    [DBG] Download-CSV Timeout — kein Download erhalten")
                except Exception as _de:
                    if debug:
                        print(f"    [DBG] Download-CSV Fehler: {_de}")

                try:
                    page.remove_listener("response", _on_resp)
                except Exception:
                    pass
                if not _via_cdp:
                    try:
                        page.unroute("**/web-family-graphql/**", _route_capture)
                    except Exception:
                        pass

                if debug:
                    for k in (_SM_KEY, _SEG_KEY):
                        bl = len((_route_bodies.get(k) or {}).get("body", ""))
                        print(f"    [DBG] route-body {k[-20:]}: len={bl}")

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

                # PRIMÄR: per "Download CSV (all pages)" geladene CSV — enthält ALLE
                # Shared Matches. Diese hat Vorrang vor der GraphQL-Vorschau (10).
                _SM_URL = "dna_single_match_get_shared_matches"
                _seen_guids: set = set()
                if _dl_csv_text:
                    _csv_rows = _parse_shared_csv(_dl_csv_text, test_guid, guid_a, fetched)
                    for sm in _csv_rows:
                        if sm.match_guid_b and sm.match_guid_b not in _seen_guids:
                            _seen_guids.add(sm.match_guid_b)
                            shared.append(sm)
                    if debug:
                        print(f"    [DBG] {len(shared)} Shared Matches aus Download-CSV")

                # Ergänzend/Fallback: GraphQL-Antworten sammeln (Dedup über guid_b).
                total_sm_count = 0
                _pages_seen = 0
                for resp_url, resp_body in intercepted:
                    if not resp_body or _SM_URL not in resp_url:
                        continue
                    try:
                        data = _json.loads(resp_body)
                        items = _items_from_json(data)
                        try:
                            sm_node = (data.get("data") or {}).get("dna_match") or {}
                            total_sm_count = max(total_sm_count, int(
                                (sm_node.get("dna_shared_matches") or {}).get("count") or 0))
                        except Exception:
                            pass
                        _pages_seen += 1
                        _added = 0
                        for item in items:
                            sm = _parse_mh_item(item)
                            if sm and sm.match_guid_b not in _seen_guids:
                                _seen_guids.add(sm.match_guid_b)
                                shared.append(sm)
                                _added += 1
                        if debug:
                            print(f"    [DBG] SM-Seite: {len(items)} Items, "
                                  f"+{_added} neu → {len(shared)} gesamt "
                                  f"(von {total_sm_count})")
                    except Exception as exc:
                        if debug:
                            print(f"    [DBG] Parse-Fehler: {exc}")
                if debug:
                    print(f"    [DBG] {_pages_seen} SM-Seiten verarbeitet, "
                          f"{len(shared)}/{total_sm_count} Matches eindeutig")
                # Hinweis, wenn nicht alle geladen wurden
                if total_sm_count > len(shared):
                    print(f"    ⚠  {len(shared)} von {total_sm_count} Shared Matches geladen "
                          f"(Download-CSV evtl. fehlgeschlagen).")
                elif len(shared) >= max(total_sm_count, 1) and len(shared) > 10:
                    print(f"    ✓ Alle {len(shared)} Shared Matches via Download-CSV geladen.")

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

                # DNA-Segmente: aus intercept oder via Browser-fetch nachladen
                seg_count = 0
                _seg_intercepted = [(ru, rb) for ru, rb in intercepted if _SEG_KEY in ru]
                _seg_info = _route_bodies.get(_SEG_KEY, {})
                # Segment-Re-Fetch nur wenn keine CSV-Daten vorhanden (CSV enthält keine Segmente)
                if not _dl_csv_text and _seg_info.get("body") and not any(
                    '"dna_shared_segments"' in rb and '"data":[' in rb
                    for _, rb in _seg_intercepted
                ):
                    _JS_SEG = """
async ([url, bodyStr]) => {
    try {
        const body = JSON.parse(bodyStr);
        const r = await fetch(url, {
            method: 'POST', credentials: 'include',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
        return await r.text();
    } catch(e) { return null; }
}
"""
                    try:
                        seg_result = page.evaluate(_JS_SEG,
                                                   [_seg_info["url"], _seg_info["body"]])
                        if seg_result:
                            _seg_intercepted.append((_seg_info["url"], seg_result))
                            if debug:
                                print(f"    [DBG] Segment via browser-fetch neu geladen: "
                                      f"{seg_result[:200]!r}")
                    except Exception as exc:
                        if debug:
                            print(f"    [DBG] Segment-fetch Fehler: {exc}")

                for resp_url, resp_body in _seg_intercepted:
                    if not resp_body:
                        continue
                    try:
                        seg_data = _json.loads(resp_body)
                        if debug:
                            print(f"    [DBG] Segment-Response: {resp_body[:800]}")
                        dm_node = ((seg_data.get("data") or {})
                                   .get("dna_match") or {})
                        if debug:
                            can_view = dm_node.get("can_view_shared_segments")
                            dss = dm_node.get("dna_shared_segments")
                            print(f"    [DBG] can_view={can_view}"
                                  f" | dm_node keys: {list(dm_node.keys())}"
                                  f" | dna_shared_segments type={type(dss).__name__}"
                                  f" val={str(dss)[:120]!r}")
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
                            chrom = int(seg.get("chromosome_id") or
                                        seg.get("chromosome") or seg.get("chr") or
                                        seg.get("id") or 0)
                            start = int(seg.get("start_position") or
                                        seg.get("start_location") or
                                        seg.get("startLocation") or 0)
                            end   = int(seg.get("end_position") or
                                        seg.get("end_location") or
                                        seg.get("endLocation") or 0)
                            lcm   = float(seg.get("length_cm") or
                                          seg.get("length_in_cm") or
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

                # Als verarbeitet markieren; repair_attempted=1 wenn dies ein Reparatur-Lauf
                # war → dieser Match wird bei künftigen --repair-threshold-Läufen
                # dauerhaft übersprungen (auch wenn der Zähler weiterhin ≤ Schwelle ist).
                _is_repair = repair_threshold > 0
                try:
                    with db._cursor() as cur:
                        cur.execute("""
                            INSERT INTO shared_matches_fetched
                              (test_guid, match_guid_a, fetched_at, repair_attempted)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(test_guid, match_guid_a) DO UPDATE SET
                              fetched_at       = excluded.fetched_at,
                              repair_attempted = MAX(repair_attempted, excluded.repair_attempted)
                        """, (test_guid, guid_a, fetched, 1 if _is_repair else 0))
                    processed_this_run += 1
                except Exception:
                    pass

            except KeyboardInterrupt:
                _remaining = len(to_do) - i
                print(f"\n⚠  Abgebrochen nach {processed_this_run} Matches. "
                      f"{_remaining} verbleiben → mit --skip-done fortsetzen.")
                _stopped_early = True
                break
            except Exception as e:
                print(f"⚠ {e}")

            time.sleep(pause)

        # Bei CDP nur die eigene Seite schließen, NICHT das Chrome des Nutzers.
        if _via_cdp:
            try:
                page.close()
            except Exception:
                pass
        else:
            ctx.close()

    _remaining_total = len(to_do) - processed_this_run
    if _stopped_early and _remaining_total > 0:
        print(f"\n✅  {total_imported} Shared Matches importiert "
              f"({processed_this_run} Match-Seiten verarbeitet).")
        print(f"   Noch ausstehend: {_remaining_total} Matches.")
        print("   Morgen erneut starten mit: --skip-done"
              + (f" --repair-threshold {repair_threshold}" if repair_threshold else ""))
    else:
        print(f"\n✅  {total_imported} Shared Matches importiert "
              f"({processed_this_run} Match-Seiten verarbeitet).")
    print("    DB: ancestry_dna.db")
