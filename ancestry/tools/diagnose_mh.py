#!/usr/bin/env python3
"""
Diagnose-Script Phase 12:
  A) Findet L.aG (Header-Präfix) aus DnaResultsBundled.js
  B) Testet /web-family-graphql mit bekannten Cookies als explizite Header
  C) Holt Typ-4-Token (verschiedene clientId-Werte)
"""
import json, re, sys, time
from pathlib import Path
import requests

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)

KIT  = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
BASE = "https://www.myheritage.com"
GQLEP= f"{BASE}/web-family-graphql"
UA   = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

s = requests.Session()
s.cookies.update(cookies)
s.headers["User-Agent"] = UA

print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text
m = re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html)
xsrf = m.group(1) if m else ""
fg_web = re.search(r'"fg_token_web"\s*:\s*"([^"]+)"', html)
fg_web = fg_web.group(1) if fg_web else ""

# PHP-Token holen
tok_url = f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php?_={int(time.time()*1000)}&csrf_token={xsrf}"
php_tok = (s.get(tok_url, headers={"Accept":"application/json","Referer":f"{BASE}/dna/matches/{KIT}"}, timeout=15)
             .json().get("data",{}).get("token",""))

print(f"xsrf    : {xsrf[:40]}")
print(f"php_tok : {php_tok[:50]}")
print(f"fg_web  : {fg_web[:50]}\n")

# ── DnaResultsBundled laden ───────────────────────────────────────────────────
bundle_map = {}
for m2 in re.finditer(r'src="((?:https?://[^"]+|/[^"]+/bundles/JS/[^"]+)\.js[^"]*)"', html):
    url = m2.group(1)
    if not url.startswith("http"): url = BASE + url
    bundle_map[url.split("/")[-1].split("?")[0]] = url

dna_url = next((v for k, v in bundle_map.items() if "DnaResults" in k), None)
js = requests.Session().get(dna_url, headers={"User-Agent": UA}, timeout=30).text

# ══════════════════════════════════════════════════════════════════════════════
# A) L.aG finden – Kontext nach dem i=[...] Array
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("A) L.aG (Header-Präfix) suchen")
print("=" * 60)

# Finde vollständigen Array
arr_m = re.search(r'(\["mh_automations"[^\]]*\])', js)
if arr_m:
    arr_end = arr_m.end()
    # Zeige was nach dem Array kommt (dort sollte s= sein)
    after = js[arr_end:arr_end+600]
    print(f"Nach dem Array:\n{after}\n")

# Suche auch direkt nach dem s= Wert
for pat in [r',s="([^"]{0,40})",', r'const s="([^"]{0,40})"', r';s="([^"]{0,40})"']:
    m3 = re.search(pat, js[max(0,arr_m.start()-100):arr_m.end()+500] if arr_m else js)
    if m3:
        print(f"s= Wert (Muster '{pat}'): {m3.group(1)!r}")

# ══════════════════════════════════════════════════════════════════════════════
# B) /web-family-graphql mit Cookie-Werten als explizite Header
# ══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 60)
print("B) /web-family-graphql mit expliziten Cookie-Headern")
print("=" * 60)

QUERY = f'{{ dna_kit (id: "{KIT}", lang: "EN") {{ dna_matches (limit: 3) {{ total_count data {{ id display_name shared_dna relationship }} }} }} }}'

def probe(label, extra_hdrs):
    hdrs = {
        "Content-Type": "application/json",
        "Accept":       "application/json",
        "Referer":      f"{BASE}/dna/matches/{KIT}",
        "Origin":       BASE,
        "x-xsrf-token": xsrf,
    }
    hdrs.update(extra_hdrs)
    try:
        resp = s.post(f"{GQLEP}?access_token={php_tok}",
                      json={"query": QUERY}, headers=hdrs, timeout=15)
        tag  = "✅" if resp.status_code==200 else "⚠️"
        body = resp.text
        print(f"  {tag} [{resp.status_code}] {label}")
        if body.strip():
            try:
                d = resp.json()
                if "data" in d and d["data"]:
                    print(f"       🎯 MATCH-DATEN! {json.dumps(d)[:500]}")
                else:
                    print(f"       {json.dumps(d)[:300]}")
            except:
                print(f"       {body[:200]!r}")
        else:
            print(f"       (leerer Body)")
    except Exception as e:
        print(f"  ❌ {label}: {e}")
    print()

# PHPSESSID ohne Präfix
probe("PHPSESSID als Header",
      {"PHPSESSID": cookies.get("PHPSESSID","")})

# PHPSESSID mit x-mh- Präfix
probe("x-mh-PHPSESSID als Header",
      {"x-mh-PHPSESSID": cookies.get("PHPSESSID","")})

# Alle bekannten Cookies als Headers (ohne Präfix)
all_cookie_hdrs = {k: str(v) for k, v in cookies.items()
                   if k in ["PHPSESSID","device_id","mhc_version","uuid","data8"]}
probe("Alle bekannten Cookies als Headers",
      all_cookie_hdrs)

# Mit x-mh- Präfix für alle
xmh_hdrs = {f"x-mh-{k}": str(v) for k, v in all_cookie_hdrs.items()}
probe("x-mh-{name} Präfix für alle",
      xmh_hdrs)

# ══════════════════════════════════════════════════════════════════════════════
# C) Verschiedene clientId-Werte für Typ-4-Token
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("C) Token-Typen mit verschiedenen clientId-Werten")
print("=" * 60)

for client_id in [4, 3, 2, 1, 35509924739, 10, 100]:
    ts = int(time.time()*1000)
    url = f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php?_={ts}&csrf_token={xsrf}&clientId={client_id}"
    try:
        resp = requests.Session().get(url, cookies=cookies, headers={"User-Agent":UA,"Accept":"application/json"}, timeout=10)
        d = resp.json()
        tok = (d.get("data") or {}).get("token","")
        tok_type = tok.split(".")[0] if tok else "❌"
        print(f"  clientId={client_id}: Token-Typ {tok_type!r}  {tok[:50] if tok else '(leer)'}")
    except Exception as e:
        print(f"  clientId={client_id}: Fehler: {e}")
