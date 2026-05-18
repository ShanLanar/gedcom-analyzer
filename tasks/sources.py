# -*- coding: utf-8 -*-
"""tasks/sources.py – Quellen-Analyse (SOUR-Records).

Liest SOUR-Records aus einer GEDCOM-Datei und zählt Zitationen pro
Quelle sowie pro Person. Liefert eine Quellen-Inventur und eine
Bewertung der Quellenlage pro Person."""

import os
import re

from lib.gedcom import safe_extract_year

SOURCE_INVENTORY_HEADERS = [
    "Quellen-ID", "Titel", "Autor", "Publikation",
    "Zitationen", "Personen-Verweise",
]
SOURCE_QUALITY_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr",
    "Quellen-Anzahl", "Qualität",
]

# 0 @S123@ SOUR
_RE_SOUR_RECORD = re.compile(r"^\s*0\s+(@[^@]+@)\s+SOUR\s*$")
# 0 @I123@ INDI
_RE_INDI_RECORD = re.compile(r"^\s*0\s+(@[^@]+@)\s+INDI\s*$")
# 0 @F123@ FAM
_RE_FAM_RECORD = re.compile(r"^\s*0\s+(@[^@]+@)\s+FAM\s*$")
# beliebige 0-Level-Zeile
_RE_LEVEL0 = re.compile(r"^\s*0\s+")
# Verweis: <level> SOUR @S123@   (level 1, 2 oder 3)
_RE_SOUR_REF = re.compile(r"^\s*([123])\s+SOUR\s+(@[^@]+@)\s*$")
# 1 TITL …, 1 AUTH …, 1 PUBL …
_RE_LEVEL1_TAG = re.compile(r"^\s*1\s+(TITL|AUTH|PUBL)\s*(.*)$")


def _name(pdata: dict) -> str:
    return (pdata.get("NAME") or "").strip()


def _birth_year(pdata: dict):
    birt = pdata.get("BIRT") or {}
    return birt.get("YEAR") or safe_extract_year(birt.get("DATE"))


def parse_sources(filepath: str) -> tuple[dict, dict, dict]:
    """Streaming-Parser für SOUR-Records und SOUR-Verweise.

    Liefert (sources, indi_citations, fam_citations):
    - sources: {source_id: {"title": str, "author": str, "publ": str,
                            "citations": int, "individuals": set,
                            "families": set}}
    - indi_citations: {indi_id: set(source_id, …)}
    - fam_citations:  {fam_id:  set(source_id, …)}
    """
    sources: dict = {}
    indi_citations: dict = {}
    fam_citations: dict = {}

    if not os.path.exists(filepath):
        return sources, indi_citations, fam_citations

    current_source_id = None  # nur gesetzt, während wir IN einem SOUR-Record sind
    current_indi_id = None
    current_fam_id = None

    with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue

            # Neue 0-Level-Zeile → alle Kontexte zurücksetzen
            if _RE_LEVEL0.match(line):
                current_source_id = None
                current_indi_id = None
                current_fam_id = None

                m = _RE_SOUR_RECORD.match(line)
                if m:
                    current_source_id = m.group(1)
                    sources.setdefault(current_source_id, {
                        "title": "", "author": "", "publ": "",
                        "citations": 0,
                        "individuals": set(),
                        "families": set(),
                    })
                    continue

                m = _RE_INDI_RECORD.match(line)
                if m:
                    current_indi_id = m.group(1)
                    continue

                m = _RE_FAM_RECORD.match(line)
                if m:
                    current_fam_id = m.group(1)
                    continue
                continue

            # Innerhalb eines SOUR-Records: TITL/AUTH/PUBL einsammeln
            if current_source_id:
                m = _RE_LEVEL1_TAG.match(line)
                if m:
                    tag, val = m.group(1), m.group(2).strip()
                    src = sources[current_source_id]
                    if tag == "TITL" and not src["title"]:
                        src["title"] = val
                    elif tag == "AUTH" and not src["author"]:
                        src["author"] = val
                    elif tag == "PUBL" and not src["publ"]:
                        src["publ"] = val
                continue

            # Innerhalb eines INDI/FAM: SOUR-Verweise einsammeln
            if current_indi_id or current_fam_id:
                m = _RE_SOUR_REF.match(line)
                if m:
                    src_id = m.group(2)
                    sources.setdefault(src_id, {
                        "title": "", "author": "", "publ": "",
                        "citations": 0,
                        "individuals": set(),
                        "families": set(),
                    })
                    sources[src_id]["citations"] += 1
                    if current_indi_id:
                        sources[src_id]["individuals"].add(current_indi_id)
                        indi_citations.setdefault(current_indi_id, set()).add(src_id)
                    elif current_fam_id:
                        sources[src_id]["families"].add(current_fam_id)
                        fam_citations.setdefault(current_fam_id, set()).add(src_id)

    return sources, indi_citations, fam_citations


def _classify(count: int) -> str:
    if count == 0:
        return "Keine Quelle"
    if count <= 2:
        return "Schwach belegt"
    if count <= 5:
        return "Solide belegt"
    return "Gut belegt"


def analyze_sources(individuals, families, filepath: str,
                    progress_cb=None) -> tuple[list, list]:
    """Liefert (inventory_rows, quality_rows).

    Wenn die GEDCOM-Datei keinerlei SOUR-Tags enthält, wird
    ([], []) zurückgegeben und eine Warnung über progress_cb gemeldet."""
    p = progress_cb or (lambda m, **kw: None)
    p("Quellen-Analyse …")

    sources, indi_citations, fam_citations = parse_sources(filepath)

    if not sources and not indi_citations and not fam_citations:
        p("Keine SOUR-Tags in GEDCOM gefunden", tag="warn")
        return [], []

    # Inventur
    inventory_rows = []
    for src_id, src in sources.items():
        inventory_rows.append([
            src_id,
            src.get("title") or "",
            src.get("author") or "",
            src.get("publ") or "",
            src.get("citations", 0),
            len(src.get("individuals") or set()),
        ])
    # Sortiert nach Zitationen absteigend, dann Quellen-ID
    inventory_rows.sort(key=lambda r: (-r[4], r[0]))

    # Personen-Quellenqualität
    quality_rows = []
    for pid, pdata in individuals.items():
        count = len(indi_citations.get(pid, set()))
        quality_rows.append([
            pid,
            _name(pdata),
            _birth_year(pdata) or "",
            count,
            _classify(count),
        ])
    # Sortiert nach Quellen-Anzahl absteigend, dann Person-ID
    quality_rows.sort(key=lambda r: (-r[3], r[0]))

    p(f"Quellen: {len(inventory_rows)} Quellen, "
      f"{sum(1 for r in quality_rows if r[3] > 0)} Personen mit Belegen",
      tag="ok")
    return inventory_rows, quality_rows
