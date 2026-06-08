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

Gerichteter Crawl (Standard 'both'): erst alle Vorfahren des Vaters,
dann von jedem Vorfahren alle Nachkommen = die ganze Blutsverwandtschaft:

    python crawl_webtrees.py crawl "https://.../individual/I114571/..." --mode both

Nachkommen-Explosion eindämmen (optional, Raum/Zeit):

    python crawl_webtrees.py crawl "https://.../I114571/..." \\
        --place "Osnabrück,Hagen,Oesede,Ostercappeln,Mettingen" \\
        --year-min 1650 --year-max 1930

Matricula-Belege samt reparierter (Pfarrei-)URLs ausgeben:

    python crawl_webtrees.py matricula
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


# ── Familienlotse: Rollen (Eltern vs. Kinder) deterministisch trennen ─────────

_FNAV_ROW = re.compile(
    r'<tr class="text-center wt-family-navigator-(parent|child)[^"]*">(.*?)</tr>',
    re.S)


def parse_family_nav(html: str) -> dict:
    """Zerlegt den 'Familienlotse'-Sidebar in gerichtete Kanten.

    Rückgabe: {"parents": [...], "children": [...], "spouses": [...],
               "siblings": [...]} mit webtrees-IDs.

    Der Sidebar trennt über HTML-Kommentare sauber zwischen Eltern-Familien
    (oben) und eigenen Familien (unten):
      <!-- parent families --> … <!-- spouse and children --> … <!-- step children -->
    In Eltern-Familien sind Kind-Zeilen = Geschwister; in eigenen Familien
    sind Kind-Zeilen = Nachkommen.
    """
    nav = html.split("wt-sidebar-family-navigator", 1)
    nav = nav[1] if len(nav) > 1 else ""
    parent_seg, _, own_seg = nav.partition("<!-- spouse and children -->")

    parents, children, spouses, siblings = [], [], [], []

    def _rows(segment, sibling_mode):
        for kind, body in _FNAV_ROW.findall(segment):
            th, _, td = body.partition("</th>")
            role = _clean(th)
            mm = re.search(r"/individual/([A-Z]+\d+)", td)
            if not mm:
                continue
            pid = mm.group(1)
            if "selbst" in role:
                continue
            if kind == "parent":
                if any(w in role for w in ("Vater", "Mutter")):
                    parents.append(pid)
                elif any(w in role for w in ("Ehefrau", "Ehemann", "Partner",
                                             "Ehepartner")):
                    spouses.append(pid)
            else:  # child-Zeile
                if sibling_mode:
                    siblings.append(pid)
                else:
                    children.append(pid)

    _rows(parent_seg, sibling_mode=True)    # Eltern-Familien -> Geschwister
    _rows(own_seg,    sibling_mode=False)   # eigene Familien -> Nachkommen

    dedup = lambda xs: list(dict.fromkeys(xs))
    return {"parents": dedup(parents), "children": dedup(children),
            "spouses": dedup(spouses), "siblings": dedup(siblings)}


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

    # ── gerichtete Verwandtschaft (Eltern/Kinder/Partner/Geschwister)
    fam = parse_family_nav(html)

    # ── verlinkte Personen/Familien (für ungerichtete Traversierung)
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
        "parents":     fam["parents"],
        "children":    fam["children"],
        "spouses_ids": fam["spouses"],
        "siblings":    fam["siblings"],
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
            parents_json TEXT, children_json TEXT, spouses_json TEXT,
            siblings_json TEXT,
            related_json TEXT, families_json TEXT, fetched_at TEXT
        );
        -- direction: 'up' = Eltern verfolgen, 'down' = Kinder verfolgen
        CREATE TABLE IF NOT EXISTS wt_frontier (
            id TEXT NOT NULL, direction TEXT NOT NULL DEFAULT 'both',
            depth INTEGER DEFAULT 0, done INTEGER DEFAULT 0,
            PRIMARY KEY (id, direction)
        );
    """)
    c.commit()
    return c


def _save_person(c, p, ind_id, url):
    c.execute("""INSERT OR REPLACE INTO wt_persons
        (id,url,name,given_name,surname,sex,birth_date,birth_place,
         birth_year,death_date,death_place,death_year,father_name,
         mother_name,spouse_names_json,child_names_json,matricula_json,
         parents_json,children_json,spouses_json,siblings_json,
         related_json,families_json,fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
        (p["id"] or ind_id, url, p["name"], p["given_name"], p["surname"],
         p["sex"], p["birth_date"], p["birth_place"], p["birth_year"],
         p["death_date"], p["death_place"], p["death_year"],
         p["father_name"], p["mother_name"],
         json.dumps(p["spouse_names"]), json.dumps(p["child_names"]),
         json.dumps(p["matricula"]),
         json.dumps(p["parents"]), json.dumps(p["children"]),
         json.dumps(p["spouses_ids"]), json.dumps(p["siblings"]),
         json.dumps(p["related"]), json.dumps(p["families"])))


def _in_scope(p, place_filter, year_min, year_max) -> bool:
    """Liegt die Person im gewünschten Raum/Zeitfenster? Bestimmt, ob ihre
    Nachkommen WEITER verfolgt werden (Pruning gegen Explosion)."""
    if place_filter:
        hay = f"{p.get('birth_place','')} {p.get('death_place','')}".lower()
        if not any(tok in hay for tok in place_filter):
            # Ort passt nicht – nur durchlassen, wenn (noch) kein Ort bekannt
            if p.get("birth_place") or p.get("death_place"):
                return False
    if year_min or year_max:
        ys = []
        for y in (p.get("birth_year"), p.get("death_year")):
            try:
                if y:
                    ys.append(int(y))
            except (ValueError, TypeError):
                pass
        if ys:
            y = min(ys)
            if year_min and y < year_min:
                return False
            if year_max and y > year_max:
                return False
    return True


# ── Crawl (gerichtet, zweiphasig, resumierbar) ────────────────────────────────

def crawl(seed_url: str, max_pages: int = 300, delay: float = 4.0,
          mode: str = "both", place_filter=None, year_min=0, year_max=0,
          db_path: Path = DB_PATH):
    """mode:
        'up'   – nur Vorfahren (Eltern rückwärts)
        'down' – nur Nachkommen (Kinder vorwärts)
        'both' – erst alle Vorfahren, dann von ihnen alle Nachkommen
    place_filter: Liste von Ortsteilstrings (lowercase); year_min/max: Pruning
    der Nachkommen, damit der Crawl im gewünschten Raum/Zeitfenster bleibt.
    """
    base = (_BASE_RE.match(seed_url) or [None, ""])[1]
    if not base:
        print("Ungültige Start-URL."); return
    tree_m = re.search(r"/tree/([^/]+)/individual/", seed_url)
    tree = tree_m.group(1) if tree_m else "anverwandte"
    place_filter = [s.lower() for s in (place_filter or [])]

    f = Fetcher(base, delay=delay)
    c = _db(db_path)
    seed_id = (_IND_RE.search(seed_url) or [None, ""])[1]

    def enqueue(pid, direction, depth):
        c.execute("INSERT OR IGNORE INTO wt_frontier (id,direction,depth,done) "
                  "VALUES (?,?,?,0)", (pid, direction, depth))

    def neighbors(pid, direction):
        """IDs in der gewünschten Richtung. Lädt die Seite (einmalig) falls nötig.

        Rückgabe: (id_list, pdata) — ODER (None, None) bei Netzwerkfehler.
        None signalisiert dem Caller: nicht als done markieren, nächste Runde
        nochmal versuchen.
        """
        row = c.execute("SELECT parents_json, children_json, birth_place, "
                        "death_place, birth_year, death_year FROM wt_persons "
                        "WHERE id=?", (pid,)).fetchone()
        if row is None:
            url = f"{base}/tree/{tree}/individual/{pid}"
            html = f.get(url)
            if not html:
                return None, None   # Netzwerkfehler → nicht als erledigt markieren
            try:
                p = parse_individual(html, url)
                _save_person(c, p, pid, url)
            except Exception as e:
                log.warning("Parse/Speicher-Fehler %s: %s", pid, e)
                # Mark done so we don't retry an unparseable page endlessly,
                # but return empty ids so no phantom descendants get enqueued.
                c.execute("UPDATE wt_frontier SET done=1 WHERE id=? AND direction=?",
                          (pid, direction))
                c.commit()
                return [], None  # pdata=None prevents _in_scope expansion
            pdata = p
            par, chi = p["parents"], p["children"]
        else:
            try:
                par = json.loads(row[0] or "[]")
            except (json.JSONDecodeError, TypeError):
                par = []
            try:
                chi = json.loads(row[1] or "[]")
            except (json.JSONDecodeError, TypeError):
                chi = []
            pdata = {"birth_place": row[2], "death_place": row[3],
                     "birth_year": row[4], "death_year": row[5]}
        return (par if direction == "up" else chi), pdata

    # ── Phase steuern ────────────────────────────────────────────────────────
    phases = {"up": ["up"], "down": ["down"], "both": ["up", "down"]}[mode]

    for ph_idx, direction in enumerate(phases):
        if direction == "up" and seed_id:
            enqueue(seed_id, "up", 0)
        if direction == "down":
            # Startpunkte abwärts: alle bisher (in Phase 'up') gefundenen Personen
            if mode == "both":
                for (pid,) in c.execute("SELECT id FROM wt_persons").fetchall():
                    enqueue(pid, "down", 0)
            elif seed_id:
                enqueue(seed_id, "down", 0)
        c.commit()

        label = {"up": "Vorfahren ⬆", "down": "Nachkommen ⬇"}[direction]
        print(f"\n=== Phase {ph_idx+1}/{len(phases)}: {label} ===")
        processed = 0
        while processed < max_pages:
            row = c.execute("SELECT id, depth FROM wt_frontier WHERE done=0 AND "
                            "direction=? ORDER BY depth LIMIT 1", (direction,)
                            ).fetchone()
            if not row:
                print(f"Frontier ({direction}) leer — Phase vollständig."); break
            pid, depth = row
            ids, pdata = neighbors(pid, direction)
            if ids is None:
                # Netzwerkfehler — in Frontier lassen für nächsten Lauf
                processed += 1
                continue
            c.execute("UPDATE wt_frontier SET done=1 WHERE id=? AND direction=?",
                      (pid, direction))

            # Pruning: abwärts nur expandieren, wenn Person im Raum/Zeitfenster
            expand = True
            if direction == "down" and pdata is not None:
                expand = _in_scope(pdata, place_filter, year_min, year_max)
            if expand:
                for nid in ids:
                    enqueue(nid, direction, depth + 1)

            processed += 1
            if processed % 25 == 0:
                c.commit()
                total = c.execute("SELECT COUNT(*) FROM wt_persons").fetchone()[0]
                openf = c.execute("SELECT COUNT(*) FROM wt_frontier WHERE done=0 "
                                  "AND direction=?", (direction,)).fetchone()[0]
                print(f"  +{processed}  | Personen: {total} | offen({direction}): {openf}")
        c.commit()
        if processed >= max_pages:
            print(f"Seiten-Limit ({max_pages}) erreicht – erneut starten zum Fortsetzen.")
            break

    total = c.execute("SELECT COUNT(*) FROM wt_persons").fetchone()[0]
    print(f"\nFertig. Personen gesamt: {total}.")
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


# ── Matricula-Link-Reparatur (Pfarrei-Slug alt -> neu) ────────────────────────
# Matricula hat die Pfarrei-Slugs UND Register-IDs neu vergeben. Die Register-ID
# (z.B. 0035 -> D1_001) ist ohne Matricula-Katalog NICHT herleitbar; den
# Pfarrei-Slug können wir aber für den überschaubaren Raum (südl. Kreis
# Osnabrück) pflegen, sodass wir auf die aktuelle PFARREI-Übersicht verlinken.
# Erweiterbar über tools/matricula_parish_map.json  {"<alt-slug>": "<neu-slug>"}.
MATRICULA_PARISH_MAP = {
    # bestätigt:
    "hagen-st-martinus": "hagen-a-t-w-st-martinus",
}


def _load_parish_map() -> dict:
    m = dict(MATRICULA_PARISH_MAP)
    f = SCRIPT_DIR / "matricula_parish_map.json" if "SCRIPT_DIR" in globals() else None
    try:
        p = Path(__file__).resolve().parent / "matricula_parish_map.json"
        if p.exists():
            m.update(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return m


def matricula_current_url(entry: dict, parish_map: dict | None = None) -> str:
    """Bestmögliche AKTUELLE Matricula-URL für einen Beleg.
    Bekannte Pfarrei -> aktuelle Pfarrei-Übersicht; sonst Diözesen-Seite.
    Die genaue Register-/Seitenangabe steckt im 'ref' (z.B. 'S. 352')."""
    pm = parish_map if parish_map is not None else _load_parish_map()
    dio = entry.get("diocese", "")
    parish_old = entry.get("parish_old", "")
    new_parish = pm.get(parish_old)
    if dio and new_parish:
        return f"https://data.matricula-online.eu/de/deutschland/{dio}/{new_parish}/"
    return entry.get("diocese_url", "")


def matricula_report(db_path: Path = DB_PATH):
    """Listet alle gesammelten Matricula-Belege mit reparierter (Pfarrei-)URL."""
    if not db_path.exists():
        print(f"DB nicht gefunden: {db_path}"); return
    pm = _load_parish_map()
    c = sqlite3.connect(str(db_path)); c.row_factory = sqlite3.Row
    n = unmapped = 0
    seen_parishes = {}
    for r in c.execute("SELECT name, birth_place, matricula_json FROM wt_persons "
                       "WHERE COALESCE(matricula_json,'') NOT IN ('','[]')"):
        for e in json.loads(r["matricula_json"]):
            n += 1
            cur = matricula_current_url(e, pm)
            mapped = e.get("parish_old") in pm
            if not mapped and e.get("parish_old"):
                unmapped += 1
                seen_parishes[e["parish_old"]] = e.get("diocese", "")
            print(f"- {r['name']}  [{e.get('ref','')}]")
            print(f"    alt:    {e.get('url_old','')}")
            print(f"    aktuell:{' (Pfarrei)' if mapped else ' (Diözese)'} {cur}")
    print(f"\n{n} Belege. {unmapped} mit noch nicht gemappter Pfarrei.")
    if seen_parishes:
        print("Noch zu mappen (in matricula_parish_map.json eintragen):")
        for slug, dio in sorted(seen_parishes.items()):
            print(f'    "{slug}": "",   // {dio}')
    c.close()


def main(argv):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("dump");  d.add_argument("url")
    cr = sub.add_parser("crawl")
    cr.add_argument("url")
    cr.add_argument("--mode", choices=["up", "down", "both"], default="both",
                    help="up=Vorfahren, down=Nachkommen, both=erst auf- dann abwärts")
    cr.add_argument("--max", type=int, default=300,
                    help="Max. Seiten pro Lauf (Default 300, schonend)")
    cr.add_argument("--delay", type=float, default=4.0,
                    help="Mindestpause zw. Anfragen in s (Default 4.0 + Jitter)")
    cr.add_argument("--place", default="",
                    help="Nachkommen nur im Ort weiterverfolgen (Komma-Liste, "
                         "z.B. 'Osnabrück,Hagen,Oesede,Ostercappeln')")
    cr.add_argument("--year-min", type=int, default=0)
    cr.add_argument("--year-max", type=int, default=0)
    mr = sub.add_parser("matricula", help="Matricula-Belege + reparierte URLs ausgeben")
    args = ap.parse_args(argv[1:])

    if args.cmd == "dump":
        dump(args.url)
    elif args.cmd == "crawl":
        places = [s.strip() for s in args.place.split(",") if s.strip()]
        crawl(args.url, max_pages=args.max, delay=args.delay, mode=args.mode,
              place_filter=places, year_min=args.year_min, year_max=args.year_max)
    elif args.cmd == "matricula":
        matricula_report()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
