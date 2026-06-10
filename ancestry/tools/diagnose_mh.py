#!/usr/bin/env python3
"""
Phase 15: fgTokenDna aus window.promotionalBannerSystemData testen.
"""
import json
import re
import sys
import time
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

# Tokens extrahieren
xsrf   = (re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html) or re.compile('').search('')).group(1) or ""
m_xsrf = re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html)
xsrf   = m_xsrf.group(1) if m_xsrf else ""

# fgTokenDna aus promotionalBannerSystemData
m_promo = re.search(r'promotionalBannerSystemData\s*=\s*(\{.{10,5000}\})', html)
fg_dna_tok = ""
if m_promo:
    try:
        promo = json.loads(m_promo.group(1))
        fg_dna_tok = promo.get("fgTokenDna", "")
        print(f"fgTokenDna : {fg_dna_tok[:70]}…")
    except Exception as e:
        # JSON-Parsing kann manchmal fehlschlagen, Regex-Fallback
        m2 = re.search(r'"fgTokenDna"\s*:\s*"([^"]+)"', m_promo.group(1))
        if m2:
            fg_dna_tok = m2.group(1)
            print(f"fgTokenDna : {fg_dna_tok[:70]}…")

if not fg_dna_tok:
    # Direkter HTML-Fallback
    m3 = re.search(r'"fgTokenDna"\s*:\s*"([^"]+)"', html)
    if m3:
        fg_dna_tok = m3.group(1)
        print(f"fgTokenDna (Fallback): {fg_dna_tok[:70]}…")

# Normaler PHP-Token
tok_url = f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php?_={int(time.time()*1000)}&csrf_token={xsrf}"
php_tok = s.get(tok_url, headers={"Accept":"application/json"}, timeout=15).json().get("data",{}).get("token","")
fg_web  = (re.search(r'"fg_token_web"\s*:\s*"([^"]+)"', html) or re.compile('').search('')).group(1) or ""
m_fgw = re.search(r'"fg_token_web"\s*:\s*"([^"]+)"', html)
fg_web = m_fgw.group(1) if m_fgw else ""

print(f"fg_token_web: {fg_web[:60]}")
print(f"php_tok    : {php_tok[:60]}")
print()

QUERY_MIN = f'{{ dna_kit (id: "{KIT}", lang: "EN") {{ dna_matches (limit: 3) {{ total_count data {{ id display_name shared_dna relationship }} }} }} }}'
QUERY_FULL = f'''{{
  dna_kit (id: "{KIT}", lang: "EN") {{
    dna_matches (limit: 5, offset: 0) {{
      total_count
      data {{
        id
        display_name
        first_name
        last_name
        shared_dna
        shared_segments
        relationship
        predicted_relationship
        image_url
        added_date
        kit_id
        country
      }}
    }}
  }}
}}'''

HDR = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Referer":      f"{BASE}/dna/matches/{KIT}",
    "Origin":       BASE,
    "x-xsrf-token": xsrf,
    "mhc#PHPSESSID": cookies.get("PHPSESSID",""),
}

def probe(label, url, query=QUERY_MIN):
    try:
        resp = s.post(url, json={"query": query}, headers=HDR, timeout=15)
        tag  = "✅" if resp.status_code == 200 else "⚠️"
        body = resp.text
        print(f"{tag} [{resp.status_code}] {label}")
        if body.strip():
            try:
                d = resp.json()
                txt = json.dumps(d)
                if "data" in d and d["data"]:
                    print(f"  🎯 MATCH-DATEN! {txt[:600]}")
                elif "errors" in d:
                    err = json.dumps(d["errors"])[:300]
                    print(f"  GQL-Fehler: {err}")
                else:
                    print(f"  {txt[:300]}")
            except:
                print(f"  {body[:200]!r}")
        else:
            print("  (leerer Body)")
    except Exception as e:
        print(f"❌ {label}: {e}")
    print()

print("=" * 60)
print("TEST 1: fgTokenDna als access_token")
print("=" * 60)
if fg_dna_tok:
    probe("fgTokenDna + JSON", f"{GQLEP}?access_token={fg_dna_tok}")
else:
    print("❌ fgTokenDna nicht gefunden!")
print()

print("=" * 60)
print("TEST 2: fgTokenDna – vollständige Query")
print("=" * 60)
if fg_dna_tok:
    probe("fgTokenDna + volle Query", f"{GQLEP}?access_token={fg_dna_tok}", QUERY_FULL)
print()

print("=" * 60)
print("TEST 3: fgTokenDna + form-encoded")
print("=" * 60)
if fg_dna_tok:
    try:
        hdrs = {**HDR, "Content-Type": "application/x-www-form-urlencoded"}
        resp = s.post(f"{GQLEP}?access_token={fg_dna_tok}",
                      data={"query": QUERY_MIN}, headers=hdrs, timeout=15)
        tag  = "✅" if resp.status_code == 200 else "⚠️"
        print(f"{tag} [{resp.status_code}] form-encoded")
        if resp.text.strip():
            try: d=resp.json(); print(f"  {json.dumps(d)[:400]}")
            except: print(f"  {resp.text[:200]!r}")
        else:
            print("  (leerer Body)")
    except Exception as e:
        print(f"❌ {e}")
print()

print("=" * 60)
print("TEST 4: Pagination – was ist anders zwischen p1 und p2?")
print("=" * 60)
r1 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20).text
r2 = s.get(f"{BASE}/dna/matches/{KIT}?p=2", timeout=20).text
# Zeige was sich unterscheidet
diffs = []
for i, (c1, c2) in enumerate(zip(r1, r2)):
    if c1 != c2:
        start = max(0, i-50)
        end   = min(len(r1), i+100)
        diffs.append((i, r1[start:end], r2[start:end]))
        if len(diffs) >= 5:
            break
print(f"  Unterschiede zwischen p1 und p2: {len(r1)-len(r2)} chars Längenunterschied")
for pos, ctx1, ctx2 in diffs[:3]:
    print(f"  Position {pos}:")
    print(f"    p1: …{ctx1}…")
    print(f"    p2: …{ctx2}…")
    print()
