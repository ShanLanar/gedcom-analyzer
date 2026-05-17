# -*- coding: utf-8 -*-
"""lib/cache.py – Cache für häufig berechnete genealogische Werte"""

from collections import defaultdict, deque


class GenealogyCache:
    """LRU-Cache für Ahnenpfade (per Person-ID)."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        # Echter LRU: OrderedDict + move_to_end on hit.
        from collections import OrderedDict
        self.ancestor_cache: "OrderedDict[str, dict]" = OrderedDict()
        self.stats = {"hits": 0, "misses": 0}

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_ancestors(self, person_id, individuals, families):
        cache = self.ancestor_cache
        if person_id in cache:
            self.stats["hits"] += 1
            cache.move_to_end(person_id)
            return cache[person_id]
        self.stats["misses"] += 1
        result = self._compute_ancestors(person_id, individuals, families)
        cache[person_id] = result
        if len(cache) > self.max_size:
            cache.popitem(last=False)
        return result

    def clear(self):
        self.ancestor_cache.clear()
        self.stats = {"hits": 0, "misses": 0}

    def get_stats(self) -> dict:
        hits = self.stats["hits"]
        total = hits + self.stats["misses"]
        return {**self.stats,
                "hit_rate": round(hits / max(1, total) * 100, 2),
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
