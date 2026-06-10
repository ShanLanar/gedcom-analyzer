from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ancestry.core.database import Database


class PedigreeRepo:
    def __init__(self, db: "Database"):
        self._db = db

    def get_matches_needing_pedigree(self, test_guid: str, min_cm: float = 0.0,
                                      force: bool = False) -> list:
        skip_fetched = "" if force else "AND COALESCE(pedigree_fetched,0)=0 "
        with self._db._cursor() as cur:
            cur.execute(
                "SELECT match_guid, display_name FROM matches "
                "WHERE test_guid=? AND has_tree=1 "
                f"{skip_fetched}AND shared_cm>=? "
                "ORDER BY shared_cm DESC", (test_guid, min_cm))
            return [(r["match_guid"], r["display_name"]) for r in cur.fetchall()]

    def save_match_pedigree(self, test_guid: str, match_guid: str, ancestors: list):
        with self._db._cursor() as cur:
            cur.execute("DELETE FROM match_pedigree WHERE test_guid=? AND match_guid=?",
                        (test_guid, match_guid))
            for a in ancestors:
                cur.execute("""
                    INSERT OR REPLACE INTO match_pedigree
                      (test_guid, match_guid, generation, ahnen_path, person_id,
                       given_name, surname, is_male, birth_year, birth_date,
                       birth_place, death_year, death_date, death_place)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (test_guid, match_guid, a.get("generation", 0),
                      a.get("ahnen_path", ""), a.get("person_id", ""),
                      a.get("given_name", ""), a.get("surname", ""),
                      1 if a.get("is_male") else 0,
                      a.get("birth_year", ""), a.get("birth_date", ""),
                      a.get("birth_place", ""), a.get("death_year", ""),
                      a.get("death_date", ""), a.get("death_place", "")))
            cur.execute("UPDATE matches SET pedigree_fetched=1 "
                        "WHERE match_guid=? AND test_guid=?", (match_guid, test_guid))

    def get_pedigree_for_match(self, test_guid: str, match_guid: str) -> list:
        with self._db._cursor() as cur:
            cur.execute(
                "SELECT * FROM match_pedigree WHERE test_guid=? AND match_guid=? "
                "ORDER BY generation, ahnen_path", (test_guid, match_guid))
            return [dict(r) for r in cur.fetchall()]

    def get_all_pedigrees(self, test_guid: str) -> dict:
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT p.match_guid, m.display_name, m.shared_cm,
                       m.has_common_ancestor,
                       COALESCE(m.linked_in_tree,0) AS linked_in_tree,
                       p.generation,
                       p.ahnen_path, p.given_name, p.surname, p.birth_year,
                       p.birth_place, p.death_year
                FROM match_pedigree p
                JOIN matches m ON m.match_guid=p.match_guid AND m.test_guid=p.test_guid
                WHERE p.test_guid=? AND p.generation>=2
                ORDER BY m.shared_cm DESC, p.generation, p.ahnen_path
            """, (test_guid,))
            rows = cur.fetchall()
        out: dict = {}
        for r in rows:
            g = out.setdefault(r["match_guid"], {
                "name": r["display_name"], "cm": r["shared_cm"],
                "linked": bool(r["linked_in_tree"] or r["has_common_ancestor"]),
                "rows": []})
            g["rows"].append(dict(r))
        return out

    def get_matches_needing_ancestors(self, test_guid: str, min_cm: float = 0.0) -> list:
        with self._db._cursor() as cur:
            cur.execute(
                "SELECT match_guid, display_name FROM matches "
                "WHERE test_guid=? AND (has_tree=1 OR has_common_ancestor=1) "
                "AND COALESCE(ancestors_fetched,0)=0 AND shared_cm>=? "
                "ORDER BY shared_cm DESC", (test_guid, min_cm))
            return [(r["match_guid"], r["display_name"]) for r in cur.fetchall()]

    def save_match_ancestors(self, test_guid: str, match_guid: str,
                             ancestors: list, birthplaces: list):
        with self._db._cursor() as cur:
            cur.execute("DELETE FROM match_ancestors WHERE test_guid=? AND match_guid=?",
                        (test_guid, match_guid))
            for a in ancestors:
                cur.execute("""
                    INSERT OR REPLACE INTO match_ancestors
                      (test_guid, match_guid, ancestor_name, birth_year, death_year,
                       is_male, relationship_to_sample, relationship_to_match,
                       kinship_path_sample, kinship_path_match, in_match_tree, amt_gid)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (test_guid, match_guid,
                      a.get("ancestor_name",""), a.get("birth_year",""),
                      a.get("death_year",""), 1 if a.get("is_male") else 0,
                      a.get("relationship_to_sample",""), a.get("relationship_to_match",""),
                      a.get("kinship_path_sample",""), a.get("kinship_path_match",""),
                      1 if a.get("in_match_tree") else 0, a.get("amt_gid","")))
            cur.execute("DELETE FROM match_birthplaces WHERE test_guid=? AND match_guid=?",
                        (test_guid, match_guid))
            for b in birthplaces:
                cur.execute("""
                    INSERT OR REPLACE INTO match_birthplaces
                      (test_guid, match_guid, side, place_name, coords, person_count)
                    VALUES (?,?,?,?,?,?)
                """, (test_guid, match_guid, b.get("side","match"),
                      b.get("place_name",""), b.get("coords",""),
                      int(b.get("person_count",0) or 0)))
            cur.execute("UPDATE matches SET ancestors_fetched=1 "
                        "WHERE match_guid=? AND test_guid=?", (match_guid, test_guid))

    def get_pedigree_groups(self, test_guid: str, min_matches: int = 2,
                            mode: str = "person", only_guids: list = None) -> list:
        sql = """
            SELECT p.given_name, p.surname, p.birth_year, p.birth_place,
                   p.generation, p.ahnen_path, p.match_guid,
                   m.display_name, m.shared_cm
            FROM match_pedigree p
            JOIN matches m ON m.match_guid=p.match_guid AND m.test_guid=p.test_guid
            WHERE p.test_guid=? AND p.generation>=2
        """
        params = [test_guid]
        if only_guids:
            sql += " AND p.match_guid IN (%s)" % ",".join("?" * len(only_guids))
            params.extend(only_guids)
        with self._db._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        groups: dict = {}
        for r in rows:
            given, sur = (r["given_name"] or "").strip(), (r["surname"] or "").strip()
            if mode == "surname":
                if not sur:
                    continue
                key, label, detail = ("S:"+sur.lower(), sur, "Nachname")
            elif mode == "place":
                place = (r["birth_place"] or "").strip()
                if not place:
                    continue
                key, label, detail = ("P:"+place.lower(), place, "Geburtsort")
            else:  # person
                if not (given or sur):
                    continue
                name = (given + " " + sur).strip()
                yr = r["birth_year"] or ""
                key = "N:" + name.lower() + "|" + yr
                label, detail = name, (f"*{yr}" if yr else "")
            g = groups.setdefault(key, {"label": label, "detail": detail,
                                        "_seen": set(), "matches": []})
            if mode == "person" and not g.get("birth_place"):
                bp = (r["birth_place"] or "").strip()
                if bp:
                    g["birth_place"] = bp
            if r["match_guid"] in g["_seen"]:
                continue
            g["_seen"].add(r["match_guid"])
            g["matches"].append((r["match_guid"], r["display_name"],
                                 r["ahnen_path"], r["generation"], r["shared_cm"]))
        out = []
        for g in groups.values():
            if len(g["matches"]) >= min_matches:
                g.pop("_seen", None)
                out.append(dict(count=len(g["matches"]), **g))
        out.sort(key=lambda g: g["count"], reverse=True)
        return out

    def get_ancestors_for_match(self, match_guid: str) -> list:
        with self._db._cursor() as cur:
            cur.execute("SELECT * FROM match_ancestors WHERE match_guid=? "
                        "ORDER BY length(kinship_path_sample), ancestor_name",
                        (match_guid,))
            return [dict(r) for r in cur.fetchall()]

    def get_ancestor_groups(self, test_guid: str, min_matches: int = 2) -> list:
        with self._db._cursor() as cur:
            cur.execute("""
                SELECT a.ancestor_name, a.birth_year,
                       a.match_guid, m.display_name, a.kinship_path_sample, m.shared_cm
                FROM match_ancestors a
                JOIN matches m ON m.match_guid=a.match_guid AND m.test_guid=a.test_guid
                WHERE a.test_guid=? AND a.ancestor_name<>''
                ORDER BY a.ancestor_name, a.birth_year, m.shared_cm DESC
            """, (test_guid,))
            rows = cur.fetchall()
        groups: dict = {}
        for r in rows:
            key = (r["ancestor_name"], r["birth_year"] or "")
            g = groups.setdefault(key, {"ancestor_name": r["ancestor_name"],
                                        "birth_year": r["birth_year"] or "",
                                        "matches": []})
            g["matches"].append((r["match_guid"], r["display_name"],
                                 r["kinship_path_sample"], r["shared_cm"]))
        out = [dict(count=len(g["matches"]), **g) for g in groups.values()
               if len(g["matches"]) >= min_matches]
        out.sort(key=lambda g: g["count"], reverse=True)
        return out

    def get_pedigree_summary_for_match(self, test_guid: str, match_guid: str) -> str:
        with self._db._cursor() as cur:
            rows = cur.execute(
                """SELECT generation, COUNT(*) AS cnt FROM match_pedigree
                   WHERE test_guid=? AND match_guid=?
                   GROUP BY generation ORDER BY generation""",
                (test_guid, match_guid)
            ).fetchall()
        if not rows:
            return ""
        gen_counts = {r["generation"]: r["cnt"] for r in rows}
        max_gen = max(gen_counts)
        total = sum(gen_counts.values())
        possible = sum(2 ** (g - 1) for g in range(1, max_gen + 1))
        pct = round(total / possible * 100) if possible else 0
        return f"{max_gen} Gen. · {total} Personen ({pct}%)"

    def get_pedigree_completeness_per_match(self, test_guid: str) -> list:
        with self._db._cursor() as cur:
            rows = cur.execute(
                """SELECT a.match_guid, m.display_name, m.shared_cm,
                          a.generation, COUNT(*) AS count
                   FROM match_pedigree a
                   JOIN matches m ON m.match_guid = a.match_guid
                   WHERE m.test_guid = ?
                   GROUP BY a.match_guid, a.generation
                   ORDER BY m.shared_cm DESC, a.generation""",
                (test_guid,)
            ).fetchall()
        result = {}
        for r in rows:
            guid = r["match_guid"]
            if guid not in result:
                result[guid] = {
                    "match_guid": guid,
                    "display_name": r["display_name"],
                    "shared_cm": r["shared_cm"],
                    "generations": {}
                }
            result[guid]["generations"][r["generation"]] = r["count"]
        return list(result.values())

    def get_cluster_ancestor_years(self, test_guid: str, match_guids: list) -> list:
        if not match_guids:
            return []
        placeholders = ",".join("?" * len(match_guids))
        with self._db._cursor() as cur:
            rows = cur.execute(
                f"""SELECT a.given_name, a.surname, a.birth_year, a.birth_place, a.generation
                    FROM match_pedigree a
                    JOIN matches m ON m.match_guid = a.match_guid
                    WHERE m.test_guid = ?
                      AND a.match_guid IN ({placeholders})
                      AND a.birth_year != ''
                      AND CAST(a.birth_year AS INTEGER) BETWEEN 1600 AND 1960
                    ORDER BY CAST(a.birth_year AS INTEGER)""",
                [test_guid] + list(match_guids)
            ).fetchall()
        return [dict(r) for r in rows]
