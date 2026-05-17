"""Tests für tasks.names – Kölner Phonetik & Cluster-Bildung (Regression B1)."""
from tasks.names import koelner_phonetik, _levenshtein, analyze_name_morphology


def test_koelner_phonetik_known_pairs():
    # Klassiker aus der Kölner-Phonetik-Literatur:
    assert koelner_phonetik("Müller") == koelner_phonetik("Mueller")
    assert koelner_phonetik("Meier") == koelner_phonetik("Mayer")
    assert koelner_phonetik("Schmidt") == koelner_phonetik("Schmitt")


def test_koelner_phonetik_empty():
    assert koelner_phonetik("") == ""
    assert koelner_phonetik(None) == ""


def test_levenshtein():
    assert _levenshtein("abc", "abc") == 0
    assert _levenshtein("abc", "abd") == 1
    assert _levenshtein("abc", "") == 3
    assert _levenshtein("kitten", "sitting") == 3


def test_cluster_does_not_swallow_unrelated_names():
    # B1-Regression: variable shadowing im all(_similar(v, w) for v in cluster)
    # konnte unverwandte Namen fälschlicherweise in einen Cluster ziehen.
    individuals = {
        "@I1@": {"NAME": "/Müller/", "BIRT": {"DATE": "1850"}},
        "@I2@": {"NAME": "/Mueller/", "BIRT": {"DATE": "1860"}},
        "@I3@": {"NAME": "/Schmidt/", "BIRT": {"DATE": "1870"}},
        "@I4@": {"NAME": "/Schmitt/", "BIRT": {"DATE": "1880"}},
    }
    variants, _persons = analyze_name_morphology(individuals)
    # Erwartung: Müller/Mueller und Schmidt/Schmitt sind jeweils eigene Cluster,
    # NICHT gemeinsam in einem.
    all_variants = [set(row[3].split(", ")) for row in variants]
    for cluster in all_variants:
        assert not ({"Müller", "Schmidt"} <= cluster)
        assert not ({"Mueller", "Schmidt"} <= cluster)
