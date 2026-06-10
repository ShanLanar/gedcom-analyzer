"""
Stammbaum- und Pedigree-Mixin für den Ancestry-API-Client.
"""

import time
import logging
from typing import Optional

import ancestry.endpoints as cfg
from ._session import _api_get, _jitter

log = logging.getLogger(__name__)


class _PedigreeMixin:
    """Methoden für Stammbaum-Daten, gemeinsame Vorfahren und Pedigree."""

    def get_common_ancestors(self, test_guid: str,
                             sample_ids: list[str]) -> set:
        """commonAncestors → Set der sampleIds, die einen gemeinsamen Vorfahren haben."""
        if not sample_ids or self._detail_blocked:
            return set()
        url  = cfg.COMMON_ANCESTORS_URL.format(test_guid=test_guid)
        data = self._signed_post(url, {"sampleIds": list(sample_ids)},
                                 test_guid, "commonAncestors")
        return set(data) if isinstance(data, list) else set()

    def get_matches_in_tree(self, test_guid: str, sample_ids: list[str]) -> set:
        """matchesInTree → Set der sampleIds, die in DEINEM Baum verknüpft sind
        ('View in tree' – unabhängig von ThruLines/gemeinsamem Vorfahren)."""
        if not sample_ids or self._detail_blocked:
            return set()
        url  = cfg.MATCHES_IN_TREE_URL.format(test_guid=test_guid)
        data = self._signed_post(url, {"sampleIds": list(sample_ids)},
                                 test_guid, "matchesInTree")
        return set(data) if isinstance(data, list) else set()

    @staticmethod
    def _tree_status(info: dict) -> dict:
        """Wandelt treeData-Flags in {tree_status, tree_size, has_tree}."""
        size = int(info.get("treeSize") or 0)
        if info.get("hasNoTrees"):
            status, has = "Kein Baum", False
        elif info.get("isTreeUnavailable"):
            status, has = "Nicht verfügbar", False
        elif info.get("isUnlinkedTree"):
            status, has = "Unverknüpft", False
        elif info.get("isPrivateTree"):
            status, has = "Privat", True
        elif info.get("isPublicTree"):
            status, has = "Öffentlich", True
        else:
            status, has = "", False
        return {"tree_status": status, "tree_size": size, "has_tree": has}

    def get_tree_data_bulk(self, test_guid: str,
                           sid_to_ucdmid: dict) -> dict[str, dict]:
        """treeData → {sampleId: {tree_status, tree_size, has_tree}}.

        Braucht pro Match die userId (== matchUcdmid aus profileData).
        """
        match_list = [{"sampleId": sid, "matchProfile": {"userId": uc}}
                      for sid, uc in sid_to_ucdmid.items() if uc]
        if not match_list or self._detail_blocked:
            return {}
        url  = cfg.TREE_DATA_URL.format(test_guid=test_guid)
        data = self._signed_post(url, {"matchList": match_list},
                                 test_guid, "treeData")
        out = {}
        for sid, info in (data or {}).items():
            if isinstance(info, dict):
                out[sid] = self._tree_status(info)
        return out

    def get_compare_common_ancestors(self, test_guid: str, match_guid: str) -> list:
        """commonancestors → Liste von Vorfahr-Dicts (Name, *Jahr, Pfad, Seite)."""
        url = cfg.COMPARE_COMMON_ANCESTORS_URL.format(
            test_guid=test_guid, match_guid=match_guid)
        r = _api_get(self._s, url)
        if not r or r.status_code != 200:
            return []
        try:
            data = r.json()
        except ValueError as e:
            log.debug("%s JSON parse: %s", self.__class__.__name__, e)
            return []

        if not getattr(self, "_logged_ca_sample", False):
            self._logged_ca_sample = True
            import json as _dj
            log.info("commonancestors-BEISPIEL: %s",
                     _dj.dumps(data, ensure_ascii=False)[:2500])

        out = []
        for couple in (data.get("ancestorCouples") or []):
            if not isinstance(couple, dict):
                continue
            for slot in ("father", "mother"):
                anc = couple.get(slot)
                if not isinstance(anc, dict):
                    continue
                pd = anc.get("personData") or {}
                name = (pd.get("displayName") or "").strip()
                if not name or pd.get("notFound"):
                    continue
                amt = anc.get("amtGid") or {}
                out.append({
                    "ancestor_name"         : name,
                    "birth_year"            : str(pd.get("birthYear") or ""),
                    "death_year"            : str(pd.get("deathYear") or ""),
                    "is_male"               : bool(pd.get("isMale")),
                    "relationship_to_sample": anc.get("relationshipToSampleId") or "",
                    "relationship_to_match" : anc.get("relationshipFromSampleToMatch") or "",
                    "kinship_path_sample"   : anc.get("kinshipPathToSampleId") or "",
                    "kinship_path_match"    : anc.get("kinshipPathFromSampleToMatch") or "",
                    "in_match_tree"         : bool(anc.get("inMatchTree")),
                    "amt_gid"               : (amt.get("v") if isinstance(amt, dict) else "") or "",
                })
        return out

    def get_compare_tree_data(self, test_guid: str, match_guid: str) -> list:
        """completeTreeData → Geburtsorte des Match-Baums [{place,coords,count,side}]."""
        url = cfg.COMPARE_TREE_DATA_URL.format(
            test_guid=test_guid, match_guid=match_guid)
        r = _api_get(self._s, url)
        if not r or r.status_code != 200:
            return []
        try:
            data = r.json()
        except ValueError as e:
            log.debug("get_compare_tree_data JSON parse: %s", e)
            return []

        if not getattr(self, "_logged_ctd_sample", False):
            self._logged_ctd_sample = True
            import json as _dj
            log.info("completeTreeData-BEISPIEL: %s",
                     _dj.dumps(data, ensure_ascii=False)[:2000])

        out = []
        for side in ("match", "sample"):
            tree = (data.get(side) or {}).get("linkedTree") or {}
            for loc in (tree.get("birthLocations") or []):
                if not isinstance(loc, dict):
                    continue
                place = (loc.get("name") or "").strip()
                if not place:
                    continue
                out.append({
                    "side"        : side,
                    "place_name"  : place,
                    "coords"      : loc.get("coords") or "",
                    "person_count": int(loc.get("personCount") or 0),
                })
        return out

    def get_match_tree_link(self, test_guid: str, match_guid: str) -> Optional[tuple]:
        """Liefert (tree_id, focus_person_id, person_count) des verknüpften Baums."""
        url = cfg.MATCH_TREES_URL.format(test_guid=test_guid, match_guid=match_guid)
        with self._http_lock:
            r = _api_get(self._s, url)
        if not r or r.status_code != 200:
            return None
        try:
            trees = (r.json() or {}).get("trees") or []
        except ValueError as e:
            log.debug("get_tree_id_for_match JSON parse: %s", e)
            return None
        # bevorzugt den verknüpften Baum mit Person-Verknüpfung
        linked = [t for t in trees if t.get("personId")]
        linked.sort(key=lambda t: (t.get("type") != "linked",
                                   -(t.get("personCount") or 0)))
        if not linked:
            return None
        t = linked[0]
        return (str(t.get("treeId")), str(t.get("personId")),
                int(t.get("personCount") or 0))

    @staticmethod
    def _pedigree_person(p: dict) -> dict:
        """Extrahiert Name/Geschlecht/Geburt/Tod aus einem Tree-Viewer-Person-Objekt."""
        n = (p.get("Names") or [{}])[0]
        given   = "" if n.get("veiled") else (n.get("g") or "").strip()
        surname = "" if n.get("veiled") else (n.get("s") or "").strip()
        gender  = ((p.get("Genders") or [{}])[0].get("g") or "").lower()
        out = {"given_name": given, "surname": surname,
               "is_male": gender == "m",
               "birth_year": "", "birth_date": "", "birth_place": "",
               "death_year": "", "death_date": "", "death_place": ""}
        for e in (p.get("Events") or []):
            t = e.get("t")
            if t not in ("Birth", "Death"):
                continue
            if e.get("veiled"):
                continue
            nd = (e.get("nd") or "")
            dd = (e.get("d") or "")
            place = (e.get("p") or "")
            year = nd[:4] if nd[:4].isdigit() else ""
            if t == "Birth":
                out["birth_year"], out["birth_date"], out["birth_place"] = year, dd, place
            else:
                out["death_year"], out["death_date"], out["death_place"] = year, dd, place
        return out

    @staticmethod
    def _pid(g):
        try:
            return (g or {}).get("v", "").split(":")[0]
        except (AttributeError, TypeError):
            return ""

    def _fetch_pedigree_persons(self, tree_id: str, focus_pid: str,
                                is_focus: bool) -> dict:
        """Holt eine Pedigree-Antwort und liefert {pid: person}. Re-Fokussierung
        (is_focus=False) holt die Vorfahren AB dieser Person (für tiefere Gen.)."""
        url = cfg.PEDIGREE_URL.format(tree_id=tree_id, focus_pid=focus_pid,
                                      is_focus="true" if is_focus else "false")
        with self._http_lock:
            r = _api_get(self._s, url)
        if not r or r.status_code != 200:
            return {}
        try:
            data = r.json()
        except ValueError as e:
            log.debug("_fetch_pedigree_persons JSON parse: %s", e)
            return {}
        out = {}
        for p in (data.get("Persons") or []):
            pid = self._pid(p.get("gid"))
            if pid:
                out[pid] = p
        return out

    def get_pedigree(self, test_guid: str, match_guid: str,
                     max_generations: int = 5, max_extra_calls: int = 0) -> list:
        """Volle Ahnentafel eines Matches: walkt F/M ab Fokus.
        max_generations begrenzt die Tiefe; max_extra_calls erlaubt Vertiefung
        über Re-Fokussierung an den Rand-Vorfahren (für entfernte Cousins, deren
        gemeinsamer Vorfahr >5 Generationen zurückliegt).
        Liefert [{generation, ahnen_path, person_id, given_name, surname,
                  is_male, birth_*, death_*}]."""
        link = self.get_match_tree_link(test_guid, match_guid)
        if not link:
            return []
        tree_id, focus_pid, _ = link

        by_id = self._fetch_pedigree_persons(tree_id, focus_pid, True)
        if focus_pid not in by_id:
            return []

        if not getattr(self, "_logged_ped_sample", False):
            self._logged_ped_sample = True
            log.info("pedigree-BEISPIEL: tree=%s focus=%s, %d Personen",
                     tree_id, focus_pid, len(by_id))

        def _parents(p):
            f = m = None
            for fam in (p.get("Family") or []):
                if fam.get("t") == "F":
                    f = self._pid(fam.get("tgid"))
                elif fam.get("t") == "M":
                    m = self._pid(fam.get("tgid"))
            return f, m

        def _walk():
            out, seen = [], set()
            boundary = []  # (parent_pid) deren Daten fehlen, aber noch in Reichweite
            queue = [(focus_pid, 1, "")]
            while queue:
                pid, gen, path = queue.pop(0)
                if pid in seen or gen > max_generations:
                    continue
                seen.add(pid)
                p = by_id.get(pid)
                if not p:
                    continue
                rec = self._pedigree_person(p)
                rec.update(generation=gen, ahnen_path=path, person_id=pid)
                out.append(rec)
                f, m = _parents(p)
                for parent, step in ((f, "F"), (m, "M")):
                    if not parent:
                        continue
                    if parent in by_id:
                        queue.append((parent, gen + 1, path + step))
                    elif gen + 1 <= max_generations:
                        boundary.append(parent)  # fehlt → Kandidat für Re-Fokus
            return out, boundary

        # Iteratives Vertiefen per Re-Fokussierung an den Rand-Vorfahren
        extra = 0
        while extra < max_extra_calls:
            _out, boundary = _walk()
            boundary = [b for b in boundary if b not in by_id]
            if not boundary:
                break
            for pid in boundary:
                if extra >= max_extra_calls:
                    break
                more = self._fetch_pedigree_persons(tree_id, pid, False)
                by_id.update(more)
                extra += 1
                time.sleep(_jitter(getattr(cfg, "PEDIGREE_REQUEST_DELAY", 1.0)))

        out, _ = _walk()
        return out
