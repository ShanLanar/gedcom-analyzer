"""Tests for TSV export functionality (F5)."""

import csv
import tempfile
from pathlib import Path

import pytest

from ancestry.core.export import export_matches_tsv
from ancestry.models import DnaMatch


class TestExportMatchesTsv:
    """Test TSV export for matches."""

    def test_empty_list(self):
        """Empty match list should write only header."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            filepath = f.name

        try:
            count = export_matches_tsv([], filepath)
            assert count == 0

            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 1  # Header only
            assert "match_guid" in lines[0]
        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_single_match(self):
        """Single match should be exported correctly."""
        match = DnaMatch(
            match_guid="abc123",
            test_guid="test456",
            display_name="John Doe",
            shared_cm=100.5,
            shared_segments=15,
            predicted_relationship="1. Cousin",
            fetched_at="2026-06-22T10:30:00",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            filepath = f.name

        try:
            count = export_matches_tsv([match], filepath)
            assert count == 1

            # Read back and verify
            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                rows = list(reader)

            assert len(rows) == 1
            row = rows[0]
            assert row["match_guid"] == "abc123"
            assert row["display_name"] == "John Doe"
            assert row["shared_cm"] == "100.5"
            assert row["shared_segments"] == "15"
            assert row["predicted_relationship"] == "1. Cousin"
            assert row["test_guid"] == "test456"
        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_multiple_matches(self):
        """Multiple matches should all be exported."""
        matches = [
            DnaMatch(
                match_guid="guid1",
                test_guid="test1",
                display_name="Alice",
                shared_cm=50,
                shared_segments=10,
                predicted_relationship="2. Cousin",
                fetched_at="2026-06-22",
            ),
            DnaMatch(
                match_guid="guid2",
                test_guid="test1",
                display_name="Bob",
                shared_cm=150,
                shared_segments=30,
                predicted_relationship="1. Cousin",
                fetched_at="2026-06-22",
            ),
            DnaMatch(
                match_guid="guid3",
                test_guid="test1",
                display_name="Charlie",
                shared_cm=200,
                shared_segments=40,
                predicted_relationship="1. Cousin",
                fetched_at="2026-06-22",
            ),
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            filepath = f.name

        try:
            count = export_matches_tsv(matches, filepath)
            assert count == 3

            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                rows = list(reader)

            assert len(rows) == 3
            assert rows[0]["match_guid"] == "guid1"
            assert rows[1]["match_guid"] == "guid2"
            assert rows[2]["match_guid"] == "guid3"
        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_utf8_encoding(self):
        """UTF-8 special characters should be handled correctly."""
        match = DnaMatch(
            match_guid="guid1",
            test_guid="test1",
            display_name="Jürgen Müller-Schönefeld",
            shared_cm=100,
            shared_segments=20,
            predicted_relationship="Cousin",
            fetched_at="2026-06-22",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            filepath = f.name

        try:
            count = export_matches_tsv([match], filepath)
            assert count == 1

            # Verify UTF-8 encoding
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            assert "Jürgen" in content
            assert "Müller-Schönefeld" in content
            assert "Cousin" in content
        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_tab_delimiter(self):
        """Verify tab-delimited format."""
        match = DnaMatch(
            match_guid="guid1",
            test_guid="test1",
            display_name="Test User",
            shared_cm=100,
            shared_segments=20,
            predicted_relationship="Cousin",
            fetched_at="2026-06-22",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            filepath = f.name

        try:
            export_matches_tsv([match], filepath)

            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Header line should have tabs
            header = lines[0].strip()
            assert "\t" in header
            assert header.count("\t") >= 6  # At least 6 columns

            # Data line should have tabs
            data = lines[1].strip()
            assert "\t" in data
        finally:
            Path(filepath).unlink(missing_ok=True)

    def test_header_columns(self):
        """Verify all required columns are present."""
        match = DnaMatch(
            match_guid="guid1",
            test_guid="test1",
            display_name="Test",
            shared_cm=100,
            shared_segments=20,
            predicted_relationship="Cousin",
            fetched_at="2026-06-22",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
            filepath = f.name

        try:
            export_matches_tsv([match], filepath)

            with open(filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                fieldnames = reader.fieldnames

            required_cols = [
                "match_guid",
                "display_name",
                "shared_cm",
                "shared_segments",
                "predicted_relationship",
                "test_guid",
                "fetched_at",
            ]
            for col in required_cols:
                assert col in fieldnames
        finally:
            Path(filepath).unlink(missing_ok=True)
