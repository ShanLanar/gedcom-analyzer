# -*- coding: utf-8 -*-
"""
tasks/compgen_metasearch.py — CompGen-/genealogy.net-Metasuche pro Ahn.

Fragt die zentrale Metasuche des Vereins für Computergenealogie (CompGen,
genealogy.net) ab. Diese Metasuche bündelt unter einer einzigen Schnittstelle
mehrere deutschsprachige Genealogie-Datenbanken, u. a.:

  • GEDBAS        — hochgeladene (lineage-linked) Stammbäume
  • OFB           — Ortsfamilienbücher / Dorfsippenbücher
  • Adressbücher  — digitalisierte Einwohner-/Adressbücher
  • Grabsteine    — Grabstein-Dokumentationsprojekt (Friedhöfe)
  • Verlustlisten — Verlustlisten 1. Weltkrieg (DES-Projekt)
  • FOKO          — Forschungskontakte (wer forscht zu welchem Namen/Ort)

Schnittstelle (dokumentiert unter wiki-en.genealogy.net/Metasearch/API):
  Endpoint  https://meta.genealogy.net/metasearch/search
  Parameter lastname (Pflicht), placename (optional), placeid (GOV, optional),
            since (YYYY-MM-DD, optional)
  Antwort   text/xml mit Wurzel <result>, darin je Datenbank ein <database>
            mit <name>, <url> und beliebig vielen <entry> (lastname, firstname,
            details, url); <more>true</more> markiert weitere Treffer.

Es wird AUSSCHLIESSLICH gelesen — nichts wird ins GEDCOM zurückgeschrieben.
Es ist KEIN API-Key erforderlich (die Lese-Metasuche ist öffentlich).

FAIL-SOFT: Bei nicht erreichbarem Endpoint, Timeout, HTTP-Fehler oder
abweichendem XML-Format wird NIE eine Exception nach oben gereicht. Statt-
dessen liefert die Person eine Zeile mit leeren Trefferzahlen und nur dem
GEDBAS-/Meta-Such-Link, damit der Lauf weiterläuft.
"""

import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from lib.gedcom import safe_extract_year

# ── Konstanten ────────────────────────────────────────────────────────────────

_META_ENDPOINT = "https://meta.genealogy.net/metasearch/search"
# Reine Such-Oberfläche (für den anklickbaren Link in der Ergebniszeile).
_META_SEARCH_UI = "https://meta.genealogy.net/search/index"
_GEDBAS_SEARCH  = "https://gedbas.genealogy.net/search/simple"

_USER_AGENT = (
    "gedcom-analyzer/9.0 (genealogy research tool; "
    "contact: github.com/shanlanar/gedcom-analyzer)"
)

# Pause zwischen Personen, damit die CompGen-Server nicht überlastet werden.
_DELAY_S = 1.5

# Obergrenze, um stundenlange Läufe bei großen Bäumen zu verhindern.
_MAX_LOOKUPS = 300

# Personen ab diesem Geburtsjahr werden aus Datenschutzgründen NICHT abgefragt
# (könnten noch leben).
_MAX_BIRTH_YEAR = 1930

# Schlüsselwörter → Spaltenzuordnung. Die Metasuche liefert je Datenbank einen
# <name>-String; wir ordnen ihn anhand dieser Marker einer Ergebnis-Spalte zu.
_DB_BUCKETS: list[tuple[str, tuple[str, ...]]] = [
    ("gedbas",       ("gedbas",)),
    ("ofb",          ("ofb", "ortsfamilienbuch", "ortsfamilienbücher",
                      "familienbuch", "dorfsippenbuch")),
    ("adressbuch",   ("adressbuch", "adressbücher", "adressbuecher",
                      "einwohner")),
    ("grabstein",    ("grabstein", "grabsteine", "friedhof", "grabmal")),
    ("verlustliste", ("verlustliste", "verlustlisten")),
    ("foko",         ("foko", "forschungskontakt", "forschungskontakte")),
]

COMPGEN_METASEARCH_HEADERS = [
    "Person-ID", "Name", "Geb.", "Geb.-Ort",
    "GEDBAS-Treffer", "OFB-Treffer", "Adressbuch-Treffer",
    "Grabstein-Treffer", "Verlustliste-Treffer", "FOKO-Kontakte",
    "Link",
]

# Plausible DACH-Marker (leichtgewichtig, falls externe_quellen nicht importierbar).
_DACH_FALLBACK = {
    "deutschland", "germany", "niedersachsen", "westfalen", "preußen",
    "sachsen", "thüringen", "bayern", "württemberg", "hessen", "rheinland",
    "österreich", "austria", "schweiz", "switzerland",
    "osnabrück", "münster", "hannover", "hamburg", "bremen", "berlin",
}

# Helfer aus externe_quellen wiederverwenden, wo praktikabel.
try:
    from tasks.externe_quellen import _is_dach as _is_dach  # type: ignore
    from tasks.externe_quellen import _split_name as _split_name  # type: ignore
except Exception:  # pragma: no cover - reiner Fallback
    def _split_name(name: str) -> tuple[str, str]:
        if not name:
            return "", ""
        cleaned = re.sub(r"[✠★⚔‡]", "", name).strip()
        cleaned = re.sub(r"\bmig\.\S*\b", "", cleaned, flags=re.IGNORECASE).strip()
        if "/" in cleaned:
            parts = cleaned.split("/")
            return parts[0].strip(), (parts[1].strip() if len(parts) >= 2 else "")
        words = cleaned.split()
        return (" ".join(words[:-1]), words[-1]) if len(words) > 1 else (cleaned, "")

    def _is_dach(plac: str) -> bool:
        if not plac:
            return True
        return any(w in plac.lower() for w in _DACH_FALLBACK)


# ── Hilfs-Extraktion (Konventionen wie externe_quellen) ───────────────────────

def _yr(evt) -> int | None:
    if not evt:
        return None
    return evt.get("YEAR") or safe_extract_year(evt.get("DATE"))


def _first(plac: str) -> str:
    return plac.split(",")[0].strip() if plac else ""


def _gedbas_link(surname: str, place: str) -> str:
    """GEDBAS-Einfachsuche als anklickbarer Fallback-Link."""
    params: dict = {"lastname": surname}
    p = _first(place)
    if p:
        params["placename"] = p
    return _GEDBAS_SEARCH + "?" + urllib.parse.urlencode(params)


def _meta_ui_link(surname: str, place: str) -> str:
    """Metasuche-Oberfläche als anklickbarer Link für die Person."""
    params: dict = {"lastname": surname}
    p = _first(place)
    if p:
        params["placename"] = p
    return _META_SEARCH_UI + "?" + urllib.parse.urlencode(params)


# ── Metasuche-Abfrage ─────────────────────────────────────────────────────────

def _classify_db(name: str) -> str | None:
    """Datenbank-Namen aus der Metasuche → interner Bucket-Schlüssel."""
    if not name:
        return None
    low = name.lower()
    for bucket, markers in _DB_BUCKETS:
        if any(m in low for m in markers):
            return bucket
    return None


def _count_entries(db_el) -> int:
    """Zählt <entry>-Kinder eines <database>-Elements (rekursiv-tolerant)."""
    n = len(db_el.findall("entry"))
    if n == 0:
        # Manche Implementierungen verschachteln die Einträge tiefer.
        n = len(db_el.findall(".//entry"))
    return n


def _query_metasearch(surname: str, place: str) -> dict | None:
    """Fragt die CompGen-Metasuche ab und liefert ein Bucket→Anzahl-Dict.

    Rückgabe None signalisiert einen harten Fehler (Netz/Format) → Aufrufer
    fällt auf eine Link-only-Zeile zurück. Ein leeres Dict bedeutet: Abfrage
    erfolgreich, aber keine zuordenbaren Treffer.
    """
    if not surname:
        return None

    params: dict = {"lastname": surname}
    p = _first(place)
    if p:
        params["placename"] = p

    url = _META_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "text/xml, application/xml")

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None
    except Exception:  # pragma: no cover - fail-soft Absicherung
        return None

    if not raw:
        return None

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    except Exception:  # pragma: no cover
        return None

    # Fehler-Element der Schnittstelle → wie harter Fehler behandeln.
    if root.find("error") is not None or root.tag.lower() == "error":
        return None

    counts: dict[str, int] = {}
    # Datenbank-Elemente können direkt unter <result> oder verschachtelt liegen.
    db_elements = root.findall("database") or root.findall(".//database")
    for db_el in db_elements:
        name_el = db_el.find("name")
        db_name = (name_el.text or "").strip() if name_el is not None else ""
        bucket = _classify_db(db_name)
        if bucket is None:
            continue
        n = _count_entries(db_el)
        if n == 0 and db_el.find("more") is not None:
            # Treffer vorhanden, aber gekappt/nicht einzeln gelistet.
            n = 1
        counts[bucket] = counts.get(bucket, 0) + n

    return counts


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_compgen_metasearch(individuals: dict, root_related_ids=None,
                           progress_cb=None,
                           max_persons: int = _MAX_LOOKUPS) -> list:
    """CompGen-/genealogy.net-Metasuche pro Ahn.

    Gibt eine Liste von Zeilen für das Report-Sheet zurück (Spalten siehe
    COMPGEN_METASEARCH_HEADERS). Schreibt NICHTS in individuals zurück.
    Fail-soft: einzelne Fehler erzeugen eine Link-only-Zeile, der Lauf bricht
    nicht ab.
    """
    p = progress_cb or (lambda m, **kw: None)
    p("CompGen-Metasuche: Kandidaten sammeln …")

    scope = root_related_ids or set(individuals.keys())

    # Kandidaten: Name + Nachname vorhanden, nicht zu jung, DACH-plausibel.
    candidates = []
    for pid in scope:
        pdata = individuals.get(pid)
        if not pdata:
            continue

        name_raw = (pdata.get("NAME") or "").strip()
        if not name_raw:
            continue

        _given, surname = _split_name(name_raw)
        if not surname:
            continue

        birt = pdata.get("BIRT") or {}
        by   = _yr(birt)
        if by and by > _MAX_BIRTH_YEAR:
            continue  # Datenschutz: könnte noch leben

        bp = (birt.get("PLAC") or "").strip()
        if not _is_dach(bp):
            continue  # nur DACH-plausible Personen abfragen

        candidates.append((pid, name_raw, surname, by, bp))

    cap = min(len(candidates), max(0, max_persons), _MAX_LOOKUPS)
    p(f"CompGen-Metasuche: {len(candidates):,} Kandidaten, davon {cap} werden "
      f"abgefragt")

    rows = []
    for i, (pid, name_raw, surname, by, bp) in enumerate(candidates[:cap]):
        if i % 15 == 0 and i:
            p(f"  … {i}/{cap} abgefragt, {len(rows)} Zeilen")

        link = _meta_ui_link(surname, bp) or _gedbas_link(surname, bp)
        counts = _query_metasearch(surname, bp)

        if counts is None:
            # Fail-soft: nur den Link, leere Trefferzahlen.
            rows.append([
                pid, name_raw, by or "", _first(bp),
                "", "", "", "", "", "",
                link,
            ])
        else:
            def _c(bucket: str):
                v = counts.get(bucket, 0)
                return v if v else ""
            rows.append([
                pid, name_raw, by or "", _first(bp),
                _c("gedbas"), _c("ofb"), _c("adressbuch"),
                _c("grabstein"), _c("verlustliste"), _c("foko"),
                link,
            ])

        time.sleep(_DELAY_S)

    # Personen mit den meisten Gesamttreffern zuerst (besser erschlossen).
    def _total(r):
        return sum(v for v in r[4:10] if isinstance(v, int))
    rows.sort(key=lambda r: (-_total(r), r[1]))

    p(f"CompGen-Metasuche: {len(rows):,} Personen abgefragt", tag="ok")
    return rows
