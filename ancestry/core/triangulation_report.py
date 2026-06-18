"""Druckbarer Triangulations-Forschungsbericht (HTML, „als PDF drucken").

Dependency-frei: erzeugt eine eigenständige HTML-Seite mit @media-print-CSS,
die der Browser per „Drucken → Als PDF speichern" zu einem PDF macht – analog
zu export_heatmap/mrca_map, ohne reportlab/weasyprint.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone


def _mbp(pos) -> str:
    try:
        return f"{int(pos) / 1_000_000:.1f}"
    except (TypeError, ValueError):
        return "?"


def build_triangulation_report_html(tgs: list, name_by_guid: dict | None = None,
                                    title: str = "Triangulations-Bericht",
                                    kit_label: str = "") -> str:
    """Erzeugt den HTML-Bericht für eine Liste von Triangulationsgruppen.

    tgs:          wie build_triangulation_groups() liefert (chromosome,
                  chromosome_label, region_start/-_end, members[]).
    name_by_guid: optionale {match_guid: Anzeigename}-Auflösung.
    """
    names = name_by_guid or {}
    n_tg = len(tgs)
    total_members = sum(len(t.get("members", [])) for t in tgs)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = []
    for i, tg in enumerate(sorted(tgs, key=lambda t: (-len(t.get("members", [])),
                                                      t.get("chromosome", 0))), 1):
        members = tg.get("members", [])
        chrom = html.escape(str(tg.get("chromosome_label") or tg.get("chromosome", "?")))
        region = f"{_mbp(tg.get('region_start'))}–{_mbp(tg.get('region_end'))} Mbp"
        mem_rows = []
        for m in sorted(members, key=lambda x: -(x.get("length_cm") or 0)):
            guid = m.get("match_guid", "")
            nm = html.escape(names.get(guid, guid[:12] or "?"))
            cm = m.get("length_cm") or 0
            mem_rows.append(
                f"<tr><td>{nm}</td><td class='num'>{cm:.1f}</td>"
                f"<td class='num'>{_mbp(m.get('start'))}–{_mbp(m.get('end'))}</td></tr>")
        rows.append(
            f"<section class='tg'>"
            f"<h2>TG&nbsp;{i} · Chr&nbsp;{chrom} · {region} · "
            f"{len(members)} Mitglieder</h2>"
            f"<table><thead><tr><th>Match</th><th class='num'>cM</th>"
            f"<th class='num'>Segment (Mbp)</th></tr></thead>"
            f"<tbody>{''.join(mem_rows)}</tbody></table></section>")

    css = (
        "body{font-family:'Segoe UI',sans-serif;color:#222;margin:24px;}"
        "h1{font-size:20px;margin:0 0 2px;}"
        ".meta{color:#666;font-size:12px;margin-bottom:16px;}"
        ".tg{break-inside:avoid;margin:0 0 14px;border:1px solid #ddd;"
        "border-radius:6px;padding:8px 12px;}"
        ".tg h2{font-size:13px;margin:0 0 6px;color:#1F4E79;}"
        "table{border-collapse:collapse;width:100%;font-size:12px;}"
        "th,td{border-bottom:1px solid #eee;padding:3px 6px;text-align:left;}"
        ".num{text-align:right;font-variant-numeric:tabular-nums;}"
        "@media print{.tg{border-color:#bbb;}body{margin:0;}}"
    )
    header = (
        f"<h1>{html.escape(title)}</h1>"
        f"<div class='meta'>{html.escape(kit_label)} · {n_tg} Triangulationsgruppen · "
        f"{total_members} Segment-Mitgliedschaften · erstellt {when}</div>")
    body = "".join(rows) or "<p>Keine Triangulationsgruppen gefunden.</p>"
    return ("<!DOCTYPE html>\n<html lang='de'><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title><style>{css}</style></head>"
            f"<body>{header}{body}</body></html>")
