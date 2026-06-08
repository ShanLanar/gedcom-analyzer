#!/usr/bin/env python3
"""
download_myheritage.py — MyHeritage DNA-Match-Downloader

Lädt Match-Liste, Chromosom-Segment-Daten und Shared Matches (ICW)
herunter und speichert sie in ancestry/data/myheritage_dna.db.

Vorbereitung:
    1. Im Browser bei MyHeritage einloggen
    2. Cookie-Editor Extension → "Export All" → als JSON speichern unter
       ancestry/data/myheritage_cookies.json
    3. Script starten

Aufruf:
    cd ancestry
    python tools/download_myheritage.py
    python tools/download_myheritage.py --no-segments   # nur Match-Liste, schneller
    python tools/download_myheritage.py --only-new      # überspringt bekannte Matches
    python tools/download_myheritage.py --min-cm 15     # andere cM-Untergrenze

Hinweis zu API-Endpunkten:
    Falls der Download nicht startet oder 403/401 liefert:
    → spy_myheritage.js im Browser ausführen (Anleitung darin)
    → mh_spy.json hier herschicken → Endpunkte werden angepasst
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests import Session

# ── Pfade ────────────────────────────────────────────────────────────────────
_HERE    = Path(__file__).resolve().parent
_DATA    = _HERE.parent / "data"
COOKIE_FILE = _DATA / "myheritage_cookies.json"
DB_FILE     = _DATA / "myheritage_dna.db"

# ── Kit-Konfiguration ────────────────────────────────────────────────────────
# Eigene Werte aus der MyHeritage-URL:
#   https://www.myheritage.com/dna/matches/<KIT_GUID>
KIT_GUID   = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
MEMBER_ID  = "OYYV6BZ3NGOPBXRBKXER6SDKTJW2KDI"   # eigene Member-ID
OWN_DNA_ID = "D-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2"  # eigene DNA-ID

# ── API-Endpunkte ────────────────────────────────────────────────────────────
# TODO: nach spy_myheritage.js-Auswertung ggf. anpassen
BASE      = "https://www.myheritage.com"

# Match-Liste (paginiert)
# Mögliche Kandidaten (erster wird probiert, Rest als Fallback):
EP_MATCHES_CANDIDATES = [
    f"{BASE}/dna/api/get-dna-matches",
    f"{BASE}/FP/API/ClanSearch-1.0/dna/matches",
    f"{BASE}/dna/api/matches",
]

# Segment-Daten pro Match (Chromosom-Positionen!)
EP_SEGMENTS_CANDIDATES = [
    f"{BASE}/dna/api/get-dna-segments",
    f"{BASE}/dna/api/segments",
    f"{BASE}/FP/API/ClanSearch-1.0/dna/segments",
]

# ICW / Shared Matches pro Match
EP_ICW_CANDIDATES = [
    f"{BASE}/dna/api/get-shared-matches",
    f"{BASE}/dna/api/shared-matches",
]

# ── Parameter ────────────────────────────────────────────────────────────────
PAGE_SIZE      = 50
MIN_CM_DEFAULT = 8.0
DELAY_LIST     = 0.4   # Sekunden zwischen Match-Listen-Seiten
DELAY_DETAIL   = 0.6   # Sekunden zwischen Segment-Abfragen
DELAY_ICW      = 0.8   # Sekunden zwischen ICW-Abfragen

log = logging.getLogger(__name__)


# ── Datenbank ─────────────────────────────────────────────────────────────────

def init_db(db_file: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS mh_matches (
            kit_guid            TEXT NOT NULL,
            match_id            TEXT NOT NULL,   -- DNA-ID: "D-XXXXXXXX-..."
            member_id           TEXT,
            display_name        TEXT,
            age_range           TEXT,
            country             TEXT,
            shared_pct          REAL,
            shared_cm           REAL,
            shared_segments     INTEGER,
            largest_segment     REAL,
            predicted_rel       TEXT,
            has_tree            INTEGER DEFAULT 0,
            tree_size           INTEGER,
            tree_owner          TEXT,
            has_theory          INTEGER DEFAULT 0,
            theory_rel          TEXT,
            ancestral_surnames  TEXT,   -- JSON-Array
            fetched_at          TEXT,
            raw_json            TEXT,
            segments_fetched    INTEGER DEFAULT 0,
            icw_fetched         INTEGER DEFAULT 0,
            PRIMARY KEY (kit_guid, match_id)
        );

        CREATE TABLE IF NOT EXISTS mh_segments (
            kit_guid    TEXT NOT NULL,
            match_id    TEXT NOT NULL,
            chromosome  INTEGER NOT NULL,
            start_cm    REAL NOT NULL,
            end_cm      REAL,
            length_cm   REAL,
            snps        INTEGER,
            PRIMARY KEY (kit_guid, match_id, chromosome, start_cm)
        );
        CREATE INDEX IF NOT EXISTS idx_seg_chr ON mh_segments(chromosome);

        CREATE TABLE IF NOT EXISTS mh_icw (
            kit_guid        TEXT NOT NULL,
            match_id_a      TEXT NOT NULL,
            match_id_b      TEXT NOT NULL,
            shared_cm_with_kit  REAL,
            shared_cm_ab        REAL,
            predicted_rel_b     TEXT,
            PRIMARY KEY (kit_guid, match_id_a, match_id_b)
        );
    """)
    con.commit()
    return con


def match_exists(con: sqlite3.Connection, match_id: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM mh_matches WHERE kit_guid=? AND match_id=?",
        (KIT_GUID, match_id)
    ).fetchone()
    return row is not None


def upsert_match(con: sqlite3.Connection, m: dict, raw: str):
    con.execute("""
        INSERT INTO mh_matches
            (kit_guid, match_id, member_id, display_name, age_range, country,
             shared_pct, shared_cm, shared_segments, largest_segment,
             predicted_rel, has_tree, tree_size, tree_owner,
             has_theory, theory_rel, ancestral_surnames, fetched_at, raw_json)
        VALUES
            (:kit_guid,:match_id,:member_id,:display_name,:age_range,:country,
             :shared_pct,:shared_cm,:shared_segments,:largest_segment,
             :predicted_rel,:has_tree,:tree_size,:tree_owner,
             :has_theory,:theory_rel,:ancestral_surnames,:fetched_at,:raw_json)
        ON CONFLICT(kit_guid, match_id) DO UPDATE SET
            display_name=excluded.display_name,
            shared_cm=excluded.shared_cm,
            shared_segments=excluded.shared_segments,
            largest_segment=excluded.largest_segment,
            predicted_rel=excluded.predicted_rel,
            has_tree=excluded.has_tree,
            tree_size=excluded.tree_size,
            fetched_at=excluded.fetched_at,
            raw_json=excluded.raw_json
    """, {
        "kit_guid": KIT_GUID,
        "match_id": m.get("match_id", ""),
        "member_id": m.get("member_id", ""),
        "display_name": m.get("display_name", ""),
        "age_range": m.get("age_range", ""),
        "country": m.get("country", ""),
        "shared_pct": m.get("shared_pct"),
        "shared_cm": m.get("shared_cm"),
        "shared_segments": m.get("shared_segments"),
        "largest_segment": m.get("largest_segment"),
        "predicted_rel": m.get("predicted_rel", ""),
        "has_tree": int(bool(m.get("has_tree"))),
        "tree_size": m.get("tree_size"),
        "tree_owner": m.get("tree_owner", ""),
        "has_theory": int(bool(m.get("has_theory"))),
        "theory_rel": m.get("theory_rel", ""),
        "ancestral_surnames": json.dumps(m.get("ancestral_surnames", []),
                                          ensure_ascii=False),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "raw_json": raw,
    })
    con.commit()


def save_segments(con: sqlite3.Connection, match_id: str, segments: list[dict]):
    con.execute("DELETE FROM mh_segments WHERE kit_guid=? AND match_id=?",
                (KIT_GUID, match_id))
    for s in segments:
        con.execute("""
            INSERT OR REPLACE INTO mh_segments
                (kit_guid, match_id, chromosome, start_cm, end_cm, length_cm, snps)
            VALUES (?,?,?,?,?,?,?)
        """, (KIT_GUID, match_id,
              s.get("chromosome"), s.get("start_cm"), s.get("end_cm"),
              s.get("length_cm"), s.get("snps")))
    con.execute(
        "UPDATE mh_matches SET segments_fetched=1 WHERE kit_guid=? AND match_id=?",
        (KIT_GUID, match_id))
    con.commit()


def save_icw(con: sqlite3.Connection, match_id_a: str, icw: list[dict]):
    for b in icw:
        con.execute("""
            INSERT OR REPLACE INTO mh_icw
                (kit_guid, match_id_a, match_id_b,
                 shared_cm_with_kit, shared_cm_ab, predicted_rel_b)
            VALUES (?,?,?,?,?,?)
        """, (KIT_GUID, match_id_a,
              b.get("match_id"),
              b.get("shared_cm_with_kit"),
              b.get("shared_cm_ab"),
              b.get("predicted_rel", "")))
    con.execute(
        "UPDATE mh_matches SET icw_fetched=1 WHERE kit_guid=? AND match_id=?",
        (KIT_GUID, match_id_a))
    con.commit()


# ── Session / Cookies ────────────────────────────────────────────────────────

def build_session(cookie_file: Path) -> Session:
    if not cookie_file.exists():
        print(f"❌  Cookie-Datei nicht gefunden: {cookie_file}")
        print("    → Im Browser bei MyHeritage einloggen")
        print("    → Cookie-Editor Extension → Export All → JSON")
        print(f"    → Speichern als: {cookie_file}")
        sys.exit(1)

    raw = json.loads(cookie_file.read_text(encoding="utf-8"))

    # Cookie-Editor exportiert entweder eine Liste von Dicts oder ein Dict
    if isinstance(raw, dict):
        cookies = raw
    else:
        cookies = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}

    if not cookies:
        print("❌  Cookie-Datei ist leer oder hat unbekanntes Format.")
        sys.exit(1)

    sess = Session()
    sess.cookies.update(cookies)
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Origin": "https://www.myheritage.com",
        "Referer": f"https://www.myheritage.com/dna/matches/{KIT_GUID}",
        "X-Requested-With": "XMLHttpRequest",
    })
    return sess


# ── API-Endpunkt-Erkennung ───────────────────────────────────────────────────

def probe_endpoint(sess: Session, candidates: list[str],
                   params: dict) -> tuple[str | None, dict | None]:
    """Probiert Kandidaten-URLs durch, gibt (url, json_response) zurück."""
    for url in candidates:
        try:
            r = sess.get(url, params=params, timeout=15)
            if r.status_code == 200:
                try:
                    data = r.json()
                    log.debug("Endpunkt gefunden: %s", url)
                    return url, data
                except Exception:
                    pass
            elif r.status_code in (401, 403):
                log.warning("%s → %d (Auth-Problem)", url, r.status_code)
            else:
                log.debug("%s → %d", url, r.status_code)
        except Exception as e:
            log.debug("%s → Fehler: %s", url, e)
    return None, None


# ── Match-Liste parsen ───────────────────────────────────────────────────────
# TODO: nach spy_myheritage.js-Auswertung anpassen

def parse_match_list(data: dict) -> list[dict]:
    """
    Extrahiert Matches aus der API-Antwort.
    Typische Strukturen von MyHeritage:
      { "matches": [...] }
      { "data": { "matches": [...] } }
      { "result": [...] }
    → TODO: an tatsächliche Antwort anpassen
    """
    if isinstance(data, list):
        items = data
    elif "matches" in data:
        items = data["matches"]
    elif "data" in data and "matches" in data["data"]:
        items = data["data"]["matches"]
    elif "result" in data:
        items = data["result"]
    else:
        # Alle Listen-Werte als Kandidaten probieren
        for v in data.values():
            if isinstance(v, list) and v:
                items = v
                break
        else:
            log.warning("Unbekannte Antwort-Struktur: %s", list(data.keys()))
            return []

    out = []
    for item in items:
        # TODO: Feldnamen nach spy-Auswertung anpassen
        # Typische MyHeritage-Feldnamen (aus Community-Analyse):
        match_id = (
            item.get("dnaMatchId") or
            item.get("matchId") or
            item.get("id") or
            item.get("dna_id") or
            item.get("matchGuid") or
            ""
        )
        member_id = (
            item.get("memberId") or
            item.get("memberGuid") or
            item.get("person", {}).get("memberId") or
            ""
        )
        name = (
            item.get("displayName") or
            item.get("name") or
            item.get("fullName") or
            item.get("person", {}).get("name") or
            ""
        )
        shared_cm = (
            item.get("sharedDnaLength") or
            item.get("sharedDna") or
            item.get("totalSharedSegmentsLengthInCm") or
            item.get("sharedCm") or
            0.0
        )
        segments = (
            item.get("sharedSegments") or
            item.get("numSharedSegments") or
            item.get("sharedSegmentsCount") or
            0
        )
        largest = (
            item.get("largestSegment") or
            item.get("maxSegmentLengthInCm") or
            item.get("longestSegment") or
            0.0
        )
        rel = (
            item.get("estimatedRelationship") or
            item.get("relationship") or
            item.get("predictedRelationship") or
            ""
        )
        has_tree = bool(
            item.get("hasTree") or
            item.get("familyTreeId") or
            item.get("treeId")
        )
        tree_size = (
            item.get("treeSize") or
            item.get("familyTreeSize") or
            item.get("numTreePersons")
        )
        out.append({
            "match_id": match_id,
            "member_id": member_id,
            "display_name": name,
            "age_range": item.get("ageRange") or item.get("age") or "",
            "country": (item.get("country") or
                        item.get("location", {}).get("country") or ""),
            "shared_pct": item.get("sharedDnaPercentage") or item.get("sharedPct"),
            "shared_cm": float(shared_cm) if shared_cm else None,
            "shared_segments": int(segments) if segments else None,
            "largest_segment": float(largest) if largest else None,
            "predicted_rel": str(rel),
            "has_tree": has_tree,
            "tree_size": int(tree_size) if tree_size else None,
            "tree_owner": (item.get("treeOwner") or
                           item.get("familyTreeOwner") or ""),
            "has_theory": bool(item.get("hasFamilyTheory") or
                               item.get("theoryOfFamilyRelativity")),
            "theory_rel": (item.get("theoryRelationship") or
                           item.get("confirmedRelationship") or ""),
            "ancestral_surnames": (item.get("ancestralSurnames") or
                                   item.get("commonSurnames") or []),
            "_raw": item,
        })
    return out


def get_total_count(data: dict) -> int:
    for k in ("totalMatches", "total", "count", "totalCount", "numMatches"):
        if k in data:
            try:
                return int(data[k])
            except (TypeError, ValueError):
                pass
    if "data" in data and isinstance(data["data"], dict):
        return get_total_count(data["data"])
    return 0


# ── Segment-Daten parsen ─────────────────────────────────────────────────────

def parse_segments(data: dict | list) -> list[dict]:
    """
    TODO: an tatsächliche Antwort anpassen.
    Erwartet: Liste von Segmenten mit Chromosom, Start, Ende, Länge.
    """
    if isinstance(data, list):
        items = data
    elif "segments" in data:
        items = data["segments"]
    elif "data" in data:
        inner = data["data"]
        items = inner if isinstance(inner, list) else inner.get("segments", [])
    else:
        items = []

    out = []
    for s in items:
        chromosome = (
            s.get("chromosome") or
            s.get("chromosomeNumber") or
            s.get("chr")
        )
        start = (
            s.get("startPoint") or s.get("start") or
            s.get("startCm") or s.get("startPosition")
        )
        end = (
            s.get("endPoint") or s.get("end") or
            s.get("endCm") or s.get("endPosition")
        )
        length = (
            s.get("segmentLength") or s.get("length") or
            s.get("lengthCm") or s.get("cm")
        )
        if chromosome is None:
            continue
        out.append({
            "chromosome": int(chromosome),
            "start_cm": float(start) if start is not None else None,
            "end_cm": float(end) if end is not None else None,
            "length_cm": float(length) if length is not None else None,
            "snps": s.get("snpCount") or s.get("snps") or s.get("numSnps"),
        })
    return out


# ── ICW parsen ───────────────────────────────────────────────────────────────

def parse_icw(data: dict | list) -> list[dict]:
    """TODO: an tatsächliche Antwort anpassen."""
    if isinstance(data, list):
        items = data
    elif "sharedMatches" in data:
        items = data["sharedMatches"]
    elif "matches" in data:
        items = data["matches"]
    elif "data" in data:
        inner = data["data"]
        items = inner if isinstance(inner, list) else inner.get("matches", [])
    else:
        items = []

    out = []
    for item in items:
        match_id = (item.get("dnaMatchId") or item.get("matchId") or
                    item.get("id") or "")
        out.append({
            "match_id": match_id,
            "shared_cm_with_kit": (
                item.get("sharedDnaLength") or item.get("sharedCm")
            ),
            "shared_cm_ab": (
                item.get("sharedDnaLengthWithPrimary") or
                item.get("sharedCmWithPrimary") or
                item.get("sharedCmAb")
            ),
            "predicted_rel": (
                item.get("estimatedRelationship") or
                item.get("relationship") or ""
            ),
        })
    return out


# ── Hauptlogik ───────────────────────────────────────────────────────────────

def download(
    sess: Session,
    con: sqlite3.Connection,
    only_new: bool,
    fetch_segments: bool,
    fetch_icw: bool,
    min_cm: float,
):
    # ── Endpunkt für Match-Liste finden ──────────────────────────────────────
    probe_params = {
        "kitGuid": KIT_GUID,
        "memberId": MEMBER_ID,
        "page": 1,
        "pageSize": PAGE_SIZE,
        "sortBy": "total_shared_segments_length_in_cm",
        "lang": "EN",
    }
    print("🔍  Suche Match-Listen-Endpunkt …", flush=True)
    ep_matches, first_page = probe_endpoint(
        sess, EP_MATCHES_CANDIDATES, probe_params)

    if not ep_matches:
        print()
        print("❌  Kein API-Endpunkt gefunden. Mögliche Ursachen:")
        print("    1. Cookies abgelaufen → neu exportieren")
        print("    2. Endpunkte haben sich geändert → spy_myheritage.js ausführen")
        print()
        print("    Spy-Anleitung:")
        print("    1. Browser öffnen → MyHeritage Match-Liste")
        print("    2. F12 → Console → spy_myheritage.js einfügen → Enter")
        print("    3. Seite neu laden, einen Match anklicken")
        print("    4. mh_spy.json hier herschicken")
        sys.exit(1)

    print(f"✅  Endpunkt: {ep_matches}")

    total = get_total_count(first_page)
    print(f"📊  Gesamt-Matches laut API: {total}")

    # ── Endpunkt für Segmente testen ─────────────────────────────────────────
    ep_segments = None
    if fetch_segments:
        print("🔍  Suche Segment-Endpunkt …", flush=True)
        ep_segments, _ = probe_endpoint(
            sess, EP_SEGMENTS_CANDIDATES,
            {"kitGuid": KIT_GUID, "matchId": "test"})
        if ep_segments:
            print(f"✅  Segment-Endpunkt: {ep_segments}")
        else:
            print("⚠️  Segment-Endpunkt nicht gefunden — Segmente werden übersprungen")
            fetch_segments = False

    # ── Match-Liste laden ─────────────────────────────────────────────────────
    page = 1
    fetched = 0
    skipped = 0
    new_count = 0
    start_ts = time.time()
    done = False

    while not done:
        if page == 1:
            data = first_page
        else:
            probe_params["page"] = page
            r = sess.get(ep_matches, params=probe_params, timeout=20)
            if r.status_code != 200:
                print(f"\n⚠️  Seite {page}: HTTP {r.status_code} — abgebrochen")
                break
            try:
                data = r.json()
            except Exception:
                print(f"\n⚠️  Seite {page}: Kein JSON in Antwort — abgebrochen")
                break

        matches = parse_match_list(data)
        if not matches:
            break

        for m in matches:
            fetched += 1
            cm = m.get("shared_cm") or 0.0
            if cm < min_cm:
                done = True
                break

            mid = m["match_id"]
            if not mid:
                continue

            is_new = not match_exists(con, mid)
            if only_new and not is_new:
                skipped += 1
                continue

            new_count += 1
            upsert_match(con, m, json.dumps(m["_raw"], ensure_ascii=False))

            elapsed = time.time() - start_ts
            remaining = max(0, (total - fetched)) * (elapsed / max(fetched, 1))
            print(
                f"\r  Seite {page:3d} | {fetched:5d}/{total or '?':5} Matches"
                f" | {cm:.0f} cM"
                f" | +{new_count} neu | {elapsed:.0f}s/{elapsed+remaining:.0f}s est.",
                end="", flush=True,
            )

            # ── Segment-Daten ─────────────────────────────────────────────
            if fetch_segments and ep_segments and mid and (is_new or not only_new):
                time.sleep(DELAY_DETAIL)
                try:
                    r = sess.get(ep_segments,
                                 params={"kitGuid": KIT_GUID, "matchId": mid,
                                         "memberId": MEMBER_ID},
                                 timeout=15)
                    if r.status_code == 200:
                        segs = parse_segments(r.json())
                        if segs:
                            save_segments(con, mid, segs)
                except Exception as e:
                    log.debug("Segmente für %s: %s", mid, e)

            # ── ICW ───────────────────────────────────────────────────────
            if fetch_icw and is_new and cm >= 30:
                ep_icw, icw_data = probe_endpoint(
                    sess, EP_ICW_CANDIDATES,
                    {"kitGuid": KIT_GUID, "matchId": mid,
                     "memberId": MEMBER_ID, "page": 1, "pageSize": 50})
                if ep_icw and icw_data:
                    icw = parse_icw(icw_data)
                    if icw:
                        save_icw(con, mid, icw)

        page += 1
        if not done:
            time.sleep(DELAY_LIST)

    print()
    return fetched, new_count, skipped


# ── Statistik nach Download ───────────────────────────────────────────────────

def print_stats(con: sqlite3.Connection):
    row = con.execute("""
        SELECT COUNT(*), AVG(shared_cm), MAX(shared_cm),
               SUM(segments_fetched), SUM(icw_fetched)
        FROM mh_matches WHERE kit_guid=?
    """, (KIT_GUID,)).fetchone()
    seg_total = con.execute(
        "SELECT COUNT(*) FROM mh_segments WHERE kit_guid=?", (KIT_GUID,)
    ).fetchone()[0]

    print()
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Matches gesamt:     {row[0]:>6}")
    print(f"  Ø gemeinsame cM:    {(row[1] or 0):>6.1f}")
    print(f"  Max. cM:            {(row[2] or 0):>6.1f}")
    print(f"  Matches mit Segm.:  {row[3] or 0:>6}")
    print(f"  Matches mit ICW:    {row[4] or 0:>6}")
    print(f"  Segment-Einträge:   {seg_total:>6}  ← Chromosom-Browser möglich!")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="MyHeritage DNA-Match-Downloader")
    ap.add_argument("--cookies",     default=str(COOKIE_FILE),
                    help="Pfad zur Cookie-JSON-Datei")
    ap.add_argument("--db",          default=str(DB_FILE),
                    help="Pfad zur SQLite-Datenbank")
    ap.add_argument("--only-new",    action="store_true",
                    help="Bereits bekannte Matches überspringen")
    ap.add_argument("--no-segments", action="store_true",
                    help="Segment-Daten nicht herunterladen (schneller)")
    ap.add_argument("--no-icw",      action="store_true",
                    help="Shared Matches (ICW) nicht herunterladen")
    ap.add_argument("--min-cm",      type=float, default=MIN_CM_DEFAULT,
                    help=f"Untergrenze für cM (Standard: {MIN_CM_DEFAULT})")
    ap.add_argument("--debug",       action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    print(f"📂  Datenbank:  {args.db}")
    print(f"🍪  Cookies:    {args.cookies}")
    print(f"🧬  Kit-GUID:   {KIT_GUID}")
    print(f"📏  Min. cM:    {args.min_cm}")
    print()

    _DATA.mkdir(parents=True, exist_ok=True)
    sess = build_session(Path(args.cookies))
    con  = init_db(Path(args.db))

    fetched, new_count, skipped = download(
        sess, con,
        only_new=args.only_new,
        fetch_segments=not args.no_segments,
        fetch_icw=not args.no_icw,
        min_cm=args.min_cm,
    )

    print(f"✅  Download abgeschlossen: {fetched} verarbeitet, "
          f"{new_count} neu/aktualisiert, {skipped} übersprungen")
    print_stats(con)
    con.close()


if __name__ == "__main__":
    main()
