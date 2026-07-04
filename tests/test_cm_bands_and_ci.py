"""Sprint 7: erweitertes cM-Tiefenband (bis Meiose 16) und Konfidenzintervalle."""
from ancestry.core.bridge.matching import (
    _DEPTH_CM_BAND, _MAX_BAND_DEPTH, _MIN_BAND_DEPTH, _cm_consistency,
)
from tasks.dna_predict import predict_relationship_detailed


# ── Nahe Grade (Meiose 2/3) + Half-/Multiplikator-Korrektur ───────────────────

def test_band_covers_close_relations():
    assert _MIN_BAND_DEPTH == 2
    assert 2 in _DEPTH_CM_BAND and 3 in _DEPTH_CM_BAND


def test_close_relations_are_evaluated():
    """Vollgeschwister-Distanz (Meiose 2) wird jetzt geprüft (früher <4-Abbruch)."""
    verdict, band = _cm_consistency(2600, total_depth=2)
    assert verdict == "ok"
    assert band  # nicht leer


def test_half_relation_halves_expected_band():
    """half=True halbiert die erwartete cM (ein statt zwei gemeinsame Ahnen)."""
    # 1C-Band (Meiose 4) = 396–1397; halbiert ~198–699.
    full = _cm_consistency(900, total_depth=4)          # 900 in 396–1397 → ok
    half = _cm_consistency(900, total_depth=4, half=True)  # 900 > 699*1.4? nein
    assert full[0] == "ok"
    # bei half ist die Obergrenze ~699 → 900 > 699*1.4=978? nein → ok grenzwertig
    assert half[0] in ("ok", "high")
    assert half[1] != full[1]                            # anderes Band angezeigt


def test_multiplier_raises_expected_band():
    """Doppelte Cousins (multiplier=2) heben die erwartete cM an → hohe DNA ok."""
    single = _cm_consistency(2000, total_depth=4)        # > 1397*1.4=1956 → high
    double = _cm_consistency(2000, total_depth=4, multiplier=2)  # Band ~792–2794
    assert single[0] == "high"
    assert double[0] == "ok"


# ── _DEPTH_CM_BAND-Erweiterung ────────────────────────────────────────────────

def test_band_reaches_depth_16():
    assert _MAX_BAND_DEPTH == 16
    for d in range(4, 17):
        assert d in _DEPTH_CM_BAND, f"Tiefe {d} fehlt im Band"


def test_band_high_bound_monotonic_decreasing():
    """Mit wachsender Meiosen-Distanz sinkt die erwartete Obergrenze."""
    highs = [_DEPTH_CM_BAND[d][1] for d in range(4, 17)]
    assert highs == sorted(highs, reverse=True)


def test_deep_relation_uses_extended_band():
    """Ein 7C-Link (Tiefe 16) bei 60 cM wird jetzt als 'zu nah' bewertet
    statt bei Tiefe 12 abgeschnitten zu werden."""
    verdict, band = _cm_consistency(shared_cm=300.0, total_depth=16)
    assert verdict == "high"           # 300 cM >> erwartete ~57 cM
    assert "57" in band


def test_depth_beyond_16_clamps():
    """Noch tiefere Distanzen werden auf das tiefste Band geklemmt (kein KeyError)."""
    verdict, band = _cm_consistency(shared_cm=30.0, total_depth=25)
    assert band == _cm_consistency(30.0, 16)[1]


# ── Konfidenzintervalle im cM-Prädiktor ───────────────────────────────────────

def test_detailed_prediction_has_ci():
    res = predict_relationship_detailed(1750)
    assert res
    top = res[0]
    for key in ("label", "probability", "mean_cm", "ci_low", "ci_high"):
        assert key in top
    assert top["ci_low"] < top["mean_cm"] < top["ci_high"]


def test_ci_low_clamped_at_zero():
    """Für entfernte Grade darf die Untergrenze nicht negativ werden."""
    for d in predict_relationship_detailed(35):
        assert d["ci_low"] >= 0


def test_ambiguous_cm_lists_multiple_relations():
    """1750 cM ist mehrdeutig (Halbgeschwister/Großeltern/Onkel) — der
    Prädiktor liefert mehrere plausible Grade, nicht nur einen."""
    labels = [d["label"] for d in predict_relationship_detailed(1750)]
    assert len(labels) >= 3
