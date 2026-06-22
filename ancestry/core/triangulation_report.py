"""Druckbarer Triangulations-Forschungsbericht (HTML, „als PDF drucken").

Generiert eine eigenständige HTML-Seite mit @media-print-CSS,
die der Browser per „Drucken → Als PDF speichern" zu einem PDF macht.

Optional: Matplotlib-Charts (cM-Verteilung pro TG) als embedded base64-PNG.
Falls Matplotlib nicht verfügbar, wird auf Text-Tabellen zurückgegriffen.
"""
from __future__ import annotations

import base64
import html
import io
from datetime import datetime, timezone


def _mbp(pos) -> str:
    try:
        return f"{int(pos) / 1_000_000:.1f}"
    except (TypeError, ValueError):
        return "?"


def _generate_cm_distribution_chart(members: list) -> str | None:
    """Erzeugt ein base64-encoded PNG eines Balkendiagramms der cM-Verteilung.

    Falls Matplotlib nicht vorhanden oder Fehler, gibt None zurück.
    """
    if not members:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")  # Headless rendering
        import matplotlib.pyplot as plt

        names = []
        cms = []
        for m in sorted(members, key=lambda x: -(x.get("length_cm") or 0)):
            guid = m.get("match_guid", "?")
            # Kurzer Name für Diagramm (erste 20 Zeichen)
            short_name = guid[:20] if len(guid) > 20 else guid
            names.append(short_name)
            cms.append(m.get("length_cm") or 0)

        fig, ax = plt.subplots(figsize=(8, 3), dpi=100)
        colors = ["#1a73e8" if i == 0 else "#e8a81a" for i in range(len(names))]
        ax.bar(range(len(names)), cms, color=colors)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("cM", fontsize=9)
        ax.set_title("cM-Verteilung", fontsize=10, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()

        # In memory buffer zu PNG
        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)

        # Base64 encoding für HTML embed
        b64 = base64.b64encode(buf.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except ImportError:
        return None
    except Exception:
        return None


def build_triangulation_report_html(tgs: list, name_by_guid: dict | None = None,
                                    title: str = "Triangulations-Bericht",
                                    kit_label: str = "",
                                    include_charts: bool = True) -> str:
    """Erzeugt den HTML-Bericht für eine Liste von Triangulationsgruppen.

    tgs:            wie build_triangulation_groups() liefert (chromosome,
                    chromosome_label, region_start/-_end, members[]).
    name_by_guid:   optionale {match_guid: Anzeigename}-Auflösung.
    include_charts: falls True und matplotlib verfügbar, generiert cM-Balkendiagramme.
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

        # Optional: cM-Verteilung Chart
        chart_html = ""
        if include_charts:
            chart_data = _generate_cm_distribution_chart(members)
            if chart_data:
                chart_html = (
                    f"<figure class='chart'>"
                    f"<img src='{chart_data}' alt='cM-Verteilung'>"
                    f"</figure>")

        rows.append(
            f"<section class='tg'>"
            f"<h2>TG&nbsp;{i} · Chr&nbsp;{chrom} · {region} · "
            f"{len(members)} Mitglieder</h2>"
            f"{chart_html}"
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
        ".chart{margin:6px 0;text-align:center;break-inside:avoid;}"
        ".chart img{max-width:100%;height:auto;border:1px solid #f0f0f0;border-radius:4px;}"
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
