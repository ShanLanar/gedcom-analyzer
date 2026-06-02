# -*- coding: utf-8 -*-
"""
tasks/book_statistics.py
21 demographische Analysen inspiriert von 'The Village in the Field'.
"""

import math
import statistics
from collections import defaultdict

from lib.gedcom import safe_extract_year

# ── Header-Konstanten ──────────────────────────────────────────────────────────

DEATH_SPIKE_HEADERS = ["Jahr", "Sterbefälle", "Baseline (10J-Ø)", "Abweichung %",
                        "Spike?", "Geschlecht-M", "Geschlecht-F", "Dominante Altersgruppe"]

AGE_DIST_HEADERS = ["Kohorte", "Altersgruppe", "Anteil %", "Absolut",
                     "Infant-Peak %", "Adult-Peak-Alter"]

MATERNAL_MORTALITY_HEADERS = ["Jahrhundert", "Müttertode", "Gesamtgeburten", "Rate pro 1000"]

CENTENARIAN_HEADERS = ["Person-ID", "Name", "Geburtsjahr", "Sterbejahr", "Alter",
                        "Geschlecht", "Geburtsland"]

BIRTH_ORDER_LIFESPAN_HEADERS = ["Epoche", "Geburtsrang", "Anzahl", "Ø Lebensalter",
                                  "Median Lebensalter"]

RURAL_URBAN_HEADERS = ["Epoche", "Typ", "Anzahl", "Ø Lebensalter", "Median"]

MARRIAGE_DURATION_HEADERS = ["Jahrhundert", "Ø Ehedauer (Jahre)", "Median", "Anzahl Ehen",
                               "Beendet durch Tod-M", "Beendet durch Tod-F", "Offen (lebend)"]

DIVORCE_HEADERS = ["Jahrhundert", "Ehen gesamt", "Scheidungen", "Rate %"]

LAST_CHILD_HEADERS = ["Jahrhundert", "Geschlecht", "Ø Alter letztes Kind", "Median", "Anzahl"]

NEVER_MARRIED_HEADERS = ["Jahrhundert", "Nie geheiratet ≥25", "Gesamt ≥25", "Rate %"]

PREMARITAL_CONCEPTION_HEADERS = ["Jahrhundert", "Vorehelich konzipiert", "Gesamt Erstgeborene",
                                   "Rate %"]

REMARRIAGE_HEADERS = ["Geschlecht", "Epoche", "Anzahl Wiederverheiratungen",
                       "Ø Jahre bis Wiederheirat", "Median",
                       "Anteil <1 Jahr %", "Anteil <3 Jahre %"]

MARRIAGE_DISTANCE_HEADERS = ["Epoche", "Ø Distanz km", "Median km",
                               "Unter 5 km %", "5–20 km %", "Über 20 km %", "Anzahl"]

PARISH_FERTILITY_HEADERS = ["Pfarrei/Ort", "Familien", "Ø Kinder/Familie",
                              "Median", "8+ Kinder %", "Epoche"]

EMIGRANT_STAYER_HEADERS = ["Gruppe", "Land", "Anzahl", "Ø Lebensalter",
                             "Median", "Differenz zu DE"]

CROSSOVER_HEADERS = ["Jahrzehnt", "Sterbefälle Deutschland", "Sterbefälle USA",
                      "Sterbefälle NL", "Sterbefälle Andere",
                      "USA-Anteil %", "Kumulativ DE", "Kumulativ USA"]

GRAVITY_HEADERS = ["Jahrzehnt", "Lat (gewichtet)", "Lon (gewichtet)",
                    "Dominantes Land", "Anteil Westfalen %", "Anteil Ohio %", "Anteil Texas %"]

GENANNT_HEADERS = ["Person-ID", "Name", "Geburtsname", "Hofname", "Geburtsjahr",
                    "Geburtsort", "Geschlecht", "Ehepartner-Nachname"]

OCCUPATION_LIFESPAN_HEADERS = ["Berufskategorie", "Anzahl", "Ø Lebensalter", "Median", "Epoche"]

SURNAME_GINI_HEADERS = ["Epoche", "Gini-Koeffizient", "Einzigartige Nachnamen",
                         "Top-5-Anteil %", "Häufigster Nachname", "Anteil %"]

AMERICANIZATION_HEADERS = ["Jahrzehnt", "Land", "Top-Vorname-1", "Anteil-1 %",
                             "Top-Vorname-2", "Anteil-2 %",
                             "Top-Vorname-3", "Anteil-3 %",
                             "Deutsch-Anteil %", "Englisch-Anteil %"]

# ── Lookup-Tabellen ────────────────────────────────────────────────────────────

PLACE_COORDS = {
    "hagen am teutoburger wald": (52.18, 8.02),
    "osnabrück": (52.28, 8.05),
    "glandorf": (52.09, 8.00),
    "belm": (52.30, 8.12),
    "wallenhorst": (52.35, 8.07),
    "oesede": (52.15, 8.02),
    "ostercappeln": (52.35, 8.22),
    "bohmte": (52.37, 8.33),
    "cappeln": (52.32, 8.15),
    "schwagstorf": (52.38, 8.20),
    "stemwede": (52.43, 8.45),
    "lübbecke": (52.31, 8.62),
    "rahden": (52.43, 8.61),
    "blasheim": (52.31, 8.65),
    "wehdem": (52.40, 8.58),
    "mettingen": (52.32, 7.77),
    "hitzhausen": (52.10, 7.98),
    "delphos": (40.84, -84.34),
    "glandorf oh": (40.87, -84.08),
    "fort jennings": (40.94, -84.30),
    "ottawa oh": (41.02, -84.04),
    "putnam county oh": (41.00, -84.13),
    "minster": (40.39, -84.37),
    "new wehdem": (29.72, -96.39),
    "galveston": (29.30, -94.80),
}

# Land-Mittelpunkte für Fallback
COUNTRY_COORDS = {
    "DE": (51.2, 10.4),
    "USA-OH": (40.4, -82.7),
    "USA-TX": (31.0, -100.0),
    "NL": (52.3, 5.3),
    "AU": (-25.0, 133.0),
}

URBAN_KEYWORDS = [
    "osnabrück", "münster", "hamburg", "bremen", "köln", "berlin",
    "amsterdam", "cincinnati", "cleveland", "columbus", "dayton", "lima",
    "houston", "galveston", "new york", "chicago",
]

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _safe_age(by, dy):
    """Gibt Alter zurück wenn sinnvoll, sonst None."""
    if by and dy and 1 <= dy - by <= 120:
        return dy - by
    return None


def _century(year):
    if year is None:
        return None
    return ((year - 1) // 100) * 100 + 1  # z.B. 1801 für 19. Jh.


def _century_label(year):
    if year is None:
        return None
    c = (year - 1) // 100 + 1
    return f"{c}. Jh."


def _epoch_50(year):
    if year is None:
        return None
    base = (year // 50) * 50
    return f"{base}–{base+49}"


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _lookup_coords(place_str):
    """Gibt (lat, lon) oder None zurück. Fuzzy-match über Lookup-Dict."""
    if not place_str:
        return None
    raw = place_str.lower()
    first = raw.split(",")[0].strip()
    # Direkter Treffer
    if first in PLACE_COORDS:
        return PLACE_COORDS[first]
    # Teilstring-Suche
    for key, coords in PLACE_COORDS.items():
        if key in first or first in key:
            return coords
    return None


def _extract_surname(name_str):
    """Extrahiert Nachname aus GEDCOM NAME ('Vorname /Nachname/')."""
    if not name_str:
        return ""
    parts = name_str.split("/")
    if len(parts) >= 2:
        return parts[1].strip()
    return name_str.strip()


def _extract_firstname(name_str):
    """Extrahiert Vorname aus GEDCOM NAME."""
    if not name_str:
        return ""
    return name_str.split("/")[0].strip()


def _parse_date_to_year_month(date_str):
    """Versucht Jahr und Monat aus GEDCOM-Datumsstring zu extrahieren."""
    if not date_str:
        return None, None
    parts = date_str.strip().split()
    year = None
    month = None
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
               "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
               "mär": 3, "okt": 10, "dez": 12}
    for p in parts:
        try:
            v = int(p)
            if 1400 <= v <= 2100:
                year = v
        except ValueError:
            key = p[:3].lower()
            if key in months:
                month = months[key]
    return year, month


def _parse_full_date(date_str):
    """Gibt (year, month, day) zurück, je nach Verfügbarkeit."""
    if not date_str:
        return None, None, None
    parts = date_str.strip().split()
    year = None
    month = None
    day = None
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
               "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
               "mär": 3, "okt": 10, "dez": 12}
    for p in parts:
        try:
            v = int(p)
            if 1400 <= v <= 2100:
                year = v
            elif 1 <= v <= 31 and day is None:
                day = v
        except ValueError:
            key = p[:3].lower()
            if key in months:
                month = months[key]
    return year, month, day


def _classify_country_simple(place_str):
    """Einfache Länderklassifikation ohne location_data."""
    if not place_str:
        return "Andere"
    p = place_str.lower()
    if any(x in p for x in ["ohio", "texas", "indiana", "michigan", "illinois",
                              "pennsylvania", "new york", "wisconsin", "usa",
                              "united states", "america", " oh,", " tx,",
                              " oh ", " tx "]):
        if any(x in p for x in ["ohio", " oh,", " oh "]):
            return "USA-Ohio"
        if any(x in p for x in ["texas", " tx,", " tx "]):
            return "USA-Texas"
        return "USA-Andere"
    if any(x in p for x in ["deutschland", "germany", "westfalen", "niedersachsen",
                              "preußen", "hanover", "hannover", "osnabrück"]):
        return "Deutschland"
    if any(x in p for x in ["netherlands", "niederlande", "holland", "nederland"]):
        return "Niederlande"
    if any(x in p for x in ["australia", "australien"]):
        return "Australien"
    # Grob: endet auf Bundesland/Landschaft
    return "Andere"


def _classify_country_with_data(place_str, location_data):
    if location_data is None:
        return _classify_country_simple(place_str)
    try:
        from lib.places import extract_country_from_place
        country = extract_country_from_place(place_str, location_data)
        if country in ("DE", "Germany", "Deutschland"):
            return "Deutschland"
        if country in ("US", "USA", "United States"):
            p = (place_str or "").lower()
            if any(x in p for x in ["ohio", " oh"]):
                return "USA-Ohio"
            if any(x in p for x in ["texas", " tx"]):
                return "USA-Texas"
            return "USA-Andere"
        if country in ("NL", "Netherlands"):
            return "Niederlande"
        if country in ("AU", "Australia"):
            return "Australien"
        return "Andere"
    except Exception:
        return _classify_country_simple(place_str)


def _avg(lst):
    return round(statistics.mean(lst), 1) if lst else ""


def _median(lst):
    return round(statistics.median(lst), 1) if lst else ""


# ── Analyse-Funktionen ─────────────────────────────────────────────────────────

def analyze_death_spikes(individuals):
    """1. Jährliche Sterbezahlreihe + Spitzenjahre."""
    yearly = defaultdict(lambda: {"total": 0, "M": 0, "F": 0, "ages": []})

    for pid, pdata in individuals.items():
        deat = pdata.get("DEAT") or {}
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        if not dy or not (1580 <= dy <= 2030):
            continue
        sex = pdata.get("SEX", "")
        birt = pdata.get("BIRT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        age = _safe_age(by, dy)

        yearly[dy]["total"] += 1
        if sex == "M":
            yearly[dy]["M"] += 1
        elif sex == "F":
            yearly[dy]["F"] += 1
        if age is not None:
            yearly[dy]["ages"].append(age)

    years = sorted(yearly.keys())
    if not years:
        return []

    def dominant_age_group(ages):
        if not ages:
            return ""
        groups = {"0–9": 0, "10–29": 0, "30–59": 0, "60+": 0}
        for a in ages:
            if a < 10:
                groups["0–9"] += 1
            elif a < 30:
                groups["10–29"] += 1
            elif a < 60:
                groups["30–59"] += 1
            else:
                groups["60+"] += 1
        return max(groups, key=groups.get)

    # Gleitender 10-Jahres-Durchschnitt
    rows = []
    for i, yr in enumerate(years):
        window = [yearly[y]["total"] for y in years
                  if abs(y - yr) <= 5 and y != yr]
        baseline = round(statistics.mean(window), 1) if window else 0
        total = yearly[yr]["total"]
        if baseline > 0:
            pct = round((total - baseline) / baseline * 100, 1)
        else:
            pct = ""
        spike = "SPIKE" if isinstance(pct, float) and pct > 40 else ""
        rows.append([
            yr,
            total,
            baseline,
            pct,
            spike,
            yearly[yr]["M"],
            yearly[yr]["F"],
            dominant_age_group(yearly[yr]["ages"]),
        ])
    return rows


def analyze_age_distribution(individuals):
    """2. Alter-beim-Tod Verteilung."""
    cohort_defs = [
        ("1700–1799", 1700, 1799),
        ("1750–1849", 1750, 1849),
        ("1800–1899", 1800, 1899),
        ("1850–1949", 1850, 1949),
        ("1900–1999", 1900, 1999),
    ]
    age_groups = [
        ("0–4",   0,  4),
        ("5–14",  5, 14),
        ("15–29", 15, 29),
        ("30–44", 30, 44),
        ("45–59", 45, 59),
        ("60–74", 60, 74),
        ("75–89", 75, 89),
        ("90+",   90, 200),
    ]

    rows = []
    for clabel, c_from, c_to in cohort_defs:
        ages_in_cohort = []
        for pid, pdata in individuals.items():
            birt = pdata.get("BIRT") or {}
            deat = pdata.get("DEAT") or {}
            by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
            dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
            if not by or not (c_from <= by <= c_to):
                continue
            age = _safe_age(by, dy)
            if age is not None:
                ages_in_cohort.append(age)

        if not ages_in_cohort:
            continue

        total = len(ages_in_cohort)
        infant_peak = round(sum(1 for a in ages_in_cohort if a <= 4) / total * 100, 1)
        adult_ages = [a for a in ages_in_cohort if a >= 15]
        if adult_ages:
            # Modalwert: häufigster Wert in 5-Jahres-Bins
            bins = defaultdict(int)
            for a in adult_ages:
                bins[(a // 5) * 5] += 1
            adult_peak = max(bins, key=bins.get) + 2  # Mitte des Bins
        else:
            adult_peak = ""

        for glabel, g_from, g_to in age_groups:
            count = sum(1 for a in ages_in_cohort if g_from <= a <= g_to)
            pct = round(count / total * 100, 1) if total else 0
            rows.append([clabel, glabel, pct, count, infant_peak, adult_peak])

    return rows


def analyze_maternal_mortality(individuals, families):
    """3. Müttersterblichkeit nach Jahrhundert."""
    # Sammle Kinder mit Geburtsjahr pro Mutter
    mother_births = defaultdict(list)  # mother_pid -> [child_by]

    for fid, fdata in families.items():
        wife = fdata.get("WIFE")
        if not wife:
            continue
        for chil in (fdata.get("CHIL") or []):
            cpdata = individuals.get(chil) or {}
            cbirt = cpdata.get("BIRT") or {}
            cby = cbirt.get("YEAR") or safe_extract_year(cbirt.get("DATE", ""))
            if cby:
                mother_births[wife].append(cby)

    # Gesamtgeburten pro Jahrhundert
    century_births = defaultdict(int)
    century_deaths = defaultdict(int)

    for pid, pdata in individuals.items():
        if pdata.get("SEX") != "F":
            continue
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))

        if not by:
            continue

        # Zähle Geburten
        child_years = mother_births.get(pid, [])
        century = _century_label(by)
        century_births[century] += len(child_years)

        # Prüfe Müttertod
        if dy and child_years:
            if dy in child_years or (dy - 1) in child_years:
                century_deaths[century] += 1

    rows = []
    for c in sorted(century_births.keys()):
        births = century_births[c]
        deaths = century_deaths.get(c, 0)
        rate = round(deaths / births * 1000, 1) if births else 0
        rows.append([c, deaths, births, rate])
    return rows


def find_centenarians(individuals):
    """4. Hundertjährige-Register."""
    results = []
    for pid, pdata in individuals.items():
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        age = _safe_age(by, dy)
        if age is None or age < 100:
            continue
        bplace = birt.get("PLAC", "")
        country = _classify_country_simple(bplace)
        results.append([
            pid,
            pdata.get("NAME", ""),
            by,
            dy,
            age,
            pdata.get("SEX", ""),
            country,
        ])
    results.sort(key=lambda r: r[4], reverse=True)
    return results


def analyze_birth_order_lifespan(individuals, families):
    """5. Geburtsrang vs. Lebenserwartung."""
    # Sammle Kinder geordnet nach Geburtsjahr pro Familie
    person_rank = {}  # pid -> rank (1-based)

    for fid, fdata in families.items():
        children = fdata.get("CHIL") or []
        if not children:
            continue
        child_years = []
        for chil in children:
            cpdata = individuals.get(chil) or {}
            cbirt = cpdata.get("BIRT") or {}
            cby = cbirt.get("YEAR") or safe_extract_year(cbirt.get("DATE", ""))
            child_years.append((cby or 9999, chil))
        child_years.sort()
        for rank, (_, chil) in enumerate(child_years, 1):
            person_rank[chil] = rank

    def rank_group(rank):
        if rank == 1:
            return "Erstgeboren"
        elif rank <= 3:
            return "2.–3. Kind"
        elif rank <= 6:
            return "4.–6. Kind"
        else:
            return "7.+ Kind"

    def epoch(by):
        if by is None:
            return None
        if by < 1800:
            return "vor 1800"
        elif by < 1900:
            return "1800–1899"
        else:
            return "1900+"

    bucket = defaultdict(list)  # (epoch, rank_group) -> [ages]

    for pid, pdata in individuals.items():
        rank = person_rank.get(pid)
        if rank is None:
            continue
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        age = _safe_age(by, dy)
        if age is None:
            continue
        ep = epoch(by)
        if ep is None:
            continue
        bucket[(ep, rank_group(rank))].append(age)

    rows = []
    epoch_order = ["vor 1800", "1800–1899", "1900+"]
    rg_order = ["Erstgeboren", "2.–3. Kind", "4.–6. Kind", "7.+ Kind"]
    for ep in epoch_order:
        for rg in rg_order:
            ages = bucket.get((ep, rg), [])
            if not ages:
                continue
            rows.append([ep, rg, len(ages), _avg(ages), _median(ages)])
    return rows


def analyze_rural_urban_lifespan(individuals):
    """6. Stadt-Land-Lebenserwartung."""
    def is_urban(place):
        if not place:
            return False
        p = place.lower()
        return any(kw in p for kw in URBAN_KEYWORDS)

    def epoch(by):
        if by is None:
            return None
        if by < 1700:
            return "vor 1700"
        elif by < 1800:
            return "1700–1799"
        elif by < 1850:
            return "1800–1849"
        elif by < 1900:
            return "1850–1899"
        elif by < 1950:
            return "1900–1949"
        else:
            return "1950+"

    bucket = defaultdict(list)  # (epoch, typ) -> [ages]

    for pid, pdata in individuals.items():
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        age = _safe_age(by, dy)
        if age is None:
            continue
        bplace = birt.get("PLAC", "")
        typ = "städtisch" if is_urban(bplace) else "ländlich"
        ep = epoch(by)
        if ep is None:
            continue
        bucket[(ep, typ)].append(age)

    rows = []
    ep_order = ["vor 1700", "1700–1799", "1800–1849", "1850–1899", "1900–1949", "1950+"]
    for ep in ep_order:
        for typ in ["städtisch", "ländlich"]:
            ages = bucket.get((ep, typ), [])
            if not ages:
                continue
            rows.append([ep, typ, len(ages), _avg(ages), _median(ages)])
    return rows


def analyze_marriage_duration(individuals, families):
    """7. Ehedauer nach Jahrhundert."""
    century_data = defaultdict(lambda: {"durations": [], "by_husb": 0, "by_wife": 0, "open": 0})

    for fid, fdata in families.items():
        marr = fdata.get("MARR_DATE", "")
        my, _ = _parse_date_to_year_month(marr)
        if not my:
            continue
        label = _century_label(my)

        husb_id = fdata.get("HUSB")
        wife_id = fdata.get("WIFE")

        husb_dy = None
        wife_dy = None

        if husb_id:
            hp = individuals.get(husb_id) or {}
            hd = hp.get("DEAT") or {}
            husb_dy = hd.get("YEAR") or safe_extract_year(hd.get("DATE", ""))

        if wife_id:
            wp = individuals.get(wife_id) or {}
            wd = wp.get("DEAT") or {}
            wife_dy = wd.get("YEAR") or safe_extract_year(wd.get("DATE", ""))

        if husb_dy and wife_dy:
            first_death = min(husb_dy, wife_dy)
            dur = first_death - my
            if 0 <= dur <= 80:
                century_data[label]["durations"].append(dur)
                if husb_dy < wife_dy:
                    century_data[label]["by_husb"] += 1
                else:
                    century_data[label]["by_wife"] += 1
        elif husb_dy:
            dur = husb_dy - my
            if 0 <= dur <= 80:
                century_data[label]["durations"].append(dur)
                century_data[label]["by_husb"] += 1
        elif wife_dy:
            dur = wife_dy - my
            if 0 <= dur <= 80:
                century_data[label]["durations"].append(dur)
                century_data[label]["by_wife"] += 1
        else:
            century_data[label]["open"] += 1

    rows = []
    for c in sorted(century_data.keys()):
        d = century_data[c]
        durs = d["durations"]
        n = len(durs)
        rows.append([
            c,
            _avg(durs),
            _median(durs),
            n + d["open"],
            d["by_husb"],
            d["by_wife"],
            d["open"],
        ])
    return rows


def analyze_divorce_rate(families):
    """8. Scheidungsrate nach Jahrhundert."""
    century_data = defaultdict(lambda: {"total": 0, "div": 0})

    for fid, fdata in families.items():
        marr = fdata.get("MARR_DATE", "")
        my, _ = _parse_date_to_year_month(marr)
        if not my:
            continue
        label = _century_label(my)
        century_data[label]["total"] += 1
        if fdata.get("DIV_DATE"):
            century_data[label]["div"] += 1

    rows = []
    for c in sorted(century_data.keys()):
        d = century_data[c]
        total = d["total"]
        div = d["div"]
        rate = round(div / total * 100, 1) if total else 0
        rows.append([c, total, div, rate])
    return rows


def analyze_last_child_age(individuals, families):
    """9. Alter beim letzten Kind nach Jahrhundert."""
    parent_last_child = defaultdict(list)  # pid -> [child_by]

    for fid, fdata in families.items():
        children = fdata.get("CHIL") or []
        child_years = []
        for chil in children:
            cpdata = individuals.get(chil) or {}
            cbirt = cpdata.get("BIRT") or {}
            cby = cbirt.get("YEAR") or safe_extract_year(cbirt.get("DATE", ""))
            if cby:
                child_years.append(cby)
        if not child_years:
            continue
        last_year = max(child_years)
        for role in ["HUSB", "WIFE"]:
            pid = fdata.get(role)
            if pid:
                parent_last_child[pid].append(last_year)

    bucket = defaultdict(list)  # (century, sex) -> [ages at last child]

    for pid, last_years in parent_last_child.items():
        pdata = individuals.get(pid) or {}
        birt = pdata.get("BIRT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        if not by:
            continue
        sex = pdata.get("SEX", "?")
        label = _century_label(by)
        last_child_year = max(last_years)
        age = last_child_year - by
        if 15 <= age <= 70:
            bucket[(label, sex)].append(age)

    rows = []
    for key in sorted(bucket.keys()):
        c, sex = key
        ages = bucket[key]
        rows.append([c, sex, _avg(ages), _median(ages), len(ages)])
    return rows


def analyze_never_married(individuals):
    """10. Nie-geheiratet-Rate nach Jahrhundert."""
    bucket = defaultdict(lambda: {"never": 0, "total": 0})

    for pid, pdata in individuals.items():
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        if not by or not dy:
            continue
        age = _safe_age(by, dy)
        if age is None or age < 25:
            continue
        label = _century_label(by)
        bucket[label]["total"] += 1
        if not pdata.get("FAMS"):
            bucket[label]["never"] += 1

    rows = []
    for c in sorted(bucket.keys()):
        d = bucket[c]
        total = d["total"]
        never = d["never"]
        rate = round(never / total * 100, 1) if total else 0
        rows.append([c, never, total, rate])
    return rows


def analyze_premarital_conception(individuals, families):
    """11. Voreheliche Konzeptionsrate nach Jahrhundert."""
    bucket = defaultdict(lambda: {"premarital": 0, "total": 0})

    for fid, fdata in families.items():
        marr = fdata.get("MARR_DATE", "")
        my, mm = _parse_date_to_year_month(marr)
        if not my or not mm:
            continue

        children = fdata.get("CHIL") or []
        if not children:
            continue

        # Finde erstgeborenes Kind nach Datum
        first_child = None
        first_date = None
        for chil in children:
            cpdata = individuals.get(chil) or {}
            cbirt = cpdata.get("BIRT") or {}
            cdate = cbirt.get("DATE", "")
            cy, cm = _parse_date_to_year_month(cdate)
            if cy and cm:
                if first_date is None or (cy, cm) < first_date:
                    first_date = (cy, cm)
                    first_child = chil

        if first_date is None:
            continue

        cy, cm = first_date
        marr_months = my * 12 + mm
        birth_months = cy * 12 + cm
        diff_months = birth_months - marr_months

        label = _century_label(my)
        bucket[label]["total"] += 1
        if diff_months < 8:
            bucket[label]["premarital"] += 1

    rows = []
    for c in sorted(bucket.keys()):
        d = bucket[c]
        total = d["total"]
        premarital = d["premarital"]
        rate = round(premarital / total * 100, 1) if total else 0
        rows.append([c, premarital, total, rate])
    return rows


def analyze_remarriage_speed(individuals, families):
    """12. Witwen/Witwer-Wiederheirats-Geschwindigkeit."""
    # Sammle alle Eheschließungen pro Person mit Datum
    person_marriages = defaultdict(list)  # pid -> [(marr_year, marr_month, fid)]

    for fid, fdata in families.items():
        marr = fdata.get("MARR_DATE", "")
        my, mm = _parse_date_to_year_month(marr)
        if not my:
            continue
        for role in ["HUSB", "WIFE"]:
            pid = fdata.get(role)
            if pid:
                person_marriages[pid].append((my, mm or 6, fid))

    bucket = defaultdict(list)  # (sex, epoch) -> [years_to_remarriage]

    for pid, marriages in person_marriages.items():
        if len(marriages) < 2:
            continue
        marriages.sort()
        pdata = individuals.get(pid) or {}
        sex = pdata.get("SEX", "?")

        for i in range(len(marriages) - 1):
            prev_my, prev_mm, prev_fid = marriages[i]
            next_my, next_mm, next_fid = marriages[i + 1]

            # Prüfe ob voriger Ehepartner gestorben ist
            prev_fdata = families.get(prev_fid) or {}
            spouse_role = "WIFE" if sex == "M" else "HUSB"
            spouse_id = prev_fdata.get(spouse_role)
            if not spouse_id:
                continue

            sp = individuals.get(spouse_id) or {}
            sdeat = sp.get("DEAT") or {}
            sdy = sdeat.get("YEAR") or safe_extract_year(sdeat.get("DATE", ""))
            if not sdy:
                continue

            # Ehepartner muss vor Wiederheirat gestorben sein
            if sdy > next_my:
                continue

            years_to_remarry = (next_my * 12 + next_mm - sdy * 12 - 6) / 12.0
            if 0 <= years_to_remarry <= 50:
                birt = pdata.get("BIRT") or {}
                by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
                ep = "vor 1800" if (by and by < 1800) else ("1800–1899" if (by and by < 1900) else "1900+")
                bucket[(sex, ep)].append(years_to_remarry)

    rows = []
    for key in sorted(bucket.keys()):
        sex, ep = key
        yrs = bucket[key]
        lt1 = round(sum(1 for y in yrs if y < 1) / len(yrs) * 100, 1)
        lt3 = round(sum(1 for y in yrs if y < 3) / len(yrs) * 100, 1)
        rows.append([sex, ep, len(yrs), _avg(yrs), _median(yrs), lt1, lt3])
    return rows


def analyze_marriage_distance(individuals, families):
    """13. Heiratsdistanz (Endogamie-Radius)."""
    def epoch(year):
        if year is None:
            return None
        if year < 1750:
            return "1600–1749"
        elif year < 1850:
            return "1750–1849"
        elif year < 1900:
            return "1850–1899"
        elif year < 1950:
            return "1900–1949"
        else:
            return "1950+"

    bucket = defaultdict(list)  # epoch -> [distances]

    for fid, fdata in families.items():
        marr = fdata.get("MARR_DATE", "")
        my, _ = _parse_date_to_year_month(marr)
        ep = epoch(my)
        if not ep:
            continue

        husb_id = fdata.get("HUSB")
        wife_id = fdata.get("WIFE")
        if not husb_id or not wife_id:
            continue

        hp = individuals.get(husb_id) or {}
        wp = individuals.get(wife_id) or {}
        hbirt = hp.get("BIRT") or {}
        wbirt = wp.get("BIRT") or {}
        h_place = hbirt.get("PLAC", "")
        w_place = wbirt.get("PLAC", "")

        h_coords = _lookup_coords(h_place)
        w_coords = _lookup_coords(w_place)

        if not h_coords or not w_coords:
            continue

        dist = _haversine(h_coords[0], h_coords[1], w_coords[0], w_coords[1])
        bucket[ep].append(dist)

    rows = []
    ep_order = ["1600–1749", "1750–1849", "1850–1899", "1900–1949", "1950+"]
    for ep in ep_order:
        dists = bucket.get(ep, [])
        if not dists:
            continue
        n = len(dists)
        lt5 = round(sum(1 for d in dists if d < 5) / n * 100, 1)
        m5_20 = round(sum(1 for d in dists if 5 <= d <= 20) / n * 100, 1)
        gt20 = round(sum(1 for d in dists if d > 20) / n * 100, 1)
        rows.append([ep, _avg(dists), _median(dists), lt5, m5_20, gt20, n])
    return rows


def analyze_parish_fertility(individuals, families):
    """14. Pfarrei-Fertilität."""
    def normalize_place(place):
        if not place:
            return ""
        return place.split(",")[0].strip().lower()

    def epoch(year):
        if not year:
            return "unbekannt"
        if year < 1800:
            return "vor 1800"
        elif year < 1900:
            return "1800–1899"
        else:
            return "1900+"

    parish_families = defaultdict(list)  # (parish, epoch) -> [n_children]

    for fid, fdata in families.items():
        wife_id = fdata.get("WIFE")
        if not wife_id:
            continue
        wp = individuals.get(wife_id) or {}
        wbirt = wp.get("BIRT") or {}
        wplace = normalize_place(wbirt.get("PLAC", ""))
        if not wplace:
            continue
        wy = wbirt.get("YEAR") or safe_extract_year(wbirt.get("DATE", ""))
        ep = epoch(wy)
        n_children = len(fdata.get("CHIL") or [])
        parish_families[(wplace, ep)].append(n_children)

    rows = []
    for (parish, ep), counts in sorted(parish_families.items()):
        if len(counts) < 5:
            continue
        avg = _avg(counts)
        med = _median(counts)
        pct8 = round(sum(1 for c in counts if c >= 8) / len(counts) * 100, 1)
        rows.append([parish, len(counts), avg, med, pct8, ep])
    rows.sort(key=lambda r: r[2] if r[2] != "" else 0, reverse=True)
    return rows


def analyze_emigrant_vs_stayer(individuals, location_data=None):
    """15. Auswanderer vs. Daheimgebliebene."""
    bucket = defaultdict(list)  # country -> [ages]

    for pid, pdata in individuals.items():
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        if not by or not dy:
            continue
        age = _safe_age(by, dy)
        if age is None or not (20 <= age <= 110):
            continue

        dplace = (deat.get("PLAC") or "")
        country = _classify_country_with_data(dplace, location_data)
        bucket[country].append(age)

    # Referenz: Deutschland
    de_avg = _avg(bucket.get("Deutschland", []))

    rows = []
    order = ["Deutschland", "USA-Ohio", "USA-Texas", "USA-Andere",
             "Niederlande", "Australien", "Andere"]
    for country in order:
        ages = bucket.get(country, [])
        if not ages:
            continue
        avg = _avg(ages)
        diff = round(float(avg) - float(de_avg), 1) if avg != "" and de_avg != "" else ""
        rows.append([
            "Auswanderer" if country != "Deutschland" else "Daheimgeblieben",
            country,
            len(ages),
            avg,
            _median(ages),
            diff,
        ])
    return rows


def analyze_crossover(individuals, location_data=None):
    """16. Deutschland vs. Amerika Kreuzungspunkt."""
    decade_data = defaultdict(lambda: defaultdict(int))

    for pid, pdata in individuals.items():
        deat = pdata.get("DEAT") or {}
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        if not dy:
            continue
        decade = (dy // 10) * 10
        dplace = (deat.get("PLAC") or "")
        country = _classify_country_with_data(dplace, location_data)
        decade_data[decade][country] += 1

    rows = []
    cum_de = 0
    cum_usa = 0
    for decade in sorted(decade_data.keys()):
        d = decade_data[decade]
        de = d.get("Deutschland", 0)
        usa = d.get("USA-Ohio", 0) + d.get("USA-Texas", 0) + d.get("USA-Andere", 0)
        nl = d.get("Niederlande", 0)
        other = d.get("Australien", 0) + d.get("Andere", 0)
        total = de + usa + nl + other
        usa_pct = round(usa / total * 100, 1) if total else 0
        cum_de += de
        cum_usa += usa
        rows.append([decade, de, usa, nl, other, usa_pct, cum_de, cum_usa])
    return rows


def analyze_demographic_gravity(individuals, location_data=None):
    """17. Demographischer Schwerpunkt."""
    decade_points = defaultdict(list)  # decade -> [(lat, lon, country)]

    for pid, pdata in individuals.items():
        deat = pdata.get("DEAT") or {}
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        if not dy:
            continue
        decade = (dy // 10) * 10
        dplace = (deat.get("PLAC") or "")
        country = _classify_country_with_data(dplace, location_data)

        coords = _lookup_coords(dplace)
        if not coords:
            # Fallback auf Land-Mittelpunkt
            if country == "Deutschland":
                coords = COUNTRY_COORDS["DE"]
            elif country == "USA-Ohio":
                coords = COUNTRY_COORDS["USA-OH"]
            elif country == "USA-Texas":
                coords = COUNTRY_COORDS["USA-TX"]
            elif country == "Niederlande":
                coords = COUNTRY_COORDS["NL"]
            elif country == "Australien":
                coords = COUNTRY_COORDS["AU"]
            else:
                continue

        decade_points[decade].append((coords[0], coords[1], country))

    rows = []
    westfalen_kws = ["westfal", "osnabrück", "münster", "glandorf", "hagen",
                      "belm", "bohmte", "cappeln"]
    ohio_kws = ["ohio", " oh,", " oh "]
    texas_kws = ["texas", " tx,", " tx "]

    for decade in sorted(decade_points.keys()):
        pts = decade_points[decade]
        if not pts:
            continue
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        avg_lat = round(statistics.mean(lats), 3)
        avg_lon = round(statistics.mean(lons), 3)

        country_counts = defaultdict(int)
        for p in pts:
            country_counts[p[2]] += 1
        dominant = max(country_counts, key=country_counts.get)
        n = len(pts)

        # Anteile: Westfalen = Deutschland mit westfälischen Koordinaten (lat > 51, lon 7-9)
        westfalen = sum(1 for p in pts if 51 <= p[0] <= 53 and 7 <= p[1] <= 10)
        ohio = sum(1 for p in pts if 38 <= p[0] <= 43 and -86 <= p[1] <= -79)
        texas = sum(1 for p in pts if 25 <= p[0] <= 37 and -107 <= p[1] <= -93)

        rows.append([
            decade, avg_lat, avg_lon, dominant,
            round(westfalen / n * 100, 1),
            round(ohio / n * 100, 1),
            round(texas / n * 100, 1),
        ])
    return rows


def analyze_genannt_names(individuals, families):
    """18. Hofnamen (genannt) Analyse."""
    rows = []
    for pid, pdata in individuals.items():
        name = pdata.get("NAME", "")
        if "genannt" not in name.lower():
            continue

        # Extrahiere Teile
        lower = name.lower()
        idx = lower.find(" genannt ")
        if idx < 0:
            continue

        birth_name_part = name[:idx].strip()
        hof_name_part = name[idx + len(" genannt "):].strip().strip("/").strip()

        birt = pdata.get("BIRT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        bplace = birt.get("PLAC", "")
        sex = pdata.get("SEX", "")

        # Ehepartner-Nachname
        spouse_surnames = []
        for fid in (pdata.get("FAMS") or []):
            fdata = families.get(fid) or {}
            spouse_role = "WIFE" if sex == "M" else "HUSB"
            spouse_id = fdata.get(spouse_role)
            if spouse_id:
                sp = individuals.get(spouse_id) or {}
                sn = _extract_surname(sp.get("NAME", ""))
                if sn:
                    spouse_surnames.append(sn)

        rows.append([
            pid,
            name,
            birth_name_part,
            hof_name_part,
            by or "",
            bplace,
            sex,
            "; ".join(spouse_surnames),
        ])
    return rows


def analyze_occupation_lifespan(individuals):
    """19. Berufsstand-Lebenserwartung."""
    EDU_KWS = ["lehrer", "pastor", "priester", "pater", "kaplan", "arzt",
                "doktor", "apotheker", "jurist", "notar"]
    FARMER_KWS = ["bauer", "farmer", "landwirt", "ackerbauer", "colonus",
                   "landmann", "colon"]
    CRAFT_KWS = ["schlosser", "tischler", "zimmermann", "schmied", "schneider",
                  "schuster", "bäcker", "metzger", "küfer", "weber", "leineweber"]
    MERCHANT_KWS = ["kaufmann", "händler", "krämer", "merchant"]
    LABOR_KWS = ["heuerling", "knecht", "tagelöhner", "laborer", "labourer", "arbeiter"]
    NOBLE_KWS = ["von ", "graf", "baron", "freiherr", "ritter"]

    def classify(occu, name):
        s = (occu or "").lower()
        n = (name or "").lower()
        if any(k in s for k in EDU_KWS):
            return "Bildung/Kirche/Medizin"
        if any(k in s for k in FARMER_KWS):
            return "Bauer/Landwirt"
        if any(k in s for k in CRAFT_KWS):
            return "Handwerker"
        if any(k in s for k in MERCHANT_KWS):
            return "Kaufmann"
        if any(k in s for k in LABOR_KWS):
            return "Heuerling/Knecht"
        if any(k in n for k in NOBLE_KWS):
            return "Adel"
        if s:
            return "Sonstiges"
        return None

    def epoch(by):
        if by is None:
            return "unbekannt"
        if by < 1800:
            return "vor 1800"
        elif by < 1900:
            return "1800–1899"
        else:
            return "1900+"

    bucket = defaultdict(list)  # (category, epoch) -> [ages]

    for pid, pdata in individuals.items():
        occu = pdata.get("OCCU") or pdata.get("OCC") or ""
        name = pdata.get("NAME", "")
        cat = classify(occu, name)
        if cat is None:
            continue
        birt = pdata.get("BIRT") or {}
        deat = pdata.get("DEAT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        dy = deat.get("YEAR") or safe_extract_year(deat.get("DATE", ""))
        age = _safe_age(by, dy)
        if age is None:
            continue
        bucket[(cat, epoch(by))].append(age)

    rows = []
    for key in sorted(bucket.keys()):
        cat, ep = key
        ages = bucket[key]
        rows.append([cat, len(ages), _avg(ages), _median(ages), ep])
    return rows


def analyze_surname_gini(individuals):
    """20. Nachnamen-Gini-Koeffizient nach Epoche."""
    def gini(values):
        if not values:
            return 0.0
        values = sorted(values)
        n = len(values)
        total = sum(values)
        if total == 0:
            return 0.0
        cumsum = 0
        for i, v in enumerate(values):
            cumsum += v * (n - i)
        return round(1 - 2 * cumsum / (n * total) + 1 / n, 4)

    epochs = []
    for start in range(1700, 2000, 50):
        epochs.append((f"{start}–{start+49}", start, start + 49))

    rows = []
    for label, e_from, e_to in epochs:
        surname_counts = defaultdict(int)
        for pid, pdata in individuals.items():
            birt = pdata.get("BIRT") or {}
            by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
            if not by or not (e_from <= by <= e_to):
                continue
            sn = _extract_surname(pdata.get("NAME", ""))
            if sn:
                surname_counts[sn] += 1

        if not surname_counts:
            continue

        total = sum(surname_counts.values())
        top5 = sorted(surname_counts.values(), reverse=True)[:5]
        top5_pct = round(sum(top5) / total * 100, 1)
        top_name = max(surname_counts, key=surname_counts.get)
        top_pct = round(surname_counts[top_name] / total * 100, 1)
        g = gini(list(surname_counts.values()))

        rows.append([
            label, g, len(surname_counts), top5_pct, top_name, top_pct
        ])
    return rows


def analyze_americanization(individuals, location_data=None):
    """21. Vornamen-Amerikanisierungs-Zeitstempel."""
    GERMAN_NAMES = {"johann", "johannes", "heinrich", "friedrich", "karl",
                     "wilhelm", "joseph", "anna", "maria", "katharina",
                     "margaretha", "georg", "anton", "franz", "peter",
                     "paul", "bernhard", "caspar", "gerhard"}
    ENGLISH_NAMES = {"john", "james", "william", "henry", "george", "charles",
                      "edward", "robert", "joseph", "mary", "margaret",
                      "elizabeth", "alice", "helen", "ruth", "dorothy",
                      "catherine", "frances"}

    # Nur USA-Geborene
    decade_data = defaultdict(list)  # decade -> [first_name]

    for pid, pdata in individuals.items():
        birt = pdata.get("BIRT") or {}
        by = birt.get("YEAR") or safe_extract_year(birt.get("DATE", ""))
        if not by:
            continue
        bplace = birt.get("PLAC") or ""
        country = _classify_country_with_data(bplace, location_data)
        if not country.startswith("USA"):
            continue

        fn = _extract_firstname(pdata.get("NAME", "")).split()[0] if _extract_firstname(pdata.get("NAME", "")) else ""
        if not fn:
            continue

        decade = (by // 10) * 10
        decade_data[decade].append(fn.lower())

    rows = []
    for decade in sorted(decade_data.keys()):
        names = decade_data[decade]
        if not names:
            continue
        n = len(names)
        name_counts = defaultdict(int)
        for nm in names:
            name_counts[nm] += 1
        top3 = sorted(name_counts.items(), key=lambda x: x[1], reverse=True)[:3]

        # Pad to 3
        while len(top3) < 3:
            top3.append(("", 0))

        german_pct = round(sum(1 for nm in names if nm in GERMAN_NAMES) / n * 100, 1)
        english_pct = round(sum(1 for nm in names if nm in ENGLISH_NAMES) / n * 100, 1)

        rows.append([
            decade,
            "USA",
            top3[0][0], round(top3[0][1] / n * 100, 1) if top3[0][1] else "",
            top3[1][0], round(top3[1][1] / n * 100, 1) if top3[1][1] else "",
            top3[2][0], round(top3[2][1] / n * 100, 1) if top3[2][1] else "",
            german_pct,
            english_pct,
        ])
    return rows


# ── Haupt-Einstiegspunkt ───────────────────────────────────────────────────────

def run_book_statistics(individuals, families, location_data=None, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)

    p("Sterbespitzen analysieren …")
    death_spikes = analyze_death_spikes(individuals)

    p("Altersverteilung berechnen …")
    age_distribution = analyze_age_distribution(individuals)

    p("Müttersterblichkeit analysieren …")
    maternal_mortality = analyze_maternal_mortality(individuals, families)

    p("Hundertjährige suchen …")
    centenarians = find_centenarians(individuals)

    p("Geburtsrang vs. Lebenserwartung …")
    birth_order_lifespan = analyze_birth_order_lifespan(individuals, families)

    p("Stadt-Land-Lebenserwartung …")
    rural_urban = analyze_rural_urban_lifespan(individuals)

    p("Ehedauer analysieren …")
    marriage_duration = analyze_marriage_duration(individuals, families)

    p("Scheidungsrate berechnen …")
    divorce_rate = analyze_divorce_rate(families)

    p("Alter beim letzten Kind …")
    last_child_age = analyze_last_child_age(individuals, families)

    p("Nie-Geheiratet-Rate …")
    never_married = analyze_never_married(individuals)

    p("Voreheliche Konzeption …")
    premarital_conception = analyze_premarital_conception(individuals, families)

    p("Wiederheirat-Geschwindigkeit …")
    remarriage_speed = analyze_remarriage_speed(individuals, families)

    p("Heiratsdistanz (Endogamie-Radius) …")
    marriage_distance = analyze_marriage_distance(individuals, families)

    p("Pfarrei-Fertilität …")
    parish_fertility = analyze_parish_fertility(individuals, families)

    p("Auswanderer vs. Stayer …")
    emigrant_stayer = analyze_emigrant_vs_stayer(individuals, location_data)

    p("DE-USA Kreuzungspunkt …")
    crossover = analyze_crossover(individuals, location_data)

    p("Demographischer Schwerpunkt …")
    gravity = analyze_demographic_gravity(individuals, location_data)

    p("Hofnamen (genannt) …")
    genannt = analyze_genannt_names(individuals, families)

    p("Berufsstand-Lebenserwartung …")
    occupation_lifespan = analyze_occupation_lifespan(individuals)

    p("Nachnamen-Gini …")
    surname_gini = analyze_surname_gini(individuals)

    p("Vornamen-Amerikanisierung …")
    americanization = analyze_americanization(individuals, location_data)

    p("Buch-Statistiken fertig.", tag="ok")

    return {
        "death_spikes": death_spikes,
        "age_distribution": age_distribution,
        "maternal_mortality": maternal_mortality,
        "centenarians": centenarians,
        "birth_order_lifespan": birth_order_lifespan,
        "rural_urban": rural_urban,
        "marriage_duration": marriage_duration,
        "divorce_rate": divorce_rate,
        "last_child_age": last_child_age,
        "never_married": never_married,
        "premarital_conception": premarital_conception,
        "remarriage_speed": remarriage_speed,
        "marriage_distance": marriage_distance,
        "parish_fertility": parish_fertility,
        "emigrant_stayer": emigrant_stayer,
        "crossover": crossover,
        "gravity": gravity,
        "genannt": genannt,
        "occupation_lifespan": occupation_lifespan,
        "surname_gini": surname_gini,
        "americanization": americanization,
    }
