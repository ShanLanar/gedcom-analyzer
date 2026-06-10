"""
Segment triangulation for DNA genealogy.

A Triangulation Group (TG) is a set of DNA matches who:
  1. All share overlapping segments on the same chromosomal region, and
  2. Are confirmed to share DNA with each other (via shared_matches table).

Connected components (not cliques) are used: if A-B and B-C share, all
three form one TG even without a direct A-C record, which mirrors typical
genealogical practice.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ancestry.core.database import Database


def build_triangulation_groups(
    db: "Database",
    test_guid: str,
    min_cm: float = 7.0,
    min_overlap_cm: float = 5.0,
) -> list[dict]:
    """
    Return a list of Triangulation Groups for *test_guid*.

    Each TG dict has:
      chromosome   int
      region_start int   (intersection start of all member segments)
      region_end   int   (intersection end of all member segments)
      members      list of dicts: {match_guid, length_cm, start, end}
    """
    segments = db.get_segments(test_guid, min_cm=min_cm)
    if not segments:
        return []

    shared_pairs = db.get_shared_pairs_set(test_guid)

    by_chrom: dict[int, list[dict]] = defaultdict(list)
    for seg in segments:
        by_chrom[seg["chromosome"]].append(seg)

    tgs: list[dict] = []

    for chrom in sorted(by_chrom):
        segs = sorted(by_chrom[chrom], key=lambda s: s["start_location"])
        n = len(segs)
        if n < 2:
            continue

        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        for i in range(n):
            for j in range(i + 1, n):
                if segs[j]["start_location"] > segs[i]["end_location"]:
                    break
                overlap_start = max(segs[i]["start_location"], segs[j]["start_location"])
                overlap_end   = min(segs[i]["end_location"],   segs[j]["end_location"])
                if overlap_end - overlap_start < min_overlap_cm * 1_000_000:
                    continue
                pair = frozenset({segs[i]["match_guid"], segs[j]["match_guid"]})
                if pair in shared_pairs:
                    union(i, j)

        comp: dict[int, list[int]] = defaultdict(list)
        for idx in range(n):
            comp[find(idx)].append(idx)

        for indices in comp.values():
            if len(indices) < 2:
                continue
            members = [segs[k] for k in indices]
            region_start = max(s["start_location"] for s in members)
            region_end   = min(s["end_location"]   for s in members)
            if region_end <= region_start:
                region_start = min(s["start_location"] for s in members)
                region_end   = max(s["end_location"]   for s in members)
            tgs.append({
                "chromosome":   chrom,
                "region_start": region_start,
                "region_end":   region_end,
                "members": [
                    {
                        "match_guid": s["match_guid"],
                        "length_cm":  s["length_cm"],
                        "start":      s["start_location"],
                        "end":        s["end_location"],
                    }
                    for s in members
                ],
            })

    tgs.sort(key=lambda t: (t["chromosome"], t["region_start"]))
    return tgs
