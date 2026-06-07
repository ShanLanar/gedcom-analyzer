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

# ancestry/ in Pfad
_HERE = os.path.dirname(os.path.abspath(__file__))
_ANCS = os.path.dirname(_HERE)
sys.path.insert(0, _ANCS)

from core.auth import AncestryAuth
from core.api  import AncestryApiClient
from core.database import Database
from core.scraper   import Scraper
from models import DnaKit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("download_mother")

COOKIE_FILE = os.path.join(_HERE, "..", "data", "mother_cookies.json")
DB_FILE     = os.path.join(_HERE, "..", "ancestry_dna.db")


def _progress(fetched, total, label):
    pct = f"{fetched/max(total,1)*100:.0f}%" if total else ""
    print(f"\r  {label}: {fetched}/{total or '?'} {pct}    ", end="", flush=True)


def _status(msg):
    print(f"\n[Status] {msg}")


def main():
    ap = argparse.ArgumentParser(description="Mutter-Kit herunterladen")
    ap.add_argument("--min-cm",    type=float, default=0.0,
                    help="Nur Matches ab dieser cM-Zahl (Standard: 0)")
    ap.add_argument("--max-pages", type=int,   default=9999,
                    help="Maximale Seiten (für Tests)")
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

    # ── Kit ermitteln ──────────────────────────────────────────────────────────
    client = AncestryApiClient(auth.get_session())
    kits = []
    if uid:
        kits = client.get_dna_kits(uid)
    if not kits and uid:
        guid = client.detect_kit_from_uid(uid)
        if guid:
            kits = [DnaKit(guid=guid, name="Mutter-Kit")]
    if not kits:
        # LAU-Cookie als UID-Fallback
        lau = auth.get_session().cookies.get("LAU")
        if lau:
            log.info("Versuche Kit-Erkennung via LAU-Cookie: %s", lau[:20])
            guid = client.detect_kit_from_uid(lau)
            if guid:
                kits = [DnaKit(guid=guid, name="Mutter-Kit")]

    if not kits:
        log.error("Kein DNA-Kit gefunden. Session möglicherweise abgelaufen.")
        sys.exit(1)

    kit = kits[0]
    log.info("Kit erkannt: %s (GUID: %s)", kit.name or "Mutter", kit.guid)

    # ── Datenbank ──────────────────────────────────────────────────────────────
    db = Database(os.path.abspath(DB_FILE))
    db.upsert_kit(DnaKit(
        guid=kit.guid,
        name=kit.name or "Mutter-Kit",
        test_type=kit.test_type or "AncestryDNA",
        created_date=kit.created_date or "",
        is_owner=False,
    ))
    log.info("Kit in DB gespeichert.")

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

    log.info("Starte Match-Download für Kit %s …", kit.guid[:16])
    scraper.start_matches(
        test_guid=kit.guid,
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
