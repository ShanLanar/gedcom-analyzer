#!/usr/bin/env python3
"""
Verarbeitet die mh_indexeddb_dna.json (aus read_indexeddb.js) und importiert
die gecachten Matches in die Datenbank – als Überbrückung bis mh_all_matches.json
via download_all_matches.js verfügbar ist.

Aufruf:
  python process_indexeddb_cache.py [pfad/zu/mh_indexeddb_dna.json]
"""
import json, sys
from pathlib import Path

SCRIPT_DIR  = Path(__file__).resolve().parent
JSON_FILE   = SCRIPT_DIR / "mh_indexeddb_dna.json"
if len(sys.argv) > 1:
    JSON_FILE = Path(sys.argv[1])

# ── IndexedDB-Rohdaten in flache Match-Liste umwandeln ───────────────────────
raw   = json.loads(JSON_FILE.read_text(encoding="utf-8"))
store = raw.get("MyHeritage.dna", [])

all_matches: dict = {}  # id → match-dict (dedupliziert)

for entry in store:
    cached = entry.get("cached", {})
    data_str = cached.get("data", "{}")
    try:
        data = json.loads(data_str) if isinstance(data_str, str) else data_str
    except Exception:
        continue

    # FETCH_DNA_MATCHES_FOR_KIT Einträge
    kit_data = data.get("dna_kit", {})
    matches  = (kit_data.get("dna_matches") or {}).get("data") or []
    for m in matches:
        if m and m.get("id"):
            existing = all_matches.get(m["id"])
            # Neueren / vollständigeren Eintrag bevorzugen
            if not existing or len(json.dumps(m)) > len(json.dumps(existing)):
                all_matches[m["id"]] = m

match_list = list(all_matches.values())
print(f"IndexedDB-Cache: {len(store)} Einträge, {len(match_list)} einzigartige Matches")

# ── Als mh_all_matches.json-Format exportieren ───────────────────────────────
meta  = {"kit_id": "dnakit-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2",
         "site_id": "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ",
         "total_count": 11145,
         "downloaded_count": len(match_list),
         "downloaded_at": None,
         "sort": "indexeddb_cache",
         "source": "indexeddb"}

out_file = SCRIPT_DIR / "mh_indexeddb_matches.json"
out_file.write_text(json.dumps({"meta": meta, "matches": match_list}, indent=2),
                    encoding="utf-8")
print(f"Exportiert nach: {out_file}")

# ── Direkt in die DB importieren ─────────────────────────────────────────────
sys.path.insert(0, str(SCRIPT_DIR))
try:
    import import_mh_matches as imp
    imp.JSON_FILE = out_file
    imp.run()
except Exception as e:
    print(f"Import-Fehler: {e}")
    print(f"Manuell ausführen: python import_mh_matches.py {out_file}")
