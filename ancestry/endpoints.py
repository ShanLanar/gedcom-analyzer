"""Ancestry API — Endpunkte, HTTP-Defaults und Anfrageparameter."""

BASE_URL      = "https://www.ancestry.com"
SIGNIN_PAGE   = f"{BASE_URL}/account/signin"
AUTH_ENDPOINT = f"{BASE_URL}/account/signin/frame/authenticate"

# ── Bestätigte API-Endpunkte (Stand Mai 2026) ─────────────────────────────────
DNA_LIST_BASE    = f"{BASE_URL}/discoveryui-matches/parents/list/api"
DNA_CLUSTER_BASE = f"{BASE_URL}/discoveryui-matches/cluster/api"

# Match-Liste
MATCHES_URL      = f"{DNA_LIST_BASE}/matchList/{{test_guid}}"
MATCH_COUNT_URL  = f"{DNA_LIST_BASE}/matchCount/{{test_guid}}"

# Shared Matches: eigener Pfad-Endpunkt /with/{match_guid} (per DevTools bestätigt).
SHARED_MATCHES_URL = f"{DNA_LIST_BASE}/matchList/{{test_guid}}/with/{{match_guid}}"

# Kit-Verwaltung (alter Endpunkt, ggf. nicht verfügbar)
MANAGE_TESTS_URL = f"{BASE_URL}/dna/api/uhura/v2/people/{{uid}}/managetests"

# ── Match-Namen: Bulk-Endpunkt (bestätigt via DevTools, Juni 2026) ────────────
PROFILE_DATA_URL  = f"{DNA_CLUSTER_BASE}/profileData/{{test_guid}}"
PROFILE_DATA_BATCH = 20   # sampleIds pro Request (wie Ancestry-UI)

# ── Stammbaum & gemeinsamer Vorfahre (bestätigt via Spion, Juni 2026) ─────────
COMMON_ANCESTORS_URL = f"{DNA_LIST_BASE}/commonAncestors/{{test_guid}}"
TREE_DATA_URL        = f"{DNA_LIST_BASE}/treeData/{{test_guid}}"
MATCHES_IN_TREE_URL  = f"{DNA_LIST_BASE}/badges/matchesInTree/{{test_guid}}"

# ── Compare-Seite: gemeinsame Vorfahren + Geburtsorte ────────────────────────
COMPARE_COMMON_ANCESTORS_URL = (
    f"{DNA_LIST_BASE}/compare/{{test_guid}}/with/{{match_guid}}/commonancestors")
COMPARE_TREE_DATA_URL = (
    f"{BASE_URL}/discoveryui-matches/parents/compare/api"
    f"/{{test_guid}}/with/{{match_guid}}/completeTreeData")

# ── Pedigree / volle Ahnentafel (Tree-Viewer) ─────────────────────────────────
MATCH_TREES_URL = (
    f"{BASE_URL}/discoveryui-matches/parents/tests/{{test_guid}}"
    f"/matches/{{match_guid}}/trees")
PEDIGREE_URL = (
    f"{BASE_URL}/api/treeviewer/tree/{{tree_id}}"
    f"?focusPersonId={{focus_pid}}&isFocus={{is_focus}}&view=pedigree")

# ── Match-Detail (Legacy, nicht mehr genutzt) ─────────────────────────────────
MATCHESSERVICE_BASE = f"{BASE_URL}/discoveryui-matchesservice/api"

MATCH_DETAIL_CANDIDATES = [
    f"{DNA_LIST_BASE}/matchProfile/{{test_guid}}/{{sample_id}}",
    f"{DNA_LIST_BASE}/profile/{{test_guid}}/{{sample_id}}",
    f"{DNA_LIST_BASE}/match/{{test_guid}}/{{sample_id}}",
    f"{BASE_URL}/dna/api/uhura/v2/people/{{test_guid}}/matches/{{sample_id}}",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matches/{{sample_id}}",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matches/{{sample_id}}/details",
    f"{MATCHESSERVICE_BASE}/samples/{{test_guid}}/matchProfile/{{sample_id}}",
]

MATCHESSERVICE_HEADERS = {
    "Accept"        : "application/json",
    "Origin"        : BASE_URL,
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}
MATCHESSERVICE_REFERER = f"{BASE_URL}/discoveryui-matches/list/{{test_guid}}"
DETAIL_REQUEST_DELAY = 1.5

# ── Paginierung & Rate-Limiting ────────────────────────────────────────────────
PAGE_SIZE              = 50
MAX_PAGES              = 0
REQUEST_DELAY          = 4.0
SHARED_REQUEST_DELAY   = 2.0
PEDIGREE_REQUEST_DELAY = 1.0
PEDIGREE_WORKERS       = 5
ANCESTOR_REQUEST_DELAY = 3.0
ANCESTOR_WORKERS       = 2
PEDIGREE_DEEP_GENERATIONS = 8
PEDIGREE_DEEP_EXTRA       = 16
REQUEST_TIMEOUT        = 30

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = "DEBUG"

# ── HTTP-Defaults ──────────────────────────────────────────────────────────────
DEFAULT_HEADERS = {
    "User-Agent"      : ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/136.0.0.0 Safari/537.36"),
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "de-DE,de;q=0.9,en-US;q=0.8",
    "Origin"          : BASE_URL,
    "Referer"         : f"{BASE_URL}/discoveryui-matches/",
}
