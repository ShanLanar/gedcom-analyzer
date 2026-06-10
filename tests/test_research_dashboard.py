"""Tests für ancestry.gui.analysis.research_dashboard — pure Funktionen.

Getestet werden _score(), _steps() und ACHIEVEMENTS-Bedingungen.
GUI-Code (show_research_dashboard, _gather) wird NICHT getestet — erfordert
Tkinter-Display und Datenbank.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Mock tkinter and its sub-modules before any import
_TK = MagicMock()
for _mod in ("tkinter", "tkinter.ttk", "tkinter.scrolledtext", "tkinter.messagebox"):
    sys.modules[_mod] = _TK

# Load the module directly from its file to avoid pkg __init__ chains
_RD_PATH = (
    Path(__file__).parent.parent
    / "ancestry" / "gui" / "analysis" / "research_dashboard.py"
)
_spec = importlib.util.spec_from_file_location("_rd", _RD_PATH)
_rd   = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_rd)  # type: ignore[union-attr]

ACHIEVEMENTS = _rd.ACHIEVEMENTS
_LEVELS      = _rd._LEVELS
_score       = _rd._score
_steps       = _rd._steps


# ── Hilfsfunktion ─────────────────────────────────────────────────────────────

def _stats(**overrides) -> dict:
    base = {
        "total": 1000, "clustered": 500, "with_pedigree": 600,
        "with_origin": 300, "gedcom_persons": 5000, "sosa_filled": 20,
        "clusters": 8, "ml_model_exists": False, "matricula": 0,
        "birth_dist": 0,
    }
    return {**base, **overrides}


# ── _score ────────────────────────────────────────────────────────────────────

class TestScore:
    def test_returns_three_tuple(self):
        pts, level, dims = _score(_stats())
        assert isinstance(pts, int)
        assert isinstance(level, str)
        assert isinstance(dims, dict)

    def test_score_in_range(self):
        pts, _, _ = _score(_stats())
        assert 0 <= pts <= 100

    def test_perfect_score_is_100(self):
        s = _stats(
            total=1000, clustered=1000, with_pedigree=1000, with_origin=1000,
            sosa_filled=31, gedcom_persons=1, ml_model_exists=True,
            matricula=1, birth_dist=1,
        )
        pts, _, _ = _score(s)
        assert pts == 100

    def test_empty_score_near_zero(self):
        s = _stats(
            total=0, clustered=0, with_pedigree=0, with_origin=0,
            sosa_filled=0, gedcom_persons=0, ml_model_exists=False,
            matricula=0, birth_dist=0,
        )
        pts, _, _ = _score(s)
        assert pts == 0

    def test_level_meister_at_90(self):
        # Force score to 100 → Meister-Genealoge
        s = _stats(
            total=1000, clustered=1000, with_pedigree=1000, with_origin=1000,
            sosa_filled=31, gedcom_persons=1, ml_model_exists=True,
            matricula=1, birth_dist=1,
        )
        _, level, _ = _score(s)
        assert level == "Meister-Genealoge"

    def test_level_am_anfang_at_zero(self):
        s = _stats(
            total=0, clustered=0, with_pedigree=0, with_origin=0,
            sosa_filled=0, gedcom_persons=0, ml_model_exists=False,
            matricula=0, birth_dist=0,
        )
        _, level, _ = _score(s)
        assert level == "Am Anfang"

    def test_five_dimensions_returned(self):
        _, _, dims = _score(_stats())
        assert len(dims) == 5

    def test_dim_names(self):
        _, _, dims = _score(_stats())
        assert "Cluster" in dims
        assert "Ahnentafeln" in dims
        assert "Herkunft" in dims
        assert "Ahnen-Vollst." in dims
        assert "Quellenbreite" in dims

    def test_dim_values_in_range(self):
        _, _, dims = _score(_stats())
        for v in dims.values():
            assert 0.0 <= v <= 1.0

    def test_total_zero_no_crash(self):
        pts, level, dims = _score(_stats(total=0))
        assert isinstance(pts, int)

    def test_more_complete_higher_score(self):
        low  = _stats(clustered=0, with_pedigree=0)
        high = _stats(clustered=1000, with_pedigree=1000)
        pts_low, _, _  = _score(low)
        pts_high, _, _ = _score(high)
        assert pts_high > pts_low

    def test_quellenbreite_all_sources(self):
        s = _stats(gedcom_persons=1, ml_model_exists=True, matricula=1, birth_dist=1)
        _, _, dims = _score(s)
        assert dims["Quellenbreite"] == 1.0

    def test_quellenbreite_no_sources(self):
        s = _stats(gedcom_persons=0, ml_model_exists=False, matricula=0, birth_dist=0)
        _, _, dims = _score(s)
        assert dims["Quellenbreite"] == 0.0

    def test_sosa_filled_31_max_dim(self):
        s = _stats(sosa_filled=31)
        _, _, dims = _score(s)
        assert dims["Ahnen-Vollst."] == 1.0

    def test_score_above_50_is_aktiver_forscher_or_better(self):
        # Only care that level thresholds follow _LEVELS ordering
        thresholds = {name: thresh for thresh, name in _LEVELS}
        s = _stats(
            total=1000, clustered=600, with_pedigree=700, with_origin=500,
            sosa_filled=25, gedcom_persons=1, ml_model_exists=True,
        )
        pts, level, _ = _score(s)
        assert thresholds[level] <= pts


# ── _steps ────────────────────────────────────────────────────────────────────

class TestSteps:
    def test_returns_list(self):
        assert isinstance(_steps(_stats()), list)

    def test_max_three_steps(self):
        assert len(_steps(_stats())) <= 3

    def test_no_steps_when_all_good(self):
        s = _stats(
            total=1000, clustered=1000, with_pedigree=1000, with_origin=1000,
            gedcom_persons=1, ml_model_exists=True, sosa_filled=25, matricula=1,
        )
        steps = _steps(s)
        assert len(steps) == 1
        assert "Exzellent" in steps[0] or "✅" in steps[0]

    def test_cluster_step_when_low(self):
        s = _stats(total=1000, clustered=100)  # 10% < 50%
        steps = _steps(s)
        assert any("Cluster" in st for st in steps)

    def test_pedigree_step_when_low(self):
        s = _stats(total=1000, with_pedigree=100)  # 10% < 60%
        steps = _steps(s)
        assert any("Ahnentafel" in st for st in steps)

    def test_origin_step_when_low(self):
        s = _stats(total=1000, with_origin=100)  # 10% < 40%
        steps = _steps(s)
        assert any("Herkunft" in st or "Inferenz" in st for st in steps)

    def test_ml_step_when_gedcom_large_but_no_model(self):
        s = _stats(total=1000, clustered=600, with_pedigree=700,
                   with_origin=600, gedcom_persons=5000, ml_model_exists=False,
                   sosa_filled=25)
        steps = _steps(s)
        assert any("ML" in st or "Modell" in st for st in steps)

    def test_ml_step_not_shown_when_gedcom_too_small(self):
        s = _stats(total=1000, clustered=600, with_pedigree=700,
                   with_origin=600, gedcom_persons=100, ml_model_exists=False,
                   sosa_filled=25)
        steps = _steps(s)
        assert not any("ML" in st for st in steps)

    def test_sosa_step_when_few(self):
        s = _stats(total=1000, clustered=600, with_pedigree=700,
                   with_origin=600, gedcom_persons=0, ml_model_exists=False,
                   sosa_filled=5)
        steps = _steps(s)
        assert any("GEDCOM" in st or "Sosa" in st or "Vorfahren" in st for st in steps)

    def test_matricula_step_when_gedcom_exists_but_no_entries(self):
        s = _stats(total=1000, clustered=600, with_pedigree=700,
                   with_origin=600, gedcom_persons=5000, ml_model_exists=True,
                   sosa_filled=25, matricula=0)
        steps = _steps(s)
        assert any("Kirchenbuch" in st or "Matricula" in st for st in steps)

    def test_total_zero_no_crash(self):
        steps = _steps(_stats(total=0))
        assert isinstance(steps, list)


# ── ACHIEVEMENTS ──────────────────────────────────────────────────────────────

class TestAchievements:
    def _s(self, **kw):
        return _stats(**kw)

    def test_all_achievements_have_four_fields(self):
        for entry in ACHIEVEMENTS:
            assert len(entry) == 4
            key, emoji, label, cond = entry
            assert isinstance(key, str)
            assert isinstance(emoji, str)
            assert isinstance(label, str)
            assert callable(cond)

    def test_erste_matches_false_when_zero(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "erste_matches")
        assert cond(self._s(total=0)) is False

    def test_erste_matches_true_when_one(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "erste_matches")
        assert cond(self._s(total=1)) is True

    def test_tausend_threshold(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "tausend")
        assert cond(self._s(total=999)) is False
        assert cond(self._s(total=1000)) is True

    def test_fuenftausend_threshold(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "fuenftausend")
        assert cond(self._s(total=4999)) is False
        assert cond(self._s(total=5000)) is True

    def test_zehntausend_threshold(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "zehntausend")
        assert cond(self._s(total=9999)) is False
        assert cond(self._s(total=10000)) is True

    def test_cluster_calc(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "cluster_calc")
        assert cond(self._s(clusters=0)) is False
        assert cond(self._s(clusters=1)) is True

    def test_cluster_meister(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "cluster_meister")
        assert cond(self._s(clusters=9)) is False
        assert cond(self._s(clusters=10)) is True

    def test_ahnentafeln(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "ahnentafeln")
        assert cond(self._s(with_pedigree=50)) is False
        assert cond(self._s(with_pedigree=51)) is True

    def test_gedcom(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "gedcom")
        assert cond(self._s(gedcom_persons=0)) is False
        assert cond(self._s(gedcom_persons=1)) is True

    def test_herkunft(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "herkunft")
        assert cond(self._s(with_origin=99)) is False
        assert cond(self._s(with_origin=100)) is True

    def test_ml_pionier(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "ml_pionier")
        assert cond(self._s(ml_model_exists=False)) is False
        assert cond(self._s(ml_model_exists=True)) is True

    def test_kirchenbuch(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "kirchenbuch")
        assert cond(self._s(matricula=0)) is False
        assert cond(self._s(matricula=1)) is True

    def test_bevoelkerung(self):
        _, _, _, cond = next(a for a in ACHIEVEMENTS if a[0] == "bevoelkerung")
        assert cond(self._s(birth_dist=100)) is False
        assert cond(self._s(birth_dist=101)) is True

    def test_twelve_achievements(self):
        assert len(ACHIEVEMENTS) == 12

    def test_unique_keys(self):
        keys = [a[0] for a in ACHIEVEMENTS]
        assert len(keys) == len(set(keys))
