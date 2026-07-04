"""Tests für den FamilySearch-OAuth-Client + Record-Normalisierung.

Der HTTP-Transport wird gemockt — kein Live-Netz, keine Credentials nötig.
"""
import pytest

from ancestry.core.api.familysearch_client import (
    FamilySearchClient, person_to_dict,
)


# ── Beispiel-FS-Person (GEDCOM-X) ─────────────────────────────────────────────

_FS_PERSON = {
    "id": "L123-ABC",
    "gender": {"type": "http://gedcomx.org/Male"},
    "names": [{
        "nameForms": [{
            "parts": [
                {"type": "http://gedcomx.org/Given",   "value": "Johann Heinrich"},
                {"type": "http://gedcomx.org/Surname", "value": "Kovermann"},
            ]
        }]
    }],
    "facts": [
        {"type": "http://gedcomx.org/Birth",
         "date":  {"original": "12 March 1823"},
         "place": {"original": "Damme, Oldenburg"}},
        {"type": "http://gedcomx.org/Death",
         "date":  {"original": "1889"},
         "place": {"original": "Osnabrück"}},
    ],
}


def test_person_to_dict_full():
    d = person_to_dict(_FS_PERSON)
    assert d["ext_id"] == "L123-ABC"
    assert d["given_name"] == "Johann Heinrich"
    assert d["surname"] == "Kovermann"
    assert d["sex"] == "M"
    assert d["birth_year"] == 1823
    assert d["birth_place"] == "Damme, Oldenburg"
    assert d["death_year"] == 1889
    assert d["death_place"] == "Osnabrück"


def test_person_to_dict_minimal():
    d = person_to_dict({"id": "X1"})
    assert d["ext_id"] == "X1"
    assert d["given_name"] == "" and d["surname"] == ""
    assert d["birth_year"] is None


def test_authorize_url_contains_params():
    c = FamilySearchClient("my-client", "http://localhost/cb")
    url = c.authorize_url(state="xyz")
    assert "response_type=code" in url
    assert "client_id=my-client" in url
    assert "state=xyz" in url
    assert url.startswith("https://ident.familysearch.org")


def test_exchange_code_sets_token():
    calls = {}

    def fake_transport(method, url, headers, data=None):
        calls["method"] = method
        calls["url"] = url
        return {"access_token": "TOKEN-42", "token_type": "Bearer"}

    c = FamilySearchClient("cid", "http://cb", transport=fake_transport)
    tok = c.exchange_code("auth-code-1")
    assert tok == "TOKEN-42"
    assert c.access_token == "TOKEN-42"
    assert calls["method"] == "POST"
    assert calls["url"].endswith("/token")


def test_exchange_code_missing_token_raises():
    c = FamilySearchClient("cid", "http://cb",
                           transport=lambda *a, **k: {"error": "bad"})
    with pytest.raises(RuntimeError):
        c.exchange_code("x")


def test_get_person_requires_auth():
    c = FamilySearchClient("cid", "http://cb", transport=lambda *a, **k: {})
    with pytest.raises(RuntimeError):
        c.get_person("L1")


def test_get_person_returns_first():
    def fake(method, url, headers, data=None):
        assert headers.get("Authorization") == "Bearer T"
        return {"persons": [_FS_PERSON]}

    c = FamilySearchClient("cid", "http://cb", transport=fake)
    c.access_token = "T"
    p = c.get_person("L123-ABC")
    assert p["id"] == "L123-ABC"


def test_search_persons_normalizes():
    def fake(method, url, headers, data=None):
        return {"entries": [
            {"content": {"gedcomx": {"persons": [_FS_PERSON]}}}
        ]}

    c = FamilySearchClient("cid", "http://cb", transport=fake)
    c.access_token = "T"
    results = c.search_persons(surname="Kovermann", birth_year=1823)
    assert len(results) == 1
    assert results[0]["surname"] == "Kovermann"
