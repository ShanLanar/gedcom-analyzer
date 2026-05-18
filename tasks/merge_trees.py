# -*- coding: utf-8 -*-
"""tasks/merge_trees.py – Minimaler Merge zweier GEDCOM-Bäume.

Lädt zwei GEDCOM-Dateien, vergibt für die zweite ein ID-Präfix zur
Kollisionsvermeidung, findet Heuristik-Duplikate (Nachname + Vorname +
Geburtsjahr ± 2) und merged sie.  Schreibt das Ergebnis als GEDCOM.

Die Strategie ist bewusst einfach gehalten – produktives Mergen erfordert
deutlich mehr Logik (Quellenabwägung, Konflikt-UI, Familien-Verschmelzung).
"""

import os
from collections import defaultdict

from lib.gedcom import robust_load_gedcom, safe_extract_year
from lib.helpers import safe_extract_family_name

from tasks.extract_subtree import write_gedcom


# ── ID-Renumbering ────────────────────────────────────────────────────────────

def _renumber(indi_b, fam_b, prefix="B_"):
    """Hängt `prefix` an alle IDs (innerhalb der @…@-Klammern) und aktualisiert
    alle FAMC/FAMS/HUSB/WIFE/CHIL-Verweise."""

    def _r(old_id):
        if not old_id or not isinstance(old_id, str):
            return old_id
        if old_id.startswith("@") and old_id.endswith("@"):
            return f"@{prefix}{old_id[1:-1]}@"
        return old_id

    new_indi = {}
    for pid, pdata in indi_b.items():
        new_pid = _r(pid)
        copy = dict(pdata)
        copy["FAMC"] = [_r(f) for f in (pdata.get("FAMC") or [])]
        copy["FAMS"] = [_r(f) for f in (pdata.get("FAMS") or [])]
        for ev in ("BIRT", "DEAT", "EMIG", "IMMI"):
            if ev in copy and isinstance(copy[ev], dict):
                copy[ev] = dict(copy[ev])
        new_indi[new_pid] = copy

    new_fam = {}
    for fid, fam in fam_b.items():
        new_fid = _r(fid)
        copy = dict(fam)
        copy["HUSB"] = _r(fam.get("HUSB"))
        copy["WIFE"] = _r(fam.get("WIFE"))
        copy["CHIL"] = [_r(c) for c in (fam.get("CHIL") or [])]
        new_fam[new_fid] = copy

    return new_indi, new_fam


# ── Vornamen-Extraktion (lokal, ohne Religions-Klassifikation) ────────────────

def _first_given(name_str):
    if not name_str:
        return ""
    s = str(name_str)
    if "/" in s:
        s = s.split("/", 1)[0]
    s = s.strip()
    if not s:
        return ""
    first = s.split()[0].strip(".,;:()[]'\"")
    return first.upper()


def _birth_year(pdata):
    birt = pdata.get("BIRT") or {}
    return birt.get("YEAR") or safe_extract_year(birt.get("DATE"))


# ── Duplikat-Heuristik ────────────────────────────────────────────────────────

def _find_duplicates(indi_a, indi_b):
    """Liefert eine Liste [(id_a, id_b), …] kandidatengleicher Paare.

    Heuristik: exakt gleicher Nachname (uppercased) UND exakt gleicher
    erster Vorname (uppercased) UND Geburtsjahr-Differenz <= 2.
    Jede B-ID wird höchstens einmal gematcht (erstes Treffen gewinnt).
    """
    # Index über A: key=(surname, first), value=[(pid, year)]
    a_idx = defaultdict(list)
    for pid, pdata in indi_a.items():
        sn = safe_extract_family_name(pdata.get("NAME") or "").upper()
        fn = _first_given(pdata.get("NAME") or "")
        if not sn or not fn:
            continue
        a_idx[(sn, fn)].append((pid, _birth_year(pdata)))

    pairs = []
    used_a = set()
    for pid_b, pdata in indi_b.items():
        sn = safe_extract_family_name(pdata.get("NAME") or "").upper()
        fn = _first_given(pdata.get("NAME") or "")
        if not sn or not fn:
            continue
        yr_b = _birth_year(pdata)
        if yr_b is None:
            continue
        for pid_a, yr_a in a_idx.get((sn, fn), ()):
            if pid_a in used_a:
                continue
            if yr_a is None:
                continue
            if abs(yr_a - yr_b) <= 2:
                pairs.append((pid_a, pid_b))
                used_a.add(pid_a)
                break
    return pairs


# ── Feld-Merge ────────────────────────────────────────────────────────────────

def _merge_event(ev_a, ev_b):
    """Mergt zwei Event-Dicts: A hat Vorrang, B füllt nur leere Felder."""
    if not isinstance(ev_a, dict):
        ev_a = {}
    if not isinstance(ev_b, dict):
        ev_b = {}
    out = dict(ev_a)
    for key in ("DATE", "YEAR", "DATE_QUAL", "PLAC"):
        if not out.get(key) and ev_b.get(key):
            out[key] = ev_b[key]
    return out


def _merge_person(p_a, p_b):
    out = dict(p_a)
    # Skalare: A bevorzugt
    for key in ("NAME", "SEX", "BIRTH_PLACE"):
        if not out.get(key) and p_b.get(key):
            out[key] = p_b[key]
    # Bools: OR
    for key in ("MIGRATED", "DIED_IN_BATTLE", "VETERAN",
                "LINE_ENDS", "GERMAN_SOLDIER", "OTHER_SOLDIER"):
        out[key] = bool(p_a.get(key)) or bool(p_b.get(key))
    # Events
    for ev in ("BIRT", "DEAT", "EMIG", "IMMI"):
        out[ev] = _merge_event(p_a.get(ev), p_b.get(ev))
    # FAMC/FAMS: Union, Reihenfolge erhalten
    for key in ("FAMC", "FAMS"):
        seen = set()
        merged = []
        for src in (p_a.get(key) or [], p_b.get(key) or []):
            for v in src:
                if v and v not in seen:
                    seen.add(v)
                    merged.append(v)
        out[key] = merged
    return out


# ── Verweise umschreiben ──────────────────────────────────────────────────────

def _rewrite_refs(indi, fam, id_map):
    """Ersetzt in allen FAMC/FAMS/HUSB/WIFE/CHIL die alten IDs gemäß id_map."""
    def _m(x):
        return id_map.get(x, x)
    for pdata in indi.values():
        pdata["FAMC"] = [_m(f) for f in (pdata.get("FAMC") or [])]
        pdata["FAMS"] = [_m(f) for f in (pdata.get("FAMS") or [])]
    for f in fam.values():
        if f.get("HUSB"):
            f["HUSB"] = _m(f["HUSB"])
        if f.get("WIFE"):
            f["WIFE"] = _m(f["WIFE"])
        f["CHIL"] = [_m(c) for c in (f.get("CHIL") or [])]


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

def merge_gedcoms(file_a, file_b, output_path, progress_cb=None):
    """Mergt zwei GEDCOM-Dateien und schreibt das Ergebnis nach output_path.

    Returns
    -------
    (merged_individuals, merged_count) : (dict, int)
    """
    p = progress_cb or (lambda m, **kw: None)
    p(f"Lade A: {file_a}")
    indi_a, fam_a = robust_load_gedcom(file_a)
    p(f"  A: {len(indi_a):,} Personen, {len(fam_a):,} Familien")

    p(f"Lade B: {file_b}")
    indi_b_raw, fam_b_raw = robust_load_gedcom(file_b)
    p(f"  B: {len(indi_b_raw):,} Personen, {len(fam_b_raw):,} Familien")

    # B durchnummerieren
    indi_b, fam_b = _renumber(indi_b_raw, fam_b_raw, prefix="B_")

    # Duplikate finden
    p("Suche Duplikat-Kandidaten …")
    dup_pairs = _find_duplicates(indi_a, indi_b)
    p(f"  Kandidaten: {len(dup_pairs)}")

    # Felder mergen, ID-Map aufbauen (B → A)
    id_map = {}
    merge_log_pairs = []
    for pid_a, pid_b in dup_pairs:
        if pid_b not in indi_b or pid_a not in indi_a:
            continue
        merged = _merge_person(indi_a[pid_a], indi_b[pid_b])
        indi_a[pid_a] = merged
        id_map[pid_b] = pid_a
        merge_log_pairs.append((pid_a, pid_b,
                                 indi_a[pid_a].get("NAME") or "",
                                 indi_b[pid_b].get("NAME") or ""))
        # B-Eintrag entfernen
        del indi_b[pid_b]

    # In B verbliebene Personen/Familien einfügen, dann Verweise umschreiben
    merged_indi = dict(indi_a)
    merged_indi.update(indi_b)
    merged_fam = dict(fam_a)
    merged_fam.update(fam_b)

    _rewrite_refs(merged_indi, merged_fam, id_map)

    # Schreiben
    write_gedcom(merged_indi, merged_fam, output_path, progress_cb=progress_cb)

    # Merge-Log schreiben
    log_path = output_path + ".merge.log"
    try:
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write(f"# Merge log: {file_a}  +  {file_b}\n")
            lf.write(f"# Ergebnis:   {output_path}\n")
            lf.write(f"# Gemergte Duplikate: {len(merge_log_pairs)}\n")
            lf.write(f"# Format: <A-ID>\\t<B-ID-renumbered>\\t<A-Name>\\t<B-Name>\n")
            for pid_a, pid_b, na, nb in merge_log_pairs:
                lf.write(f"{pid_a}\t{pid_b}\t{na}\t{nb}\n")
        p(f"Merge-Log: {log_path}", tag="ok")
    except OSError as exc:
        p(f"Konnte Merge-Log nicht schreiben: {exc}", tag="warn")

    p(f"Merge fertig: {len(merged_indi):,} Personen, "
      f"{len(merge_log_pairs)} Duplikate gemergt", tag="ok")
    return merged_indi, len(merge_log_pairs)
