#!/usr/bin/env python3
"""
MyHeritage Shared-Matches-Scraper — backward-compat shim.

The implementation has moved to ancestry/tools/fetch_mh/.
This file is kept so that existing scripts/references continue to work.
"""
from __future__ import annotations

from ancestry.tools.fetch_mh import scrape  # noqa: F401

__all__ = ["scrape"]


def main() -> None:
    import argparse

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
    ap.add_argument("--extension", default="",
                    help="Pfad ODER Chrome-Extension-ID der Browser-Erweiterung "
                         "(z.B. Genealogy Assistant 'knnjkkdihbjonnkmajijmnfblpbopapk') "
                         "für 'Download CSV (all pages)'")
    ap.add_argument("--extension-id", default="",
                    help="Alias für --extension: Chrome-Extension-ID; Ordner wird "
                         "automatisch im Chrome/Edge-Profil gesucht")
    ap.add_argument("--wait-login", action="store_true",
                    help="Nach dem Aufwärmen pausieren (ENTER), um im sichtbaren "
                         "Browser die Erweiterung zu verifizieren/einzuloggen")
    ap.add_argument("--cdp", nargs="?", const="http://127.0.0.1:9222", default="",
                    help="An ein laufendes Chrome anhängen (Remote-Debugging). "
                         "Nutzt dessen bereits installierte/verifizierte Erweiterung "
                         "und Session. Standard-URL: http://127.0.0.1:9222")
    ap.add_argument("--repair-threshold", type=int, default=0, metavar="N",
                    help="Reparatur-Modus: Matches die bereits verarbeitet wurden, "
                         "aber ≤ N Shared Matches in der DB haben, werden erneut geladen. "
                         "Sinnvoll wenn bei einem Lauf nur die erste Seite (10 Ergebnisse) "
                         "abgefangen wurde (Extension fehlte). Empfehlung: --repair-threshold 10")
    ap.add_argument("--max-per-run", type=int, default=0, metavar="N",
                    help="Tages-Limit: nach N erfolgreich verarbeiteten Matches stoppen. "
                         "Verhindert Sperren durch Daily-Limits. Morgen --skip-done nutzen "
                         "um dort weiterzumachen. Empfehlung: --max-per-run 50 (oder 100)")
    args = ap.parse_args()

    scrape(
        csv_path         = args.csv,
        min_cm           = args.min_cm,
        limit            = args.limit,
        headless         = not args.visible,
        pause            = args.pause,
        skip_done        = not args.no_skip,
        profile_dir      = args.profile_dir or None,
        cookies_path     = args.cookies or None,
        debug            = args.debug,
        extension_dir    = args.extension or args.extension_id or None,
        wait_login       = args.wait_login,
        cdp_url          = args.cdp or None,
        repair_threshold = args.repair_threshold,
        max_per_run      = args.max_per_run,
    )


if __name__ == "__main__":
    main()
