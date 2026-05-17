# -*- coding: utf-8 -*-
"""tasks/export.py – Excel- und JSON-Export aller Analyse-Sheets"""

import json
import os
from datetime import datetime

_logger = None

def set_logger(lg):
    global _logger
    _logger = lg

def _p(msg, tag=""):
    if _logger:
        {"ok": _logger.info, "warn": _logger.warning,
         "err": _logger.error}.get(tag, _logger.info)(msg)
    else:
        print(msg)


# ── Excel-Export ───────────────────────────────────────────────────────────────

def export_to_excel(all_sheets: list, output_path: str,
                    progress_cb=None) -> bool:
    """
    Schreibt eine Excel-Datei mit einem Sheet pro Eintrag in all_sheets.
    all_sheets = [(sheet_name, [headers], [rows]), ...]
    """
    p = progress_cb or (lambda m, **kw: None)
    p(f"Erstelle Excel: {output_path} …")
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        p("openpyxl nicht verfügbar – bitte installieren: pip install openpyxl",
          tag="err")
        return False

    wb = Workbook()
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])

    header_fill = PatternFill(start_color="366092", end_color="366092",
                               fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    alt_fill    = PatternFill(start_color="F2F2F2", end_color="F2F2F2",
                               fill_type="solid")

    for sheet_name, headers, data in all_sheets:
        if not data:
            continue
        try:
            ws = wb.create_sheet(title=sheet_name[:31])
            ws.append(headers)
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            for ri, row in enumerate(data[:200_000], start=2):
                ws.append(row)
                if ri % 2 == 0:
                    for cell in ws[ri]:
                        cell.fill = alt_fill

            # Spaltenbreiten
            for ci in range(1, len(headers) + 1):
                max_len = len(str(headers[ci - 1]))
                for ri2 in range(2, min(len(data) + 2, 100)):
                    v = ws.cell(row=ri2, column=ci).value
                    if v: max_len = max(max_len, len(str(v)))
                ws.column_dimensions[get_column_letter(ci)].width = min(max_len + 2, 50)

            ws.freeze_panes = "A2"
            p(f"  ✓ Sheet '{sheet_name[:31]}': {len(data)} Zeilen")

        except Exception as e:
            p(f"Fehler bei Sheet '{sheet_name}': {e}", tag="warn")

    try:
        wb.save(output_path)
        size_mb = os.path.getsize(output_path) / 1_048_576
        p(f"Excel gespeichert: {output_path} ({size_mb:.1f} MB)", tag="ok")
        return True
    except Exception as e:
        p(f"Fehler beim Speichern von Excel: {e}", tag="err")
        return False


# ── JSON-Export ────────────────────────────────────────────────────────────────

def export_to_json(data: dict, output_path: str, progress_cb=None) -> bool:
    p = progress_cb or (lambda m, **kw: None)
    p(f"JSON-Export: {output_path} …")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        size_mb = os.path.getsize(output_path) / 1_048_576
        p(f"JSON gespeichert: {output_path} ({size_mb:.1f} MB)", tag="ok")
        return True
    except Exception as e:
        p(f"Fehler beim JSON-Export: {e}", tag="err")
        return False


# ── Sheet-Definitionen ─────────────────────────────────────────────────────────

def build_symbol_sheet(individuals) -> tuple:
    return ("Symbol-Statistik", ["Symbol", "Bedeutung", "Anzahl"], [
        ["✠", "Deutsche Soldaten",
         sum(1 for i in individuals.values() if i.get("GERMAN_SOLDIER"))],
        ["★", "Andere Soldaten",
         sum(1 for i in individuals.values() if i.get("OTHER_SOLDIER"))],
        ["⚔", "Gefallene",
         sum(1 for i in individuals.values() if i.get("DIED_IN_BATTLE"))],
        ["‡", "Linie endet",
         sum(1 for i in individuals.values() if i.get("LINE_ENDS"))],
        ["mig.", "Migriert (markiert)",
         sum(1 for i in individuals.values() if i.get("MIGRATED"))],
    ])


def build_gedcom_events_sheet(individuals) -> tuple:
    return ("GEDCOM-Events", ["Event-Typ", "Anzahl", "Beschreibung"], [
        ["EMIG",
         sum(1 for i in individuals.values() if i.get("EMIG", {}).get("DATE")),
         "Auswanderung (EMIG Event)"],
        ["IMMI",
         sum(1 for i in individuals.values() if i.get("IMMI", {}).get("DATE")),
         "Einwanderung (IMMI Event)"],
        ["mig. im Namen",
         sum(1 for i in individuals.values()
             if "mig." in (i.get("NAME") or "").lower()),
         "mig. im Namen markiert"],
    ])


def build_location_info_sheet(location_data: dict) -> tuple:
    countries = len(location_data.get("countries", {}))
    states = sum(len(c.get("states", {}))
                 for c in location_data.get("countries", {}).values())
    return ("Ortsdaten-Info", ["Kategorie", "Anzahl", "Beschreibung"], [
        ["Länder", countries, "Anzahl der definierten Länder"],
        ["Bundesstaaten", states, "Gesamtzahl der Bundesstaaten/Provinzen"],
        ["Bezirks-Indikatoren",
         len(location_data.get("district_indicators", [])),
         "Wörter zur Bezirkserkennung"],
        ["Provinz-Indikatoren",
         len(location_data.get("province_indicators", [])),
         "Wörter zur Provinz/Region-Erkennung"],
    ])
