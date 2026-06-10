# -*- coding: utf-8 -*-
"""tasks/family_structure.py – Familienstruktur-Analysen: Mehrfachehen,
Alters-Differenz, reproduktive Spanne, Kinderlosigkeit, Zwillinge."""

from collections import defaultdict
from statistics import median
from lib.gedcom import safe_extract_year


MAX_ROWS = 50_000

EPOCHS = {
    "vor_1800":   (1500, 1799),
    "1800-1850":  (1800, 1849),
    "1850-1900":  (1850, 1899),
    "1900-1950":  (1900, 1949),
    "nach_1950":  (1950, 2024),
}


def _epoch_for(year):
    if not year:
        return None
    for name, (s, e) in EPOCHS.items():
        if s <= year <= e:
            return name
    return None


# ── Mehrfachehen ───────────────────────────────────────────────────────────────

MULTIPLE_MARRIAGES_HEADERS = [
    "Person-ID", "Name", "Geschlecht", "Anzahl Ehen", "Ehen-Detail"
]


def analyze_multiple_marriages(individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Mehrfachehen analysieren …")

    rows = []
    for pid, pdata in individuals.items():
        fams = pdata.get("FAMS", []) or []
        if len(fams) < 2:
            continue

        birth_year = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        sex = pdata.get("SEX", "U")

        marriages = []
        for fid in fams:
            fam = families.get(fid)
            if not fam:
                continue
            my = safe_extract_year(fam.get("MARR_DATE"))
            spouse_id = fam.get("WIFE") if sex == "M" else fam.get("HUSB")
            if not spouse_id and sex not in ("M", "F"):
                spouse_id = fam.get("WIFE") if fam.get("HUSB") == pid else fam.get("HUSB")
            spouse = individuals.get(spouse_id, {}) if spouse_id else {}
            spouse_death = safe_extract_year((spouse.get("DEAT") or {}).get("DATE"))
            marriages.append({
                "year": my,
                "spouse_id": spouse_id,
                "spouse_death": spouse_death,
            })

        marriages.sort(key=lambda m: (m["year"] is None, m["year"] or 0))

        details = []
        for i, m in enumerate(marriages):
            year = m["year"]
            age_str = ""
            if year and birth_year:
                age = year - birth_year
                age_str = f", {age} J."
            note = ""
            if i > 0:
                prev = marriages[i - 1]
                if prev["spouse_death"] and year and prev["spouse_death"] <= year:
                    note = ", Witwer" if sex == "M" else ", Witwe" if sex == "F" else ", verwitwet"
                elif prev["year"] and year and prev["spouse_death"] is None:
                    note = ", parallel?"
            year_str = str(year) if year else "?"
            details.append(f"{year_str} ({age_str.lstrip(', ')}{note})".replace("()", ""))

        rows.append([
            pid,
            (pdata.get("NAME") or "")[:60],
            "Männlich" if sex == "M" else "Weiblich" if sex == "F" else "Unbekannt",
            len(fams),
            "; ".join(details),
        ])

        if len(rows) >= MAX_ROWS:
            break

    rows.sort(key=lambda r: r[3], reverse=True)
    p(f"Mehrfachehen: {len(rows)} Personen", tag="ok")
    return rows


# ── Alters-Differenz Ehepartner ────────────────────────────────────────────────

SPOUSE_AGE_GAP_HEADERS = [
    "Epoche", "Anzahl Paare", "Ø Alters-Differenz (Mann−Frau)", "Median",
    "Min", "Max", "% Mann älter", "% Frau älter", "% gleichaltrig (±1 J.)"
]


def analyze_spouse_age_gap(individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Alters-Differenz Ehepartner analysieren …")

    by_epoch = defaultdict(list)

    for fid, fam in families.items():
        husb_id = fam.get("HUSB")
        wife_id = fam.get("WIFE")
        if not husb_id or not wife_id:
            continue
        husb = individuals.get(husb_id)
        wife = individuals.get(wife_id)
        if not husb or not wife:
            continue
        hby = safe_extract_year((husb.get("BIRT") or {}).get("DATE"))
        wby = safe_extract_year((wife.get("BIRT") or {}).get("DATE"))
        if not hby or not wby:
            continue
        gap = hby - wby

        my = safe_extract_year(fam.get("MARR_DATE"))
        ref_year = my if my else wby + 25
        ep = _epoch_for(ref_year)
        if not ep:
            continue
        by_epoch[ep].append(gap)

    rows = []
    for ep_name in EPOCHS:
        gaps = by_epoch.get(ep_name, [])
        if not gaps:
            continue
        n = len(gaps)
        avg = sum(gaps) / n
        med = median(gaps)
        husb_older = sum(1 for g in gaps if g > 1)
        wife_older = sum(1 for g in gaps if g < -1)
        equal = sum(1 for g in gaps if -1 <= g <= 1)
        rows.append([
            ep_name, n,
            f"{avg:.2f}", f"{med:.1f}",
            min(gaps), max(gaps),
            f"{husb_older/n*100:.1f}%",
            f"{wife_older/n*100:.1f}%",
            f"{equal/n*100:.1f}%",
        ])

    p(f"Alters-Differenz: {len(rows)} Epochen", tag="ok")
    return rows


# ── Reproduktive Spanne ────────────────────────────────────────────────────────

REPRODUCTIVE_SPAN_HEADERS = [
    "Mutter-ID", "Name", "Geburtsjahr", "Anzahl Kinder",
    "Alter erstes Kind", "Alter letztes Kind", "Reproduktive Spanne (J.)"
]


def analyze_reproductive_span(individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Reproduktive Spanne analysieren …")

    rows = []
    epoch_spans = defaultdict(list)

    for pid, pdata in individuals.items():
        if pdata.get("SEX") != "F":
            continue
        mby = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if not mby:
            continue

        child_years = []
        n_children = 0
        for fid in pdata.get("FAMS", []) or []:
            fam = families.get(fid, {})
            for cid in fam.get("CHIL", []):
                n_children += 1
                cd = individuals.get(cid, {})
                cby = safe_extract_year((cd.get("BIRT") or {}).get("DATE"))
                if cby:
                    child_years.append(cby)

        if len(child_years) < 2:
            continue

        child_years.sort()
        age_first = child_years[0] - mby
        age_last = child_years[-1] - mby
        span = age_last - age_first

        if age_first < 10 or age_first > 60 or span < 0:
            continue

        rows.append([
            pid,
            (pdata.get("NAME") or "")[:60],
            mby,
            n_children,
            age_first,
            age_last,
            span,
        ])

        ep = _epoch_for(mby)
        if ep:
            epoch_spans[ep].append(span)

        if len(rows) >= MAX_ROWS:
            break

    rows.sort(key=lambda r: r[6], reverse=True)

    if epoch_spans:
        rows.append(["", "", "", "", "", "", ""])
        rows.append(["── Aggregat pro Epoche ──", "", "", "", "", "", ""])
        for ep_name in EPOCHS:
            sp = epoch_spans.get(ep_name, [])
            if not sp:
                continue
            rows.append([
                f"Epoche {ep_name}",
                f"{len(sp)} Mütter",
                "",
                "",
                "",
                "Ø Spanne",
                f"{sum(sp)/len(sp):.1f}",
            ])

    p(f"Reproduktive Spanne: {len(rows)} Zeilen", tag="ok")
    return rows


# ── Kinderlosigkeit ────────────────────────────────────────────────────────────

CHILDLESSNESS_HEADERS = [
    "Epoche", "Anzahl Paare gesamt", "Paare ohne Kinder",
    "Paare mit Kindern", "Kinderlosigkeits-Rate %"
]


def analyze_childlessness(individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Kinderlosigkeit analysieren …")

    totals = defaultdict(int)
    childless = defaultdict(int)
    with_children = defaultdict(int)

    for fid, fam in families.items():
        husb_id = fam.get("HUSB")
        wife_id = fam.get("WIFE")
        if not husb_id or not wife_id:
            continue
        if husb_id not in individuals or wife_id not in individuals:
            continue
        my = safe_extract_year(fam.get("MARR_DATE"))
        if not my:
            continue
        ep = _epoch_for(my)
        if not ep:
            continue
        totals[ep] += 1
        n_chil = len(fam.get("CHIL", []) or [])
        if n_chil == 0:
            childless[ep] += 1
        else:
            with_children[ep] += 1

    rows = []
    for ep_name in EPOCHS:
        tot = totals.get(ep_name, 0)
        if tot == 0:
            continue
        cl = childless.get(ep_name, 0)
        wc = with_children.get(ep_name, 0)
        rate = cl / tot * 100 if tot else 0
        rows.append([
            ep_name, tot, cl, wc, f"{rate:.1f}%"
        ])

    p(f"Kinderlosigkeit: {len(rows)} Epochen", tag="ok")
    return rows


# ── Zwillinge ──────────────────────────────────────────────────────────────────

TWIN_HEADERS = [
    "Familie-ID", "Eltern", "Geburtsjahr", "Anzahl gleichzeitig geborener Kinder",
    "Namen", "Hinweis"
]


def detect_twins(individuals, families, progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Zwillinge erkennen …")

    rows = []
    for fid, fam in families.items():
        children = fam.get("CHIL", []) or []
        if len(children) < 2:
            continue

        by_year = defaultdict(list)
        for cid in children:
            cd = individuals.get(cid)
            if not cd:
                continue
            birt = cd.get("BIRT") or {}
            year = birt.get("YEAR") or safe_extract_year(birt.get("DATE"))
            if year:
                by_year[year].append(cid)

        husb_id = fam.get("HUSB")
        wife_id = fam.get("WIFE")
        husb_name = (individuals.get(husb_id, {}).get("NAME") or "")[:40] if husb_id else ""
        wife_name = (individuals.get(wife_id, {}).get("NAME") or "")[:40] if wife_id else ""
        parents = f"{husb_name} & {wife_name}".strip(" &")

        for year, cids in by_year.items():
            if len(cids) < 2:
                continue
            names = ", ".join((individuals.get(c, {}).get("NAME") or "")[:30] for c in cids)
            hint = "wahrsch. Zwillinge" if len(cids) == 2 else "wahrsch. Mehrlinge"
            rows.append([
                fid, parents, year, len(cids), names, hint
            ])

            if len(rows) >= MAX_ROWS:
                break
        if len(rows) >= MAX_ROWS:
            break

    rows.sort(key=lambda r: (-r[3], r[2] if isinstance(r[2], int) else 0))
    p(f"Zwillinge: {len(rows)} Fälle", tag="ok")
    return rows
