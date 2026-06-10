# -*- coding: utf-8 -*-
"""tasks/export_graphml.py – GraphML-Export des Familiennetzwerks"""

import os
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, SubElement
from lib.gedcom import safe_extract_year


# ── GraphML-Konstanten ─────────────────────────────────────────────────────────

_GRAPHML_NS = "http://graphml.graphdrawing.org/graphml"
_KEY_DEFS = [
    # (id, for, attr.name, attr.type)
    ("name",       "node", "name",       "string"),
    ("sex",        "node", "sex",        "string"),
    ("birth_year", "node", "birth_year", "int"),
    ("death_year", "node", "death_year", "int"),
    ("relation",   "edge", "relation",   "string"),
]


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _strip_at(pid: str) -> str:
    """Entfernt @ aus GEDCOM-IDs: '@I123@' → 'I123'."""
    return pid.replace("@", "")


def _display_name(pdata: dict) -> str:
    """Gibt den Anzeigenamen zurück; leere Strings vermieden."""
    return (pdata.get("NAME") or "").strip()


def _get_birth_year(pdata: dict):
    """Gibt Geburtsjahr als int oder None zurück."""
    return safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))


def _get_death_year(pdata: dict):
    """Gibt Sterbejahr als int oder None zurück."""
    return safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))


def _add_data(parent: Element, key: str, value) -> None:
    """Fügt ein <data key="...">wert</data>-Element hinzu."""
    d = SubElement(parent, "data", key=key)
    d.text = str(value)


def _indent(elem: Element, level: int = 0) -> None:
    """Fügt Einrückung und Zeilenumbrüche für lesbares XML ein (in-place)."""
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


# ── Haupt-Export-Funktion ──────────────────────────────────────────────────────

def export_graphml(
    individuals: dict,
    families: dict,
    output_path: str,
    root_id: str = None,
    root_related_ids: set = None,
    progress_cb=None,
) -> bool:
    """
    Schreibt das Familiennetzwerk als valide GraphML-Datei.

    Parameter
    ---------
    individuals : dict
        Personen-Dictionary aus robust_load_gedcom.
    families : dict
        Familien-Dictionary aus robust_load_gedcom.
    output_path : str
        Zieldatei (wird erstellt / überschrieben).
    root_id : str, optional
        ID der Stammperson (wird nur für Progress-Nachrichten genutzt).
    root_related_ids : set, optional
        Wenn angegeben, werden nur diese Personen (+ ihre Ehepartner)
        als Knoten exportiert.
    progress_cb : callable, optional
        Callback(msg, **kw) für Fortschrittsanzeige.

    Rückgabe
    --------
    bool
        True bei Erfolg, False bei Fehler.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("GraphML-Export gestartet …")

    # ── Personenmenge bestimmen ────────────────────────────────────────────────
    if root_related_ids is not None:
        # Ehepartner aller selektierten Personen einschließen
        extra_spouses: set = set()
        for pid in root_related_ids:
            pdata = individuals.get(pid)
            if not pdata:
                continue
            for fam_id in pdata.get("FAMS", []):
                fam = families.get(fam_id, {})
                for spouse_key in ("HUSB", "WIFE"):
                    spouse_id = fam.get(spouse_key)
                    if spouse_id and spouse_id in individuals:
                        extra_spouses.add(spouse_id)
        included_ids: set = root_related_ids | extra_spouses
        p(f"  Gefiltert: {len(included_ids):,} Personen (root_related + Ehepartner)")
    else:
        included_ids = set(individuals.keys())
        p(f"  Alle Personen exportieren: {len(included_ids):,}")

    # ── XML-Baum aufbauen ──────────────────────────────────────────────────────
    try:
        root_elem = Element("graphml")
        root_elem.set("xmlns", _GRAPHML_NS)

        # Schlüsseldefinitionen
        for key_id, for_attr, attr_name, attr_type in _KEY_DEFS:
            key_elem = SubElement(root_elem, "key")
            key_elem.set("id",        key_id)
            key_elem.set("for",       for_attr)
            key_elem.set("attr.name", attr_name)
            key_elem.set("attr.type", attr_type)

        # Graph-Element
        graph_elem = SubElement(root_elem, "graph")
        graph_elem.set("id",          "G")
        graph_elem.set("edgedefault", "directed")

        # ── Knoten ────────────────────────────────────────────────────────────
        p("  Schreibe Knoten …")
        node_count = 0
        for pid in sorted(included_ids):
            pdata = individuals.get(pid)
            if not pdata:
                continue
            node_elem = SubElement(graph_elem, "node")
            node_elem.set("id", _strip_at(pid))

            name = _display_name(pdata)
            if name:
                _add_data(node_elem, "name", name)

            sex = pdata.get("SEX") or ""
            if sex:
                _add_data(node_elem, "sex", sex)

            by = _get_birth_year(pdata)
            if by is not None:
                _add_data(node_elem, "birth_year", by)

            dy = _get_death_year(pdata)
            if dy is not None:
                _add_data(node_elem, "death_year", dy)

            node_count += 1

        p(f"  Knoten geschrieben: {node_count:,}")

        # ── Kanten ────────────────────────────────────────────────────────────
        p("  Schreibe Kanten …")
        edge_counter = 0
        parent_child_count = 0
        spouse_count = 0

        # Bereits geschriebene Ehepaar-Paare (ungerichtet: kleinere ID zuerst)
        written_spouse_pairs: set = set()

        for fam_id, fam in families.items():
            husb_id = fam.get("HUSB")
            wife_id = fam.get("WIFE")
            children = fam.get("CHIL", [])

            # Eltern→Kind-Kanten
            for parent_id in (husb_id, wife_id):
                if not parent_id or parent_id not in included_ids:
                    continue
                src = _strip_at(parent_id)
                for cid in children:
                    if cid not in included_ids:
                        continue
                    tgt = _strip_at(cid)
                    edge_elem = SubElement(graph_elem, "edge")
                    edge_elem.set("id",     f"e{edge_counter}")
                    edge_elem.set("source", src)
                    edge_elem.set("target", tgt)
                    _add_data(edge_elem, "relation", "parent_child")
                    edge_counter += 1
                    parent_child_count += 1

            # Ehepartner-Kanten (in beide Richtungen, jedes Paar nur einmal)
            if (husb_id and wife_id
                    and husb_id in included_ids
                    and wife_id in included_ids):
                pair = (min(husb_id, wife_id), max(husb_id, wife_id))
                if pair not in written_spouse_pairs:
                    written_spouse_pairs.add(pair)
                    h_node = _strip_at(husb_id)
                    w_node = _strip_at(wife_id)

                    # Vorwärts-Kante
                    e1 = SubElement(graph_elem, "edge")
                    e1.set("id",     f"e{edge_counter}")
                    e1.set("source", h_node)
                    e1.set("target", w_node)
                    _add_data(e1, "relation", "spouse")
                    edge_counter += 1

                    # Rückwärts-Kante (symmetrisch für Ehe)
                    e2 = SubElement(graph_elem, "edge")
                    e2.set("id",     f"e{edge_counter}")
                    e2.set("source", w_node)
                    e2.set("target", h_node)
                    _add_data(e2, "relation", "spouse")
                    edge_counter += 1

                    spouse_count += 1

        p(f"  Kanten geschrieben: {parent_child_count:,} Eltern→Kind, "
          f"{spouse_count:,} Ehepaare ({spouse_count * 2:,} gerichtete Kanten)")

    except Exception as exc:
        p(f"Fehler beim Aufbau des GraphML-Baums: {exc}", tag="err")
        return False

    # ── Datei schreiben ────────────────────────────────────────────────────────
    try:
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        p("  Einrücken und Serialisieren …")
        _indent(root_elem)

        tree = ET.ElementTree(root_elem)
        ET.register_namespace("", _GRAPHML_NS)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            # Schreibe ohne XML-Deklaration (bereits manuell geschrieben)
            tree.write(f, encoding="unicode", xml_declaration=False)
            f.write("\n")

        size_kb = os.path.getsize(output_path) / 1024
        p(f"GraphML gespeichert: {output_path} ({size_kb:.1f} KB, "
          f"{node_count:,} Knoten, {edge_counter:,} Kanten)", tag="ok")
        return True

    except OSError as exc:
        p(f"Fehler beim Schreiben der GraphML-Datei: {exc}", tag="err")
        return False
    except Exception as exc:
        p(f"Unerwarteter Fehler beim GraphML-Export: {exc}", tag="err")
        return False
