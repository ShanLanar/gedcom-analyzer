# -*- coding: utf-8 -*-
"""tasks/migration.py – Detaillierte Migrationsanalyse"""

import re
from collections import Counter, defaultdict
from lib.gedcom import safe_extract_year
from lib.helpers import (get_ancestor_paths, relationship_label,
                          safe_determine_migration_status,
                          extract_emigration_year_from_name,
                          extract_emigration_data_from_gedcom,
                          safe_extract_family_name)
from lib.places import (extract_country_from_place, format_place_for_display,
                         parse_detailed_place, get_last_three_components)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _relationship_to_root(root_id, pid, individuals, families,
                           root_paths=None, cache=None):
    if pid == root_id:
        return "root", "self"
    if root_paths is None:
        root_paths = get_ancestor_paths(root_id, individuals, families, cache)
    if pid in root_paths:
        sp = min(root_paths[pid], key=len)
        return relationship_label(len(sp) - 1, 0, True), "ancestor"
    if pid not in individuals:
        return "unrelated", "unknown"
    person_paths = get_ancestor_paths(pid, individuals, families, cache)
    if root_id in person_paths:
        sp = min(person_paths[root_id], key=len)
        return relationship_label(0, len(sp) - 1, False), "descendant"
    common = set(root_paths) & set(person_paths)
    if common:
        best = None
        for anc in common:
            r = min(len(p) - 1 for p in root_paths[anc])
            t = min(len(p) - 1 for p in person_paths[anc])
            s = max(r, t)
            if best is None or s < best[0]:
                best = (s, r, t)
        if best:
            return relationship_label(best[1], best[2]), "cousin"
    return "unrelated", "unknown"


LINEAGE_MAP = {
    "father": "väterlich", "mother": "mütterlich", "both": "beide",
    "väterlich": "väterlich", "mütterlich": "mütterlich", "beide": "beide"
}


# ── Detail-Analyse ─────────────────────────────────────────────────────────────

def analyze_detailed_migration_routes(individuals, families, root_id,
                                       location_data, root_related_ids=None,
                                       root_paths=None, cache=None,
                                       progress_cb=None):
    from tasks._runner import is_aborted, AbortedError
    p = progress_cb or (lambda m, **kw: None)
    p("Analysiere Migrationsrouten …")
    if root_related_ids is None:
        root_related_ids = set(individuals)
    if root_paths is None:
        root_paths = get_ancestor_paths(root_id, individuals, families, cache)

    migrations = []

    for idx, pid in enumerate(root_related_ids):
        if idx % 200 == 0 and is_aborted():
            raise AbortedError("Migrationsanalyse abgebrochen")
        if pid not in individuals:
            continue
        pdata = individuals[pid]
        name = pdata.get("NAME", "") or ""
        birth_place = (pdata.get("BIRT") or {}).get("PLAC") or ""
        death_place  = (pdata.get("DEAT") or {}).get("PLAC") or ""

        # Für die Migrationsanalyse zählt jeder Länderwechsel als Migration,
        # auch wenn die Person dort gefallen ist.
        mig_status = safe_determine_migration_status(
            pdata, name, location_data,
            battle_counts_as_migration=True)
        if not mig_status.startswith("ja"):
            continue

        bc_city, bc_dist, bc_prov, bc_country, _ = parse_detailed_place(
            birth_place, location_data)
        dc_city, dc_dist, dc_prov, dc_country, _ = parse_detailed_place(
            death_place, location_data)
        if not dc_country and "australia" in death_place.lower():
            dc_country = "Australien"

        dest = get_last_three_components(death_place, location_data)
        if dc_country:
            dest[2] = dc_country

        route = (f"{bc_country} → {', '.join(d for d in dest if d)}"
                 if bc_country and any(dest) else
                 f"{bc_country} → {dc_country}" if bc_country and dc_country
                 else "unbekannt")

        birth_year = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        death_year = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))

        emig_year, emig_place, emig_src = extract_emigration_data_from_gedcom(pdata)
        if not emig_year:
            emig_year = extract_emigration_year_from_name(name)
            if emig_year:
                emig_src = "NAME"
        if not emig_year:
            m = re.search(r'mig\.\s*(\d{4})', name, re.IGNORECASE)
            if m:
                emig_year, emig_src = int(m.group(1)), "NAME_MIG"

        age_at_mig = (emig_year - birth_year if emig_year and birth_year
                      else death_year - birth_year if death_year and birth_year
                      else None)

        # Familienzusammenhang
        fam_mig = spouse_mig = False
        children_mig = []
        for fam_id in pdata.get("FAMS", []):
            fam = families.get(fam_id, {})
            if not fam:
                continue
            sid = (fam.get("WIFE") if fam.get("HUSB") == pid else fam.get("HUSB"))
            if sid and sid in root_related_ids:
                sd = individuals.get(sid, {})
                if sd and safe_determine_migration_status(
                        sd, sd.get("NAME", ""), location_data).startswith("ja"):
                    spouse_mig = fam_mig = True
            for cid in fam.get("CHIL", []):
                if cid in root_related_ids:
                    cd = individuals.get(cid, {})
                    if cd and safe_determine_migration_status(
                            cd, cd.get("NAME", ""), location_data).startswith("ja"):
                        children_mig.append(cd.get("NAME", ""))
                        fam_mig = True

        rel, lin_raw = _relationship_to_root(root_id, pid, individuals, families,
                                              root_paths, cache=cache)
        lineage = LINEAGE_MAP.get(lin_raw, lin_raw)

        migrations.append([
            pid, name,
            format_place_for_display(birth_place),
            format_place_for_display(death_place),
            route, dest[0] or "", dest[1] or "", dest[2] or "",
            " | ".join(filter(None, [
                f"Bezirk: {dc_dist}" if dc_dist else "",
                f"Provinz: {dc_prov}" if dc_prov else "",
                f"Land: {dc_country}" if dc_country else ""])) or "unbekannt",
            mig_status,
            birth_year or "", death_year or "",
            age_at_mig or "",
            emig_year or "", emig_src or "",
            format_place_for_display(emig_place) if emig_place else "",
            "ja" if fam_mig else "nein",
            "ja" if spouse_mig else "nein",
            len(children_mig),
            ", ".join(children_mig[:2]) + ("…" if len(children_mig) > 2 else ""),
            rel, lineage,
        ])

    migrations.sort(key=lambda r: (r[13] if r[13] else r[10] or 0,
                                    r[10] or 0))
    p(f"Migrationsrouten: {len(migrations)} gefunden", tag="ok")
    return migrations


DETAIL_HEADERS = [
    "ID", "Name", "Geburtsort", "Sterbeort", "Migrationsroute",
    "Ziel Bezirk", "Ziel Provinz", "Ziel Land", "Ziel Details",
    "Migrationstyp", "Geburtsjahr", "Sterbejahr", "Alter bei Migration",
    "Emigrationsjahr", "Emigrationsquelle", "Emigrationsort",
    "Familienmigration", "Ehepartner migriert", "Kinder migriert", "Kinder Namen",
    "Verwandtschaft zu Root", "Linie"
]


# ── Compressed ────────────────────────────────────────────────────────────────

def _rel_distance(rel: str) -> int:
    """Numerische Distanz zur Root-Person aus einem deutschen
    Verwandtschafts-Label. Kleinere Werte = enger verwandt."""
    if not rel:
        return 999
    rl = rel.lower()
    if "selbst" in rl or "root" in rl:
        return 0
    # Reihenfolge: spezifischer vor allgemeiner (urgroß enthält "großeltern").
    if "urgroß" in rl and "eltern" in rl:
        # "3-fach Urgroßelternteil" → 3 great-Stufen + 2 Großeltern-Basis
        m = re.search(r'(\d+)-fach', rl)
        return 2 + (int(m.group(1)) if m else 1)
    if "großeltern" in rl:
        return 2
    if "eltern" in rl:
        return 1
    if "geschwister" in rl:
        return 1
    if "onkel" in rl or "tante" in rl:
        if "urgroß" in rl:
            m = re.search(r'(\d+)-fach', rl)
            return 3 + (int(m.group(1)) if m else 1)
        return 3 if "groß" in rl else 2
    if "cousin" in rl:
        m = re.search(r'cousin\s+(\d+)\.\s*grades', rl)
        g = int(m.group(1)) if m else 1
        rm = re.search(r'(\d+)x\s*entfernt', rl)
        rv = int(rm.group(1)) if rm else 0
        return g * 2 + rv + 3
    return 999


def create_compressed_migration_routes(migration_details, individuals, families,
                                        root_id, location_data, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Erstelle Migrationsrouten Compressed …")
    if not migration_details:
        return []

    groups = {}
    for row in migration_details:
        pid, name, route = row[0], row[1], row[4]
        linie, rel = row[21], row[20]
        dc = row[7]
        surname = safe_extract_family_name(name) or "Unbekannt"
        ln = ("väterlich" if linie.lower() in ["väterlich", "father", "paternal"]
              else "mütterlich" if linie.lower() in ["mütterlich", "mother", "maternal"]
              else "beide" if linie.lower() in ["beide", "both"]
              else linie or "unbekannt")
        key = (surname, ln, route, dc)
        g = groups.setdefault(key, {
            "surname": surname, "linie": ln, "migration_route": route,
            "destination_country": dc,
            "person_ids": [], "names": [], "relationships": [],
            "relationship_distances": [], "emigration_years": [],
            "example_person_id": pid, "example_name": name,
            "example_relationship": rel, "destination_details": row[8] if len(row) > 8 else ""
        })
        g["person_ids"].append(pid); g["names"].append(name)
        g["relationships"].append(rel)
        if len(row) > 13 and row[13]: g["emigration_years"].append(row[13])
        g["relationship_distances"].append(_rel_distance(rel))

    rows = []
    for gd in groups.values():
        cnt = len(gd["person_ids"])
        mi = min(range(len(gd["relationship_distances"])),
                 key=lambda i: gd["relationship_distances"][i])
        closest_rel = gd["relationships"][mi]
        ex_pid = gd["person_ids"][mi]
        ex_name = gd["names"][mi]

        years = [int(y) for y in gd["emigration_years"] if str(y).isdigit()]
        year_span = f"{min(years)}-{max(years)}" if years else "unbekannt"
        avg_year = int(sum(years) / len(years)) if years else ""

        rp = gd["migration_route"].split(" → ")
        route_simple = f"{rp[0]} → {rp[-1]}" if len(rp) >= 2 else gd["migration_route"]

        rows.append([
            gd["surname"], gd["linie"], gd["migration_route"], route_simple,
            rp[0] if len(rp) >= 2 else "unbekannt",
            rp[-1] if len(rp) >= 2 else gd.get("destination_country", ""),
            cnt,
            ", ".join(gd["person_ids"][:10]) + (f" … (+{cnt-10})" if cnt > 10 else ""),
            ", ".join(n[:20] + "…" for n in gd["names"][:3]) +
            (f" … (+{cnt-3})" if cnt > 3 else ""),
            closest_rel, ex_pid, ex_name[:40] + "…",
            year_span, avg_year,
            gd.get("destination_details", "")[:100]
        ])

    rows.sort(key=lambda x: (x[0], 0 if x[1] == "väterlich" else
                              1 if x[1] == "mütterlich" else 2, -x[6]))
    p(f"Compressed: {len(rows)} Gruppen", tag="ok")
    return rows


COMPRESSED_HEADERS = [
    "Familienname", "Linie", "Migrationsroute", "Vereinfachte Route",
    "Startland", "Zielland", "Anzahl Personen", "Personen-IDs",
    "Namen (Beispiele)", "Engste Verwandtschaft zu Root", "Beispiel-Person ID",
    "Beispiel-Person Name", "Emigrationsjahr-Spanne", "Durchschn. Emigrationsjahr",
    "Ziel Details"
]


# ── Migrationswellen ───────────────────────────────────────────────────────────

_HIST_CONTEXT = {
    (1845, 1855): "Deutsche Revolution 1848/49, Wirtschaftskrise",
    (1870, 1880): "Gründerkrise, Ende des Bürgerkriegs in USA",
    (1880, 1890): "Industrialisierung, Landflucht",
    (1900, 1914): "Vor dem 1. Weltkrieg, Wirtschaftsboom",
    (1919, 1933): "Weimarer Republik, Inflation, Weltwirtschaftskrise",
    (1933, 1939): "NS-Zeit, Verfolgung",
    (1945, 1955): "Nachkriegszeit, Wirtschaftswunder",
}


def detect_migration_waves(migration_results, individuals, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Analysiere Migrationswellen …")
    if not migration_results:
        return []

    emig_data = [
        {"year": int(r[13]), "person_id": r[0], "name": r[1],
         "source": r[14], "route": r[4]}
        for r in migration_results
        if r[13] and str(r[13]).isdigit() and 1600 <= int(r[13]) <= 2020
    ]
    if not emig_data:
        return []

    years_sorted = sorted(d["year"] for d in emig_data)
    waves, cur = [], [years_sorted[0]]
    for yr in years_sorted[1:]:
        if yr - cur[-1] <= 5:
            cur.append(yr)
        else:
            if len(cur) >= 3: waves.append(cur)
            cur = [yr]
    if len(cur) >= 3:
        waves.append(cur)

    results = []
    for wave_years in waves:
        ws, we = min(wave_years), max(wave_years)
        wpers = [d for d in emig_data if ws <= d["year"] <= we]
        routes = [d["route"] for d in wpers]
        dest_countries = []
        for rt in routes:
            if " → " in rt:
                dest_part = rt.split(" → ")[1]
                if ", " in dest_part:
                    dest_countries.append(dest_part.split(", ")[-1])
        country_ctr = Counter(dest_countries)
        ages = []
        males = females = 0
        for d in wpers:
            pd2 = individuals.get(d["person_id"], {})
            by = safe_extract_year((pd2.get("BIRT") or {}).get("DATE"))
            if by:
                age = d["year"] - by
                if 10 <= age <= 80:
                    ages.append(age)
            sx = pd2.get("SEX", "")
            if sx == "M": males += 1
            elif sx == "F": females += 1
        avg_age = sum(ages) / len(ages) if ages else 0
        wl = we - ws
        intensity = len(wpers) / wl if wl > 0 else len(wpers)
        hist = next((v for (s, e), v in _HIST_CONTEXT.items() if s <= ws <= e), "")
        results.append([
            f"Welle {len(results)+1}", ws, we, wl, len(wpers),
            round(intensity, 2),
            round(avg_age, 1) if ages else "",
            f"{min(ages)}-{max(ages)}" if ages else "",
            ", ".join(f"{k} ({v})" for k, v in country_ctr.most_common(3)),
            f"{males}♂ {females}♀",
            ", ".join(f"{d['name'][:20]}… ({d['year']})" for d in wpers[:4]),
            hist
        ])

    results.sort(key=lambda x: x[1])
    p(f"Migrationswellen: {len(results)} identifiziert", tag="ok")
    return results


WAVES_HEADERS = [
    "Welle", "Startjahr", "Endjahr", "Länge (Jahre)", "Anzahl Personen",
    "Intensität (Pers/Jahr)", "Ø Alter", "Altersspanne", "Top Ziele",
    "Geschlechter", "Beispielpersonen", "Historischer Kontext"
]


# ── Korrelation Migration-Demografie ──────────────────────────────────────────

def analyze_migration_correlations(individuals, families, migration_results,
                                    location_data, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Korrelationsanalyse Migration-Demografie …")
    rows = []
    DEVELOPED = ["USA", "Kanada", "Australien", "Großbritannien",
                 "Deutschland", "Frankreich"]

    for mig in migration_results:
        pid = mig[0]
        if pid not in individuals: continue
        pdata = individuals[pid]
        birth_year = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        death_year = safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))
        emig_year = mig[13]
        if not (birth_year and emig_year): continue

        age_mig = emig_year - birth_year
        life_after = death_year - emig_year if death_year and death_year > emig_year else None

        # Familienstatus
        fam_status = "unverheiratet"
        children_at_mig = 0
        for fam_id in pdata.get("FAMS", []):
            fam = families.get(fam_id, {})
            if fam:
                my = safe_extract_year(fam.get("MARR_DATE"))
                if my:
                    fam_status = ("verheiratet" if my < emig_year
                                  else "im Migrationsjahr geheiratet")
                    if my < emig_year:
                        for cid in fam.get("CHIL", []):
                            cd = individuals.get(cid, {})
                            if cd:
                                cby = safe_extract_year((cd.get("BIRT") or {}).get("DATE"))
                                if cby and cby < emig_year:
                                    children_at_mig += 1

        sx = pdata.get("SEX", "U")
        sex_disp = "Männlich" if sx == "M" else "Weiblich" if sx == "F" else "Unbekannt"

        ep = ("gering (vor 1800)" if birth_year < 1800
              else "grundlegend (19. Jh.)" if birth_year < 1900
              else "verbessert (frühes 20. Jh.)" if birth_year < 1950
              else "modern (nach 1950)")

        reason = ("frühe Erwachsenenphase" if age_mig < 25
                  else "beruflich/familiär" if age_mig < 40
                  else "späte Migration")

        bp = (pdata.get("BIRT") or {}).get("PLAC", "")
        dp = (pdata.get("DEAT") or {}).get("PLAC", "")
        bc = extract_country_from_place(bp, location_data)
        dc = extract_country_from_place(dp, location_data)
        if bc and dc:
            if bc in DEVELOPED and dc in DEVELOPED:   mob = "innerhalb entwickelter Länder"
            elif bc not in DEVELOPED and dc in DEVELOPED: mob = "Aufwärtsmobilität"
            elif bc in DEVELOPED and dc not in DEVELOPED: mob = "Abwärtsmobilität"
            else: mob = "zwischen Entwicklungsländern"
        else:
            mob = "unbekannt"

        success = ("" if not life_after
                   else "erfolgreich (lange Lebensspanne)" if life_after > 30
                   else "moderat" if life_after > 10
                   else "kurze Lebensspanne")

        rows.append([
            pid, mig[1], birth_year, emig_year, age_mig,
            life_after or "", fam_status, children_at_mig, sex_disp,
            ep, reason, mob, success, mig[4], mig[7]
        ])

    p(f"Korrelation: {len(rows)} analysiert", tag="ok")
    return rows


CORRELATION_HEADERS = [
    "ID", "Name", "Geburtsjahr", "Emigrationsjahr", "Alter bei Migration",
    "Lebensspanne nach Migration", "Familienstatus bei Migration",
    "Kinder bei Migration", "Geschlecht", "Bildungsniveau (geschätzt)",
    "Migrationsgrund (geschätzt)", "Soziale Mobilität", "Erfolgsmetrik",
    "Migrationsroute", "Zielland"
]
