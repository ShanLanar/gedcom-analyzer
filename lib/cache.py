# -*- coding: utf-8 -*-
"""lib/cache.py – Cache für häufig berechnete genealogische Werte"""

from collections import defaultdict, deque


class GenealogyCache:
    """LRU-ähnlicher Cache für Ahnen- und Verwandtschaftspfade."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.ancestor_cache: dict = {}
        self.descendant_cache: dict = {}
        self.relationship_cache: dict = {}
        self.stats = {"hits": 0, "misses": 0, "size": 0}

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_ancestors(self, person_id, individuals, families, force_recalc=False):
        key = f"ancestors_{person_id}"
        if not force_recalc and key in self.ancestor_cache:
            self.stats["hits"] += 1
            return self.ancestor_cache[key]
        self.stats["misses"] += 1
        result = self._compute_ancestors(person_id, individuals, families)
        if len(self.ancestor_cache) >= self.max_size:
            self._evict_oldest()
        self.ancestor_cache[key] = result
        self.stats["size"] = len(self.ancestor_cache)
        return result

    def clear(self):
        self.ancestor_cache.clear()
        self.descendant_cache.clear()
        self.relationship_cache.clear()
        self.stats = {"hits": 0, "misses": 0, "size": 0}

    def get_stats(self) -> dict:
        hits = self.stats["hits"]
        total = hits + self.stats["misses"]
        return {**self.stats, "hit_rate": round(hits / max(1, total) * 100, 2),
                "cache_size": len(self.ancestor_cache)}

    # ── Internal ───────────────────────────────────────────────────────────────

    def _compute_ancestors(self, person_id, individuals, families):
        paths = defaultdict(list)
        if person_id not in individuals:
            return paths
        queue = deque([[person_id]])
        while queue:
            path = queue.popleft()
            current = path[-1]
            for fam_id in (individuals.get(current) or {}).get("FAMC", []):
                fam = families.get(fam_id)
                if not fam:
                    continue
                for parent in (fam.get("HUSB"), fam.get("WIFE")):
                    if parent and parent in individuals:
                        new_path = path + [parent]
                        paths[parent].append(new_path)
                        queue.append(new_path)
        return paths

    def _evict_oldest(self):
        if self.ancestor_cache:
            del self.ancestor_cache[next(iter(self.ancestor_cache))]
