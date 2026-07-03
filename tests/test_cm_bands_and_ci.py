"""Sprint 7: erweitertes cM-Tiefenband (bis Meiose 16) und Konfidenzintervalle."""
from ancestry.core.bridge.matching import (
    _DEPTH_CM_BAND, _MAX_BAND_DEPTH, _cm_consistency,
)
from tasks.dna_predict import predict_relationship_detailed


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
