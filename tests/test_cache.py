"""Tests für lib.cache – LRU-Verhalten."""
from lib.cache import GenealogyCache


def _indi():
    return {f"@P{i}@": {} for i in range(10)}


def test_cache_hit_miss_counters():
    c = GenealogyCache(max_size=5)
    c.get_ancestors("@P0@", _indi(), {})
    c.get_ancestors("@P0@", _indi(), {})
    assert c.stats["hits"] == 1
    assert c.stats["misses"] == 1


def test_cache_evicts_least_recently_used():
    c = GenealogyCache(max_size=3)
    indi = _indi()
    # 3 Misses füllen den Cache.
    c.get_ancestors("@P0@", indi, {})
    c.get_ancestors("@P1@", indi, {})
    c.get_ancestors("@P2@", indi, {})
    # Touch @P0@ macht es jüngst-benutzt; @P1@ wird damit zum ältesten.
    c.get_ancestors("@P0@", indi, {})
    c.get_ancestors("@P3@", indi, {})  # verdrängt @P1@
    assert "@P1@" not in c.ancestor_cache
    assert {"@P0@", "@P2@", "@P3@"} == set(c.ancestor_cache)


def test_cache_clear():
    c = GenealogyCache(max_size=5)
    c.get_ancestors("@P0@", _indi(), {})
    c.clear()
    assert len(c.ancestor_cache) == 0
    assert c.stats == {"hits": 0, "misses": 0}
