#!/usr/bin/env python3
"""
Diagnose-Script Phase 13: mhc# Header-Präfix testen.
L.aG = "mhc#" → Headers heißen mhc#PHPSESSID, mhc#mh_automations etc.
"""
import json, re, sys, time
from pathlib import Path
import requests

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)

KIT   = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
BASE  = "https://www.myheritage.com"
GQLEP = f"{BASE}/web-family-graphql"
UA    = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

s = requests.Session()
s.cookies.update(cookies)
s.headers["User-Agent"] = UA

print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text
xsrf   = (re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html) or type('',(object,),{'group':lambda s,n:''})()).group(1)
fg_web = (re.search(r'"fg_token_web"\s*:\s*"([^"]+)"', html) or type('',(object,),{'group':lambda s,n:''})()).group(1)

tok_url = f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php?_={int(time.time()*1000)}&csrf_token={xsrf}"
php_tok = s.get(tok_url, headers={"Accept":"application/json"}, timeout=15).json().get("data",{}).get("token","")

print(f"Token: {php_tok[:50]}…\n")

# ── Vollständiger L.Gz Array (aus Phase 11) ───────────────────────────────────
L_GZ = ["mh_automations","mh_automations_scenario","mh_location","mh_ip_address",
        "featureFlagData","abTestData","automation_test_services","PHPSESSID",
        "mh_confu_overrides","ndd","x-mh-circuit-breaker-test",
        "x-mh-circuit-breaker-policy","x-mh-circuit-breaker-config","is_embed"]
L_AG = "mhc#"

# mhc#-Header aus vorhandenen Cookies aufbauen
mhc_headers = {}
for name in L_GZ:
    val = cookies.get(name)
    if val:
        mhc_headers[f"{L_AG}{name}"] = str(val)

print(f"mhc#-Header die wir haben ({len(mhc_headers)}):")
for k, v in mhc_headers.items():
    print(f"  {k}: {v[:40]}")
print()

QUERY = f'{{ dna_kit (id: "{KIT}", lang: "EN") {{ dna_matches (limit: 3) {{ total_count data {{ id display_name shared_dna relationship }} }} }} }}'

BASE_HDR = {
    "Content-Type":  "application/json",
    "Accept":        "application/json",
    "Referer":       f"{BASE}/dna/matches/{KIT}",
    "Origin":        BASE,
    "x-xsrf-token":  xsrf,
}

def probe(label, url, extra_hdrs=None):
    hdrs = {**BASE_HDR}
    if extra_hdrs: hdrs.update(extra_hdrs)
    try:
        resp = s.post(url, json={"query": QUERY}, headers=hdrs, timeout=15)
        tag  = "✅" if resp.status_code == 200 else "⚠️"
        body = resp.text
        print(f"  {tag} [{resp.status_code}] {label}")
        if body.strip():
            try:
                d = resp.json()
                if "data" in d and d["data"]:
                    print(f"       🎯 MATCH-DATEN! {json.dumps(d)[:500]}")
                elif "errors" in d:
                    print(f"       GQL-Fehler: {json.dumps(d['errors'])[:300]}")
                else:
                    print(f"       {json.dumps(d)[:300]}")
            except:
                print(f"       {body[:200]!r}")
        else:
            print(f"       (leerer Body)")
    except Exception as e:
        print(f"  ❌ {label}: {e}")
    print()

print("=" * 60)
print("TEST 1: php_tok + mhc# Headers")
print("=" * 60)
probe("php_tok + alle mhc# Cookie-Header",
      f"{GQLEP}?access_token={php_tok}", mhc_headers)

print("=" * 60)
print("TEST 2: fg_token_web + mhc# Headers")
print("=" * 60)
probe("fg_web + alle mhc# Cookie-Header",
      f"{GQLEP}?access_token={fg_web}", mhc_headers)

print("=" * 60)
print("TEST 3: Nur mhc#PHPSESSID (ohne access_token)")
print("=" * 60)
probe("nur mhc#PHPSESSID, kein access_token",
      GQLEP, {"mhc#PHPSESSID": cookies.get("PHPSESSID","")})

print("=" * 60)
print("TEST 4: mhc# Headers + access_token im Body")
print("=" * 60)
try:
    hdrs = {**BASE_HDR, **mhc_headers}
    resp = s.post(GQLEP, json={"query": QUERY, "access_token": php_tok}, headers=hdrs, timeout=15)
    tag  = "✅" if resp.status_code == 200 else "⚠️"
    print(f"  {tag} [{resp.status_code}] access_token im Body")
    if resp.text.strip():
        print(f"       {resp.text[:300]}")
    else:
        print(f"       (leerer Body)")
except Exception as e:
    print(f"  ❌ {e}")
print()

print("=" * 60)
print("TEST 5: mhc# Headers + form-encoded")
print("=" * 60)
try:
    hdrs = {**BASE_HDR, **mhc_headers, "Content-Type": "application/x-www-form-urlencoded"}
    resp = s.post(f"{GQLEP}?access_token={php_tok}",
                  data={"query": QUERY}, headers=hdrs, timeout=15)
    tag  = "✅" if resp.status_code == 200 else "⚠️"
    print(f"  {tag} [{resp.status_code}] form-encoded + mhc# Headers")
    if resp.text.strip():
        try: d=resp.json(); print(f"       {json.dumps(d)[:400]}")
        except: print(f"       {resp.text[:200]!r}")
    else:
        print(f"       (leerer Body)")
except Exception as e:
    print(f"  ❌ {e}")
print()

print("=" * 60)
print("TEST 6: Vollständige Response-Header anzeigen (php_tok + mhc#)")
print("=" * 60)
try:
    hdrs = {**BASE_HDR, **mhc_headers}
    resp = s.post(f"{GQLEP}?access_token={php_tok}",
                  json={"query": QUERY}, headers=hdrs, timeout=15, stream=True)
    print(f"  Status: {resp.status_code}")
    for k, v in resp.headers.items():
        print(f"  {k}: {v}")
    content = b""
    for chunk in resp.iter_content(chunk_size=1024):
        content += chunk
    # Versuche zu dekomprimieren
    try:
        import gzip
        body = gzip.decompress(content).decode("utf-8","replace")
    except:
        body = content.decode("utf-8","replace")
    print(f"  Body ({len(body)} chars): {body[:400]!r}")
except Exception as e:
    print(f"  ❌ {e}")
