# -*- coding: utf-8 -*-
"""tasks/endogamy_network.py – Nachnamen-Bigraph der Ehen.

Aggregiert über alle Ehen den ungerichteten Multigraphen
„Nachname-A  ─Ehe─  Nachname-B" und liefert sowohl eine Tabellen-Ansicht
der häufigsten Paarungen als auch einen GraphML-Export.
"""

import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from xml.etree.ElementTree import Element, SubElement

from lib.gedcom import safe_extract_year
from lib.helpers import safe_extract_family_name


ENDOGAMY_NETWORK_HEADERS = [
    "Nachname A", "Nachname B", "Anzahl Ehen",
    "Erste Heirat (J.)", "Letzte Heirat (J.)",
    "Region (häufigster Heiratsort)",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _surname_of(person_id, individuals):
    if not person_id:
        return ""
    pdata = individuals.get(person_id)
    if not pdata:
        return ""
    return safe_extract_family_name(pdata.get("NAME") or "")


def _marr_year(fam):
    yr = safe_extract_year(fam.get("MARR_DATE"))
    return yr


def _marr_region(place):
    """Letzter Komma-Teil ist üblicherweise Land/Region.  Fallback: ganzer String."""
    if not place:
        return ""
    parts = [p.strip() for p in str(place).split(",") if p.strip()]
    if not parts:
        return ""
    return parts[-1]


# ── Hauptanalyse ──────────────────────────────────────────────────────────────

def analyze_endogamy_bigraph(individuals, families, top_n=50,
                              progress_cb=None) -> list:
    p = progress_cb or (lambda m, **kw: None)
    p("Endogamie-Bigraph: Nachnamen-Ehe-Paarungen …")

    # pair → {"count": int, "years": [int], "regions": Counter}
    pairs = defaultdict(lambda: {"count": 0, "years": [], "regions": Counter()})

    total = len(families)
    for i, (fid, fam) in enumerate(families.items()):
        if i % 5000 == 0 and i > 0:
            p(f"  Bigraph: {i:,}/{total:,} Familien …")

        husb = fam.get("HUSB")
        wife = fam.get("WIFE")
        sn_h = _surname_of(husb, individuals)
        sn_w = _surname_of(wife, individuals)
        if not sn_h or not sn_w:
            continue
        if sn_h == sn_w:
            # Gleicher Nachname = innerfamiliäre Endogamie, separates Konzept.
            continue

        key = tuple(sorted((sn_h, sn_w)))
        e = pairs[key]
        e["count"] += 1
        yr = _marr_year(fam)
        if yr:
            e["years"].append(yr)
        reg = _marr_region(fam.get("MARR_PLACE"))
        if reg:
            e["regions"][reg] += 1

    ranked = sorted(pairs.items(), key=lambda kv: kv[1]["count"], reverse=True)
    rows = []
    for (a, b), data in ranked[:top_n]:
        years = data["years"]
        first = min(years) if years else ""
        last = max(years) if years else ""
        region = ""
        if data["regions"]:
            region = data["regions"].most_common(1)[0][0]
        rows.append([a, b, data["count"], first, last, region])

    p(f"Endogamie-Bigraph: {len(pairs):,} Paare, Top {len(rows)} ausgegeben",
      tag="ok")
    return rows


# ── GraphML-Export ────────────────────────────────────────────────────────────

_GRAPHML_NS = "http://graphml.graphdrawing.org/graphml"


def _add_data(parent, key, value):
    d = SubElement(parent, "data", key=key)
    d.text = str(value)


def _indent(elem, level=0):
    indent = "\n" + "  " * level
    child_indent = "\n" + "  " * (level + 1)
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = child_indent
        for child in elem[:-1]:
            if not child.tail or not child.tail.strip():
                child.tail = child_indent
            _indent(child, level + 1)
        last = elem[-1]
        if not last.tail or not last.tail.strip():
            last.tail = indent
        _indent(last, level + 1)
    if not elem.tail or not elem.tail.strip():
        elem.tail = indent


def _safe_xml_id(s):
    """GraphML-Node-IDs müssen XML-NMTOKEN-konform sein; Spaces/Sonderzeichen entfernen."""
    if not s:
        return "_"
    out = []
    for ch in str(s):
        if ch.isalnum() or ch in "-_.":
            out.append(ch)
        else:
            out.append("_")
    res = "".join(out)
    if not res or not (res[0].isalpha() or res[0] == "_"):
        res = "n_" + res
    return res


def export_endogamy_graphml(individuals, families, output_path,
                             min_count=3, progress_cb=None) -> bool:
    """Exportiert den Nachnamen-Ehe-Bigraphen als GraphML.

    Knoten: Nachnamen (Attribut `count` = Anzahl Träger im Stammbaum).
    Kanten: Ehe-Paarungen zweier Nachnamen (Attribut `weight` = Anzahl Ehen).
    Es werden nur Kanten mit weight >= min_count exportiert; isolierte Knoten
    (ohne qualifizierende Kante) werden weggelassen.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Endogamie-Bigraph GraphML-Export …")

    # Nachnamen-Träger zählen
    surname_count = Counter()
    for pdata in individuals.values():
        sn = safe_extract_family_name(pdata.get("NAME") or "")
        if sn:
            surname_count[sn] += 1

    # Kanten zählen
    edges = Counter()
    for fam in families.values():
        sn_h = _surname_of(fam.get("HUSB"), individuals)
        sn_w = _surname_of(fam.get("WIFE"), individuals)
        if not sn_h or not sn_w or sn_h == sn_w:
            continue
        edges[tuple(sorted((sn_h, sn_w)))] += 1

    # Filter
    kept_edges = [(pair, w) for pair, w in edges.items() if w >= min_count]
    if not kept_edges:
        p(f"Keine Kanten mit weight >= {min_count} gefunden.", tag="warn")

    # Knoten = alle Nachnamen, die in einer behaltenen Kante vorkommen
    node_set = set()
    for (a, b), _w in kept_edges:
        node_set.add(a)
        node_set.add(b)

    try:
        root_elem = Element("graphml")
        root_elem.set("xmlns", _GRAPHML_NS)

        for key_id, for_attr, attr_name, attr_type in [
            ("name",   "node", "name",   "string"),
            ("count",  "node", "count",  "int"),
            ("weight", "edge", "weight", "int"),
        ]:
            k = SubElement(root_elem, "key")
            k.set("id", key_id)
            k.set("for", for_attr)
            k.set("attr.name", attr_name)
            k.set("attr.type", attr_type)

        graph_elem = SubElement(root_elem, "graph")
        graph_elem.set("id", "G")
        graph_elem.set("edgedefault", "undirected")

        # IDs eindeutig: ein Mapping Surname → safe-id, mit Kollisionsschutz
        used = {}
        sid_of = {}
        for sn in sorted(node_set):
            base = _safe_xml_id(sn)
            cand = base
            n = 1
            while cand in used:
                n += 1
                cand = f"{base}_{n}"
            used[cand] = sn
            sid_of[sn] = cand

            node = SubElement(graph_elem, "node")
            node.set("id", cand)
            _add_data(node, "name", sn)
            _add_data(node, "count", surname_count.get(sn, 0))

        edge_counter = 0
        for (a, b), w in kept_edges:
            e = SubElement(graph_elem, "edge")
            e.set("id", f"e{edge_counter}")
            e.set("source", sid_of[a])
            e.set("target", sid_of[b])
            _add_data(e, "weight", w)
            edge_counter += 1

        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        _indent(root_elem)
        tree = ET.ElementTree(root_elem)
        ET.register_namespace("", _GRAPHML_NS)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            tree.write(f, encoding="unicode", xml_declaration=False)
            f.write("\n")

        size_kb = os.path.getsize(output_path) / 1024
        p(f"GraphML gespeichert: {output_path} "
          f"({size_kb:.1f} KB, {len(node_set):,} Knoten, "
          f"{edge_counter:,} Kanten)", tag="ok")
        return True

    except OSError as exc:
        p(f"Fehler beim Schreiben: {exc}", tag="err")
        return False
    except Exception as exc:
        p(f"Unerwarteter Fehler beim Bigraph-Export: {exc}", tag="err")
        return False
