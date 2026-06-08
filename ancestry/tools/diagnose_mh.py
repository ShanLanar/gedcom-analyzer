#!/usr/bin/env python3
"""
Diagnose-Script Phase 8: curl_cffi (Chrome-TLS-Impersonation) gegen GraphQL.
Benötigt: pip install curl_cffi
"""
import json, re, time, sys
from pathlib import Path

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)

KIT   = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
BASE  = "https://www.myheritage.com"
GQLEP = "https://familygraphql.myheritage.com"
UA    = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# ── curl_cffi importieren ─────────────────────────────────────────────────────
try:
    from curl_cffi import requests as cfreq
    print("✅ curl_cffi gefunden")
except ImportError:
    print("❌ curl_cffi nicht installiert.")
    print("   Bitte ausführen:  pip install curl_cffi")
    sys.exit(1)

# ── Session mit Chrome-Impersonation ─────────────────────────────────────────
s = cfreq.Session(impersonate="chrome120")
s.cookies.update(cookies)
s.headers["User-Agent"] = UA

print("Lade Hauptseite …")
r0 = s.get(f"{BASE}/dna/matches/{KIT}", timeout=20)
html = r0.text
m = re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', html)
xsrf = m.group(1) if m else ""
print(f"xsrf: {xsrf[:40] if xsrf else '❌'}")

print("Hole FamilyGraph-Token …")
tok_url = f"{BASE}/FP/API/FamilyGraph/get-familygraph-token.php?_={int(time.time()*1000)}&csrf_token={xsrf}"
r_tok = s.get(tok_url, headers={"Accept": "application/json",
                                  "Referer": f"{BASE}/dna/matches/{KIT}"}, timeout=15)
tok_json = r_tok.json()
fg_tok = (tok_json.get("data") or {}).get("token", "")
print(f"Token: {fg_tok[:60] if fg_tok else '❌'}…\n")
if not fg_tok:
    print("Kein Token → Abbruch"); sys.exit(1)

QUERY = f'{{ dna_kit (id: "{KIT}", lang: "EN") {{ dna_matches (limit: 5) {{ total_count data {{ id display_name shared_dna relationship }} }} }} }}'

gql_headers = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "Referer":      f"{BASE}/dna/matches/{KIT}",
    "Origin":       BASE,
}

def try_gql(label, url, **kw):
    try:
        resp = s.post(url, headers=gql_headers, **kw)
        ct   = resp.headers.get("content-type","")
        tag  = "✅" if resp.status_code == 200 else "⚠️"
        print(f"{tag} [{resp.status_code}] {label}")
        body = resp.text
        if body.strip():
            try:
                d = resp.json()
                if "data" in d and d["data"]:
                    print(f"   🎯 DATEN! {json.dumps(d)[:600]}")
                elif "errors" in d:
                    print(f"   Fehler: {json.dumps(d['errors'])[:200]}")
                else:
                    print(f"   {json.dumps(d)[:300]}")
            except:
                print(f"   {body[:300]!r}")
        else:
            print(f"   (leerer Body)")
    except Exception as e:
        print(f"❌ {label}: {e}")
    print()

print("=" * 60)
print("A) access_token als Query-Param")
print("=" * 60)
try_gql("POST GQLEP?access_token=…",
        f"{GQLEP}?access_token={fg_tok}",
        json={"query": QUERY})

print("=" * 60)
print("B) form-encoded")
print("=" * 60)
try_gql("POST GQLEP form",
        GQLEP,
        data={"access_token": fg_tok, "query": QUERY})

print("=" * 60)
print("C) /graphql Pfad")
print("=" * 60)
try_gql("POST GQLEP/graphql?access_token=…",
        f"{GQLEP}/graphql?access_token={fg_tok}",
        json={"query": QUERY})

print("=" * 60)
print("D) Introspection – welche Typen gibt es?")
print("=" * 60)
intro = "{ __schema { queryType { name } types { name } } }"
try_gql("Introspection GQLEP?access_token=…",
        f"{GQLEP}?access_token={fg_tok}",
        json={"query": intro})
