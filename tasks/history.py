# -*- coding: utf-8 -*-
"""tasks/history.py – Historischer Kontext, Überlebenszeitanalyse, Trends, Generationenlängen"""

import math
from collections import Counter, defaultdict, deque
from lib.gedcom import safe_extract_year
from lib.places import extract_country_from_place, format_place_for_display
from lib.helpers import (safe_determine_migration_status,
                          safe_extract_family_name, get_ancestor_paths)


# ── Historische Ereignisse ─────────────────────────────────────────────────────

HISTORICAL_EVENTS = [
    (1618, 1648, "Dreißigjähriger Krieg",          "Krieg",       "Deutschland"),
    (1756, 1763, "Siebenjähriger Krieg",            "Krieg",       "Europa"),
    (1789, 1799, "Französische Revolution",         "Politik",     "Europa"),
    (1803, 1815, "Napoleonische Kriege",            "Krieg",       "Europa"),
    (1831, 1832, "Cholera-Pandemie (1. Welle)",     "Seuche",      "Europa"),
    (1848, 1849, "Revolution 1848/49",              "Politik",     "Deutschland"),
    (1849, 1850, "Cholera-Pandemie (3. Welle)",     "Seuche",      "Europa"),
    (1864, 1864, "Deutsch-Dänischer Krieg",         "Krieg",       "Deutschland"),
    (1866, 1866, "Preußisch-Österreichischer Krieg","Krieg",       "Deutschland"),
    (1866, 1867, "Cholera-Pandemie (6. Welle)",     "Seuche",      "Europa"),
    (1870, 1871, "Deutsch-Französischer Krieg",     "Krieg",       "Deutschland"),
    (1914, 1918, "Erster Weltkrieg",                "Krieg",       "Europa"),
    (1918, 1920, "Spanische Grippe",                "Seuche",      "Welt"),
    (1933, 1945, "NS-Diktatur",                     "Politik",     "Deutschland"),
    (1939, 1945, "Zweiter Weltkrieg",               "Krieg",       "Europa"),
    (1945, 1950, "Nachkriegszeit / Flucht & Vertreibung", "Migration", "Deutschland"),
    (1950, 1970, "Wirtschaftswunder",               "Gesellschaft","Deutschland"),
    (1960, 1973, "Gastarbeiter-Migration",          "Migration",   "Deutschland"),
]


def analyze_historical_context(individuals, families, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Historische Kontextualisierung …")

    event_stats = {ev[2]: {
        "start": ev[0], "end": ev[1], "kategorie": ev[3], "region": ev[4],
        "born_during": [], "died_during": [], "lived_through": [],
        "with_military": 0, "without_marker": 0
    } for ev in HISTORICAL_EVENTS}

    person_events: dict = defaultdict(list)

    for pid, pdata in individuals.items():
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        dy = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        name = pdata.get("NAME", "") or ""
        has_mil = any(s in name for s in ["✠", "★", "⚔"])

        for ev in HISTORICAL_EVENTS:
            es, ee, en = ev[0], ev[1], ev[2]
            s = event_stats[en]
            if by and es <= by <= ee:
                s["born_during"].append(pid); person_events[pid].append(f"Geb. während: {en}")
            if dy and es <= dy <= ee:
                s["died_during"].append(pid)
                if has_mil: s["with_military"] += 1
                else:       s["without_marker"] += 1
                person_events[pid].append(f"Gest. während: {en}")
            if by and by < es and (not dy or dy > ee):
                s["lived_through"].append(pid)

    ereignis_rows = []
    for ev in HISTORICAL_EVENTS:
        en = ev[2]; s = event_stats[en]
        total = len(set(s["born_during"] + s["died_during"] + s["lived_through"]))
        if total == 0: continue
        examples = [(individuals.get(pid, {}).get("NAME") or "")[:25]
                    for pid in s["died_during"][:3]]
        ereignis_rows.append([
            en, ev[0], ev[1], ev[3], ev[4],
            len(s["born_during"]), len(s["died_during"]), len(s["lived_through"]),
            total, s["with_military"], s["without_marker"],
            ", ".join(examples)
        ])

    person_rows = []
    for pid, ev_list in person_events.items():
        pdata = individuals.get(pid, {})
        name = (pdata.get("NAME") or "")[:40]
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        dy = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        person_rows.append([pid, name, by or "", dy or "", len(ev_list),
                             "; ".join(ev_list[:4])])
    person_rows.sort(key=lambda x: x[4], reverse=True)

    p(f"Historischer Kontext: {len(ereignis_rows)} Ereignisse", tag="ok")
    return ereignis_rows, person_rows


HIST_EVENT_HEADERS = [
    "Historisches Ereignis", "Startjahr", "Endjahr", "Kategorie", "Region",
    "Geboren während", "Gestorben während", "Durchlebend",
    "Personen gesamt", "Mit Militärmarkierung", "Ohne Markierung",
    "Beispiele Verstorbene"
]
HIST_PERSON_HEADERS = [
    "ID", "Name", "Geburtsjahr", "Sterbejahr",
    "Anzahl Ereignisbezüge", "Ereignisse"
]


# ── Überlebenszeitanalyse ──────────────────────────────────────────────────────

_COHORTS = [
    ("vor 1800",  None, 1799),
    ("1800–1849", 1800, 1849),
    ("1850–1899", 1850, 1899),
    ("1900–1949", 1900, 1949),
    ("nach 1950", 1950, None),
]
_CHECK_AGES = [0, 1, 5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]


def analyze_survival_curves(individuals, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Überlebenszeitanalyse …")
    cohort_ages: dict = {c[0]: [] for c in _COHORTS}

    for pdata in individuals.values():
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        dy = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        if not by or not dy: continue
        age = dy - by
        if not (0 <= age <= 115): continue
        for cname, cs, ce in _COHORTS:
            ok = True
            if cs and by < cs: ok = False
            if ce and by > ce: ok = False
            if ok:
                cohort_ages[cname].append(age)
                break

    curve_rows = []
    for age_ck in _CHECK_AGES:
        row = [age_ck]
        for cname, _, _ in _COHORTS:
            ages = cohort_ages[cname]
            row.append(round(sum(1 for a in ages if a >= age_ck) / len(ages) * 100, 1)
                       if ages else "")
        curve_rows.append(row)

    summary_rows = []
    for cname, _, _ in _COHORTS:
        ages = cohort_ages[cname]
        if not ages: continue
        n = len(ages); sa = sorted(ages)
        infant  = sum(1 for a in ages if a < 5)
        adults  = [a for a in ages if a >= 15]
        summary_rows.append([
            cname, n,
            round(sum(ages) / n, 1), sa[n // 2],
            round(sum(adults) / len(adults), 1) if adults else "",
            infant, round(infant / n * 100, 1),
            min(ages), max(ages), sa[n // 2], sa[int(n * 0.75)]
        ])

    p(f"Überlebenskurven: {len(summary_rows)} Kohorten", tag="ok")
    return curve_rows, summary_rows, [c[0] for c in _COHORTS]


SURVIVAL_CURVE_HEADERS = ["Alter (Jahre)"]  # + cohort names dynamisch
SURVIVAL_SUMMARY_HEADERS = [
    "Kohorte", "n (Personen)", "Ø Lebensalter", "Median Lebensalter",
    "Ø Erwachsenenalter (≥15J.)", "Kindersterblichkeit (Anzahl)",
    "Kindersterblichkeit (%)", "Jüngstes Sterbealter", "Höchstes Sterbealter",
    "50%-Marke (Alter)", "75%-Marke (Alter)"
]


# ── Generationenlängen ─────────────────────────────────────────────────────────

def calculate_generation_lengths(individuals, families, root_id,
                                   location_data, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Generationenlängen-Analyse …")

    # Generationen von Root aus (BFS durch FAMS)
    gen_map = {root_id: 0}
    queue = deque([root_id])
    seen = {root_id}
    while queue:
        cur = queue.popleft()
        g = gen_map[cur]
        for fid in individuals.get(cur, {}).get("FAMS", []):
            for cid in families.get(fid, {}).get("CHIL", []):
                if cid not in gen_map:
                    gen_map[cid] = g + 1
                    if cid not in seen:
                        queue.append(cid)
                        seen.add(cid)

    gen_stats: dict = {}
    for pid, pdata in individuals.items():
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if not by: continue
        g = gen_map.get(pid)
        if g is None: continue
        for fid in pdata.get("FAMS", []):
            for cid in families.get(fid, {}).get("CHIL", []):
                cd = individuals.get(cid, {})
                if not cd: continue
                cby = safe_extract_year((cd.get("BIRT") or {}).get("DATE"))
                if not cby: continue
                age = cby - by
                if not (12 <= age <= 70): continue
                st = gen_stats.setdefault(g, {
                    "ages": [], "persons": set(), "birth_years": [], "children": 0})
                st["ages"].append(age)
                st["persons"].add(pid)
                st["birth_years"].append(by)
                st["children"] += 1

    results = []
    for gn, st in sorted(gen_stats.items()):
        ages = st["ages"]
        if not ages: continue
        avg  = sum(ages) / len(ages)
        bys  = st["birth_years"]
        sa   = sorted(ages)
        mid  = len(sa) // 2
        med  = (sa[mid - 1] + sa[mid]) / 2 if len(sa) % 2 == 0 else sa[mid]
        var  = sum((a - avg) ** 2 for a in ages) / len(ages)
        std  = math.sqrt(var)
        pc   = len(st["persons"])
        mig  = sum(
            1 for pid in st["persons"]
            if safe_determine_migration_status(
                individuals.get(pid, {}),
                individuals.get(pid, {}).get("NAME", ""),
                location_data).startswith("ja"))
        males = sum(1 for pid in st["persons"]
                    if individuals.get(pid, {}).get("SEX") == "M")
        females = pc - males
        ex = [f"{(individuals.get(pid, {}).get('NAME') or '')[:25]}…"
              f" (*{safe_extract_year((individuals.get(pid, {}).get('BIRT') or {}).get('DATE')) or '?'})"
              for pid in list(st["persons"])[:3] if pid in individuals]
        results.append([
            gn, pc, st["children"], round(st["children"] / pc, 2) if pc else 0,
            round(avg, 1), round(med, 1), round(std, 2), min(ages), max(ages),
            int(round(sum(bys) / len(bys))) if bys else "",
            males, females, mig,
            round(mig / pc * 100, 1) if pc else 0,
            ", ".join(ex)
        ])
    results.sort(key=lambda x: x[0])
    p(f"Generationenlängen: {len(results)} Generationen", tag="ok")
    return results


GENERATION_HEADERS = [
    "Generation (0=Root)", "Anzahl Personen", "Anzahl Kinder", "Kinder pro Person",
    "Ø Alter bei Geburt", "Median-Alter", "Standardabweichung",
    "Minimales Alter", "Maximales Alter", "Ø Geburtsjahr",
    "Männer", "Frauen", "Auswanderer", "Migrationsrate %", "Beispielpersonen"
]


# ── Historische Trends (Jahrhunderte / Jahrzehnte) ────────────────────────────

def analyze_historical_trends(individuals, families, location_data,
                               progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Historische Trendanalyse …")

    centuries: dict = defaultdict(lambda: {
        "births": [], "deaths": [], "marriages": [], "migrations": [],
        "lifespans": [], "children_counts": [], "name_lengths": [],
        "unique_surnames": set(), "birth_countries": Counter(), "death_countries": Counter()
    })
    decades: dict = defaultdict(lambda: {"events": 0, "migration_rate": 0})

    for pid, pdata in individuals.items():
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        dy = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        name = pdata.get("NAME", "") or ""
        if by:
            c = (by // 100) * 100; d = (by // 10) * 10
            centuries[c]["births"].append(by); decades[d]["events"] += 1
            if name:
                centuries[c]["name_lengths"].append(len(name))
                sn = safe_extract_family_name(name)
                if sn: centuries[c]["unique_surnames"].add(sn)
            bp = (pdata.get("BIRT") or {}).get("PLAC", "")
            if bp:
                bc = extract_country_from_place(bp, location_data)
                if bc: centuries[c]["birth_countries"][bc] += 1
            if dy and 0 < dy - by <= 120: centuries[c]["lifespans"].append(dy - by)
            mig = safe_determine_migration_status(pdata, name, location_data)
            if mig.startswith("ja"):
                centuries[c]["migrations"].append(by); decades[d]["migration_rate"] += 1
            children = sum(len(families.get(fid, {}).get("CHIL", []))
                           for fid in pdata.get("FAMS", []))
            if children > 0: centuries[c]["children_counts"].append(children)
        if dy:
            c = (dy // 100) * 100; centuries[c]["deaths"].append(dy)
            dp = (pdata.get("DEAT") or {}).get("PLAC", "")
            if dp:
                dc = extract_country_from_place(dp, location_data)
                if dc: centuries[c]["death_countries"][dc] += 1

    for fam in families.values():
        my = safe_extract_year(fam.get("MARR_DATE"))
        if my: centuries[(my // 100) * 100]["marriages"].append(my)

    century_rows = []
    _DECADE_HIST = {
        (1840, 1850): "1848er Revolution",
        (1910, 1920): "1. Weltkrieg",
        (1930, 1940): "Weltwirtschaftskrise, NS-Zeit",
        (1940, 1950): "2. Weltkrieg",
        (1950, 1960): "Wirtschaftswunder",
    }
    for century in sorted(centuries):
        if not (1500 <= century <= 2100): continue
        cd = centuries[century]
        if not cd["births"]: continue
        avg_ls = sum(cd["lifespans"]) / len(cd["lifespans"]) if cd["lifespans"] else 0
        avg_ch = sum(cd["children_counts"]) / len(cd["children_counts"]) if cd["children_counts"] else 0
        mig_rate = len(cd["migrations"]) / len(cd["births"]) * 100 if cd["births"] else 0
        sn_div = len(cd["unique_surnames"])
        hist = ""
        if   1600 <= century < 1700: hist = "Dreißigjähriger Krieg, Kolonialisierung"
        elif 1700 <= century < 1800: hist = "Aufklärung, Industrielle Revolution beginnt"
        elif 1800 <= century < 1900: hist = "Industrielle Revolution, Auswanderungswellen"
        elif 1900 <= century < 2000: hist = "Weltkriege, Wirtschaftswunder, Globalisierung"
        century_rows.append([
            f"{century}-{century+99}",
            len(cd["births"]), len(cd["deaths"]), len(cd["marriages"]),
            len(cd["migrations"]), round(mig_rate, 1),
            round(avg_ls, 1) if cd["lifespans"] else "",
            round(avg_ch, 1) if cd["children_counts"] else "",
            round(sum(cd["name_lengths"]) / len(cd["name_lengths"]), 1) if cd["name_lengths"] else "",
            sn_div, round(sn_div / len(cd["births"]) * 100, 1) if cd["births"] else 0,
            "", ", ".join(f"{k}:{v}" for k, v in cd["birth_countries"].most_common(3)),
            ", ".join(f"{k}:{v}" for k, v in cd["death_countries"].most_common(3)),
            hist, "stabil"
        ])

    decade_rows = []
    for decade in sorted(decades):
        if not (1500 <= decade <= 2100): continue
        dd = decades[decade]
        if dd["events"] == 0: continue
        mr = dd["migration_rate"] / dd["events"] * 100
        evs = [v for (s, e), v in _DECADE_HIST.items() if s <= decade < e]
        decade_rows.append([
            f"{decade}-{decade+9}", dd["events"],
            dd["migration_rate"], round(mr, 1),
            "; ".join(evs) or "stabile Phase"
        ])

    p(f"Historische Trends: {len(century_rows)} Jahrhunderte, {len(decade_rows)} Jahrzehnte",
      tag="ok")
    return {"century_trends": century_rows, "decade_trends": decade_rows}


CENTURY_HEADERS = [
    "Jahrhundert", "Geburten", "Todesfälle", "Heiraten", "Migrationen",
    "Migrationsrate %", "Ø Lebenserwartung", "Ø Kinderzahl",
    "Ø Namenslänge", "Nachnamen-Vielfalt", "Nachnamen-Varietät %",
    "Länder-Mobilität %", "Top 3 Geburtsländer", "Top 3 Sterbeländer",
    "Historischer Kontext", "Trendrichtung"
]
DECADE_HEADERS = [
    "Jahrzehnt", "Ereignisse", "Migrationen", "Migrationsrate %",
    "Historische Ereignisse"
]


# ── Krisen-Kohorten-Follow-up ──────────────────────────────────────────────────

CRISIS_COHORT_HEADERS = [
    "Ereignis", "Zeitraum", "Kohorte-Anzahl",
    "Kohorte Ø Lebenserwartung", "Δ Lebenserwartung vs. Vor-Kohorte",
    "Kohorte Ø Heiratsalter", "Δ Heiratsalter",
    "Kohorte Ø Kinder", "Δ Kinderzahl",
    "Baseline-Anzahl",
]


def _avg(xs):
    return (sum(xs) / len(xs)) if xs else None


def _delta(a, b):
    if a is None or b is None:
        return ""
    return round(a - b, 2)


def _first_marriage_year(pdata, families):
    years = []
    for fid in pdata.get("FAMS", []) or []:
        fam = families.get(fid)
        if not fam:
            continue
        my = safe_extract_year(fam.get("MARR_DATE"))
        if my:
            years.append(my)
    return min(years) if years else None


def _children_count(pdata, families):
    total = 0
    for fid in pdata.get("FAMS", []) or []:
        fam = families.get(fid)
        if not fam:
            continue
        total += len(fam.get("CHIL", []) or [])
    return total


def _cohort_stats(pids, individuals, families):
    """Liefert (n, avg_lifespan, avg_first_marr_age, avg_children)."""
    lifespans = []
    marr_ages = []
    children = []
    for pid in pids:
        pdata = individuals.get(pid) or {}
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        dy = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        if by and dy:
            ls = dy - by
            if 0 <= ls <= 115:
                lifespans.append(ls)
        my = _first_marriage_year(pdata, families)
        if by and my:
            age = my - by
            if 10 <= age <= 90:
                marr_ages.append(age)
        children.append(_children_count(pdata, families))
    return (
        len(pids),
        _avg(lifespans),
        _avg(marr_ages),
        _avg(children),
    )


def analyze_crisis_cohort_followup(individuals, families, progress_cb=None) -> list:
    """Vergleicht die während eines historischen Ereignisses geborene Kohorte
    mit einer Baseline-Kohorte (20 Jahre vor dem Ereignis)."""
    p = progress_cb or (lambda m, **kw: None)
    p("Krisen-Kohorten-Follow-up …")

    # Vorberechnung: Geburtsjahr pro Person
    birth_by_pid: dict = {}
    for pid, pdata in individuals.items():
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if by:
            birth_by_pid[pid] = by

    rows = []
    for start, end, name, _kat, _reg in HISTORICAL_EVENTS:
        cohort = [pid for pid, by in birth_by_pid.items() if start <= by <= end]
        base_start = start - 20
        base_end = start - 1
        baseline = [pid for pid, by in birth_by_pid.items()
                    if base_start <= by <= base_end]

        if not cohort and not baseline:
            continue

        n_c, ls_c, ma_c, ch_c = _cohort_stats(cohort, individuals, families)
        n_b, ls_b, ma_b, ch_b = _cohort_stats(baseline, individuals, families)

        rows.append([
            name,
            f"{start}–{end}",
            n_c,
            round(ls_c, 2) if ls_c is not None else "",
            _delta(ls_c, ls_b),
            round(ma_c, 2) if ma_c is not None else "",
            _delta(ma_c, ma_b),
            round(ch_c, 2) if ch_c is not None else "",
            _delta(ch_c, ch_b),
            n_b,
        ])

    p(f"Krisen-Kohorten: {len(rows)} Ereignisse", tag="ok")
    return rows


# ── Eltern-Verlust-Alter ───────────────────────────────────────────────────────

PARENTAL_LOSS_HEADERS = [
    "Epoche", "Anzahl Personen",
    "Median Alter Vatertod", "Median Alter Muttertod",
    "Vollwaisen vor 18 (Anzahl)", "Vollwaisen-Rate %",
]

EPOCHS = {
    "vor_1800":  (1500, 1799),
    "1800-1850": (1800, 1849),
    "1850-1900": (1850, 1899),
    "1900-1950": (1900, 1949),
    "nach_1950": (1950, 2024),
}


def _epoch_for(year: int) -> str | None:
    for ep, (s, e) in EPOCHS.items():
        if s <= year <= e:
            return ep
    return None


def _parents_of(pdata, families):
    father = mother = None
    for fid in pdata.get("FAMC", []) or []:
        fam = families.get(fid)
        if not fam:
            continue
        if fam.get("HUSB") and not father:
            father = fam["HUSB"]
        if fam.get("WIFE") and not mother:
            mother = fam["WIFE"]
        if father and mother:
            break
    return father, mother


def analyze_parental_loss_age(individuals, families, progress_cb=None) -> list:
    """Aggregiert pro Geburts-Epoche das Alter beim Tod der Eltern und die
    Vollwaisen-Rate vor dem 18. Lebensjahr."""
    p = progress_cb or (lambda m, **kw: None)
    p("Eltern-Verlust-Alter …")

    buckets: dict = {ep: {
        "n": 0,
        "father_ages": [],
        "mother_ages": [],
        "orphans_before_18": 0,
    } for ep in EPOCHS}

    for pid, pdata in individuals.items():
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if not by:
            continue
        if not pdata.get("FAMC"):
            continue
        ep = _epoch_for(by)
        if ep is None:
            continue

        own_dy = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))

        father_id, mother_id = _parents_of(pdata, families)
        if not father_id and not mother_id:
            continue

        buckets[ep]["n"] += 1

        father_loss_age = None
        if father_id:
            f = individuals.get(father_id) or {}
            fdy = safe_extract_year((f.get("DEAT") or {}).get("DATE"))
            if fdy is not None:
                if own_dy is not None and fdy > own_dy:
                    pass  # Verlust nach eigenem Tod – ignorieren
                else:
                    age = fdy - by
                    if -1 <= age <= 115:
                        father_loss_age = age
                        buckets[ep]["father_ages"].append(age)

        mother_loss_age = None
        if mother_id:
            m = individuals.get(mother_id) or {}
            mdy = safe_extract_year((m.get("DEAT") or {}).get("DATE"))
            if mdy is not None:
                if own_dy is not None and mdy > own_dy:
                    pass
                else:
                    age = mdy - by
                    if -1 <= age <= 115:
                        mother_loss_age = age
                        buckets[ep]["mother_ages"].append(age)

        if (father_loss_age is not None and father_loss_age < 18 and
                mother_loss_age is not None and mother_loss_age < 18):
            buckets[ep]["orphans_before_18"] += 1

    def _median(xs):
        if not xs:
            return ""
        sx = sorted(xs)
        n = len(sx)
        mid = n // 2
        return (sx[mid - 1] + sx[mid]) / 2 if n % 2 == 0 else sx[mid]

    rows = []
    for ep in EPOCHS:
        b = buckets[ep]
        n = b["n"]
        if n == 0:
            continue
        rows.append([
            ep,
            n,
            _median(b["father_ages"]),
            _median(b["mother_ages"]),
            b["orphans_before_18"],
            round(b["orphans_before_18"] / n * 100, 1),
        ])

    p(f"Eltern-Verlust: {len(rows)} Epochen", tag="ok")
    return rows
