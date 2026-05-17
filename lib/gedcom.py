# -*- coding: utf-8 -*-
"""
lib/gedcom.py
GEDCOM-Parser mit Fehlerbehandlung, Symbol-Erkennung und EMIG/IMMI-Events.
"""

import os
import re
import traceback
from datetime import datetime

# Wird von außen injiziert (main.py oder Tasks)
_logger = None

def set_logger(lg):
    global _logger
    _logger = lg

def _log(level, msg):
    if _logger:
        getattr(_logger, level)(msg)
    else:
        print(f"[{level.upper()}] {msg}")


# ── Datum ──────────────────────────────────────────────────────────────────────

# Einheitlicher Jahres-Regex für die ganze Codebase (1000–2099).
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|20\d{2})\b")


def safe_parse_gedcom_date(date_str: str) -> dict:
    try:
        if not date_str:
            return {"DATE": None, "YEAR": None, "DATE_QUAL": "unknown"}
        text = date_str.strip().upper()
        year_match = re.search(_YEAR_RE, text)
        year_val = int(year_match.group(0)) if year_match else None
        if text.startswith("ABT"):   qual = "about"
        elif text.startswith("EST"): qual = "estimated"
        elif text.startswith("BEF"): qual = "before"
        elif text.startswith("AFT"): qual = "after"
        elif text.startswith("BET"): qual = "between"
        elif text.startswith("FROM"):qual = "range"
        else: qual = "exact" if year_val else "unknown"
        return {"DATE": date_str, "YEAR": year_val, "DATE_QUAL": qual}
    except Exception as e:
        _log("warning", f"Fehler beim Parsen von Datum '{date_str}': {e}")
        return {"DATE": date_str, "YEAR": None, "DATE_QUAL": "error"}


def safe_extract_year(date_str) -> int | None:
    try:
        if not date_str:
            return None
        m = re.search(_YEAR_RE, str(date_str))
        return int(m.group(1)) if m else None
    except Exception:
        return None


# ── GEDCOM-Loader ──────────────────────────────────────────────────────────────

def robust_load_gedcom(filepath: str) -> tuple[dict, dict]:
    """
    Lädt GEDCOM mit umfassender Fehlerbehandlung.
    Erkennt Militär-Symbole: ✠ ★ ⚔ ‡ und mig.-Marker.
    Unterstützt EMIG/IMMI-Events.
    Gibt (individuals, families) zurück.
    """
    _log("info", f"Lade GEDCOM-Datei: {filepath}")

    if not os.path.exists(filepath):
        # Fallback-Pfade
        for alt in [filepath.replace("C:/ahnen/data/", "./"),
                    filepath.replace("C:\\ahnen\\data\\", "./"),
                    "family.ged", "data/family.ged"]:
            if os.path.exists(alt):
                _log("info", f"Alternative gefunden: {alt}")
                return robust_load_gedcom(alt)
        raise FileNotFoundError(f"GEDCOM nicht gefunden: {filepath}")

    individuals: dict = {}
    families: dict = {}
    current_id = current_type = current_event = current_event_level = None
    line_count = 0
    errors: list[str] = []

    def _new_indi():
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
            "LOAD_ERRORS": [],
        }

    def _new_fam():
        return {
            "HUSB": None, "WIFE": None, "CHIL": [],
            "MARR_DATE": None, "MARR_PLACE": None,
            "LOAD_ERRORS": [],
        }

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            for line_num, raw_line in enumerate(f, 1):
                line_count += 1
                try:
                    line = raw_line.rstrip("\n")
                    if not line.strip():
                        continue
                    parts = line.strip().split(" ", 2)
                    if len(parts) == 2:
                        level_str, tag, data = parts[0], parts[1], ""
                    else:
                        level_str, tag, data = parts

                    try:
                        level = int(level_str)
                    except ValueError:
                        errors.append(f"Zeile {line_num}: Ungültiges Level '{level_str}'")
                        continue

                    # Neuer Datensatz
                    if level == 0:
                        current_event = current_event_level = None
                        if tag.startswith("@") and data in ("INDI", "FAM"):
                            current_id, current_type = tag, data
                            if current_type == "INDI":
                                individuals[current_id] = _new_indi()
                            else:
                                families[current_id] = _new_fam()
                        else:
                            current_id = current_type = None
                        continue

                    if current_event_level is not None and level <= current_event_level:
                        current_event = current_event_level = None

                    # Personen-Daten
                    if current_type == "INDI" and current_id:
                        ind = individuals[current_id]
                        try:
                            if tag == "NAME":
                                ind["NAME"] = data
                                if "✠" in data:
                                    ind["GERMAN_SOLDIER"] = ind["VETERAN"] = True
                                if "★" in data:
                                    ind["OTHER_SOLDIER"] = ind["VETERAN"] = True
                                if "⚔" in data:
                                    ind["DIED_IN_BATTLE"] = True
                                if "‡" in data:
                                    ind["LINE_ENDS"] = True
                                if "mig." in data.lower():
                                    ind["MIGRATED"] = True
                            elif tag == "SEX":
                                ind["SEX"] = data
                            elif tag == "FAMC":
                                ind["FAMC"].append(data)
                            elif tag == "FAMS":
                                ind["FAMS"].append(data)
                            elif tag in ("BIRT", "DEAT", "CHR", "BAPM", "RESI",
                                         "EVEN", "EMIG", "IMMI"):
                                current_event = tag
                                current_event_level = level
                            # GEDCOM 7: GIVN/SURN sub-tags unter NAME
                            elif tag == "GIVN" and not current_event:
                                if not ind.get("_GIVN"):
                                    ind["_GIVN"] = data
                            elif tag == "SURN" and not current_event:
                                if not ind.get("_SURN"):
                                    ind["_SURN"] = data
                            elif tag == "DATE" and current_event and \
                                    current_event_level is not None and \
                                    level == current_event_level + 1:
                                parsed = safe_parse_gedcom_date(data)
                                for ev in ("BIRT", "DEAT", "EMIG", "IMMI"):
                                    if current_event == ev and ind[ev]["DATE"] is None:
                                        ind[ev].update(parsed)
                                        break
                            elif tag == "PLAC" and current_event and \
                                    current_event_level is not None and \
                                    level == current_event_level + 1:
                                for ev in ("BIRT", "DEAT", "EMIG", "IMMI"):
                                    if current_event == ev and ind[ev]["PLAC"] is None:
                                        ind[ev]["PLAC"] = data
                                        if ev == "BIRT":
                                            ind["BIRTH_PLACE"] = data
                                        break
                        except Exception as e:
                            msg = f"Zeile {line_num}: Fehler bei {current_id} – {e}"
                            errors.append(msg)
                            ind["LOAD_ERRORS"].append(msg)

                    # Familien-Daten
                    elif current_type == "FAM" and current_id:
                        fam = families[current_id]
                        try:
                            if tag == "HUSB":       fam["HUSB"] = data
                            elif tag == "WIFE":     fam["WIFE"] = data
                            elif tag == "CHIL":     fam["CHIL"].append(data)
                            elif tag == "MARR":
                                current_event = "MARR"
                                current_event_level = level
                            elif tag == "DATE" and current_event == "MARR" and \
                                    current_event_level is not None and \
                                    level == current_event_level + 1:
                                fam["MARR_DATE"] = data
                            elif tag == "PLAC" and current_event == "MARR" and \
                                    current_event_level is not None and \
                                    level == current_event_level + 1:
                                fam["MARR_PLACE"] = data
                        except Exception as e:
                            msg = f"Zeile {line_num}: Fehler bei {current_id} – {e}"
                            errors.append(msg)
                            fam["LOAD_ERRORS"].append(msg)

                except Exception as e:
                    errors.append(f"Zeile {line_num}: Unbekannter Fehler – {e}")

        # GEDCOM 7: NAME aus GIVN/SURN aufbauen, wenn NAME leer blieb
        for ind in individuals.values():
            if not ind.get("NAME"):
                givn = ind.pop("_GIVN", None)
                surn = ind.pop("_SURN", None)
                if givn or surn:
                    parts = []
                    if givn: parts.append(givn)
                    if surn: parts.append(f"/{surn}/")
                    ind["NAME"] = " ".join(parts)
            else:
                ind.pop("_GIVN", None)
                ind.pop("_SURN", None)

        # Leere Fehlerlisten entfernen
        for rec in list(individuals.values()) + list(families.values()):
            if not rec.get("LOAD_ERRORS"):
                rec.pop("LOAD_ERRORS", None)

        german = sum(1 for i in individuals.values() if i.get("GERMAN_SOLDIER"))
        other  = sum(1 for i in individuals.values() if i.get("OTHER_SOLDIER"))
        fallen = sum(1 for i in individuals.values() if i.get("DIED_IN_BATTLE"))
        emig   = sum(1 for i in individuals.values() if i.get("EMIG", {}).get("DATE"))
        immi   = sum(1 for i in individuals.values() if i.get("IMMI", {}).get("DATE"))

        _log("info", f"GEDCOM geladen: {line_count:,} Zeilen")
        _log("info", f"  {len(individuals):,} Personen, {len(families):,} Familien")
        _log("info", f"  ✠ {german}  ★ {other}  ⚔ {fallen}  EMIG {emig}  IMMI {immi}")
        if errors:
            _log("warning", f"  {len(errors)} Parse-Warnungen")

        return individuals, families

    except Exception as e:
        _log("critical", f"Kritischer Fehler beim Laden: {e}")
        _log("critical", traceback.format_exc())
        raise
