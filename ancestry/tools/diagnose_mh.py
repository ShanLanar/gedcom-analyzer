#!/usr/bin/env python3
"""
Diagnose-Script Phase 3: FamilyGraph 400-Fehler analysieren + mehr Varianten.
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
FG   = "https://familygraph.myheritage.com"

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
member_id= find(r'currentMemberId\s*=\s*["\']([^"\']+)["\']')

# Suche noch nach weiteren Token-Varianten
fg_tok3  = find(r'access_token["\s:=]+([A-Za-z0-9._\-]{20,})')
api_key  = find(r'apiKey["\s:=]+["\']([^"\']{10,})["\']')

print(f"mhXsrfToken  : {xsrf[:50]}…" if xsrf else "mhXsrfToken  : ❌ nicht gefunden")
print(f"fg_token_web : {fg_tok[:50]}…" if fg_tok else "fg_token_web : ❌ nicht gefunden")
print(f"siteId       : {site_id or KIT}")
print(f"memberId     : {member_id or '❌ nicht gefunden'}")
print(f"api_key      : {api_key[:40] if api_key else '❌ nicht gefunden'}")
print()

# ── Hilfsfunktion ──────────────────────────────────────────────────────────────
def probe(label, method, url, params=None, body=None, extra_hdrs=None):
    hdrs = {
        "Referer":  f"{BASE}/dna/matches/{KIT}",
        "Accept":   "application/json, text/plain, */*",
        "Origin":   BASE,
    }
    if extra_hdrs:
        hdrs.update(extra_hdrs)
    try:
        if method == "GET":
            resp = s.get(url, params=params or {}, headers=hdrs, timeout=12)
        else:
            resp = s.post(url, json=body or {}, params=params or {}, headers=hdrs, timeout=12)
        ct  = resp.headers.get("content-type", "")
        tag = "✅" if resp.status_code == 200 else ("⚠️" if resp.status_code < 500 else "❌")
        print(f"  {tag} [{resp.status_code}] {label}")
        # Immer JSON-Body zeigen wenn vorhanden
        if "json" in ct:
            try:
                d = resp.json()
                if isinstance(d, dict):
                    keys = list(d.keys())[:15]
                    print(f"       Schlüssel: {keys}")
                    txt = json.dumps(d)
                    if any(k in txt for k in ["sharedDna","matchId","dnaMatch","totalShared",
                                              "matches","dna_matches","results","items"]):
                        print(f"       🎯 MATCH-DATEN GEFUNDEN!")
                    print(f"       Body: {txt[:400]}")
                else:
                    print(f"       Body: {json.dumps(d)[:400]}")
            except Exception:
                print(f"       Body: {resp.text[:300]!r}")
        else:
            snippet = resp.text[:200].replace('\n', ' ')
            print(f"       Body: {snippet!r}")
    except Exception as e:
        print(f"  ❌ {label} → Fehler: {e}")
    print()

print("=" * 60)
print("RUNDE 1 – FamilyGraph 400 analysieren")
print("=" * 60)

# FG ohne access_token → vielleicht cookies reichen
probe("FG – nur Cookies, kein access_token",
      "GET", f"{FG}/{KIT}/dna_matches",
      params={"limit": 5})

# FG mit access_token als Query
probe("FG – access_token als Query",
      "GET", f"{FG}/{KIT}/dna_matches",
      params={"access_token": fg_tok, "limit": 5})

# FG mit access_token als Bearer Header
probe("FG – access_token als Bearer",
      "GET", f"{FG}/{KIT}/dna_matches",
      params={"limit": 5},
      extra_hdrs={"Authorization": f"Bearer {fg_tok}"})

# FG – andere Pfad-Varianten
probe("FG – /api/dna_matches",
      "GET", f"{FG}/api/dna_matches",
      params={"access_token": fg_tok, "siteId": KIT, "limit": 5})

probe("FG – /api/v1/dna_matches",
      "GET", f"{FG}/api/v1/dna_matches",
      params={"access_token": fg_tok, "siteId": KIT, "limit": 5})

probe("FG – /users/{siteId}/dna_matches",
      "GET", f"{FG}/users/{KIT}/dna_matches",
      params={"access_token": fg_tok, "limit": 5})

print("=" * 60)
print("RUNDE 2 – MyHeritage REST API")
print("=" * 60)

# Bekannte MH API Pfade
probe("MH – /api/user/dnaMatches",
      "GET", f"{BASE}/api/user/dnaMatches",
      params={"siteGuid": KIT, "page": 1, "pageSize": 5},
      extra_hdrs={"x-xsrf-token": xsrf})

probe("MH – /FP/API/DNA-1.0/matches",
      "GET", f"{BASE}/FP/API/DNA-1.0/matches",
      params={"siteId": KIT, "page": 1, "pageSize": 5},
      extra_hdrs={"x-xsrf-token": xsrf})

probe("MH – /FP/API/DNA-1.0/sites/{KIT}/matches",
      "GET", f"{BASE}/FP/API/DNA-1.0/sites/{KIT}/matches",
      params={"page": 1, "pageSize": 5},
      extra_hdrs={"x-xsrf-token": xsrf})

probe("MH – /FP/API/DNA-2.0/matches",
      "GET", f"{BASE}/FP/API/DNA-2.0/matches",
      params={"siteId": KIT, "page": 1, "pageSize": 5},
      extra_hdrs={"x-xsrf-token": xsrf})

probe("MH – /dna/api/v1/matches",
      "GET", f"{BASE}/dna/api/v1/matches",
      params={"siteId": KIT, "page": 1, "pageSize": 5},
      extra_hdrs={"x-xsrf-token": xsrf})

probe("MH – /FP/Process/ajaxCall.php (getDnaMatches)",
      "POST", f"{BASE}/FP/Process/ajaxCall.php",
      body={"action": "getDnaMatches", "siteId": KIT, "page": 1, "pageSize": 5},
      extra_hdrs={"x-xsrf-token": xsrf, "X-Requested-With": "XMLHttpRequest"})

probe("MH – /FP/Process/ajaxCall.php (getRelatives)",
      "POST", f"{BASE}/FP/Process/ajaxCall.php",
      body={"action": "getRelatives", "siteId": KIT, "page": 1},
      extra_hdrs={"x-xsrf-token": xsrf, "X-Requested-With": "XMLHttpRequest"})

print("=" * 60)
print("RUNDE 3 – FamilyGraph direkt (ohne Kit-Pfad)")
print("=" * 60)

probe("FG – root /",
      "GET", f"{FG}/",
      extra_hdrs={"Authorization": f"Bearer {fg_tok}"})

probe("FG – /{KIT} (Site-Info)",
      "GET", f"{FG}/{KIT}",
      params={"access_token": fg_tok})
