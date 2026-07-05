"""Tests für den persistenten KI-Cache (ancestry/core/ai_cache.py)."""
import importlib

import pytest


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_CACHE_DB", str(tmp_path / "ai_cache.db"))
    import ancestry.core.ai_cache as ac
    importlib.reload(ac)
    ac._reset_for_test()
    yield ac
    ac._reset_for_test()


def test_put_get_roundtrip(cache):
    assert cache.get("k1") is None
    cache.put("k1", "claude-haiku-4-5", "Antwort A", tokens_in=10, tokens_out=5)
    assert cache.get("k1") == "Antwort A"


def test_put_is_idempotent(cache):
    cache.put("k1", "m", "erste")
    cache.put("k1", "m", "zweite")          # überschreibt
    assert cache.get("k1") == "zweite"


def test_usage_summary_aggregates(cache):
    cache.put("a", "m", "x", tokens_in=100, tokens_out=40)
    cache.put("b", "m", "y", tokens_in=50, tokens_out=20)
    s = cache.usage_summary()
    assert s["calls"] == 2
    assert s["tokens_in"] == 150
    assert s["tokens_out"] == 60


def test_clear(cache):
    cache.put("a", "m", "x")
    cache.clear()
    assert cache.get("a") is None
    assert cache.usage_summary()["calls"] == 0


def test_persists_across_reconnect(cache, tmp_path):
    cache.put("persist", "m", "bleibt")
    cache._reset_for_test()                 # Verbindung schließen
    # Neue Verbindung auf dieselbe Datei
    assert cache.get("persist") == "bleibt"


def test_cache_key_is_model_aware():
    from ancestry.core.ai_copilot import _cache_key
    assert _cache_key("prompt", "haiku", 450) != _cache_key("prompt", "sonnet", 450)
    assert _cache_key("prompt", "haiku", 450) != _cache_key("prompt", "haiku", 900)
    assert _cache_key("p", "m", 1) == _cache_key("p", "m", 1)


def test_in_memory_lru_roundtrip_and_bound():
    """Der In-Memory-LRU liefert zurück, was er speichert, und wächst nicht
    über _CACHE_MAX (P1-2: Speicherleck vermeiden)."""
    import ancestry.core.ai_copilot as ac
    ac._CACHE.clear()
    ac._cache_put("k1", "v1")
    assert ac._cache_get("k1") == "v1"
    assert ac._cache_get("fehlt") is None
    # über die Deckelung hinaus füllen → Größe bleibt begrenzt
    for i in range(ac._CACHE_MAX + 50):
        ac._cache_put(f"key{i}", "x")
    assert len(ac._CACHE) <= ac._CACHE_MAX
    ac._CACHE.clear()
