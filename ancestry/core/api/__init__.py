"""
Ancestry DNA API-Client – discoveryui-Format (Stand 2026).
Mit adaptivem Rate-Limiting und Jitter.

Dieses Package ersetzt die ehemalige Datei ancestry/core/api.py.
Die öffentliche Schnittstelle ist identisch.
"""

import time

from ._session import (
    _ApiSessionMixin,
    _jitter,
    _build_ube_header,
    _is_initials_only,
    _api_get,
    RETRY_STATUSES,
    MAX_RETRIES,
    RETRY_DELAYS,
    BURST_LIMIT,
    BURST_PAUSE,
    JWT_REFRESH_INTERVAL,
)
from ._names import _NamesProfileMixin
from ._pedigree import _PedigreeMixin
from ._matches import _MatchesMixin

__all__ = [
    "AncestryApiClient",
    "_jitter",
    "_build_ube_header",
    "_is_initials_only",
    "_api_get",
    "RETRY_STATUSES",
    "MAX_RETRIES",
    "RETRY_DELAYS",
    "BURST_LIMIT",
    "BURST_PAUSE",
    "JWT_REFRESH_INTERVAL",
]


class AncestryApiClient(
    _ApiSessionMixin,
    _NamesProfileMixin,
    _PedigreeMixin,
    _MatchesMixin,
):
    """Ancestry DNA API-Client – zusammengesetzt aus Mixins."""

    def __init__(self, session):
        self._s = session
        self._detail_blocked = False   # True wenn Namen-API 401/403 lieferte
        self._session_expired = False  # True nach 401/403 auch nach JWT-Erneuerung
        self._csrf_mode = None         # gecachte CSRF-Form sobald eine 200 lieferte
        self._http_lock = __import__("threading").Lock()  # serialisiert HTTP bei Parallelität
        self._last_jwt_refresh: float = time.time()
