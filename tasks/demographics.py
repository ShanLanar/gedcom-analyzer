# -*- coding: utf-8 -*-
"""tasks/demographics.py – Demografische Analysen, Nachnamen, Geburtsländer"""

import math
from collections import Counter, defaultdict
from lib.gedcom import safe_extract_year
from lib.places import extract_country_from_place, format_place_for_display
from lib.helpers import safe_extract_family_name, safe_determine_migration_status


# ── Demografische Statistiken ──────────────────────────────────────────────────

EPOCHS = {
    "vor_1800":   (1500, 1799),
    "1800-1850":  (1800, 1849),
    "1850-1900":  (1850, 1899),
    "1900-1950":  (1900, 1949),
    "nach_1950":  (1950, 2024),
}


def analyze_demographic_statistics(individuals, families, location_data,
                                    progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Demografische Statistiken …")

    stats_by_epoch = {
        ep: {sx: {"count": 0, "age_at_first_marriage": [], "children_count": [],
                   "lifespan": [], "child_mortality": 0, "total_children": 0}
             for sx in ("M", "F", "U")}
        for ep in EPOCHS
    }

    for pid, pdata in individuals.items():
        sex = pdata.get("SEX", "U")
        if sex not in ("M", "F"): sex = "U"
        birth_year = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if not birth_year: continue
        ep = next((k for k, (s, e) in EPOCHS.items() if s <= birth_year <= e), None)
        if not ep: continue
        st = stats_by_epoch[ep][sex]
        st["count"] += 1

        death_year = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        if death_year and death_year > birth_year:
            ls = death_year - birth_year
            if 0 < ls <= 120: st["lifespan"].append(ls)

        first_my = None
        for fid in pdata.get("FAMS", []):
            fam = families.get(fid, {})
            if fam:
                my = safe_extract_year(fam.get("MARR_DATE"))
                if my and (not first_my or my < first_my): first_my = my
        if first_my:
            age_m = first_my - birth_year
            if 12 <= age_m <= 80: st["age_at_first_marriage"].append(age_m)

        children = sum(len(families.get(fid, {}).get("CHIL", []))
                       for fid in pdata.get("FAMS", []))
        if children > 0:
            st["children_count"].append(children)
            st["total_children"] += children
            for fid in pdata.get("FAMS", []):
                for cid in families.get(fid, {}).get("CHIL", []):
                    cd = individuals.get(cid, {})
                    if cd:
                        dcy = safe_extract_year((cd.get("DEAT") or {}).get("DATE"))
                        bcy = safe_extract_year((cd.get("BIRT") or {}).get("DATE"))
                        if dcy and bcy and dcy - bcy < 5:
                            st["child_mortality"] += 1

    results = []
    for ep_name, ep_stats in stats_by_epoch.items():
        for sx in ("M", "F", "U"):
            st = ep_stats[sx]
            if st["count"] == 0: continue
            avg_ls = sum(st["lifespan"]) / len(st["lifespan"]) if st["lifespan"] else 0
            avg_am = sum(st["age_at_first_marriage"]) / len(st["age_at_first_marriage"]) \
                     if st["age_at_first_marriage"] else 0
            avg_ch = sum(st["children_count"]) / len(st["children_count"]) \
                     if st["children_count"] else 0
            cmr = st["child_mortality"] / st["total_children"] * 100 \
                  if st["total_children"] > 0 else 0
            fr = st["total_children"] / st["count"] if st["count"] > 0 else 0
            ls_str = ""
            if st["lifespan"]:
                sls = sorted(st["lifespan"])
                ls_str = f"{min(sls)}-{max(sls)} (Ø{avg_ls:.1f}, Med{sls[len(sls)//2]})"
            results.append([
                ep_name,
                "Männlich" if sx == "M" else "Weiblich" if sx == "F" else "Unbekannt",
                st["count"], f"{avg_ls:.1f}" if st["lifespan"] else "n/a",
                ls_str, f"{avg_am:.1f}" if st["age_at_first_marriage"] else "n/a",
                f"{avg_ch:.1f}" if st["children_count"] else "0",
                f"{fr:.2f}", st["child_mortality"], f"{cmr:.1f}%",
                len(st["children_count"]), st["total_children"]
            ])
    p(f"Demografie: {len(results)} Einträge", tag="ok")
    return results


DEMOGRAPHIC_HEADERS = [
    "Epoche", "Geschlecht", "Anzahl Personen", "Ø Lebenserwartung",
    "Lebensspanne (Min-Max, Ø, Med)", "Ø Alter bei 1. Ehe",
    "Ø Kinderanzahl (nur Eltern)", "Fertilitätsrate (Kinder pro Person)",
    "Kindersterblichkeit (Anzahl)", "Kindersterblichkeit (Rate)",
    "Anzahl Eltern", "Gesamtkinder"
]


# ── Familiennamen-Häufigkeit ───────────────────────────────────────────────────

def analyze_surname_frequency(individuals, progress_cb=None, top_n=100):
    p = progress_cb or (lambda m, **kw: None)
    p("Familiennamen-Analyse …")
    counter = Counter()
    details: dict = {}

    for pid, pdata in individuals.items():
        name = pdata.get("NAME", "") or ""
        surname = (safe_extract_family_name(name) or "Unbekannt").strip()
        if len(surname) < 2: continue
        counter[surname] += 1
        d = details.setdefault(surname, {
            "persons": [], "birth_years": [],
            "genders": {"M": 0, "F": 0, "U": 0},
            "migrated": 0, "veterans": 0
        })
        d["persons"].append(pid)
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if by: d["birth_years"].append(by)
        sx = pdata.get("SEX", "U")
        d["genders"][sx if sx in ("M", "F") else "U"] += 1
        if "mig." in name.lower(): d["migrated"] += 1
        if pdata.get("VETERAN") or "✠" in name or "★" in name: d["veterans"] += 1

    rows = []
    for surname, cnt in counter.most_common(top_n):
        d = details[surname]
        bys = d["birth_years"]
        rows.append([
            surname, cnt,
            f"{min(bys)}-{max(bys)}" if bys else "unbekannt",
            max(bys) - min(bys) if bys else 0,
            int(sum(bys) / len(bys)) if bys else "",
            d["genders"]["M"], d["genders"]["F"],
            f"{d['genders']['M']/cnt*100:.1f}% / {d['genders']['F']/cnt*100:.1f}%",
            d["migrated"], d["veterans"],
            ", ".join((individuals[pid2].get("NAME", "")[:30] + "…")
                      for pid2 in d["persons"][:3] if pid2 in individuals),
        ])
    p(f"Nachnamen: {len(rows)} analysiert", tag="ok")
    return rows


SURNAME_HEADERS = [
    "Familienname", "Anzahl", "Jahres-Spanne", "Spannweite (Jahre)",
    "Ø Geburtsjahr", "Männer", "Frauen", "Geschlechterverteilung",
    "Migrierte", "Veteranen", "Beispielpersonen"
]


# ── Geburtsland-Verteilung ─────────────────────────────────────────────────────

def analyze_birth_country_distribution(individuals, location_data,
                                        progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Geburtsland-Verteilung …")
    country_stats: dict = {}
    unknown = 0

    for pid, pdata in individuals.items():
        bp = (pdata.get("BIRT") or {}).get("PLAC", "")
        if not bp: unknown += 1; continue
        country = extract_country_from_place(bp, location_data) or "Unbekannt"
        if country == "Unbekannt": unknown += 1
        sx = pdata.get("SEX", "U")
        if sx not in ("M", "F"): sx = "U"
        st = country_stats.setdefault(country, {
            "total": 0, "M": 0, "F": 0, "U": 0, "birth_years": [], "examples": []
        })
        st["total"] += 1
        st[sx] += 1
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        if by: st["birth_years"].append(by)
        if len(st["examples"]) < 3:
            name = pdata.get("NAME", "") or ""
            bys = f" (*{by})" if by else ""
            st["examples"].append(f"{name[:25]}…{bys}")

    total_with = sum(st["total"] for st in country_stats.values())
    rows = []
    for country, st in sorted(country_stats.items(),
                               key=lambda x: x[1]["total"], reverse=True):
        cnt = st["total"]
        bys = st["birth_years"]
        rows.append([
            country, cnt, f"{cnt/total_with*100:.1f}%" if total_with else "0%",
            st["M"], st["F"],
            f"{st['M']/cnt*100:.1f}% / {st['F']/cnt*100:.1f}%" if cnt else "",
            f"{min(bys)}-{max(bys)}" if bys else "unbekannt",
            max(bys) - min(bys) if bys else 0,
            int(sum(bys) / len(bys)) if bys else "",
            "", "",
            ", ".join(st["examples"][:3])
        ])
    if unknown > 0:
        rows.append(["Unbekannt (kein Geburtsort)", unknown,
                     f"{unknown/len(individuals)*100:.1f}%" if individuals else "0%",
                     "", "", "", "", "", "", "", "", "Keine Geburtsort-Daten"])
    p(f"Geburtsländer: {len(country_stats)} Länder", tag="ok")
    return rows


COUNTRY_HEADERS = [
    "Land", "Anzahl", "Anteil", "Männer", "Frauen",
    "Geschlechterverteilung", "Jahres-Spanne", "Spannweite (Jahre)",
    "Ø Geburtsjahr", "Ausgewandert (geschätzt)", "Auswanderungsrate",
    "Beispielpersonen"
]


# ── Umfassende Gesamtstatistik ─────────────────────────────────────────────────

def calculate_comprehensive_statistics(individuals, families, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Umfassende Gesamtstatistiken …")
    st = {
        "total_persons": len(individuals), "total_families": len(families),
        "gender": {"M": 0, "F": 0, "U": 0},
        "birth_years": [], "death_years": [], "lifespans": [],
        "with_birth": 0, "with_death": 0,
        "persons_with_children": 0, "total_children": 0,
        "children_per_family": [],
        "veterans": 0, "migrated": 0,
    }
    for pid, pdata in individuals.items():
        sx = pdata.get("SEX", "U")
        st["gender"][sx if sx in ("M", "F") else "U"] += 1
        by = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        dy = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        if by: st["with_birth"] += 1; st["birth_years"].append(by)
        if dy: st["with_death"] += 1; st["death_years"].append(dy)
        if by and dy and 0 < dy - by <= 120: st["lifespans"].append(dy - by)
        children = sum(len(families.get(fid, {}).get("CHIL", []))
                       for fid in pdata.get("FAMS", []))
        if children > 0:
            st["persons_with_children"] += 1
            st["total_children"] += children
        name = pdata.get("NAME", "") or ""
        if pdata.get("VETERAN") or "✠" in name or "★" in name: st["veterans"] += 1
        if "mig." in name.lower(): st["migrated"] += 1
    for fam in families.values():
        c = len(fam.get("CHIL", []))
        if c > 0: st["children_per_family"].append(c)

    r = []
    T = st["total_persons"]
    r += [["Gesamtanzahl Personen", T], ["Gesamtanzahl Familien", st["total_families"]], ["", ""]]
    for key, label in (("M", "Männer"), ("F", "Frauen"), ("U", "Geschlecht unbekannt")):
        r.append([label, st["gender"][key],
                  f"{st['gender'][key]/T*100:.1f}%" if T else ""])
    r.append(["", ""])
    if st["lifespans"]:
        r += [["Ø Lebenserwartung", f"{sum(st['lifespans'])/len(st['lifespans']):.1f} Jahre"],
               ["Min Lebensspanne", f"{min(st['lifespans'])} Jahre"],
               ["Max Lebensspanne", f"{max(st['lifespans'])} Jahre"]]
    r.append(["", ""])
    if st["birth_years"]:
        r += [["Frühestes Geburtsjahr", min(st["birth_years"])],
               ["Spätestes Geburtsjahr", max(st["birth_years"])],
               ["Ø Geburtsjahr", f"{sum(st['birth_years'])/len(st['birth_years']):.0f}"]]
    r.append(["", ""])
    if st["children_per_family"]:
        r += [["Ø Kinder pro Familie",
                f"{sum(st['children_per_family'])/len(st['children_per_family']):.1f}"],
               ["Max Kinder in einer Familie", max(st["children_per_family"])]]
    r += [["Personen mit Kindern", st["persons_with_children"],
            f"{st['persons_with_children']/T*100:.1f}%" if T else ""],
           ["Gesamtkinder", st["total_children"]], ["", ""]]
    r += [["Personen mit Geburtsdatum", st["with_birth"],
            f"{st['with_birth']/T*100:.1f}%" if T else ""],
           ["Personen mit Sterbedatum", st["with_death"],
            f"{st['with_death']/T*100:.1f}%" if T else ""], ["", ""]]
    r += [["Veteranen", st["veterans"],
            f"{st['veterans']/T*100:.1f}%" if T else ""],
           ["Markierte Auswanderer", st["migrated"],
            f"{st['migrated']/T*100:.1f}%" if T else ""]]
    p("Gesamtstatistiken berechnet", tag="ok")
    return r


STATS_HEADERS = ["Statistik", "Wert", "Prozent"]
