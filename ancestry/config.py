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

# Shared Matches: eigener Pfad-Endpunkt /with/{match_guid} (per DevTools bestätigt).
# Die früher genutzte Form matchList/{test}?matchSampleId=… ignoriert den Filter
# und liefert ALLE Matches – daher die /with/-Pfadform verwenden.
SHARED_MATCHES_URL = f"{DNA_LIST_BASE}/matchList/{{test_guid}}/with/{{match_guid}}"

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

# ── Stammbaum & gemeinsamer Vorfahre (bestätigt via Spion, Juni 2026) ─────────
# Beide POSTs auf der parents/list-API (gleicher CSRF-Trick wie profileData).
#   commonAncestors: Body {"sampleIds":[...]}  → Array der sampleIds MIT Vorfahr
#   treeData:        Body {"matchList":[{"sampleId":..,"matchProfile":{"userId":..}}]}
#                    → {sid: {isPublicTree,isPrivateTree,isUnlinkedTree,
#                             hasNoTrees,isTreeUnavailable,treeSize}}
# userId in treeData == matchUcdmid aus profileData.
COMMON_ANCESTORS_URL = f"{DNA_LIST_BASE}/commonAncestors/{{test_guid}}"
TREE_DATA_URL        = f"{DNA_LIST_BASE}/treeData/{{test_guid}}"
# Bulk: welche Matches sind in DEINEM Baum verknüpft ('View in tree'). POST sampleIds.
MATCHES_IN_TREE_URL  = f"{DNA_LIST_BASE}/badges/matchesInTree/{{test_guid}}"

# ── Compare-Seite: gemeinsame Vorfahren + Geburtsorte (bestätigt via Spion) ────
# Beides GET (wie matchList) → kein CSRF nötig.
#   commonancestors → {"ancestorCouples":[{father,mother}], sampleTree, matchTree}
#                     je Vorfahr: personData{displayName,birthYear,deathYear,isMale},
#                     relationshipToSampleId, kinshipPathToSampleId,
#                     kinshipPathFromSampleToMatch, inMatchTree
#   completeTreeData → {sample,match}.linkedTree.birthLocations[]
#                     {name, coords, people[], personCount}
COMPARE_COMMON_ANCESTORS_URL = (
    f"{DNA_LIST_BASE}/compare/{{test_guid}}/with/{{match_guid}}/commonancestors")
COMPARE_TREE_DATA_URL = (
    f"{BASE_URL}/discoveryui-matches/parents/compare/api"
    f"/{{test_guid}}/with/{{match_guid}}/completeTreeData")

# ── Pedigree / volle Ahnentafel (Tree-Viewer) ─────────────────────────────────
# /matches/{match}/trees  → {trees:[{treeId, personId(=Fokus), personCount, type}]}
MATCH_TREES_URL = (
    f"{BASE_URL}/discoveryui-matches/parents/tests/{{test_guid}}"
    f"/matches/{{match_guid}}/trees")
# Pedigree-Ansicht: liefert ~5 Generationen Vorfahren in einer Antwort.
PEDIGREE_URL = (
    f"{BASE_URL}/api/treeviewer/tree/{{tree_id}}"
    f"?focusPersonId={{focus_pid}}&isFocus={{is_focus}}&view=pedigree")

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
# Eigene, kürzere Pause fürs Shared-Matches-Blättern (leichtere GETs).
SHARED_REQUEST_DELAY = 2.0
# Pedigree-Abruf (reine GETs): kürzere Pause + kontrollierte Parallelität.
PEDIGREE_REQUEST_DELAY = 1.0
PEDIGREE_WORKERS       = 5     # parallele Worker für Ahnentafel-Download
# Gezieltes Tiefer-Laden (Re-Fokussierung) – nur für untersuchte Cluster, teuer:
PEDIGREE_DEEP_GENERATIONS = 8
PEDIGREE_DEEP_EXTRA       = 16   # max. zusätzliche Re-Fokus-Calls pro Match
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
