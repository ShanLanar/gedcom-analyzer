# -*- coding: utf-8 -*-
"""tasks/mrca.py – Most Recent Common Ancestor (MRCA).

Bestimmt den jüngsten gemeinsamen Vorfahren zweier Personen und
liefert Pfade sowie eine deutsche Verwandtschaftsbezeichnung."""

from collections import deque

from lib.gedcom import safe_extract_year
from lib.helpers import relationship_label


def _name(pdata: dict) -> str:
    return (pdata.get("NAME") or "").strip()


def _birth_year(pdata: dict):
    birt = pdata.get("BIRT") or {}
    return birt.get("YEAR") or safe_extract_year(birt.get("DATE"))


def _ancestors_with_depth(start_id: str, individuals: dict, families: dict,
                           max_depth: int) -> dict:
    """BFS aufwärts: gibt {ancestor_id: min_depth} inkl. start_id (Tiefe 0)."""
    depths: dict = {}
    if start_id not in individuals:
        return depths
    queue = deque([(start_id, 0)])
    depths[start_id] = 0
    while queue:
        pid, d = queue.popleft()
        if d >= max_depth:
            continue
        pdata = individuals.get(pid) or {}
        for fam_id in pdata.get("FAMC", []) or []:
            fam = families.get(fam_id)
            if not fam:
                continue
            for parent in (fam.get("HUSB"), fam.get("WIFE")):
                if not parent or parent not in individuals:
                    continue
                nd = d + 1
                if parent not in depths or depths[parent] > nd:
                    depths[parent] = nd
                    queue.append((parent, nd))
    return depths


def _parent_of(child_id: str, individuals: dict, families: dict):
    """Liefert Liste der Eltern-IDs (HUSB, WIFE) eines Kindes, gefiltert auf existierende."""
    pdata = individuals.get(child_id) or {}
    parents = []
    for fam_id in pdata.get("FAMC", []) or []:
        fam = families.get(fam_id)
        if not fam:
            continue
        for parent in (fam.get("HUSB"), fam.get("WIFE")):
            if parent and parent in individuals:
                parents.append(parent)
    return parents


def _reconstruct_path(start_id: str, target_id: str, individuals: dict,
                      families: dict, target_depth: int) -> list:
    """Rekonstruiert einen aufsteigenden Pfad von start_id zu target_id.

    Erwartet, dass target_id in genau target_depth Schritten erreichbar ist.
    Liefert Liste [(id, name, birth_year), …], inkl. start und target."""
    # BFS mit Parent-Pointern, abbrechen bei target_id
    if start_id == target_id:
        pdata = individuals.get(start_id) or {}
        return [(start_id, _name(pdata), _birth_year(pdata))]

    visited = {start_id: None}
    queue = deque([(start_id, 0)])
    while queue:
        pid, d = queue.popleft()
        if d >= target_depth:
            continue
        for parent in _parent_of(pid, individuals, families):
            if parent in visited:
                continue
            visited[parent] = pid
            if parent == target_id:
                # Pfad rekonstruieren
                path_ids = []
                cur = parent
                while cur is not None:
                    path_ids.append(cur)
                    cur = visited[cur]
                path_ids.reverse()
                return [
                    (pid_, _name(individuals.get(pid_) or {}),
                     _birth_year(individuals.get(pid_) or {}))
                    for pid_ in path_ids
                ]
            queue.append((parent, d + 1))
    # Fallback (sollte nicht passieren, wenn target_depth korrekt ist)
    return []


def _step_labels(path: list, individuals: dict, families: dict) -> list:
    """Gibt für jede Stufe im aufsteigenden Pfad 'Vater'/'Mutter' aus."""
    labels = []
    for i in range(len(path) - 1):
        child_id = path[i][0]
        parent_id = path[i + 1][0]
        parent = individuals.get(parent_id) or {}
        sex = (parent.get("SEX") or "").upper()
        if sex == "M":
            labels.append("Vater")
        elif sex == "F":
            labels.append("Mutter")
        else:
            labels.append("Elternteil")
    return labels


def find_mrca(id_a: str, id_b: str, individuals: dict, families: dict,
              max_depth: int = 15) -> dict:
    """Findet den jüngsten gemeinsamen Vorfahren (MRCA) zweier Personen."""
    result = {
        "mrca_id": None, "mrca_name": None, "mrca_birth_year": None,
        "depth_a": None, "depth_b": None, "total_depth": None,
        "relationship": None,
        "path_a": [], "path_b": [],
        "path_a_steps": [], "path_b_steps": [],
        "found": False, "message": "",
    }

    if id_a not in individuals:
        result["message"] = f"Person {id_a!r} nicht in Daten gefunden"
        return result
    if id_b not in individuals:
        result["message"] = f"Person {id_b!r} nicht in Daten gefunden"
        return result

    anc_a = _ancestors_with_depth(id_a, individuals, families, max_depth)
    anc_b = _ancestors_with_depth(id_b, individuals, families, max_depth)

    common = set(anc_a.keys()) & set(anc_b.keys())
    if not common:
        result["message"] = (
            f"Kein gemeinsamer Vorfahr innerhalb von {max_depth} "
            f"Generationen gefunden"
        )
        return result

    # MRCA: minimales depth_a + depth_b; Tiebreaker = jüngstes Geburtsjahr
    def _tiebreak(cid: str):
        total = anc_a[cid] + anc_b[cid]
        by = _birth_year(individuals.get(cid) or {})
        # Wir wollen min(total) und max(by). Für sortable Tupel:
        # primär kleines total, sekundär großes by → wir negieren by.
        return (total, -(by if by is not None else -10**9))

    mrca_id = min(common, key=_tiebreak)
    da = anc_a[mrca_id]
    db = anc_b[mrca_id]
    mrca = individuals.get(mrca_id) or {}

    path_a = _reconstruct_path(id_a, mrca_id, individuals, families, da)
    path_b = _reconstruct_path(id_b, mrca_id, individuals, families, db)

    # Verwandtschaftsbezeichnung über lib.helpers.relationship_label.
    # Signatur: relationship_label(root_d, target_d, is_target_ancestor=False).
    # Wenn eine der Personen selbst der MRCA ist, ist die andere ihr Vorfahr
    # (is_target_ancestor=True relativ zur Nicht-MRCA-Person).
    if da == 0 and db > 0:
        relationship = relationship_label(db, da, is_target_ancestor=True)
    elif db == 0 and da > 0:
        relationship = relationship_label(da, db, is_target_ancestor=True)
    elif da == 0 and db == 0:
        relationship = "identische Person"
    else:
        relationship = relationship_label(da, db, is_target_ancestor=False)

    result.update({
        "mrca_id": mrca_id,
        "mrca_name": _name(mrca),
        "mrca_birth_year": _birth_year(mrca),
        "depth_a": da,
        "depth_b": db,
        "total_depth": da + db,
        "relationship": relationship,
        "path_a": path_a,
        "path_b": path_b,
        "path_a_steps": _step_labels(path_a, individuals, families),
        "path_b_steps": _step_labels(path_b, individuals, families),
        "found": True,
        "message": (
            f"MRCA gefunden: {_name(mrca) or mrca_id} "
            f"(Tiefe {da}+{db}={da+db})"
        ),
    })
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def mrca_cli(argv=None) -> int:
    """CLI-Wrapper: liest GEDCOM, sucht MRCA, druckt Ergebnis.

    Exit-Codes: 0 = MRCA gefunden, 1 = nicht gefunden, 2 = Fehler."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="mrca",
        description="Most Recent Common Ancestor zweier Personen finden",
    )
    parser.add_argument("--gedfile", required=True, help="Pfad zur GEDCOM-Datei")
    parser.add_argument("--id-a", required=True, help="Person-ID A (z.B. @I123@)")
    parser.add_argument("--id-b", required=True, help="Person-ID B (z.B. @I456@)")
    parser.add_argument("--max-depth", type=int, default=15,
                        help="Maximale Generationentiefe (Standard 15)")

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code not in (0, None) else 0

    try:
        from lib.gedcom import robust_load_gedcom
        individuals, families = robust_load_gedcom(args.gedfile)
    except Exception as e:
        print(f"Fehler beim Laden der GEDCOM-Datei: {e}", file=sys.stderr)
        return 2

    try:
        result = find_mrca(args.id_a, args.id_b, individuals, families,
                           max_depth=args.max_depth)
    except Exception as e:
        print(f"Fehler bei MRCA-Berechnung: {e}", file=sys.stderr)
        return 2

    if not result["found"]:
        print(result["message"])
        return 1

    print(f"MRCA-ID            : {result['mrca_id']}")
    print(f"MRCA-Name          : {result['mrca_name']}")
    print(f"MRCA-Geburtsjahr   : {result['mrca_birth_year']}")
    print(f"Tiefe von A        : {result['depth_a']}")
    print(f"Tiefe von B        : {result['depth_b']}")
    print(f"Gesamttiefe        : {result['total_depth']}")
    print(f"Verwandtschaft     : {result['relationship']}")

    print("\nPfad A (aufsteigend):")
    for i, (pid, name, by) in enumerate(result["path_a"]):
        by_str = f" (*{by})" if by else ""
        step = ""
        if i > 0 and i - 1 < len(result["path_a_steps"]):
            step = f"  [{result['path_a_steps'][i - 1]}]"
        print(f"  {i:2d}. {pid} – {name}{by_str}{step}")

    print("\nPfad B (aufsteigend):")
    for i, (pid, name, by) in enumerate(result["path_b"]):
        by_str = f" (*{by})" if by else ""
        step = ""
        if i > 0 and i - 1 < len(result["path_b_steps"]):
            step = f"  [{result['path_b_steps'][i - 1]}]"
        print(f"  {i:2d}. {pid} – {name}{by_str}{step}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(mrca_cli())
