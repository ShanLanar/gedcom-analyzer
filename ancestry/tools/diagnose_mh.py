#!/usr/bin/env python3
"""
Diagnose-Script Phase 4:
  A) Cookies analysieren (sucht nach FamilyGraph-Token)
  B) JS-Bundle laden und DNA-API-Endpunkte raussuchen
  C) Gefundene Endpunkte direkt testen
"""
import json, re, sys
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

xsrf  = find(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']')
fg_tok= find(r'"fg_token_web"\s*:\s*"([^"]+)"') or \
        find(r'fg_token_web\s*[=:]\s*["\']([^"\']+)["\']')

print(f"xsrf         : {xsrf[:50] if xsrf else '❌'}")
print(f"fg_token_web : {fg_tok[:50] if fg_tok else '❌'}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# A) COOKIES analysieren
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("A) COOKIES")
print("=" * 60)
interesting = []
for name, val in cookies.items():
    v = str(val)
    # Lange Token-artige Werte oder bekannte Namen
    if any(kw in name.lower() for kw in ["token","auth","access","fg","oauth","jwt","key","secret"]):
        print(f"  *** {name} = {v[:80]}")
        interesting.append((name, v))
    elif len(v) > 30 and re.match(r'^[A-Za-z0-9._\-]+$', v):
        print(f"  {name} = {v[:80]}")
        interesting.append((name, v))
    else:
        print(f"  {name} = {v[:40]}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# B) JS-BUNDLE analysieren
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("B) JS-BUNDLE – suche API-Endpunkte")
print("=" * 60)

# Alle JS-Bundle-URLs aus HTML extrahieren
bundle_urls = re.findall(r'src="(https?://[^"]+\.js[^"]*)"', html)
bundle_urls += re.findall(r'src="(/[^"]+\.js[^"]*)"', html)
# Chunk-URLs
chunk_urls  = re.findall(r'"((?:https?://[^"]+|/[^"]+)/chunk[^"]+\.js)"', html)
bundle_urls += chunk_urls

# Nur eindeutige URLs, Priorisierung: "main", "app", "dna" im Namen
def prio(u):
    u_low = u.lower()
    for kw in ["dna","match","app","main","bundle","index"]:
        if kw in u_low: return 0
    return 1

bundle_urls = sorted(set(bundle_urls), key=prio)
print(f"  {len(bundle_urls)} JS-Bundles gefunden")

# Max. 5 Bundles durchsuchen (die größten/relevantesten zuerst)
DNA_KEYWORDS = [
    "dna_matches", "dna-matches", "getDnaMatches", "getMatches",
    "dnaMatch", "familygraph", "segments", "chromosome",
    "/dna/api", "ClanSearch", "ajaxCall",
]

found_endpoints = set()
bundles_searched = 0

for url in bundle_urls[:12]:
    if not url.startswith("http"):
        url = BASE + url
    try:
        r = s.get(url, timeout=15)
        content = r.text
        size_kb = len(content) // 1024
        has_dna = any(kw in content for kw in DNA_KEYWORDS)
        marker = "🎯" if has_dna else "  "
        print(f"  {marker} {url[-70:]}  ({size_kb}KB)")
        if has_dna:
            bundles_searched += 1
            # Endpunkte extrahieren
            # Muster 1: String-Literals mit API-Pfad
            for m in re.finditer(r'["\`]((?:/api|/FP|/dna|https?://familygraph)[^"\`\s]{3,80})["\`]', content):
                ep = m.group(1)
                if any(kw in ep.lower() for kw in ["dna","match","segment"]):
                    found_endpoints.add(ep)
            # Muster 2: Template-Strings mit KIT/siteId
            for m in re.finditer(r'["\`]((?:/api|/FP|/dna|https?://)[^\`"]{3,60}(?:siteId|siteGuid|test_guid)[^\`"]{0,40})["\`]', content):
                found_endpoints.add(m.group(1))
            # Muster 3: fetch/axios Aufrufe
            for m in re.finditer(r'(?:fetch|axios\.get|axios\.post)\(["\`](https?://[^"\'`\s]{10,100})["\`]', content):
                found_endpoints.add(m.group(1))
    except Exception as e:
        print(f"     Fehler: {e}")

print()
if found_endpoints:
    print(f"  Gefundene API-Pfade ({len(found_endpoints)}):")
    for ep in sorted(found_endpoints):
        print(f"    {ep}")
else:
    print("  ❌ Keine DNA-API-Pfade in Bundles gefunden")
print()

# ══════════════════════════════════════════════════════════════════════════════
# C) Mit Cookie-Tokens testen
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("C) FamilyGraph mit Cookie-Tokens testen")
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
                keys = list(d.keys())[:12] if isinstance(d,dict) else f"[{len(d)}]"
                print(f"       Keys: {keys}")
                if any(k in txt for k in ["sharedDna","matchId","dna_match","matches","items","results"]):
                    print(f"       🎯 MATCH-DATEN!")
                print(f"       {txt[:300]}")
            except: print(f"       {resp.text[:200]!r}")
        else:
            print(f"       {resp.text[:150].replace(chr(10),' ')!r}")
    except Exception as e:
        print(f"  ❌ {label}: {e}")
    print()

# Mit jedem interessanten Cookie-Wert als access_token testen
for name, val in interesting[:6]:
    probe(
        f"FG – {name} als access_token",
        f"{FG}/{KIT}/dna_matches",
        params={"access_token": val, "limit": 5},
    )

# Auch gefundene Endpunkte aus Bundle testen
for ep in list(found_endpoints)[:5]:
    if ep.startswith("http"):
        probe(f"Bundle-Fund: {ep[:60]}", ep,
              params={"access_token": fg_tok, "siteId": KIT, "limit": 5},
              hdrs={"x-xsrf-token": xsrf})
    else:
        probe(f"Bundle-Fund: {ep[:60]}", BASE + ep,
              params={"access_token": fg_tok, "siteId": KIT, "limit": 5},
              hdrs={"x-xsrf-token": xsrf})
