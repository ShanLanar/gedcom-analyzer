"""Tests for ancestry.core.population_stats — all four analysis functions."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from ancestry.core.population_stats import (
    CM_BINS,
    CM_BIN_REL,
    birth_distribution,
    cm_histogram,
    migration_matrix,
    surname_entropy_series,
)


# ── In-memory DB fixture ──────────────────────────────────────────────────────

def _make_db():
    """Build a minimal in-memory SQLite DB that matches the schema expected
    by population_stats. Returns a mock that mimics db._cursor()."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute(
        """CREATE TABLE gedcom_persons (
            birth_year INTEGER,
            birth_place TEXT,
            surname     TEXT,
            sosa_number INTEGER
        )"""
    )
    cur.execute(
        """CREATE TABLE match_pedigree (
            birth_year  TEXT,
            birth_place TEXT,
            surname     TEXT,
            generation  INTEGER,
            match_guid  TEXT,
            test_guid   TEXT,
            ahnen_path  TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE matches (
            test_guid  TEXT,
            match_guid TEXT,
            shared_cm  REAL
        )"""
    )
    con.commit()

    @contextmanager
    def _cursor():
        yield con.cursor()

    db = MagicMock()
    db._cursor = _cursor
    return db, con


def _ins_gedcom(con, birth_year, birth_place, surname="Müller", sosa=1):
    con.execute(
        "INSERT INTO gedcom_persons VALUES (?,?,?,?)",
        (birth_year, birth_place, surname, sosa),
    )
    con.commit()


def _ins_pedigree(con, birth_year, birth_place, surname="Müller",
                  generation=2, match_guid="m1", test_guid="t1", ahnen_path="12"):
    con.execute(
        "INSERT INTO match_pedigree VALUES (?,?,?,?,?,?,?)",
        (str(birth_year), birth_place, surname, generation,
         match_guid, test_guid, ahnen_path),
    )
    con.commit()


def _ins_match(con, test_guid, match_guid, shared_cm):
    con.execute(
        "INSERT INTO matches VALUES (?,?,?)",
        (test_guid, match_guid, shared_cm),
    )
    con.commit()


# ── birth_distribution ────────────────────────────────────────────────────────

class TestBirthDistribution:
    def test_empty_db_returns_empty(self):
        db, _ = _make_db()
        assert birth_distribution(db) == []

    def test_gedcom_persons_counted(self):
        db, con = _make_db()
        for _ in range(5):
            _ins_gedcom(con, 1850, "Osnabrück, Niedersachsen, Deutschland")
        result = birth_distribution(db, min_count=1)
        assert any(r["decade"] == 1850 for r in result)

    def test_decade_aligned(self):
        db, con = _make_db()
        for yr in (1851, 1852, 1853, 1854, 1855):
            _ins_gedcom(con, yr, "Hamburg, Deutschland")
        result = birth_distribution(db, min_count=1)
        assert all(r["decade"] % 10 == 0 for r in result)
        assert any(r["decade"] == 1850 for r in result)

    def test_match_pedigree_counted(self):
        db, con = _make_db()
        for _ in range(4):
            _ins_pedigree(con, 1880, "Bremen, Deutschland", generation=3)
        result = birth_distribution(db, min_count=1)
        assert any(r["decade"] == 1880 for r in result)

    def test_min_count_filters(self):
        db, con = _make_db()
        # only 2 entries — below default min_count=3
        for _ in range(2):
            _ins_gedcom(con, 1900, "Köln, Nordrhein-Westfalen, Deutschland")
        assert birth_distribution(db, min_count=3) == []
        assert len(birth_distribution(db, min_count=1)) >= 1

    def test_sorted_by_decade(self):
        db, con = _make_db()
        for yr in (1900, 1850, 1800):
            for _ in range(4):
                _ins_gedcom(con, yr, "Osnabrück, Niedersachsen, Deutschland")
        result = birth_distribution(db, min_count=1)
        decades = [r["decade"] for r in result]
        assert decades == sorted(decades)

    def test_out_of_range_years_excluded(self):
        db, con = _make_db()
        for _ in range(5):
            _ins_gedcom(con, 1400, "Osnabrück, Niedersachsen, Deutschland")
        assert birth_distribution(db, min_count=1) == []

    def test_result_has_required_keys(self):
        db, con = _make_db()
        for _ in range(4):
            _ins_gedcom(con, 1870, "Osnabrück, Niedersachsen, Deutschland")
        result = birth_distribution(db, min_count=1)
        assert result
        assert {"decade", "region", "count"} <= result[0].keys()

    def test_generation_1_pedigree_excluded(self):
        db, con = _make_db()
        for _ in range(5):
            _ins_pedigree(con, 1870, "Hamburg, Deutschland", generation=1)
        assert birth_distribution(db, min_count=1) == []


# ── migration_matrix ──────────────────────────────────────────────────────────

class TestMigrationMatrix:
    def test_empty_db_returns_empty(self):
        db, _ = _make_db()
        assert migration_matrix(db) == []

    def test_sosa_parent_child_flow(self):
        db, con = _make_db()
        # child sosa=2, parent sosa=4 (2*2), different regions
        _ins_gedcom(con, 1870, "Hamburg, Deutschland", sosa=2)
        _ins_gedcom(con, 1840, "Osnabrück, Niedersachsen, Deutschland", sosa=4)
        result = migration_matrix(db)
        assert any(
            r["from_region"] != r["to_region"] for r in result
        )

    def test_same_region_excluded(self):
        db, con = _make_db()
        _ins_gedcom(con, 1870, "Osnabrück, Niedersachsen, Deutschland", sosa=2)
        _ins_gedcom(con, 1840, "Osnabrück, Niedersachsen, Deutschland", sosa=4)
        result = migration_matrix(db)
        assert not any(
            r["from_region"] == r["to_region"] for r in result
        )

    def test_result_has_required_keys(self):
        db, con = _make_db()
        _ins_gedcom(con, 1870, "Hamburg, Deutschland", sosa=2)
        _ins_gedcom(con, 1840, "Osnabrück, Niedersachsen, Deutschland", sosa=4)
        result = migration_matrix(db)
        if result:
            assert {"from_region", "to_region", "count"} <= result[0].keys()

    def test_top_n_limits(self):
        db, con = _make_db()
        # Create 5 distinct flows via different sosa pairs
        pairs = [(2, 4), (3, 6), (5, 10), (7, 14), (9, 18)]
        places = [
            ("Hamburg, Deutschland", "Osnabrück, Niedersachsen, Deutschland"),
            ("Bremen, Deutschland", "Lübeck, Schleswig-Holstein, Deutschland"),
            ("Berlin, Deutschland", "Leipzig, Sachsen, Deutschland"),
            ("München, Bayern, Deutschland", "Nürnberg, Bayern, Deutschland"),
            ("Frankfurt am Main, Hessen, Deutschland", "Wiesbaden, Hessen, Deutschland"),
        ]
        for (cs, ps), (cp, pp) in zip(pairs, places):
            for _ in range(3):
                _ins_gedcom(con, 1870, cp, sosa=cs)
                _ins_gedcom(con, 1840, pp, sosa=ps)
        result = migration_matrix(db, top_n=2)
        assert len(result) <= 2


# ── cm_histogram ──────────────────────────────────────────────────────────────

class TestCmHistogram:
    def test_empty_matches_returns_empty(self):
        db, _ = _make_db()
        assert cm_histogram(db, "test1") == []

    def test_returns_all_bins(self):
        db, con = _make_db()
        for cm in (25, 75, 125, 175, 250, 350, 500, 750, 1100, 1700, 2500):
            _ins_match(con, "t1", f"m{cm}", cm)
        result = cm_histogram(db, "t1")
        assert len(result) == len(CM_BINS)

    def test_bin_counts_correct(self):
        db, con = _make_db()
        # 3 matches in 0-50 bin, 1 in 50-100
        for _ in range(3):
            _ins_match(con, "t1", f"ma{_}", 25.0)
        _ins_match(con, "t1", "mb1", 75.0)
        result = cm_histogram(db, "t1")
        bin_0 = next(r for r in result if r["bin_lo"] == 0)
        bin_50 = next(r for r in result if r["bin_lo"] == 50)
        assert bin_0["observed"] == 3
        assert bin_50["observed"] == 1

    def test_zero_cm_excluded(self):
        db, con = _make_db()
        _ins_match(con, "t1", "m0", 0.0)
        _ins_match(con, "t1", "m1", 25.0)
        result = cm_histogram(db, "t1")
        total = sum(r["observed"] for r in result)
        assert total == 1

    def test_result_has_required_keys(self):
        db, con = _make_db()
        _ins_match(con, "t1", "m1", 25.0)
        result = cm_histogram(db, "t1")
        assert result
        assert {"bin_lo", "bin_hi", "label", "observed", "rel_hint"} <= result[0].keys()

    def test_rel_hints_match_cm_bin_rel(self):
        db, con = _make_db()
        for cm in (25, 75, 125):
            _ins_match(con, "t1", f"m{cm}", float(cm))
        result = cm_histogram(db, "t1")
        for i, r in enumerate(result):
            assert r["rel_hint"] == CM_BIN_REL[i]

    def test_wrong_test_guid_returns_empty(self):
        db, con = _make_db()
        _ins_match(con, "t1", "m1", 25.0)
        result = cm_histogram(db, "t_other")
        assert all(r["observed"] == 0 for r in result)

    def test_cm_bins_constant_length(self):
        assert len(CM_BINS) == len(CM_BIN_REL)


# ── surname_entropy_series ────────────────────────────────────────────────────

class TestSurnameEntropySeries:
    def test_empty_db_returns_empty(self):
        db, _ = _make_db()
        assert surname_entropy_series(db) == []

    def test_single_surname_entropy_zero(self):
        db, con = _make_db()
        for _ in range(25):
            _ins_gedcom(con, 1850, "irgendwo", surname="Müller")
        result = surname_entropy_series(db, min_per_decade=20)
        assert result
        assert result[0]["entropy"] == 0.0

    def test_two_equal_surnames_entropy_one(self):
        db, con = _make_db()
        for _ in range(15):
            _ins_gedcom(con, 1850, "irgendwo", surname="Müller")
        for _ in range(15):
            _ins_gedcom(con, 1850, "irgendwo", surname="Meier")
        result = surname_entropy_series(db, min_per_decade=20)
        assert result
        assert abs(result[0]["entropy"] - 1.0) < 1e-6

    def test_min_per_decade_filter(self):
        db, con = _make_db()
        for _ in range(10):
            _ins_gedcom(con, 1850, "irgendwo", surname="Müller")
        assert surname_entropy_series(db, min_per_decade=20) == []
        assert len(surname_entropy_series(db, min_per_decade=5)) >= 1

    def test_result_has_required_keys(self):
        db, con = _make_db()
        for _ in range(25):
            _ins_gedcom(con, 1850, "irgendwo", surname="Müller")
        result = surname_entropy_series(db, min_per_decade=1)
        assert result
        assert {"decade", "entropy", "unique", "total"} <= result[0].keys()

    def test_sorted_by_decade(self):
        db, con = _make_db()
        for yr in (1900, 1850, 1800):
            for _ in range(25):
                _ins_gedcom(con, yr, "irgendwo", surname="Müller")
        result = surname_entropy_series(db, min_per_decade=1)
        decades = [r["decade"] for r in result]
        assert decades == sorted(decades)

    def test_match_pedigree_included(self):
        db, con = _make_db()
        for _ in range(12):
            _ins_pedigree(con, 1880, "irgendwo", surname="Schmidt", generation=2)
        for _ in range(12):
            _ins_pedigree(con, 1880, "irgendwo", surname="Schulze", generation=2)
        result = surname_entropy_series(db, min_per_decade=20)
        assert result
        assert abs(result[0]["entropy"] - 1.0) < 1e-6

    def test_entropy_nonnegative(self):
        db, con = _make_db()
        surnames = ["Müller", "Meier", "Schmidt", "Schulze", "Fischer"]
        for i, sn in enumerate(surnames):
            for _ in range(5):
                _ins_gedcom(con, 1850, "irgendwo", surname=sn)
        result = surname_entropy_series(db, min_per_decade=1)
        assert all(r["entropy"] >= 0 for r in result)

    def test_generation_1_pedigree_excluded(self):
        db, con = _make_db()
        for _ in range(25):
            _ins_pedigree(con, 1880, "irgendwo", surname="Müller", generation=1)
        assert surname_entropy_series(db, min_per_decade=20) == []
