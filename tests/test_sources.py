# -*- coding: utf-8 -*-
"""Tests für tasks/sources.py – Quellen-Analyse (SOUR-Records + Inline-Zitate)."""
import os

import pytest

from tasks.sources import analyze_sources, parse_sources


@pytest.fixture
def ged(tmp_path):
    def _write(content: str) -> str:
        p = tmp_path / "test.ged"
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _write


def test_pointer_citation_counted(ged):
    """Klassischer @...@-Verweis auf einen SOUR-Record wird gezählt."""
    path = ged(
        "0 HEAD\n1 GEDC\n2 VERS 5.5\n"
        "0 @S1@ SOUR\n1 TITL Kirchenbuch\n"
        "0 @I1@ INDI\n1 NAME Anna /Müller/\n1 SOUR @S1@\n"
        "0 TRLR\n"
    )
    sources, indi_citations, _fam = parse_sources(path)
    assert "@S1@" in sources
    assert sources["@S1@"]["citations"] == 1
    assert indi_citations["@I1@"] == {"@S1@"}


def test_inline_free_text_citation_counted():
    """Scrum Sprint 8 (Archivar): Inline-Freitext-Zitat ohne SOUR-Record
    (nach GEDCOM 5.5.1 ebenfalls gültig, u. a. von Ancestry-/Legacy-Exporten
    genutzt) wurde vorher komplett ignoriert — die Person galt fälschlich
    als unbelegt."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".ged")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "0 HEAD\n1 GEDC\n2 VERS 5.5\n"
                "0 @I1@ INDI\n1 NAME Anna /Müller/\n"
                "1 SOUR Mündliche Überlieferung der Familie\n"
                "0 TRLR\n"
            )
        sources, indi_citations, _fam = parse_sources(path)
        assert indi_citations.get("@I1@"), \
            "Inline-Zitat muss als Quellenverweis für @I1@ gezählt werden"
        src_id = next(iter(indi_citations["@I1@"]))
        assert sources[src_id]["citations"] == 1
        assert "Mündliche Überlieferung" in sources[src_id]["title"]
    finally:
        os.unlink(path)


def test_inline_citation_person_not_classified_as_unsourced():
    """Eine Person mit NUR einem Inline-Zitat darf analyze_sources() nicht
    als 'Keine Quelle' einstufen."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".ged")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "0 HEAD\n1 GEDC\n2 VERS 5.5\n"
                "0 @I1@ INDI\n1 NAME Anna /Müller/\n1 BIRT\n2 DATE 1850\n"
                "1 SOUR Familienbibel\n"
                "0 TRLR\n"
            )
        individuals = {"@I1@": {"NAME": "Anna /Müller/",
                                 "BIRT": {"YEAR": 1850, "DATE": "1850"}}}
        _inv, quality = analyze_sources(individuals, {}, path)
        row = next(r for r in quality if r[0] == "@I1@")
        assert row[3] == 1          # Quellen-Anzahl
        assert row[4] != "Keine Quelle"
    finally:
        os.unlink(path)


def test_no_sour_at_all_still_unsourced(ged):
    """Regressionsschutz: eine Person ganz ohne SOUR-Tag bleibt 'Keine Quelle'."""
    path = ged(
        "0 HEAD\n1 GEDC\n2 VERS 5.5\n"
        "0 @I1@ INDI\n1 NAME Hans /Schmidt/\n"
        "0 TRLR\n"
    )
    individuals = {"@I1@": {"NAME": "Hans /Schmidt/", "BIRT": {}}}
    _inv, quality = analyze_sources(individuals, {}, path)
    assert quality == [] or quality[0][4] == "Keine Quelle"
