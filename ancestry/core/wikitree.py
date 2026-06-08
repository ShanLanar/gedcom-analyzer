"""
wikitree.py — Client für die öffentliche WikiTree-API (api.wikitree.com).

WikiTree ist ein kollaborativer Ein-Baum-Stammbaum. Die API ist für
öffentliche Profile **ohne Login und ohne API-Key** nutzbar. Nutzen für
dieses Tool: Vorfahren eines DNA-Matches (oder eigene Lücken) automatisch
verlängern, indem wir nach Nachname + Geburtsort + Jahr suchen und die
Ahnenlinie eines Treffers abrufen.

Wichtig: WikiTree verlangt einen aussagekräftigen User-Agent. Private
Profile liefern nur eingeschränkte Felder ohne Login — das ist ok, wir
arbeiten mit den öffentlichen.

Hinweis: In gekapselten Build-/CI-Umgebungen ohne Internet schlägt jeder
Aufruf fehl (z.B. HTTP 403 vom Proxy). Der Client ist für die lokale
Ausführung gedacht, wo das Tool läuft.

CLI-Test (lokal):
    python wikitree.py search Albert Einstein 1879
    python wikitree.py ancestors Einstein-1 4
"""
from __future__ import annotations
import json
import sys
import time
import logging
from urllib import request, parse
from urllib.error import HTTPError, URLError

log = logging.getLogger(__name__)

API_URL    = "https://api.wikitree.com/api.php"
USER_AGENT = "gedcom-analyzer/1.0 (genealogy DNA tool; contact via app)"

# Standard-Felder für Personenprofile
PROFILE_FIELDS = (
    "Id,Name,FirstName,MiddleName,LastNameAtBirth,LastNameCurrent,"
    "BirthDate,DeathDate,BirthLocation,DeathLocation,Gender,"
    "Father,Mother,Manager,IsLiving"
)


class WikiTreeError(RuntimeError):
    pass


def _post(params: dict, retries: int = 2, timeout: int = 20) -> object:
    """POST an die WikiTree-API. Gibt das geparste JSON zurück."""
    params = {**params, "format": "json"}
    body = parse.urlencode(params).encode("utf-8")
    last = None
    for attempt in range(retries + 1):
        try:
            req = request.Request(API_URL, data=body, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            with request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as e:
            last = e
            if attempt < retries:
                time.sleep(2 ** attempt)
            continue
    raise WikiTreeError(f"WikiTree-Anfrage fehlgeschlagen: {last}")


# ── Öffentliche Funktionen ──────────────────────────────────────────────────

def search_person(first_name: str = "", last_name: str = "",
                  birth_date: str = "", death_date: str = "",
                  birth_location: str = "", limit: int = 10) -> list[dict]:
    """Personensuche. birth_date als Jahr 'YYYY' oder vollständiges Datum.

    Gibt eine Liste von Profil-Dicts zurück (kann leer sein).
    """
    params = {"action": "searchPerson", "fields": PROFILE_FIELDS, "limit": str(limit)}
    if first_name:     params["FirstName"]     = first_name
    if last_name:      params["LastName"]       = last_name
    if birth_date:     params["BirthDate"]      = birth_date
    if death_date:     params["DeathDate"]      = death_date
    if birth_location: params["BirthLocation"]  = birth_location

    data = _post(params)
    try:
        block = data[0]
    except (IndexError, KeyError, TypeError):
        return []
    matches = block.get("matches") or []
    # searchPerson liefert manchmal nur Keys -> Profile separat nachladen
    out = []
    for m in matches:
        if isinstance(m, dict) and m.get("Name"):
            out.append(m)
        elif isinstance(m, dict) and m.get("user_name"):
            out.append(m)
    return out


def get_profile(key: str, fields: str = PROFILE_FIELDS) -> dict | None:
    """Einzelnes Profil per WikiTree-ID (z.B. 'Einstein-1') oder User-ID."""
    data = _post({"action": "getProfile", "key": key, "fields": fields})
    try:
        prof = data[0].get("profile")
        return prof if prof else None
    except (IndexError, KeyError, TypeError):
        return None


def get_ancestors(key: str, depth: int = 4,
                  fields: str = PROFILE_FIELDS) -> list[dict]:
    """Ahnenlinie eines Profils bis `depth` Generationen (max. 10 lt. API)."""
    depth = max(1, min(int(depth), 10))
    data = _post({"action": "getAncestors", "key": key,
                  "depth": str(depth), "fields": fields})
    try:
        anc = data[0].get("ancestors") or []
    except (IndexError, KeyError, TypeError):
        return []
    return [a for a in anc if isinstance(a, dict)]


# ── Komfort: Vorfahren-Kandidaten für einen Match-Ahnen finden ───────────────

def _year(s: str) -> str:
    """Extrahiert ein vierstelliges Jahr aus einem Datums-/Ortsstring."""
    import re
    m = re.search(r"\b(1[0-9]{3}|20[0-2][0-9])\b", s or "")
    return m.group(1) if m else ""


def find_ancestor_lineage(surname: str, birth_place: str = "",
                          birth_year: str | int = "",
                          first_name: str = "", depth: int = 4) -> dict:
    """Sucht den besten WikiTree-Treffer für einen (Match-)Ahnen und gibt
    seine Ahnenlinie zurück.

    Rückgabe:
        {"query": {...}, "best": <profile|None>, "candidates": [...],
         "lineage": [<ancestor profiles>]}
    """
    by = str(birth_year) if birth_year else _year(birth_place)
    candidates = search_person(first_name=first_name, last_name=surname,
                               birth_date=by, birth_location=birth_place,
                               limit=10)
    result = {"query": {"surname": surname, "birth_place": birth_place,
                        "birth_year": by, "first_name": first_name},
              "best": None, "candidates": candidates, "lineage": []}
    if not candidates:
        return result

    # Bestbewertung: Ort-Übereinstimmung + Jahr-Nähe
    def score(p: dict) -> float:
        s = 0.0
        loc = (p.get("BirthLocation") or "").lower()
        if birth_place:
            for tok in birth_place.lower().replace(",", " ").split():
                if len(tok) > 3 and tok in loc:
                    s += 1.0
        py = _year(p.get("BirthDate") or "")
        if by and py:
            s += max(0.0, 1.0 - abs(int(py) - int(by)) / 20.0)
        return s

    best = max(candidates, key=score)
    result["best"] = best
    key = best.get("Name")
    if key:
        result["lineage"] = get_ancestors(key, depth=depth)
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def _main(argv: list[str]):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(argv) < 2:
        print(__doc__)
        return
    cmd = argv[1]
    try:
        if cmd == "search":
            first = argv[2] if len(argv) > 2 else ""
            last  = argv[3] if len(argv) > 3 else ""
            year  = argv[4] if len(argv) > 4 else ""
            res = search_person(first_name=first, last_name=last, birth_date=year)
            print(f"{len(res)} Treffer:")
            for p in res:
                print(f"  {p.get('Name','?'):20} {p.get('FirstName','')} "
                      f"{p.get('LastNameAtBirth','')}  "
                      f"* {p.get('BirthDate','?')} {p.get('BirthLocation','')}")
        elif cmd == "ancestors":
            key   = argv[2]
            depth = int(argv[3]) if len(argv) > 3 else 4
            res = get_ancestors(key, depth=depth)
            print(f"{len(res)} Vorfahren von {key}:")
            for p in res:
                print(f"  {p.get('FirstName','')} {p.get('LastNameAtBirth','')}  "
                      f"* {p.get('BirthDate','?')} {p.get('BirthLocation','')}")
        elif cmd == "lineage":
            surname = argv[2]
            place   = argv[3] if len(argv) > 3 else ""
            year    = argv[4] if len(argv) > 4 else ""
            res = find_ancestor_lineage(surname, place, year)
            best = res["best"]
            print(f"Bester Treffer: {best.get('Name') if best else '—'}")
            print(f"Ahnenlinie: {len(res['lineage'])} Personen")
        else:
            print(f"Unbekannter Befehl: {cmd}")
    except WikiTreeError as e:
        print(f"FEHLER: {e}")


if __name__ == "__main__":
    _main(sys.argv)
