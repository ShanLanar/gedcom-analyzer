"""
Datenmodelle für Ancestry-DNA-Matches (discoveryui-Format, Stand 2026).

Neues API-Format:
  sampleId     = Match-GUID  (früher: matchGuid)
  tags         = Dict mit Tag-IDs (3=freie Bemerkung/Notiz, 5=Geschlecht, ...)
                 ACHTUNG: Tag 3 ist NICHT der echte Nachname der Match-Person,
                 sondern das selbst eingegebene Bemerkungsfeld des Nutzers.
  relationship = {meiosis, label, confidence, range, sharedCentimorgans, ...}
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


def derive_relationship(shared_cm: float, meiosis: int = 0) -> str:
    """Schätzt den Verwandtschaftsgrad aus geteilten cM (+ Meiosis-Anzahl).

    Ancestry liefert in der aktuellen matchList-API kein 'label' mehr mit,
    sondern nur sharedCentimorgans, numSharedSegments und (teils) meiosis.
    Diese Funktion bildet daraus einen lesbaren deutschen Beziehungstext –
    angelehnt an die AncestryDNA-Vorhersagen und das Shared-cM-Projekt.
    """
    cm = float(shared_cm or 0)
    if cm <= 0:
        return ""

    # Meiosis ist – wenn vorhanden – sehr präzise.
    if meiosis == 1:
        return "Elternteil / Kind"

    # cM-basierte Bereiche (von eng nach entfernt)
    if cm >= 3300:
        return "Elternteil / Kind"
    if cm >= 2400:
        return "Vollgeschwister"
    if cm >= 1700:
        return "Großeltern / Enkel · Onkel/Tante · Halbgeschwister"
    if cm >= 1300:
        return "Halbgeschwister · Onkel/Tante · Großeltern"
    if cm >= 850:
        return "1. Cousin · Großonkel/-tante · Halb-Onkel/Tante"
    if cm >= 575:
        return "1. Cousin · Halb-Cousin"
    if cm >= 350:
        return "1. Cousin 1x entfernt · Halb-1. Cousin"
    if cm >= 200:
        return "2. Cousin · 1. Cousin 2x entfernt"
    if cm >= 90:
        return "2. Cousin · 2. Cousin 1x entfernt"
    if cm >= 45:
        return "3. Cousin · 2. Cousin 1x entfernt"
    if cm >= 20:
        return "4. Cousin · 3. Cousin 1x entfernt"
    return "Entfernte Verwandtschaft (5.–8. Cousin)"


@dataclass
class DnaKit:
    guid: str
    name: str
    test_type: str = ""
    created_date: str = ""
    is_owner: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DnaMatch:
    match_guid: str
    test_guid: str
    display_name: str

    shared_cm: float = 0.0
    shared_segments: int = 0
    longest_segment: float = 0.0

    predicted_relationship: str = ""
    confidence: str = ""
    relationship_range: str = ""
    meiosis: int = 0

    has_hint: bool = False
    has_tree: bool = False
    tree_size: int = 0
    tree_id: str = ""

    starred: bool = False
    note: str = ""
    custom_relationship: str = ""
    ignored: bool = False

    # Tag-Felder (neues API-Format)
    tag_surname: str = ""       # Tag 3: freies Bemerkungs-/Notizfeld (NICHT der echte Nachname)
    tag_gender:  str = ""        # Legacy (kompatibel mit DB-Spalte)
    tag_path:   str = ""        # Tag 5: Verwandtschaftspfad (PPPPGCD)
    tags_json:  str = ""        # Alle Tags als JSON

    # Mutter/Vater-Cluster (discoveryui: "maternal"/"paternal"/"both")
    match_cluster_code: str = ""
    created_date: int = 0       # Unix-Timestamp ms

    ethnicity_regions: list = field(default_factory=list)
    last_login: str = ""
    fetched_at: str = ""
    raw_json: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ethnicity_regions"] = json.dumps(d["ethnicity_regions"])
        return d

    @classmethod
    def from_api_response(cls, data: dict, test_guid: str,
                          fetched_at: str = "") -> "DnaMatch":
        """
        Verarbeitet beide API-Formate:
        - Neu (discoveryui): sampleId, relationship{}, tags{}
        - Alt (uhura v2):    matchGuid, sharedCentimorgans, ...
        """
        def safe(key, default=""):
            return data.get(key) or default

        def safe_float(key) -> float:
            try:
                return float(data.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0

        def safe_int(key) -> int:
            try:
                return int(data.get(key) or 0)
            except (TypeError, ValueError):
                return 0

        # ── Match-GUID ────────────────────────────────────────────────────────
        match_guid = (safe("sampleId")          # neu
                      or safe("matchGuid")       # alt
                      or safe("matchMember", {}).get("guid", "")
                      or safe("guid"))

        # ── Name ──────────────────────────────────────────────────────────────
        # Mögliche Felder in verschiedenen API-Versionen.
        # Das aktuelle discoveryui-matchList-Format legt den Namen in
        # matchProfile.displayName ab (NICHT auf oberster Ebene!).
        def nested(key, sub):
            v = data.get(key)
            return v.get(sub, "") if isinstance(v, dict) else ""

        name = (safe("displayName")
                or safe("name")
                or nested("matchProfile", "displayName")      # aktuelles Format
                or nested("matchProfile", "name")
                or safe("matchTestDisplayName")
                or safe("matchTestAdminDisplayName")
                or nested("admin", "displayName")
                or nested("matchMember", "displayName")
                or nested("matchMember", "name")
                or nested("profile", "displayName")
                or nested("profile", "name")
                or nested("subjectInfo", "displayName")
                or "")

        # Fallback: Name aus Tag 3 extrahieren, wenn kein direktes Namensfeld da ist.
        if not name:
            tags_tmp = data.get("tags") or {}
            tag3_raw = str(tags_tmp.get("3") or "")

            def _p3(s):
                if not s:
                    return s, ""
                # Muster: "Surname, Firstname Lastname"
                parts = s.split(",")
                if len(parts) >= 2:
                    candidate = parts[-1].strip()
                    # Echter Name: Großbuchstabe, mind. 2 Wörter, >5 Zeichen
                    words = candidate.split()
                    if (len(words) >= 2
                            and words[0][0:1].isupper()
                            and len(candidate) > 5
                            and "relationship" not in candidate.lower()):
                        surname = parts[0].replace("(no direct relationship)", "").strip()
                        surname = "".join(c for c in surname if "(" not in c).strip()
                        return surname, candidate
                # Muster: "Surname [Firstname Lastname]"
                if "[" in s and "]" in s:
                    name_part = s[s.find("[")+1:s.find("]")]
                    surname   = s[:s.find("[")].strip().rstrip(",").strip()
                    return surname, name_part
                return s.split(",")[0].strip(), ""

            tag_surname_val, extracted_name = _p3(tag3_raw)
            if extracted_name:
                name = extracted_name
            elif tag_surname_val:
                name = tag_surname_val
            else:
                name = "Anonym"

        # ── Beziehung (neues Format: relationship-Objekt) ────────────────────
        rel = data.get("relationship") or {}
        if isinstance(rel, dict):
            shared_cm       = (rel.get("sharedCentimorgans")
                               or safe_float("sharedCentimorgans"))
            shared_segments = (rel.get("numSharedSegments")
                               or rel.get("sharedSegments")
                               or safe_int("sharedSegments"))
            longest_seg     = (rel.get("longestSegment")
                               or safe_float("longestSegment"))
            relationship    = (rel.get("label")
                               or rel.get("relationshipLabel")
                               or safe("predictedRelationship")
                               or "")
            confidence      = rel.get("confidence", "")
            rel_range       = rel.get("range", "")
            meiosis         = rel.get("meiosis") or 0
        else:
            shared_cm       = safe_float("sharedCentimorgans")
            shared_segments = safe_int("sharedSegments")
            longest_seg     = safe_float("longestSegment")
            rel_info        = data.get("relationshipInfo") or {}
            relationship    = rel_info.get("label") or safe("predictedRelationship") or ""
            confidence      = rel_info.get("confidence", "")
            rel_range       = rel_info.get("range", "")
            meiosis         = 0

        # Ancestry liefert oft kein Label mehr → aus cM + Meiosis ableiten
        if not relationship:
            relationship = derive_relationship(shared_cm, meiosis)

        # ── Tags (neues Format: tags{tagId: value}) ──────────────────────────
        import json as _j
        tags_raw   = data.get("tags") or {}
        tag3_raw   = str(tags_raw.get("3") or "")
        tag_path   = str(tags_raw.get("5") or "")
        tags_json_val = _j.dumps(tags_raw, ensure_ascii=False)
        starred    = bool(tags_raw.get("1"))       # Tag 1 = Markierung?

        # Name aus Tag 3 extrahieren: "Surname, Firstname Lastname" oder "Surname [Name]"
        def _extract_name_from_tag3(s):
            if not s:
                return s, ""
            parts = s.split(",")
            if len(parts) >= 2:
                candidate = parts[-1].strip()
                words = candidate.split()
                if (len(words) >= 2
                        and words[0][:1].isupper()
                        and len(candidate) > 5
                        and "relationship" not in candidate.lower()):
                    surname = parts[0].replace("(no direct relationship)", "").strip()
                    surname = surname.replace(")", "").replace("(", "").strip()
                    return surname, candidate
            if "[" in s and "]" in s:
                name_part = s[s.find("[")+1 : s.find("]")]
                surname   = s[:s.find("[")].strip().rstrip(",").strip()
                return surname, name_part
            return s.split(",")[0].strip(), ""

        tag_surname, extracted_name = _extract_name_from_tag3(tag3_raw)

        # ── Stammbaum ─────────────────────────────────────────────────────────
        tree_info = data.get("treeInfo") or {}
        tree_size = tree_info.get("totalPeople") or safe_int("treeSize")
        tree_id   = tree_info.get("treeId", "")
        has_tree  = bool(tree_id) or bool(tree_size) or bool(data.get("hasTree"))

        # ── Ethnizität ────────────────────────────────────────────────────────
        eth = data.get("ethnicities") or []
        eth_regions = ([e.get("name","") for e in eth if e.get("name")]
                       if isinstance(eth, list) else [])

        return cls(
            match_guid            = match_guid,
            test_guid             = test_guid,
            display_name          = name,
            shared_cm             = float(shared_cm or 0),
            shared_segments       = int(shared_segments or 0),
            longest_segment       = float(longest_seg or 0),
            predicted_relationship= relationship,
            confidence            = confidence,
            relationship_range    = rel_range,
            meiosis               = int(meiosis or 0),
            has_hint              = bool(data.get("hasHint")),
            has_tree              = has_tree,
            tree_size             = tree_size,
            tree_id               = tree_id,
            starred               = starred or bool(data.get("starred")),
            ignored               = bool(data.get("ignored")),
            note                  = safe("note"),
            custom_relationship   = safe("customRelationship"),
            tag_surname           = tag_surname,
            tag_path              = tag_path,
            tags_json             = tags_json_val,
            match_cluster_code    = safe("matchClusterCode"),
            created_date          = int(data.get("createdDate") or 0),
            ethnicity_regions     = eth_regions,
            last_login            = safe("lastLoginDate"),
            fetched_at            = fetched_at,
            raw_json              = json.dumps(data, ensure_ascii=False),
        )

    @classmethod
    def from_db_row(cls, row: dict) -> "DnaMatch":
        obj = cls.__new__(cls)
        for f in cls.__dataclass_fields__:
            setattr(obj, f, row.get(f, cls.__dataclass_fields__[f].default))
        er = obj.ethnicity_regions
        if isinstance(er, str):
            try:
                obj.ethnicity_regions = json.loads(er)
            except Exception:
                obj.ethnicity_regions = []
        return obj


@dataclass
class SharedMatch:
    test_guid      : str
    match_guid_a   : str
    match_guid_b   : str
    display_name_b : str = ""
    shared_cm_b    : float = 0.0
    shared_cm_ab   : float = 0.0
    shared_segments_b: int = 0
    relationship_b : str = ""
    has_tree_b     : bool = False
    fetched_at     : str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_api_response(cls, data: dict, test_guid: str,
                          match_guid_a: str, fetched_at: str = "") -> "SharedMatch":
        def safe(key, default=""):
            return data.get(key) or default

        def nested(key, sub):
            v = data.get(key)
            return v.get(sub, "") if isinstance(v, dict) else ""

        name   = (safe("displayName")
                  or nested("matchProfile", "displayName")
                  or nested("matchProfile", "name")
                  or safe("matchTestDisplayName")
                  or nested("matchMember", "displayName")
                  or "Unbekannt")
        guid_b = (safe("sampleId") or safe("matchGuid")
                  or safe("matchMember", {}).get("guid", "")
                  or safe("guid", ""))

        rel    = data.get("relationship") or {}
        rel_info = data.get("relationshipInfo") or {}
        shared_cm = (rel.get("sharedCentimorgans")
                     if isinstance(rel, dict)
                     else data.get("sharedCentimorgans") or 0)
        relationship = ((rel.get("label") if isinstance(rel, dict)
                        else rel_info.get("label")) or "")
        if not relationship:
            mei = rel.get("meiosis", 0) if isinstance(rel, dict) else 0
            relationship = derive_relationship(shared_cm, mei)

        tree_info = data.get("treeInfo") or {}
        has_tree  = bool(tree_info.get("treeId")) or bool(data.get("hasTree"))

        return cls(
            test_guid       = test_guid,
            match_guid_a    = match_guid_a,
            match_guid_b    = guid_b,
            display_name_b  = name,
            shared_cm_b     = float(shared_cm or 0),
            shared_segments_b = int(data.get("sharedSegments") or
                                    rel.get("sharedSegments", 0)
                                    if isinstance(rel, dict) else 0),
            relationship_b  = relationship,
            has_tree_b      = has_tree,
            fetched_at      = fetched_at,
        )

    @classmethod
    def from_db_row(cls, row: dict) -> "SharedMatch":
        obj = cls.__new__(cls)
        for f in cls.__dataclass_fields__:
            setattr(obj, f, row.get(f, cls.__dataclass_fields__[f].default))
        return obj
