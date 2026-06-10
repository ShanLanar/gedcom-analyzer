from __future__ import annotations
import statistics
from typing import Optional, TYPE_CHECKING

from ancestry.models import SharedMatch

if TYPE_CHECKING:
    from ancestry.core.database import Database


class SharedRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def upsert_shared_match(self, sm: SharedMatch) -> None:
        d = sm.to_dict()
        with self._db._cursor() as cur:
            cur.execute("""
                INSERT INTO shared_matches (
                    test_guid, match_guid_a, match_guid_b, display_name_b,
                    shared_cm_b, shared_cm_ab, shared_segments_b,
                    relationship_b, has_tree_b, fetched_at
                ) VALUES (
                    :test_guid, :match_guid_a, :match_guid_b, :display_name_b,
                    :shared_cm_b, :shared_cm_ab, :shared_segments_b,
                    :relationship_b, :has_tree_b, :fetched_at
                )
                ON CONFLICT(test_guid, match_guid_a, match_guid_b) DO UPDATE SET
                    display_name_b   = excluded.display_name_b,
                    shared_cm_b      = excluded.shared_cm_b,
                    shared_cm_ab     = excluded.shared_cm_ab,
                    shared_segments_b= excluded.shared_segments_b,
                    relationship_b   = excluded.relationship_b,
                    has_tree_b       = excluded.has_tree_b,
                    fetched_at       = excluded.fetched_at
            """, d)

    def bulk_upsert_shared(self, items: list[SharedMatch]) -> int:
        for sm in items:
            self.upsert_shared_match(sm)
        self.register_shared_stubs(items)
        return len(items)

    def register_shared_stubs(self, items: list[SharedMatch]) -> None:
        if not items:
            return
        with self._db._cursor() as cur:
            for sm in items:
                if not sm.match_guid_b:
                    continue
                cur.execute("""
                    INSERT OR IGNORE INTO matches
                        (match_guid, test_guid, display_name, shared_cm,
                         predicted_relationship)
                    VALUES (?,?,?,?,?)
                """, (sm.match_guid_b, sm.test_guid, "",
                      float(sm.shared_cm_b or 0), sm.relationship_b or ""))

    def mark_shared_fetched(self, test_guid: str, match_guid_a: str, fetched_at: str):
        with self._db._cursor() as cur:
            cur.execute("""
                INSERT INTO shared_matches_fetched(test_guid, match_guid_a, fetched_at)
                VALUES(?,?,?)
                ON CONFLICT(test_guid, match_guid_a) DO UPDATE SET fetched_at=excluded.fetched_at
            """, (test_guid, match_guid_a, fetched_at))

    def is_shared_fetched(self, test_guid: str, match_guid_a: str) -> bool:
        with self._db._cursor() as cur:
            cur.execute("""SELECT 1 FROM shared_matches_fetched
                           WHERE test_guid=? AND match_guid_a=?""",
                        (test_guid, match_guid_a))
            return cur.fetchone() is not None

    def get_shared_clusters(self, test_guid: str,
                            min_cm: float = 20.0, max_cm: float = 400.0,
                            min_size: int = 2) -> list:
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT s.match_guid_a, s.match_guid_b
                FROM shared_matches s
                JOIN matches ma ON ma.match_guid=s.match_guid_a AND ma.test_guid=s.test_guid
                JOIN matches mb ON mb.match_guid=s.match_guid_b AND mb.test_guid=s.test_guid
                WHERE s.test_guid=?
                  AND ma.shared_cm BETWEEN ? AND ?
                  AND mb.shared_cm BETWEEN ? AND ?
            """, (test_guid, min_cm, max_cm, min_cm, max_cm))
            edges = cur.fetchall()

        parent: dict = {}
        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for a, b in edges:
            union(a, b)

        undirected = set()
        for a, b in edges:
            if a != b:
                undirected.add((a, b) if a < b else (b, a))

        comps: dict = {}
        for node in list(parent.keys()):
            comps.setdefault(find(node), set()).add(node)

        edge_count: dict = {}
        for a, b in undirected:
            r = find(a)
            edge_count[r] = edge_count.get(r, 0) + 1

        guids = [g for members in comps.values() for g in members]
        info: dict = {}
        if guids:
            with self._db._cursor() as cur:
                qmarks = ",".join("?" * len(guids))
                cur.execute(f"""SELECT match_guid, display_name, shared_cm,
                                       shared_segments, longest_segment,
                                       has_common_ancestor,
                                       COALESCE(linked_in_tree,0) AS linked_in_tree
                                FROM matches WHERE test_guid=? AND match_guid IN ({qmarks})""",
                            (test_guid, *guids))
                for r in cur.fetchall():
                    info[r["match_guid"]] = (r["display_name"], r["shared_cm"],
                                             r["shared_segments"] or 0,
                                             r["longest_segment"] or 0,
                                             r["has_common_ancestor"] or 0,
                                             r["linked_in_tree"] or 0)

        from core.treematch import endogamy_flag
        out = []
        for root, members in comps.items():
            n = len(members)
            if n < min_size:
                continue
            blank = ("?", 0, 0, 0, 0, 0)
            mlist = [(g, info.get(g, blank)[0], info.get(g, blank)[1])
                     for g in members]
            mlist.sort(key=lambda x: -(x[2] or 0))
            cms  = [info.get(g, blank)[1] for g in members]
            cms  = [c for c in cms if c]
            segs = [info.get(g, blank)[2] for g in members]
            segs = [s for s in segs if s]
            longs = [info.get(g, blank)[3] for g in members]
            longs = [l for l in longs if l]
            n_thru   = sum(1 for g in members if info.get(g, blank)[4])
            n_linked = sum(1 for g in members if info.get(g, blank)[5])
            possible = n * (n - 1) / 2
            density = (edge_count.get(root, 0) / possible) if possible else 0.0
            med_cm   = statistics.median(cms) if cms else 0.0
            med_segs = statistics.median(segs) if segs else 0
            med_long = statistics.median(longs) if longs else 0.0
            _lbl, endo = endogamy_flag(med_cm, med_segs, med_long)
            out.append({"size": n, "members": mlist,
                        "density": round(density, 3),
                        "median_cm": round(med_cm, 1),
                        "median_segments": med_segs,
                        "median_longest": round(med_long, 1),
                        "endogamy": endo,
                        "n_thrulines": n_thru,
                        "n_linked": n_linked,
                        "seg_by_member": {g: (info.get(g, blank)[2],
                                              info.get(g, blank)[3]) for g in members},
                        "edges": edge_count.get(root, 0)})
        out.sort(key=lambda c: c["size"], reverse=True)
        return out

    def get_pairwise_shared(self, test_guid: str, guids: list) -> list:
        if not guids:
            return []
        gset = set(guids)
        qmarks = ",".join("?" * len(guids))
        with self._db._cursor() as cur:
            cur.execute(f"""
                SELECT match_guid_a, match_guid_b, shared_cm_ab
                FROM shared_matches
                WHERE test_guid=? AND match_guid_a IN ({qmarks})
                  AND match_guid_b IN ({qmarks}) AND shared_cm_ab > 0
            """, (test_guid, *guids, *guids))
            seen, out = set(), []
            for r in cur.fetchall():
                a, b = r["match_guid_a"], r["match_guid_b"]
                if a not in gset or b not in gset:
                    continue
                key = (a, b) if a < b else (b, a)
                if key in seen:
                    continue
                seen.add(key)
                out.append((a, b, r["shared_cm_ab"] or 0))
        out.sort(key=lambda x: -(x[2] or 0))
        return out

    def get_shared_matches(
        self,
        test_guid: str,
        match_guid_a: str,
        min_cm: float = 0.0,
        sort_asc: bool = False,
    ) -> list[SharedMatch]:
        direction = "ASC" if sort_asc else "DESC"
        with self._db._cursor() as cur:
            cur.execute(f"""
                SELECT s.*, m.display_name AS _resolved_name
                FROM shared_matches s
                LEFT JOIN matches m
                  ON m.match_guid = s.match_guid_b AND m.test_guid = s.test_guid
                WHERE s.test_guid=? AND s.match_guid_a=?
                  AND s.shared_cm_b >= ?
                ORDER BY s.shared_cm_b {direction}
            """, (test_guid, match_guid_a, min_cm))
            out = []
            for r in cur.fetchall():
                d = dict(r)
                resolved = d.pop("_resolved_name", None)
                sm = SharedMatch.from_db_row(d)
                if resolved and resolved not in ("", "Unbekannt"):
                    sm.display_name_b = resolved
                out.append(sm)
            return out

    def delete_shared_for(self, test_guid: str, match_guid_a: str):
        with self._db._cursor() as cur:
            cur.execute("DELETE FROM shared_matches WHERE test_guid=? AND match_guid_a=?",
                        (test_guid, match_guid_a))

    def reset_shared_matches(self, test_guid: str) -> int:
        with self._db._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM shared_matches WHERE test_guid=?", (test_guid,))
            n = cur.fetchone()[0]
            cur.execute("DELETE FROM shared_matches WHERE test_guid=?", (test_guid,))
            cur.execute("DELETE FROM shared_matches_fetched WHERE test_guid=?", (test_guid,))
        return n

    def get_shared_match_count(self, test_guid: str,
                                match_guid_a: Optional[str] = None) -> int:
        with self._db._cursor() as cur:
            if match_guid_a:
                cur.execute("""SELECT COUNT(*) FROM shared_matches
                               WHERE test_guid=? AND match_guid_a=?""",
                            (test_guid, match_guid_a))
            else:
                cur.execute("SELECT COUNT(*) FROM shared_matches WHERE test_guid=?",
                            (test_guid,))
            return cur.fetchone()[0]

    def get_shared_pairs_set(self, test_guid: str) -> set:
        """Return all shared-match pairs as frozensets for O(1) lookup."""
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT match_guid_a, match_guid_b
                FROM shared_matches
                WHERE test_guid = ?
            """, (test_guid,))
            return {frozenset((r[0], r[1])) for r in cur.fetchall()}

    def get_all_shared_for_cluster(self, test_guid: str,
                                    min_cm_primary: float = 20.0,
                                    min_cm_shared: float = 20.0,
                                    max_cm_primary: float = 400.0,
                                    max_cm_shared: float = 400.0) -> list[dict]:
        conds  = ["sm.test_guid = ?", "m_a.shared_cm >= ?", "sm.shared_cm_b >= ?"]
        params = [test_guid, min_cm_primary, min_cm_shared]
        if max_cm_primary and max_cm_primary > 0:
            conds.append("m_a.shared_cm <= ?");   params.append(max_cm_primary)
        if max_cm_shared and max_cm_shared > 0:
            conds.append("sm.shared_cm_b <= ?");  params.append(max_cm_shared)

        with self._db._cursor() as cur:
            cur.execute(f"""
                SELECT
                    sm.match_guid_a,
                    m_a.display_name    AS name_a,
                    m_a.shared_cm       AS cm_a,
                    m_a.predicted_relationship AS rel_a,
                    sm.match_guid_b,
                    sm.display_name_b   AS name_b,
                    sm.shared_cm_b      AS cm_b,
                    sm.relationship_b   AS rel_b
                FROM shared_matches sm
                JOIN matches m_a ON m_a.match_guid = sm.match_guid_a
                WHERE {" AND ".join(conds)}
                ORDER BY m_a.shared_cm DESC, sm.shared_cm_b DESC
            """, params)
            return [dict(r) for r in cur.fetchall()]
