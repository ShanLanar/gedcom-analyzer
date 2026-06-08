#!/usr/bin/env python3
"""
Diagnose-Script Phase 2: findet den echten API-Endpunkt für DNA-Matches.
Extrahiert Tokens aus dem HTML und probiert bekannte Endpunkt-Muster durch.
"""
import json, sys, re
from pathlib import Path
import requests

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)

s = requests.Session()
s.cookies.update(cookies)
s.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

KIT  = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
BASE = "https://www.myheritage.com"

# ── Tokens aus HTML extrahieren ───────────────────────────────────────────────
print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text

def find(pattern, default=""):
    m = re.search(pattern, html)
    return m.group(1) if m else default

xsrf     = find(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']')
fg_token = find(r'"fg_token_web"\s*:\s*"([^"]+)"')
fg_token2= find(r'fg_token_web\s*[=:]\s*["\']([^"\']+)["\']')
fg_tok   = fg_token or fg_token2
site_id  = find(r'currentSiteId\s*=\s*["\']([^"\']+)["\']')

print(f"mhXsrfToken  : {xsrf[:40]}…" if xsrf else "mhXsrfToken  : ❌ nicht gefunden")
print(f"fg_token_web : {fg_tok[:40]}…" if fg_tok else "fg_token_web : ❌ nicht gefunden")
print(f"siteId       : {site_id or KIT}")
print()

# ── Kandidaten-Endpunkte ──────────────────────────────────────────────────────
candidates = [
    # FamilyGraph API
    ("GET", f"https://familygraph.myheritage.com/{KIT}/dna_matches",
     {"access_token": fg_tok, "limit": 5, "sort_by": "total_shared_segments_length_in_cm"}),
    ("GET", f"https://familygraph.myheritage.com/{KIT}/dna-matches",
     {"access_token": fg_tok, "limit": 5}),
    # ClanSearch REST
    ("GET", f"{BASE}/FP/API/ClanSearch-1.0/app/dna-matches",
     {"siteId": KIT, "lang": "EN", "page": 1, "pageSize": 5,
      "sortBy": "total_shared_segments_length_in_cm"}),
    ("GET", f"{BASE}/FP/API/ClanSearch-1.0/sites/{KIT}/dna-matches",
     {"lang": "EN", "page": 1, "pageSize": 5}),
    # DNA-spezifische Pfade
    ("GET", f"{BASE}/dna/api/get-matches",
     {"siteId": KIT, "page": 1, "pageSize": 5}),
    ("GET", f"{BASE}/dna/api/matches",
     {"siteId": KIT, "page": 1, "pageSize": 5}),
    # PHP Ajax
    ("POST", f"{BASE}/FP/Process/ajaxCall.php", {}),
]

extra_headers = {
    "x-xsrf-token":  xsrf,
    "X-XSRF-TOKEN":  xsrf,
    "Referer": f"{BASE}/dna/matches/{KIT}",
    "Accept":  "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}

print("Probiere Endpunkte …\n")
for method, url, params in candidates:
    try:
        if method == "GET":
            resp = s.get(url, params=params, headers=extra_headers, timeout=10)
        else:
            resp = s.post(url, json=params, headers=extra_headers, timeout=10)

        ct = resp.headers.get("content-type","")
        print(f"  {method} {url.replace(BASE,'')}")
        print(f"       → {resp.status_code}  {ct[:60]}")
        if resp.status_code == 200 and "json" in ct:
            try:
                d = resp.json()
                keys = list(d.keys())[:10] if isinstance(d, dict) else f"Liste[{len(d)}]"
                print(f"       ✅ JSON! Schlüssel: {keys}")
                # Ersten Match-Kandidaten suchen
                txt = json.dumps(d)[:500]
                if any(k in txt for k in ["sharedDna","matchId","dnaMatch","totalShared"]):
                    print(f"       🎯 MATCH-DATEN GEFUNDEN!")
                    print(f"       Vorschau: {txt[:300]}")
            except Exception:
                print(f"       Inhalt: {resp.text[:200]!r}")
        elif resp.status_code == 200:
            snippet = resp.text[:150].replace('\n',' ')
            print(f"       Inhalt: {snippet!r}")
        print()
    except Exception as e:
        print(f"  {url.replace(BASE,'')} → Fehler: {e}\n")
