"""
ancestry_dna_tool – Konfiguration
"""
import os

BASE_URL      = "https://www.ancestry.com"
SIGNIN_PAGE   = f"{BASE_URL}/account/signin"
AUTH_ENDPOINT = f"{BASE_URL}/account/signin/frame/authenticate"

# ── Bestätigte API-Endpunkte (Stand Mai 2026) ─────────────────────────────────
DNA_LIST_BASE    = f"{BASE_URL}/discoveryui-matches/parents/list/api"
DNA_CLUSTER_BASE = f"{BASE_URL}/discoveryui-matches/cluster/api"

# Match-Liste
MATCHES_URL      = f"{DNA_LIST_BASE}/matchList/{{test_guid}}"
MATCH_COUNT_URL  = f"{DNA_LIST_BASE}/matchCount/{{test_guid}}"

# Shared Matches: gleicher matchList-Endpunkt + matchSampleId-Parameter (bestätigt)
SHARED_MATCHES_URL = f"{DNA_LIST_BASE}/matchList/{{test_guid}}"
# matchSampleId={sampleId}&page=1&pageSize=20 wird in api.py angehängt

# Kit-Verwaltung (alter Endpunkt, ggf. nicht verfügbar)
MANAGE_TESTS_URL = f"{BASE_URL}/dna/api/uhura/v2/people/{{uid}}/managetests"

# ── Paginierung ───────────────────────────────────────────────────────────────
PAGE_SIZE       = 50    # itemsPerPage (wie Ancestry-UI)
MAX_PAGES       = 0
REQUEST_DELAY   = 4.0   # Basis-Pause zwischen Requests (Sekunden)
REQUEST_TIMEOUT = 30

# ── Datenbank / Logging / Export ──────────────────────────────────────────────
DB_FILE    = "ancestry_dna.db"
LOG_FILE   = "ancestry_dna.log"
LOG_LEVEL  = "DEBUG"
EXPORT_DIR = os.path.join(os.path.expanduser("~"), "Documents")

DEFAULT_HEADERS = {
    "User-Agent"      : ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/124.0.0.0 Safari/537.36"),
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "de-DE,de;q=0.9,en-US;q=0.8",
    "Origin"          : BASE_URL,
    "Referer"         : f"{BASE_URL}/discoveryui-matches/",
}
