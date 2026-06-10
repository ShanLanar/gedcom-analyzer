"""
Sucht automatisch den API-Endpoint der den Match-Namen liefert.

Verwendung (aus dem ancestry/-Ordner):
    python tools/discover_endpoint.py

Liest die Cookie-Datei aus config.py (cfg.COOKIE_FILE falls gesetzt,
sonst ancestry.json neben diesem Skript) und probiert alle bekannten
Endpoint-Muster durch. Gibt aus welcher einen Namen liefert.
"""

import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # TODO(M2): entfällt mit ancestry/config.py-Umbenennung

import config as cfg
from core.auth import AncestryAuth

# ── Konfiguration ──────────────────────────────────────────────────────────────
# Wird aus erstem gespeicherten Match genommen – passe ggf. an
TEST_GUID   = None   # wird aus DB gelesen
SAMPLE_ID   = None   # wird aus DB gelesen
COOKIE_FILE = getattr(cfg, "COOKIE_FILE",
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "ancestry.json"))

CANDIDATES = [
    # discoveryui-matches – gleiche Domain, kein Akamai
    "{base}/discoveryui-matches/parents/list/api/matchProfile/{test}/{sample}",
    "{base}/discoveryui-matches/parents/list/api/match/{test}/{sample}",
    "{base}/discoveryui-matches/parents/list/api/matchDetails/{test}/{sample}",
    "{base}/discoveryui-matches/compare/api/{test}/{sample}",
    "{base}/discoveryui-matches/compare/api/profile/{test}/{sample}",
    "{base}/discoveryui-matches/parents/api/match/{test}/{sample}",
    "{base}/discoveryui-matches/parents/api/v2/match/{test}/{sample}",
    "{base}/discoveryui-matches/parents/api/matchProfile/{test}/{sample}",
    # dna-Pfad
    "{base}/dna/matches/{test}/compare/{sample}/api",
    "{base}/dna/api/matches/{test}/{sample}",
    "{base}/dna/api/v2/matches/{test}/{sample}",
    # uhura
    "{base}/api/uhura/v2/tests/{test}/matches/{sample}",
    "{base}/dna/api/uhura/v2/tests/{test}/matches/{sample}",
    # profile
    "{base}/profile/{sample}",
    "{base}/api/v2/member/{sample}",
]

def find_name(data) -> str:
    """Sucht rekursiv nach Namensfeldern in einem JSON-Objekt."""
    if isinstance(data, dict):
        for k in ("displayName","matchTestDisplayName","adminDisplayName",
                  "name","fullName","userName"):
            v = data.get(k)
            if isinstance(v, str) and 3 < len(v) < 80:
                # Systemwerte ausschließen
                if not any(x in v.lower() for x in
                           ("ancestry","loading","private","unknown","anonym")):
                    return v
        for v in data.values():
            r = find_name(v)
            if r:
                return r
    elif isinstance(data, list):
        for item in data[:5]:
            r = find_name(item)
            if r:
                return r
    return ""


def main():
    # ── Session aufbauen ──────────────────────────────────────────────────────
    auth = AncestryAuth()
    if not os.path.exists(COOKIE_FILE):
        print(f"[FEHLER] Cookie-Datei nicht gefunden: {COOKIE_FILE}")
        sys.exit(1)
    print(f"Lade Cookies aus {COOKIE_FILE} ...")
    if not auth.login_cookies(COOKIE_FILE):
        print("[FEHLER] Login fehlgeschlagen.")
        sys.exit(1)
    session = auth.get_session()
    print(f"Session OK. UID={auth.uid}\n")

    # ── Test-GUID + Sample-ID aus DB lesen ────────────────────────────────────
    test_guid   = TEST_GUID
    sample_id   = SAMPLE_ID
    if not test_guid or not sample_id:
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", cfg.DB_FILE)
            con = sqlite3.connect(db_path)
            row = con.execute(
                "SELECT test_guid, match_guid FROM matches "
                "ORDER BY shared_cm DESC LIMIT 1"
            ).fetchone()
            con.close()
            if row:
                test_guid, sample_id = row
                print(f"Aus DB: test_guid={test_guid[:8]}… "
                      f"sample_id={sample_id[:8]}…\n")
        except Exception as e:
            print(f"[FEHLER] DB nicht lesbar: {e}")
            sys.exit(1)

    if not test_guid or not sample_id:
        print("[FEHLER] Keine GUIDs gefunden – bitte TEST_GUID und SAMPLE_ID "
              "oben im Skript eintragen.")
        sys.exit(1)

    base = cfg.BASE_URL
    headers = {
        "Accept"         : "application/json, text/html, */*",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8",
        "Referer"        : f"{base}/dna/matches/{test_guid}/list",
        "Sec-Fetch-Site" : "same-origin",
        "Sec-Fetch-Mode" : "cors",
        "Sec-Fetch-Dest" : "empty",
    }
    csrf = (session.cookies.get("_dnamatches-matchlistui-x-csrf-token")
            or session.cookies.get("_csrf", ""))
    if csrf:
        headers["X-CSRF-Token"] = csrf

    print(f"Probiere {len(CANDIDATES)} Endpoints ...\n")

    for tmpl in CANDIDATES:
        url = tmpl.format(base=base, test=test_guid, sample=sample_id)
        try:
            r = session.get(url, headers=headers, timeout=15)
        except Exception as e:
            print(f"  FEHLER  {url}\n          {e}\n")
            continue

        if r.status_code == 404:
            print(f"  404     {url}")
            continue
        if r.status_code != 200:
            print(f"  {r.status_code}     {url}")
            continue

        # JSON versuchen
        try:
            data = r.json()
            name = find_name(data)
            if name:
                print(f"\n  *** TREFFER *** {url}")
                print(f"      Name: {name}")
                print(f"      Felder: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
            else:
                keys = list(data.keys())[:8] if isinstance(data, dict) else type(data).__name__
                print(f"  200/JSON kein Name  {url}  felder={keys}")
        except Exception:
            # HTML: nach "You and NAME" suchen
            html = r.text
            m = re.search(r'[Yy]ou and ([A-ZÄÖÜ][^\n"<]{2,60}?)(?:"|\s*<|\|)', html)
            if m:
                print(f"\n  *** TREFFER (HTML) *** {url}")
                print(f"      Name: {m.group(1).strip()}")
            else:
                snippet = html[:120].replace("\n", " ")
                print(f"  200/HTML kein Name  {url}  [{snippet[:80]}]")

    print("\nFertig.")


if __name__ == "__main__":
    main()
