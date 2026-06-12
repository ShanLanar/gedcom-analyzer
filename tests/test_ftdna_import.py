"""Tests für ancestry/tools/import_ftdna_matches.py und Endogamie-Kalibrierung."""
import csv
import os
import tempfile
from pathlib import Path

import pytest

from ancestry.tools.import_ftdna_matches import parse_csv, run, _make_guid
from ancestry.core.treematch.genetics import cm_to_mrca, ENDOGAMY_FACTORS


# ── FTDNA CSV-Parsing ────────────────────────────────────────────────────────

def _write_csv(rows: list[list], header: list[str], suffix=".csv") -> Path:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return Path(path)


def test_parse_classic_format():
    p = _write_csv(
        [["John Smith", "2nd Cousin", "2nd Cousin", "23.67 cM", "89.45 cM"]],
        ["Name", "Relationship Range", "Suggested Relationship", "Longest Block", "Total Shared cM"],
    )
    try:
        matches = parse_csv(p)
        assert len(matches) == 1
        m = matches[0]
        assert m["display_name"] == "John Smith"
        assert abs(m["shared_cm"] - 89.45) < 0.01
        assert abs(m["longest_segment"] - 23.67) < 0.01
        assert m["predicted_relationship"] == "2nd Cousin"
    finally:
        os.unlink(p)


def test_parse_modern_format():
    p = _write_csv(
        [["Jane Doe", "2023-01-15", "3rd Cousin", "3rd Cousin", "15.0", "42.3", "No", "87654321"]],
        ["Full Name", "Match Date", "Relationship Range", "Suggested Relationship",
         "Longest Segment", "Total Shared cM", "X Match", "FTDNA ID"],
    )
    try:
        matches = parse_csv(p)
        assert len(matches) == 1
        m = matches[0]
        assert m["display_name"] == "Jane Doe"
        assert m["ftdna_id"] == "87654321"
    finally:
        os.unlink(p)


def test_parse_skips_zero_cm():
    p = _write_csv(
        [["Noise", "?", "?", "0", "0"]],
        ["Name", "Relationship Range", "Suggested Relationship", "Longest Block", "Total Shared cM"],
    )
    try:
        matches = parse_csv(p)
        assert matches == []
    finally:
        os.unlink(p)


def test_guid_stable_with_ftdna_id():
    g1 = _make_guid("John Smith", "12345")
    g2 = _make_guid("John Smith", "12345")
    assert g1 == g2
    assert g1.startswith("ftdna-")


def test_guid_name_hash_when_no_id():
    g = _make_guid("Anna Müller")
    assert g.startswith("ftdna-")
    # Different names → different GUIDs
    assert _make_guid("Anna Müller") != _make_guid("Otto Müller")


def test_run_imports_to_db():
    import sqlite3
    p = _write_csv(
        [["Max Mustermann", "2nd Cousin", "2nd Cousin", "25.0 cM", "80.0 cM"],
         ["Tiny Match",     "Remote",     "Remote",     "3.0 cM",  "4.0 cM"]],  # < 7 cM → skip
        ["Name", "Relationship Range", "Suggested Relationship", "Longest Block", "Total Shared cM"],
    )
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db_path)
    try:
        from ancestry.core.database import Database
        db = Database(db_path)
        db.close()
        result = run(p, kit_guid="FTDNA_TEST", db_file=Path(db_path))
        assert result["imported"] == 1
        assert result["skipped"] == 1
        # Verify in DB
        conn = sqlite3.connect(db_path)
        cnt = conn.execute("SELECT COUNT(*) FROM matches WHERE test_guid='FTDNA_TEST'").fetchone()[0]
        assert cnt == 1
        conn.close()
    finally:
        os.unlink(p)
        if os.path.exists(db_path):
            os.unlink(db_path)


# ── Endogamie-Kalibrierung ───────────────────────────────────────────────────

def test_cm_to_mrca_no_correction():
    label, gen = cm_to_mrca(89.45)
    assert gen in (4, 5)  # 2. / 3. Cousin-Bereich


def test_cm_to_mrca_ashkenazi():
    # Mit Ashkenazi-Faktor 1.7: 89.45 / 1.7 ≈ 52.6 cM → entferntere Verwandtschaft
    label_plain, gen_plain = cm_to_mrca(89.45)
    label_endo,  gen_endo  = cm_to_mrca(89.45, population="ashkenazi")
    assert gen_endo >= gen_plain  # endogam → höhere Generation (entfernter)


def test_cm_to_mrca_explicit_factor():
    _, gen1 = cm_to_mrca(200.0)
    _, gen2 = cm_to_mrca(200.0, endogamy_factor=2.0)
    assert gen2 >= gen1


def test_endogamy_factors_all_above_one():
    for pop, factor in ENDOGAMY_FACTORS.items():
        assert factor >= 1.0, f"{pop}: factor {factor} < 1.0"


def test_endogamy_population_lookup():
    # "osnabrück" (niedersächsisch) → Faktor 1.10
    _, gen_base = cm_to_mrca(50.0)
    _, gen_endo = cm_to_mrca(50.0, population="osnabrück")
    assert gen_endo >= gen_base
