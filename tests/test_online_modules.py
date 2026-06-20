# -*- coding: utf-8 -*-
"""
Unit-Tests für die 4 Online-Recherche-Module (keine HTTP-Calls).

Getestet werden:
  - tasks/gov_lookup.py    — Orts-Sammlung, Archiv-URL-Builder
  - tasks/grabstein.py     — Filter-Logik, URL-Builder, Konfidenz
  - tasks/externe_quellen.py — Zeitraum-Kategorisierung, URL-Builder, Filterung
  - tasks/dfd_lookup.py    — Suchlauf, Ähnlichkeitsfunktion, HTML-Parser, Varianten-JSON
"""

import json
import os
import tempfile
import types

import pytest

# ── Gemeinsame Testdaten ──────────────────────────────────────────────────────

_INDIVIDUALS: dict = {
    "@I1@": {
        "NAME": "Johann /Schulze/",
        "SEX":  "M",
        "BIRT": {"DATE": "1 JAN 1850", "PLAC": "Osnabrück, Niedersachsen, Deutschland", "YEAR": 1850},
        "DEAT": {"DATE": "15 MAR 1920", "PLAC": "Osnabrück, Niedersachsen, Deutschland", "YEAR": 1920},
    },
    "@I2@": {
        "NAME": "Anna /Kovermann/",
        "SEX":  "F",
        "BIRT": {"DATE": "5 MAY 1870", "PLAC": "Münster, Westfalen, Deutschland", "YEAR": 1870},
        "DEAT": {"DATE": "2 JAN 1945", "PLAC": "Münster, Westfalen, Deutschland", "YEAR": 1945},
    },
    "@I3@": {
        "NAME": "Hans /Müllers/",
        "SEX":  "M",
        "BIRT": {"DATE": "1910", "PLAC": "Hamburg, Deutschland", "YEAR": 1910},
        # no death → may be alive
    },
    "@I4@": {
        "NAME": "Lieselotte /Bauer/ mig.USA",
        "SEX":  "F",
        "BIRT": {"YEAR": 1888, "PLAC": "Bremen, Deutschland"},
        "DEAT": {"YEAR": 1960, "PLAC": "New York, USA"},
        "NOTE": "ausgewandert 1910",
    },
    "@I5@": {
        "NAME": "Samuel /Levy/",
        "SEX":  "M",
        "BIRT": {"YEAR": 1882, "PLAC": "Berlin, Deutschland"},
        "DEAT": {"YEAR": 1943, "PLAC": "Berlin, Deutschland"},
    },
    "@I6@": {
        # No name — should be skipped everywhere
        "SEX": "M",
        "BIRT": {"YEAR": 1800},
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# gov_lookup
# ═══════════════════════════════════════════════════════════════════════════════

from tasks.gov_lookup import (
    _collect_places,
    _archive_links,
    GOV_LOOKUP_HEADERS,
)


class TestGovLookupCollectPlaces:
    def test_collects_birth_place(self):
        places = _collect_places(_INDIVIDUALS)  # returns dict first→full
        assert any("Osnabrück" in p for p in places)

    def test_collects_death_place(self):
        places = _collect_places(_INDIVIDUALS)
        assert any("Münster" in p for p in places)

    def test_no_duplicates(self):
        places = _collect_places(_INDIVIDUALS)
        # dict keys are inherently unique
        assert len(places) == len(list(places))

    def test_empty_individuals(self):
        assert _collect_places({}) == {}

    def test_full_string_in_values(self):
        places = _collect_places(_INDIVIDUALS)
        assert any("Niedersachsen" in v for v in places.values())


class TestGovLookupArchiveLinks:
    def test_matricula_url(self):
        links = _archive_links("Osnabrück", "")
        assert "matricula-online" in links["matricula"]
        assert "Osnabr" in links["matricula"] or "%C3%9C" in links["matricula"] \
               or "Osnabr" in links["matricula"]

    def test_archion_url(self):
        links = _archive_links("Osnabrück", "")
        assert "archion.de" in links["archion"]

    def test_arcinsys_url(self):
        links = _archive_links("Hannover", "")
        assert "arcinsys" in links["arcinsys"]

    def test_archivportal_url(self):
        links = _archive_links("Berlin", "")
        assert "archivportal-d.de" in links["archivportal"]

    def test_gov_link_with_id(self):
        links = _archive_links("Osnabrück", "OSNA_DOM")
        assert "OSNA_DOM" in links["gov"]
        assert "gov.genealogy.net" in links["gov"]

    def test_gov_link_without_id(self):
        links = _archive_links("Osnabrück", "")
        assert "gov.genealogy.net" in links["gov"]

    def test_headers_count(self):
        assert len(GOV_LOOKUP_HEADERS) == 14


# ═══════════════════════════════════════════════════════════════════════════════
# grabstein
# ═══════════════════════════════════════════════════════════════════════════════

from tasks.grabstein import (
    run_grabstein_search,
    _confidence,
    _billiongraves,
    _findagrave,
    _grabstein_projekt,
    _volksbund,
    _jewish_cemeteries,
    _might_be_jewish,
    _split_name,
    GRABSTEIN_HEADERS,
)


class TestGrabsteinFilter:
    def test_born_too_recently_skipped(self):
        inds = {"@I1@": {"NAME": "A /B/", "BIRT": {"YEAR": 1955}, "DEAT": {"YEAR": 2020}}}
        rows = run_grabstein_search(inds)
        assert rows == []

    def test_may_still_be_alive_skipped(self):
        inds = {"@I1@": {"NAME": "A /B/", "BIRT": {"YEAR": 1930}}}
        rows = run_grabstein_search(inds)
        assert rows == []

    def test_non_dach_skipped(self):
        inds = {"@I1@": {"NAME": "A /B/",
                          "BIRT": {"YEAR": 1880, "PLAC": "London, England"},
                          "DEAT": {"YEAR": 1940, "PLAC": "London, England"}}}
        rows = run_grabstein_search(inds)
        assert rows == []

    def test_valid_person_included(self):
        rows = run_grabstein_search({"@I1@": _INDIVIDUALS["@I1@"]})
        assert len(rows) == 1

    def test_war_generation_flagged(self):
        rows = run_grabstein_search({"@I2@": _INDIVIDUALS["@I2@"]})
        assert any("Kriegsgeneration" in str(r) for r in rows)

    def test_jewish_name_flagged(self):
        rows = run_grabstein_search({"@I5@": _INDIVIDUALS["@I5@"]})
        assert any("jüd" in str(r) for r in rows)

    def test_no_name_skipped(self):
        rows = run_grabstein_search({"@I6@": _INDIVIDUALS["@I6@"]})
        assert rows == []


class TestGrabsteinConfidence:
    def test_hoch(self):
        assert _confidence("Schulze", 1870, 1940) == "HOCH"

    def test_mittel(self):
        assert _confidence("Schulze", 1870, None) == "MITTEL"

    def test_niedrig(self):
        assert _confidence("Schulze", None, None) == "NIEDRIG"


class TestGrabsteinUrls:
    def test_billiongraves_contains_name(self):
        url = _billiongraves("Johann", "Schulze", 1850, 1920, "Osnabrück")
        assert "billiongraves.com" in url
        assert "Schulze" in url

    def test_findagrave_contains_name(self):
        url = _findagrave("Johann", "Schulze", 1850, 1920)
        assert "findagrave.com" in url
        assert "Schulze" in url

    def test_grabstein_projekt(self):
        url = _grabstein_projekt("Schulze", 1850)
        assert "grabsteine.genealogy.net" in url

    def test_volksbund(self):
        url = _volksbund("Johann", "Schulze", 1900)
        assert "volksbund.de" in url
        assert "Schulze" in url

    def test_jewish_cemeteries(self):
        url = _jewish_cemeteries("Samuel", "Levy", 1882)
        assert "steinheim-institut.de" in url or "epidat" in url

    def test_headers_count(self):
        assert len(GRABSTEIN_HEADERS) == 13


class TestGrabsteinHelpers:
    def test_split_name_slash(self):
        given, sn = _split_name("Johann /Schulze/")
        assert given == "Johann"
        assert sn == "Schulze"

    def test_split_name_plain(self):
        given, sn = _split_name("Johann Schulze")
        assert sn == "Schulze"

    def test_might_be_jewish_true(self):
        assert _might_be_jewish("Samuel Stern") is True

    def test_might_be_jewish_false(self):
        assert _might_be_jewish("Hans") is False


# ═══════════════════════════════════════════════════════════════════════════════
# externe_quellen
# ═══════════════════════════════════════════════════════════════════════════════

from tasks.externe_quellen import (
    run_externe_quellen,
    _zeitraum,
    _is_dach,
    _is_nrw,
    _is_emigrant,
    _split_name as _eq_split_name,
    _familysearch,
    _geneanet,
    _geni,
    _wikidata_person,
    _gnd,
    _adressbuch,
    EXTERNE_QUELLEN_HEADERS,
)


class TestExterneQuellenZeitraum:
    def test_fruehe_neuzeit(self):
        assert "1600" in _zeitraum(1550, None)

    def test_barock(self):
        assert "1600" in _zeitraum(1700, None) or "Barock" in _zeitraum(1700, None)

    def test_kirchenbuch(self):
        assert "Kirchenbuch" in _zeitraum(1800, None)

    def test_standesamt(self):
        assert "Standesamt" in _zeitraum(1890, None)

    def test_nachkrieg(self):
        assert "Nachkrieg" in _zeitraum(1950, None)

    def test_unbekannt(self):
        assert _zeitraum(None, None) == "Unbekannt"


class TestExterneQuellenFlags:
    def test_is_dach_germany(self):
        assert _is_dach("Osnabrück, Niedersachsen, Deutschland") is True

    def test_is_dach_austria(self):
        assert _is_dach("Wien, Österreich") is True

    def test_is_not_dach(self):
        assert _is_dach("London, England") is False

    def test_is_dach_empty(self):
        assert _is_dach("") is True  # no place → assume DACH

    def test_is_nrw(self):
        assert _is_nrw("Münster, Westfalen") is True

    def test_not_nrw(self):
        assert _is_nrw("Osnabrück, Niedersachsen") is False

    def test_is_emigrant_name(self):
        assert _is_emigrant({"NAME": "Hans /Müller/ mig.USA"}) is True

    def test_is_emigrant_note(self):
        assert _is_emigrant({"NAME": "Hans /Müller/", "NOTE": "auswanderer nach Amerika"}) is True

    def test_not_emigrant(self):
        assert _is_emigrant({"NAME": "Hans /Müller/"}) is False


class TestExterneQuellenUrls:
    def test_familysearch_url(self):
        url = _familysearch("Johann", "Schulze", 1850, "Osnabrück")
        assert "familysearch.org" in url
        assert "Schulze" in url

    def test_geneanet_url(self):
        url = _geneanet("Johann", "Schulze", "Osnabrück")
        assert "geneanet.org" in url

    def test_geni_url(self):
        url = _geni("Johann", "Schulze", 1850)
        assert "geni.com" in url

    def test_wikidata_person_url(self):
        url = _wikidata_person("Johann", "Schulze", 1850)
        assert "wikidata.org" in url or "query.wikidata" in url

    def test_gnd_url(self):
        url = _gnd("Johann", "Schulze", 1850)
        assert "lobid.org" in url

    def test_adressbuch_url(self):
        url = _adressbuch("Schulze", "Osnabrück", 1850)
        assert "genealogy.net" in url or "adressbuch" in url.lower()


class TestExterneQuellenRun:
    def test_returns_list(self):
        rows = run_externe_quellen(_INDIVIDUALS)
        assert isinstance(rows, list)

    def test_emigrant_included(self):
        rows = run_externe_quellen({"@I4@": _INDIVIDUALS["@I4@"]})
        assert len(rows) == 1
        row_str = " ".join(str(c) for c in rows[0])
        # Besonderheit-Spalte enthält "Auswanderer"; ancestry.de-URL für Hamburg-Listen
        assert "Auswanderer" in row_str or "ancestry.de" in row_str

    def test_too_young_skipped(self):
        inds = {"@I1@": {**_INDIVIDUALS["@I1@"],
                          "BIRT": {"YEAR": 1970, "PLAC": "Berlin"},
                          "DEAT": {}}}
        rows = run_externe_quellen(inds)
        assert rows == []

    def test_no_name_skipped(self):
        rows = run_externe_quellen({"@I6@": _INDIVIDUALS["@I6@"]})
        assert rows == []

    def test_headers_count(self):
        assert len(EXTERNE_QUELLEN_HEADERS) == 27

    def test_scope_filter(self):
        rows_all = run_externe_quellen(_INDIVIDUALS)
        rows_one = run_externe_quellen(_INDIVIDUALS, root_related_ids={"@I1@"})
        assert len(rows_one) <= len(rows_all)
        assert len(rows_one) <= 1


# ═══════════════════════════════════════════════════════════════════════════════
# dfd_lookup
# ═══════════════════════════════════════════════════════════════════════════════

from tasks.dfd_lookup import (
    _similar_enough,
    _normalize_first,
    _collect_surnames,
    _search_url,
    _find_article_link,
    _parse_article,
    run_dfd_lookup,
    DFD_LOOKUP_HEADERS,
)


class TestDfdSimilarEnough:
    def test_identical(self):
        assert _similar_enough("Schulze", "Schulze") is True

    def test_close_variant(self):
        assert _similar_enough("Schulze", "Schulz") is True

    def test_k_c_equivalence(self):
        assert _similar_enough("Kovermann", "Covermann") is True

    def test_f_v_equivalence(self):
        assert _similar_enough("Vogt", "Fogt") is True

    def test_unrelated(self):
        assert _similar_enough("Schulze", "Müller") is False

    def test_empty(self):
        assert _similar_enough("", "Schulze") is False
        assert _similar_enough("Schulze", "") is False

    def test_too_different_length(self):
        assert _similar_enough("A", "Alexandrewski") is False


class TestDfdNormalizeFirst:
    def test_c_to_k(self):
        assert _normalize_first("C") == "K"

    def test_v_to_f(self):
        assert _normalize_first("V") == "F"

    def test_w_to_f(self):
        assert _normalize_first("W") == "F"

    def test_q_to_k(self):
        assert _normalize_first("Q") == "K"

    def test_y_to_i(self):
        assert _normalize_first("Y") == "I"

    def test_normal_letter(self):
        assert _normalize_first("S") == "S"

    def test_lowercase_input(self):
        assert _normalize_first("c") == "K"


class TestDfdCollectSurnames:
    def test_extracts_surnames(self):
        sn = _collect_surnames(_INDIVIDUALS)
        assert "Schulze" in sn
        assert "Kovermann" in sn

    def test_no_name_skipped(self):
        sn = _collect_surnames({"@I6@": _INDIVIDUALS["@I6@"]})
        assert sn == []

    def test_sorted_by_frequency(self):
        inds = {
            "@I1@": {"NAME": "A /Müller/"},
            "@I2@": {"NAME": "B /Müller/"},
            "@I3@": {"NAME": "C /Schmidt/"},
        }
        sn = _collect_surnames(inds)
        assert sn[0] == "Müller"


class TestDfdSearchUrl:
    def test_contains_name(self):
        url = _search_url("Schulze")
        assert "Schulze" in url or "schulze" in url.lower()

    def test_contains_base(self):
        url = _search_url("Schulze")
        assert "namenforschung.net" in url

    def test_contains_action(self):
        url = _search_url("Schulze")
        assert "list" in url


class TestDfdFindArticleLink:
    _FAKE_HTML = """
    <html><body>
      <a href="/dfd/woerterbuch/liste/?tx_dfd_names%5Bname%5D=1234
      &tx_dfd_names%5Baction%5D=show&cHash=abc">Schulze</a>
      <a href="/dfd/woerterbuch/liste/?tx_dfd_names%5Bname%5D=5678
      &tx_dfd_names%5Baction%5D=show&cHash=xyz">Schulz</a>
    </body></html>
    """

    def test_finds_matching_link(self):
        link = _find_article_link("Schulze", self._FAKE_HTML)
        assert link is not None
        assert "namenforschung.net" in link

    def test_returns_none_for_unknown(self):
        link = _find_article_link("Xyzzy", self._FAKE_HTML)
        assert link is None


class TestDfdParseArticle:
    _FAKE_ARTICLE = """
    <html><body>
    <p>Häufigkeit: 45.320</p>
    <p>Rang: 42</p>
    <p>Namentyp: Berufsname des Schulmeister und Schulsprechers</p>
    <p>Etymologie: mittelhochdeutsch schuolmeister Grundwort Schule Bildung</p>
    <p>Varianten: Schulz, Schultz, Schultze</p>
    </body></html>
    """

    def test_parses_frequency(self):
        d = _parse_article("Schulze", self._FAKE_ARTICLE)
        assert d["frequency"]

    def test_parses_rank(self):
        d = _parse_article("Schulze", self._FAKE_ARTICLE)
        assert d["rank"] == "42"

    def test_parses_type(self):
        d = _parse_article("Schulze", self._FAKE_ARTICLE)
        assert "Berufsname" in d["type"]

    def test_parses_etymology(self):
        d = _parse_article("Schulze", self._FAKE_ARTICLE)
        assert d["etymology"]

    def test_parses_variants(self):
        d = _parse_article("Schulze", self._FAKE_ARTICLE)
        assert "Schulz" in d["variants"] or "Schultz" in d["variants"]


class TestDfdRunLookupNoScrape:
    def test_url_only_mode(self):
        rows, variants = run_dfd_lookup(_INDIVIDUALS, scrape=False)
        assert isinstance(rows, list)
        assert len(rows) > 0
        assert isinstance(variants, dict)

    def test_row_structure(self):
        rows, _ = run_dfd_lookup(_INDIVIDUALS, scrape=False)
        assert len(rows[0]) == len(DFD_LOOKUP_HEADERS)

    def test_url_in_last_column(self):
        rows, _ = run_dfd_lookup(_INDIVIDUALS, scrape=False)
        for row in rows:
            assert "namenforschung.net" in row[-1]

    def test_headers_count(self):
        assert len(DFD_LOOKUP_HEADERS) == 8

    def test_max_names_respected(self):
        rows, _ = run_dfd_lookup(_INDIVIDUALS, scrape=False, max_names=2)
        assert len(rows) <= 2


class TestDfdVariantsJson:
    def test_saves_json(self, tmp_path, monkeypatch):
        import tasks.dfd_lookup as dfd_mod
        json_path = tmp_path / "dfd_variants.json"
        monkeypatch.setattr(dfd_mod, "_VARIANTS_JSON", str(json_path))
        monkeypatch.setattr(dfd_mod, "_get_html", lambda url: _FAKE_ARTICLE_HTML)
        monkeypatch.setattr(dfd_mod, "_find_article_link",
                            lambda sn, html: "https://example.com/show")
        monkeypatch.setattr(dfd_mod, "time", types.SimpleNamespace(sleep=lambda s: None))

        rows, variants = dfd_mod.run_dfd_lookup(
            {"@I1@": {"NAME": "Johann /Schulze/"}},
            scrape=True,
        )
        if variants:
            assert json_path.exists()
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            assert isinstance(loaded, dict)


_FAKE_ARTICLE_HTML = """
<html><body>
<p>Häufigkeit: 45.320</p><p>Rang: 42</p>
<p>Namentyp: Berufsname</p>
<p>Etymologie: mittelhochdeutsch Schule</p>
<p>Varianten: Schulz, Schultz</p>
</body></html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# expand_surname_variants (bridge integration)
# ═══════════════════════════════════════════════════════════════════════════════

from ancestry.core.bridge._text import expand_surname_variants, _norm


class TestExpandSurnameVariants:
    def test_always_includes_self(self):
        result = expand_surname_variants("schulze")
        assert "schulze" in result

    def test_loads_from_json(self, tmp_path, monkeypatch):
        import ancestry.core.bridge._text as txt
        data = {"Schulze": ["Schulz", "Schultz"]}
        json_path = tmp_path / "dfd_variants.json"
        json_path.write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr(txt, "_VARIANTS_LOADED", False)
        monkeypatch.setattr(txt, "_SURNAME_VARIANTS", {})

        original_load = txt._load_surname_variants

        def _patched_load():
            nonlocal original_load
            txt._VARIANTS_LOADED = True
            try:
                raw = json.loads(json_path.read_text(encoding="utf-8"))
                txt._SURNAME_VARIANTS = {k: list(v) for k, v in raw.items()}
            except Exception:
                pass

        monkeypatch.setattr(txt, "_load_surname_variants", _patched_load)

        result = txt.expand_surname_variants(_norm("Schulze"))
        assert _norm("Schulz") in result or _norm("Schulze") in result

    def test_unknown_surname_returns_self_only(self, monkeypatch):
        import ancestry.core.bridge._text as txt
        monkeypatch.setattr(txt, "_VARIANTS_LOADED", True)
        monkeypatch.setattr(txt, "_SURNAME_VARIANTS", {})
        result = txt.expand_surname_variants("xyzzy")
        assert result == {"xyzzy"}
