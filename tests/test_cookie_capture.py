"""Tests für ancestry/core/cookie_capture.py — Cookie-Datei-Erzeugung.

Fokus: _save_cookies normalisiert korrekt UND setzt restriktive Datei-
rechte (0600), da die Datei Session-Cookies im Klartext enthält und auf
Mehrbenutzersystemen sonst für andere lokale Nutzer lesbar wäre
(Scrum-Gremium-Fund, Datenschutzjurist-Perspektive).
"""
import json
import os
import stat
import tempfile

import pytest

from ancestry.core.cookie_capture import _save_cookies


@pytest.fixture
def tmp_path_str():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)  # _save_cookies soll die Datei selbst anlegen
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_save_cookies_normalises_fields(tmp_path_str):
    _save_cookies(
        [{"name": "session", "value": "abc123", "domain": ".ancestry.com",
          "path": "/", "extra_field_to_drop": "x"}],
        tmp_path_str,
    )
    data = json.loads(open(tmp_path_str, encoding="utf-8").read())
    assert data == [{"name": "session", "value": "abc123",
                     "domain": ".ancestry.com", "path": "/"}]


def test_save_cookies_drops_entries_without_name_or_value(tmp_path_str):
    _save_cookies(
        [{"name": "", "value": "x"}, {"name": "ok", "value": ""},
         {"name": "keep", "value": "v"}],
        tmp_path_str,
    )
    data = json.loads(open(tmp_path_str, encoding="utf-8").read())
    assert [c["name"] for c in data] == ["keep"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX-Dateirechte gelten nicht unter Windows")
def test_save_cookies_sets_owner_only_permissions(tmp_path_str):
    _save_cookies([{"name": "session", "value": "abc123"}], tmp_path_str)
    mode = stat.S_IMODE(os.stat(tmp_path_str).st_mode)
    assert mode == 0o600
