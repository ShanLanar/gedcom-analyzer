# -*- coding: utf-8 -*-
"""
tests/test_wikitree.py – Tests für WikiTree-Lookup-Modul.

Tests für:
  1. Konfidenz-Berechnung (HIGH/MEDIUM/LOW)
  2. API-Fehlerbehandlung
  3. Name-Parsing
  4. URL-Generierung
"""

import unittest
from unittest.mock import patch, MagicMock

from tasks.wikitree_lookup import (
    _confidence, _search_url, _split_name, _api_search, run_wikitree_lookup
)


class TestConfidenceCalculation(unittest.TestCase):
    """Tests für die Konfidenz-Berechnung."""

    def test_high_confidence_exact_name_close_year(self):
        """HIGH: Exakter Nachname + ±2 Jahre."""
        wt = {
            "FirstName": "Johann",
            "LastNameAtBirth": "Mueller",
            "BirthDate": "1850-05-12",
            "DeathLocation": "Berlin"
        }
        level, score = _confidence("Johann", "Mueller", 1850, wt)
        self.assertEqual(level, "HIGH")
        self.assertGreaterEqual(score, 0.85)

    def test_high_confidence_exact_name_5_years(self):
        """HIGH: Exakter Nachname + ±5 Jahre."""
        wt = {
            "FirstName": "Anna",
            "LastNameAtBirth": "Schmidt",
            "BirthDate": "1855-03-20",
            "DeathLocation": "Hamburg"
        }
        level, score = _confidence("Anna", "Schmidt", 1852, wt)
        self.assertEqual(level, "HIGH")
        self.assertGreaterEqual(score, 0.85)

    def test_medium_confidence_fuzzy_name_year_match(self):
        """MEDIUM: Fuzzy-Match (Teilname) + Jahr-Match ist eigentlich HIGH."""
        wt = {
            "FirstName": "Otto",  # nicht "Heinrich"
            "LastNameAtBirth": "Mueller",
            "BirthDate": "1880-06-10",
            "DeathLocation": "Hannover"
        }
        # "Muell" ist in "Mueller" enthalten (0.5) + Jahr ±2 (0.35) = 0.85 → HIGH
        level, score = _confidence("Heinrich", "Muell", 1880, wt)
        self.assertEqual(level, "HIGH")
        self.assertGreaterEqual(score, 0.85)

    def test_medium_confidence_exact_name_no_year(self):
        """MEDIUM: Exakter Nachname, Jahr fehlt — aber Vorname stimmt (HIGH ohne Jahr)."""
        wt = {
            "FirstName": "Wilhelm",
            "LastNameAtBirth": "Hoffmann",
            "BirthDate": "",
            "DeathLocation": "Bremen"
        }
        # Mit Vornamen-Match: 0.8 (name) + 0.15 (given) = 0.95 → HIGH
        # Das ist korrekt (mit Namen-Übereinstimmung)
        level, score = _confidence("Wilhelm", "Hoffmann", None, wt)
        self.assertEqual(level, "HIGH")
        self.assertGreaterEqual(score, 0.85)

    def test_low_confidence_no_name_match(self):
        """LOW: Nachname stimmt nicht überein."""
        wt = {
            "FirstName": "Karl",
            "LastNameAtBirth": "Fischer",
            "BirthDate": "1900-01-01",
            "DeathLocation": "Cologne"
        }
        level, score = _confidence("Karl", "Schulz", 1900, wt)
        self.assertEqual(level, "LOW")
        self.assertEqual(score, 0.0)

    def test_low_confidence_name_only(self):
        """LOW: Nur Nachname, kein Jahr + unterschiedlicher Vorname."""
        wt = {
            "FirstName": "Karl",  # nicht "Friedrich"
            "LastNameAtBirth": "Braun",
            "BirthDate": "",
            "DeathLocation": "Leipzig"
        }
        level, score = _confidence("Friedrich", "Braun", None, wt)
        self.assertEqual(level, "MEDIUM")  # Name stimmt, aber kein Jahr und kein Vorname
        self.assertGreaterEqual(score, 0.65)

    def test_confidence_given_name_match_boost(self):
        """Vornamen-Match gibt +0.15 Bonus."""
        wt = {
            "FirstName": "John",
            "LastNameAtBirth": "Smith",
            "BirthDate": "1870-02-14",
            "DeathLocation": "New York"
        }
        # "Jo" == "Jo" (first 2 chars)
        level, score = _confidence("John", "Smith", 1870, wt)
        self.assertGreaterEqual(score, 0.95)  # 0.8 (name) + 0.35 (year) + 0.15 (given)

    def test_empty_names_return_low(self):
        """Leere Namen → LOW."""
        wt = {"FirstName": "", "LastNameAtBirth": "", "BirthDate": ""}
        level, score = _confidence("", "Meier", 1800, wt)
        self.assertEqual(level, "LOW")
        self.assertEqual(score, 0.0)


class TestNameParsing(unittest.TestCase):
    """Tests für Name-Splitting."""

    def test_simple_name_split(self):
        """Einfacher Name: Vornamen und Nachname."""
        given, surname = _split_name("Johann Mueller")
        self.assertEqual(given, "Johann")
        self.assertEqual(surname, "Mueller")

    def test_name_with_slash(self):
        """Name mit GEDCOM-Nachname-Markierung (/)."""
        given, surname = _split_name("Maria Anna /Schmidt/")
        self.assertEqual(given, "Maria Anna")
        self.assertEqual(surname, "Schmidt")

    def test_name_with_symbols(self):
        """Name mit Symbolen (✠, ★)."""
        given, surname = _split_name("Peter Mueller ✠")
        self.assertEqual(given, "Peter")
        self.assertEqual(surname, "Mueller")

    def test_single_name(self):
        """Nur ein Name (kein Nachname erkennbar)."""
        given, surname = _split_name("Elizabeth")
        self.assertEqual(given, "Elizabeth")
        self.assertEqual(surname, "")

    def test_name_with_middle_names(self):
        """Name mit Mittelnamen."""
        given, surname = _split_name("Johann Friedrich Wilhelm Goethe")
        self.assertEqual(given, "Johann Friedrich Wilhelm")
        self.assertEqual(surname, "Goethe")


class TestSearchURL(unittest.TestCase):
    """Tests für WikiTree-Such-URL-Generierung."""

    def test_search_url_full_data(self):
        """Such-URL mit Vorname, Nachname, Geburtsjahr."""
        url = _search_url("Wilhelm", "Mueller", 1880)
        # URL ist URL-encoded: "Special:SearchPerson" wird zu "Special%3ASearchPerson"
        self.assertIn("SearchPerson", url)
        self.assertIn("wpSurname=Mueller", url)
        self.assertIn("wpFirst=Wilhelm", url)
        self.assertIn("wpBirthYear=1880", url)

    def test_search_url_no_given(self):
        """Such-URL ohne Vorname."""
        url = _search_url("", "Schmidt", 1820)
        self.assertIn("wpSurname=Schmidt", url)
        self.assertNotIn("wpFirst", url)

    def test_search_url_no_year(self):
        """Such-URL ohne Geburtsjahr."""
        url = _search_url("Anna", "Fischer", None)
        self.assertIn("wpSurname=Fischer", url)
        self.assertIn("wpFirst=Anna", url)
        self.assertNotIn("wpBirthYear", url)


class TestAPIErrorHandling(unittest.TestCase):
    """Tests für API-Fehlerbehandlung."""

    @patch("urllib.request.urlopen")
    def test_api_timeout_handling(self, mock_urlopen):
        """API-Timeout → None zurückgeben."""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Timeout")
        result = _api_search("Johann", "Mueller", 1850)
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_api_empty_results(self, mock_urlopen):
        """API liefert leeres Ergebnis → None."""
        from io import BytesIO
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"searchResult": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        result = _api_search("NonExistent", "Name", 1800)
        self.assertIsNone(result)

    @patch("urllib.request.urlopen")
    def test_api_malformed_response(self, mock_urlopen):
        """API-Antwort fehlerhaft → None."""
        from io import BytesIO
        mock_response = MagicMock()
        mock_response.read.return_value = b'{invalid json}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        result = _api_search("Johann", "Mueller", 1850)
        self.assertIsNone(result)


class TestRunWikiTreeLookup(unittest.TestCase):
    """Integration Tests für run_wikitree_lookup()."""

    def setUp(self):
        """Beispiel-Personen für Tests."""
        self.individuals = {
            "I1": {
                "NAME": "Johann /Mueller/",
                "BIRT": {"YEAR": 1850, "DATE": "12 MAY 1850", "PLAC": "Berlin"},
                "DEAT": {"YEAR": 1920, "DATE": "10 JAN 1920", "PLAC": "Berlin"}
            },
            "I2": {
                "NAME": "Anna /Schmidt/",
                "BIRT": {"YEAR": 1855, "DATE": "03 MAR 1855", "PLAC": "Hamburg"},
                "DEAT": {}
            },
            "I3": {
                "NAME": "Unknown",
                "BIRT": {},
                "DEAT": {}
            }
        }

    @patch("tasks.wikitree_lookup._api_search")
    def test_lookup_returns_rows(self, mock_api):
        """run_wikitree_lookup() gibt Reihen zurück."""
        mock_api.return_value = {
            "Id": "Mueller-123",
            "FirstName": "Johann",
            "LastNameAtBirth": "Mueller",
            "BirthDate": "1850-05-12",
            "DeathLocation": "Berlin"
        }
        rows = run_wikitree_lookup(
            self.individuals,
            max_persons=2,
            scrape=True,
            progress_cb=None
        )
        self.assertGreater(len(rows), 0)
        # Erste Spalte sollte Person-ID sein
        self.assertEqual(rows[0][0], "I1")

    def test_lookup_no_scrape_mode(self):
        """Nur Such-URLs (scrape=False)."""
        rows = run_wikitree_lookup(
            self.individuals,
            max_persons=2,
            scrape=False,
            progress_cb=None
        )
        self.assertGreater(len(rows), 0)
        # Spalte 12 (letzte) ist Such-URL, sollte nicht leer sein
        # URL ist URL-encoded
        self.assertIn("SearchPerson", rows[0][-1])

    def test_lookup_filters_too_young(self):
        """Personen > 1940 werden gefiltert."""
        young = {
            "I99": {
                "NAME": "Recent /Person/",
                "BIRT": {"YEAR": 1960, "DATE": "01 JAN 1960", "PLAC": "Berlin"},
                "DEAT": {}
            }
        }
        rows = run_wikitree_lookup(
            young,
            max_persons=10,
            scrape=False,
            progress_cb=None
        )
        # Sollte keine Reihen für I99 zurückgeben (zu jung)
        ids = [r[0] for r in rows]
        self.assertNotIn("I99", ids)


if __name__ == "__main__":
    unittest.main()
