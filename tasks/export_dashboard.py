# -*- coding: utf-8 -*-
"""tasks/export_dashboard.py – HTML-Dashboard mit Chart.js und Tab-Navigation.

Erzeugt eine eigenständige HTML-Datei mit dunklem Theme und sechs Tabs
(Übersicht, Demografie, Migration, Namen, Geografie, Genetik), die alle
relevanten Auswertungs-Ergebnisse aus dem Runner-State visualisiert.
"""

import os
import html
import json
from collections import Counter
from lib.gedcom import safe_extract_year


# ── Theme / Konstanten ────────────────────────────────────────────────────────

_BG          = "#1e1e2e"
_BG_PANEL    = "#181825"
_BG_CARD     = "#252537"
_FG          = "#cdd6f4"
_ACCENT      = "#7c7cf8"
_ACCENT_2    = "#f5a97f"
_MUTED       = "#9399b2"
_OK          = "#a6e3a1"
_WARN        = "#f9e2af"
_ERR         = "#f38ba8"

_CHARTJS_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"

_PALETTE = [
    "#7c7cf8", "#f5a97f", "#a6e3a1", "#f9e2af", "#f38ba8",
    "#94e2d5", "#cba6f7", "#89b4fa", "#fab387", "#74c7ec",
]


# ── State-Extraktion ──────────────────────────────────────────────────────────

def _state_get(state, key, default=None):
    """Defensive Lookup-Funktion: arbeitet mit Dict oder Objekt."""
    if state is None:
        return default
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _persons_by_century(individuals: dict) -> dict:
    counter: Counter = Counter()
    for pdata in individuals.values():
        birt = pdata.get("BIRT") or {}
        y = birt.get("YEAR") or safe_extract_year(birt.get("DATE"))
        if not y:
            continue
        century = (y // 100) * 100
        counter[century] += 1
    return dict(sorted(counter.items()))


def _sex_distribution(individuals: dict) -> dict:
    counter: Counter = Counter()
    for pdata in individuals.values():
        sex = (pdata.get("SEX") or "U").upper()
        if sex not in ("M", "F"):
            sex = "U"
        counter[sex] += 1
    return {
        "Männlich":  counter.get("M", 0),
        "Weiblich":  counter.get("F", 0),
        "Unbekannt": counter.get("U", 0),
    }


def _birth_year_range(individuals: dict) -> tuple:
    years = []
    for pdata in individuals.values():
        birt = pdata.get("BIRT") or {}
        y = birt.get("YEAR") or safe_extract_year(birt.get("DATE"))
        if y:
            years.append(y)
    if not years:
        return (None, None)
    return (min(years), max(years))


# ── Chart-Daten-Aufbereitung ──────────────────────────────────────────────────

def _coerce_pairs(obj) -> list:
    """Wandelt ein Dict oder Liste von Paaren in [(label, value), ...] um."""
    if obj is None:
        return []
    if isinstance(obj, dict):
        return [(str(k), v) for k, v in obj.items() if isinstance(v, (int, float))]
    if isinstance(obj, (list, tuple)):
        out = []
        for item in obj:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    out.append((str(item[0]), float(item[1])))
                except (TypeError, ValueError):
                    continue
        return out
    return []


def _extract_lifespan_per_epoch(demographic_results) -> tuple:
    """Liefert (labels, values) für durchschnittliche Lebensdauer je Epoche."""
    if not demographic_results:
        return ([], [])
    # Übliche Form: Dict mit "lifespan_per_epoch" / "epochs" / etc.
    if isinstance(demographic_results, dict):
        for key in ("lifespan_per_epoch", "avg_lifespan_per_epoch",
                    "lebensdauer_pro_epoche", "epochs"):
            data = demographic_results.get(key)
            pairs = _coerce_pairs(data)
            if pairs:
                return ([p[0] for p in pairs], [p[1] for p in pairs])
    return ([], [])


def _extract_marriage_age(demographic_results) -> tuple:
    if not demographic_results:
        return ([], [])
    if isinstance(demographic_results, dict):
        for key in ("marriage_age_per_epoch", "avg_marriage_age",
                    "heiratsalter_pro_epoche"):
            data = demographic_results.get(key)
            pairs = _coerce_pairs(data)
            if pairs:
                return ([p[0] for p in pairs], [p[1] for p in pairs])
    return ([], [])


def _extract_migration_per_decade(migration_waves) -> tuple:
    if not migration_waves:
        return ([], [])
    if isinstance(migration_waves, dict):
        for key in ("per_decade", "waves", "pro_dekade", "decades"):
            pairs = _coerce_pairs(migration_waves.get(key))
            if pairs:
                return ([p[0] for p in pairs], [p[1] for p in pairs])
        pairs = _coerce_pairs(migration_waves)
        if pairs:
            return ([p[0] for p in pairs], [p[1] for p in pairs])
    elif isinstance(migration_waves, (list, tuple)):
        pairs = _coerce_pairs(migration_waves)
        if pairs:
            return ([p[0] for p in pairs], [p[1] for p in pairs])
    return ([], [])


def _extract_top_destinations(migration_results, header_idx_to=7,
                              limit: int = 10) -> tuple:
    """Zählt Ziel-Länder aus den Migration-Detail-Zeilen."""
    if not migration_results:
        return ([], [])
    counter: Counter = Counter()
    for row in migration_results:
        try:
            country = row[header_idx_to]
        except (IndexError, TypeError):
            continue
        if country and isinstance(country, str):
            counter[country.strip()] += 1
    top = counter.most_common(limit)
    return ([t[0] for t in top], [t[1] for t in top])


def _extract_top_surnames(surname_results, limit: int = 20) -> tuple:
    if not surname_results:
        return ([], [])
    if isinstance(surname_results, dict):
        for key in ("top_surnames", "frequencies", "haeufigkeiten", "ranking"):
            pairs = _coerce_pairs(surname_results.get(key))
            if pairs:
                pairs.sort(key=lambda x: x[1], reverse=True)
                pairs = pairs[:limit]
                return ([p[0] for p in pairs], [p[1] for p in pairs])
        pairs = _coerce_pairs(surname_results)
        if pairs:
            pairs.sort(key=lambda x: x[1], reverse=True)
            return ([p[0] for p in pairs[:limit]],
                    [p[1] for p in pairs[:limit]])
    elif isinstance(surname_results, (list, tuple)):
        pairs = _coerce_pairs(surname_results)
        if pairs:
            pairs.sort(key=lambda x: x[1], reverse=True)
            return ([p[0] for p in pairs[:limit]],
                    [p[1] for p in pairs[:limit]])
    return ([], [])


def _extract_top_given_names(state, limit: int = 15) -> tuple:
    name_drift = _state_get(state, "name_drift_results")
    if not name_drift:
        name_drift = _state_get(state, "name_drift")
    if isinstance(name_drift, dict):
        for key in ("top_given_names", "given_names", "vornamen",
                    "frequencies"):
            pairs = _coerce_pairs(name_drift.get(key))
            if pairs:
                pairs.sort(key=lambda x: x[1], reverse=True)
                return ([p[0] for p in pairs[:limit]],
                        [p[1] for p in pairs[:limit]])
    # Fallback: aus individuals selbst zählen.
    individuals = _state_get(state, "individuals") or {}
    counter: Counter = Counter()
    for pdata in individuals.values():
        raw = (pdata.get("NAME") or "").strip()
        if not raw:
            continue
        first = raw.split("/")[0].strip().split(" ")[0]
        if first:
            counter[first] += 1
    top = counter.most_common(limit)
    return ([t[0] for t in top], [t[1] for t in top])


def _extract_top_countries(country_dist_results, limit: int = 10) -> tuple:
    if not country_dist_results:
        return ([], [])
    if isinstance(country_dist_results, dict):
        for key in ("birth_countries", "geburtslaender", "countries",
                    "frequencies"):
            pairs = _coerce_pairs(country_dist_results.get(key))
            if pairs:
                pairs.sort(key=lambda x: x[1], reverse=True)
                return ([p[0] for p in pairs[:limit]],
                        [p[1] for p in pairs[:limit]])
        pairs = _coerce_pairs(country_dist_results)
        if pairs:
            pairs.sort(key=lambda x: x[1], reverse=True)
            return ([p[0] for p in pairs[:limit]],
                    [p[1] for p in pairs[:limit]])
    elif isinstance(country_dist_results, (list, tuple)):
        pairs = _coerce_pairs(country_dist_results)
        if pairs:
            pairs.sort(key=lambda x: x[1], reverse=True)
            return ([p[0] for p in pairs[:limit]],
                    [p[1] for p in pairs[:limit]])
    return ([], [])


def _extract_pedigree_collapse(state) -> tuple:
    gen_data = _state_get(state, "genetics_results") or {}
    if isinstance(gen_data, dict):
        for key in ("pedigree_collapse_per_gen", "collapse_per_gen",
                    "ahnenschwund_pro_generation"):
            pairs = _coerce_pairs(gen_data.get(key))
            if pairs:
                return ([p[0] for p in pairs], [p[1] for p in pairs])
    endogamy = _state_get(state, "endogamy_results") or {}
    if isinstance(endogamy, dict):
        for key in ("pedigree_collapse_per_gen", "collapse_per_gen"):
            pairs = _coerce_pairs(endogamy.get(key))
            if pairs:
                return ([p[0] for p in pairs], [p[1] for p in pairs])
    return ([], [])


def _extract_inbreeding_histogram(state) -> tuple:
    gen_data = _state_get(state, "genetics_results") or {}
    if isinstance(gen_data, dict):
        for key in ("inbreeding_histogram", "f_histogram", "histogram"):
            pairs = _coerce_pairs(gen_data.get(key))
            if pairs:
                return ([p[0] for p in pairs], [p[1] for p in pairs])
    return ([], [])


# ── HTML-Generierung ──────────────────────────────────────────────────────────

_CSS = f"""
* {{ box-sizing: border-box; }}
body {{
    margin: 0;
    background: {_BG};
    color: {_FG};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.4;
}}
header {{
    background: {_BG_PANEL};
    padding: 18px 28px;
    border-bottom: 2px solid {_ACCENT};
}}
header h1 {{
    margin: 0 0 6px 0;
    font-size: 22px;
    color: {_ACCENT};
}}
header .summary {{
    color: {_MUTED};
    font-size: 13px;
}}
nav.tabs {{
    display: flex;
    background: {_BG_PANEL};
    border-bottom: 1px solid #313244;
    padding: 0 16px;
    overflow-x: auto;
}}
nav.tabs button {{
    background: transparent;
    border: 0;
    color: {_FG};
    padding: 12px 20px;
    cursor: pointer;
    font-size: 14px;
    border-bottom: 3px solid transparent;
    font-family: inherit;
    transition: color .15s, border-color .15s;
}}
nav.tabs button:hover {{ color: {_ACCENT}; }}
nav.tabs button.active {{
    color: {_ACCENT};
    border-bottom-color: {_ACCENT};
    font-weight: 600;
}}
main {{ padding: 22px 28px; }}
.tab-panel {{ display: none; }}
.tab-panel.active {{ display: block; }}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 18px;
    margin-top: 18px;
}}
.card {{
    background: {_BG_CARD};
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 16px;
}}
.card h2 {{
    margin: 0 0 12px 0;
    font-size: 15px;
    color: {_ACCENT};
    font-weight: 600;
}}
.stat-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-bottom: 18px;
}}
.stat-card {{
    background: {_BG_CARD};
    border: 1px solid #313244;
    border-radius: 8px;
    padding: 16px;
    text-align: center;
}}
.stat-card .value {{
    font-size: 28px;
    font-weight: 700;
    color: {_ACCENT};
    margin-bottom: 4px;
}}
.stat-card .label {{
    color: {_MUTED};
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.chart-container {{
    position: relative;
    height: 320px;
    width: 100%;
}}
.no-data {{
    color: {_MUTED};
    font-style: italic;
    text-align: center;
    padding: 40px 0;
}}
footer {{
    color: {_MUTED};
    font-size: 12px;
    padding: 16px 28px;
    text-align: center;
    border-top: 1px solid #313244;
    margin-top: 24px;
}}
"""


def _render_stat_card(label: str, value) -> str:
    if value is None:
        value_str = "–"
    elif isinstance(value, int):
        value_str = f"{value:,}".replace(",", ".")
    else:
        value_str = str(value)
    return (
        f'<div class="stat-card">'
        f'<div class="value">{html.escape(value_str)}</div>'
        f'<div class="label">{html.escape(label)}</div>'
        f'</div>'
    )


def _render_chart_card(chart_id: str, title: str, has_data: bool) -> str:
    inner = (
        f'<div class="chart-container"><canvas id="{chart_id}"></canvas></div>'
        if has_data
        else '<div class="no-data">Keine Daten verfügbar</div>'
    )
    return (
        f'<div class="card">'
        f'<h2>{html.escape(title)}</h2>'
        f'{inner}'
        f'</div>'
    )


def _build_charts_js(charts: list) -> str:
    """Erzeugt das JS, das alle Charts erstellt. `charts` ist eine Liste
    von Dicts: {id, type, labels, datasets, options}."""
    payload = json.dumps(charts, ensure_ascii=False)
    return f"""
const CHART_DEFS = {payload};
Chart.defaults.color = {json.dumps(_FG)};
Chart.defaults.borderColor = "#313244";
Chart.defaults.font.family = '"Segoe UI", Arial, sans-serif';

function buildAll() {{
  CHART_DEFS.forEach(def => {{
    const el = document.getElementById(def.id);
    if (!el) return;
    new Chart(el, {{
      type: def.type,
      data: {{ labels: def.labels, datasets: def.datasets }},
      options: Object.assign({{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
          legend: {{ labels: {{ color: {json.dumps(_FG)} }} }},
        }},
        scales: def.type === 'pie' || def.type === 'doughnut' ? undefined : {{
          x: {{ ticks: {{ color: {json.dumps(_MUTED)} }},
                grid: {{ color: "#313244" }} }},
          y: {{ ticks: {{ color: {json.dumps(_MUTED)} }},
                grid: {{ color: "#313244" }} }}
        }}
      }}, def.options || {{}})
    }});
  }});
}}

document.addEventListener('DOMContentLoaded', () => {{
  buildAll();
  document.querySelectorAll('nav.tabs button').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const target = btn.dataset.tab;
      document.querySelectorAll('nav.tabs button').forEach(b =>
        b.classList.toggle('active', b === btn));
      document.querySelectorAll('.tab-panel').forEach(p =>
        p.classList.toggle('active', p.id === 'tab-' + target));
    }});
  }});
}});
"""


def _make_dataset(label: str, data: list, color: str,
                  fill: bool = False) -> dict:
    return {
        "label": label,
        "data": data,
        "backgroundColor": color,
        "borderColor": color,
        "borderWidth": 2,
        "fill": fill,
        "tension": 0.25,
    }


def _make_pie_dataset(data: list, colors: list) -> dict:
    return {
        "label": "Anteil",
        "data": data,
        "backgroundColor": colors,
        "borderColor": _BG_CARD,
        "borderWidth": 2,
    }


# ── Haupt-Export-Funktion ─────────────────────────────────────────────────────

def export_dashboard_html(state, output_path: str,
                          progress_cb=None) -> bool:
    """Erzeugt ein HTML-Dashboard mit Chart.js auf Basis des Runner-State."""
    p = progress_cb or (lambda m, **kw: None)
    p("Dashboard-HTML-Export gestartet …")

    try:
        individuals = _state_get(state, "individuals") or {}
        families   = _state_get(state, "families") or {}

        n_persons  = len(individuals)
        n_families = len(families)
        min_y, max_y = _birth_year_range(individuals)

        p(f"  Personen: {n_persons:,}, Familien: {n_families:,}")

        # ── Übersicht ────────────────────────────────────────────────────────
        sex_dist = _sex_distribution(individuals)
        century = _persons_by_century(individuals)
        charts: list = []

        if sum(sex_dist.values()) > 0:
            charts.append({
                "id": "chart-sex",
                "type": "pie",
                "labels": list(sex_dist.keys()),
                "datasets": [_make_pie_dataset(
                    list(sex_dist.values()),
                    [_ACCENT, _ERR, _MUTED])],
            })
        if century:
            charts.append({
                "id": "chart-century",
                "type": "bar",
                "labels": [f"{int(k)}–{int(k)+99}" for k in century.keys()],
                "datasets": [_make_dataset(
                    "Personen", list(century.values()), _ACCENT)],
            })

        # ── Demografie ───────────────────────────────────────────────────────
        demographic_results = _state_get(state, "demographic_results")
        life_labels, life_vals = _extract_lifespan_per_epoch(demographic_results)
        marr_labels, marr_vals = _extract_marriage_age(demographic_results)

        if life_labels:
            charts.append({
                "id": "chart-lifespan",
                "type": "line",
                "labels": life_labels,
                "datasets": [_make_dataset(
                    "Ø Lebensdauer (Jahre)", life_vals, _ACCENT, fill=False)],
            })
        if marr_labels:
            charts.append({
                "id": "chart-marriage-age",
                "type": "bar",
                "labels": marr_labels,
                "datasets": [_make_dataset(
                    "Ø Heiratsalter", marr_vals, _ACCENT_2)],
            })

        # ── Migration ────────────────────────────────────────────────────────
        migration_waves = _state_get(state, "migration_waves")
        mig_labels, mig_vals = _extract_migration_per_decade(migration_waves)
        if mig_labels:
            charts.append({
                "id": "chart-migration-decades",
                "type": "line",
                "labels": [str(x) for x in mig_labels],
                "datasets": [_make_dataset(
                    "Migrationen", mig_vals, _ACCENT, fill=True)],
            })

        migration_results = _state_get(state, "migration_results") or []
        dest_labels, dest_vals = _extract_top_destinations(migration_results,
                                                            header_idx_to=7,
                                                            limit=10)
        if dest_labels:
            charts.append({
                "id": "chart-migration-dest",
                "type": "bar",
                "labels": dest_labels,
                "datasets": [_make_dataset(
                    "Ziele", dest_vals, _ACCENT_2)],
                "options": {"indexAxis": "y"},
            })

        # ── Namen ────────────────────────────────────────────────────────────
        surname_results = _state_get(state, "surname_results")
        sn_labels, sn_vals = _extract_top_surnames(surname_results, limit=20)
        if sn_labels:
            charts.append({
                "id": "chart-surnames",
                "type": "bar",
                "labels": sn_labels,
                "datasets": [_make_dataset(
                    "Häufigkeit", sn_vals, _ACCENT)],
                "options": {"indexAxis": "y"},
            })
        gn_labels, gn_vals = _extract_top_given_names(state, limit=15)
        if gn_labels:
            charts.append({
                "id": "chart-givennames",
                "type": "bar",
                "labels": gn_labels,
                "datasets": [_make_dataset(
                    "Häufigkeit", gn_vals, _ACCENT_2)],
                "options": {"indexAxis": "y"},
            })

        # ── Geografie ────────────────────────────────────────────────────────
        country_dist_results = _state_get(state, "country_dist_results")
        c_labels, c_vals = _extract_top_countries(country_dist_results, limit=10)
        if c_labels:
            charts.append({
                "id": "chart-countries",
                "type": "bar",
                "labels": c_labels,
                "datasets": [_make_dataset(
                    "Geburten", c_vals, _ACCENT)],
                "options": {"indexAxis": "y"},
            })

        # ── Genetik ──────────────────────────────────────────────────────────
        pc_labels, pc_vals = _extract_pedigree_collapse(state)
        if pc_labels:
            charts.append({
                "id": "chart-pedigree-collapse",
                "type": "line",
                "labels": [str(x) for x in pc_labels],
                "datasets": [_make_dataset(
                    "Ahnenschwund (%)", pc_vals, _ACCENT, fill=True)],
            })
        ih_labels, ih_vals = _extract_inbreeding_histogram(state)
        if ih_labels:
            charts.append({
                "id": "chart-inbreeding",
                "type": "bar",
                "labels": [str(x) for x in ih_labels],
                "datasets": [_make_dataset(
                    "Personen", ih_vals, _ERR)],
            })

        chart_ids = {c["id"] for c in charts}
        p(f"  Diagramme: {len(charts)}")

        # ── HTML zusammenbauen ──────────────────────────────────────────────
        time_range = (f"{min_y}–{max_y}" if (min_y and max_y) else "–")
        header_html = (
            f'<header>'
            f'<h1>Stammbaum-Dashboard</h1>'
            f'<div class="summary">'
            f'{n_persons:,} Personen · {n_families:,} Familien · '
            f'Zeitraum: {html.escape(time_range)}'
            f'</div>'
            f'</header>'
        )

        tab_buttons = [
            ("uebersicht", "Übersicht"),
            ("demografie", "Demografie"),
            ("migration", "Migration"),
            ("namen",      "Namen"),
            ("geografie",  "Geografie"),
            ("genetik",    "Genetik"),
        ]
        nav_html = '<nav class="tabs">' + "".join(
            f'<button data-tab="{tid}" class="{ "active" if i==0 else "" }">'
            f'{html.escape(label)}</button>'
            for i, (tid, label) in enumerate(tab_buttons)
        ) + '</nav>'

        # Übersicht-Panel
        stat_cards = (
            '<div class="stat-grid">' +
            _render_stat_card("Personen", n_persons) +
            _render_stat_card("Familien", n_families) +
            _render_stat_card("Älteste Geburt",
                              min_y if min_y else "–") +
            _render_stat_card("Jüngste Geburt",
                              max_y if max_y else "–") +
            '</div>'
        )
        uebersicht_html = (
            f'<div class="tab-panel active" id="tab-uebersicht">'
            f'{stat_cards}'
            f'<div class="grid">'
            f'{_render_chart_card("chart-sex", "Geschlechterverteilung", "chart-sex" in chart_ids)}'
            f'{_render_chart_card("chart-century", "Personen pro Jahrhundert", "chart-century" in chart_ids)}'
            f'</div></div>'
        )

        demografie_html = (
            f'<div class="tab-panel" id="tab-demografie">'
            f'<div class="grid">'
            f'{_render_chart_card("chart-lifespan", "Ø Lebensdauer pro Epoche", "chart-lifespan" in chart_ids)}'
            f'{_render_chart_card("chart-marriage-age", "Ø Heiratsalter pro Epoche", "chart-marriage-age" in chart_ids)}'
            f'</div></div>'
        )

        migration_html = (
            f'<div class="tab-panel" id="tab-migration">'
            f'<div class="grid">'
            f'{_render_chart_card("chart-migration-decades", "Migrationen pro Dekade", "chart-migration-decades" in chart_ids)}'
            f'{_render_chart_card("chart-migration-dest", "Top-10 Zielländer", "chart-migration-dest" in chart_ids)}'
            f'</div></div>'
        )

        namen_html = (
            f'<div class="tab-panel" id="tab-namen">'
            f'<div class="grid">'
            f'{_render_chart_card("chart-surnames", "Top-20 Familiennamen", "chart-surnames" in chart_ids)}'
            f'{_render_chart_card("chart-givennames", "Top-15 Vornamen", "chart-givennames" in chart_ids)}'
            f'</div></div>'
        )

        geografie_html = (
            f'<div class="tab-panel" id="tab-geografie">'
            f'<div class="grid">'
            f'{_render_chart_card("chart-countries", "Top-10 Geburtsländer", "chart-countries" in chart_ids)}'
            f'</div></div>'
        )

        genetik_html = (
            f'<div class="tab-panel" id="tab-genetik">'
            f'<div class="grid">'
            f'{_render_chart_card("chart-pedigree-collapse", "Ahnenschwund pro Generation", "chart-pedigree-collapse" in chart_ids)}'
            f'{_render_chart_card("chart-inbreeding", "Inzucht-Histogramm", "chart-inbreeding" in chart_ids)}'
            f'</div></div>'
        )

        main_html = (
            '<main>'
            + uebersicht_html
            + demografie_html
            + migration_html
            + namen_html
            + geografie_html
            + genetik_html
            + '</main>'
        )

        footer_html = (
            '<footer>Erzeugt vom GEDCOM-Analyzer · '
            'Dark Theme · Chart.js</footer>'
        )

        js = _build_charts_js(charts)

        html_doc = (
            '<!DOCTYPE html>\n'
            '<html lang="de"><head>'
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Stammbaum-Dashboard</title>'
            f'<style>{_CSS}</style>'
            f'<script src="{_CHARTJS_CDN}"></script>'
            '</head><body>'
            + header_html
            + nav_html
            + main_html
            + footer_html
            + f'<script>{js}</script>'
            '</body></html>'
        )

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_doc)

        size_kb = os.path.getsize(output_path) / 1024
        p(f"Dashboard gespeichert: {output_path} ({size_kb:.1f} KB, "
          f"{len(charts)} Diagramme)", tag="ok")
        return True

    except OSError as exc:
        p(f"Fehler beim Schreiben der Dashboard-HTML: {exc}", tag="err")
        return False
    except Exception as exc:
        p(f"Unerwarteter Fehler beim Dashboard-Export: {exc}", tag="err")
        return False
