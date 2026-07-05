"""
FamilySearch-OAuth-2.0-Client (Grundgerüst) + Record-Normalisierung.

FamilySearch bietet eine kostenlose API (Developer-Account nötig) mit weltweiten
Kirchenbuch-/Census-Records und dem Family Tree. Bisher generierte
tasks/familysearch.py nur Suchlinks — hier kommt der echte Datenzugriff.

Der HTTP-Transport ist injizierbar (``transport``), damit Token-Austausch und
Requests OHNE Live-Netz getestet werden können. Der OAuth-Consent-Schritt
(Authorization-Code) erfordert einen Browser/Redirect und wird über
``authorize_url()`` vorbereitet; ``exchange_code()`` tauscht den Code gegen ein
Access-Token.

Normalisierung: ``person_to_dict()`` bildet eine FamilySearch-Person auf das
Schema von ``import_external_persons`` ab (source='familysearch').
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)
_YEAR_RE = re.compile(r"\b(1[0-9]{3}|2[01]\d{2})\b")

# Standard-Endpunkte (Produktions-Umgebung)
IDENT_BASE = "https://ident.familysearch.org/cis-web/oauth2/v3"
API_BASE = "https://api.familysearch.org"


def _default_transport(method: str, url: str, headers: dict,
                       data: bytes | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


class FamilySearchClient:
    def __init__(self, client_id: str, redirect_uri: str,
                 ident_base: str = IDENT_BASE, api_base: str = API_BASE,
                 transport=None):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.ident_base = ident_base.rstrip("/")
        self.api_base = api_base.rstrip("/")
        self._transport = transport or _default_transport
        self.access_token: str | None = None

    # ── OAuth ──────────────────────────────────────────────────────────────────

    def authorize_url(self, state: str = "") -> str:
        """Consent-URL, die der Nutzer im Browser öffnet."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        if state:
            params["state"] = state
        return f"{self.ident_base}/authorization?" + urllib.parse.urlencode(params)

    def exchange_code(self, code: str) -> str:
        """Authorization-Code gegen Access-Token tauschen. Gibt das Token zurück."""
        data = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }).encode()
        resp = self._transport(
            "POST", f"{self.ident_base}/token",
            {"Content-Type": "application/x-www-form-urlencoded"}, data)
        self.access_token = resp.get("access_token")
        if not self.access_token:
            # Kein vollständiges resp loggen (kann error_description/Korrelations-
            # IDs enthalten) — nur den Fehlercode.
            raise RuntimeError(
                f"Token-Austausch fehlgeschlagen (error={resp.get('error') or '?'})")
        return self.access_token

    # ── API ────────────────────────────────────────────────────────────────────

    def _get(self, path: str) -> dict:
        if not self.access_token:
            raise RuntimeError("Nicht authentifiziert – erst exchange_code() aufrufen.")
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        return self._transport("GET", url, {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        })

    def get_person(self, person_id: str) -> dict:
        """Family-Tree-Person als rohes FS-JSON (persons[0]). {} bei HTTP-Fehler."""
        if not self.access_token:
            raise RuntimeError("Nicht authentifiziert – erst exchange_code() aufrufen.")
        try:
            data = self._get(f"/platform/tree/persons/{person_id}")
        except Exception as e:
            log.warning("FamilySearch get_person(%s): %s", person_id, e)
            return {}
        persons = data.get("persons") or []
        return persons[0] if persons else {}

    def search_persons(self, given: str = "", surname: str = "",
                       birth_year: int | None = None) -> list[dict]:
        """Personensuche; gibt normalisierte Dicts (import-fähig) zurück.
        Fail-soft: bei HTTP-Fehler (401/429/5xx) leere Liste statt Abbruch."""
        if not self.access_token:
            raise RuntimeError("Nicht authentifiziert – erst exchange_code() aufrufen.")
        q_parts = []
        if given:
            q_parts.append(f'givenName:"{given}"')
        if surname:
            q_parts.append(f'surname:"{surname}"')
        if birth_year:
            q_parts.append(f"birthLikeDate:from {birth_year - 2} to {birth_year + 2}")
        query = urllib.parse.urlencode({"q": " ".join(q_parts)})
        try:
            data = self._get(f"/platform/tree/search?{query}")
        except Exception as e:
            log.warning("FamilySearch search_persons: %s", e)
            return []
        entries = (data.get("entries") or [])
        out = []
        for e in entries:
            content = (e.get("content") or {}).get("gedcomx") or {}
            for p in content.get("persons") or []:
                out.append(person_to_dict(p))
        return [d for d in out if d.get("ext_id")]


# ── Normalisierung FS-Person → import_external_persons-Schema ──────────────────

def _fact_value(person: dict, fact_type: str, field: str) -> str:
    for f in person.get("facts") or []:
        if (f.get("type") or "").endswith(fact_type):
            node = f.get(field) or {}
            return (node.get("original") or "").strip()
    return ""


def person_to_dict(person: dict) -> dict:
    """FamilySearch-Person (GEDCOM-X-JSON) → Import-Dict.

    Erwartet Felder: ``id``, ``names[].nameForms[].parts[{type,value}]``,
    ``gender.type``, ``facts[]`` mit BIRTH/DEATH und ``date``/``place``.
    """
    given = surname = ""
    for name in person.get("names") or []:
        for form in name.get("nameForms") or []:
            for part in form.get("parts") or []:
                t = (part.get("type") or "").rsplit("/", 1)[-1].lower()
                val = (part.get("value") or "").strip()
                if t == "given" and not given:
                    given = val
                elif t == "surname" and not surname:
                    surname = val
            if given or surname:
                break
        if given or surname:
            break

    gender = (person.get("gender") or {}).get("type") or ""
    sex = "M" if gender.endswith("Male") else ("F" if gender.endswith("Female") else "")

    def _year(fact_type: str):
        raw = _fact_value(person, fact_type, "date")
        m = _YEAR_RE.search(raw)
        return int(m.group(1)) if m else None

    return {
        "ext_id":      str(person.get("id") or "").strip(),
        "given_name":  given,
        "surname":     surname,
        "sex":         sex,
        "birth_year":  _year("Birth"),
        "birth_place": _fact_value(person, "Birth", "place"),
        "death_year":  _year("Death"),
        "death_place": _fact_value(person, "Death", "place"),
    }
