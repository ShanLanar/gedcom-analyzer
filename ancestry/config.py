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

# ── Match-Detail (voller Name) ────────────────────────────────────────────────
# Der Bulk-matchList-Endpunkt liefert KEINEN echten Namen, nur das selbst
# eingegebene Bemerkungsfeld (Tag 3). Den echten Anzeigenamen der Match-Person
# gibt es nur über einen Detail-Abruf pro Match. Da Ancestry den
# genauen Pfad mehrfach geändert hat, werden mehrere Kandidaten der Reihe nach
# probiert; der erste, der einen Namen liefert, wird gemerkt.
MATCHESSERVICE_BASE = f"{BASE_URL}/discoveryui-matchesservice/api"
MATCH_DETAIL_CANDIDATES = [
    # matchesservice – liefert i.d.R. matchProfile.displayName
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matches/{{sample_id}}",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matches/{{sample_id}}/details",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matchProfile/{{sample_id}}",
    f"{MATCHESSERVICE_BASE}/compare/{{test_guid}}/with/{{sample_id}}/details",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matchesv2/{{sample_id}}",
    # ältere discoveryui-Pfade
    f"{DNA_LIST_BASE}/match/{{test_guid}}/{{sample_id}}",
    f"{DNA_LIST_BASE}/matchProfile/{{test_guid}}/{{sample_id}}",
    f"{DNA_LIST_BASE}/details/{{test_guid}}/{{sample_id}}",
]
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
                         "Chrome/124.0.0.0 Safari/537.36"),
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "de-DE,de;q=0.9,en-US;q=0.8",
    "Origin"          : BASE_URL,
    "Referer"         : f"{BASE_URL}/discoveryui-matches/",
}
