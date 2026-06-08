#!/usr/bin/env python3
"""
Diagnose-Script Phase 9:
  Endpunkt www.myheritage.com/web-family-graphql (Proxy-Endpunkt, den
  MyHeritage's window.fetch-Patch benutzt statt familygraphql.myheritage.com).
"""
import json, re, time, sys
from pathlib import Path
import requests

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)

KIT  = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
BASE = "https://www.myheritage.com"
# Echter Endpunkt (MyHeritage leitet intern familygraphql.myheritage.com dorthin)
GQLEP = f"{BASE}/web-family-graphql"
UA   = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

s = requests.Session()
s.cookies.update(cookies)
s.headers["User-Agent"] = UA

# ── Tokens holen ──────────────────────────────────────────────────────────────
print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text

def find(pat):
    m = re.search(pat, html)
    return m.group(1) if m else ""

xsrf    = find(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']')
fg_web  = find(r'"fg_token_web"\s*:\s*"([^"]+)"')   # Typ 4 (Web-Token)

print("Hole PHP-Token (Typ 1) …")
tok_url = f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php?_={int(time.time()*1000)}&csrf_token={xsrf}"
r_tok   = s.get(tok_url, headers={"Accept": "application/json",
                                   "Referer": f"{BASE}/dna/matches/{KIT}"}, timeout=15)
php_tok = (r_tok.json().get("data") or {}).get("token", "")

print(f"xsrf     : {xsrf[:40] if xsrf else '❌'}")
print(f"fg_web   : {fg_web[:40] if fg_web else '❌'}  (Typ 4)")
print(f"php_tok  : {php_tok[:40] if php_tok else '❌'}  (Typ 1)")
print()

QUERY_MIN = f'{{ dna_kit (id: "{KIT}", lang: "EN") {{ dna_matches (limit: 3) {{ total_count data {{ id display_name shared_dna relationship }} }} }} }}'

BASE_HDR = {
    "Content-Type":      "application/json",
    "Accept":            "application/json",
    "Referer":           f"{BASE}/dna/matches/{KIT}",
    "Origin":            BASE,
    "X-Requested-With":  "XMLHttpRequest",
}

def probe(label, url, tok, extra_hdrs=None):
    hdrs = {**BASE_HDR, "x-xsrf-token": xsrf}
    if extra_hdrs:
        hdrs.update(extra_hdrs)
    try:
        resp = s.post(url, json={"query": QUERY_MIN}, headers=hdrs, timeout=15)
        ct   = resp.headers.get("content-type","")
        tag  = "✅" if resp.status_code == 200 else "⚠️"
        print(f"  {tag} [{resp.status_code}] {label}")
        body = resp.text
        if body.strip() and "json" in ct:
            try:
                d = resp.json()
                txt = json.dumps(d)
                if "data" in d and d["data"]:
                    print(f"       🎯 MATCH-DATEN! {txt[:600]}")
                elif "errors" in d:
                    print(f"       GQL-Fehler: {json.dumps(d['errors'])[:300]}")
                else:
                    print(f"       {txt[:300]}")
            except:
                print(f"       {body[:200]!r}")
        elif body.strip():
            print(f"       {body[:200].replace(chr(10),' ')!r}")
        else:
            print(f"       (leerer Body)")
    except Exception as e:
        print(f"  ❌ {label}: {e}")
    print()

print("=" * 60)
print("1) /web-family-graphql mit PHP-Token (Typ 1)")
print("=" * 60)
probe("?access_token=php_tok",
      f"{GQLEP}?access_token={php_tok}", php_tok)

print("=" * 60)
print("2) /web-family-graphql mit fg_token_web (Typ 4)")
print("=" * 60)
probe("?access_token=fg_web",
      f"{GQLEP}?access_token={fg_web}", fg_web)

print("=" * 60)
print("3) /web-family-graphql – nur Cookies + xsrf, kein access_token")
print("=" * 60)
probe("nur Cookies", GQLEP, "")

print("=" * 60)
print("4) /web-family-graphql – PHP-Token im Body")
print("=" * 60)
try:
    hdrs = {**BASE_HDR, "x-xsrf-token": xsrf}
    resp = s.post(GQLEP, json={"query": QUERY_MIN, "access_token": php_tok}, headers=hdrs, timeout=15)
    ct   = resp.headers.get("content-type","")
    print(f"  {'✅' if resp.status_code==200 else '⚠️'} [{resp.status_code}] Token im Body")
    if resp.text.strip(): print(f"       {resp.text[:300]}")
    else: print(f"       (leerer Body)")
except Exception as e:
    print(f"  ❌ {e}")
print()

print("=" * 60)
print("5) Alle Response-Header bei Typ-4-Token zeigen")
print("=" * 60)
try:
    resp5 = s.post(f"{GQLEP}?access_token={fg_web}",
                   json={"query": QUERY_MIN},
                   headers={**BASE_HDR, "x-xsrf-token": xsrf},
                   timeout=15)
    print(f"  Status: {resp5.status_code}")
    for k, v in resp5.headers.items():
        print(f"  {k}: {v}")
    print(f"  Body: {resp5.text[:400]!r}")
except Exception as e:
    print(f"  ❌ {e}")
