"""
Leeds-Cluster-Algorithmus für DNA-Matches.

Grundprinzip (Leeds-Methode):
  Matches >= min_cm_primary cM (Standard: 20 cM) werden als primäre
  Ankerpunkte verwendet. Der klassische Wert wäre 90 cM, aber bei
  kleinen Datensätzen ist ein niedrigerer Schwellenwert sinnvoll.
  Zwei primäre Matches landen im selben Cluster, wenn sie einen
  gemeinsamen Shared Match >= 20 cM haben (direkt oder transitiv).

  Das ergibt typischerweise 4 Cluster (die vier Großelternlinien),
  kann aber bei endogamen Populationen mehr oder weniger ergeben.

Ergebnis: dict mit cluster_id (int) → Liste von Match-Dicts

Alternative: Modularitäts-Clustering (Louvain/Clauset-Newman-Moore)
------------------------------------------------------------------
build_clusters_modularity() bietet eine graphbasierte Alternative zum
Union-Find der Leeds-Methode. Statt zwei primäre Matches schon bei *einem*
gemeinsamen Shared Match transitiv zu verschmelzen, wird ein gewichteter
ungerichteter Graph aufgebaut (Kantengewicht = Anzahl/Stärke gemeinsamer
Shared Matches) und die Greedy-Modularität Q maximiert:

    Q = (1 / 2m) · Σ_ij [ A_ij − resolution · k_i·k_j / 2m ] · δ(c_i, c_j)

Dabei werden Gemeinschaften nur dann zusammengelegt, wenn der Modularitäts-
gewinn ΔQ positiv ist. Das macht das Verfahren robuster gegen das klassische
Union-Find-Problem, bei dem ein einziges „über-geteiltes" Brücken-Match (etwa
ein enger Verwandter, der in mehreren Linien auftaucht) zwei eigentlich
getrennte Großelternlinien verschmelzen lässt (transitives Über-Mergen).

Wann bevorzugen? Wenn die Cluster „auslaufen" / alles in einen Riesencluster
fällt, oder wenn ein objektives Qualitätsmaß gewünscht ist: graph_modularity()
liefert das globale Q (≈0 = zufällig, →1 = stark modular, gut getrennt). Der
resolution-Parameter (>1 = mehr/kleinere, <1 = weniger/größere Cluster) steuert
die Granularität.
"""

import logging
import math
from typing import Optional

log = logging.getLogger(__name__)


def build_clusters(
    shared_data: list[dict],
    min_cm_primary: float = 20.0,
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

    if min_cm_primary > max_cm_primary > 0:
        log.warning("build_clusters: min_cm_primary (%.0f) > max_cm_primary (%.0f) — Werte getauscht",
                    min_cm_primary, max_cm_primary)
        min_cm_primary, max_cm_primary = max_cm_primary, min_cm_primary

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
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])  # vollständige Pfadkomprimierung
        return parent[x]

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
        return sum(m["cm"] for m in members) / len(members) if members else 0.0
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


def _build_modularity_graph(
    shared_data: list[dict],
    min_cm_primary: float,
    min_cm_shared: float,
    max_cm_primary: float,
) -> tuple[dict[str, dict], dict[str, dict[str, float]]]:
    """Sammelt primäre Matches und baut einen gewichteten ungerichteten Graphen.

    Liefert ``(primaries, adj)``:
      - ``primaries``: {guid: {"guid","name","cm","rel"}} — identisch zu
        build_clusters.
      - ``adj``: Adjazenzliste {a: {b: weight, ...}}, symmetrisch. Gewicht =
        Anzahl gemeinsamer Shared Matches (jeweils +1 pro gemeinsamem Shared
        Match), plus direkte Kanten (Gewicht 1), falls ein primärer Match selbst
        Shared Match eines anderen ist. Die cM-Filter (min_cm_shared,
        max_cm_primary-Brückenausschluss) entsprechen exakt build_clusters.
    """
    def in_primary_range(cm) -> bool:
        if cm is None or cm < min_cm_primary:
            return False
        if max_cm_primary and max_cm_primary > 0 and cm > max_cm_primary:
            return False
        return True

    # ── Primäre Matches sammeln (wie build_clusters) ──────────────────────────
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

    adj: dict[str, dict[str, float]] = {g: {} for g in primaries}
    if not primaries:
        return primaries, adj

    def add_edge(a: str, b: str, w: float) -> None:
        if a == b or a not in adj or b not in adj:
            return
        adj[a][b] = adj[a].get(b, 0.0) + w
        adj[b][a] = adj[b].get(a, 0.0) + w

    # ── Kanten über gemeinsame Shared Matches ─────────────────────────────────
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

    # Jeder gemeinsame Shared Match b erhöht das Gewicht jedes Paares (a_i, a_j)
    # um 1. Mehr gemeinsame Shared Matches → stärkere Kante.
    for b, a_list in shared_b_to_a.items():
        uniq = list(dict.fromkeys(a_list))      # Duplikate entfernen, Reihenfolge halten
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                add_edge(uniq[i], uniq[j], 1.0)

    # ── Direkte Kanten: Shared Match ist selbst primär (wie build_clusters) ────
    for row in shared_data:
        a, b = row["match_guid_a"], row["match_guid_b"]
        if a in primaries and b in primaries:
            add_edge(a, b, 1.0)

    return primaries, adj


def _greedy_modularity_communities(
    nodes: list[str],
    adj: dict[str, dict[str, float]],
    resolution: float,
) -> tuple[list[set[str]], float]:
    """Greedy-Modularitätsmaximierung (Clauset-Newman-Moore, agglomerativ).

    Start: jeder Knoten in eigener Gemeinschaft. Dann iterativ das Paar von
    Gemeinschaften zusammenlegen, das den größten positiven ΔQ liefert. Stopp,
    sobald kein Merge Q mehr erhöht. Knoten ohne Kanten bleiben Singletons.

    :return: (Liste von Gemeinschaften (set[guid]), finales Q)
    """
    # Gesamtgewicht m (Summe der Kantengewichte, ungerichtet).
    # 2m = Σ_i k_i, mit k_i = gewichteter Grad von i.
    deg: dict[str, float] = {n: sum(adj.get(n, {}).values()) for n in nodes}
    two_m = sum(deg.values())            # = 2 * m
    if two_m <= 0:
        # Keine Kanten → alle Singletons, Q = 0.
        return [{n} for n in nodes], 0.0
    m = two_m / 2.0

    # Gemeinschaft → Mitglieder; Knoten → Gemeinschafts-ID.
    comm_of: dict[str, int] = {n: i for i, n in enumerate(nodes)}
    members: dict[int, set[str]] = {i: {n} for i, n in enumerate(nodes)}

    # Σ_tot[c] = Summe der Grade aller Knoten in c.
    sigma_tot: dict[int, float] = {i: deg[nodes[i]] for i in range(len(nodes))}

    # Kantengewicht zwischen Gemeinschaften: e[(c, d)] (c < d) bzw. via Helper.
    def w_between(c: int, d: int) -> float:
        # Summe der Kantengewichte zwischen Gemeinschaft c und d.
        cm, dm = members[c], members[d]
        # über die kleinere Gemeinschaft iterieren
        if len(cm) > len(dm):
            cm, dm = dm, cm
        total = 0.0
        for u in cm:
            for v, w in adj.get(u, {}).items():
                if v in dm:
                    total += w
        return total

    def delta_q(c: int, d: int) -> float:
        # ΔQ beim Verschmelzen von c und d (ungerichtet, Resolution-skaliert).
        # ΔQ = (e_cd / m) − resolution · (Σtot_c · Σtot_d) / (2 m^2)
        e_cd = w_between(c, d)
        return (e_cd / m) - resolution * (sigma_tot[c] * sigma_tot[d]) / (2.0 * m * m)

    # Anfangs-Q (jeder Knoten allein) = − Σ_i resolution·(k_i/2m)^2.
    q = 0.0
    for n in nodes:
        q -= resolution * (deg[n] / two_m) ** 2

    # Kandidaten-Paare: nur Gemeinschaften, die durch mindestens eine Kante
    # verbunden sind (sonst ΔQ < 0, da e_cd = 0).
    while True:
        best_gain = 1e-12       # nur echte positive Gewinne akzeptieren
        best_pair: Optional[tuple[int, int]] = None

        active = [c for c in members if members[c]]
        # verbundene Paare bestimmen
        seen: set[tuple[int, int]] = set()
        for c in active:
            for u in members[c]:
                for v in adj.get(u, {}):
                    d = comm_of[v]
                    if d == c:
                        continue
                    pair = (c, d) if c < d else (d, c)
                    if pair in seen:
                        continue
                    seen.add(pair)
                    gain = delta_q(pair[0], pair[1])
                    if gain > best_gain:
                        best_gain = gain
                        best_pair = pair

        if best_pair is None:
            break

        c, d = best_pair
        # d in c verschmelzen
        for n in members[d]:
            comm_of[n] = c
        members[c] |= members[d]
        sigma_tot[c] += sigma_tot[d]
        del members[d]
        del sigma_tot[d]
        q += best_gain

    communities = [s for s in members.values() if s]
    return communities, q


def build_clusters_modularity(
    shared_data: list[dict],
    min_cm_primary: float = 20.0,
    min_cm_shared : float = 20.0,
    max_cm_primary: float = 400.0,
    resolution    : float = 1.0,
) -> dict[int, list[dict]]:
    """Graph-Modularitäts-Clustering (Louvain/CNM) – Alternative zu build_clusters.

    Gleicher Input-/Output-Vertrag wie build_clusters (drop-in für die GUI):
      - Input:  shared_data = db.get_all_shared_for_cluster()
      - Output: {cluster_id: [{"guid","name","cm","rel"}, ...]}, ids ab 1,
                echte Cluster (>=2) zuerst nach Ø-cM, dann Singletons, Mitglieder
                je Cluster nach cM absteigend.

    Statt Union-Find wird ein gewichteter Graph der primären Matches gebaut
    (Kantengewicht = Zahl/Stärke gemeinsamer Shared Matches) und die Greedy-
    Modularität maximiert. Das verhindert, dass ein einzelnes über-geteiltes
    Brücken-Match zwei getrennte Linien verschmelzt (transitives Über-Mergen).

    :param resolution: skaliert den Erwartungswert-Term (>1 = mehr/kleinere
                       Cluster, <1 = weniger/größere). Standard 1.0.
    """
    if not shared_data:
        return {}

    if min_cm_primary > max_cm_primary > 0:
        log.warning("build_clusters_modularity: min_cm_primary (%.0f) > "
                    "max_cm_primary (%.0f) — Werte getauscht",
                    min_cm_primary, max_cm_primary)
        min_cm_primary, max_cm_primary = max_cm_primary, min_cm_primary

    primaries, adj = _build_modularity_graph(
        shared_data, min_cm_primary, min_cm_shared, max_cm_primary)

    if not primaries:
        return {}

    nodes = list(primaries.keys())
    communities, q = _greedy_modularity_communities(nodes, adj, resolution)

    # ── Cluster zusammensetzen (Reihenfolge exakt wie build_clusters) ─────────
    groups: list[list[dict]] = [
        [primaries[g] for g in comm] for comm in communities
    ]

    def avg_cm(members):
        return sum(m["cm"] for m in members) / len(members) if members else 0.0
    multi  = sorted((g for g in groups if len(g) >= 2), key=avg_cm, reverse=True)
    single = sorted((g for g in groups if len(g) == 1), key=avg_cm, reverse=True)

    result = {}
    for idx, members in enumerate(multi + single, 1):
        members.sort(key=lambda m: m["cm"], reverse=True)
        result[idx] = members

    log.info("Modularitäts-Clustering: %d primäre Matches → %d Cluster "
             "(%d echte, %d Singletons), Q=%.4f, resolution=%.2f",
             len(primaries), len(result), len(multi), len(single), q, resolution)
    return result


def graph_modularity(
    shared_data: list[dict],
    min_cm_primary: float = 20.0,
    min_cm_shared : float = 20.0,
    max_cm_primary: float = 400.0,
    resolution    : float = 1.0,
) -> float:
    """Liefert das finale globale Modularitätsmaß Q des Modularitäts-Clusterings.

    Q ≈ 0 → Gemeinschaftsstruktur nicht besser als Zufall; Q → 1 → stark
    modular (sauber getrennte Linien). Praktisch sind Werte 0.3–0.7 typisch für
    klar strukturierte DNA-Match-Netze. Nützlich, um die Qualität/Trennschärfe
    eines Clusterings objektiv zu beurteilen.
    """
    if not shared_data:
        return 0.0
    if min_cm_primary > max_cm_primary > 0:
        min_cm_primary, max_cm_primary = max_cm_primary, min_cm_primary
    primaries, adj = _build_modularity_graph(
        shared_data, min_cm_primary, min_cm_shared, max_cm_primary)
    if not primaries:
        return 0.0
    nodes = list(primaries.keys())
    _, q = _greedy_modularity_communities(nodes, adj, resolution)
    return q


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


# Entfernt (Scrum-Review P2-7): compute_wrights_f() war nirgends aufgerufener,
# nicht funktionierender Code — durch die Union-Find-Partitionierung von
# build_clusters lag jeder Match in genau EINEM Cluster, sodass die Formel
# (n_clusters-1)/3 immer 0 ergab (Endogamie nie erkannt). Zudem hat
# "(n-1)/3" nichts mit dem Wright'schen Inzuchtkoeffizienten F zu tun (der eine
# IBD-Wahrscheinlichkeit ist) — der Name war irreführend. Eine echte
# Endogamie-Schätzung (Segment-Fragmentierung / Mehrfach-Cluster über
# shared_data) ist ein eigenes Thema und sollte nicht "Wright's F" heißen.


# Klassische Leeds-Methode: vier Farben für die vier Großelternlinien.
# Reihenfolge = Slot A–D (mitgliederstärkster Cluster zuerst).
LEEDS_COLORS = ["#F4B942", "#5B8FF9", "#5AD8A6", "#E8684A"]     # gelb, blau, grün, rot
LEEDS_COLOR_NAMES = ["Gelb", "Blau", "Grün", "Rot"]


def assign_grandparent_quadrants(clusters: dict[int, list[dict]],
                                 top_names: int = 6) -> dict:
    """Ordnet die (bis zu) 4 größten Cluster den vier Großeltern-Linien zu.

    Phasing-/Leeds-Heuristik: die vier mitgliederstärksten Cluster entsprechen
    typischerweise den vier Großelternlinien. Ohne Eltern-Kit lässt sich nicht
    entscheiden, welcher Quadrant väterlich bzw. mütterlich ist – die Slots sind
    daher generisch (A–D) benannt.

    Erwartet pro Match-dict mindestens ``cm`` und ``name`` (wie build_clusters
    liefert); ``guid`` optional.

    Returns
    -------
    dict mit:
      - ``n_clusters``: Gesamtzahl der Cluster
      - ``quadrants``:  Liste von bis zu 4 Slots (2×2-Raster), je
        ``{slot, label, cluster_id, size, max_cm, total_cm, names}``
      - ``unassigned``: gleiche Struktur für Cluster jenseits der Top 4
      - ``note``:       kurze Interpretationshilfe
    """
    def _summary(cid: int, members: list[dict]) -> dict:
        cms = [float(m.get("cm") or 0) for m in members]
        names = [m.get("name", "") for m in members[:top_names]]
        return {
            "cluster_id": cid,
            "size":       len(members),
            "max_cm":     max(cms) if cms else 0.0,
            "total_cm":   sum(cms),
            "names":      names,
        }

    # größte Cluster zuerst (nach Mitgliederzahl, dann max cM)
    ordered = sorted(
        clusters.items(),
        key=lambda kv: (len(kv[1]),
                        max((float(m.get("cm") or 0) for m in kv[1]), default=0.0)),
        reverse=True,
    )

    slot_labels = ["Großeltern-Linie A", "Großeltern-Linie B",
                   "Großeltern-Linie C", "Großeltern-Linie D"]
    quadrants, unassigned = [], []
    for idx, (cid, members) in enumerate(ordered):
        entry = _summary(cid, members)
        if idx < 4:
            entry = {"slot": idx, "label": slot_labels[idx],
                     "color": LEEDS_COLORS[idx],
                     "color_name": LEEDS_COLOR_NAMES[idx], **entry}
            quadrants.append(entry)
        else:
            unassigned.append(entry)

    n = len(clusters)
    if n == 0:
        note = "Keine Cluster – erst Shared Matches laden und Cluster berechnen."
    elif n == 4:
        note = "Genau 4 Cluster → passt sauber zu den 4 Großelternlinien (Leeds)."
    elif n < 4:
        note = ("Weniger als 4 Cluster: evtl. endogame Population oder zu wenige "
                "Shared Matches. Quadranten teils leer.")
    else:
        note = (f"{n} Cluster: die 4 größten sind den Quadranten zugeordnet, "
                f"{n - 4} weitere unten als 'weitere Linien'.")

    return {"n_clusters": n, "quadrants": quadrants,
            "unassigned": unassigned, "note": note}


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
