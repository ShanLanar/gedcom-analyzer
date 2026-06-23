#!/usr/bin/env python3
"""CLI: Interaktives HTML-Dashboard aus GEDCOM-Datei erzeugen.
Usage: python -m ancestry.tools.gen_dashboard [--gedcom PATH] [--out PATH]
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg
cfg.apply_overrides()

def main():
    ap = argparse.ArgumentParser(description="HTML-Dashboard erzeugen")
    ap.add_argument("--gedcom", default=cfg.DEFAULT_CONFIG.get("gedfile",""), help="GEDCOM-Datei")
    ap.add_argument("--out",    default="", help="Ausgabedatei (Standard: output/dashboard.html)")
    args = ap.parse_args()

    gedcom_path = args.gedcom
    if not gedcom_path or not os.path.exists(gedcom_path):
        print(f"FEHLER: GEDCOM-Datei nicht gefunden: {gedcom_path!r}")
        print("  --gedcom <Pfad> angeben oder config.py / config_user.json setzen")
        sys.exit(1)

    from lib.gedcom import robust_load_gedcom
    print(f"Lade GEDCOM: {gedcom_path}")
    individuals, families = robust_load_gedcom(gedcom_path)
    print(f"  → {len(individuals)} Personen, {len(families)} Familien")

    out_dir = cfg.DIRS.get("output", "output")
    out_path = args.out or os.path.join(out_dir, "dashboard.html")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    state = {"individuals": individuals, "families": families}

    from tasks.export_dashboard import export_dashboard_html
    print("Erstelle HTML-Dashboard …")
    export_dashboard_html(state, out_path,
                          progress_cb=lambda msg, **_: print(f"  {msg}"))
    print(f"✓ Gespeichert: {out_path}")

if __name__ == "__main__":
    main()
