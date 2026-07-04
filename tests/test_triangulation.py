"""
Tests für Segment-Triangulation (ancestry/core/triangulation.py)
und den Segment-Import (ancestry/tools/import_segments.py).
"""

import os
import tempfile

import pytest

from ancestry.core.database import Database
from ancestry.core.triangulation import (
    build_triangulation_groups, chromosome_label, X_CHROMOSOME,
)
from ancestry.models import DnaMatch, SharedMatch
from ancestry.tools import import_segments


MBP = 1_000_000


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)
    yield database
    database.close()
    if os.path.exists(path):
        os.unlink(path)


def _seg(match_guid, chrom, start, end, cm, test_guid="kit-1", is_ibd2=0):
    return {"test_guid": test_guid, "match_guid": match_guid,
            "chromosome": chrom, "start_location": start, "end_location": end,
            "length_cm": cm, "snp_count": 1000, "fetched_at": "2026-01-01",
            "is_ibd2": is_ibd2}


def _share(db, a, b, test_guid="kit-1"):
    db.upsert_shared_match(SharedMatch(
        test_guid=test_guid, match_guid_a=a, match_guid_b=b,
        shared_cm_ab=30.0, fetched_at="2026-01-01"))


# ── Triangulation ─────────────────────────────────────────────────────────────


def test_tg_requires_overlap_and_shared_match(db):
    db.bulk_upsert_segments([
        _seg("A", 5, 10 * MBP, 60 * MBP, 25.0),
        _seg("B", 5, 20 * MBP, 70 * MBP, 22.0),
        _seg("C", 5, 25 * MBP, 65 * MBP, 20.0),
    ])
    _share(db, "A", "B")
    _share(db, "B", "C")
    tgs = build_triangulation_groups(db, "kit-1")
    assert len(tgs) == 1
    tg = tgs[0]
    assert tg["chromosome"] == 5
    assert {m["match_guid"] for m in tg["members"]} == {"A", "B", "C"}
    # Region = Schnittmenge aller Segmente
    assert tg["region_start"] == 25 * MBP
    assert tg["region_end"] == 60 * MBP


def test_overlap_without_shared_match_is_no_tg(db):
    db.bulk_upsert_segments([
        _seg("A", 3, 10 * MBP, 50 * MBP, 20.0),
        _seg("B", 3, 15 * MBP, 55 * MBP, 20.0),
    ])
    # kein shared_matches-Eintrag → Überlappung allein reicht nicht
    assert build_triangulation_groups(db, "kit-1") == []


def test_shared_match_without_overlap_is_no_tg(db):
    db.bulk_upsert_segments([
        _seg("A", 7, 10 * MBP, 20 * MBP, 12.0),
        _seg("B", 7, 80 * MBP, 95 * MBP, 14.0),
    ])
    _share(db, "A", "B")
    assert build_triangulation_groups(db, "kit-1") == []


def test_min_cm_filters_small_segments(db):
    db.bulk_upsert_segments([
        _seg("A", 1, 10 * MBP, 50 * MBP, 6.0),
        _seg("B", 1, 15 * MBP, 55 * MBP, 6.0),
    ])
    _share(db, "A", "B")
    assert build_triangulation_groups(db, "kit-1", min_cm=7.0) == []
    assert len(build_triangulation_groups(db, "kit-1", min_cm=5.0)) == 1


def test_separate_chromosomes_separate_tgs(db):
    db.bulk_upsert_segments([
        _seg("A", 2, 10 * MBP, 50 * MBP, 20.0),
        _seg("B", 2, 15 * MBP, 55 * MBP, 20.0),
        _seg("A", 9, 10 * MBP, 50 * MBP, 18.0),
        _seg("C", 9, 15 * MBP, 55 * MBP, 18.0),
    ])
    _share(db, "A", "B")
    _share(db, "A", "C")
    tgs = build_triangulation_groups(db, "kit-1")
    assert [(t["chromosome"], len(t["members"])) for t in tgs] == [(2, 2), (9, 2)]


def test_overlap_measured_in_cm_not_bp(db):
    """Zwei Segmente mit großer bp-Überlappung, aber sehr niedriger cM-Dichte
    (wenig cM auf viel bp) bilden KEINE TG, wenn die cM-Overlap-Schwelle greift."""
    # 40 Mbp Überlappung, aber nur ~1 cM Segmentlänge → cM-Overlap << 5 cM
    db.bulk_upsert_segments([
        _seg("A", 8, 10 * MBP, 60 * MBP, 1.0),
        _seg("B", 8, 15 * MBP, 65 * MBP, 1.0),
    ])
    _share(db, "A", "B")
    # min_cm=0 lässt die kurzen Segmente durch, aber der cM-Overlap ist winzig
    assert build_triangulation_groups(db, "kit-1", min_cm=0.0,
                                      min_overlap_cm=5.0) == []


def test_chain_without_common_region_does_not_inflate(db):
    """A–B und B–C überlappen, aber A und C nicht → KEINE TG über das ganze
    Chromosom, sondern zwei Untergruppen mit echtem gemeinsamem Bereich."""
    db.bulk_upsert_segments([
        _seg("A", 4,  1 * MBP, 40 * MBP, 20.0),
        _seg("B", 4, 15 * MBP, 60 * MBP, 20.0),
        _seg("C", 4, 45 * MBP, 90 * MBP, 20.0),   # A∩C leer
    ])
    _share(db, "A", "B")
    _share(db, "B", "C")
    tgs = build_triangulation_groups(db, "kit-1")
    # Kein einziger TG darf das ganze Chromosom (1–90 Mb) beanspruchen
    for tg in tgs:
        span = tg["region_end"] - tg["region_start"]
        assert span < 80 * MBP
        assert tg["region_end"] > tg["region_start"]     # echte Schnittmenge
    # A,C nie zusammen in einer Gruppe (sie überlappen nicht)
    for tg in tgs:
        guids = {m["match_guid"] for m in tg["members"]}
        assert not {"A", "C"} <= guids


def test_strict_requires_pairwise_shared_cm_ab(db):
    """shared_cm_b allein (ohne in-common shared_cm_ab) begründet KEINE TG."""
    db.bulk_upsert_segments([
        _seg("A", 6, 10 * MBP, 60 * MBP, 25.0),
        _seg("B", 6, 20 * MBP, 70 * MBP, 22.0),
    ])
    # Paar mit shared_cm_b, aber shared_cm_ab=0 → strikt verworfen
    db.upsert_shared_match(SharedMatch(
        test_guid="kit-1", match_guid_a="A", match_guid_b="B",
        shared_cm_b=90.0, shared_cm_ab=0.0, fetched_at="2026-01-01"))
    assert build_triangulation_groups(db, "kit-1") == []


def test_x_chromosome_label(db):
    db.bulk_upsert_segments([
        _seg("A", X_CHROMOSOME, 10 * MBP, 60 * MBP, 20.0),
        _seg("B", X_CHROMOSOME, 20 * MBP, 70 * MBP, 20.0),
    ])
    _share(db, "A", "B")
    tgs = build_triangulation_groups(db, "kit-1")
    assert tgs[0]["chromosome_label"] == "X"
    assert chromosome_label(7) == "7"


# ── X-DNA & IBD2 (Sprint 7) ──────────────────────────────────────────────────


def test_get_x_dna_matches_aggregates_chr23(db):
    db.bulk_upsert_segments([
        _seg("A", 23, 10 * MBP, 60 * MBP, 20.0),
        _seg("A", 23, 70 * MBP, 90 * MBP, 8.0),
        _seg("B", 5,  10 * MBP, 60 * MBP, 25.0),   # autosomal → nicht X
    ])
    rows = db.get_x_dna_matches("kit-1")
    assert len(rows) == 1
    assert rows[0]["match_guid"] == "A"
    assert rows[0]["x_cm"] == 28.0
    assert rows[0]["x_segments"] == 2
    assert rows[0]["longest_x_cm"] == 20.0


def test_get_x_dna_matches_min_cm(db):
    db.bulk_upsert_segments([_seg("A", 23, 10 * MBP, 20 * MBP, 4.0)])
    assert db.get_x_dna_matches("kit-1", min_cm=7.0) == []


def test_get_ibd2_matches(db):
    db.bulk_upsert_segments([
        _seg("A", 1, 10 * MBP, 60 * MBP, 40.0, is_ibd2=1),
        _seg("A", 2, 10 * MBP, 60 * MBP, 30.0, is_ibd2=0),   # IBD1 → ignoriert
        _seg("B", 3, 10 * MBP, 60 * MBP, 25.0, is_ibd2=0),
    ])
    rows = db.get_ibd2_matches("kit-1")
    assert len(rows) == 1
    assert rows[0]["match_guid"] == "A"
    assert rows[0]["ibd2_cm"] == 40.0
    assert rows[0]["ibd2_segments"] == 1


def test_ibd2_defaults_to_zero(db):
    """Segmente ohne is_ibd2-Feld gelten als IBD1 (rückwärtskompatibel)."""
    db.bulk_upsert_segments([{
        "test_guid": "kit-1", "match_guid": "A", "chromosome": 1,
        "start_location": 10 * MBP, "end_location": 60 * MBP,
        "length_cm": 40.0, "snp_count": 1000, "fetched_at": "2026-01-01",
    }])
    assert db.get_ibd2_matches("kit-1") == []
    assert db.get_segments("kit-1")[0]["is_ibd2"] == 0


# ── Segment-Import ────────────────────────────────────────────────────────────


def test_parse_chromosome():
    assert import_segments.parse_chromosome("1") == 1
    assert import_segments.parse_chromosome("22") == 22
    assert import_segments.parse_chromosome("X") == 23
    assert import_segments.parse_chromosome("x") == 23
    assert import_segments.parse_chromosome("chr5") == 5
    assert import_segments.parse_chromosome("MT") == 0
    assert import_segments.parse_chromosome("99") == 0


def test_detect_format():
    assert import_segments.detect_format(
        ["PrimaryKit", "MatchedKit", "chr", "B37 Start", "B37 End",
         "Segment cM", "SNPs", "MatchedName"]) == "gedmatch"
    assert import_segments.detect_format(
        ["Name", "Match name", "Chromosome", "Start Location", "End Location",
         "Start RSID", "End RSID", "Centimorgans", "SNPs"]) == "myheritage"
    assert import_segments.detect_format(
        ["Match Name", "Chromosome", "Start Location", "End Location",
         "Centimorgans", "Matching SNPs"]) == "ftdna"
    assert import_segments.detect_format(["foo", "bar"]) == ""


def test_import_gedmatch_csv(db, tmp_path):
    csv_file = tmp_path / "gm.csv"
    csv_file.write_text(
        "PrimaryKit,MatchedKit,chr,B37 Start,B37 End,Segment cM,SNPs,MatchedName\n"
        "AB1,XY9,5,10000000,60000000,25.4,5100,Maria Beispiel\n"
        "AB1,XY9,X,1000000,9000000,11.0,900,Maria Beispiel\n"
        "AB1,ZZ2,5,12000000,58000000,22.0,4800,Hans Muster\n",
        encoding="utf-8")
    res = import_segments.run(csv_file, db_file=db.db_file)
    assert res["format"] == "gedmatch"
    assert res["imported"] == 3
    segs = db.get_segments("gedmatch-self")
    assert {s["match_guid"] for s in segs} == {"gm-XY9", "gm-ZZ2"}
    assert any(s["chromosome"] == 23 for s in segs)


def test_import_myheritage_csv_resolves_names(db, tmp_path):
    db.upsert_match(DnaMatch(match_guid="mh-1", test_guid="kit-1",
                             display_name="Maria Beispiel", shared_cm=40))
    csv_file = tmp_path / "mh.csv"
    csv_file.write_text(
        "Name,Match name,Chromosome,Start Location,End Location,"
        "Start RSID,End RSID,Centimorgans,SNPs\n"
        "Ich,Maria Beispiel,5,10000000,60000000,rs1,rs2,25.4,5100\n"
        "Ich,Unbekannte Person,5,12000000,58000000,rs3,rs4,22.0,4800\n",
        encoding="utf-8")
    res = import_segments.run(csv_file, kit_guid="kit-1", db_file=db.db_file)
    assert res["imported"] == 1
    assert "Unbekannte Person" in res["unresolved"]
    segs = db.get_segments("kit-1")
    assert segs[0]["match_guid"] == "mh-1"
