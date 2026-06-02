"""
Leeds-Cluster-Algorithmus für DNA-Matches.

Grundprinzip (Leeds-Methode):
  Matches >= 90 cM werden als primäre Ankerpunkte verwendet.
  Zwei primäre Matches landen im selben Cluster, wenn sie einen
  gemeinsamen Shared Match >= 20 cM haben (direkt oder transitiv).

  Das ergibt typischerweise 4 Cluster (die vier Großelternlinien),
  kann aber bei endogamen Populationen mehr oder weniger ergeben.

Ergebnis: dict mit cluster_id (int) → Liste von Match-Dicts
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


def build_clusters(
    shared_data: list[dict],
    min_cm_primary: float = 90.0,
    min_cm_shared : float = 20.0,
    max_cm_primary: float = 400.0,
) -> dict[int, list[dict]]:
    """
    Baut Cluster aus den Shared-Match-Daten auf (Union-Find-Algorithmus).

    :param shared_data:     Ergebnis von db.get_all_shared_for_cluster()
    :param min_cm_primary:  Mindest-cM für primäre Matches (Ankerpunkte)
    :param min_cm_shared:   Mindest-cM für Shared Matches (Kanten)
    :param max_cm_primary:  Obergrenze cM für primäre Matches – enge Verwandte
                            (>400 cM) verschmelzen sonst alle Cluster. <=0 = aus.
    :return:                {cluster_id: [{"guid", "name", "cm", "rel"}, ...]}
    """
    if not shared_data:
        return {}

    def in_primary_range(cm) -> bool:
        if cm is None or cm < min_cm_primary:
            return False
        if max_cm_primary and max_cm_primary > 0 and cm > max_cm_primary:
            return False
        return True

    # ── Primäre Matches sammeln (defensiver cM-Bereichsfilter) ────────────────
    primaries: dict[str, dict] = {}
    for row in shared_data:
        g = row["match_guid_a"]
        if g in primaries or not in_primary_range(row["cm_a"]):
            continue
        primaries[g] = {
            "guid": g,
            "name": row["name_a"],
            "cm"  : row["cm_a"],
            "rel" : row.get("rel_a", ""),
        }

    if not primaries:
        return {}

    # ── Union-Find ────────────────────────────────────────────────────────────
    parent = {g: g for g in primaries}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    # ── Kanten: zwei primäre Matches teilen einen Shared Match ───────────────
    # Shared-Match-cM ebenfalls prüfen (Brücken durch enge Verwandte vermeiden).
    shared_b_to_a: dict[str, list[str]] = {}
    for row in shared_data:
        a, b = row["match_guid_a"], row["match_guid_b"]
        if a not in primaries:
            continue
        cm_b = row.get("cm_b")
        if cm_b is not None and cm_b < min_cm_shared:
            continue
        if max_cm_primary and max_cm_primary > 0 and cm_b and cm_b > max_cm_primary:
            continue   # enger Verwandter als Shared → verbindet alle Linien
        shared_b_to_a.setdefault(b, []).append(a)

    for b, a_list in shared_b_to_a.items():
        for i in range(1, len(a_list)):
            union(a_list[0], a_list[i])

    # Falls ein Shared Match selbst ein primärer Match ist → direkt verbinden
    for row in shared_data:
        a, b = row["match_guid_a"], row["match_guid_b"]
        if a in primaries and b in primaries:
            union(a, b)

    # ── Cluster zusammensetzen ────────────────────────────────────────────────
    clusters: dict[str, list[dict]] = {}
    for g, info in primaries.items():
        clusters.setdefault(find(g), []).append(info)

    # Echte Cluster (>=2 Mitglieder) zuerst, dann Singletons – jeweils nach
    # durchschnittlicher cM absteigend. So stehen die Großelternlinien oben.
    groups = list(clusters.values())
    def avg_cm(members):
        return sum(m["cm"] for m in members) / len(members)
    multi  = sorted((g for g in groups if len(g) >= 2), key=avg_cm, reverse=True)
    single = sorted((g for g in groups if len(g) == 1), key=avg_cm, reverse=True)

    result = {}
    for idx, members in enumerate(multi + single, 1):
        members.sort(key=lambda m: m["cm"], reverse=True)
        result[idx] = members

    log.info("Clustering: %d primäre Matches → %d Cluster "
             "(%d echte, %d Singletons)",
             len(primaries), len(result), len(multi), len(single))
    return result


def cluster_summary(clusters: dict[int, list[dict]]) -> list[dict]:
    """Gibt eine kompakte Zusammenfassung der Cluster zurück."""
    summary = []
    for cid, members in clusters.items():
        cms = [m["cm"] for m in members]
        summary.append({
            "cluster_id"  : cid,
            "count"       : len(members),
            "max_cm"      : max(cms),
            "avg_cm"      : sum(cms) / len(cms),
            "top_matches" : [m["name"] for m in members[:3]],
        })
    return summary


def suggest_grandparent_lines(clusters: dict[int, list[dict]]) -> str:
    """
    Gibt eine einfache Textinterpretation der Cluster als Großelternlinien aus.
    Funktioniert am besten, wenn genau 4 Cluster entstehen.
    """
    n = len(clusters)
    lines = [f"Gefundene Cluster: {n}"]
    if n == 4:
        lines.append("→ Passt zur klassischen Leeds-Methode (4 Großelternlinien).")
    elif n < 4:
        lines.append("→ Weniger als 4 Cluster: möglicherweise endogame Population "
                     "oder zu wenige Shared Matches heruntergeladen.")
    else:
        lines.append("→ Mehr als 4 Cluster: gemischte Linien oder Halbgeschwister-Situation.")

    lines.append("")
    for cid, members in clusters.items():
        cms = [m["cm"] for m in members]
        top = ", ".join(m["name"] for m in members[:5])
        lines.append(
            f"Cluster {cid} ({len(members)} Matches, max {max(cms):.0f} cM): {top}"
            + ("…" if len(members) > 5 else "")
        )
    return "\n".join(lines)
