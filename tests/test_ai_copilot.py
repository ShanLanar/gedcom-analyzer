"""Tests für ancestry.core.ai_copilot — prompt-builder und Hilfsfunktionen.

Die eigentlichen Claude-API-Aufrufe werden NICHT getestet (erfordern
ANTHROPIC_API_KEY + Netzwerk). Getestet werden:
  - is_available(): korrekte Logik ohne Paket
  - availability_hint(): korrekter Text je Zustand
  - cluster_prompt(): Prompt-Struktur und Inhalt
  - gaps_prompt(): Prompt-Struktur und Inhalt
  - _cache_key(): Determinismus + Länge
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import ancestry.core.ai_copilot as copilot


# ── is_available ──────────────────────────────────────────────────────────────

class TestIsAvailable:
    def test_false_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert copilot.is_available() is False

    def test_false_with_key_but_no_package(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        # Hide anthropic even if installed
        with patch.dict(sys.modules, {"anthropic": None}):
            assert copilot.is_available() is False

    def test_true_with_key_and_mock_package(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            assert copilot.is_available() is True


# ── availability_hint ─────────────────────────────────────────────────────────

class TestAvailabilityHint:
    def test_no_package_hint(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch.dict(sys.modules, {"anthropic": None}):
            hint = copilot.availability_hint()
        assert "pip install" in hint
        assert "anthropic" in hint

    def test_no_key_hint(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            hint = copilot.availability_hint()
        assert "ANTHROPIC_API_KEY" in hint

    def test_empty_when_available(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            hint = copilot.availability_hint()
        assert hint == ""


# ── _cache_key ────────────────────────────────────────────────────────────────

class TestCacheKey:
    def test_deterministic(self):
        assert copilot._cache_key("hello") == copilot._cache_key("hello")

    def test_different_for_different_prompts(self):
        assert copilot._cache_key("a") != copilot._cache_key("b")

    def test_fixed_length(self):
        assert len(copilot._cache_key("x" * 10_000)) == 20


# ── cluster_prompt ────────────────────────────────────────────────────────────

class TestClusterPrompt:
    def _members(self, n=10, cm=100.0, name="Schmidt"):
        return [{"name": name, "cm": cm} for _ in range(n)]

    def test_returns_string(self):
        assert isinstance(copilot.cluster_prompt(1, self._members()), str)

    def test_empty_members_returns_empty(self):
        assert copilot.cluster_prompt(3, []) == ""

    def test_contains_cluster_id(self):
        prompt = copilot.cluster_prompt(42, self._members())
        assert "42" in prompt

    def test_contains_member_count(self):
        prompt = copilot.cluster_prompt(1, self._members(n=15))
        assert "15" in prompt

    def test_contains_cm_range(self):
        members = [{"name": "Müller", "cm": 80.0},
                   {"name": "Müller", "cm": 320.0}]
        prompt = copilot.cluster_prompt(1, members)
        assert "80" in prompt
        assert "320" in prompt

    def test_top_surnames_appear(self):
        members = [{"name": "Hans Müller", "cm": 100.0}] * 5
        prompt = copilot.cluster_prompt(1, members)
        assert "Müller" in prompt

    def test_prompt_in_german(self):
        prompt = copilot.cluster_prompt(1, self._members())
        assert "Deutsch" in prompt or "Genealoge" in prompt

    def test_mrca_question_included(self):
        prompt = copilot.cluster_prompt(1, self._members())
        assert "MRCA" in prompt

    def test_members_without_cm_handled(self):
        members = [{"name": "Müller"}] * 5
        prompt = copilot.cluster_prompt(1, members)
        assert "Müller" in prompt  # doesn't crash

    def test_members_with_origin(self):
        members = [{"name": "Hans Müller", "cm": 100.0,
                    "probable_origin": '{"region": "Osnabrück"}'}] * 5
        prompt = copilot.cluster_prompt(1, members)
        # origin field may appear (region extracted from probable_origin)
        assert isinstance(prompt, str)


# ── gaps_prompt ───────────────────────────────────────────────────────────────

class TestGapsPrompt:
    def _stats(self, **overrides) -> dict:
        base = {
            "total": 1000, "clustered": 500, "with_pedigree": 600,
            "with_origin": 300, "gedcom_persons": 5000, "sosa_filled": 20,
            "ml_model_exists": False, "matricula": 0,
        }
        return {**base, **overrides}

    def test_returns_string(self):
        assert isinstance(copilot.gaps_prompt(self._stats()), str)

    def test_contains_totals(self):
        prompt = copilot.gaps_prompt(self._stats(total=1234))
        assert "1234" in prompt

    def test_contains_percentages(self):
        prompt = copilot.gaps_prompt(self._stats(total=1000, clustered=500))
        assert "50%" in prompt

    def test_ml_false_shown(self):
        prompt = copilot.gaps_prompt(self._stats(ml_model_exists=False))
        assert "nein" in prompt.lower()

    def test_ml_true_shown(self):
        prompt = copilot.gaps_prompt(self._stats(ml_model_exists=True))
        assert "ja" in prompt.lower()

    def test_sosa_count_shown(self):
        prompt = copilot.gaps_prompt(self._stats(sosa_filled=17))
        assert "17" in prompt

    def test_prompt_in_german(self):
        prompt = copilot.gaps_prompt(self._stats())
        assert "Genealoge" in prompt or "Deutsch" in prompt

    def test_zero_total_no_crash(self):
        prompt = copilot.gaps_prompt(self._stats(total=0))
        assert isinstance(prompt, str)
