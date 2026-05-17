# -*- coding: utf-8 -*-
"""tasks/extract_subtree.py – Teilbaum-Extraktion und GEDCOM-Export.

Extrahiert Nachkommen- bzw. Vorfahren-Teilbäume aus einem geladenen GEDCOM
und schreibt sie als gültige GEDCOM-5.5-Datei zurück.
"""

import os
from collections import deque


# ── Nachkommen-Extraktion ─────────────────────────────────────────────────────

def extract_descendants(root_id, individuals, families,
                         max_gen=10, progress_cb=None):
    """BFS über FAMS → CHIL, beschränkt auf max_gen Generationen.

    Liefert (individuals_subset, families_subset).  Eingeschlossen werden:
    - Wurzel und alle erreichten Nachkommen (bis max_gen)
    - Ehepartner jeder eingeschlossenen Person (HUSB/WIFE jeder FAMS-Familie)
    - Alle Familien, die zwei eingeschlossene Personen verbinden
    """
    p = progress_cb or (lambda m, **kw: None)
    p(f"Extrahiere Nachkommen von {root_id} (max_gen={max_gen}) …")

    if root_id not in individuals:
        p(f"Wurzel {root_id} nicht im Individuen-Dict.", tag="err")
        return {}, {}

    descendants = set()
    # BFS: (person_id, generation)
    queue = deque([(root_id, 0)])
    seen = set()
    while queue:
        cur, gen = queue.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        descendants.add(cur)
        if gen >= max_gen:
            continue
        pdata = individuals.get(cur)
        if not pdata:
            continue
        for fid in pdata.get("FAMS", []):
            fam = families.get(fid)
            if not fam:
                continue
            for child in fam.get("CHIL", []):
                if child and child in individuals and child not in seen:
                    queue.append((child, gen + 1))

    # Ehepartner aller Nachkommen hinzufügen
    keep_indi = set(descendants)
    for pid in list(descendants):
        pdata = individuals.get(pid)
        if not pdata:
            continue
        for fid in pdata.get("FAMS", []):
            fam = families.get(fid)
            if not fam:
                continue
            for spouse_key in ("HUSB", "WIFE"):
                sp = fam.get(spouse_key)
                if sp and sp in individuals:
                    keep_indi.add(sp)

    # Familien einschließen, in denen mindestens zwei eingeschlossene Personen
    # liegen ODER Wurzel-/Nachkommen-FAMS und FAMC-Verbindungen.
    keep_fam = set()
    for fid, fam in families.items():
        members = []
        if fam.get("HUSB"):
            members.append(fam["HUSB"])
        if fam.get("WIFE"):
            members.append(fam["WIFE"])
        members.extend(fam.get("CHIL", []) or [])
        in_set = [m for m in members if m in keep_indi]
        if len(in_set) >= 2:
            keep_fam.add(fid)
        elif len(in_set) == 1:
            # FAMS einer Einzelperson (Solo-Ehe ohne bekannten Partner): mitnehmen,
            # damit FAMS-Verweise konsistent bleiben.
            sole = in_set[0]
            if fid in (individuals.get(sole, {}).get("FAMS") or []):
                keep_fam.add(fid)

    sub_indi, sub_fam = _build_subset(keep_indi, keep_fam, individuals, families)
    p(f"  Nachkommen-Teilbaum: {len(sub_indi):,} Personen, {len(sub_fam):,} Familien",
      tag="ok")
    return sub_indi, sub_fam


# ── Vorfahren-Extraktion ──────────────────────────────────────────────────────

def extract_ancestors(root_id, individuals, families,
                      max_gen=12, progress_cb=None):
    """BFS über FAMC → HUSB/WIFE, beschränkt auf max_gen Generationen."""
    p = progress_cb or (lambda m, **kw: None)
    p(f"Extrahiere Vorfahren von {root_id} (max_gen={max_gen}) …")

    if root_id not in individuals:
        p(f"Wurzel {root_id} nicht im Individuen-Dict.", tag="err")
        return {}, {}

    keep_indi = set([root_id])
    queue = deque([(root_id, 0)])
    seen = set()
    while queue:
        cur, gen = queue.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        if gen >= max_gen:
            continue
        pdata = individuals.get(cur)
        if not pdata:
            continue
        for fid in pdata.get("FAMC", []):
            fam = families.get(fid)
            if not fam:
                continue
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par and par in individuals and par not in seen:
                    keep_indi.add(par)
                    queue.append((par, gen + 1))

    keep_fam = set()
    for fid, fam in families.items():
        members = []
        if fam.get("HUSB"):
            members.append(fam["HUSB"])
        if fam.get("WIFE"):
            members.append(fam["WIFE"])
        members.extend(fam.get("CHIL", []) or [])
        in_set = [m for m in members if m in keep_indi]
        if len(in_set) >= 2:
            keep_fam.add(fid)

    sub_indi, sub_fam = _build_subset(keep_indi, keep_fam, individuals, families)
    p(f"  Vorfahren-Teilbaum: {len(sub_indi):,} Personen, {len(sub_fam):,} Familien",
      tag="ok")
    return sub_indi, sub_fam


# ── Subset-Builder ────────────────────────────────────────────────────────────

def _build_subset(keep_indi, keep_fam, individuals, families):
    """Kopiert die behaltenen Records und filtert Referenzen auf das Subset."""
    sub_indi = {}
    for pid in keep_indi:
        src = individuals.get(pid)
        if not src:
            continue
        copy = dict(src)
        copy["FAMC"] = [f for f in (src.get("FAMC") or []) if f in keep_fam]
        copy["FAMS"] = [f for f in (src.get("FAMS") or []) if f in keep_fam]
        # Event-Dicts sind im Loader pro Person erzeugt — gemeinsame
        # Referenzen wären sicher, defensiv aber wir kopieren flach.
        for ev in ("BIRT", "DEAT", "EMIG", "IMMI"):
            if ev in copy and isinstance(copy[ev], dict):
                copy[ev] = dict(copy[ev])
        sub_indi[pid] = copy

    sub_fam = {}
    for fid in keep_fam:
        src = families.get(fid)
        if not src:
            continue
        copy = dict(src)
        h = src.get("HUSB")
        w = src.get("WIFE")
        copy["HUSB"] = h if h in keep_indi else None
        copy["WIFE"] = w if w in keep_indi else None
        copy["CHIL"] = [c for c in (src.get("CHIL") or []) if c in keep_indi]
        sub_fam[fid] = copy

    return sub_indi, sub_fam


# ── GEDCOM-Writer ─────────────────────────────────────────────────────────────

def _emit_event(lines, tag, ev_dict):
    """Hängt einen Event-Block (BIRT/DEAT/EMIG/IMMI) an, wenn DATE oder PLAC vorhanden."""
    if not ev_dict:
        return
    date = ev_dict.get("DATE")
    plac = ev_dict.get("PLAC")
    if not date and not plac:
        return
    lines.append(f"1 {tag}")
    if date:
        lines.append(f"2 DATE {date}")
    if plac:
        lines.append(f"2 PLAC {plac}")


def write_gedcom(individuals, families, output_path,
                  progress_cb=None) -> bool:
    """Schreibt (individuals, families) als GEDCOM-5.5-Datei.

    Felder, die in den Dicts None oder leer sind, werden ausgelassen.
    """
    p = progress_cb or (lambda m, **kw: None)
    p(f"Schreibe GEDCOM → {output_path}")

    try:
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        lines = []
        # Header
        lines.append("0 HEAD")
        lines.append("1 SOUR gedcom-analyzer")
        lines.append("1 GEDC")
        lines.append("2 VERS 5.5")
        lines.append("2 FORM LINEAGE-LINKED")
        lines.append("1 CHAR UTF-8")

        # Personen
        for pid, pdata in individuals.items():
            if not pdata:
                continue
            lines.append(f"0 {pid} INDI")
            name = pdata.get("NAME")
            if name:
                lines.append(f"1 NAME {name}")
            sex = pdata.get("SEX")
            if sex:
                lines.append(f"1 SEX {sex}")

            _emit_event(lines, "BIRT", pdata.get("BIRT"))
            _emit_event(lines, "DEAT", pdata.get("DEAT"))
            _emit_event(lines, "EMIG", pdata.get("EMIG"))
            _emit_event(lines, "IMMI", pdata.get("IMMI"))

            for fid in pdata.get("FAMC") or []:
                if fid:
                    lines.append(f"1 FAMC {fid}")
            for fid in pdata.get("FAMS") or []:
                if fid:
                    lines.append(f"1 FAMS {fid}")

        # Familien
        for fid, fam in families.items():
            if not fam:
                continue
            lines.append(f"0 {fid} FAM")
            if fam.get("HUSB"):
                lines.append(f"1 HUSB {fam['HUSB']}")
            if fam.get("WIFE"):
                lines.append(f"1 WIFE {fam['WIFE']}")
            for cid in fam.get("CHIL") or []:
                if cid:
                    lines.append(f"1 CHIL {cid}")
            mdate = fam.get("MARR_DATE")
            mplac = fam.get("MARR_PLACE")
            if mdate or mplac:
                lines.append("1 MARR")
                if mdate:
                    lines.append(f"2 DATE {mdate}")
                if mplac:
                    lines.append(f"2 PLAC {mplac}")

        lines.append("0 TRLR")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n")

        size_kb = os.path.getsize(output_path) / 1024
        p(f"GEDCOM gespeichert: {output_path} ({size_kb:.1f} KB, "
          f"{len(individuals):,} Personen, {len(families):,} Familien)",
          tag="ok")
        return True

    except OSError as exc:
        p(f"Fehler beim Schreiben: {exc}", tag="err")
        return False
    except Exception as exc:
        p(f"Unerwarteter Fehler: {exc}", tag="err")
        return False
