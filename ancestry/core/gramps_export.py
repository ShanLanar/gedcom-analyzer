"""
gramps_export.py — Export von DNA-Vorfahren und Matches in das native Gramps-XML-Format.

Das Gramps-XML-Format (*.gramps) ist das native Austauschformat von Gramps
(https://gramps-project.org). Es kann direkt importiert werden und unterstützt
alle Gramps-Analysen (Verwandtschaft, Karten, Statistiken, Berichte).

DSGVO: Lebende Personen (geschätztes Geburtsjahr nach 1920, kein Sterbejahr)
werden als „[privat]" exportiert — kein Name, kein Geburtsdatum.

Format-Version: Gramps XML 1.7.1
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _handle(seed: str) -> str:
    """Deterministisch reproduzierbares Gramps-Handle aus einem beliebigen Seed."""
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20].upper()
    return f"_{h}"


def _clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text)).strip()


def _is_living(birth_year: Optional[str], death_year: Optional[str]) -> bool:
    """True wenn die Person wahrscheinlich noch lebt (DSGVO-Schutz)."""
    if death_year and str(death_year).strip():
        return False
    if not birth_year:
        return False
    try:
        by = int(str(birth_year).lstrip("*").strip())
        return by >= 1920
    except (ValueError, TypeError):
        return False


def _sub(parent: ET.Element, tag: str, text: str = "", **attrib) -> ET.Element:
    el = ET.SubElement(parent, tag, **attrib)
    if text:
        el.text = _clean(text)
    return el


def export_gramps(
    groups: list,
    output_path: str,
    submitter_name: str = "AncestryDNATool",
    mask_living: bool = True,
) -> int:
    """Exportiert Pedigree-Gruppen in das Gramps-XML-Format.

    Parameters
    ----------
    groups : list
        Liste von Dicts aus ``db.get_pedigree_groups(mode="person")``.
        Pflicht-Keys: label, detail, count, matches.
        Optionale Keys: birth_place, death_year.
    output_path : str
        Zieldatei (.gramps).
    submitter_name : str
        Name des Erstellers (im Researcher-Block).
    mask_living : bool
        True = lebende Personen werden als [privat] exportiert.

    Returns
    -------
    int — Anzahl der exportierten INDI-Einträge.
    """
    ns = "https://gramps-project.org/xml/1.7.1/"
    ET.register_namespace("", ns)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Wurzel-Element ────────────────────────────────────────────────────────
    db_el = ET.Element("database", xmlns=ns)

    hdr = _sub(db_el, "header")
    _sub(hdr, "created", date=now_iso, version="5.1.5")
    res = _sub(hdr, "researcher")
    _sub(res, "resname", submitter_name)

    people_el  = _sub(db_el, "people")
    families_el = _sub(db_el, "families")
    events_el  = _sub(db_el, "events")
    notes_el   = _sub(db_el, "notes")

    # ── Phase 1: Personen sammeln ─────────────────────────────────────────────
    # Key: (name_lower, birth_year) → deduplizierte Personen
    indi_order: list[tuple] = []
    indi_meta: dict[tuple, dict] = {}
    sosa_to_keys: dict[int, list[tuple]] = {}
    indi_count = 0
    event_count = 0
    note_count = 0

    def _sosa_from_path(path: str) -> int:
        sosa = 1
        for ch in (path or ""):
            sosa = sosa * 2 if ch == "F" else sosa * 2 + 1
        return sosa

    def _register(label: str, birth_year: str, death_year: str,
                  count: int, matches: list, sosas: set,
                  birth_place: str = "") -> tuple:
        nonlocal indi_count
        key = (_clean(label).lower(), _clean(birth_year))
        if key not in indi_meta:
            indi_count += 1
            pid = f"I{indi_count:05d}"
            parts = label.split()
            given = " ".join(parts[:-1]) if len(parts) >= 2 else ""
            surn  = parts[-1] if parts else ""
            total_cm  = sum(float(m[4] or 0) for m in matches if len(m) > 4)
            s_list    = sorted(float(m[4] or 0) for m in matches if len(m) > 4)
            median_cm = s_list[len(s_list) // 2] if s_list else 0.0
            match_names = [_clean(m[1]) for m in matches[:5] if len(m) > 1 and m[1]]
            living = mask_living and _is_living(birth_year, death_year)
            indi_meta[key] = {
                "pid": pid, "handle": _handle(pid),
                "label": _clean(label),
                "given": "" if living else given,
                "surn":  "[privat]" if living else surn,
                "birth_year": "" if living else _clean(birth_year),
                "death_year": _clean(death_year),
                "birth_place": "" if living else _clean(birth_place),
                "count": count, "total_cm": total_cm, "median_cm": median_cm,
                "match_names": match_names,
                "extra_matches": max(0, len(matches) - len(match_names)),
                "sosas": set(sosas),
                "living": living,
                "fams": [], "famc": [],
                "birth_event_handle": None,
                "death_event_handle": None,
                "note_handle": None,
            }
            indi_order.append(key)
        else:
            m = indi_meta[key]
            m["count"] += count
            m["total_cm"] += sum(float(x[4] or 0) for x in matches if len(x) > 4)
            m["sosas"].update(sosas)
        for s in sosas:
            sosa_to_keys.setdefault(s, [])
            if key not in sosa_to_keys[s]:
                sosa_to_keys[s].append(key)
        return key

    for group in groups:
        label   = _clean(group.get("label", ""))
        detail  = _clean(group.get("detail", ""))
        count   = group.get("count", 0)
        matches = group.get("matches", [])
        if not label:
            continue
        birth_year  = detail.lstrip("*").strip()
        death_year  = _clean(group.get("death_year", ""))
        birth_place = _clean(group.get("birth_place", ""))
        sosas: set[int] = set()
        for m in matches:
            path = m[2] if len(m) > 2 else ""
            if path:
                sosas.add(_sosa_from_path(path))
        _register(label, birth_year, death_year, count, matches, sosas, birth_place)

    # ── Phase 2: Familienstruktur aus Sosa-Arithmetik ────────────────────────
    fam_count = 0
    fam_registry: dict[tuple, dict] = {}  # (father_handle, mother_handle) → fam_meta
    fam_children: dict[str, list] = {}    # fam_handle → [child_handle, …]

    for child_key in indi_order:
        meta = indi_meta[child_key]
        child_handle = meta["handle"]
        for sosa in list(meta["sosas"]):
            if sosa <= 1:
                continue
            father_sosa = sosa * 2
            mother_sosa = sosa * 2 + 1
            father_keys = sosa_to_keys.get(father_sosa, [])
            mother_keys = sosa_to_keys.get(mother_sosa, [])
            if not father_keys and not mother_keys:
                continue
            father_handle = indi_meta[father_keys[0]]["handle"] if father_keys else ""
            mother_handle = indi_meta[mother_keys[0]]["handle"] if mother_keys else ""
            fk = (father_handle, mother_handle)
            if fk not in fam_registry:
                fam_count += 1
                fam_id  = f"F{fam_count:05d}"
                fam_hnd = _handle(fam_id)
                fam_registry[fk] = {"id": fam_id, "handle": fam_hnd}
                fam_children[fam_hnd] = []
                if father_handle:
                    fk2 = next((k for k in indi_order if indi_meta[k]["handle"] == father_handle), None)
                    if fk2 and fam_hnd not in indi_meta[fk2]["fams"]:
                        indi_meta[fk2]["fams"].append(fam_hnd)
                if mother_handle:
                    mk2 = next((k for k in indi_order if indi_meta[k]["handle"] == mother_handle), None)
                    if mk2 and fam_hnd not in indi_meta[mk2]["fams"]:
                        indi_meta[mk2]["fams"].append(fam_hnd)
            else:
                fam_hnd = fam_registry[fk]["handle"]
            if child_handle not in fam_children[fam_hnd]:
                fam_children[fam_hnd].append(child_handle)
            if fam_hnd not in meta["famc"]:
                meta["famc"].append(fam_hnd)
            break

    # ── Phase 3: Events + Notes schreiben ────────────────────────────────────
    for key in indi_order:
        meta = indi_meta[key]
        if meta["living"]:
            continue
        # Geburts-Event
        if meta["birth_year"] or meta["birth_place"]:
            nonlocal_event_count = [event_count]
            nonlocal_event_count[0] += 1
            event_count = nonlocal_event_count[0]
            eid = f"E{event_count:05d}"
            ehnd = _handle(eid)
            ev = _sub(events_el, "event", handle=ehnd, id=eid)
            _sub(ev, "type", "Birth")
            if meta["birth_year"]:
                dv = _sub(ev, "dateval")
                dv.set("val", meta["birth_year"])
            if meta["birth_place"]:
                _sub(ev, "place", hlink=_handle("P" + meta["birth_place"][:20]))
            meta["birth_event_handle"] = ehnd

        # DNA-Notiz
        if not meta["living"] and meta["count"] > 0:
            note_count += 1
            nid = f"N{note_count:05d}"
            nhnd = _handle(nid)
            n = _sub(notes_el, "note", handle=nhnd, id=nid, type="General")
            note_text = (
                f"DNA-Beleg: {meta['count']} Match(es) · "
                f"gesamt {meta['total_cm']:.0f} cM · "
                f"Median {meta['median_cm']:.0f} cM"
            )
            if meta["match_names"]:
                joined = "; ".join(meta["match_names"])
                if meta["extra_matches"] > 0:
                    joined += f" (+{meta['extra_matches']} weitere)"
                note_text += f"\nBelegt durch: {joined}"
            _sub(n, "text", note_text)
            meta["note_handle"] = nhnd

    # ── Phase 4: INDI-Elemente schreiben ─────────────────────────────────────
    for key in indi_order:
        meta = indi_meta[key]
        p = _sub(people_el, "person", handle=meta["handle"], id=meta["pid"])

        # Geschlecht aus Sosa-Parität
        sosas_ns = {s for s in meta["sosas"] if s >= 2}
        if sosas_ns:
            sexes = {"M" if s % 2 == 0 else "F" for s in sosas_ns}
            gender = sexes.pop() if len(sexes) == 1 else "U"
        else:
            gender = "U"
        _sub(p, "gender", gender)

        # Name
        nm = _sub(p, "name", type="Birth Name")
        if meta["living"]:
            _sub(nm, "first", "[privat]")
        else:
            if meta["given"]:
                _sub(nm, "first", meta["given"])
            if meta["surn"]:
                _sub(_sub(nm, "surname"), "").text  # placeholder
                # Gramps erwartet <surname>text</surname>
                nm.remove(nm[-1])  # entfernen und neu anlegen
                sn_el = ET.SubElement(nm, "surname")
                sn_el.text = _clean(meta["surn"])

        # Geburts-Event-Referenz
        if meta.get("birth_event_handle"):
            er = _sub(p, "eventref", hlink=meta["birth_event_handle"], role="Primary")
            er.set("type", "Birth")

        # Sosa-Attribute
        sosas_sorted = sorted(meta["sosas"])[:8]
        if sosas_sorted:
            attr = _sub(p, "attribute", type="DNA Sosa", value=",".join(str(s) for s in sosas_sorted))
        if not meta["living"] and meta["count"] > 0:
            _sub(p, "attribute", type="DNA Matches", value=str(meta["count"]))
            _sub(p, "attribute", type="DNA gesamt cM", value=f"{meta['total_cm']:.0f}")

        # Notiz-Referenz
        if meta.get("note_handle"):
            _sub(p, "noteref", hlink=meta["note_handle"])

        # Familien-Links
        for fam_hnd in meta["famc"]:
            _sub(p, "childof", hlink=fam_hnd)
        for fam_hnd in meta["fams"]:
            _sub(p, "parentin", hlink=fam_hnd)

    # ── Phase 5: FAM-Elemente schreiben ──────────────────────────────────────
    for (father_hnd, mother_hnd), fam_meta in fam_registry.items():
        fam_hnd = fam_meta["handle"]
        f = _sub(families_el, "family", handle=fam_hnd, id=fam_meta["id"])
        _sub(f, "rel", type="Married")
        if father_hnd:
            _sub(f, "father", hlink=father_hnd)
        if mother_hnd:
            _sub(f, "mother", hlink=mother_hnd)
        for ch_hnd in fam_children.get(fam_hnd, []):
            _sub(f, "childref", hlink=ch_hnd)

    # ── Serialisierung ────────────────────────────────────────────────────────
    try:
        ET.indent(ET.ElementTree(db_el), space="  ")
    except AttributeError:
        _indent(db_el)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    xml_body = ET.tostring(db_el, encoding="unicode", xml_declaration=False)
    with out.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write('<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"\n')
        fh.write('  "https://gramps-project.org/xml/1.7.1/grampsxml.dtd">\n')
        fh.write(xml_body)
        fh.write("\n")

    return indi_count


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Minimal pretty-printer (Fallback für Python < 3.9 ohne ET.indent)."""
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent
