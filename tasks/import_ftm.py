# -*- coding: utf-8 -*-
"""
tasks/import_ftm.py
Family Tree Maker (FTM) 2014+ direkter SQLite-Import.

FTM 2014+ speichert Stammbäume als SQLite-Datenbank (.ftm).
Erzeugt dieselbe (individuals, families)-Struktur wie lib/gedcom.py,
sodass alle nachgelagerten Analysen ohne Änderung weiterarbeiten.
"""

import os
import sqlite3

from lib.gedcom import safe_parse_gedcom_date

_logger = None


def set_logger(lg):
    global _logger
    _logger = lg


def _log(level, msg):
    if _logger:
        getattr(_logger, level)(msg)
    else:
        print(f"[{level.upper()}] {msg}")


# ── Schema-Discovery ───────────────────────────────────────────────────────────

class _Schema:
    """Entdeckt und cached Tabellen-/Spaltennamen einer FTM-SQLite-Datenbank."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        # lowercase key → original name
        self.tables: dict[str, str] = {r[0].lower(): r[0] for r in cur.fetchall()}
        self._col_cache: dict[str, dict[str, str]] = {}

    def cols(self, table_key: str) -> dict[str, str]:
        """Spaltennamen für Tabelle (lowercase → original)."""
        key = table_key.lower()
        if key not in self._col_cache:
            real = self.tables.get(key, table_key)
            cur = self.conn.cursor()
            cur.execute(f'PRAGMA table_info("{real}")')
            self._col_cache[key] = {r[1].lower(): r[1] for r in cur.fetchall()}
        return self._col_cache.get(key, {})

    def find_table(self, *candidates: str) -> str | None:
        """Gibt den ersten vorhandenen Tabellennamen zurück."""
        for c in candidates:
            if c.lower() in self.tables:
                return self.tables[c.lower()]
        return None

    def find_col(self, table_key: str, *candidates: str) -> str | None:
        """Gibt den ersten vorhandenen Spaltennamen zurück."""
        cols = self.cols(table_key.lower())
        for c in candidates:
            if c.lower() in cols:
                return cols[c.lower()]
        return None

    def fetch(self, sql: str, params=()):
        """Führt SQL aus und gibt Zeilen als Liste von dicts (lowercase keys) zurück."""
        cur = self.conn.cursor()
        cur.execute(sql, params)
        if cur.description is None:
            return []
        col_names = [d[0].lower() for d in cur.description]
        return [dict(zip(col_names, row)) for row in cur.fetchall()]


# ── Konstanten ─────────────────────────────────────────────────────────────────

# GEDCOM-Tags, die direkt in der FactType-Tabelle stehen können
_GEDCOM_TAGS = {"BIRT", "DEAT", "MARR", "EMIG", "IMMI", "CHR", "BAPM",
                "RESI", "EVEN", "OCCU", "EDUC", "NATU"}

# Mapping von FTM-Anzeigenamen (EN + DE) auf GEDCOM-Tags
_TAG_MAP: dict[str, str] = {
    "birth": "BIRT",        "death": "DEAT",        "marriage": "MARR",
    "emigration": "EMIG",   "immigration": "IMMI",
    "christening": "CHR",   "baptism": "BAPM",
    "geburt": "BIRT",       "tod": "DEAT",          "taufe": "CHR",
    "heirat": "MARR",       "trauung": "MARR",      "eheschließung": "MARR",
    "auswanderung": "EMIG", "einwanderung": "IMMI",
}


# ── Interne Hilfsfunktionen ────────────────────────────────────────────────────

def _indi_id(num) -> str:
    return f"@I{num}@"


def _fam_id(num) -> str:
    return f"@F{num}@"


def _new_indi() -> dict:
    return {
        "NAME": None, "SEX": None,
        "FAMC": [], "FAMS": [],
        "BIRT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "DEAT": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "BIRTH_PLACE": None,
        "MIGRATED": False, "DIED_IN_BATTLE": False, "VETERAN": False,
        "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False,
    }


def _new_fam() -> dict:
    return {
        "HUSB": None, "WIFE": None, "CHIL": [],
        "MARR_DATE": None, "MARR_PLACE": None,
    }


def _build_tag_map(schema: _Schema) -> dict:
    """Baut ein FactTypeID → GEDCOM-Tag-Mapping aus der FactType-Tabelle."""
    ftype_tbl = schema.find_table("FactType", "facttype", "eventtype", "eventtypes",
                                  "factcategory")
    if not ftype_tbl:
        return {}
    ftkey = ftype_tbl.lower()
    fid_col   = schema.find_col(ftkey, "facttypeid", "id", "typeid", "eventid")
    tag_col   = schema.find_col(ftkey, "tag", "abbreviation", "gedcomtag", "gedtag")
    name_col  = schema.find_col(ftkey, "name", "typename", "label", "displayname")
    if not fid_col:
        return {}
    result: dict = {}
    for row in schema.fetch(f'SELECT * FROM "{ftype_tbl}"'):
        fid = row.get(fid_col.lower())
        if fid is None:
            continue
        tag = ""
        if tag_col:
            tag = str(row.get(tag_col.lower(), "") or "").strip().upper()
        if tag not in _GEDCOM_TAGS and name_col:
            name = str(row.get(name_col.lower(), "") or "").strip().lower()
            tag = _TAG_MAP.get(name, "")
        if tag:
            result[fid] = tag
    return result


def _build_place_map(schema: _Schema) -> dict:
    """Baut ein PlaceID → Ortsname-Mapping."""
    place_tbl = schema.find_table("Place", "places", "placerecord",
                                  "placeinfo", "locality")
    if not place_tbl:
        return {}
    ptkey = place_tbl.lower()
    pid_col   = schema.find_col(ptkey, "placeid", "placerecordid", "id")
    pname_col = schema.find_col(ptkey, "name", "placename", "fullname",
                                "plac", "place", "location")
    if not pid_col or not pname_col:
        return {}
    result: dict = {}
    for row in schema.fetch(f'SELECT * FROM "{place_tbl}"'):
        pid  = row.get(pid_col.lower())
        name = str(row.get(pname_col.lower(), "") or "").strip()
        if pid is not None and name:
            result[pid] = name
    return result


# ── Lade-Funktionen ────────────────────────────────────────────────────────────

def _load_individuals(schema: _Schema, p) -> dict:
    tbl = schema.find_table("Individual", "person", "individuals", "persons")
    if not tbl:
        raise ValueError("Tabelle 'Individual' nicht gefunden – keine FTM-Datenbank?")
    tkey    = tbl.lower()
    id_col  = schema.find_col(tkey, "individualid", "personid", "id", "recordid")
    sex_col = schema.find_col(tkey, "sex", "gender", "geschlecht")
    if not id_col:
        raise ValueError(f"Keine ID-Spalte in Tabelle '{tbl}'")
    individuals: dict = {}
    for row in schema.fetch(f'SELECT * FROM "{tbl}"'):
        num = row.get(id_col.lower())
        if num is None:
            continue
        indi = _new_indi()
        if sex_col:
            raw = str(row.get(sex_col.lower(), "") or "").strip().upper()
            if raw in ("M", "MALE", "1"):
                indi["SEX"] = "M"
            elif raw in ("F", "FEMALE", "2"):
                indi["SEX"] = "F"
        individuals[_indi_id(num)] = indi
    p(f"  {len(individuals):,} Personen aus '{tbl}'")
    return individuals


def _load_names(schema: _Schema, individuals: dict, p) -> None:
    tbl = schema.find_table("PersonName", "Name", "names", "personnames",
                             "individualname", "individualnames")
    if not tbl:
        _log("warning", "Tabelle 'PersonName' nicht gefunden – keine Namen")
        return
    tkey        = tbl.lower()
    id_col      = schema.find_col(tkey, "individualid", "personid", "ownerid", "id")
    given_col   = schema.find_col(tkey, "given", "givenname", "firstname",
                                   "vorname", "rufname")
    surname_col = schema.find_col(tkey, "surname", "familyname", "lastname",
                                   "nachname", "familienname")
    prefix_col  = schema.find_col(tkey, "prefix", "title", "namenszusatz")
    suffix_col  = schema.find_col(tkey, "suffix", "namenssuffix")
    type_col    = schema.find_col(tkey, "nametype", "type")
    order_col   = schema.find_col(tkey, "nameorder", "sortorder", "order", "namerank")
    if not id_col:
        _log("warning", f"Keine IndividualID-Spalte in '{tbl}'")
        return

    # Primärnamen pro Person: bevorzuge NameType=0 oder NameOrder=1
    primary: dict[str, dict] = {}
    for row in schema.fetch(f'SELECT * FROM "{tbl}"'):
        raw_id = row.get(id_col.lower())
        if raw_id is None:
            continue
        iid = _indi_id(raw_id)
        if iid not in individuals:
            continue
        name_type  = int(row.get(type_col.lower(),  0) or 0) if type_col  else 0
        name_order = int(row.get(order_col.lower(), 1) or 1) if order_col else 1
        if iid not in primary or name_type == 0 or name_order == 1:
            primary[iid] = row

    for iid, row in primary.items():
        def _s(col):
            if col:
                return str(row.get(col.lower(), "") or "").strip()
            return ""
        given   = _s(given_col)
        surname = _s(surname_col)
        prefix  = _s(prefix_col)
        suffix  = _s(suffix_col)

        # GEDCOM-Namensformat: "Prefix Vorname /Nachname/ Suffix"
        parts = []
        if prefix:  parts.append(prefix)
        if given:   parts.append(given)
        if surname: parts.append(f"/{surname}/")
        if suffix:  parts.append(suffix)
        name_str = " ".join(parts) if parts else None

        indi = individuals[iid]
        indi["NAME"] = name_str
        if name_str:
            if "✠" in name_str:
                indi["GERMAN_SOLDIER"] = indi["VETERAN"] = True
            if "★" in name_str:
                indi["OTHER_SOLDIER"] = indi["VETERAN"] = True
            if "⚔" in name_str:
                indi["DIED_IN_BATTLE"] = True
            if "‡" in name_str:
                indi["LINE_ENDS"] = True
            if "mig." in name_str.lower():
                indi["MIGRATED"] = True

    p(f"  {len(primary):,} Namen zugeordnet")


def _load_facts(schema: _Schema, individuals: dict, families: dict,
                tag_map: dict, places: dict, p) -> None:
    """Lädt Ereignisse (Geburt, Tod, Heirat, Migration) aus der Fact-Tabelle."""
    fact_tbl = schema.find_table("Fact", "facts", "event", "events",
                                  "individualfact", "individualfacts")
    if not fact_tbl:
        _log("warning", "Keine Fact-Tabelle – Ereignisdaten fehlen")
        return
    ftkey       = fact_tbl.lower()
    owner_col   = schema.find_col(ftkey, "ownerid", "individualid", "personid")
    otype_col   = schema.find_col(ftkey, "ownertype", "recordtype", "ownerrecordtype")
    ftype_col   = schema.find_col(ftkey, "facttypeid", "eventtype", "type",
                                   "facttype", "typeid")
    date_col    = schema.find_col(ftkey, "date1", "date", "datum",
                                   "eventdate", "factdate")
    place_id_col = schema.find_col(ftkey, "place1id", "placeid", "place_id",
                                    "placerecordid")
    place_col   = schema.find_col(ftkey, "place1", "place", "plac", "ort")
    if not owner_col or not ftype_col:
        _log("warning", "Fact-Tabelle ohne Owner- oder TypeID-Spalte")
        return

    indi_count = fam_count = 0
    for row in schema.fetch(f'SELECT * FROM "{fact_tbl}"'):
        raw_id = row.get(owner_col.lower())
        if raw_id is None:
            continue

        # Besitzertyp bestimmen: 0/None = Individual, 1 = Familie
        owner_type = 0
        if otype_col:
            ot = row.get(otype_col.lower())
            if ot in (1, "1", "family", "FAM"):
                owner_type = 1

        # GEDCOM-Tag ermitteln
        raw_type = row.get(ftype_col.lower())
        tag = tag_map.get(raw_type, "")
        if not tag and raw_type:
            candidate = str(raw_type).strip().upper()
            if candidate in _GEDCOM_TAGS:
                tag = candidate
            else:
                tag = _TAG_MAP.get(candidate.lower(), "")
        if not tag:
            continue

        # Datum + Ort
        date_str = ""
        if date_col:
            date_str = str(row.get(date_col.lower(), "") or "").strip()
        parsed = safe_parse_gedcom_date(date_str) if date_str else {
            "DATE": None, "YEAR": None, "DATE_QUAL": "unknown"
        }
        place_name = ""
        if place_id_col:
            pid = row.get(place_id_col.lower())
            if pid is not None:
                place_name = places.get(pid, "")
        if not place_name and place_col:
            place_name = str(row.get(place_col.lower(), "") or "").strip()

        if owner_type == 1:
            # Familien-Event
            if tag != "MARR":
                continue
            fid = _fam_id(raw_id)
            fam = families.get(fid)
            if fam is None:
                continue
            if fam["MARR_DATE"] is None and parsed.get("DATE"):
                fam["MARR_DATE"] = parsed["DATE"]
            if fam["MARR_PLACE"] is None and place_name:
                fam["MARR_PLACE"] = place_name
            fam_count += 1
        else:
            # Individual-Event
            if tag not in ("BIRT", "DEAT", "EMIG", "IMMI"):
                continue
            iid = _indi_id(raw_id)
            indi = individuals.get(iid)
            if indi is None:
                # Könnte otype_col fehlen → als Individual behandeln, aber ID prüfen
                continue
            ev = indi[tag]
            if ev["DATE"] is None:
                ev["DATE"]      = parsed.get("DATE")
                ev["YEAR"]      = parsed.get("YEAR")
                ev["DATE_QUAL"] = parsed.get("DATE_QUAL")
            if ev["PLAC"] is None and place_name:
                ev["PLAC"] = place_name
                if tag == "BIRT":
                    indi["BIRTH_PLACE"] = place_name
            indi_count += 1

    p(f"  {indi_count:,} Personen-Ereignisse, {fam_count:,} Familien-Ereignisse geladen")


def _load_families(schema: _Schema, individuals: dict, p) -> dict:
    fam_tbl   = schema.find_table("Family", "families")
    child_tbl = schema.find_table("FamilyChild", "familychildren", "familychild",
                                  "childlink", "childlinks", "familymember")
    if not fam_tbl:
        raise ValueError("Tabelle 'Family' nicht gefunden")
    ftkey    = fam_tbl.lower()
    fid_col  = schema.find_col(ftkey, "familyid", "id", "recordid")
    husb_col = schema.find_col(ftkey, "husbandid", "fatherid", "father",
                                "husband", "spouseid1")
    wife_col = schema.find_col(ftkey, "wifeid", "motherid", "mother",
                                "wife", "spouseid2")
    if not fid_col:
        raise ValueError(f"Keine FamilyID-Spalte in '{fam_tbl}'")

    families: dict = {}
    for row in schema.fetch(f'SELECT * FROM "{fam_tbl}"'):
        num = row.get(fid_col.lower())
        if num is None:
            continue
        fam = _new_fam()
        if husb_col:
            hid = row.get(husb_col.lower())
            if hid:
                fam["HUSB"] = _indi_id(hid)
        if wife_col:
            wid = row.get(wife_col.lower())
            if wid:
                fam["WIFE"] = _indi_id(wid)
        families[_fam_id(num)] = fam
    p(f"  {len(families):,} Familien aus '{fam_tbl}'")

    # Kinder
    if child_tbl:
        ctkey     = child_tbl.lower()
        cfid_col  = schema.find_col(ctkey, "familyid", "family_id", "familyrecordid")
        child_col = schema.find_col(ctkey, "childid", "individualid", "personid",
                                    "memberid")
        if cfid_col and child_col:
            added = 0
            for row in schema.fetch(f'SELECT * FROM "{child_tbl}"'):
                fnum = row.get(cfid_col.lower())
                cnum = row.get(child_col.lower())
                if fnum is None or cnum is None:
                    continue
                fid = _fam_id(fnum)
                cid = _indi_id(cnum)
                if fid in families and cid in individuals:
                    families[fid]["CHIL"].append(cid)
                    added += 1
            p(f"  {added:,} Kind-Verknüpfungen geladen")

    # Rückverknüpfungen: HUSB/WIFE → FAMS; Kinder → FAMC
    for fid, fam in families.items():
        if fam["HUSB"] and fam["HUSB"] in individuals:
            individuals[fam["HUSB"]]["FAMS"].append(fid)
        if fam["WIFE"] and fam["WIFE"] in individuals:
            individuals[fam["WIFE"]]["FAMS"].append(fid)
        for cid in fam["CHIL"]:
            if cid in individuals:
                individuals[cid]["FAMC"].append(fid)

    return families


# ── Öffentliche API ────────────────────────────────────────────────────────────

def is_ftm_file(filepath: str) -> bool:
    """True wenn die Datei den SQLite-Magic-Header hat (FTM 2014+)."""
    try:
        with open(filepath, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def load_ftm(filepath: str, progress_cb=None) -> tuple[dict, dict]:
    """
    Lädt eine Family-Tree-Maker-Datei (FTM 2014+, SQLite) und gibt
    (individuals, families) zurück — identische Struktur wie
    lib.gedcom.robust_load_gedcom().
    """
    p = progress_cb or (lambda m, **kw: None)
    _log("info", f"Lade FTM-Datei: {filepath}")

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"FTM-Datei nicht gefunden: {filepath}")
    if not is_ftm_file(filepath):
        raise ValueError(f"Datei ist keine SQLite/FTM-Datenbank: {filepath}")

    conn = sqlite3.connect(filepath)
    try:
        schema = _Schema(conn)
        table_preview = ", ".join(sorted(schema.tables)[:8])
        if len(schema.tables) > 8:
            table_preview += " …"
        p(f"  FTM-Schema: {len(schema.tables)} Tabellen ({table_preview})")

        # Gemeinsam genutzte Lookup-Maps vorab bauen
        tag_map = _build_tag_map(schema)
        places  = _build_place_map(schema)
        p(f"  {len(tag_map)} Ereignistypen, {len(places):,} Orte geladen")

        individuals = _load_individuals(schema, p)
        _load_names(schema, individuals, p)
        families    = _load_families(schema, individuals, p)
        # Ereignisse nach dem Familien-Aufbau, damit MARR direkt eingetragen wird
        _load_facts(schema, individuals, families, tag_map, places, p)

        german = sum(1 for i in individuals.values() if i.get("GERMAN_SOLDIER"))
        other  = sum(1 for i in individuals.values() if i.get("OTHER_SOLDIER"))
        fallen = sum(1 for i in individuals.values() if i.get("DIED_IN_BATTLE"))
        emig   = sum(1 for i in individuals.values() if i.get("EMIG", {}).get("DATE"))
        immi   = sum(1 for i in individuals.values() if i.get("IMMI", {}).get("DATE"))

        _log("info", f"FTM: {len(individuals):,} Personen, {len(families):,} Familien")
        _log("info", f"  ✠ {german}  ★ {other}  ⚔ {fallen}  EMIG {emig}  IMMI {immi}")
        p(f"FTM geladen: {len(individuals):,} Personen, {len(families):,} Familien",
          tag="ok")
        return individuals, families
    finally:
        conn.close()
