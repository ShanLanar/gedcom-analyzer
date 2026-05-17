# -*- coding: utf-8 -*-
"""tasks/genetics.py – Inzuchtkoeffizient (Wright's F) und Pedigree Collapse"""

from collections import defaultdict, deque
from lib.gedcom import safe_extract_year
from lib.places import format_place_for_display


# ── Wright's F ────────────────────────────────────────────────────────────────

# Modul-lokale Caches: Stammbaumdaten ändern sich pro Run nicht, also
# ist Memoization über (person_id, max_d) bzw. (person_id) sicher und spart
# in Stammbäumen mit starker Implosion drei Größenordnungen Laufzeit.
_ANCESTORS_DEPTH_CACHE: dict = {}
_F_CACHE: dict = {}


def clear_genetics_cache() -> None:
    """Aufrufen, wenn die GEDCOM-Daten neu geladen werden."""
    _ANCESTORS_DEPTH_CACHE.clear()
    _F_CACHE.clear()


def _ancestors_with_depth(start_id, individuals, families, max_d):
    key = (start_id, max_d)
    cached = _ANCESTORS_DEPTH_CACHE.get(key)
    if cached is not None:
        return cached
    result = defaultdict(list)
    queue = deque([(start_id, 0)])
    visited = set()
    while queue:
        cur, depth = queue.popleft()
        if depth > max_d: continue
        vkey = (cur, depth)
        if vkey in visited: continue
        visited.add(vkey)
        if depth > 0:
            result[cur].append(depth)
        cd = individuals.get(cur, {})
        if not cd: continue
        for fid in cd.get("FAMC", []):
            fam = families.get(fid, {})
            if not fam: continue
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par and par in individuals:
                    queue.append((par, depth + 1))
    _ANCESTORS_DEPTH_CACHE[key] = result
    return result


def compute_inbreeding_coefficient(person_id, individuals, families,
                                    max_depth=12) -> float:
    if person_id in _F_CACHE:
        return _F_CACHE[person_id]
    pdata = individuals.get(person_id, {})
    if not pdata:
        _F_CACHE[person_id] = 0.0
        return 0.0
    father_id = mother_id = None
    for fid in pdata.get("FAMC", []):
        fam = families.get(fid, {})
        if fam:
            father_id = fam.get("HUSB")
            mother_id = fam.get("WIFE")
            break
    if not father_id or not mother_id:
        _F_CACHE[person_id] = 0.0
        return 0.0

    fa = _ancestors_with_depth(father_id, individuals, families, max_depth)
    ma = _ancestors_with_depth(mother_id, individuals, families, max_depth)
    common = set(fa) & set(ma)
    if not common:
        _F_CACHE[person_id] = 0.0
        return 0.0

    # Markierung gegen Rekursion über Zyklen (in echten Pedigrees nicht
    # vorhanden, defensiv aber harmlos).
    _F_CACHE[person_id] = 0.0
    F = 0.0
    for anc in common:
        F_A = compute_inbreeding_coefficient(anc, individuals, families, max_depth)
        for l1 in fa[anc]:
            for l2 in ma[anc]:
                F += (0.5 ** (l1 + l2 + 1)) * (1 + F_A)
    F = round(min(F, 1.0), 6)
    _F_CACHE[person_id] = F
    return F


def analyze_inbreeding_all(individuals, families, root_related_ids=None,
                            progress_cb=None):
    from tasks._runner import is_aborted, AbortedError
    p = progress_cb or (lambda m, **kw: None)
    p("Inzuchtkoeffizient-Analyse (Wright's F) …")
    pids = list(root_related_ids if root_related_ids else individuals)
    results_inbred, results_clean = [], []

    for i, pid in enumerate(pids):
        if i % 100 == 0 and is_aborted():
            raise AbortedError("Inzucht-Analyse abgebrochen")
        if i % 500 == 0 and i > 0:
            p(f"  Inzucht: {i}/{len(pids)} …")
        pdata = individuals.get(pid, {})
        if not pdata: continue
        F = compute_inbreeding_coefficient(pid, individuals, families)
        name = pdata.get("NAME", "") or ""
        birth_year = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
        birth_place = format_place_for_display((pdata.get("BIRT") or {}).get("PLAC", ""))
        sex = pdata.get("SEX", "U")

        if F == 0.0:        klasse = "keine Inzucht"
        elif F < 0.0157:    klasse = "leicht (Cousins 3. Grades)"
        elif F < 0.0626:    klasse = "mäßig (Cousins 2./Halbcousin)"
        elif F < 0.126:     klasse = "erhöht (Cousins 1. Grades)"
        elif F < 0.251:     klasse = "stark (Onkel/Nichte, Halbgeschwister)"
        else:               klasse = "sehr stark (Geschwister / Elternteil-Kind)"

        fname = mname = ""
        for fid in pdata.get("FAMC", []):
            fam = families.get(fid, {})
            if fam:
                if fam.get("HUSB") and fam["HUSB"] in individuals:
                    fname = (individuals[fam["HUSB"]].get("NAME") or "")[:30]
                if fam.get("WIFE") and fam["WIFE"] in individuals:
                    mname = (individuals[fam["WIFE"]].get("NAME") or "")[:30]
                break

        row = [
            pid, name,
            "Männlich" if sex == "M" else "Weiblich" if sex == "F" else "Unbekannt",
            birth_year or "", birth_place,
            round(F, 6), f"{F*100:.3f}%", klasse, fname, mname
        ]
        (results_clean if F == 0.0 else results_inbred).append(row)

    results_inbred.sort(key=lambda x: x[5], reverse=True)
    final = results_inbred + results_clean
    inbred_cnt = len(results_inbred)
    f_vals = [r[5] for r in results_inbred]
    if f_vals:
        p(f"Inzucht: {inbred_cnt} Personen F > 0, Ø {sum(f_vals)/len(f_vals)*100:.3f}%",
          tag="ok")
    return final


INBREEDING_HEADERS = [
    "ID", "Name", "Geschlecht", "Geburtsjahr", "Geburtsort",
    "F-Koeffizient", "F in %", "Klassifizierung", "Vater", "Mutter"
]


# ── Pedigree Collapse ─────────────────────────────────────────────────────────

def analyze_pedigree_collapse(root_id, individuals, families,
                               max_generations=12, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Pedigree-Collapse-Analyse …")

    gen_slots  = defaultdict(list)
    gen_unique = defaultdict(set)
    person_gen = defaultdict(lambda: defaultdict(int))

    queue = deque([(root_id, 0)])
    visited = set()
    while queue:
        cur, gen = queue.popleft()
        if gen > max_generations: continue
        if (cur, gen) in visited: continue
        visited.add((cur, gen))
        if gen > 0:
            gen_slots[gen].append(cur)
            gen_unique[gen].add(cur)
            person_gen[cur][gen] += 1
        cd = individuals.get(cur, {})
        if not cd: continue
        for fid in cd.get("FAMC", []):
            fam = families.get(fid, {})
            if not fam: continue
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par and par in individuals:
                    queue.append((par, gen + 1))

    gen_rows = []
    max_gen = max(gen_slots) if gen_slots else 0
    for gen in range(1, max_gen + 1):
        theoretical  = 2 ** gen
        actual_slots = len(gen_slots.get(gen, []))
        unique       = len(gen_unique.get(gen, set()))
        dupes        = actual_slots - unique
        collapse     = (1 - unique / theoretical) * 100 if theoretical else 0
        fill         = (actual_slots / theoretical) * 100 if theoretical else 0
        examples = [
            f"{(individuals.get(pid, {}).get('NAME') or '')[:30]} (×{person_gen[pid].get(gen,1)})"
            for pid in gen_unique.get(gen, set())
            if person_gen[pid].get(gen, 1) > 1
        ][:3]
        gen_rows.append([gen, theoretical, actual_slots, unique, dupes,
                          round(fill, 1), round(collapse, 1),
                          ", ".join(examples) if examples else "—"])

    multi_rows = []
    for pid, gd in person_gen.items():
        total = sum(gd.values())
        if total > 1:
            pdata = individuals.get(pid, {})
            name  = (pdata.get("NAME") or "")[:40]
            by    = safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))
            bp    = format_place_for_display((pdata.get("BIRT") or {}).get("PLAC", ""))
            gens_str = ", ".join(f"Gen {g} (×{c})" for g, c in sorted(gd.items()))
            multi_rows.append([
                pid, name, by or "", bp, total, len(gd),
                min(gd), max(gd), gens_str[:80]
            ])
    multi_rows.sort(key=lambda x: x[4], reverse=True)
    p(f"Pedigree Collapse: {max_gen} Generationen, {len(multi_rows)} Mehrfach-Vorfahren",
      tag="ok")
    return gen_rows, multi_rows


PEDIGREE_GEN_HEADERS = [
    "Generation", "Theoretische Slots (2^n)", "Bekannte Slots",
    "Eindeutige Personen", "Duplikate",
    "Bekannte Slots %", "Collapse-Rate %", "Mehrfach-Personen (Beispiele)"
]
PEDIGREE_MULTI_HEADERS = [
    "ID", "Name", "Geburtsjahr", "Geburtsort",
    "Gesamt-Auftreten", "Anzahl Generationen",
    "Früheste Generation", "Späteste Generation", "Generationen-Detail"
]


# ── Kinship-Koeffizient ───────────────────────────────────────────────────────

def _kinship_coefficient(id_a, id_b, individuals, families, max_depth=10) -> float:
    """Computes kinship coefficient Φ(A,B).

    Φ(A,B) = (1/2) × Σ_{C ∈ common_ancestors(A,B)} Σ_{l_a, l_b}
              (1/2)^(l_a + l_b) × (1 + F_C)

    Each person is included at depth 0 (themselves) so that, e.g.,
    Φ(parent, child) = 0.25 is correct.
    """
    # Build ancestor maps including self at depth 0.
    raw_a = _ancestors_with_depth(id_a, individuals, families, max_depth)
    anc_a = defaultdict(list, {k: list(v) for k, v in raw_a.items()})
    anc_a[id_a].append(0)

    raw_b = _ancestors_with_depth(id_b, individuals, families, max_depth)
    anc_b = defaultdict(list, {k: list(v) for k, v in raw_b.items()})
    anc_b[id_b].append(0)

    common = set(anc_a) & set(anc_b)
    if not common:
        return 0.0

    phi = 0.0
    for anc in common:
        F_C = compute_inbreeding_coefficient(anc, individuals, families, max_depth)
        for l_a in anc_a[anc]:
            for l_b in anc_b[anc]:
                phi += (0.5 ** (l_a + l_b)) * (1 + F_C)
    return phi * 0.5


# ── DNA-cM-Schätzung ──────────────────────────────────────────────────────────

DNA_CM_HEADERS = [
    "ID", "Name", "Geschlecht", "Geburtsjahr", "Kinship Φ", "Erw. cM (Ø)", "DNA-Klasse"
]


def analyze_dna_cm_estimates(root_id, individuals, families,
                              root_related_ids=None, progress_cb=None) -> list:
    """For each person in root_related_ids (or all, capped at 50 000), compute
    the kinship coefficient Φ and the expected shared cM, then classify the
    relationship.  Only persons with Φ > 0 are included in the output.
    """
    from tasks._runner import is_aborted, AbortedError

    p = progress_cb or (lambda m, **kw: None)
    p("DNA-cM-Schätzungs-Analyse …")

    pids = list(root_related_ids if root_related_ids else individuals)
    if len(pids) > 50_000:
        pids = pids[:50_000]

    results = []
    for i, pid in enumerate(pids):
        if i % 500 == 0 and is_aborted():
            raise AbortedError("DNA-cM-Analyse abgebrochen")
        if i % 2000 == 0 and i > 0:
            p(f"  DNA-cM: {i}/{len(pids)} …")

        if pid == root_id:
            continue
        pdata = individuals.get(pid)
        if not pdata:
            continue

        phi = _kinship_coefficient(root_id, pid, individuals, families, max_depth=10)
        if phi == 0.0:
            continue

        expected_cm = round(phi * 2 * 7000, 1)

        if expected_cm >= 2400:
            klasse = "Elternteil/Geschwister"
        elif expected_cm >= 1300:
            klasse = "Großelternteil/Halbgeschwister/Tante/Onkel"
        elif expected_cm >= 600:
            klasse = "Cousin 1. Grades"
        elif expected_cm >= 200:
            klasse = "Cousin 2. Grades"
        elif expected_cm >= 60:
            klasse = "Cousin 3. Grades"
        elif expected_cm >= 20:
            klasse = "Cousin 4. Grades"
        elif expected_cm > 0:
            klasse = "Entfernter Verwandter"
        else:
            klasse = "Kein Nachweis"

        name = pdata.get("NAME", "") or ""
        sex = pdata.get("SEX", "U")
        birth_year = safe_extract_year((pdata.get("BIRT") or {}).get("DATE")) or ""

        results.append([
            pid, name,
            "Männlich" if sex == "M" else "Weiblich" if sex == "F" else "Unbekannt",
            birth_year,
            round(phi, 6),
            expected_cm,
            klasse,
        ])

    results.sort(key=lambda x: x[5], reverse=True)
    p(f"DNA-cM: {len(results)} verwandte Personen gefunden", tag="ok")
    return results
