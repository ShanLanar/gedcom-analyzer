"""Tests für Sosa-Stradonitz-Nummerierung und FamilySearch-URL-Generator."""
import pytest


def _indi(iid, name, sex="M", by=None, bp="", dy=None, dp="", famc=None, fams=None):
    return iid, {
        "NAME": name, "SEX": sex,
        "FAMC": famc or [], "FAMS": fams or [],
        "BIRT": {"DATE": f"1 JAN {by}" if by else None, "YEAR": by,
                 "DATE_QUAL": "exact" if by else None, "PLAC": bp or None},
        "DEAT": {"DATE": f"1 JAN {dy}" if dy else None, "YEAR": dy,
                 "DATE_QUAL": "exact" if dy else None, "PLAC": dp or None},
        "EMIG": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "IMMI": {"DATE": None, "YEAR": None, "DATE_QUAL": None, "PLAC": None},
        "BIRTH_PLACE": bp or None,
        "MIGRATED": False, "VETERAN": False, "DIED_IN_BATTLE": False,
        "LINE_ENDS": False, "GERMAN_SOLDIER": False, "OTHER_SOLDIER": False,
    }


def _fam(fid, h=None, w=None, ch=None):
    return fid, {"HUSB": h, "WIFE": w, "CHIL": list(ch or []),
                 "MARR_DATE": None, "MARR_PLACE": None}


# ── Sosa-Stradonitz ────────────────────────────────────────────────────────────

def test_sosa_root_is_1():
    from tasks.sosa import compute_sosa_numbers
    indiv = dict([_indi("@R@", "Root /Müller/", "M", 1900)])
    sosa = compute_sosa_numbers("@R@", indiv, {})
    assert sosa["@R@"] == [1]


def test_sosa_father_is_2_mother_is_3():
    from tasks.sosa import compute_sosa_numbers
    indiv = dict([
        _indi("@R@", "Root", "M", 1900, famc=["@F@"]),
        _indi("@F@", "Vater", "M", 1870, fams=["@F@"]),
        _indi("@M@", "Mutter", "F", 1875, fams=["@F@"]),
    ])
    fams = dict([_fam("@F@", "@F@", "@M@", ["@R@"])])
    sosa = compute_sosa_numbers("@R@", indiv, fams)
    assert sosa["@F@"] == [2], f"Vater = {sosa['@F@']}, erwartet [2]"
    assert sosa["@M@"] == [3], f"Mutter = {sosa['@M@']}, erwartet [3]"


def test_sosa_grandparents_are_4_5_6_7():
    """Klassische 4 Großeltern-Nummern: 4 = PP, 5 = PM, 6 = MP, 7 = MM."""
    from tasks.sosa import compute_sosa_numbers
    indiv = dict([
        _indi("@R@",  "Root", "M",  1950, famc=["@FR@"]),
        _indi("@F@",  "Vater", "M", 1920, famc=["@FF@"], fams=["@FR@"]),
        _indi("@M@",  "Mutter", "F", 1925, famc=["@FM@"], fams=["@FR@"]),
        _indi("@PP@", "Paternal-Opa",  "M", 1890, fams=["@FF@"]),
        _indi("@PM@", "Paternal-Oma",  "F", 1895, fams=["@FF@"]),
        _indi("@MP@", "Maternal-Opa",  "M", 1892, fams=["@FM@"]),
        _indi("@MM@", "Maternal-Oma",  "F", 1898, fams=["@FM@"]),
    ])
    fams = dict([
        _fam("@FR@", "@F@",  "@M@",  ["@R@"]),
        _fam("@FF@", "@PP@", "@PM@", ["@F@"]),
        _fam("@FM@", "@MP@", "@MM@", ["@M@"]),
    ])
    sosa = compute_sosa_numbers("@R@", indiv, fams)
    assert sosa["@PP@"] == [4]
    assert sosa["@PM@"] == [5]
    assert sosa["@MP@"] == [6]
    assert sosa["@MM@"] == [7]


def test_sosa_implex_multiple_numbers():
    """Bei Cousin-Heirat hat eine Person mehrere Sosa-Nummern (Pedigree-Collapse)."""
    from tasks.sosa import compute_sosa_numbers
    # Stamm-Paar; ihre Töchter heiraten Cousins → die Stamm-Eltern sind
    # gleichzeitig PP/PM UND MP/MM für ein Inzucht-Kind
    indiv = dict([
        _indi("@A@",  "Stamm-Vater", "M", 1800, fams=["@F0@"]),
        _indi("@B@",  "Stamm-Mutter", "F", 1805, fams=["@F0@"]),
        _indi("@C1@", "Cousin1", "M", 1830, famc=["@F0@"], fams=["@FX@"]),
        _indi("@C2@", "Cousine2", "F", 1832, famc=["@F0@"], fams=["@FX@"]),
        _indi("@INB@", "Inzucht-Kind", "M", 1860, famc=["@FX@"]),
    ])
    fams = dict([
        _fam("@F0@", "@A@",  "@B@",  ["@C1@", "@C2@"]),
        _fam("@FX@", "@C1@", "@C2@", ["@INB@"]),
    ])
    sosa = compute_sosa_numbers("@INB@", indiv, fams)
    # @A@ ist gleichzeitig Vater-des-Vaters (4) UND Vater-der-Mutter (6)
    assert 4 in sosa["@A@"] and 6 in sosa["@A@"], \
        f"@A@ Sosa-Nrn = {sosa['@A@']}, erwartet [4, 6]"
    # @B@ ist gleichzeitig 5 und 7
    assert 5 in sosa["@B@"] and 7 in sosa["@B@"]


def test_sosa_to_generation():
    from tasks.sosa import sosa_to_generation
    assert sosa_to_generation(1) == 0
    assert sosa_to_generation(2) == 1   # Vater
    assert sosa_to_generation(3) == 1   # Mutter
    assert sosa_to_generation(4) == 2   # Großeltern beginnen
    assert sosa_to_generation(7) == 2
    assert sosa_to_generation(8) == 3   # Urgroßeltern
    assert sosa_to_generation(15) == 3
    assert sosa_to_generation(16) == 4


def test_sosa_to_role_basic():
    from tasks.sosa import sosa_to_role
    assert sosa_to_role(1) == "Proband"
    assert sosa_to_role(2) == "Vater"
    assert sosa_to_role(3) == "Mutter"
    # Großeltern: enthalten "Groß"
    for s in (4, 5, 6, 7):
        assert "Groß" in sosa_to_role(s), f"Sosa {s}: {sosa_to_role(s)}"


def test_sosa_ahnentafel_sorted():
    from tasks.sosa import build_sosa_ahnentafel
    indiv = dict([
        _indi("@R@",  "Root /R/", "M", 1900, famc=["@FR@"]),
        _indi("@F@",  "Vater /F/", "M", 1870, fams=["@FR@"]),
        _indi("@M@",  "Mutter /M/", "F", 1875, fams=["@FR@"]),
    ])
    fams = dict([_fam("@FR@", "@F@", "@M@", ["@R@"])])
    rows = build_sosa_ahnentafel("@R@", indiv, fams)
    sosa_nrs = [r[0] for r in rows]
    assert sosa_nrs == sorted(sosa_nrs)
    # Mindestens Root (Sosa 1), Vater (2), Mutter (3)
    assert sosa_nrs[:3] == [1, 2, 3]


# ── FamilySearch ───────────────────────────────────────────────────────────────

def test_familysearch_split_name():
    from tasks.familysearch import _split_name
    assert _split_name("Hans /Müller/") == ("Hans", "Müller")
    assert _split_name("Hans Peter /von Müller/") == ("Hans Peter", "von Müller")
    assert _split_name("Hans") == ("Hans", "")
    assert _split_name("") == ("", "")


def test_familysearch_records_url_contains_name_and_year():
    from tasks.familysearch import build_records_url
    _, p = _indi("@A@", "Hans /Müller/", "M", 1850, "Berlin")
    url = build_records_url(p)
    assert "familysearch.org/search/record/results" in url
    assert "Hans" in url
    # URL-encoded Umlaut
    assert "M%C3%BCller" in url or "Müller" in url
    assert "1848" in url or "1850" in url or "1852" in url  # ±2-Spanne


def test_familysearch_tree_url_includes_place():
    from tasks.familysearch import build_tree_url
    _, p = _indi("@A@", "Anna /Schmidt/", "F", 1880, "Hamburg, Deutschland")
    url = build_tree_url(p)
    assert "tree/results" in url
    assert "Hamburg" in url


def test_familysearch_url_empty_when_no_data():
    from tasks.familysearch import build_records_url
    _, p = _indi("@A@", "", "U")
    url = build_records_url(p)
    assert url == ""


def test_familysearch_quality_score():
    from tasks.familysearch import _search_quality_score
    # Komplett dokumentiert
    _, full = _indi("@A@", "Hans /Müller/", "M", 1850, "Berlin",
                      dy=1920, dp="Hamburg", fams=["@F@"])
    assert _search_quality_score(full) >= 90
    # Minimal
    _, sparse = _indi("@B@", "Hans", "M")
    assert _search_quality_score(sparse) < 30


def test_familysearch_lookup_sheet_sorted_by_quality():
    from tasks.familysearch import generate_familysearch_lookup_sheet
    indiv = dict([
        _indi("@A@", "Hans /Müller/", "M", 1850, "Berlin",
              dy=1920, dp="Hamburg", fams=["@F@"]),   # hohe Qualität
        _indi("@B@", "Anna /Schmidt/", "F", 1860),   # mittel
        _indi("@C@", "Hans", "M"),                   # zu wenig
    ])
    rows = generate_familysearch_lookup_sheet(indiv)
    qualities = [r[2] for r in rows]
    assert qualities == sorted(qualities, reverse=True)
    # Spalte 7 = Records-URL, Spalte 8 = Tree-URL
    assert all(r[7].startswith("https://") for r in rows if r[7])


def test_familysearch_records_url_has_birth_and_death_years():
    from tasks.familysearch import build_records_url
    _, p = _indi("@A@", "Friedrich /Bauer/", "M", 1820,
                  dy=1895, bp="München")
    url = build_records_url(p)
    # Beide Jahres-Fenster sind drin
    assert "birthLikeDate" in url
    assert "deathLikeDate" in url
