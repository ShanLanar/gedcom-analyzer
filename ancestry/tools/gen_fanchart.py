#!/usr/bin/env python3
"""CLI: Sosa-Fächerdiagramm als SVG aus GEDCOM-Datei erzeugen.
Usage: python -m ancestry.tools.gen_fanchart [--gedcom PATH] [--root ID] [--out PATH]
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
    ap = argparse.ArgumentParser(description="Sosa-Fächerdiagramm als SVG")
    ap.add_argument("--gedcom", default=cfg.DEFAULT_CONFIG.get("gedfile",""), help="GEDCOM-Datei")
    ap.add_argument("--root",   default=cfg.DEFAULT_CONFIG.get("root_id",""), help="Wurzel-ID")
    ap.add_argument("--out",    default="", help="Ausgabedatei (Standard: output/fan_chart.svg)")
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

    root_id = args.root
    if not root_id and individuals:
        root_id = next(iter(individuals))
        print(f"  Keine Wurzel angegeben, nehme ersten Eintrag: {root_id}")
    if not root_id:
        print("FEHLER: Keine Wurzel-ID. --root angeben.")
        sys.exit(1)

    out_dir = cfg.DIRS.get("output", "output")
    out_path = args.out or os.path.join(out_dir, "fan_chart.svg")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    from tasks.export_fanchart import export_fanchart_svg
    print(f"Erstelle Fächerdiagramm für {root_id} …")
    export_fanchart_svg(root_id, individuals, families, out_path)
    print(f"✓ Gespeichert: {out_path}")

if __name__ == "__main__":
    main()
