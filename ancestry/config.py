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

# ── Match-Namen: Bulk-Endpunkt (bestätigt via DevTools, Juni 2026) ────────────
# POST /discoveryui-matches/cluster/api/profileData/{test_guid}
#   Body:     {"matchSampleIds": [ ... bis zu 20 sampleIds ... ]}
#   Antwort:  { "<sampleId>": {"matchName": "...", "managedName": "...", ...}, ... }
# Gleicher Service wie matchList (discoveryui-matches) → kein Cloudflare-520.
# Liefert echte Anzeigenamen – ein Request pro 20 Matches.
PROFILE_DATA_URL  = f"{DNA_CLUSTER_BASE}/profileData/{{test_guid}}"
PROFILE_DATA_BATCH = 20   # sampleIds pro Request (wie Ancestry-UI)

# ── Match-Detail (Legacy, nicht mehr genutzt) ─────────────────────────────────
# matchList liefert keine Namen. Wir probieren mehrere Endpunkte der Reihe nach;
# zuerst den parents/list-Service (selber Host, kein Akamai-Block),
# dann den matchesservice (oft durch Akamai 520 blockiert).
MATCHESSERVICE_BASE = f"{BASE_URL}/discoveryui-matchesservice/api"

# Kandidaten in Prioritätsreihenfolge:
# 1. parents/list-Sub-Pfade (gleicher Service wie matchList, kein extra Akamai)
# 2. uhura-v2 (ältere API, weniger streng)
# 3. matchesservice (meist Akamai-blockiert)
MATCH_DETAIL_CANDIDATES = [
    # parents/list Varianten
    f"{DNA_LIST_BASE}/matchProfile/{{test_guid}}/{{sample_id}}",
    f"{DNA_LIST_BASE}/profile/{{test_guid}}/{{sample_id}}",
    f"{DNA_LIST_BASE}/match/{{test_guid}}/{{sample_id}}",
    # Alte uhura-v2 API
    f"{BASE_URL}/dna/api/uhura/v2/people/{{test_guid}}/matches/{{sample_id}}",
    # matchesservice (oft Akamai-blockiert)
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matches/{{sample_id}}",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matches/{{sample_id}}/details",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matchProfile/{{sample_id}}",
]
# Header, die ein echter Browser bei XHR an den matchesservice-Host sendet.
# Ohne diese blockt Akamai Bot Manager mit "Access denied" (520).
MATCHESSERVICE_HEADERS = {
    "Accept"        : "application/json",
    "Origin"        : BASE_URL,
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}
# Referer auf eine echte Match-Listenseite (nicht die fiktive Compare-URL)
MATCHESSERVICE_REFERER = f"{BASE_URL}/discoveryui-matches/list/{{test_guid}}"
# Zusätzliche Pause speziell für Detail-Abrufe (Sekunden)
DETAIL_REQUEST_DELAY = 1.5

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
                         "Chrome/136.0.0.0 Safari/537.36"),
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "de-DE,de;q=0.9,en-US;q=0.8",
    "Origin"          : BASE_URL,
    "Referer"         : f"{BASE_URL}/discoveryui-matches/",
}
