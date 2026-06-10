#!/usr/bin/env python3
"""
Ancestry DNA Tool – Einstiegspunkt.

Startet die grafische Oberfläche oder (mit --cli) den reinen
Kommandozeilen-Modus für Batch-Downloads.

Verwendung:
  python main.py                              # GUI
  python main.py --cli --guid <KIT-GUID>     # Kommandozeile
"""

import argparse
import sys

from ancestry.paths import DB_PATH, LOG_DIR
from ancestry.endpoints import LOG_LEVEL
from ancestry.utils import setup_logging, get_logger


def run_gui(gedcom_path: str = ""):
    """Startet die Tkinter-GUI."""
    try:
        import tkinter as tk
    except ImportError:
        print("FEHLER: tkinter ist nicht verfügbar. "
              "Bitte Python mit Tk-Unterstützung installieren.", file=sys.stderr)
        sys.exit(1)

    from gui.app import AncestryDnaApp
    app = AncestryDnaApp(gedcom_path=gedcom_path)
    app.mainloop()


def run_cli(args: argparse.Namespace):
    """Führt einen Download ohne GUI aus (Headless-Modus)."""
    log = get_logger("cli")
    from core.auth import AncestryAuth
    from core.api import AncestryApiClient
    from core.database import Database
    from core.scraper import Scraper
    import threading

    auth = AncestryAuth()

    # Login
    if args.cookie_file:
        ok = auth.login_cookies(args.cookie_file)
    elif args.email and args.password:
        ok = auth.login_password(args.email, args.password)
    else:
        log.error("Bitte --email + --password oder --cookie-file angeben.")
        sys.exit(1)

    if not ok:
        log.error("Login fehlgeschlagen.")
        sys.exit(1)

    client = AncestryApiClient(auth.get_session())
    db     = Database(str(DB_PATH))

    guid = args.guid
    if not guid and auth.uid:
        guid = client.detect_kit_from_uid(auth.uid)
    if not guid:
        log.error("Keine Kit-GUID. Bitte mit --guid angeben.")
        sys.exit(1)

    done_event = threading.Event()
    result_holder = []

    def on_done(result):
        result_holder.append(result)
        done_event.set()

    scraper = Scraper(
        client    = client,
        db        = db,
        on_status = lambda m: log.info("Status: %s", m),
        on_done   = on_done,
    )
    scraper.start(guid, args.filter or "ALL", args.sort or "RELATIONSHIP")
    done_event.wait()

    if result_holder and result_holder[0].success:
        log.info("Download erfolgreich.")
    else:
        log.error("Download fehlgeschlagen oder abgebrochen.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Ancestry DNA Tool")
    parser.add_argument("--cli",         action="store_true",
                        help="Kommandozeilen-Modus (kein GUI)")
    parser.add_argument("--guid",        help="Kit-GUID (DNA-Test-ID)")
    parser.add_argument("--email",       help="Ancestry-E-Mail (für automatischen Login)")
    parser.add_argument("--password",    help="Ancestry-Passwort")
    parser.add_argument("--cookie-file", help="Cookie-JSON-Datei (Cookie-Editor-Export)",
                        dest="cookie_file")
    parser.add_argument("--filter",      choices=["ALL", "STARRED", "CLOSE", "DISTANT"],
                        default="ALL")
    parser.add_argument("--sort",        choices=["RELATIONSHIP", "SHARED_CM"],
                        default="RELATIONSHIP")
    parser.add_argument("--log-level",   default=LOG_LEVEL,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--gedcom",      default="",
                        help="GEDCOM-Datei, die automatisch als Stammbaum vorbelegt wird")

    args = parser.parse_args()
    setup_logging(str(LOG_DIR / "ancestry_dna.log"), args.log_level)

    if args.cli:
        run_cli(args)
    else:
        run_gui(gedcom_path=args.gedcom or "")


if __name__ == "__main__":
    main()
