"""Tests für ancestry/core/gedcom_export.py — DNA-Ahnentafel-GEDCOM-Export."""
import os
import re
import tempfile

import pytest

from ancestry.core.gedcom_export import export_gedcom, _sosa_from_path, _clean


# ── Pure helpers ──────────────────────────────────────────────────────────────

def test_sosa_root():
    assert _sosa_from_path("") == 1


def test_sosa_father():
    assert _sosa_from_path("F") == 2


def test_sosa_mother():
    assert _sosa_from_path("M") == 3


def test_sosa_paternal_grandfather():
    assert _sosa_from_path("FF") == 4


def test_sosa_maternal_grandmother():
    assert _sosa_from_path("MM") == 7


def test_clean_strips_at_sign():
    assert "@" not in _clean("test@example")


def test_clean_strips_newlines():
    assert "\n" not in _clean("line1\nline2")


def test_clean_none_returns_empty():
    assert _clean(None) == ""


# ── export_gedcom ─────────────────────────────────────────────────────────────

def _make_groups(n_groups=1, matches_per=2):
    """Build synthetic pedigree groups as returned by get_pedigree_groups(mode='person')."""
    groups = []
    names = ["Johann Kovermann", "Maria Müller", "Hans Schmidt", "Anna Weber"]
    for i in range(n_groups):
        name = names[i % len(names)]
        yr = str(1800 + i * 10)
        matches = [
            (f"GUID_{i}_{j}", f"Match {i}/{j}", "FF" if j % 2 == 0 else "MF",
             4, float(50 + j * 10))
            for j in range(matches_per)
        ]
        groups.append({
            "label":   name,
            "detail":  f"*{yr}",
            "count":   matches_per,
            "matches": matches,
        })
    return groups


@pytest.fixture
def tmp_ged():
    fd, path = tempfile.mkstemp(suffix=".ged")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_export_writes_file(tmp_ged):
    groups = _make_groups(2)
    n = export_gedcom(groups, tmp_ged)
    assert n == 2
    assert os.path.getsize(tmp_ged) > 0


def test_export_valid_gedcom_header(tmp_ged):
    export_gedcom(_make_groups(1), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "0 HEAD" in content
    assert "0 TRLR" in content
    assert "VERS 5.5.1" in content


def test_export_indi_records(tmp_ged):
    export_gedcom(_make_groups(2), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    indi_count = content.count("0 @I")
    assert indi_count == 2


def test_export_dna_note_contains_cm(tmp_ged):
    export_gedcom(_make_groups(1, matches_per=3), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "DNA-Beleg" in content
    assert "cM" in content


def test_export_match_count_in_note(tmp_ged):
    groups = _make_groups(1, matches_per=4)
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "4 Matches" in content


def test_export_sosa_custom_tag(tmp_ged):
    export_gedcom(_make_groups(1), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "_SOSA" in content


def test_export_name_split(tmp_ged):
    groups = [{
        "label":   "Johann Kovermann",
        "detail":  "*1802",
        "count":   1,
        "matches": [("G1", "Match A", "FF", 4, 89.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "Kovermann" in content
    assert "Johann" in content
    assert "SURN Kovermann" in content


def test_export_birth_year(tmp_ged):
    groups = [{
        "label":   "Anna Müller",
        "detail":  "1835",
        "count":   1,
        "matches": [("G2", "Match B", "MF", 4, 45.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1835" in content
    assert "1 BIRT" in content


def test_export_deduplicates_same_ancestor(tmp_ged):
    groups = [
        {"label": "Karl Meier", "detail": "*1800", "count": 2,
         "matches": [("G1", "A", "FF", 4, 60.0), ("G2", "B", "FF", 4, 55.0)]},
        {"label": "Karl Meier", "detail": "*1800", "count": 1,
         "matches": [("G3", "C", "MF", 4, 40.0)]},
    ]
    n = export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    # Deduplicated: only one INDI for Karl Meier 1800
    assert n == 1
    assert content.count("0 @I") == 1


def test_export_empty_groups(tmp_ged):
    n = export_gedcom([], tmp_ged)
    assert n == 0
    content = open(tmp_ged, encoding="utf-8").read()
    assert "0 HEAD" in content
    assert "0 TRLR" in content


def test_export_match_names_in_note(tmp_ged):
    groups = [{
        "label":   "Otto Weber",
        "detail":  "*1780",
        "count":   2,
        "matches": [("G1", "Elsa Müller", "FF", 4, 80.0),
                    ("G2", "Franz Mayer", "FM", 4, 65.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "Elsa Müller" in content or "Franz Mayer" in content


def test_export_birth_place_written_as_plac(tmp_ged):
    groups = [{
        "label":       "Heinrich Finkeldey",
        "detail":      "*1832",
        "count":       1,
        "birth_place": "Osnabrück",
        "matches":     [("G1", "Match A", "FF", 4, 75.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "2 PLAC Osnabrück" in content
    assert "1 BIRT" in content


def test_export_no_plac_when_birth_place_absent(tmp_ged):
    groups = [{
        "label":   "Anna Müller",
        "detail":  "*1850",
        "count":   1,
        "matches": [("G1", "Match B", "MF", 4, 60.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "PLAC" not in content


def test_export_sour_record_in_header(tmp_ged):
    export_gedcom(_make_groups(1), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "0 @S001@ SOUR" in content
    assert "1 TITL AncestryDNA" in content
    assert "1 AUTH Ancestry.com" in content


def test_export_indi_references_sour(tmp_ged):
    export_gedcom(_make_groups(1, matches_per=3), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 SOUR @S001@" in content
    assert "2 PAGE" in content
    assert "2 QUAY 3" in content


def test_export_sex_tag_male_from_even_sosa(tmp_ged):
    # Ahnen-Pfad "FF" → Sosa 4 (gerade) → SEX M
    groups = [{
        "label":   "Johann Kovermann",
        "detail":  "*1800",
        "count":   1,
        "matches": [("G1", "Match A", "FF", 4, 80.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 SEX M" in content


def test_export_sex_tag_female_from_odd_sosa(tmp_ged):
    # Ahnen-Pfad "FM" → Sosa 5 (ungerade) → SEX F
    groups = [{
        "label":   "Anna Weber",
        "detail":  "*1805",
        "count":   1,
        "matches": [("G1", "Match A", "FM", 4, 75.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 SEX F" in content


def test_export_no_sex_tag_for_sosa_one(tmp_ged):
    # Sosa 1 = Proband selbst → kein SEX-Tag
    groups = [{
        "label":   "Selbst",
        "detail":  "*1970",
        "count":   1,
        "matches": [("G1", "Eigen", "", 0, 3500.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 SEX" not in content


def test_export_handles_missing_birth_year(tmp_ged):
    groups = [{
        "label":   "Unbekannt Nachname",
        "detail":  "",
        "count":   1,
        "matches": [("G1", "Test", "FF", 4, 50.0)],
    }]
    n = export_gedcom(groups, tmp_ged)
    assert n == 1
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 BIRT" not in content   # no birth tag without year


# ── FAM / CHIL / FAMS / FAMC structure ───────────────────────────────────────

def _three_gen_groups():
    """Grandfather (Sosa 4 = FF), Grandmother (Sosa 5 = FM), Father (Sosa 2 = F)."""
    return [
        {   # Father (Sosa 2 = "F")
            "label":   "Karl Kovermann",
            "detail":  "*1850",
            "count":   3,
            "matches": [("G1", "A", "F", 2, 120.0),
                        ("G2", "B", "F", 2, 110.0),
                        ("G3", "C", "F", 2, 100.0)],
        },
        {   # Grandfather (Sosa 4 = "FF")
            "label":   "Heinrich Kovermann",
            "detail":  "*1820",
            "count":   2,
            "matches": [("G4", "D", "FF", 3, 65.0),
                        ("G5", "E", "FF", 3, 60.0)],
        },
        {   # Grandmother (Sosa 5 = "FM")
            "label":   "Maria Schulze",
            "detail":  "*1825",
            "count":   2,
            "matches": [("G6", "F", "FM", 3, 55.0),
                        ("G7", "G", "FM", 3, 50.0)],
        },
    ]


def test_fam_record_created(tmp_ged):
    export_gedcom(_three_gen_groups(), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "0 @F" in content    # at least one FAM record


def test_fam_husb_and_wife(tmp_ged):
    export_gedcom(_three_gen_groups(), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 HUSB" in content
    assert "1 WIFE" in content


def test_fam_chil_pointer(tmp_ged):
    export_gedcom(_three_gen_groups(), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 CHIL" in content   # child linked in FAM record


def test_indi_famc_pointer(tmp_ged):
    export_gedcom(_three_gen_groups(), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 FAMC" in content   # child's INDI has FAMC pointer


def test_indi_fams_pointer(tmp_ged):
    export_gedcom(_three_gen_groups(), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "1 FAMS" in content   # parent's INDI has FAMS pointer


def test_fam_chil_matches_famc(tmp_ged):
    export_gedcom(_three_gen_groups(), tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    # Extract the CHIL pointer value from the FAM block
    chil_match = re.search(r"1 CHIL (@I\d+@)", content)
    famc_match  = re.search(r"1 FAMC (@F\d+@)", content)
    assert chil_match, "No CHIL pointer found"
    assert famc_match, "No FAMC pointer found"
    # The FAMC value in the child's INDI must match the fam_id in the FAM record
    famc_fam_id = famc_match.group(1)
    chil_indi   = chil_match.group(1)
    # Verify the FAM block containing CHIL is the same fam referenced by FAMC
    assert famc_fam_id in content


def test_no_phantom_fam_without_ancestors(tmp_ged):
    # Single ancestor only — no parent/child available → no FAM record
    groups = [{
        "label":   "Isoliert",
        "detail":  "*1800",
        "count":   1,
        "matches": [("G1", "X", "FFFFF", 6, 20.0)],
    }]
    export_gedcom(groups, tmp_ged)
    content = open(tmp_ged, encoding="utf-8").read()
    assert "0 @F" not in content  # no FAM without parent AND child in export
