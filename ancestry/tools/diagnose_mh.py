#!/usr/bin/env python3
"""
Diagnose-Script Phase 11:
  Extrahiert aus DnaResultsBundled.js:
  - Den vollständigen i=["mh_automat…"] Cookie-Array
  - Den Header-Präfix (L.aG / s=…)
  - Alle exportierten Konstanten rund um den GraphQL-Aufruf
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

bundle_map = {}
for m in re.finditer(r'src="((?:https?://[^"]+|/[^"]+/bundles/JS/[^"]+)\.js[^"]*)"', html):
    url = m.group(1)
    name = url.split("/")[-1].split("?")[0]
    if not url.startswith("http"):
        url = BASE + url
    bundle_map[name] = url

# ── DnaResultsBundled laden ───────────────────────────────────────────────────
dna_url = next((v for k, v in bundle_map.items() if "DnaResults" in k), None)
if not dna_url:
    print("DnaResultsBundled nicht gefunden!"); sys.exit(1)

print(f"Lade DnaResultsBundled …")
js = requests.Session().get(dna_url, headers={"User-Agent": UA}, timeout=30).text
print(f"Größe: {len(js)//1024}KB\n")

# ══════════════════════════════════════════════════════════════════════════════
# 1) Vollständiger Kontext rund um web-family-graphql (±1200 Zeichen)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("1) web-family-graphql – vollständiger Kontext")
print("=" * 60)
pos = js.find("web-family-graphql")
if pos >= 0:
    start = max(0, pos - 1200)
    end   = min(len(js), pos + 1200)
    print(js[start:end])
print()

# ══════════════════════════════════════════════════════════════════════════════
# 2) mh_automat Array – vollständiger Inhalt
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("2) mh_automat Array")
print("=" * 60)
m = re.search(r'(\[["\'](mh_[^"\']+)["\'][^\]]*\])', js)
if m:
    print(f"Gefundener Array: {m.group(1)[:500]}")
else:
    # Breiteren Match versuchen
    m2 = re.search(r'mh_automat[a-z_]*', js)
    if m2:
        pos2 = m2.start()
        print(js[max(0,pos2-200):pos2+400])
    else:
        print("❌ 'mh_automat' nicht gefunden – suche nach 'mh_':")
        for m3 in re.finditer(r'"(mh_[a-z_]+)"', js):
            print(f"  {m3.group(1)}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# 3) Alle Exports des GraphQL-Moduls
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("3) Exports des GraphQL-Moduls (aG, Gz, mZ, nk, Zh, lD, wv)")
print("=" * 60)
# Suche den Export-Block
export_m = re.search(r'(Zh:\(\)=>[^,}]{1,30},aG:\(\)=>[^,}]{1,30},lD:\(\)=>[^,}]{1,30}[^}]{0,200})', js)
if export_m:
    print(f"Export-Block: {export_m.group(1)}")
else:
    # Alternativ: Kontext um 'aG:' suchen
    for m in re.finditer(r'.{0,100}aG:\(\)=>.{0,100}', js):
        print(f"aG-Kontext: {m.group()}")
        break
print()

# ══════════════════════════════════════════════════════════════════════════════
# 4) Alle String-Konstanten in Nähe des GraphQL-Aufrufs
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("4) String-Konstanten rund um FamilyGraphQL-Service")
print("=" * 60)
svc_m = re.search(r'familyGraphQlService', js)
if svc_m:
    pos3 = svc_m.start()
    snippet = js[max(0,pos3-2000):pos3+500]
    # Alle String-Literale extrahieren
    strings = re.findall(r'"([^"]{2,60})"', snippet)
    strings = [x for x in strings if not x.startswith('/') and not x.startswith('http')]
    print(f"Strings in Nähe von familyGraphQlService: {strings[:30]}")
    print()
    print(f"Vollständiger Kontext (-2000..+500):")
    print(snippet[:1000])
print()

# ══════════════════════════════════════════════════════════════════════════════
# 5) Prüfe ob mh_automat* Cookies in unserem Cookie-File vorhanden
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("5) Unsere Cookies vs. mh_* Cookies")
print("=" * 60)
print("Alle Cookies in myheritage_cookies.json:")
for name, val in cookies.items():
    print(f"  {name} = {str(val)[:50]}")
print()
mh_auto = {k: v for k, v in cookies.items() if 'automat' in k.lower() or 'mh_' in k.lower()}
if mh_auto:
    print(f"mh_automat* gefunden: {mh_auto}")
else:
    print("❌ Keine mh_automat* Cookies im Cookie-File!")
    print()
    print("=> LÖSUNG: Browser-Konsole auf der DNA-Matches-Seite öffnen und eingeben:")
    print('   let r={}; document.cookie.split(";").forEach(c=>{const[k,...v]=c.trim().split("="); if(k.startsWith("mh_"))r[k]=v.join("=");}); console.log(JSON.stringify(r));')
    print()
    print("=> Das zeigt die mh_* Cookies im Browser. Diese bitte hier einfügen.")
