# -*- coding: utf-8 -*-
"""
tasks/osnabrueck.py
Osnabrück-Region Spezialanalyse – strikte hierarchische Ortszuordnung.
Gemeinden: Wallenhorst, Georgsmarienhütte, Hagen a.T.W., Osnabrück (Stadt),
           Ostercappeln, Belm, Bohmte, Hunteburg
"""

import re
from collections import Counter
from lib.gedcom import safe_extract_year
from lib.places import format_place_for_display
from lib.helpers import (safe_determine_migration_status,
                          extract_military_force_from_name)


# ── Gemeinde-Daten ─────────────────────────────────────────────────────────────

MUNICIPALITIES = {
    "wallenhorst": {
        "name": "Wallenhorst",
        "historical_names": ["wallenhorst", "hollage", "lechtingen", "rulle", "wulften"],
        "districts": [
            {"name": "Wallenhorst", "alt_names": ["wallenhorst"]},
            {"name": "Hollage",     "alt_names": ["hollage"]},
            {"name": "Lechtingen", "alt_names": ["lechtingen"]},
            {"name": "Rulle",      "alt_names": ["rulle"]},
            {"name": "Wulften",    "alt_names": ["wulften", "wülften"]},
        ],
    },
    "georgsmarienhuette": {
        "name": "Georgsmarienhütte",
        "historical_names": [
            "georgsmarienhuette", "georgsmarienhutte", "georgsmarienhütte",
            "gmhütte", "gmhuette", "gmh", "gm-huette",
            "oesede", "ösede", "kloster oesede", "harderberg", "holzhausen",
            "malbergen", "holsten", "mündrup", "mundrup", "muendrup",
        ],
        "districts": [
            {"name": "Oesede",          "alt_names": ["oesede", "ösede", "kloster oesede", "oe.", "oessede"]},
            {"name": "Harderberg",      "alt_names": ["harderberg"]},
            {"name": "Holzhausen",      "alt_names": ["holzhausen"]},
            {"name": "Malbergen",       "alt_names": ["malbergen"]},
            {"name": "Holsten-Mündrup", "alt_names": ["holsten", "mündrup", "mundrup", "muendrup"]},
        ],
    },
    "hagen": {
        "name": "Hagen am Teutoburger Wald",
        "historical_names": [
            "hagen am teutoburger wald", "hagen a.t.w.", "hagen atw", "hagen",
            "altenhagen", "gellenbeck", "natrup-hagen", "natrup hagen", "natrup",
            "sudenfeld", "beckerode", "mersch", "berg", "plessen", "schierloh",
            "stapel", "grosse heide", "große heide", "grosseheide",
        ],
        "districts": [
            {"name": "Hagen",       "alt_names": ["hagen", "hagen a.t.w.", "hagen atw"]},
            {"name": "Altenhagen",  "alt_names": ["altenhagen"]},
            {"name": "Gellenbeck",  "alt_names": ["gellenbeck"]},
            {"name": "Natrup",      "alt_names": ["natrup", "natrup-hagen", "natrup hagen"]},
            {"name": "Sudenfeld",   "alt_names": ["sudenfeld"]},
            {"name": "Beckerode",   "alt_names": ["beckerode"]},
            {"name": "Mersch",      "alt_names": ["mersch"]},
            {"name": "Berg",        "alt_names": ["berg"]},
            {"name": "Plessen",     "alt_names": ["plessen"]},
            {"name": "Schierloh",   "alt_names": ["schierloh"]},
            {"name": "Stapel",      "alt_names": ["stapel"]},
            {"name": "Große Heide", "alt_names": ["grosse heide", "große heide", "grosseheide"]},
        ],
    },
    "osnabrueck": {
        "name": "Osnabrück",
        "historical_names": [
            "osnabrueck", "osnabrück", "osnabruck",
            "stadt osnabrueck", "stadt osnabrück",
            "kreisfreie stadt osnabrueck", "kreisfreie stadt osnabrück",
        ],
        "districts": [
            {"name": "Innenstadt", "alt_names": ["innenstadt", "zentrum", "stadtmitte"]},
            {"name": "Westerberg", "alt_names": ["westerberg"]},
            {"name": "Wüste",      "alt_names": ["wüste", "wueste"]},
            {"name": "Haste",      "alt_names": ["haste"]},
            {"name": "Sutthausen", "alt_names": ["sutthausen"]},
        ],
    },
    "ostercappeln": {
        "name": "Ostercappeln",
        "historical_names": [
            "ostercappeln", "oster-cappeln", "oster cappeln",
            "nordhausen", "cappeln", "haaren", "felsen",
            "jöstinghausen", "joestinghausen",
        ],
        "districts": [
            {"name": "Ostercappeln", "alt_names": ["ostercappeln", "oster-cappeln"]},
            {"name": "Schwagstorf",  "alt_names": ["schwagstorf"]},
            {"name": "Venne",        "alt_names": ["venne"]},
            {"name": "Hitzhausen",   "alt_names": ["hitzhausen"]},
            {"name": "Haaren",       "alt_names": ["haaren"]},
            {"name": "Broxten",      "alt_names": ["broxten"]},
            {"name": "Nordhausen",   "alt_names": ["nordhausen"]},
            {"name": "Cappeln",      "alt_names": ["cappeln"]},
            {"name": "Felsen",       "alt_names": ["felsen"]},
        ],
    },
    "belm": {
        "name": "Belm",
        "historical_names": ["belm"],
        "districts": [
            {"name": "Belm",  "alt_names": ["belm"]},
            {"name": "Vehrte","alt_names": ["vehrte"]},
            {"name": "Icker", "alt_names": ["icker"]},
            {"name": "Powe",  "alt_names": ["powe"]},
        ],
    },
    "bohmte": {
        "name": "Bohmte",
        "historical_names": ["bohmte", "böhmte", "hunteburg", "stirpe", "oelingen",
                              "herringhausen", "büscherheide", "borgloh", "brockum"],
        "districts": [
            {"name": "Bohmte",          "alt_names": ["bohmte", "böhmte"]},
            {"name": "Hunteburg",       "alt_names": ["hunteburg"]},
            {"name": "Stirpe-Oelingen", "alt_names": ["stirpe", "oelingen"]},
            {"name": "Herringhausen",   "alt_names": ["herringhausen"]},
            {"name": "Büscherheide",    "alt_names": ["büscherheide", "buescherheide"]},
            {"name": "Borgloh",         "alt_names": ["borgloh"]},
            {"name": "Brockum",         "alt_names": ["brockum"]},
        ],
    },
}

_EXCLUDED_COUNTRIES = [
    "usa", "united states", "america", "canada", "australia",
    "england", "ireland", "scotland", "ohio", "texas", "california",
    "iowa", "illinois", "indiana", "kentucky", "dakota", "maine", "minnesota"
]
_GERMANY_INDICATORS = ["deutschland", "germany", "niedersachsen", "lower saxony"]


# ── Ortsnormalisierung ─────────────────────────────────────────────────────────

def _normalize(place_str: str) -> str:
    place = str(place_str).lower().strip()
    place = " ".join(place.split())
    for wrong, correct in [("lower saxony", "niedersachsen"), ("germany", "deutschland"),
                             ("ü", "ue"), ("ö", "oe"), ("ä", "ae"), ("ß", "ss")]:
        place = place.replace(wrong, correct)
    return place


def _parse_hierarchy(place_str: str) -> dict | None:
    norm = _normalize(place_str)
    parts = [p.strip() for p in norm.split(",") if p.strip()]
    if not parts: return None
    n = len(parts)
    h = {"parts": parts, "detail": None, "city": None,
         "district": None, "county": None, "state": None, "country": None}
    if n == 1:   h["city"] = parts[0]
    elif n == 2: h["city"] = parts[0]; h["country"] = parts[1]
    elif n == 3: h["city"] = parts[0]; h["county"] = parts[1]; h["country"] = parts[2]
    elif n == 4: h["city"] = parts[0]; h["district"] = parts[1]; h["state"] = parts[2]; h["country"] = parts[3]
    else:        h["detail"] = parts[0]; h["city"] = parts[1]; h["district"] = parts[2]; h["state"] = parts[3]; h["country"] = parts[4]
    return h


def _is_osnabrueck_county(h: dict) -> bool:
    if not h: return False
    for field in ("county", "district"):
        v = h.get(field, "")
        if v and "osnabr" in v.lower(): return True
    return False


def _match_municipality(h: dict, mdata: dict) -> bool:
    if not h: return False
    for field in ("city", "district", "detail"):
        v = h.get(field, "")
        if v and v.lower() in mdata["historical_names"]:
            return True
    return False


def _match_district(h: dict, mdata: dict) -> str:
    if not h: return mdata["name"]
    for field in ("city", "detail"):
        v = h.get(field, "")
        if not v: continue
        for d in mdata["districts"]:
            if v.lower() in d["alt_names"]:
                return d["name"]
    return mdata["name"]


# ── Analyse ────────────────────────────────────────────────────────────────────

def analyze_persons_by_municipality(individuals, families, location_data,
                                     progress_cb=None) -> dict:
    p = progress_cb or (lambda m, **kw: None)
    p("Osnabrück-Region Analyse (strikte Hierarchie) …")

    results = {k: [] for k in MUNICIPALITIES}
    total = matched = rej_country = rej_county = 0

    for pid, pdata in individuals.items():
        total += 1
        bp = (pdata.get("BIRT") or {}).get("PLAC", "")
        if not bp: continue

        bpl = bp.lower()
        if any(ex in bpl for ex in _EXCLUDED_COUNTRIES):
            if not any(de in bpl for de in _GERMANY_INDICATORS):
                rej_country += 1; continue

        h = _parse_hierarchy(bp)
        if not h: continue
        if not _is_osnabrueck_county(h):
            rej_county += 1; continue

        for mkey, mdata in MUNICIPALITIES.items():
            if _match_municipality(h, mdata):
                ortsteil = _match_district(h, mdata)
                results[mkey].append(_build_person_entry(
                    pid, pdata, bp, ortsteil, individuals, families,
                    location_data))
                matched += 1
                break

    p(f"Osnabrück: {matched} von {total} zugeordnet "
      f"(Ausschluss: {rej_country} falsches Land, {rej_county} kein OS-Kreis)",
      tag="ok")
    return results


def _build_person_entry(pid, pdata, birth_place, ortsteil,
                         individuals, families, location_data) -> dict:
    name = pdata.get("NAME", "") or ""
    sx   = pdata.get("SEX", "")
    bd   = (pdata.get("BIRT") or {}).get("DATE", "")
    by   = safe_extract_year(bd)
    dd   = (pdata.get("DEAT") or {}).get("DATE", "")
    dy   = safe_extract_year(dd)
    dp   = (pdata.get("DEAT") or {}).get("PLAC", "")
    age  = dy - by if by and dy else None

    father = mother = ""
    for fid in pdata.get("FAMC", []):
        fam = families.get(fid, {})
        if fam:
            fi = fam.get("HUSB")
            mi = fam.get("WIFE")
            if fi and fi in individuals: father = individuals[fi].get("NAME", "") or ""
            if mi and mi in individuals: mother = individuals[mi].get("NAME", "") or ""
            break

    spouses = []; children_count = 0
    for fid in pdata.get("FAMS", []):
        fam = families.get(fid, {})
        if fam:
            children_count += len(fam.get("CHIL", []))
            sid = fam.get("WIFE") if fam.get("HUSB") == pid else fam.get("HUSB")
            if sid and sid in individuals:
                sn = individuals[sid].get("NAME", "") or ""
                if sn: spouses.append(sn)

    mig = safe_determine_migration_status(pdata, name, location_data)
    return {
        "person_id": pid, "name": name, "sex": sx,
        "birth_date": bd, "birth_year": by or "", "birth_place": birth_place,
        "ortsteil": ortsteil,
        "death_date": dd, "death_year": dy or "", "death_place": dp,
        "age": age or "",
        "father": father, "mother": mother,
        "spouses": ", ".join(spouses[:3]),
        "children_count": children_count,
        "migrated": mig if mig.startswith("ja") else "",
        "military_force": extract_military_force_from_name(name),
        "died_in_battle": "ja" if pdata.get("DIED_IN_BATTLE") else "nein",
        "veteran": "ja" if pdata.get("VETERAN") else "nein",
        "relationship": "unbekannt",
    }


# ── Zusammenfassung ────────────────────────────────────────────────────────────

def create_municipality_summary(analysis_results: dict) -> dict:
    summaries = {}
    for mkey, mdata in MUNICIPALITIES.items():
        persons = analysis_results.get(mkey, [])
        if not persons:
            summaries[mkey] = {
                "municipality_name": mdata["name"], "person_count": 0,
                "male_count": 0, "female_count": 0, "unknown_sex": 0,
                "birth_year_range": "keine Daten", "earliest_birth": None,
                "latest_birth": None, "avg_age": None,
                "ortsteil_distribution": {}, "top_ortsteil": ("keine", 0),
                "migration_count": 0, "migration_rate": 0,
                "veteran_count": 0, "veteran_rate": 0, "fallen_count": 0,
                "avg_children": 0, "has_data": False,
            }
            continue

        bys  = [p["birth_year"] for p in persons if p["birth_year"]]
        ages = [p["age"] for p in persons if p["age"]]
        m_cnt = sum(1 for p in persons if p["sex"] == "M")
        f_cnt = sum(1 for p in persons if p["sex"] == "F")
        ot_ctr = Counter(p["ortsteil"] for p in persons)
        mig   = sum(1 for p in persons if p["migrated"] and "ja" in p["migrated"].lower())
        vet   = sum(1 for p in persons if p["veteran"] == "ja")
        fallen = sum(1 for p in persons if p["died_in_battle"] == "ja")
        avg_ch = sum(p["children_count"] for p in persons) / len(persons)

        summaries[mkey] = {
            "municipality_name": mdata["name"],
            "person_count": len(persons),
            "male_count": m_cnt, "female_count": f_cnt,
            "unknown_sex": len(persons) - m_cnt - f_cnt,
            "birth_year_range": f"{min(bys)}-{max(bys)}" if bys else "Unbekannt",
            "earliest_birth": min(bys) if bys else None,
            "latest_birth":  max(bys) if bys else None,
            "avg_age": sum(ages) / len(ages) if ages else None,
            "ortsteil_distribution": dict(ot_ctr.most_common()),
            "top_ortsteil": ot_ctr.most_common(1)[0] if ot_ctr else ("Unbekannt", 0),
            "migration_count": mig,
            "migration_rate": mig / len(persons) * 100 if persons else 0,
            "veteran_count": vet,
            "veteran_rate": vet / len(persons) * 100 if persons else 0,
            "fallen_count": fallen,
            "avg_children": round(avg_ch, 1),
            "has_data": True,
        }
    return summaries


# ── Übersicht-Zeilen für Excel-Integration ────────────────────────────────────

def build_overview_rows(summaries: dict) -> list:
    rows = []
    for summary in sorted(summaries.values(),
                           key=lambda x: x["person_count"], reverse=True):
        rows.append([
            summary["municipality_name"],
            summary["person_count"],
            summary["male_count"],
            summary["female_count"],
            f"{summary['avg_age']:.1f}" if summary.get("avg_age") else "N/A",
            summary["birth_year_range"],
            f"{summary.get('migration_rate', 0):.1f}%",
            f"{summary.get('veteran_rate', 0):.1f}%",
            f"{summary['top_ortsteil'][0]} ({summary['top_ortsteil'][1]})"
            if summary["top_ortsteil"][1] > 0 else "keine",
            summary.get("fallen_count", 0),
        ])
    return rows


def build_detail_rows(persons: list) -> list:
    rows = []
    for person in persons[:5000]:
        rows.append([
            person.get("person_id", ""),
            str(person.get("name", ""))[:50],
            person.get("sex", ""),
            person.get("birth_date", ""),
            person.get("birth_year", ""),
            str(person.get("birth_place", ""))[:100],
            person.get("ortsteil", ""),
            person.get("death_date", ""),
            person.get("death_year", ""),
            str(person.get("death_place", ""))[:100],
            person.get("age", ""),
            str(person.get("father", ""))[:50],
            str(person.get("mother", ""))[:50],
            str(person.get("spouses", ""))[:100],
            person.get("children_count", 0),
            person.get("migrated", ""),
            person.get("military_force", ""),
            person.get("veteran", ""),
            person.get("died_in_battle", ""),
        ])
    return rows


OVERVIEW_HEADERS = [
    "Gemeinde", "Personen", "Männer", "Frauen", "Ø Alter",
    "Geburtsjahr-Spanne", "Migration %", "Veteranen %",
    "Top Ortsteil", "Gefallene"
]
DETAIL_HEADERS = [
    "Person ID", "Name", "Geschlecht", "Geburtsdatum", "Geburtsjahr",
    "Geburtsort", "Ortsteil", "Sterbedatum", "Sterbejahr", "Sterbeort",
    "Alter", "Vater", "Mutter", "Ehepartner", "Kinderzahl",
    "Migriert", "Militär", "Veteran", "Gefallen"
]
