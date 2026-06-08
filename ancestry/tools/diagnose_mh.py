#!/usr/bin/env python3
"""
Diagnose-Script Phase 6: FamilyGraph-Token holen + GraphQL-Query testen.
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

# ── Hauptseite laden → XSRF-Token ────────────────────────────────────────────
print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text
xsrf = (re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html) or re.Match()).group(1) \
       if re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html) else ""
print(f"xsrf: {xsrf[:40] if xsrf else '❌ nicht gefunden'}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# SCHRITT 1: FamilyGraph-Token über PHP-Endpoint holen
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("SCHRITT 1 – FamilyGraph-Token holen")
print("=" * 60)

token_url = (f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php"
             f"?_={int(time.time()*1000)}&csrf_token={xsrf}")
print(f"URL: {token_url[:80]}…")

r_tok = s.get(token_url, headers={
    "Accept": "application/json",
    "Referer": f"{BASE}/dna/matches/{KIT}",
    "X-Requested-With": "XMLHttpRequest",
}, timeout=15)

print(f"Status: {r_tok.status_code}  CT: {r_tok.headers.get('content-type','')}")
print(f"Body:   {r_tok.text[:500]}")

fg_access_token = ""
try:
    tok_data = r_tok.json()
    fg_access_token = (tok_data.get("data") or {}).get("token", "")
    if fg_access_token:
        print(f"\n✅ FamilyGraph-Token erhalten: {fg_access_token[:60]}…")
    else:
        print(f"\n⚠️  Kein token-Feld in Antwort: {list(tok_data.keys())}")
except Exception as e:
    print(f"\n❌ JSON-Parse-Fehler: {e}")
print()

if not fg_access_token:
    print("Ohne FG-Token kann nicht weiter gemacht werden.")
    import sys; sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
# SCHRITT 2: GraphQL-Introspection (welche Felder gibt es?)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("SCHRITT 2 – GraphQL-Introspection")
print("=" * 60)

gql_headers = {
    "Authorization":  f"Bearer {fg_access_token}",
    "Content-Type":   "application/json",
    "Accept":         "application/json",
    "Referer":        f"{BASE}/dna/matches/{KIT}",
    "Origin":         BASE,
}

# Nur den dna_kit Typ introspectieren
intro_q = """
{
  __type(name: "DnaKit") {
    name
    fields { name type { name kind ofType { name kind } } }
  }
}
"""
r_intro = s.post(GQLEP, json={"query": intro_q}, headers=gql_headers, timeout=15)
print(f"Status: {r_intro.status_code}")
try:
    d = r_intro.json()
    if "data" in d and d["data"]:
        fields = (d["data"].get("__type") or {}).get("fields", [])
        print(f"DnaKit-Felder: {[f['name'] for f in fields]}")
    else:
        print(f"Antwort: {json.dumps(d)[:400]}")
except:
    print(f"Body: {r_intro.text[:400]}")
print()

# ══════════════════════════════════════════════════════════════════════════════
# SCHRITT 3: Echte dna_matches Query (erste 5 Matches)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("SCHRITT 3 – dna_matches Query (5 Matches)")
print("=" * 60)

matches_q = f"""
{{
  dna_kit (id: "{KIT}", lang: "EN") {{
    dna_matches (limit: 5, offset: 0) {{
      data {{
        id
        link
        display_name
        first_name
        last_name
        shared_dna
        shared_segments
        relationship
        predicted_relationship
        image_url
        added_date
      }}
      total_count
    }}
  }}
}}
"""
r_matches = s.post(GQLEP, json={"query": matches_q}, headers=gql_headers, timeout=20)
print(f"Status: {r_matches.status_code}  CT: {r_matches.headers.get('content-type','')}")
try:
    d = r_matches.json()
    print(f"Keys: {list(d.keys())}")
    txt = json.dumps(d, indent=2)
    print(txt[:2000])
    if "errors" not in d and "data" in d:
        print("\n🎯 MATCH-DATEN GEFUNDEN!")
    elif "errors" in d:
        print(f"\n⚠️  GraphQL-Fehler: {json.dumps(d['errors'])[:300]}")
except Exception as e:
    print(f"Parse-Fehler: {e}")
    print(r_matches.text[:500])
print()

# ══════════════════════════════════════════════════════════════════════════════
# SCHRITT 4: Alternativ-Query ohne Feldliste (alle Felder)
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("SCHRITT 4 – Alternativ (einfache Felder)")
print("=" * 60)

simple_q = f"""
{{
  dna_kit (id: "{KIT}", lang: "EN") {{
    dna_matches (limit: 3) {{
      total_count
      data {{
        id
        display_name
        shared_dna
        relationship
      }}
    }}
  }}
}}
"""
r2 = s.post(GQLEP, json={"query": simple_q}, headers=gql_headers, timeout=15)
print(f"Status: {r2.status_code}")
try:
    d2 = r2.json()
    print(json.dumps(d2, indent=2)[:1500])
except:
    print(r2.text[:500])
