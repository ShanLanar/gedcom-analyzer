#!/usr/bin/env python3
"""
download_myheritage.py — MyHeritage DNA-Match-Downloader

Strategie: MyHeritage nutzt Server-Side Rendering (React SSR).
Die Match-Daten stecken direkt im HTML der Seite als eingebettetes JSON.
Das Script parst die HTML-Seiten ohne separate API-Calls.

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
    python tools/download_myheritage.py --probe         # zeigt eingebettetes JSON (Diagnose)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests import Session

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ── Pfade ─────────────────────────────────────────────────────────────────────
_HERE       = Path(__file__).resolve().parent
_DATA       = _HERE.parent / "data"
COOKIE_FILE = _DATA / "myheritage_cookies.json"
DB_FILE     = _DATA / "myheritage_dna.db"

# ── Kit-Konfiguration ─────────────────────────────────────────────────────────
KIT_GUID   = "OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ"
MEMBER_ID  = "OYYV6BZ3NGOPBXRBKXER6SDKTJW2KDI"
OWN_DNA_ID = "D-9F9E6C0C-5EF0-4A73-9F85-1F1C8219B3A2"

BASE      = "https://www.myheritage.com"
PAGE_SIZE = 10   # MyHeritage zeigt 10 Matches pro Seite

MIN_CM_DEFAULT = 8.0
DELAY_PAGE     = 0.6
DELAY_DETAIL   = 0.8

log = logging.getLogger(__name__)


# ── Datenbank ─────────────────────────────────────────────────────────────────

def init_db(db_file: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS mh_matches (
            kit_guid            TEXT NOT NULL,
            match_id            TEXT NOT NULL,
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
            ancestral_surnames  TEXT,
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
            kit_guid            TEXT NOT NULL,
            match_id_a          TEXT NOT NULL,
            match_id_b          TEXT NOT NULL,
            shared_cm_with_kit  REAL,
            shared_cm_ab        REAL,
            predicted_rel_b     TEXT,
            PRIMARY KEY (kit_guid, match_id_a, match_id_b)
        );
    """)
    con.commit()
    return con


def match_exists(con: sqlite3.Connection, match_id: str) -> bool:
    return con.execute(
        "SELECT 1 FROM mh_matches WHERE kit_guid=? AND match_id=?",
        (KIT_GUID, match_id)
    ).fetchone() is not None


def upsert_match(con: sqlite3.Connection, m: dict):
    con.execute("""
        INSERT INTO mh_matches
            (kit_guid, match_id, member_id, display_name, age_range, country,
             shared_pct, shared_cm, shared_segments, largest_segment,
             predicted_rel, has_tree, tree_size, tree_owner,
             has_theory, theory_rel, ancestral_surnames, fetched_at, raw_json)
        VALUES
            (:kit,:mid,:member,:name,:age,:country,
             :pct,:cm,:segs,:largest,
             :rel,:htree,:tsize,:towner,
             :htheory,:trel,:surnames,:ts,:raw)
        ON CONFLICT(kit_guid, match_id) DO UPDATE SET
            display_name=excluded.display_name, shared_cm=excluded.shared_cm,
            shared_segments=excluded.shared_segments, predicted_rel=excluded.predicted_rel,
            has_tree=excluded.has_tree, tree_size=excluded.tree_size,
            fetched_at=excluded.fetched_at, raw_json=excluded.raw_json
    """, {
        "kit": KIT_GUID, "mid": m["match_id"], "member": m.get("member_id",""),
        "name": m.get("display_name",""), "age": m.get("age_range",""),
        "country": m.get("country",""),
        "pct": m.get("shared_pct"), "cm": m.get("shared_cm"),
        "segs": m.get("shared_segments"), "largest": m.get("largest_segment"),
        "rel": m.get("predicted_rel",""),
        "htree": int(bool(m.get("has_tree"))), "tsize": m.get("tree_size"),
        "towner": m.get("tree_owner",""),
        "htheory": int(bool(m.get("has_theory"))), "trel": m.get("theory_rel",""),
        "surnames": json.dumps(m.get("ancestral_surnames",[]), ensure_ascii=False),
        "ts": datetime.now(timezone.utc).isoformat(),
        "raw": json.dumps(m.get("_raw",{}), ensure_ascii=False),
    })
    con.commit()


def save_segments(con: sqlite3.Connection, match_id: str, segs: list[dict]):
    con.execute("DELETE FROM mh_segments WHERE kit_guid=? AND match_id=?",
                (KIT_GUID, match_id))
    for s in segs:
        con.execute("""
            INSERT OR REPLACE INTO mh_segments
                (kit_guid, match_id, chromosome, start_cm, end_cm, length_cm, snps)
            VALUES (?,?,?,?,?,?,?)
        """, (KIT_GUID, match_id,
              s.get("chromosome"), s.get("start_cm"),
              s.get("end_cm"), s.get("length_cm"), s.get("snps")))
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
              b.get("match_id",""),
              b.get("shared_cm_with_kit"),
              b.get("shared_cm_ab"),
              b.get("predicted_rel","")))
    con.execute(
        "UPDATE mh_matches SET icw_fetched=1 WHERE kit_guid=? AND match_id=?",
        (KIT_GUID, match_id_a))
    con.commit()


# ── Session ───────────────────────────────────────────────────────────────────

def build_session(cookie_file: Path) -> Session:
    if not cookie_file.exists():
        print(f"❌  Cookie-Datei nicht gefunden: {cookie_file}")
        print("    → Browser → Cookie-Editor Extension → Export All → JSON")
        print(f"    → Speichern als: {cookie_file}")
        sys.exit(1)

    raw = json.loads(cookie_file.read_text(encoding="utf-8"))
    cookies = ({c["name"]: c["value"] for c in raw if "name" in c}
               if isinstance(raw, list) else raw)
    if not cookies:
        print("❌  Cookie-Datei leer oder unbekanntes Format.")
        sys.exit(1)

    sess = Session()
    sess.cookies.update(cookies)
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Referer": "https://www.myheritage.com/",
    })
    return sess


# ── HTML-Parsing: eingebettetes JSON extrahieren ──────────────────────────────

# Muster für React-SSR-Datenpakete (von häufig nach selten)
_JSON_PATTERNS = [
    # Standard React SSR / Next.js
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>',
    # window.__INITIAL_STATE__
    r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;',
    r'window\.__APP_STATE__\s*=\s*(\{.*?\})\s*;',
    r'window\.__STATE__\s*=\s*(\{.*?\})\s*;',
    # data-Attribute auf Root-Element
    r'<div[^>]+id=["\']root["\'][^>]+data-state=["\']([^"\']+)["\']',
    # Allgemeine application/json script-Tags
    r'<script[^>]+type=["\']application/json["\'][^>]*>\s*(\{.*?\})\s*</script>',
    # MyHeritage-spezifisch (nach spy-Auswertung ggf. ergänzen)
    r'window\.MH_APP_DATA\s*=\s*(\{.*?\})\s*;',
    r'window\.dnaMatchesData\s*=\s*(\{.*?\})\s*;',
    r'"dnaMatches"\s*:\s*(\[.*?\])',
]


def extract_json_from_html(html: str) -> dict | list | None:
    """Sucht eingebettetes JSON in SSR-HTML nach bekannten Mustern."""
    for pat in _JSON_PATTERNS:
        m = re.search(pat, html, re.DOTALL | re.IGNORECASE)
        if m:
            raw = m.group(1)
            try:
                parsed = json.loads(raw)
                log.debug("JSON gefunden via Muster: %s…", pat[:50])
                return parsed
            except json.JSONDecodeError:
                continue

    # Fallback: alle <script>-Inhalte die JSON-artig aussehen
    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("script"):
            txt = (tag.string or "").strip()
            if txt.startswith("{") or txt.startswith("["):
                try:
                    return json.loads(txt)
                except Exception:
                    pass
    return None


def find_matches_in_json(data: Any, depth: int = 0) -> list[dict]:
    """Sucht rekursiv nach einer Liste von Match-Objekten im JSON-Baum."""
    if depth > 6 or data is None:
        return []

    # Kandidaten-Schlüssel für Match-Listen
    MATCH_KEYS = {
        "matches", "dnaMatches", "matchList", "results",
        "items", "data", "list", "dnaMatchesList",
    }

    if isinstance(data, list) and data and isinstance(data[0], dict):
        # Prüfen ob es wie Match-Objekte aussieht
        sample = data[0]
        match_indicators = {
            "sharedDna", "sharedCm", "dnaMatchId", "matchId",
            "totalSharedSegmentsLengthInCm", "estimatedRelationship",
            "sharedSegmentsCount", "sharedDnaPercentage",
        }
        if match_indicators & set(sample.keys()):
            return data

    if isinstance(data, dict):
        for k, v in data.items():
            if k in MATCH_KEYS:
                result = find_matches_in_json(v, depth + 1)
                if result:
                    return result
        # Breitere Suche
        for v in data.values():
            result = find_matches_in_json(v, depth + 1)
            if result:
                return result

    return []


# ── Match-Objekt normalisieren ────────────────────────────────────────────────

def normalize_match(item: dict) -> dict | None:
    """Normalisiert ein rohe Match-Dict auf einheitliche Feldnamen."""
    # DNA-ID des Matches
    match_id = (
        item.get("dnaMatchId") or item.get("matchId") or
        item.get("id") or item.get("matchGuid") or
        item.get("dnaId") or ""
    )
    if not match_id:
        return None

    shared_cm = (
        item.get("totalSharedSegmentsLengthInCm") or
        item.get("sharedDnaLength") or item.get("sharedDna") or
        item.get("sharedCm") or item.get("sharedDnaInCm") or 0.0
    )
    segments = (
        item.get("sharedSegmentsCount") or item.get("numSharedSegments") or
        item.get("sharedSegments") or 0
    )
    largest = (
        item.get("maxSegmentLengthInCm") or item.get("largestSegment") or
        item.get("longestSegment") or 0.0
    )
    rel = (
        item.get("estimatedRelationship") or item.get("relationship") or
        item.get("predictedRelationship") or item.get("relationshipLabel") or ""
    )
    member_id = (
        item.get("memberId") or item.get("memberGuid") or
        (item.get("person") or {}).get("memberId") or ""
    )
    name = (
        item.get("displayName") or item.get("name") or item.get("fullName") or
        (item.get("person") or {}).get("name") or ""
    )
    has_tree = bool(
        item.get("hasTree") or item.get("familyTreeId") or
        item.get("treeId") or item.get("hasFamilyTree")
    )

    return {
        "match_id": str(match_id),
        "member_id": str(member_id),
        "display_name": str(name),
        "age_range": str(item.get("ageRange") or item.get("age") or ""),
        "country": str(
            item.get("country") or
            (item.get("location") or {}).get("country") or ""
        ),
        "shared_pct": float(
            item.get("sharedDnaPercentage") or item.get("sharedPct") or 0
        ),
        "shared_cm": float(shared_cm) if shared_cm else None,
        "shared_segments": int(segments) if segments else None,
        "largest_segment": float(largest) if largest else None,
        "predicted_rel": str(rel),
        "has_tree": has_tree,
        "tree_size": item.get("treeSize") or item.get("familyTreeSize"),
        "tree_owner": str(
            item.get("treeOwner") or item.get("familyTreeOwner") or ""
        ),
        "has_theory": bool(
            item.get("hasFamilyTheory") or item.get("theoryOfFamilyRelativity")
        ),
        "theory_rel": str(
            item.get("theoryRelationship") or item.get("confirmedRelationship") or ""
        ),
        "ancestral_surnames": (
            item.get("ancestralSurnames") or item.get("commonSurnames") or []
        ),
        "_raw": item,
    }


# ── Segment-Daten aus Match-Detail-Seite ─────────────────────────────────────

def fetch_segments_for_match(
    sess: Session, match_id: str, page: int = 1
) -> list[dict]:
    """Lädt die Match-Detail-Seite und extrahiert Segment-Daten."""
    url = (f"{BASE}/dna/match/"
           f"{OWN_DNA_ID}-{match_id}/{KIT_GUID}"
           f"?p={page}&ps={PAGE_SIZE}&sort=total_shared_segments_length_in_cm"
           f"&memberId={MEMBER_ID}&index=0")
    try:
        r = sess.get(url, timeout=20)
        if r.status_code != 200:
            log.debug("Detail %s: HTTP %d", match_id, r.status_code)
            return []
        data = extract_json_from_html(r.text)
        if not data:
            return []
        return _extract_segments(data)
    except Exception as e:
        log.debug("Segmente %s: %s", match_id, e)
        return []


def _extract_segments(data: Any, depth: int = 0) -> list[dict]:
    if depth > 5 or not data:
        return []
    SEG_KEYS = {"segments", "dnaSegments", "chromosomeSegments",
                "sharedSegments", "segmentData"}
    SEG_INDICATORS = {"chromosome", "chromosomeNumber", "startPoint",
                      "endPoint", "segmentLength", "startCm"}

    if isinstance(data, list) and data and isinstance(data[0], dict):
        if SEG_INDICATORS & set(data[0].keys()):
            return _normalize_segments(data)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in SEG_KEYS:
                result = _extract_segments(v, depth + 1)
                if result:
                    return result
        for v in data.values():
            result = _extract_segments(v, depth + 1)
            if result:
                return result
    return []


def _normalize_segments(raw: list[dict]) -> list[dict]:
    out = []
    for s in raw:
        chr_num = (s.get("chromosome") or s.get("chromosomeNumber") or
                   s.get("chr"))
        if chr_num is None:
            continue
        start = s.get("startPoint") or s.get("startCm") or s.get("start")
        end   = s.get("endPoint")   or s.get("endCm")   or s.get("end")
        length = s.get("segmentLength") or s.get("lengthCm") or s.get("length")
        out.append({
            "chromosome": int(chr_num),
            "start_cm": float(start) if start is not None else None,
            "end_cm":   float(end)   if end   is not None else None,
            "length_cm": float(length) if length is not None else None,
            "snps": s.get("snpCount") or s.get("snps"),
        })
    return out


# ── ICW aus Match-Detail-Seite ────────────────────────────────────────────────

def fetch_icw_for_match(
    sess: Session, match_id: str
) -> list[dict]:
    url = (f"{BASE}/dna/match/"
           f"{OWN_DNA_ID}-{match_id}/{KIT_GUID}"
           f"?p=1&ps=50&sort=total_shared_segments_length_in_cm"
           f"&memberId={MEMBER_ID}&index=0")
    try:
        r = sess.get(url, timeout=20)
        if r.status_code != 200:
            return []
        data = extract_json_from_html(r.text)
        if not data:
            return []
        return _extract_icw(data)
    except Exception as e:
        log.debug("ICW %s: %s", match_id, e)
        return []


def _extract_icw(data: Any, depth: int = 0) -> list[dict]:
    if depth > 5 or not data:
        return []
    ICW_KEYS = {"sharedMatches", "commonMatches", "mutualMatches",
                "inCommonWith", "icw"}
    if isinstance(data, dict):
        for k, v in data.items():
            if k in ICW_KEYS and isinstance(v, list):
                return [{"match_id": (i.get("dnaMatchId") or i.get("matchId") or ""),
                         "shared_cm_with_kit": i.get("sharedDnaLength") or i.get("sharedCm"),
                         "shared_cm_ab": i.get("sharedWithPrimary") or i.get("sharedCmAb"),
                         "predicted_rel": i.get("estimatedRelationship","")}
                        for i in v if i]
        for v in data.values():
            r = _extract_icw(v, depth + 1)
            if r:
                return r
    return []


# ── Hauptdownload ─────────────────────────────────────────────────────────────

def probe_html(sess: Session) -> tuple[str, int]:
    """Lädt erste Seite, gibt (html, http_status) zurück."""
    url = f"{BASE}/dna/matches/{KIT_GUID}"
    r = sess.get(url, timeout=20)
    return r.text, r.status_code


def download(
    sess: Session, con: sqlite3.Connection,
    only_new: bool, fetch_segments: bool, fetch_icw: bool, min_cm: float,
):
    page = 1
    fetched = total_pages = 0
    new_count = skipped = 0
    seg_count = 0
    start_ts = time.time()
    done = False

    while not done:
        url = f"{BASE}/dna/matches/{KIT_GUID}?p={page}&ps={PAGE_SIZE}"
        print(f"\r  Seite {page:3d} …", end="", flush=True)
        try:
            r = sess.get(url, timeout=20)
        except Exception as e:
            print(f"\n⚠️  Netzwerkfehler Seite {page}: {e}")
            break

        if r.status_code == 401 or r.status_code == 403:
            print(f"\n❌  HTTP {r.status_code} — Cookies abgelaufen. Bitte neu exportieren.")
            break
        if r.status_code != 200:
            print(f"\n⚠️  HTTP {r.status_code} auf Seite {page} — abgebrochen.")
            break

        data = extract_json_from_html(r.text)
        if data is None:
            # Letzter Versuch: gibt es JSON in der URL-Response direkt?
            try:
                data = r.json()
            except Exception:
                pass

        if data is None:
            print(f"\n⚠️  Seite {page}: Kein JSON gefunden.")
            print("   → Bitte Network-Tab (F12) → ersten XHR/Fetch-Call anklicken")
            print("     → URL + Response-Anfang hier herschicken")
            break

        matches_raw = find_matches_in_json(data)
        if not matches_raw:
            if page == 1:
                print("\n⚠️  Keine Matches in JSON gefunden.")
                keys = list(data.keys())[:15] if isinstance(data, dict) else type(data).__name__
                print(f"   → JSON-Schlüssel auf Ebene 1: {keys}")
                print("   Bitte diesen Output hier herschicken.")
            break

        for item in matches_raw:
            m = normalize_match(item)
            if not m:
                continue
            fetched += 1
            cm = m.get("shared_cm") or 0.0
            if cm < min_cm:
                done = True
                break

            mid = m["match_id"]
            is_new = not match_exists(con, mid)
            if only_new and not is_new:
                skipped += 1
                continue

            new_count += 1
            upsert_match(con, m)

            elapsed = time.time() - start_ts
            print(
                f"\r  Seite {page:3d} | {fetched:5d} Matches"
                f" | {cm:.0f} cM | +{new_count} neu | {elapsed:.0f}s",
                end="", flush=True,
            )

            if fetch_segments and mid and (is_new or not only_new):
                time.sleep(DELAY_DETAIL)
                segs = fetch_segments_for_match(sess, mid)
                if segs:
                    save_segments(con, mid, segs)
                    seg_count += len(segs)

            if fetch_icw and is_new and cm >= 30:
                time.sleep(DELAY_DETAIL)
                icw = fetch_icw_for_match(sess, mid)
                if icw:
                    save_icw(con, mid, icw)

        if not done:
            page += 1
            time.sleep(DELAY_PAGE)

    print()
    return fetched, new_count, skipped, seg_count


# ── --probe Modus ─────────────────────────────────────────────────────────────

def probe_mode(sess: Session):
    """Zeigt was auf der ersten Seite gefunden wird — für Diagnose."""
    print("🔍  Lade erste Seite …")
    html, status = probe_html(sess)
    print(f"    HTTP {status}, {len(html)} Zeichen")

    data = extract_json_from_html(html)
    if data is None:
        print("❌  Kein JSON gefunden.")
        print()
        # Alle <script>-Tags ausgeben
        for pat in [r'<script[^>]*>(.*?)</script>']:
            for m in re.finditer(pat, html, re.DOTALL):
                content = m.group(1).strip()
                if len(content) > 50 and ('{' in content or '[' in content):
                    print(f"  Script ({len(content)} Zeichen): {content[:200]!r} …")
        return

    print(f"✅  JSON gefunden: Typ={type(data).__name__}", end="")
    if isinstance(data, dict):
        print(f", Schlüssel: {list(data.keys())[:20]}")
    else:
        print(f", Länge: {len(data)}")

    matches = find_matches_in_json(data)
    if matches:
        print(f"✅  {len(matches)} Match-Objekte gefunden")
        m0 = matches[0]
        print(f"   Felder: {list(m0.keys())[:15]}")
        nm = normalize_match(m0)
        if nm:
            print(f"   Erster Match: {nm['display_name']}, "
                  f"{nm['shared_cm']} cM, {nm['match_id']}")
    else:
        print("⚠️  Keine Match-Objekte erkannt.")
        print(f"   JSON-Inhalt (Anfang): {json.dumps(data)[:500]}")


# ── Statistik ─────────────────────────────────────────────────────────────────

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
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Matches gesamt:     {row[0]:>6}")
    print(f"  Ø cM:               {(row[1] or 0):>6.1f}")
    print(f"  Max cM:             {(row[2] or 0):>6.1f}")
    print(f"  Matches mit Segm.:  {row[3] or 0:>6}")
    print(f"  Matches mit ICW:    {row[4] or 0:>6}")
    print(f"  Segment-Einträge:   {seg_total:>6}  ← Chromosom-Browser möglich!")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookies",     default=str(COOKIE_FILE))
    ap.add_argument("--db",          default=str(DB_FILE))
    ap.add_argument("--only-new",    action="store_true")
    ap.add_argument("--no-segments", action="store_true")
    ap.add_argument("--no-icw",      action="store_true")
    ap.add_argument("--min-cm",      type=float, default=MIN_CM_DEFAULT)
    ap.add_argument("--probe",       action="store_true",
                    help="Diagnose: zeigt gefundene JSON-Struktur der ersten Seite")
    ap.add_argument("--debug",       action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    if not HAS_BS4:
        print("⚠️  beautifulsoup4 nicht installiert (optional, verbessert HTML-Parsing)")
        print("    pip install beautifulsoup4")

    print(f"📂  DB:      {args.db}")
    print(f"🍪  Cookies: {args.cookies}")
    print(f"🧬  Kit:     {KIT_GUID}")
    print()

    _DATA.mkdir(parents=True, exist_ok=True)
    sess = build_session(Path(args.cookies))
    con  = init_db(Path(args.db))

    if args.probe:
        probe_mode(sess)
        return

    fetched, new_count, skipped, seg_count = download(
        sess, con,
        only_new=args.only_new,
        fetch_segments=not args.no_segments,
        fetch_icw=not args.no_icw,
        min_cm=args.min_cm,
    )

    print(f"✅  {fetched} verarbeitet, {new_count} neu, {skipped} übersprungen, "
          f"{seg_count} Segmente")
    print_stats(con)
    con.close()


if __name__ == "__main__":
    main()
