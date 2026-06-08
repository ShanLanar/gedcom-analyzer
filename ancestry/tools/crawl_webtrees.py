#!/usr/bin/env python3
"""
webtrees-Crawler — iterativer, höflicher Crawler für öffentliche
webtrees-Stammbäume (z.B. https://stammbaum.anverwandte.info/).

Geht von einer Start-Person aus, folgt den Verwandtschafts-Links
(Eltern/Partner/Kinder) im Breitensuch-Verfahren und legt jede Person in
einer lokalen SQLite-DB ab. Resumierbar: Frontier und besuchte IDs werden
gespeichert, ein erneuter Aufruf macht da weiter, wo er aufhörte.

WICHTIG / fair use — DIESE SEITE BITTE BESONDERS SCHONEN:
  * robots.txt wird respektiert (Abbruch, wenn das Ziel verboten ist).
  * Standard-Rate-Limit: 4 s zwischen Anfragen + zufälliger Jitter
    (~4–6 s real). Der Betreiber hatte schon Crawler-Probleme — lieber
    zu langsam als zu schnell. --delay kann nur ERHÖHT werden (sinnvoll).
  * Standard nur 300 Seiten pro Lauf; danach Pause. Resumierbar, also über
    mehrere Tage verteilen statt 400k am Stück.
  * Klarer User-Agent. Nur öffentlich zugängliche Seiten werden gelesen.
  Bitte ausschließlich für eigene Forschung und im Rahmen der
  Nutzungsbedingungen der Seite verwenden.

Da sich das HTML je nach webtrees-Theme unterscheidet, ist der Parser
HEURISTISCH. Erst eine echte Seite prüfen:

    python crawl_webtrees.py dump "https://stammbaum.anverwandte.info/tree/anverwandte/individual/I114571/..."

Das zeigt, was der Parser extrahiert. Stimmt es, dann crawlen:

    python crawl_webtrees.py crawl "https://.../individual/I114571/..." --max 500 --delay 1.0

Export ins GEDCOM-kompatible Format folgt, sobald der Parser sauber sitzt.
"""
from __future__ import annotations
import re
import sys
import time
import json
import sqlite3
import argparse
import logging
from urllib import request, parse
from urllib.error import HTTPError, URLError
from urllib.robotparser import RobotFileParser
from pathlib import Path

log = logging.getLogger(__name__)

USER_AGENT = "gedcom-analyzer-crawler/1.0 (personal genealogy research)"
DB_PATH    = Path(__file__).resolve().parent / "webtrees_crawl.db"

# webtrees-Link-Muster: /tree/<baum>/individual/I12345/slug
# IDs können auch andere Buchstaben-Präfixe haben (X…, F… ist Familie)
_IND_RE    = re.compile(r"/tree/[^/\"']+/individual/([A-Z]+\d+)")
_FAM_RE    = re.compile(r"/tree/[^/\"']+/family/(F\d+)")
_BASE_RE   = re.compile(r"^(https?://[^/]+)")
_TITLE_RE  = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAG_RE    = re.compile(r"<[^>]+>")
_YEAR_RE   = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")

# webtrees-spezifische Muster (Theme xenea, v2.x)
_DESC_RE   = re.compile(r'<meta name="description" content="(.*?)">', re.I | re.S)
_H2_RE     = re.compile(r'<h2 class="wt-page-title[^>]*>(.*?)</h2>', re.I | re.S)
_NAME_SPAN = re.compile(r'<span class="NAME"[^>]*>(.*?)</span>\s*</span>', re.I | re.S)
_SURN_RE   = re.compile(r'<span class="SURN">(.*?)</span>', re.I | re.S)
_GEDNAME   = re.compile(r'<bdi>([^<]*?/[^<]*?/[^<]*?)</bdi>')
# title="Ort ⁨Datum⁩"  (⁨ = U+2068, ⁩ = U+2069 — bidi-Isolate)
_LIFE_RE   = re.compile(r'title="([^"⁨⁩]*?)\s*⁨([^⁩]*?)⁩"')
# Matricula-Kirchenbuch-Quellen (für die nicht-indizierte Matricula-Suche Gold wert).
# ACHTUNG: Die im Stammbaum hinterlegten Matricula-URLs sind die ALTE Struktur
# (z.B. .../hagen-st-martinus/0035/?pg=4). Matricula hat Pfarrei-Slugs, Register-
# IDs und Seitenzählung neu vergeben – die Deep-Links sind tot und NICHT
# deterministisch umrechenbar. Wir bewahren daher zusätzlich den lesbaren
# Quellenbeleg (Seite/Nummer) UND die Pfarrei (aus dem Ortskontext der Tatsache),
# damit die Quelle auf dem aktuellen Matricula auffindbar bleibt.
_MATRIC_RE   = re.compile(r'(https?://data\.matricula-online\.eu/[^\s"\'<>]+)')
# Anker + nachfolgender Belegtext, z.B. >Quelle: Matricula</a> S. 49, Nr. 25 weibl.
_MATRIC_CITE = re.compile(
    r'<a href="(https?://data\.matricula-online\.eu/[^"]+)"[^>]*>'
    r'[^<]*</a>\s*([^<]*)')
# Diözese + Pfarrei-Pfad aus einer (alten) Matricula-URL ziehen:
# /de/deutschland/<diözese>/<pfarrei>/<register>/...
_MATRIC_PATH = re.compile(
    r'data\.matricula-online\.eu/\w+/\w+/([^/]+)/([^/]+)/')


def _clean(html_fragment: str) -> str:
    txt = _TAG_RE.sub(" ", html_fragment or "")
    txt = re.sub(r"&nbsp;", " ", txt)
    txt = re.sub(r"&amp;", "&", txt)
    return re.sub(r"\s+", " ", txt).strip()


# ── HTTP (höflich) ────────────────────────────────────────────────────────────

class Fetcher:
    def __init__(self, base: str, delay: float = 4.0):
        self.base = base
        self.delay = delay      # Mindestpause zwischen Anfragen (Sekunden)
        self._last = 0.0
        self.robots = RobotFileParser()
        try:
            self.robots.set_url(base + "/robots.txt")
            self.robots.read()
        except Exception:
            self.robots = None  # kein robots.txt -> erlaubt

    def allowed(self, url: str) -> bool:
        if not self.robots:
            return True
        try:
            return self.robots.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def get(self, url: str, retries: int = 2, timeout: int = 25) -> str | None:
        if not self.allowed(url):
            log.warning("robots.txt verbietet: %s", url)
            return None
        # Rate-Limit mit Jitter (schonend, menschenähnlich, keine Lastspitzen)
        import random
        target = self.delay + random.uniform(0, self.delay * 0.5)
        wait = target - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        last_err = None
        for attempt in range(retries + 1):
            try:
                req = request.Request(url, headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "de,en;q=0.8",
                })
                with request.urlopen(req, timeout=timeout) as r:
                    self._last = time.time()
                    return r.read().decode("utf-8", errors="replace")
            except (HTTPError, URLError, TimeoutError) as e:
                last_err = e
                if isinstance(e, HTTPError) and e.code in (403, 404, 410):
                    break  # nicht erneut versuchen
                time.sleep(2 ** attempt)
        log.warning("Fehlgeschlagen %s: %s", url, last_err)
        self._last = time.time()
        return None


# ── Parser (heuristisch — an einer echten Seite eichen!) ──────────────────────

def parse_individual(html: str, url: str) -> dict:
    """Extrahiert Felder einer webtrees-Individual-Seite (Theme xenea, v2.x)."""
    m = _IND_RE.search(url)
    ind_id = m.group(1) if m else ""

    # ── Name: bevorzugt GEDCOM-Name aus dem Namen-Accordion: "Peter* Georg /Kovermann/"
    given = surname = name = ""
    gn = _GEDNAME.search(html)
    if gn:
        raw = gn.group(1).strip()
        sm = re.search(r"/([^/]*)/", raw)
        surname = (sm.group(1).strip() if sm else "")
        given = re.sub(r"/[^/]*/", "", raw).replace("*", "").strip()
        given = re.sub(r"\s+", " ", given)
        name = f"{given} {surname}".strip()
    # Fallback: SURN-Span im Seitentitel-h2
    h2 = _H2_RE.search(html)
    h2txt = h2.group(1) if h2 else ""
    if not surname and h2txt:
        sm = _SURN_RE.search(h2txt)
        surname = _clean(sm.group(1)) if sm else ""
    if not name:
        nm = _NAME_SPAN.search(h2txt or html)
        name = _clean(nm.group(1)) if nm else ""
        if surname and not given:
            given = name.replace(surname, "").strip()

    # ── Geschlecht
    sex = ""
    if "female_gender" in (h2txt or "") or "wt-icon-sex-f" in (h2txt or ""):
        sex = "F"
    elif "male_gender" in (h2txt or "") or "wt-icon-sex-m" in (h2txt or ""):
        sex = "M"

    # ── Geburt/Tod: title="Ort ⁨Datum⁩" im h2 (1. = Geburt, 2. = Tod)
    birth_place = birth_date = death_place = death_date = ""
    life = _LIFE_RE.findall(h2txt)
    if life:
        birth_place, birth_date = life[0][0].strip(", "), life[0][1].strip()
    if len(life) > 1:
        death_place, death_date = life[1][0].strip(", "), life[1][1].strip()

    # Jahre aus den Daten oder dem Titel
    def _yr(s):
        y = _YEAR_RE.search(s or ""); return y.group(1) if y else ""
    birth_year, death_year = _yr(birth_date), _yr(death_date)
    if not (birth_year and death_year):
        t = _TITLE_RE.search(html)
        if t:
            yy = _YEAR_RE.findall(t.group(1))
            birth_year = birth_year or (yy[0] if yy else "")
            death_year = death_year or (yy[1] if len(yy) > 1 else "")

    # ── Meta-Description: "Geburt … , Tod … , Eltern A + B, Partner/in C, Kinder D, E…"
    father_name = mother_name = ""
    spouse_names: list[str] = []
    child_names:  list[str] = []
    dsc = _DESC_RE.search(html)
    if dsc:
        desc = _clean(dsc.group(1))
        em = re.search(r"Eltern\s+(.+?)\s+\+\s+(.+?)(?:,\s+(?:Partner/in|Kinder)\b|$)", desc)
        if em:
            father_name, mother_name = em.group(1).strip(), em.group(2).strip()
        sp = re.search(r"Partner/in\s+(.+?)(?:,\s+Kinder\b|$)", desc)
        if sp:
            spouse_names = [s.strip() for s in re.split(r"\s+&\s+", sp.group(1)) if s.strip()]
        ki = re.search(r"Kinder\s+(.+)$", desc)
        if ki:
            child_names = [c.strip() for c in ki.group(1).split(",") if c.strip()]

    # ── Matricula-Kirchenbuch-Quellen (nicht-indizierte Fundstellen!)
    # Liste von {url_old, ref, diocese, parish_old} – url_old ist die alte,
    # tote Deep-Link-Struktur; ref ("S. 49, Nr. 25") + parish bleiben nutzbar.
    matricula = []
    seen_m = set()
    for m_url, m_ref in _MATRIC_CITE.findall(html):
        if m_url in seen_m:
            continue
        seen_m.add(m_url)
        pth = _MATRIC_PATH.search(m_url)
        diocese = pth.group(1) if pth else ""
        matricula.append({
            "url_old":     m_url,
            "ref":         re.sub(r"\s+", " ", (m_ref or "")).strip(),
            "diocese":     diocese,
            "parish_old":  pth.group(2) if pth else "",
            "diocese_url": (f"https://data.matricula-online.eu/de/deutschland/{diocese}/"
                            if diocese else ""),
        })
    # Falls ein Link ohne erkennbaren Beleg-Text auftaucht, trotzdem erfassen:
    for m_url in _MATRIC_RE.findall(html):
        if m_url not in seen_m:
            seen_m.add(m_url)
            pth = _MATRIC_PATH.search(m_url)
            matricula.append({"url_old": m_url, "ref": "",
                              "diocese": pth.group(1) if pth else "",
                              "parish_old": pth.group(2) if pth else ""})

    # ── verlinkte Personen/Familien (für BFS-Traversierung)
    related = sorted(set(_IND_RE.findall(html)) - ({ind_id} if ind_id else set()))
    families = sorted(set(_FAM_RE.findall(html)))

    return {
        "id":          ind_id,
        "url":         url,
        "name":        name,
        "given_name":  given,
        "surname":     surname,
        "sex":         sex,
        "birth_date":  birth_date,
        "birth_place": birth_place,
        "birth_year":  birth_year,
        "death_date":  death_date,
        "death_place": death_place,
        "death_year":  death_year,
        "father_name": father_name,
        "mother_name": mother_name,
        "spouse_names": spouse_names,
        "child_names":  child_names,
        "matricula":   matricula,
        "related":     related,
        "families":    families,
    }


# ── Persistenz ────────────────────────────────────────────────────────────────

def _db(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(path))
    c.executescript("""
        CREATE TABLE IF NOT EXISTS wt_persons (
            id TEXT PRIMARY KEY, url TEXT, name TEXT, given_name TEXT,
            surname TEXT, sex TEXT, birth_date TEXT, birth_place TEXT,
            birth_year TEXT, death_date TEXT, death_place TEXT, death_year TEXT,
            father_name TEXT, mother_name TEXT, spouse_names_json TEXT,
            child_names_json TEXT, matricula_json TEXT,
            related_json TEXT, families_json TEXT, fetched_at TEXT
        );
        CREATE TABLE IF NOT EXISTS wt_frontier (
            id TEXT PRIMARY KEY, depth INTEGER DEFAULT 0, done INTEGER DEFAULT 0
        );
    """)
    c.commit()
    return c


# ── Crawl (BFS, resumierbar) ──────────────────────────────────────────────────

def crawl(seed_url: str, max_pages: int = 300, delay: float = 4.0,
          db_path: Path = DB_PATH):
    base = (_BASE_RE.match(seed_url) or [None, ""])[1]
    if not base:
        print("Ungültige Start-URL."); return
    tree_m = re.search(r"/tree/([^/]+)/individual/", seed_url)
    tree = tree_m.group(1) if tree_m else "anverwandte"

    f = Fetcher(base, delay=delay)
    c = _db(db_path)

    seed_id = (_IND_RE.search(seed_url) or [None, ""])[1]
    if seed_id:
        c.execute("INSERT OR IGNORE INTO wt_frontier (id, depth, done) VALUES (?,0,0)",
                  (seed_id,))
        c.commit()

    done_count = c.execute("SELECT COUNT(*) FROM wt_frontier WHERE done=1").fetchone()[0]
    print(f"Start. Bereits erledigt: {done_count}. Ziel: +{max_pages} Seiten. "
          f"Delay: {delay}s")

    processed = 0
    while processed < max_pages:
        row = c.execute(
            "SELECT id, depth FROM wt_frontier WHERE done=0 ORDER BY depth LIMIT 1"
        ).fetchone()
        if not row:
            print("Frontier leer — Crawl vollständig."); break
        ind_id, depth = row
        url = f"{base}/tree/{tree}/individual/{ind_id}"
        html = f.get(url)
        c.execute("UPDATE wt_frontier SET done=1 WHERE id=?", (ind_id,))
        if html:
            p = parse_individual(html, url)
            c.execute("""INSERT OR REPLACE INTO wt_persons
                (id,url,name,given_name,surname,sex,birth_date,birth_place,
                 birth_year,death_date,death_place,death_year,father_name,
                 mother_name,spouse_names_json,child_names_json,
                 matricula_json,related_json,families_json,fetched_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (p["id"] or ind_id, url, p["name"], p["given_name"], p["surname"],
                 p["sex"], p["birth_date"], p["birth_place"], p["birth_year"],
                 p["death_date"], p["death_place"], p["death_year"],
                 p["father_name"], p["mother_name"],
                 json.dumps(p["spouse_names"]), json.dumps(p["child_names"]),
                 json.dumps(p["matricula"]),
                 json.dumps(p["related"]), json.dumps(p["families"])))
            for rid in p["related"]:
                c.execute("INSERT OR IGNORE INTO wt_frontier (id,depth,done) "
                          "VALUES (?,?,0)", (rid, depth + 1))
        processed += 1
        if processed % 25 == 0:
            c.commit()
            total = c.execute("SELECT COUNT(*) FROM wt_persons").fetchone()[0]
            front = c.execute("SELECT COUNT(*) FROM wt_frontier WHERE done=0").fetchone()[0]
            print(f"  +{processed}  | Personen: {total} | offen: {front}")
    c.commit()
    total = c.execute("SELECT COUNT(*) FROM wt_persons").fetchone()[0]
    front = c.execute("SELECT COUNT(*) FROM wt_frontier WHERE done=0").fetchone()[0]
    print(f"\nFertig. Personen gesamt: {total}. Noch offen: {front}.")
    print(f"DB: {db_path}  (erneut starten = fortsetzen)")
    c.close()


def dump(url: str):
    """Eine Seite holen und zeigen, was der Parser extrahiert (zum Eichen)."""
    base = (_BASE_RE.match(url) or [None, ""])[1]
    f = Fetcher(base, delay=0)
    print(f"robots.txt erlaubt: {f.allowed(url)}")
    html = f.get(url)
    if not html:
        print("Keine Antwort (Sandbox? Sperre? robots?)."); return
    print(f"HTML-Länge: {len(html)} Zeichen")
    p = parse_individual(html, url)
    p2 = dict(p); p2["related"] = p["related"][:15]
    print(json.dumps(p2, indent=2, ensure_ascii=False))
    print(f"\nVerlinkte Personen gesamt: {len(p['related'])}")


def main(argv):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("dump");  d.add_argument("url")
    cr = sub.add_parser("crawl")
    cr.add_argument("url")
    cr.add_argument("--max", type=int, default=300,
                    help="Max. Seiten pro Lauf (Default 300, schonend)")
    cr.add_argument("--delay", type=float, default=4.0,
                    help="Mindestpause zw. Anfragen in s (Default 4.0 + Jitter)")
    args = ap.parse_args(argv[1:])
    if args.cmd == "dump":
        dump(args.url)
    elif args.cmd == "crawl":
        crawl(args.url, max_pages=args.max, delay=args.delay)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
