#!/usr/bin/env python3
"""
Diagnose-Script Phase 5:
  A) FamilyGraphTokenBundled.js lesen (zeigt wie FG-Token benutzt wird)
  B) DnaResultsBundled.js nach API-Calls scannen
  C) uuid/data8p2 JWTs als FamilyGraph access_token testen
"""
import json, re, base64
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

# ── Hauptseite laden ──────────────────────────────────────────────────────────
print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text

def find(pattern, default=""):
    m = re.search(pattern, html)
    return m.group(1) if m else default

xsrf   = find(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']')
fg_tok = find(r'"fg_token_web"\s*:\s*"([^"]+)"') or \
         find(r'fg_token_web\s*[=:]\s*["\']([^"\']+)["\']')
uuid_c = cookies.get("uuid", "")
data8p2= cookies.get("data8p2", "")

print(f"xsrf         : {xsrf[:40] if xsrf else '❌'}")
print(f"fg_token_web : {fg_tok[:40] if fg_tok else '❌'}")
print(f"uuid (JWT)   : {uuid_c[:60] if uuid_c else '❌'}")
print(f"data8p2 (JWT): {data8p2[:60] if data8p2 else '❌'}")
print()

# JWT Payload dekodieren (nur zur Info)
def decode_jwt_payload(token):
    try:
        parts = token.split(".")
        if len(parts) < 2: return {}
        pad = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(pad))
    except:
        return {}

if uuid_c:
    pl = decode_jwt_payload(uuid_c)
    print(f"uuid JWT payload: {json.dumps(pl)[:200]}")
if data8p2:
    pl2 = decode_jwt_payload(data8p2)
    print(f"data8p2 payload: {json.dumps(pl2)[:200]}")
print()

# ── Bundle-URLs aus HTML ──────────────────────────────────────────────────────
bundle_map = {}
for m in re.finditer(r'src="((?:https?://[^"]+|/[^"]+/bundles/JS/[^"]+)\.js[^"]*)"', html):
    url = m.group(1)
    name = url.split("/")[-1].split("?")[0]
    if not url.startswith("http"):
        url = BASE + url
    bundle_map[name] = url

# ══════════════════════════════════════════════════════════════════════════════
# A) FamilyGraphTokenBundled.js lesen
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("A) FamilyGraphTokenBundled.js")
print("=" * 60)

fg_bundle_url = next((v for k, v in bundle_map.items() if "FamilyGraphToken" in k), None)
if fg_bundle_url:
    print(f"URL: {fg_bundle_url}")
    r = s.get(fg_bundle_url, timeout=15)
    content = r.text
    print(f"Inhalt ({len(content)} Zeichen):")
    print(content)
else:
    print("❌ FamilyGraphTokenBundled nicht gefunden in Bundle-Map")
    print("Bekannte Bundle-Namen:", list(bundle_map.keys())[:10])
print()

# ══════════════════════════════════════════════════════════════════════════════
# B) DnaResultsBundled.js nach fetch/axios/endpoint scannen
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("B) DnaResultsBundled.js – API-Call-Scan")
print("=" * 60)

dna_bundle_url = next((v for k, v in bundle_map.items() if "DnaResults" in k), None)
if dna_bundle_url:
    print(f"Lade {dna_bundle_url[-60:]} …")
    r2 = s.get(dna_bundle_url, timeout=30)
    js = r2.text
    print(f"  Größe: {len(js)//1024}KB")

    endpoints = set()

    # Muster 1: String-Pfade mit dna/match/segment Keywords
    for m in re.finditer(r'["\`]((?:https?://|/)[A-Za-z0-9/_\-\.]{5,80})["\`]', js):
        ep = m.group(1)
        if any(kw in ep.lower() for kw in ["dna","match","segment","chromosome","relatives"]):
            endpoints.add(ep)

    # Muster 2: fetch/axios calls
    for m in re.finditer(r'(?:fetch|axios\.(?:get|post))\(\s*["\`](https?://[^"\'`]{5,120})["\`]', js):
        endpoints.add(m.group(1))

    # Muster 3: URL-Teile zusammengebaut (template literals)
    for m in re.finditer(r'["\`](/FP/[A-Za-z0-9/_\-\.]{3,80})["\`]', js):
        ep = m.group(1)
        if any(kw in ep.lower() for kw in ["dna","match","get","api"]):
            endpoints.add(ep)

    # Muster 4: FamilyGraph URL-Bau
    for m in re.finditer(r'["\`](https?://familygraph\.myheritage\.com/[^"\'`\s]{3,120})["\`]', js):
        endpoints.add(m.group(1))

    # Muster 5: PHP-Endpoints
    for m in re.finditer(r'["\`](/[A-Za-z0-9/_\-]+\.php)["\`]', js):
        endpoints.add(m.group(1))

    if endpoints:
        print(f"\n  Gefundene Pfade ({len(endpoints)}):")
        for ep in sorted(endpoints):
            print(f"    {ep}")
    else:
        print("  Keine Pfade gefunden")

    # Kontext-Suche für 'dna_match' / 'matches'
    print("\n  Kontext-Suche 'dna_match' (erste 5 Treffer):")
    for m in list(re.finditer(r'.{0,60}dna_match.{0,60}', js))[:5]:
        print(f"    …{m.group()}…")

    print("\n  Kontext-Suche 'familygraph' (erste 5 Treffer):")
    for m in list(re.finditer(r'.{0,80}familygraph.{0,80}', js, re.I))[:5]:
        print(f"    …{m.group()}…")
else:
    print("❌ DnaResultsBundled nicht gefunden")
print()

# ══════════════════════════════════════════════════════════════════════════════
# C) uuid/data8p2 JWTs gegen FamilyGraph testen
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("C) JWT-Tokens gegen FamilyGraph")
print("=" * 60)

def probe(label, url, params=None, hdrs=None):
    h = {"Referer": f"{BASE}/dna/matches/{KIT}", "Accept": "application/json, */*"}
    if hdrs: h.update(hdrs)
    try:
        resp = s.get(url, params=params or {}, headers=h, timeout=10)
        ct   = resp.headers.get("content-type","")
        tag  = "✅" if resp.status_code==200 else "⚠️"
        print(f"  {tag} [{resp.status_code}] {label}")
        if "json" in ct:
            try:
                d = resp.json()
                txt = json.dumps(d)
                keys = list(d.keys())[:15] if isinstance(d,dict) else f"[{len(d)}]"
                print(f"       Keys: {keys}")
                if any(k in txt for k in ["sharedDna","matchId","dna_match","matches","items","results","total"]):
                    print(f"       🎯 MATCH-DATEN!")
                print(f"       {txt[:400]}")
            except: print(f"       {resp.text[:200]!r}")
        else:
            print(f"       {resp.text[:150].replace(chr(10),' ')!r}")
    except Exception as e:
        print(f"  ❌ {label}: {e}")
    print()

for token_name, token_val in [("uuid", uuid_c), ("data8p2", data8p2)]:
    if not token_val:
        continue
    probe(f"{token_name} als access_token (Query)",
          f"{FG}/{KIT}/dna_matches",
          params={"access_token": token_val, "limit": 5})
    probe(f"{token_name} als Bearer-Header",
          f"{FG}/{KIT}/dna_matches",
          params={"limit": 5},
          hdrs={"Authorization": f"Bearer {token_val}"})

# PHP Exchange-Endpoint: Session → FG-Token
probe("PHP FG-Token Exchange",
      f"{BASE}/FP/API/FamilyGraph/get-access-token.php",
      params={"siteId": KIT},
      hdrs={"x-xsrf-token": xsrf, "X-Requested-With": "XMLHttpRequest"})

probe("PHP FG-Token Exchange v2",
      f"{BASE}/FP/Process/getFamilyGraphToken.php",
      params={"siteId": KIT},
      hdrs={"x-xsrf-token": xsrf, "X-Requested-With": "XMLHttpRequest"})
