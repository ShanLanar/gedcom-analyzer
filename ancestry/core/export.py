"""
Export-Funktionen: CSV und XLSX (Matches + Shared Matches).
"""

import csv
import logging
from typing import Optional

from models import DnaMatch, SharedMatch

log = logging.getLogger(__name__)

MATCH_COLUMNS = [
    "display_name", "shared_cm", "shared_segments", "longest_segment",
    "predicted_relationship", "confidence", "relationship_range",
    "has_tree", "tree_size", "starred", "note", "custom_relationship",
    "ethnicity_regions", "last_login", "fetched_at", "match_guid",
]

SHARED_COLUMNS = [
    "match_guid_a", "display_name_b", "shared_cm_b", "shared_cm_ab",
    "shared_segments_b", "relationship_b", "has_tree_b",
    "match_guid_b", "fetched_at",
]

MATCH_LABELS = {
    "display_name"           : "Name",
    "shared_cm"              : "Gemeinsame cM",
    "shared_segments"        : "Segmente",
    "longest_segment"        : "Längstes Segment (cM)",
    "predicted_relationship" : "Beziehung (Ancestry)",
    "confidence"             : "Konfidenz",
    "relationship_range"     : "Beziehungsbereich",
    "has_tree"               : "Hat Stammbaum",
    "tree_size"              : "Stammbaum-Personen",
    "starred"                : "Markiert",
    "note"                   : "Notiz",
    "custom_relationship"    : "Eigene Beziehung",
    "ethnicity_regions"      : "Herkunftsregionen",
    "last_login"             : "Letzter Login",
    "fetched_at"             : "Abgerufen am",
    "match_guid"             : "Match-GUID",
}

SHARED_LABELS = {
    "match_guid_a"    : "Primärer Match (GUID)",
    "display_name_b"  : "Shared Match (Name)",
    "shared_cm_b"     : "cM (Benutzer ↔ Shared)",
    "shared_cm_ab"    : "cM (Primär ↔ Shared)",
    "shared_segments_b": "Segmente (Shared)",
    "relationship_b"  : "Beziehung (Shared)",
    "has_tree_b"      : "Stammbaum (Shared)",
    "match_guid_b"    : "Shared Match (GUID)",
    "fetched_at"      : "Abgerufen am",
}


def _fmt(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    if isinstance(val, bool):
        return "Ja" if val else "Nein"
    return str(val) if val is not None else ""


# ── CSV ───────────────────────────────────────────────────────────────────────

def export_csv(matches: list[DnaMatch], filepath: str) -> int:
    headers = [MATCH_LABELS.get(c, c) for c in MATCH_COLUMNS]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for m in matches:
            d = m.to_dict()
            w.writerow({MATCH_LABELS.get(c, c): _fmt(d.get(c, ""))
                        for c in MATCH_COLUMNS})
    log.info("CSV-Export Matches: %d → %s", len(matches), filepath)
    return len(matches)


def export_shared_csv(shared: list[SharedMatch], filepath: str,
                       match_name_map: Optional[dict] = None) -> int:
    """
    Exportiert Shared Matches als CSV.
    match_name_map: {match_guid_a: display_name} – optional für lesbaren Namen.
    """
    headers = ["Primärer Match (Name)"] + [SHARED_LABELS.get(c, c) for c in SHARED_COLUMNS]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for sm in shared:
            d = sm.to_dict()
            row = {"Primärer Match (Name)":
                   (match_name_map or {}).get(sm.match_guid_a, "")}
            for c in SHARED_COLUMNS:
                row[SHARED_LABELS.get(c, c)] = _fmt(d.get(c, ""))
            w.writerow(row)
    log.info("CSV-Export Shared Matches: %d → %s", len(shared), filepath)
    return len(shared)


# ── XLSX ──────────────────────────────────────────────────────────────────────

def _write_xlsx_sheet(ws, headers: list[str], rows: list[list], col_widths: list[int]):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        raise ImportError("openpyxl nicht installiert: pip install openpyxl")

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F4E79")
    alt_fill    = PatternFill("solid", fgColor="EBF0FA")
    thin_border = Border(bottom=Side(style="thin", color="CCCCCC"))

    for col_idx, (header, width) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font      = header_font
        cell.fill      = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    for row_idx, row_data in enumerate(rows, 2):
        fill = alt_fill if row_idx % 2 == 0 else None
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = thin_border
            if fill:
                cell.fill = fill

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def export_xlsx(matches: list[DnaMatch], filepath: str,
                shared: Optional[list[SharedMatch]] = None,
                match_name_map: Optional[dict] = None) -> int:
    """
    Exportiert Matches (und optional Shared Matches) in eine XLSX-Datei.
    Bei shared != None wird ein zweites Tabellenblatt angelegt.
    """
    try:
        import openpyxl
    except ImportError:
        raise ImportError("openpyxl nicht installiert: pip install openpyxl")

    wb = openpyxl.Workbook()

    # ── Blatt 1: Matches ──────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "DNA-Matches"
    headers1 = [MATCH_LABELS.get(c, c) for c in MATCH_COLUMNS]
    widths1  = [30, 14, 10, 18, 25, 12, 20, 12, 12, 10, 40, 20, 30, 20, 20, 36]
    rows1 = []
    for m in matches:
        d = m.to_dict()
        rows1.append([_fmt(d.get(c, "")) for c in MATCH_COLUMNS])
    _write_xlsx_sheet(ws1, headers1, rows1, widths1)

    # ── Blatt 2: Shared Matches (optional) ────────────────────────────────────
    if shared:
        ws2 = wb.create_sheet("Shared Matches")
        headers2 = ["Primärer Match"] + [SHARED_LABELS.get(c, c) for c in SHARED_COLUMNS]
        widths2  = [30, 36, 20, 18, 14, 16, 22, 12, 36, 20]
        rows2 = []
        for sm in shared:
            d = sm.to_dict()
            name_a = (match_name_map or {}).get(sm.match_guid_a, "")
            rows2.append([name_a] + [_fmt(d.get(c, "")) for c in SHARED_COLUMNS])
        _write_xlsx_sheet(ws2, headers2, rows2, widths2)

    wb.save(filepath)
    log.info("XLSX-Export: %d Matches, %d Shared → %s",
             len(matches), len(shared) if shared else 0, filepath)
    return len(matches)
