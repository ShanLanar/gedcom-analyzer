#!/usr/bin/env python3
"""
Diagnose-Script Phase 7: FG-Token bekannt – verschiedene Auth-Methoden testen.
"""
import json, re, time
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

KIT   = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
BASE  = "https://www.myheritage.com"
GQLEP = "https://familygraphql.myheritage.com"

# ── Hauptseite + Token ────────────────────────────────────────────────────────
print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text
m = re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html)
xsrf = m.group(1) if m else ""

print("Hole FamilyGraph-Token …")
tok_url = f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php?_={int(time.time()*1000)}&csrf_token={xsrf}"
r_tok = s.get(tok_url, headers={"Accept": "application/json",
                                 "Referer": f"{BASE}/dna/matches/{KIT}"}, timeout=15)
fg_tok = r_tok.json()["data"]["token"]
print(f"Token: {fg_tok[:60]}…\n")

# Einfache Query für alle Tests
QUERY = f'{{ dna_kit (id: "{KIT}", lang: "EN") {{ dna_matches (limit: 3) {{ total_count data {{ id display_name shared_dna relationship }} }} }} }}'

def probe(label, **kwargs):
    try:
        resp = s.request(**kwargs)
        ct  = resp.headers.get("content-type", "")
        tag = "✅" if resp.status_code == 200 else "⚠️"
        print(f"  {tag} [{resp.status_code}] {label}")
        body = resp.text[:600]
        if "json" in ct and resp.text.strip():
            try:
                d = resp.json()
                if "data" in d and d["data"]:
                    print(f"       🎯 DATEN! {json.dumps(d)[:400]}")
                elif "errors" in d:
                    print(f"       GraphQL-Fehler: {json.dumps(d['errors'])[:200]}")
                else:
                    print(f"       {json.dumps(d)[:300]}")
            except:
                print(f"       {body}")
        else:
            print(f"       {body[:200]!r}")
    except Exception as e:
        print(f"  ❌ {label}: {e}")
    print()

print("=" * 60)
print("Test 1: access_token als URL-Param + JSON body")
print("=" * 60)
probe("POST GQLEP?access_token=...",
      method="POST", url=f"{GQLEP}?access_token={fg_tok}",
      json={"query": QUERY},
      headers={"Content-Type": "application/json", "Accept": "application/json",
               "Referer": f"{BASE}/dna/matches/{KIT}", "Origin": BASE})

print("=" * 60)
print("Test 2: form-encoded (wie Bundle: content-type=x-www-form-urlencoded)")
print("=" * 60)
probe("POST GQLEP form-encoded",
      method="POST", url=GQLEP,
      data={"access_token": fg_tok, "query": QUERY},
      headers={"Content-Type": "application/x-www-form-urlencoded",
               "Accept": "application/json",
               "Referer": f"{BASE}/dna/matches/{KIT}", "Origin": BASE})

probe("POST GQLEP form-encoded + access_token in URL",
      method="POST", url=f"{GQLEP}?access_token={fg_tok}",
      data={"query": QUERY},
      headers={"Content-Type": "application/x-www-form-urlencoded",
               "Accept": "application/json",
               "Referer": f"{BASE}/dna/matches/{KIT}", "Origin": BASE})

print("=" * 60)
print("Test 3: /graphql Pfad-Varianten")
print("=" * 60)
for path in ["/graphql", "/api/graphql", "/api", "/"]:
    probe(f"POST {GQLEP}{path}?access_token=...",
          method="POST", url=f"{GQLEP}{path}?access_token={fg_tok}",
          json={"query": QUERY},
          headers={"Content-Type": "application/json", "Accept": "application/json",
                   "Referer": f"{BASE}/dna/matches/{KIT}", "Origin": BASE})

print("=" * 60)
print("Test 4: client-id Header (aus Bundle: clientId = memberId)")
print("=" * 60)
member_id = cookies.get("data8", "1111959401")
probe("POST + client-id Header",
      method="POST", url=f"{GQLEP}?access_token={fg_tok}",
      json={"query": QUERY},
      headers={"Content-Type": "application/json", "Accept": "application/json",
               "client-id": str(member_id), "x-client-id": str(member_id),
               "Referer": f"{BASE}/dna/matches/{KIT}", "Origin": BASE})

print("=" * 60)
print("Test 5: fg_token_web statt neuem Token")
print("=" * 60)
fg_web = re.search(r'"fg_token_web"\s*:\s*"([^"]+)"', html)
fg_web_tok = fg_web.group(1) if fg_web else ""
if fg_web_tok:
    probe("POST GQLEP?access_token=fg_token_web",
          method="POST", url=f"{GQLEP}?access_token={fg_web_tok}",
          json={"query": QUERY},
          headers={"Content-Type": "application/json", "Accept": "application/json",
                   "Referer": f"{BASE}/dna/matches/{KIT}", "Origin": BASE})

print("=" * 60)
print("Test 6: GET statt POST")
print("=" * 60)
import urllib.parse
probe("GET GQLEP?access_token=...&query=...",
      method="GET", url=GQLEP,
      params={"access_token": fg_tok, "query": QUERY},
      headers={"Accept": "application/json",
               "Referer": f"{BASE}/dna/matches/{KIT}"})
