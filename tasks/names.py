# -*- coding: utf-8 -*-
"""tasks/names.py – Namensmorphologie: Kölner Phonetik + Levenshtein"""

import re
from collections import defaultdict
from lib.gedcom import safe_extract_year
from lib.helpers import safe_extract_family_name


# ── Kölner Phonetik ────────────────────────────────────────────────────────────

def koelner_phonetik(name: str) -> str:
    if not name: return ""
    name = name.upper().strip()
    name = (name.replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE")
            .replace("ß", "SS").replace("PH", "F").replace("TH", "T"))
    name = re.sub(r'[^A-Z]', '', name)
    if not name: return ""
    codes = []
    n = len(name)
    for i, ch in enumerate(name):
        nxt = name[i + 1] if i < n - 1 else ''
        prev = name[i - 1] if i > 0 else ''
        if ch in 'AEIJOUY':  codes.append('0')
        elif ch == 'H':      continue
        elif ch == 'B':      codes.append('1')
        elif ch == 'P':      codes.append('1' if nxt != 'H' else '3')
        elif ch in 'DT':     codes.append('2' if nxt not in 'CSZ' else '8')
        elif ch in 'FVW':    codes.append('3')
        elif ch in 'GKQ':    codes.append('4')
        elif ch == 'C':
            if i == 0:       codes.append('4' if nxt in 'AHKLOQRUX' else '8')
            elif prev in 'SZ': codes.append('8')
            elif nxt in 'AHKOQUX': codes.append('4')
            else:            codes.append('8')
        elif ch == 'X':      codes.extend(['4', '8'])
        elif ch == 'L':      codes.append('5')
        elif ch in 'MN':     codes.append('6')
        elif ch == 'R':      codes.append('7')
        elif ch in 'SZ':     codes.append('8')
    reduced = []
    for c in codes:
        if not reduced or c != reduced[-1]: reduced.append(c)
    result = ''.join(reduced).lstrip('0') or '0'
    return result


def _levenshtein(a: str, b: str) -> int:
    if a == b: return 0
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        curr = [i]
        for j in range(1, lb + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            curr.append(min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + cost))
        prev = curr
    return prev[lb]


def _similar(a: str, b: str, max_lev: int = 2) -> bool:
    if not a or not b: return False
    au, bu = a.upper(), b.upper()
    if au[0] != bu[0]: return False
    la, lb = len(au), len(bu)
    if abs(la - lb) > max(3, int(max(la, lb) * 0.35)): return False
    return _levenshtein(au, bu) <= (max_lev if max(la, lb) <= 6 else max_lev + 1)


def _split_by_levenshtein(variants: set) -> list:
    vs = sorted(variants)
    clusters, assigned = [], set()
    for v in vs:
        if v in assigned: continue
        cluster = {v}; assigned.add(v)
        for w in vs:
            if w in assigned: continue
            if all(_similar(c, w) for c in cluster):
                cluster.add(w); assigned.add(w)
        if len(cluster) >= 2:
            clusters.append(frozenset(cluster))
    return clusters


# ── Analyse ────────────────────────────────────────────────────────────────────

def analyze_name_morphology(individuals, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Namensmorphologie (Kölner Phonetik + Levenshtein) …")

    surname_to_persons: dict = defaultdict(list)
    for pid, pdata in individuals.items():
        sn = safe_extract_family_name(pdata.get("NAME") or "")
        if sn and len(sn) >= 2:
            surname_to_persons[sn].append(pid)

    phonetik_groups: dict = defaultdict(set)
    for sn in surname_to_persons:
        kp = koelner_phonetik(sn)
        if kp: phonetik_groups[kp].add(sn)

    final_groups: dict = {}
    for kp, variants in phonetik_groups.items():
        if len(variants) < 2: continue
        if len(variants) <= 8:
            valid = frozenset(
                v for v in variants
                if any(_similar(v, w) for w in variants if w != v)
            )
            if len(valid) >= 2:
                clusters = _split_by_levenshtein(valid)
                if clusters: final_groups[kp] = clusters
        else:
            clusters = _split_by_levenshtein(variants)
            if clusters: final_groups[kp] = clusters

    variant_rows, person_cluster_map = [], {}
    for kp, clusters in final_groups.items():
        for ci, cluster in enumerate(clusters):
            sv = sorted(cluster)
            total = sum(len(surname_to_persons[v]) for v in cluster)
            first_years = []
            for v in cluster:
                for pid in surname_to_persons[v]:
                    by = safe_extract_year((individuals.get(pid, {}).get("BIRT") or {}).get("DATE"))
                    if by: first_years.append(by)
                    person_cluster_map[pid] = (kp, cluster)
            yr = f"{min(first_years)}–{max(first_years)}" if first_years else ""
            main = max(sv, key=len)
            code = f"{kp}" if len(clusters) == 1 else f"{kp}-{ci+1}"
            variant_rows.append([code, main, len(cluster), ", ".join(sv), total, yr,
                                   "Kölner Phonetik + Levenshtein-geprüfte Schreibvarianten"])

    variant_rows.sort(key=lambda x: x[4], reverse=True)

    person_rows = []
    for pid, (kp, cluster) in person_cluster_map.items():
        pdata = individuals.get(pid, {})
        name = (pdata.get("NAME") or "")[:40]
        sn   = safe_extract_family_name(pdata.get("NAME") or "")
        by   = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        others = ", ".join(sorted(cluster - {sn}))
        person_rows.append([pid, name, sn or "", kp, by or "", len(cluster), others[:60]])
    person_rows.sort(key=lambda x: x[3])

    p(f"Namensvarianten: {len(variant_rows)} Gruppen", tag="ok")
    return variant_rows, person_rows


VARIANT_HEADERS = [
    "Phonetik-Code", "Hauptname (heuristisch)", "Anzahl Varianten",
    "Alle Varianten", "Gesamtpersonen", "Zeitspanne", "Hinweis"
]
PERSON_VARIANT_HEADERS = [
    "ID", "Name", "Nachname", "Phonetik-Code", "Geburtsjahr",
    "Anzahl Varianten", "Andere Varianten"
]
