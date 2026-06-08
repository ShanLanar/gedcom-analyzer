#!/usr/bin/env python3
import json, sys, re
from pathlib import Path
import requests

cookie_file = Path(__file__).parent.parent / "data" / "myheritage_cookies.json"
if not cookie_file.exists():
    print("FEHLER: Cookie-Datei nicht gefunden:", cookie_file)
    sys.exit(1)

raw = json.loads(cookie_file.read_text(encoding="utf-8"))
cookies = ({x["name"]: x["value"] for x in raw if "name" in x}
           if isinstance(raw, list) else raw)

s = requests.Session()
s.cookies.update(cookies)
s.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

KIT = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"


def extract_js_var(html, varname):
    """Extrahiert window.VARNAME = {...} via Klammer-Zählung."""
    marker = f"{varname} = "
    idx = html.find(marker)
    if idx == -1:
        return None
    try:
        start = html.index("{", idx + len(marker))
    except ValueError:
        return None
    depth = 0
    in_str = escape = False
    for i in range(start, len(html)):
        c = html[i]
        if escape:       escape = False; continue
        if c == "\\" and in_str: escape = True; continue
        if c == '"':     in_str = not in_str; continue
        if in_str:       continue
        if c == "{":     depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:    return json.loads(html[start:i+1])
                except: return None
    return None


def show_structure(obj, prefix="", max_depth=3, depth=0):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:30]:
            if isinstance(v, dict):
                print(f"{prefix}{k}: {{...}} ({len(v)} Schlüssel)")
                show_structure(v, prefix + "  ", max_depth, depth + 1)
            elif isinstance(v, list):
                print(f"{prefix}{k}: [...] ({len(v)} Einträge)")
                if v and isinstance(v[0], dict):
                    show_structure(v[0], prefix + "  [0] ", max_depth, depth + 1)
            else:
                val = str(v)[:80]
                print(f"{prefix}{k}: {val!r}")
    elif isinstance(obj, list):
        print(f"{prefix}Liste mit {len(obj)} Einträgen")
        if obj and isinstance(obj[0], dict):
            show_structure(obj[0], prefix + "[0] ", max_depth, depth + 1)


# ── Seite 1 laden ─────────────────────────────────────────────────────────────
for page in [1, 2]:
    url = f"https://www.myheritage.com/dna/matches/{KIT}?p={page}"
    print(f"\n{'='*60}")
    print(f"Seite {page}: {url}")
    r = s.get(url, timeout=20)
    print(f"Status: {r.status_code}, {len(r.text)} Zeichen")

    cd = extract_js_var(r.text, "window.clientData")
    if cd:
        print(f"\n✅ window.clientData gefunden ({len(str(cd))} Zeichen)")
        print("Struktur:")
        show_structure(cd, "  ", max_depth=2)
    else:
        print("❌ window.clientData nicht gefunden")

    # XSRF-Token extrahieren
    m = re.search(r'mhXsrfToken\s*=\s*["\']([^"\']+)["\']', r.text)
    if m:
        print(f"\nmhXsrfToken: {m.group(1)[:40]}...")
