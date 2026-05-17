# -*- coding: utf-8 -*-
"""tasks/network.py – Familiennetzwerkanalyse"""

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed


def _build_adjacency(individuals, families) -> dict:
    adj = defaultdict(set)
    for fam in families.values():
        h, w = fam.get("HUSB"), fam.get("WIFE")
        if h and w:
            adj[h].add(w); adj[w].add(h)
    for pid, pdata in individuals.items():
        for fid in pdata.get("FAMC", []):
            fam = families.get(fid, {})
            if not fam: continue
            for par in (fam.get("HUSB"), fam.get("WIFE")):
                if par:
                    adj[pid].add(par); adj[par].add(pid)
        for fid in pdata.get("FAMS", []):
            fam = families.get(fid, {})
            if not fam: continue
            for sib in fam.get("CHIL", []):
                if sib != pid:
                    adj[pid].add(sib)
    return adj


def _social_role(pid, root_id, degree):
    if pid == root_id: return "Root/Stammvater"
    if degree >= 15:   return "Haupt-Knotenpunkt"
    if degree >= 10:   return "Knotenpunkt"
    if degree >= 5:    return "Vernetzt"
    return "Standard"


# ── Schnelle Version ───────────────────────────────────────────────────────────

def analyze_family_network_fast(individuals, families, root_id,
                                 progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Schnelle Netzwerkanalyse …")
    adj = _build_adjacency(individuals, families)

    priority = set([root_id])
    if root_id in adj: priority.update(adj[root_id])

    results = []
    for pid in priority:
        if pid not in individuals: continue
        conns = adj.get(pid, set())
        deg   = len(conns)
        pdata = individuals[pid]
        sx    = pdata.get("SEX", "")
        role  = ("Root" if pid == root_id
                 else "Ehemann/Vater" if sx == "M" and pdata.get("FAMS")
                 else "Ehefrau/Mutter" if sx == "F" and pdata.get("FAMS")
                 else "Kind" if pdata.get("FAMC") else "Unbekannt")
        conn_to_root = ("Root" if pid == root_id
                        else "Direkt" if root_id in conns
                        else "Indirekt")
        results.append([
            pid, (pdata.get("NAME", "") or "")[:40], deg,
            conn_to_root, role,
            len(pdata.get("FAMS", [])), len(pdata.get("FAMC", [])),
            ", ".join(list(conns)[:3])
        ])

    # Top 20 hoch-vernetzte hinzufügen
    all_deg = sorted(((pid, len(adj.get(pid, set())))
                      for pid in individuals), key=lambda x: -x[1])
    for pid, deg in all_deg[:20]:
        if pid not in priority and deg >= 5 and pid in individuals:
            name = (individuals[pid].get("NAME", "") or "")[:40]
            results.append([pid, name, deg, "Hoch vernetzt", "Vernetzungspunkt",
                             0, 0, f"{deg} Verbindungen"])

    results.sort(key=lambda x: x[2], reverse=True)
    p(f"Netzwerkanalyse: {len(results)} Personen", tag="ok")
    return results


# ── Parallele Version ──────────────────────────────────────────────────────────

def analyze_family_network_parallel(individuals, families, root_id,
                                     max_workers=4, progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Parallele Netzwerkanalyse …")
    adj = _build_adjacency(individuals, families)
    dist_cache: dict = {}

    def _analyze(pid):
        if pid not in adj: return None
        conns = adj[pid]
        deg   = len(conns)
        dc    = deg / (len(individuals) - 1) if len(individuals) > 1 else 0

        key = f"d_{pid}"
        if key in dist_cache:
            distances = dist_cache[key]
        else:
            distances, queue = {}, deque([(pid, 0)])
            seen = {pid}
            while queue:
                cur, d = queue.popleft()
                distances[cur] = d
                if d >= 6: continue
                for nb in adj.get(cur, set()):
                    if nb not in seen:
                        seen.add(nb); queue.append((nb, d + 1))
            if len(distances) < 1000:
                dist_cache[key] = distances

        closeness = 1 / (sum(distances.values()) / len(distances)) \
                    if len(distances) > 1 else 0
        cluster = ("Root-Linie" if pid == root_id
                   else "Hauptlinie" if root_id in conns
                   else "Nahe Hauptlinie" if any(root_id in adj.get(nb, set())
                                                  for nb in conns)
                   else "unbekannt")
        # Brücke (Heuristik): Nachbarn gehören zu mindestens zwei verschiedenen
        # Haushalten, identifiziert über den HUSB der jeweils ersten FAMS-
        # Familie eines Nachbarn. Eine echte Edge-Cut-Berechnung wäre teurer.
        neighbor_household_heads: set = set()
        for nb in conns:
            nb_fams = individuals.get(nb, {}).get("FAMS", [])
            if not nb_fams:
                continue
            head = families.get(nb_fams[0], {}).get("HUSB", "")
            if head:
                neighbor_household_heads.add(head)
        is_bridge = len(neighbor_household_heads) >= 2

        cn = [
            f"{(individuals.get(c, {}).get('NAME', '') or '')[:15]}…"
            for c in list(conns)[:5] if c in individuals
        ]
        return [pid, individuals[pid].get("NAME", "") or "",
                deg, round(dc, 4), round(closeness, 4),
                cluster, _social_role(pid, root_id, deg),
                "Ja" if is_bridge else "Nein", ", ".join(cn)]

    all_pids = list(individuals)
    results  = []
    batch    = 1000
    for i in range(0, len(all_pids), batch):
        bpids = [pid for pid in all_pids[i:i+batch] if pid in adj]
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_analyze, pid): pid for pid in bpids}
            for fut in as_completed(futs):
                try:
                    r = fut.result(timeout=5)
                    if r: results.append(r)
                except Exception:
                    pass
        if len(dist_cache) > 5000: dist_cache.clear()

    results.sort(key=lambda x: x[3], reverse=True)
    p(f"Parallele Netzwerkanalyse: {len(results)} Personen", tag="ok")
    return results


# ── Optimierte Version (Sampling) ─────────────────────────────────────────────

def analyze_family_network_optimized(individuals, families, root_id,
                                      sample_size=2000, max_workers=4,
                                      progress_cb=None):
    p = progress_cb or (lambda m, **kw: None)
    p("Optimierte Netzwerkanalyse (Sampling) …")
    adj = _build_adjacency(individuals, families)

    # Priorisiere nach Degree
    all_deg = sorted(((pid, len(adj.get(pid, set())))
                      for pid in individuals), key=lambda x: -x[1])
    sample = set([root_id])
    for pid, _ in all_deg[:sample_size]:
        sample.add(pid)
    if root_id in adj:
        sample.update(adj[root_id])

    def _analyze_opt(pid):
        if pid not in adj: return None
        conns = adj[pid]; deg = len(conns)
        dc = deg / (len(individuals) - 1) if len(individuals) > 1 else 0
        # 2-Hop-Erreichbarkeit als grobes Vernetzungsmaß
        reachable: set = {pid}
        for nb in conns:
            reachable.add(nb)
            reachable.update(adj.get(nb, set()))
        conn_to_root = ("Root" if pid == root_id
                        else "Direkt" if root_id in conns
                        else "Indirekt (1 Schritt)" if any(
                            root_id in adj.get(nb, set()) for nb in conns)
                        else "Nein")
        return [pid, individuals[pid].get("NAME", "") or "", deg,
                round(dc, 4), len(reachable),
                conn_to_root, _social_role(pid, root_id, deg),
                "Hoch" if deg >= 10 else "Mittel" if deg >= 5 else "Niedrig",
                ", ".join(list(conns)[:3])]

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_analyze_opt, pid) for pid in sample]
        for fut in futs:
            try:
                r = fut.result(timeout=3)
                if r: results.append(r)
            except Exception:
                pass

    results.sort(key=lambda x: x[3], reverse=True)
    p(f"Optimierte Netzwerkanalyse: {len(results)} Personen", tag="ok")
    return results


# ── Dispatcher ─────────────────────────────────────────────────────────────────

def run(individuals, families, root_id, progress_cb=None):
    """Wählt automatisch die passende Netzwerkanalyse nach Datenmenge."""
    total = len(individuals)
    if total > 10000:
        return analyze_family_network_optimized(
            individuals, families, root_id,
            sample_size=min(3000, total // 3), progress_cb=progress_cb)
    elif total > 3000:
        return analyze_family_network_parallel(
            individuals, families, root_id, progress_cb=progress_cb)
    else:
        return analyze_family_network_fast(
            individuals, families, root_id, progress_cb=progress_cb)


NETWORK_HEADERS_FAST = [
    "ID", "Name", "Degree (Verbindungen)", "Verbindung zu Root",
    "Familienrolle", "Anzahl Ehen", "Anzahl Eltern", "Verbindungen (Beispiele)"
]
NETWORK_HEADERS_FULL = [
    "ID", "Name", "Degree (Verbindungen)", "Degree Centrality",
    "Closeness Centrality", "Cluster/Familienzweig",
    "Soziale Rolle", "Brückenperson", "Wichtige Verbindungen (Beispiele)"
]
