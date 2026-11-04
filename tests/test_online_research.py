# -*- coding: utf-8 -*-
"""Tests für tasks/online_research.py – Fehlertoleranz (Scrum Sprint 8, Data Engineer)."""
import tasks.online_research as R


def _indi(iid, given, surname, by):
    return iid, {
        "NAME": f"{given} /{surname}/",
        "BIRT": {"YEAR": by, "DATE": str(by)},
        "DEAT": {},
    }


def test_query_wikidata_handles_non_dict_response(monkeypatch):
    """_get_json() ist dict|list|None typisiert — eine unerwartete Top-Level-
    Liste (statt Dict) durfte keine ungefangene AttributeError werfen."""
    monkeypatch.setattr(R, "_get_json", lambda *a, **kw: ["unexpected", "list"])
    result = R._query_wikidata("Johann", "Schulze", 1850)
    assert result == []


def test_query_wikidata_handles_none_response(monkeypatch):
    monkeypatch.setattr(R, "_get_json", lambda *a, **kw: None)
    assert R._query_wikidata("Johann", "Schulze", 1850) == []


def test_run_online_death_research_survives_candidate_error(monkeypatch):
    """Ein einzelner fehlschlagender Kandidat darf die restliche
    Batch-Recherche nicht abreißen — bereits gesammelte Treffer anderer
    Kandidaten bleiben erhalten."""
    individuals = dict([
        _indi("@I1@", "Johann", "Schulze", 1850),   # löst eine Exception aus
        _indi("@I2@", "Anna", "Müller", 1860),       # liefert einen echten Treffer
    ])

    call_count = {"n": 0}

    def fake_wikidata(given, surname, by):
        call_count["n"] += 1
        if surname == "Schulze":
            raise ValueError("malformed API response")
        return [{"source": "Wikidata", "death_year": 1920,
                 "death_place": "Berlin", "url": "https://example.org"}]

    monkeypatch.setattr(R, "_query_wikidata", fake_wikidata)
    monkeypatch.setattr(R, "_query_gnd", lambda *a, **kw: [])
    monkeypatch.setattr(R, "time", __import__("types").SimpleNamespace(sleep=lambda s: None))

    rows = R.run_online_death_research(individuals, {})

    assert call_count["n"] == 2          # beide Kandidaten wurden versucht
    assert len(rows) == 1                # nur der erfolgreiche Treffer blieb erhalten
    assert rows[0][0] == "@I2@"
