#!/usr/bin/env python3
"""
Phase 14: Matches direkt aus SSR-HTML extrahieren.
  - Vergleicht ?p=1 vs ?p=2 vs ?p=3 auf echte Unterschiede
  - Sucht Match-Daten in HTML (cM-Werte, Namen, GUIDs)
  - Liest alle <script>-Tags nach eingebetteten Daten
"""
import json, re, sys, hashlib
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

# ══════════════════════════════════════════════════════════════════════════════
# A) Pagination testen: ?p=1 vs ?p=2 vs Offset-Varianten
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("A) Pagination – sind die Seiten wirklich identisch?")
print("=" * 60)

pages = {}
for variant in [
    ("p1",   f"{BASE}/dna/matches/{KIT}"),
    ("p2",   f"{BASE}/dna/matches/{KIT}?p=2"),
    ("p3",   f"{BASE}/dna/matches/{KIT}?p=3"),
    ("pg2",  f"{BASE}/dna/matches/{KIT}?page=2"),
    ("off50",f"{BASE}/dna/matches/{KIT}?offset=50"),
]:
    name, url = variant
    r = s.get(url, timeout=20)
    h = hashlib.md5(r.text.encode()).hexdigest()
    pages[name] = (len(r.text), h, r.text)
    print(f"  {name:6s} → {len(r.text):7d} chars  MD5={h[:16]}")

print()
# Sind sie alle identisch?
unique = set(h for _, h, _ in pages.values())
if len(unique) == 1:
    print("  ⚠️  Alle Seiten identisch → Server ignoriert Pagination-Parameter")
else:
    print(f"  ✅ {len(unique)} verschiedene Versionen gefunden!")
    for name, (sz, h, _) in pages.items():
        print(f"     {name}: {h[:16]}")
print()

# Haupt-HTML für weitere Analyse
html = pages["p1"][2]

# ══════════════════════════════════════════════════════════════════════════════
# B) Alle <script>-Tags durchsuchen nach eingebetteten Daten
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("B) <script>-Tags – JSON / eingebettete Daten")
print("=" * 60)

scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
print(f"  {len(scripts)} Script-Tags gefunden")
for i, sc in enumerate(scripts):
    sc = sc.strip()
    if not sc or sc.startswith("//"):
        continue
    # Große Script-Tags (>500 Zeichen) mit interessantem Inhalt
    if len(sc) > 200:
        # Nach Match-Daten suchen
        if any(kw in sc for kw in ["dna_match","dnaMatch","shared","cM","matchGuid","match_guid",
                                    "display_name","sharedDna","firstName","lastName"]):
            print(f"\n  *** Script {i+1} ({len(sc)} chars) – MATCH-DATEN:")
            print(f"  {sc[:1000]}")
        elif any(kw in sc for kw in ["window.", "initialState", "__STATE__", "pageProps",
                                      "__NEXT_DATA__", "serverData", "preloaded"]):
            kws = [k for k in ["window.","initialState","__STATE__","pageProps","__NEXT_DATA__","serverData","preloaded"] if k in sc]
            print(f"\n  Script {i+1} ({len(sc)} chars) – Vars: {kws}")
            print(f"  Vorschau: {sc[:400]}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# C) Match-Daten in HTML-Markup (cM-Werte, Namen, GUIDs)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("C) Match-Daten aus HTML-Markup")
print("=" * 60)

# cM-Werte suchen
cm_vals = re.findall(r'(\d+(?:\.\d+)?)\s*(?:cM|shared_cm|sharedCm)', html)
print(f"  cM-Werte gefunden: {cm_vals[:20]}")

# GUIDs suchen (UUID-Format)
guids = re.findall(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', html)
print(f"  GUIDs gefunden: {len(guids)} Stück, erste 10: {guids[:10]}")

# Lange alphanumerische IDs (wie MH-Kit-IDs)
kit_ids = re.findall(r'[A-Z0-9]{20,}', html)
kit_ids = [x for x in kit_ids if x != KIT]
print(f"  Lange IDs (ex. KIT): {len(kit_ids)} Stück, erste 5: {kit_ids[:5]}")

# Personen-Namen in match-ähnlichem Kontext
name_patterns = re.findall(r'(?:display_name|displayName|fullName|matchName)["\s:=]+["\']([^"\']{2,50})["\']', html)
print(f"  Namen-Pattern: {name_patterns[:10]}")

# JSON-ähnliche Match-Objekte
json_matches = re.findall(r'\{"(?:id|matchId|match_id)"\s*:\s*"([^"]+)"[^}]{0,200}"(?:name|display_name|displayName)"\s*:\s*"([^"]+)"', html)
print(f"  JSON-Match-Objekte: {json_matches[:5]}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# D) Suche nach window.* Zuweisungen
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("D) window.* Zuweisungen im HTML")
print("=" * 60)
window_vars = re.findall(r'window\.([A-Za-z][A-Za-z0-9_]+)\s*=\s*({[^;]{0,200}|"[^"]{0,100}"|\'[^\']{0,100}\'|\[[^\]]{0,200}\])', html)
for name, val in window_vars[:20]:
    print(f"  window.{name} = {val[:80]}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# E) Rohe HTML-Struktur für Match-Cards
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("E) HTML-Struktur rund um 'match' / 'dna'")
print("=" * 60)
for kw in ["dna-match","match-card","matchCard","data-match","dnaMatchRow"]:
    occ = html.lower().count(kw.lower())
    if occ > 0:
        pos = html.lower().find(kw.lower())
        print(f"  '{kw}': {occ} Vorkommen")
        print(f"    Kontext: …{html[max(0,pos-50):pos+200]}…\n")
