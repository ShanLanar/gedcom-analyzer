"""Tests für den Ancestry-API-Client (ancestry.core.api) mit Mock-HTTP.

Das Kernstück der DNA-Downloads (_session/_matches/_pedigree) war bisher
ungetestet. Hier wird OHNE echtes Netz getestet:

- pure Helfer in _session (Jitter, UBE-Header, Initialen-Erkennung, JSON-Parse,
  CSRF-Form, JWT-Restlaufzeit, _api_get-Retry/Abbruch),
- die Client-Methoden über AncestryApiClient mit gefälschter Session und
  gepatchtem _api_get (DNA-Kits, Match-Count, iter_matches, Shared Matches,
  Notiz speichern),
- die reine _tree_status-Logik aus dem Pedigree-Mixin.
"""
import base64
import json
import time

import pytest

import ancestry.core.api._matches as matches_mod
from ancestry.core.api import (
    AncestryApiClient,
    _build_ube_header,
    _is_initials_only,
    _jitter,
)
from ancestry.core.api import _session as session_mod


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeCookies:
    def __init__(self, store=None):
        self._store = store or {}

    def get(self, name, domain=None):  # domain wird ignoriert
        return self._store.get(name)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text="",
                 raise_json=False):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {"Content-Type": "application/json"}
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("kein JSON")
        return self._json


class FakeSession:
    """Minimaler Ersatz für die curl_cffi/requests-Session."""

    def __init__(self, cookies=None):
        self.cookies = FakeCookies(cookies)
        self.get_calls = []
        self.put_calls = []
        self._get_response = FakeResponse()
        self._put_response = FakeResponse(status_code=200)

    def get(self, url, **kw):
        self.get_calls.append((url, kw))
        return self._get_response

    def put(self, url, **kw):
        self.put_calls.append((url, kw))
        return self._put_response


def make_client(cookies=None):
    return AncestryApiClient(FakeSession(cookies))


# ── _session: pure Helfer ─────────────────────────────────────────────────────

def test_is_initials_only():
    assert _is_initials_only("L. S.")
    assert _is_initials_only("K. F.")
    assert _is_initials_only("A.")
    assert not _is_initials_only("Hans Müller")
    assert not _is_initials_only("Anna")


def test_jitter_within_range():
    for _ in range(200):
        v = _jitter(100.0)
        assert 80.0 <= v <= 120.0


def test_build_ube_header_is_valid_base64_json():
    sess = FakeSession({"ANCSESSIONID": "sess-123"})
    header = _build_ube_header(sess)
    decoded = json.loads(base64.b64decode(header))
    assert decoded["correlatedSessionId"] == "sess-123"
    assert "screenName" in decoded


def test_parse_json_variants():
    parse = AncestryApiClient._parse_json
    assert parse(None, "x") is None
    assert parse(FakeResponse(status_code=500), "x") is None
    html = FakeResponse(headers={"Content-Type": "text/html"}, json_data={"a": 1})
    assert parse(html, "x") is None
    ok = FakeResponse(json_data={"a": 1})
    assert parse(ok, "x") == {"a": 1}
    bad = FakeResponse(raise_json=True)
    assert parse(bad, "x") is None


def test_csrf_value_modes():
    c = make_client({"_dnamatches-matchlistui-x-csrf-token": "tok%7Csig"})
    assert c._csrf_value("raw") == "tok%7Csig"
    assert c._csrf_value("decoded") == "tok|sig"
    assert c._csrf_value("prefix") == "tok"
    assert c._csrf_value("none") == ""


def test_jwt_remaining():
    # JWT mit exp weit in der Zukunft → positive Restlaufzeit
    future = int(time.time()) + 3600
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": future}).encode()).decode().rstrip("=")
    jwt = "header." + payload + ".sig"
    c = make_client({"SecureATT": jwt})
    assert c._jwt_remaining() > 3000

    # kein Cookie → 0
    assert make_client({})._jwt_remaining() == 0


def test_api_get_returns_on_200(monkeypatch):
    monkeypatch.setattr(session_mod.time, "sleep", lambda *_: None)
    sess = FakeSession()
    sess._get_response = FakeResponse(status_code=200, json_data={"ok": True})
    r = session_mod._api_get(sess, "https://x/y")
    assert r.status_code == 200


def test_api_get_no_retry_on_401(monkeypatch):
    # 401 ist KEIN Retry-Status → kommt direkt zurück, nur ein einziger GET
    monkeypatch.setattr(session_mod.time, "sleep", lambda *_: None)
    sess = FakeSession()
    sess._get_response = FakeResponse(status_code=401)
    r = session_mod._api_get(sess, "https://x/y")
    assert r.status_code == 401
    assert len(sess.get_calls) == 1


def test_api_get_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(session_mod.time, "sleep", lambda *_: None)
    sess = FakeSession()
    sess._get_response = FakeResponse(status_code=503)  # immer Retry-Status
    r = session_mod._api_get(sess, "https://x/y")
    assert r is None
    assert len(sess.get_calls) == session_mod.MAX_RETRIES


# ── _matches: Client-Methoden mit gepatchtem _api_get ─────────────────────────

def patch_api_get(monkeypatch, dispatcher):
    """Ersetzt _api_get im _matches-Modul durch einen URL-Dispatcher."""
    monkeypatch.setattr(matches_mod, "_api_get",
                        lambda session, url, *a, **kw: dispatcher(url))


def test_get_dna_kits_list_form(monkeypatch):
    data = [{"testGuid": "G1", "displayName": "Oma"},
            {"guid": "G2", "name": "Opa"}]
    patch_api_get(monkeypatch, lambda url: FakeResponse(json_data=data))
    kits = make_client().get_dna_kits("uid")
    assert [k.guid for k in kits] == ["G1", "G2"]
    assert kits[0].name == "Oma"


def test_get_dna_kits_dict_form(monkeypatch):
    data = {"kits": [{"testGuid": "G9", "displayName": "X"}]}
    patch_api_get(monkeypatch, lambda url: FakeResponse(json_data=data))
    kits = make_client().get_dna_kits("uid")
    assert len(kits) == 1 and kits[0].guid == "G9"


def test_get_dna_kits_handles_error(monkeypatch):
    patch_api_get(monkeypatch, lambda url: FakeResponse(status_code=500))
    assert make_client().get_dna_kits("uid") == []


def test_detect_kit_from_uid(monkeypatch):
    data = [{"testGuid": "FIRST"}, {"testGuid": "SECOND"}]
    patch_api_get(monkeypatch, lambda url: FakeResponse(json_data=data))
    assert make_client().detect_kit_from_uid("uid") == "FIRST"


def test_get_match_count_variants(monkeypatch):
    patch_api_get(monkeypatch, lambda url: FakeResponse(json_data=42))
    assert make_client().get_match_count("g") == 42

    patch_api_get(monkeypatch, lambda url: FakeResponse(json_data={"count": 7}))
    assert make_client().get_match_count("g") == 7

    patch_api_get(monkeypatch, lambda url: FakeResponse(json_data={"totalCount": 9}))
    assert make_client().get_match_count("g") == 9

    patch_api_get(monkeypatch, lambda url: FakeResponse(status_code=404))
    assert make_client().get_match_count("g") == 0


def test_iter_matches_single_page(monkeypatch):
    page = {
        "totalPages": 1,
        "matchList": [
            {"sampleId": "AAA", "relationship": {"sharedCentimorgans": 200}},
            {"sampleId": "BBB", "relationship": {"sharedCentimorgans": 50}},
        ],
    }

    def dispatch(url):
        if "matchCount" in url:
            return FakeResponse(json_data=2)
        return FakeResponse(json_data=page)

    monkeypatch.setattr(matches_mod.time, "sleep", lambda *_: None)
    patch_api_get(monkeypatch, dispatch)
    c = make_client()
    guids = [m.match_guid for m in c.iter_matches("g")]
    assert guids == ["AAA", "BBB"]


def test_iter_shared_matches_filters_self_and_stops(monkeypatch):
    page = {
        "totalPages": 1,
        "isLastPage": True,
        "matchList": [
            {"sampleId": "SELF"},                 # == match_guid_a → übersprungen
            {"sampleId": "OTHER",
             "relationship": {"sharedCentimorgans": 30}},
        ],
    }
    monkeypatch.setattr(matches_mod.time, "sleep", lambda *_: None)
    patch_api_get(monkeypatch, lambda url: FakeResponse(json_data=page))
    c = make_client()
    res = list(c.iter_shared_matches("g", "SELF"))
    assert [s.match_guid_b for s in res] == ["OTHER"]


def test_iter_shared_matches_stops_on_403(monkeypatch):
    monkeypatch.setattr(matches_mod.time, "sleep", lambda *_: None)
    patch_api_get(monkeypatch, lambda url: FakeResponse(status_code=403))
    assert list(make_client().iter_shared_matches("g", "A")) == []


def test_save_match_note(monkeypatch):
    c = make_client()
    c._s._put_response = FakeResponse(status_code=204)
    assert c.save_match_note("g", "m", "Notiz") is True
    c._s._put_response = FakeResponse(status_code=500)
    assert c.save_match_note("g", "m", "Notiz") is False


# ── _pedigree: reine Logik ────────────────────────────────────────────────────

def test_tree_status_classification():
    ts = AncestryApiClient._tree_status
    assert ts({"hasNoTrees": True})["has_tree"] is False
    assert ts({"isPrivateTree": True, "treeSize": 5}) == {
        "tree_status": "Privat", "tree_size": 5, "has_tree": True}
    assert ts({"isPublicTree": True, "treeSize": 99})["has_tree"] is True
    assert ts({"isUnlinkedTree": True})["tree_status"] == "Unverknüpft"
    assert ts({})["tree_status"] == ""
