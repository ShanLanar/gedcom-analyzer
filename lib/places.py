# -*- coding: utf-8 -*-
"""
lib/places.py
Ortsdaten laden, parsen und normalisieren.
Verwendet location_data.json (Länder, Bundesstaaten, Indikatoren).
"""

import os
import re
import json

_logger = None

def set_logger(lg):
    global _logger
    _logger = lg

def _log(level, msg):
    if _logger:
        getattr(_logger, level)(msg)


# ── Ortsdaten laden ────────────────────────────────────────────────────────────

def load_location_data(json_path: str) -> dict:
    """Lädt Ortsdaten aus JSON; erzeugt und speichert Standarddaten als Fallback."""
    if not json_path:
        _log("warning", "Kein Pfad für Ortsdaten angegeben – nutze Fallback")
        return _default_location_data()
    if not os.path.exists(json_path):
        _log("warning", f"Ortsdaten-JSON nicht gefunden: {json_path}")
        data = _default_location_data()
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return data
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        countries = len(data.get("countries", {}))
        states = sum(len(c.get("states", {})) for c in data.get("countries", {}).values())
        _log("info", f"Ortsdaten geladen: {countries} Länder, {states} Provinzen")
        return data
    except Exception as e:
        _log("error", f"Fehler beim Laden der Ortsdaten: {e}")
        return _default_location_data()


# ── Ortsparsing ────────────────────────────────────────────────────────────────

_HOF_KEYWORDS = ('hof', 'farm', 'anwesen', 'gut', 'haus', 'house', 'farmhouse')


def clean_place_part(part: str, extra_remove=()) -> str:
    """Entfernt Klammern, Hausnummern und Hof-/Farm-Begriffe aus einer
    Ortskomponente. Wird sowohl von parse_detailed_place als auch von
    tasks/endogamy.py genutzt — Single Source of Truth für die Cleanup-
    Regeln."""
    if not part:
        return ""
    p = re.sub(r'\([^)]*\)', '', part)
    p = re.sub(r'\[[^\]]*\]', '', p)
    p = re.sub(r'\b(nr\.?|no\.?|number)\s*\d+\b', '', p, flags=re.IGNORECASE)
    p = re.sub(r'\b\d+\b', '', p)
    for w in _HOF_KEYWORDS:
        p = re.sub(fr'\b{w}\b', '', p, flags=re.IGNORECASE)
    for w in extra_remove:
        p = re.sub(fr'\b{re.escape(w)}\b', '', p, flags=re.IGNORECASE)
    return ' '.join(p.split()).strip(' ,.-')


def parse_detailed_place(place_str, location_data, include_city=True,
                         include_zusatz=False) -> list:
    """
    Zerlegt einen GEDCOM-Ortsstring in [city, district, province, country, display].
    Entfernt Hof-/Farm-Namen, Nummern und Zusätze.
    Standardreihenfolge: [Ort, Bezirk, Provinz, Land]
    """
    if not place_str:
        return [None, None, None, None, ""]
    try:
        place = str(place_str).strip()
        if not location_data:
            return [None, None, None, None, place[:80]]

        generic   = location_data.get("generic_indicators", [])
        districts = location_data.get("district_indicators", [])
        zusatz_kw = location_data.get("zusatz_keywords", [])
        cities_kn = location_data.get("common_cities", [])
        countries_data = location_data.get("countries", {})

        # Zusätze entfernen
        if not include_zusatz:
            for z in zusatz_kw:
                place = re.sub(fr'\b{re.escape(z)}\b', '', place, flags=re.IGNORECASE)

        for w in generic:
            for variant in (w, w.upper(), w.capitalize()):
                place = place.replace(variant, "")
        place = place.strip(" ,;.-")
        if not place or len(place) < 3:
            return [None, None, None, None, place_str[:80]]

        parts = [p.strip() for p in place.split(",") if p.strip()] if "," in place else [place]
        cleaned = [c for c in (clean_place_part(part) for part in parts)
                   if c and len(c) >= 2]

        if not cleaned:
            return [None, None, None, None, place[:80]]

        remaining = cleaned[:]
        city = district = province = country = None

        # 1. Land (letztes Element)
        if remaining and countries_data:
            last = remaining[-1].lower()
            for cname, cinfo in countries_data.items():
                aliases = [a.lower() for a in cinfo.get("aliases", [])]
                if last in aliases or last == cname.lower():
                    country = cname
                    remaining.pop()
                    break
            if not country and "australia" in place.lower():
                country = "Australien"

        # 2. Provinz (vorletztes)
        if remaining and country and country in countries_data:
            last = remaining[-1].lower()
            for sname, saliases in countries_data[country].get("states", {}).items():
                if last in [a.lower() for a in saliases] or last == sname.lower():
                    province = sname
                    remaining.pop()
                    break

        # 3. Bezirk
        if remaining:
            last = remaining[-1].lower()
            for ind in districts:
                if ind in last:
                    district = remaining.pop()
                    break
            else:
                if (last and 3 < len(last) < 25
                        and last not in cities_kn
                        and not any(w in last for w in ["stadt", "city", "town", "dorf", "village"])):
                    district = remaining.pop()

        # 4. Stadt
        if remaining:
            city = ", ".join(remaining) if include_city else remaining[0]

        display_parts = []
        if include_zusatz and district:
            display_parts.append(district)
        if city:            display_parts.append(city)
        if district:        display_parts.append(district)
        if province:        display_parts.append(province)
        if country:         display_parts.append(country)

        return [city, district, province, country,
                ", ".join(display_parts) if display_parts else place[:80]]
    except Exception:
        return [None, None, None, None, place_str[:80] if place_str else ""]


def extract_country_from_place(place_str, location_data) -> str:
    if not place_str:
        return ""
    place_str = str(place_str)
    _, _, _, country, _ = parse_detailed_place(place_str, location_data)
    if not country and "australia" in place_str.lower():
        return "Australien"
    return country or ""


def format_place_for_display(place_str, max_parts=4) -> str:
    if not place_str:
        return ""
    try:
        parts = [p.strip() for p in str(place_str).split(",") if p.strip()]
        return ", ".join(parts[:max_parts])
    except Exception:
        return str(place_str)[:100]


def get_last_three_components(place_str, location_data) -> list:
    if not place_str:
        return ["", "", ""]
    _, district, province, country, _ = parse_detailed_place(
        place_str, location_data, include_city=False)
    return [district or "", province or "", country or ""]


def get_place_with_fallback(individuals, families, person_id, location_data) -> str:
    """
    Rückfallhierarchie:
    1. Geburtsort  2. Sterbeort  3. Sterbeort des Partners  4. Geburtsort ältestes Kind
    """
    if person_id not in individuals:
        return "unbekannt"
    pdata = individuals[person_id]
    bp = (pdata.get("BIRT") or {}).get("PLAC", "")
    if bp:
        return bp
    dp = (pdata.get("DEAT") or {}).get("PLAC", "")
    if dp:
        return dp
    for fam_id in pdata.get("FAMS", []):
        fam = families.get(fam_id, {})
        if fam:
            sid = fam.get("WIFE") if fam.get("HUSB") == person_id else fam.get("HUSB")
            if sid and sid in individuals:
                sp = (individuals[sid].get("DEAT") or {}).get("PLAC", "")
                if sp:
                    return sp
            for cid in fam.get("CHIL", []):
                if cid in individuals:
                    cp = (individuals[cid].get("BIRT") or {}).get("PLAC", "")
                    if cp:
                        return cp
    return "unbekannt"


# ── Standarddaten ──────────────────────────────────────────────────────────────

def _default_location_data() -> dict:
    """Minimale Ortsdaten als Fallback (Deutschland + USA + wichtige Länder)."""
    return {
        "countries": {
            "Deutschland": {
                "aliases": ["deutschland", "germany", "de", "ger", "bundesrepublik",
                            "germ.", "deutsch", "deutsches reich"],
                "states": {
                    "Bayern": ["bayern", "bavaria", "by"],
                    "Baden-Württemberg": ["baden-württemberg", "bw"],
                    "Nordrhein-Westfalen": ["nordrhein-westfalen", "nrw", "westfalen"],
                    "Niedersachsen": ["niedersachsen", "lower saxony", "ni"],
                    "Hessen": ["hessen", "hesse"],
                    "Sachsen": ["sachsen", "saxony"],
                    "Thüringen": ["thüringen", "thuringia"],
                    "Brandenburg": ["brandenburg"],
                    "Sachsen-Anhalt": ["sachsen-anhalt"],
                    "Mecklenburg-Vorpommern": ["mecklenburg-vorpommern", "mecklenburg"],
                    "Rheinland-Pfalz": ["rheinland-pfalz", "rheinland"],
                    "Saarland": ["saarland"],
                    "Berlin": ["berlin"],
                    "Hamburg": ["hamburg"],
                    "Bremen": ["bremen"],
                    "Schleswig-Holstein": ["schleswig-holstein"],
                }
            },
            "USA": {
                "aliases": ["usa", "vereinigte staaten", "united states", "us",
                            "u.s.a.", "u.s.", "america", "amerika"],
                "states": {
                    "Ohio": ["ohio", "oh"], "Texas": ["texas", "tx"],
                    "California": ["california", "ca", "calif"],
                    "New York": ["new york", "ny"], "Iowa": ["iowa", "ia"],
                    "Illinois": ["illinois", "il"], "Indiana": ["indiana", "in"],
                    "Pennsylvania": ["pennsylvania", "pa"],
                    "Minnesota": ["minnesota", "mn"], "Wisconsin": ["wisconsin", "wi"],
                }
            },
            "Australien": {
                "aliases": ["australien", "australia", "au"],
                "states": {
                    "New South Wales": ["new south wales", "nsw"],
                    "Victoria": ["victoria", "vic"],
                    "Queensland": ["queensland", "qld"],
                    "Western Australia": ["western australia", "wa"],
                }
            },
            "Niederlande": {"aliases": ["niederlande", "netherlands", "nl", "holland"], "states": {}},
            "Kanada":      {"aliases": ["kanada", "canada", "ca"], "states": {}},
            "Frankreich":  {"aliases": ["frankreich", "france", "fr"], "states": {}},
            "Österreich":  {"aliases": ["österreich", "austria", "at"], "states": {}},
            "Schweiz":     {"aliases": ["schweiz", "switzerland", "ch"], "states": {}},
            "Großbritannien": {"aliases": ["großbritannien", "great britain", "united kingdom",
                                           "uk", "england"], "states": {}},
            "Polen":       {"aliases": ["polen", "poland", "pl"], "states": {}},
            "Russland":    {"aliases": ["russland", "russia", "ru"], "states": {}},
        },
        "district_indicators":  ["county", "bezirk", "kreis", "district", "landkreis",
                                   "gemeinde", "stadtkreis", "municipality"],
        "province_indicators":  ["province", "region", "state", "prefecture", "department"],
        "zusatz_keywords":      ["near", "bei", "west of", "east of", "circa", "approx."],
        "generic_indicators":   ["unbekannt", "unknown", "n/a", "keine angabe", "?", "---"],
        "common_cities":        ["berlin", "hamburg", "münchen", "köln", "frankfurt",
                                  "hannover", "dresden", "stuttgart", "düsseldorf",
                                  "paris", "london", "new york", "sydney", "wien", "zürich"],
    }
