"""
Download-Skript für das zweite DNA-Kit (Mutter).

Liest Cookies aus data/mother_cookies.json, authentifiziert sich,
erkennt das Kit und lädt Matches in die gemeinsame DB (ancestry_dna.db).
Die Matches landen als separater test_guid, sodass die Seitenableitung
(väterlich/mütterlich) via Überlappungs-Vergleich funktioniert.

WICHTIG: Dieses Skript muss auf der gleichen Maschine laufen, auf der
die Cookies exportiert wurden (gleiche IP → Cloudflare-Check bestanden).

Vorbereitung:
    1. Cookies in data/mother_cookies.json ablegen (bereits erledigt)
    2. Ggf. erneuern wenn SecureATT-JWT abgelaufen (30-Min-Token):
       → Auf ancestry.com einloggen → Cookie-Editor → Export All

Aufruf:
    cd ancestry
    python tools/download_mother_kit.py
    python tools/download_mother_kit.py --only-new  # nur neue Matches
"""

import argparse
import logging
import os
import sys
import time

from ancestry.core.auth import AncestryAuth
from ancestry.core.api  import AncestryApiClient
from ancestry.core.database import Database
from ancestry.core.scraper  import Scraper
from ancestry.models import DnaKit
from ancestry.paths import DB_PATH, DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("download_mother")

COOKIE_FILE = str(DATA_DIR / "mother_cookies.json")
DB_FILE     = str(DB_PATH)


def _progress(fetched, total, label):
    pct = f"{fetched/max(total,1)*100:.0f}%" if total else ""
    print(f"\r  {label}: {fetched}/{total or '?'} {pct}    ", end="", flush=True)


def _status(msg):
    print(f"\n[Status] {msg}")


def _check_jwt(session) -> int:
    """Gibt verbleibende Sekunden des SecureATT JWT zurück (negativ = abgelaufen)."""
    import base64
    import json as _json
    import time as _time
    try:
        jwt = session.cookies.get("SecureATT", domain="www.ancestry.com") or ""
        if not jwt:
            jwt = session.cookies.get("SecureATT") or ""
        if not jwt:
            return 0
        parts = jwt.split(".")
        if len(parts) < 2:
            return 0
        pad = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(pad))
        return int(payload.get("exp", 0)) - int(_time.time())
    except Exception:
        return 0


def _find_kit_from_pages(session) -> str:
    """Versucht die Kit-GUID aus den DNA-Seiten zu extrahieren."""
    import re
    patterns = [
        r'discoveryui-matches/list/([0-9A-Fa-f\-]{32,})',
        r'"testGuid"\s*:\s*"([0-9A-Fa-f\-]{32,})"',
        r'"sampleId"\s*:\s*"([0-9A-Fa-f\-]{32,})"',
    ]
    urls = [
        "https://www.ancestry.com/discoveryui-matches/list/",
        "https://www.ancestry.com/dna/home",
        "https://www.ancestry.com/dna/insights",
    ]
    for url in urls:
        try:
            r = session.get(url, timeout=15)
            if r.status_code == 200:
                for pat in patterns:
                    m = re.search(pat, r.text)
                    if m:
                        return m.group(1)
        except Exception:
            pass
    return ""


def main():
    ap = argparse.ArgumentParser(description="Mutter-Kit herunterladen")
    ap.add_argument("--kit-guid",  type=str,   default="",
                    help="Kit-GUID manuell angeben (URL: .../discoveryui-matches/list/{GUID})")
    ap.add_argument("--kit-name",  type=str,   default="Mutter-Kit",
                    help="Anzeigename für dieses Kit (Standard: Mutter-Kit)")
    ap.add_argument("--min-cm",    type=float, default=0.0,
                    help="Nur Matches ab dieser cM-Zahl (Standard: 0)")
    ap.add_argument("--only-new",  action="store_true",
                    help="Nur neue Matches laden (bereits vorhandene überspringen)")
    args = ap.parse_args()

    # ── Authentifizierung ──────────────────────────────────────────────────────
    cookie_path = os.path.abspath(COOKIE_FILE)
    if not os.path.exists(cookie_path):
        log.error("Cookie-Datei nicht gefunden: %s", cookie_path)
        sys.exit(1)

    log.info("Lade Cookies aus %s …", cookie_path)
    auth = AncestryAuth()
    if not auth.login_cookies(cookie_path):
        log.error("Authentifizierung fehlgeschlagen.")
        sys.exit(1)

    uid = auth.uid or ""
    log.info("Authentifiziert. UID: %s", uid[:20] if uid else "(unbekannt)")

    # ── JWT-Gültigkeit prüfen ──────────────────────────────────────────────────
    remaining = _check_jwt(auth.get_session())
    if remaining < 0:
        log.error(
            "SecureATT JWT abgelaufen (vor %d Sekunden = %.1f Minuten).\n"
            "  Das ist der Grund für 303-Fehler beim Match-Download.\n\n"
            "  Lösung (sofort):\n"
            "  1. ancestry.com im Browser öffnen → als Mutter eingeloggt bleiben\n"
            "  2. DNA-Matches-Seite aufrufen (damit JWT erneuert wird)\n"
            "  3. Cookie-Editor → Export All → data/mother_cookies.json überschreiben\n"
            "  4. Script SOFORT ausführen (JWT nur 30 Minuten gültig!)\n",
            -remaining, -remaining / 60,
        )
        sys.exit(1)
    elif remaining > 0:
        log.info("JWT noch %d Sekunden gültig (%.1f Minuten)", remaining, remaining / 60)
    else:
        log.warning("JWT-Status unbekannt (kein SecureATT-Cookie gefunden).")

    # ── Kit ermitteln ──────────────────────────────────────────────────────────
    client = AncestryApiClient(auth.get_session())
    kit_guid = args.kit_guid.strip()

    if not kit_guid:
        # Versuch 1: API via UID
        kits = []
        for try_uid in filter(None, [uid, auth.get_session().cookies.get("LAU")]):
            kits = client.get_dna_kits(try_uid)
            if kits:
                break
            g = client.detect_kit_from_uid(try_uid)
            if g:
                kits = [DnaKit(guid=g, name=args.kit_name)]
                break

        if kits:
            kit_guid = kits[0].guid
            log.info("Kit via API erkannt: %s", kit_guid)

    if not kit_guid:
        # Versuch 2: aus DNA-Seiten extrahieren
        log.info("Suche Kit-GUID aus DNA-Seiten …")
        kit_guid = _find_kit_from_pages(auth.get_session())
        if kit_guid:
            log.info("Kit aus Seite extrahiert: %s", kit_guid)

    if not kit_guid:
        log.error(
            "Kit-GUID konnte nicht automatisch ermittelt werden.\n"
            "\n"
            "  Lösung: GUID manuell angeben:\n"
            "  1. Auf ancestry.com als Mutter einloggen\n"
            "  2. DNA-Matches aufrufen\n"
            "  3. URL lautet: .../discoveryui-matches/list/{GUID}\n"
            "  4. GUID aus URL kopieren und übergeben:\n"
            "\n"
            "     python tools/download_mother_kit.py --kit-guid XXXXXXXX-XXXX-...\n"
        )
        sys.exit(1)

    log.info("Verwende Kit-GUID: %s", kit_guid)

    # ── Session aufwärmen (DNA-Seite besuchen → CSRF + JWT frisch) ────────────
    log.info("Wärme Session auf (besuche DNA-Seite) …")
    _session = auth.get_session()
    for _warm_url in [
        f"https://www.ancestry.com/discoveryui-matches/list/{kit_guid}",
        "https://www.ancestry.com/dna/home",
    ]:
        try:
            _r = _session.get(_warm_url, timeout=15)
            log.info("  %s → %s", _warm_url[:60], _r.status_code)
            if _r.status_code == 200:
                # Log CSRF cookies present after warmup
                for _cname in ("_dnamatches-matchlistui-x-csrf-token", "_csrf"):
                    try:
                        _cv = _session.cookies.get(_cname, domain="www.ancestry.com")
                        if _cv:
                            log.info("  CSRF %s: %s…", _cname[:40], str(_cv)[:20])
                    except Exception:
                        pass
                break
        except Exception as _e:
            log.warning("  Warmup-Fehler: %s", _e)

    # ── Datenbank ──────────────────────────────────────────────────────────────
    db = Database(os.path.abspath(DB_FILE))
    db.upsert_kit(DnaKit(
        guid=kit_guid,
        name=args.kit_name,
        test_type="AncestryDNA",
        created_date="",
        is_owner=False,
    ))
    log.info("Kit in DB gespeichert: %s (%s)", args.kit_name, kit_guid[:16])

    # ── Matches laden ──────────────────────────────────────────────────────────
    done = {"ok": False}

    def _on_done(result):
        done["ok"] = result.success
        print()
        log.info("Download abgeschlossen: %d geladen, %d neu, %d Fehler",
                 result.fetched, result.new, result.errors)

    scraper = Scraper(
        client=client,
        db=db,
        on_progress=_progress,
        on_status=_status,
        on_done=_on_done,
    )

    log.info("Starte Match-Download für Kit %s …", kit_guid[:16])
    scraper.start_matches(
        test_guid=kit_guid,
        filter_by="ALL",
        sort_by="RELATIONSHIP",
        only_new=args.only_new,
    )

    # Warten bis fertig
    while scraper._thread and scraper._thread.is_alive():
        time.sleep(2)

    db.close()
    if done["ok"]:
        log.info("Fertig. Mutter-Kit-Matches in DB: %s", DB_FILE)
    else:
        log.warning("Download endete mit Fehlern.")
    return 0 if done["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
