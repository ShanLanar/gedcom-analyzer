#!/usr/bin/env python3
"""
Diagnose-Script Phase 10:
  A) Liest MainFullInitializeBundled.js und sucht Ze / web-family-graphql Kontext
  B) Liest das Relationships-Bundle und sucht nach Match-Lade-Logik
  C) Sucht nach alternativen PHP-Endpunkten
"""
import json, re, sys
from pathlib import Path
import requests

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)

KIT  = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
BASE = "https://www.myheritage.com"
UA   = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

s = requests.Session()
s.cookies.update(cookies)
s.headers["User-Agent"] = UA

print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text

# Bundle-URLs aus HTML
bundle_map = {}
for m in re.finditer(r'src="((?:https?://[^"]+|/[^"]+/bundles/JS/[^"]+)\.js[^"]*)"', html):
    url = m.group(1)
    name = url.split("/")[-1].split("?")[0]
    if not url.startswith("http"):
        url = BASE + url
    bundle_map[name] = url

def show_context(js, keyword, chars=300, max_hits=5):
    """Gibt Kontext um alle Vorkommen eines Keywords aus."""
    hits = [m.start() for m in re.finditer(re.escape(keyword), js)]
    if not hits:
        print(f"  '{keyword}' nicht gefunden.")
        return
    print(f"  '{keyword}' – {len(hits)} Vorkommen, erste {min(max_hits, len(hits))} gezeigt:")
    for i, pos in enumerate(hits[:max_hits]):
        start = max(0, pos - chars)
        end   = min(len(js), pos + chars)
        snippet = js[start:end].replace('\n', ' ')
        print(f"  [{i+1}] …{snippet}…")
        print()

# ══════════════════════════════════════════════════════════════════════════════
# A) MainFullInitializeBundled.js
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("A) MainFullInitializeBundled.js")
print("=" * 60)

main_url = next((v for k, v in bundle_map.items() if "MainFullInitialize" in k), None)
if main_url:
    print(f"Lade {main_url[-60:]} …")
    r = s.get(main_url, timeout=30)
    js_main = r.text
    print(f"Größe: {len(js_main)//1024}KB\n")

    show_context(js_main, "web-family-graphql", 400)
    show_context(js_main, "web-family-graph\"", 300)
    show_context(js_main, "graphql_token", 300)
    show_context(js_main, "app_id", 200, 3)

    # PHP-Endpunkte in diesem Bundle
    print("  PHP-Endpunkte in MainFullInitialize:")
    for m in re.finditer(r'["\`](/FP/[A-Za-z0-9/_\-]+\.php)["\`]', js_main):
        ep = m.group(1)
        if any(k in ep.lower() for k in ["dna","match","kit","relative","test"]):
            print(f"    {ep}")
else:
    print("  MainFullInitializeBundled nicht in Bundle-Map gefunden")
    print("  Verfügbare Bundles:", list(bundle_map.keys())[:8])
print()

# ══════════════════════════════════════════════════════════════════════════════
# B) Relationships-Bundle (onships/AncientDNA, 1231KB)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("B) Relationships-Bundle (1231KB)")
print("=" * 60)

rel_url = next((v for k, v in bundle_map.items()
                if "onships" in k or "Relationship" in k or ("Ancient" in k and len(k) > 50)), None)
if rel_url:
    print(f"Lade {rel_url[-60:]} …")
    r2 = s.get(rel_url, timeout=60)
    js_rel = r2.text
    print(f"Größe: {len(js_rel)//1024}KB\n")

    show_context(js_rel, "web-family-graphql", 400)
    show_context(js_rel, "dna_matches", 300, 3)

    print("  PHP-Endpunkte im Relationships-Bundle:")
    rel_php = set()
    for m in re.finditer(r'["\`](/(?:FP|api)[A-Za-z0-9/_\-]+\.php)["\`]', js_rel):
        ep = m.group(1)
        if any(k in ep.lower() for k in ["dna","match","kit","relative","test","segment"]):
            rel_php.add(ep)
    for ep in sorted(rel_php):
        print(f"    {ep}")
else:
    print("  Relationships-Bundle nicht gefunden")
    print("  Verfügbare Bundles:", list(bundle_map.keys())[:8])
print()

# ══════════════════════════════════════════════════════════════════════════════
# C) DnaResultsBundled – Kontext für Ze / fetch Calls
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("C) DnaResultsBundled – fetch/axios Calls")
print("=" * 60)

dna_url = next((v for k, v in bundle_map.items() if "DnaResults" in k), None)
if dna_url:
    r3 = s.get(dna_url, timeout=30)
    js_dna = r3.text
    print(f"Größe: {len(js_dna)//1024}KB\n")
    show_context(js_dna, "web-family-graphql", 400)
    show_context(js_dna, "access_token", 200, 3)
    show_context(js_dna, "authorization", 200, 3)

    print("  Alle PHP-Endpunkte in DnaResults:")
    dna_php = set()
    for m in re.finditer(r'["\`](/(?:FP|api)[A-Za-z0-9/_\-]+\.php)["\`]', js_dna):
        dna_php.add(m.group(1))
    for ep in sorted(dna_php):
        print(f"    {ep}")
