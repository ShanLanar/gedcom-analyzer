"""Tests für die DNA-Endogamie-Heuristik (EPIC 3)."""
from ancestry.core.endogamy_dna import (
    avg_segment_cm,
    endogamy_score,
    is_endogamy_suspect,
)


def test_score_and_avg():
    assert endogamy_score(99.0, 10) == 0.1
    assert avg_segment_cm(100.0, 10) == 10.0
    assert avg_segment_cm(100.0, 0) == 0.0


def test_suspect_many_short_segments():
    # 12 Segmente auf 60 cM -> Ø 5 cM, score 12/61 ≈ 0.197 > 0.15 -> Verdacht
    assert is_endogamy_suspect(60.0, 12)


def test_not_suspect_few_long_segments():
    # 2 Segmente auf 120 cM -> Ø 60 cM -> kein Verdacht
    assert not is_endogamy_suspect(120.0, 2)


def test_min_segments_gate():
    # hoher Score, aber zu wenige Segmente -> kein Verdacht
    assert not is_endogamy_suspect(2.0, 3, min_segments=5)


def test_max_avg_gate():
    # viele Segmente, aber grosse Durchschnittslänge -> kein Verdacht
    assert not is_endogamy_suspect(200.0, 8, max_avg_cm=12.0)  # Ø 25 cM


def test_zero_cm():
    assert not is_endogamy_suspect(0.0, 10)
    assert endogamy_score(0.0, 0) == 0.0


def test_auto_flag_endogamy_db_roundtrip(tmp_path):
    """End-to-End: verdächtige Matches werden markiert, unauffällige nicht,
    manuelle Annotationen bleiben erhalten."""
    from ancestry.core.database import Database
    from ancestry.models import DnaKit, DnaMatch

    db = Database(str(tmp_path / "e.db"))
    db.upsert_kit(DnaKit(guid="KIT", name="K", test_type="AncestryDNA"))
    # verdächtig: viele kurze Segmente
    db.upsert_match(DnaMatch(match_guid="SUS", test_guid="KIT", display_name="S",
                             shared_cm=60.0, shared_segments=12))
    # unauffällig: wenige lange Segmente
    db.upsert_match(DnaMatch(match_guid="OK", test_guid="KIT", display_name="O",
                             shared_cm=120.0, shared_segments=2))
    # bereits manuell annotiert -> nicht überschreiben
    db.upsert_match(DnaMatch(match_guid="MAN", test_guid="KIT", display_name="M",
                             shared_cm=60.0, shared_segments=12))
    db.set_endogamy_cluster("MAN", "Ostercappeln")

    n = db.auto_flag_endogamy("KIT")
    db_rows = {m.match_guid: m for m in db.get_matches(test_guid="KIT")}
    db.close()

    assert n == 1
    assert db_rows["SUS"].endogamy_cluster == "(auto)"
    assert db_rows["OK"].endogamy_cluster == ""
    assert db_rows["MAN"].endogamy_cluster == "Ostercappeln"  # nicht überschrieben
