#!/usr/bin/env python3
import json, sys
from pathlib import Path
import requests

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
if not cookie_file.exists():
    print("FEHLER: Cookie-Datei nicht gefunden:", cookie_file)
    sys.exit(1)

raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)
print(f"Cookies geladen: {len(cookies)} Stück")

s = requests.Session()
s.cookies.update(cookies)
s.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

url = "https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
print(f"Lade: {url}")
r = s.get(url, timeout=20)
print(f"Status: {r.status_code}")
print(f"Final-URL: {r.url}")
print(f"HTML-Länge: {len(r.text)} Zeichen")
print()
print("=== HTML-Anfang (erste 3000 Zeichen) ===")
print(r.text[:3000])
print()
print("=== Script-Tags ===")
import re
for m in re.finditer(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL):
    c = m.group(1).strip()
    if len(c) > 100 and ('{' in c or '[' in c):
        print(f"  [{len(c)} Zeichen] {c[:300]!r}")
        print()
