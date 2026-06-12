"""
Namen- und Profil-Detail-Mixin für den Ancestry-API-Client.
"""

import logging

import ancestry.endpoints as cfg
from ._session import _is_initials_only

log = logging.getLogger(__name__)


class _NamesProfileMixin:
    """Methoden für Namen-/Profil-Abfragen."""

    @staticmethod
    def _pick_name(info: dict) -> str:
        """Wählt aus einem profileData-Eintrag den besten Anzeigenamen."""
        if not isinstance(info, dict):
            return ""
        name = (info.get("matchName") or "").strip()
        # "L. S." o.ä. sind initialisierte Privatprofile – managedName ist
        # oft aussagekräftiger (z.B. "kathy_stevers").
        managed = (info.get("managedName") or "").strip()
        if name and not _is_initials_only(name):
            return name
        if managed:
            return managed
        return name

    def get_profile_details_bulk(self, test_guid: str,
                                 sample_ids: list[str]) -> dict[str, dict]:
        """profileData → {sampleId: {"name":.., "ucdmid":.., "gender":..}}."""
        if not sample_ids or self._detail_blocked:
            return {}
        url  = cfg.PROFILE_DATA_URL.format(test_guid=test_guid)
        data = self._signed_post(url, {"matchSampleIds": list(sample_ids)},
                                 test_guid, "profileData")
        out = {}
        for sid, info in (data or {}).items():
            if not isinstance(info, dict):
                continue
            out[sid] = {
                "name"  : self._pick_name(info),
                "ucdmid": info.get("matchUcdmid") or "",
                "gender": info.get("displayGender") or "",
            }
        return out

    def get_match_names_bulk(self, test_guid: str,
                             sample_ids: list[str]) -> dict[str, str]:
        """Rückwärtskompatibel: nur {sampleId: name}."""
        details = self.get_profile_details_bulk(test_guid, sample_ids)
        return {sid: d["name"] for sid, d in details.items() if d.get("name")}
