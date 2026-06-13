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

Gespeicherte Profile auflisten:

    python crawl_webtrees.py profiles

Alle bekannten Instanzen (lokale DBs) auflisten:

    python crawl_webtrees.py list-sites
"""
from __future__ import annotations
import re
import sys
import time
import json
import sqlite3
import argparse
import logging
import http.cookiejar
from urllib import request, parse
from urllib.error import HTTPError, URLError
from urllib.robotparser import RobotFileParser
from pathlib import Path

log = logging.getLogger(__name__)

USER_AGENT = "gedcom-analyzer-crawler/1.0 (personal genealogy research)"
SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH    = SCRIPT_DIR / "webtrees_crawl.db"   # legacy default (anverwandte)
PROFILES_FILE = SCRIPT_DIR / "webtrees_profiles.json"

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

# ── Fakten-Tabelle (wt-tab-facts) — die reichhaltigen Ereignisdaten ───────────
# Jede Tatsache ist eine <tr> mit <div class="wt-fact-label ut">TYP</div> und
# einer <td> mit Datum (<span class="date">), Ort (wt-fact-place > a),
# Religion/sonstigen Attributen (<span class="label">…</span>: …) sowie einer
# Notiz (oft Matricula-Quelle + Pate/Patin). Heirats-Zeilen verlinken Partner
# (/individual/…) und Familie (/family/…).
_FACT_LABEL_RE = re.compile(r'<div class="wt-fact-label[^"]*">(.*?)</div>', re.S)
_FACT_DATE_RE  = re.compile(r'<span class="date">(.*?)</span>', re.S)
_FACT_PLACE_RE = re.compile(r'wt-fact-place">\s*<a[^>]*>(.*?)</a>', re.S)
_FACT_VALUE_RE = re.compile(r'wt-fact-value">\s*<span class="ut">(.*?)</span>', re.S)
# generische Attribut-/Notiz-Paare: <span class="label">LABEL</span>: …</div>
_FACT_ATTR_RE  = re.compile(r'<span class="label">(.*?)</span>\s*:\s*(.*?)</div>', re.S)
_FACT_MATURL_RE = re.compile(r'href="(https?://data\.matricula-online\.eu/[^"]+)"')

# Deutsche webtrees-Fakten-Labels → GEDCOM-Tags
_LABEL_TO_TAG = {
    "geburt": "BIRT", "taufe": "BAPM", "tod": "DEAT",
    "begräbnis": "BURI", "beerdigung": "BURI", "bestattung": "BURI",
    "beisetzung": "BURI",
    "kirchliche trauung": "MARR", "standesamtliche trauung": "MARR",
    "trauung": "MARR", "heirat": "MARR", "eheschließung": "MARR",
    "verlobung": "ENGA", "aufgebot": "MARB",
    "beruf": "OCCU", "beschäftigung": "OCCU",
    "auswanderung": "EMIG", "emigration": "EMIG", "einwanderung": "IMMI",
    "wohnort": "RESI", "wohnsitz": "RESI", "aufenthalt": "RESI",
    "konfirmation": "CONF", "firmung": "CONF", "erstkommunion": "FCOM",
    "religion": "RELI", "staatsangehörigkeit": "NATI", "bildung": "EDUC",
    "titel": "TITL", "besitz": "PROP", "eigentum": "PROP",
}
# Labels, die wir nicht als Ereignis exportieren (Meta/Verwaltung)
_FACT_SKIP = {"letzte änderung", "letzter import", "geschlecht", "name", ""}


def _clean(html_fragment: str) -> str:
    txt = _TAG_RE.sub(" ", html_fragment or "")
    txt = re.sub(r"&nbsp;", " ", txt)
    txt = re.sub(r"&amp;", "&", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _host_to_slug(host: str) -> str:
    """Convert hostname to filesystem-safe slug: dots → underscores."""
    return host.replace(".", "_").replace("-", "_")


def _db_path_for_url(seed_url: str) -> Path:
    """Derive default DB path from seed URL host.

    Special case: stammbaum.anverwandte.info → webtrees_crawl.db (legacy name)
    for backward compatibility. All other hosts get webtrees_{slug}.db.
    """
    m = _BASE_RE.match(seed_url)
    if not m:
        return SCRIPT_DIR / "webtrees_crawl.db"
    host = parse.urlparse(m.group(1)).hostname or ""
    # Legacy alias: keep the old DB name for anverwandte
    if host == "stammbaum.anverwandte.info":
        legacy = SCRIPT_DIR / "webtrees_crawl.db"
        if legacy.exists():
            return legacy
    slug = _host_to_slug(host)
    return SCRIPT_DIR / f"webtrees_{slug}.db"


# ── Profile helpers ───────────────────────────────────────────────────────────

def _load_profiles() -> dict:
    if PROFILES_FILE.exists():
        try:
            return json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_profiles(profiles: dict):
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2, ensure_ascii=False),
                             encoding="utf-8")


# ── HTTP (höflich) ────────────────────────────────────────────────────────────

class Fetcher:
    def __init__(self, base: str, delay: float = 4.0,
                 auth: str | None = None,
                 cookies_path: str | None = None,
                 login_url: str | None = None,
                 login_user: str | None = None,
                 login_pass: str | None = None):
        """
        base         – scheme + host, e.g. "https://stammbaum.anverwandte.info"
        delay        – minimum seconds between requests
        auth         – "user:pass" for HTTP Basic Auth
        cookies_path – path to a cookie JSON file (Cookie Editor / Netscape format)
        login_url    – full URL for form-based login POST
        login_user   – username for form-based login
        login_pass   – password for form-based login
        """
        self.base = base
        self.delay = delay      # Mindestpause zwischen Anfragen (Sekunden)
        self._last = 0.0
        self._extra_headers: dict[str, str] = {}

        # HTTP Basic Auth
        if auth:
            import base64
            encoded = base64.b64encode(auth.encode()).decode()
            self._extra_headers["Authorization"] = f"Basic {encoded}"

        # Cookie jar (shared across requests for session persistence)
        self._cookie_jar = http.cookiejar.CookieJar()
        self._opener = request.build_opener(
            request.HTTPCookieProcessor(self._cookie_jar)
        )
        self._perm_fail: set[str] = set()  # URLs that returned 403/404/410

        # Load cookies from file (JSON from Cookie Editor or Netscape)
        if cookies_path:
            self._load_cookies(cookies_path)

        # Form-based login (must happen after cookie jar is set up)
        if login_url and login_user is not None and login_pass is not None:
            self._form_login(login_url, login_user, login_pass)

        self.robots = RobotFileParser()
        try:
            self.robots.set_url(base + "/robots.txt")
            self.robots.read()
        except Exception:
            self.robots = None  # kein robots.txt -> erlaubt

    def _load_cookies(self, cookies_path: str):
        """Load cookies from a JSON file (Cookie Editor export format) or
        attempt Netscape format via MozillaCookieJar."""
        p = Path(cookies_path)
        if not p.exists():
            log.warning("Cookie-Datei nicht gefunden: %s", cookies_path)
            return
        raw = p.read_text(encoding="utf-8").strip()
        # Try JSON format first (Cookie Editor exports a JSON array)
        if raw.startswith("[") or raw.startswith("{"):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    data = list(data.values())
                # Build a Cookie header string to inject into every request
                pairs = []
                for entry in data:
                    name = entry.get("name", "")
                    value = entry.get("value", "")
                    if name:
                        pairs.append(f"{name}={value}")
                if pairs:
                    self._extra_headers["Cookie"] = "; ".join(pairs)
                log.info("Cookies geladen (%d Stück) aus %s", len(pairs), cookies_path)
                return
            except json.JSONDecodeError:
                pass
        # Fallback: Netscape / Mozilla format
        try:
            jar = http.cookiejar.MozillaCookieJar(cookies_path)
            jar.load(ignore_discard=True, ignore_expires=True)
            for cookie in jar:
                self._cookie_jar.set_cookie(cookie)
            log.info("Netscape-Cookies geladen aus %s", cookies_path)
        except Exception as e:
            log.warning("Cookie-Datei konnte nicht gelesen werden: %s", e)

    def _form_login(self, login_url: str, username: str, password: str):
        """POST username/password to login_url (webtrees login form)."""
        data = parse.urlencode({
            "username": username,
            "password": password,
        }).encode()
        req = request.Request(login_url, data=data, method="POST", headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            **self._extra_headers,
        })
        try:
            with self._opener.open(req, timeout=25) as r:
                log.info("Login-POST an %s → HTTP %s", login_url, r.status)
        except Exception as e:
            log.warning("Form-Login fehlgeschlagen: %s", e)

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
                headers = {
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "de,en;q=0.8",
                    **self._extra_headers,
                }
                req = request.Request(url, headers=headers)
                with self._opener.open(req, timeout=timeout) as r:
                    self._last = time.time()
                    return r.read().decode("utf-8", errors="replace")
            except (HTTPError, URLError, TimeoutError) as e:
                last_err = e
                if isinstance(e, HTTPError) and e.code in (403, 404, 410):
                    self._perm_fail.add(url)
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


def parse_facts(html: str) -> list[dict]:
    """Zerlegt die Fakten-Tabelle (wt-tab-facts) in strukturierte Ereignisse.

    Jedes Ereignis: {tag, label, date, place, religion, note, value,
    matricula_url, spouse_id, family_id}. tag ist ein GEDCOM-Tag
    (BIRT/BAPM/MARR/DEAT/BURI/OCCU/EMIG/RESI/RELI/EVEN…). Heirats-Ereignisse
    tragen spouse_id/family_id, sodass MARR der richtigen Familie zugeordnet
    werden kann. Notizen enthalten oft Matricula-Quelle + Pate/Patin/Zeuge.
    """
    seg = html.split("wt-tab-facts", 1)
    if len(seg) < 2:
        return []
    seg = seg[1]
    end = seg.find("</table>")
    if end >= 0:
        seg = seg[:end]

    facts: list[dict] = []
    for raw in re.split(r'<tr class="', seg)[1:]:
        lm = _FACT_LABEL_RE.search(raw)
        if not lm:
            continue
        label = _clean(lm.group(1))
        key = label.lower().strip()
        if key in _FACT_SKIP:
            continue
        tag = _LABEL_TO_TAG.get(key, "EVEN")

        dm = _FACT_DATE_RE.search(raw)
        date = _clean(dm.group(1)) if dm else ""
        pm = _FACT_PLACE_RE.search(raw)
        place = _clean(pm.group(1)) if pm else ""
        vm = _FACT_VALUE_RE.search(raw)
        value = _clean(vm.group(1)) if vm else ""

        # Alle „Label: Wert"-Attribute der Tatsache sammeln (Religion, Zeugen,
        # Arbeitgeber, Adresse …) plus eine oder mehrere Notizen. Notizen tragen
        # oft die Matricula-Quelle und Paten/Zeugen-Angaben.
        attrs: dict[str, str] = {}
        notes: list[str] = []
        matricula_url = ""
        for alabel, aval in _FACT_ATTR_RE.findall(raw):
            al = _clean(alabel).lower()
            val = _clean(aval)
            if al.startswith("notiz") or al.startswith("note"):
                if val:
                    notes.append(val)
                if not matricula_url:
                    mu = _FACT_MATURL_RE.search(aval)
                    if mu:
                        matricula_url = mu.group(1)
            elif al and not al.startswith("autor"):
                attrs.setdefault(al, val)
        religion = attrs.get("religion", "")
        witnesses = (attrs.get("zeugen") or attrs.get("zeuge")
                     or attrs.get("paten") or attrs.get("pate")
                     or attrs.get("patin") or "")
        employer = attrs.get("arbeitgeber", "")
        address = attrs.get("adresse", "")
        note = "; ".join(notes)

        spouse_id = family_id = ""
        if tag in ("MARR", "ENGA", "MARB"):
            sm = re.search(r"/individual/([A-Z]+\d+)", raw)
            fm = re.search(r"/family/([A-Z]+\d+)", raw)
            spouse_id = sm.group(1) if sm else ""
            family_id = fm.group(1) if fm else ""

        facts.append({
            "tag": tag, "label": label, "date": date, "place": place,
            "value": value, "religion": religion, "note": note,
            "witnesses": witnesses, "employer": employer, "address": address,
            "matricula_url": matricula_url,
            "spouse_id": spouse_id, "family_id": family_id,
        })
    return facts


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

    # ── reichhaltige Ereignisse aus der Fakten-Tabelle ───────────────────
    facts = parse_facts(html)
    # Komfort-Felder (für GUI/Export) aus den Fakten ableiten
    occupation = next((f["value"] for f in facts
                       if f["tag"] == "OCCU" and f["value"]), "")
    religion = next((f["religion"] for f in facts if f.get("religion")), "")
    fact_notes = [f["note"] for f in facts if f.get("note")]
    # Geburt/Tod aus den Fakten ergänzen, falls der h2-Titel nichts lieferte
    for f in facts:
        if f["tag"] == "BIRT" and not birth_date:
            birth_date = f["date"]; birth_place = birth_place or f["place"]
        elif f["tag"] == "DEAT" and not death_date:
            death_date = f["date"]; death_place = death_place or f["place"]
    if not birth_year:
        birth_year = _yr(birth_date)
    if not death_year:
        death_year = _yr(death_date)

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
        "facts":       facts,
        "occupation":  occupation,
        "religion":    religion,
        "notes":       fact_notes,
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
        -- Speichert Seed-Person + Meta pro Crawl-Site (für Resume + Anzeige)
        CREATE TABLE IF NOT EXISTS wt_crawl_meta (
            tree_source TEXT PRIMARY KEY,
            seed_id     TEXT NOT NULL,
            seed_url    TEXT NOT NULL,
            base_url    TEXT,
            tree_name   TEXT,
            mode        TEXT DEFAULT 'both',
            started_at  TEXT,
            last_run    TEXT
        );
    """)
    c.commit()

    # Schema migration: add columns if missing (additiv, datenschonend)
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(wt_persons)")}
    for col in ("tree_source", "facts_json", "occupation", "religion", "notes_json"):
        if col not in existing_cols:
            c.execute(f"ALTER TABLE wt_persons ADD COLUMN {col} TEXT")
    c.commit()

    return c


def _save_person(c, p, ind_id, url, tree_source: str | None = None):
    c.execute("""INSERT OR REPLACE INTO wt_persons
        (id,url,name,given_name,surname,sex,birth_date,birth_place,
         birth_year,death_date,death_place,death_year,father_name,
         mother_name,spouse_names_json,child_names_json,matricula_json,
         parents_json,children_json,spouses_json,siblings_json,
         related_json,families_json,fetched_at,tree_source,
         facts_json,occupation,religion,notes_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?,
                ?,?,?,?)""",
        (p["id"] or ind_id, url, p["name"], p["given_name"], p["surname"],
         p["sex"], p["birth_date"], p["birth_place"], p["birth_year"],
         p["death_date"], p["death_place"], p["death_year"],
         p["father_name"], p["mother_name"],
         json.dumps(p["spouse_names"]), json.dumps(p["child_names"]),
         json.dumps(p["matricula"]),
         json.dumps(p["parents"]), json.dumps(p["children"]),
         json.dumps(p["spouses_ids"]), json.dumps(p["siblings"]),
         json.dumps(p["related"]), json.dumps(p["families"]),
         tree_source,
         json.dumps(p.get("facts") or []), p.get("occupation") or "",
         p.get("religion") or "", json.dumps(p.get("notes") or [])))


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
          db_path: Path = DB_PATH,
          auth: str | None = None,
          cookies: str | None = None,
          login_url: str | None = None,
          login_user: str | None = None,
          login_pass: str | None = None,
          tree_source: str | None = None,
          discover: bool = False,
          extra_seeds: list | None = None,
          reset_stale: bool = False):
    """mode:
        'up'   – nur Vorfahren (Eltern rückwärts)
        'down' – nur Nachkommen (Kinder vorwärts)
        'both' – erst alle Vorfahren, dann von ihnen alle Nachkommen
    place_filter: Liste von Ortsteilstrings (lowercase); year_min/max: Pruning
    der Nachkommen, damit der Crawl im gewünschten Raum/Zeitfenster bleibt.
    auth: "user:pass" for HTTP Basic Auth.
    cookies: path to cookie JSON file.
    login_url/login_user/login_pass: form-based login credentials.
    tree_source: "{host}/{tree}" label stored in wt_persons.tree_source column.
    discover: scan every stored related_json for unknown IDs and crawl them.
    extra_seeds: list of webtrees individual URLs to add as extra start points.
    reset_stale: re-fetch pages where child_names_json lists children but
                 children_json is empty (detects endogamy parse failures).
    """
    base = (_BASE_RE.match(seed_url) or [None, ""])[1]
    if not base:
        print("Ungültige Start-URL."); return
    tree_m = re.search(r"/tree/([^/]+)/individual/", seed_url)
    tree = tree_m.group(1) if tree_m else "anverwandte"
    place_filter = [s.lower() for s in (place_filter or [])]

    # Derive tree_source from seed URL if not explicitly provided
    if tree_source is None:
        parsed_host = parse.urlparse(base).hostname or ""
        tree_source = f"{parsed_host}/{tree}" if parsed_host else tree

    f = Fetcher(base, delay=delay,
                auth=auth,
                cookies_path=cookies,
                login_url=login_url,
                login_user=login_user,
                login_pass=login_pass)
    c = _db(db_path)
    seed_id = (_IND_RE.search(seed_url) or [None, ""])[1]

    print(f"tree_source : {tree_source}")
    print(f"Seed-ID     : {seed_id or '(aus URL nicht erkannt)'}")
    print(f"DB          : {db_path}")

    # Seed-Person + Meta persistieren (für Resume-Erkennung und Viewer-Verknüpfung)
    if seed_id:
        c.execute("""
            INSERT INTO wt_crawl_meta
                (tree_source, seed_id, seed_url, base_url, tree_name, mode,
                 started_at, last_run)
            VALUES (?,?,?,?,?,?,
                    COALESCE((SELECT started_at FROM wt_crawl_meta WHERE tree_source=?),
                             datetime('now')),
                    datetime('now'))
            ON CONFLICT(tree_source) DO UPDATE SET
                seed_id  = excluded.seed_id,
                seed_url = excluded.seed_url,
                mode     = excluded.mode,
                last_run = excluded.last_run
        """, (tree_source, seed_id, seed_url, base, tree, mode,
              tree_source))
        c.commit()

    # ── reset-stale: re-fetch pages where meta mentions children but none were stored
    if reset_stale:
        stale = c.execute(
            "SELECT id FROM wt_persons "
            "WHERE children_json='[]' "
            "AND child_names_json IS NOT NULL "
            "AND child_names_json NOT IN ('[]','null','')"
        ).fetchall()
        if stale:
            print(f"--reset-stale: {len(stale)} Seiten mit fehlenden Kinder-Daten werden neu geladen.")
            for (sid,) in stale:
                c.execute("DELETE FROM wt_persons WHERE id=?", (sid,))
                c.execute("UPDATE wt_frontier SET done=0 WHERE id=? AND direction='down'", (sid,))
            c.commit()
        else:
            print("--reset-stale: keine veralteten Einträge gefunden.")

    # ── extra-seeds: add specific person URLs to both frontier directions
    if extra_seeds:
        for eseed in extra_seeds:
            em = _IND_RE.search(eseed)
            if not em:
                print(f"  Warnung: Kein Individual-Link in '{eseed}' gefunden — übersprungen.")
                continue
            eid = em.group(1)
            # Force into frontier even if previously done
            c.execute("INSERT OR IGNORE INTO wt_frontier (id,direction,depth,done) "
                      "VALUES (?,'down',0,0)", (eid,))
            c.execute("UPDATE wt_frontier SET done=0 WHERE id=? AND direction='down'", (eid,))
            c.execute("INSERT OR IGNORE INTO wt_frontier (id,direction,depth,done) "
                      "VALUES (?,'up',0,0)", (eid,))
            c.execute("UPDATE wt_frontier SET done=0 WHERE id=? AND direction='up'", (eid,))
            # Remove from wt_persons so the page gets re-fetched fresh
            c.execute("DELETE FROM wt_persons WHERE id=?", (eid,))
            print(f"  Extra-Seed: {eid}")
        c.commit()

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
                if url in f._perm_fail:
                    # 403/404/410 — person not accessible, skip permanently
                    log.info("Person %s dauerhaft nicht erreichbar (HTTP 403/404) — überspringe", pid)
                    c.execute("UPDATE wt_frontier SET done=1 WHERE id=? AND direction=?",
                              (pid, direction))
                    c.commit()
                    return [], None
                return None, None   # Netzwerkfehler → nicht als erledigt markieren
            # Webtrees returns 200 for private/deleted persons with an error message
            if ("existiert nicht" in html or "keine Berechtigung" in html
                    or "does not exist" in html or "not authorised" in html):
                log.info("Person %s nicht sichtbar (gelöscht/privat) — überspringe", pid)
                c.execute("UPDATE wt_frontier SET done=1 WHERE id=? AND direction=?",
                          (pid, direction))
                c.commit()
                return [], None
            try:
                p = parse_individual(html, url)
                _save_person(c, p, pid, url, tree_source=tree_source)
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

    # ── Hilfsfunktion: eine Richtung crawlen bis die Frontier leer ist ──────────
    def _run_phase(direction: str, label: str, phase_label: str):
        crawl._open0 = None   # type: ignore[attr-defined]
        print(f"\n=== {phase_label}: {label} ===")
        processed = 0
        _phase_start = time.time()
        while max_pages == 0 or processed < max_pages:
            row = c.execute("SELECT id, depth FROM wt_frontier WHERE done=0 AND "
                            "direction=? ORDER BY depth LIMIT 1", (direction,)
                            ).fetchone()
            if not row:
                print(f"Frontier ({direction}) leer — Phase vollständig."); break
            pid, depth = row
            ids, pdata = neighbors(pid, direction)
            if ids is None:
                processed += 1
                continue
            c.execute("UPDATE wt_frontier SET done=1 WHERE id=? AND direction=?",
                      (pid, direction))
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
                elapsed = time.time() - _phase_start
                rate = processed / elapsed if elapsed > 0 else 0
                if not hasattr(crawl, "_ema_state"):
                    crawl._ema_state = {}  # type: ignore[attr-defined]
                _st = crawl._ema_state.setdefault(direction, {"prev_open": openf, "ema": 0.0})
                interval_growth = (openf - _st["prev_open"]) / 25.0
                alpha = 0.05
                _st["ema"] = alpha * interval_growth + (1 - alpha) * _st["ema"]
                _st["prev_open"] = openf
                gpg = _st["ema"]
                nd = 1.0 - gpg
                if nd > 0.05 and rate > 0:
                    eta_s = min((openf / nd) / rate, 999 * 3600)
                    eta_str = (f"{int(eta_s//3600)}h{int((eta_s%3600)//60)}m"
                               if eta_s > 60 else f"{int(eta_s)}s")
                elif nd <= 0:
                    eta_str = "wächst noch"
                else:
                    eta_str = ">99h"
                km = total + openf
                est = f"(~{int(km/(1-gpg))})" if 0 < gpg < 0.95 else ""
                print(f"  +{processed} | Personen: {total} | offen: {openf} "
                      f"| gesamt≥{km}{est} | {rate:.2f}/s | ETA ~{eta_str}")
        c.commit()
        if max_pages > 0 and processed >= max_pages:
            print(f"Seiten-Limit ({max_pages}) erreicht – erneut starten zum Fortsetzen.")

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
        _run_phase(direction, label, f"Phase {ph_idx+1}/{len(phases)}")

    # ── Entdeckungs-Schleife: related_json → convergence ─────────────────────
    # Jede geholte Seite speichert in related_json ALLE verlinkten Personen-IDs
    # (nicht nur Eltern/Kinder, sondern auch Cousins via Endogamie-Pfade).
    # Wir scannen diese Links wiederholt, bis keine neuen IDs mehr auftauchen.
    if discover:
        disc_round = 0
        while True:
            disc_round += 1
            known    = {r[0] for r in c.execute("SELECT id FROM wt_persons").fetchall()}
            queued   = {r[0] for r in c.execute(
                "SELECT id FROM wt_frontier WHERE direction='down'").fetchall()}
            new_ids: set[str] = set()
            for (rel_json,) in c.execute(
                "SELECT related_json FROM wt_persons "
                "WHERE related_json IS NOT NULL AND related_json != '[]'"
            ).fetchall():
                for rid in json.loads(rel_json or "[]"):
                    if rid not in known and rid not in queued:
                        c.execute("INSERT OR IGNORE INTO wt_frontier "
                                  "(id,direction,depth,done) VALUES (?,'down',0,0)", (rid,))
                        queued.add(rid)
                        new_ids.add(rid)
            c.commit()
            if not new_ids:
                total = c.execute("SELECT COUNT(*) FROM wt_persons").fetchone()[0]
                print(f"\nEntdeckung abgeschlossen nach {disc_round} Runde(n). "
                      f"Personen gesamt: {total}.")
                break
            print(f"\n=== Entdeckungs-Runde {disc_round}: "
                  f"{len(new_ids)} neue IDs aus verlinkten Seiten ===")
            _run_phase("down", "Nachkommen ⬇ (Entdeckung)", f"Runde {disc_round}")

    # ── Restlicher Code (Phasen-Loop war hier, jetzt in _run_phase) ──────────
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


def training_run(seed_url: str, n_pages: int = 100, delay: float = 4.0,
                 out_dir: str | Path | None = None,
                 auth: str | None = None,
                 cookies: str | None = None,
                 login_url: str | None = None,
                 login_user: str | None = None,
                 login_pass: str | None = None) -> Path | None:
    """Stichprobe echter webtrees-Seiten als Roh-HTML sammeln (Parser eichen).

    Anders als `crawl` schreibt dieser Lauf NICHTS in die Datenbank. Er folgt
    ab der Start-Person den Verwandtschafts-Links (Breitensuche) und legt für
    jede besuchte Person zwei Dateien ab:

      <id>.html   – das unveränderte Roh-HTML der Seite
      <id>.json   – was der aktuelle Parser daraus macht

    Dazu ein _manifest.json mit Übersicht. Der ganze Ordner kann gezippt und
    zur Parser-Verbesserung zurückgegeben werden: die HTML-Dateien sind echte
    Eingaben, die JSON-Dateien zeigen, wo der Parser heute noch danebenliegt.

    Schonend wie der Crawler: robots.txt + Rate-Limit (delay + Jitter) gelten.

    Rückgabe: Pfad zum Ausgabeordner (oder None bei Fehler).
    """
    from collections import deque

    base = (_BASE_RE.match(seed_url) or [None, ""])[1]
    if not base:
        print("Ungültige Start-URL."); return None
    tree_m = re.search(r"/tree/([^/]+)/individual/", seed_url)
    tree = tree_m.group(1) if tree_m else "anverwandte"
    seed_id = (_IND_RE.search(seed_url) or [None, ""])[1]
    if not seed_id:
        print("Seed-ID aus URL nicht erkannt — bitte volle Individual-URL angeben.")
        return None

    host = parse.urlparse(base).hostname or "webtrees"
    if out_dir is None:
        out_dir = SCRIPT_DIR / "webtrees_training" / _host_to_slug(host)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    f = Fetcher(base, delay=delay, auth=auth, cookies_path=cookies,
                login_url=login_url, login_user=login_user, login_pass=login_pass)

    print(f"Trainings-Stichprobe: bis zu {n_pages} Seiten")
    print(f"Start-ID  : {seed_id}")
    print(f"Zielordner: {out_dir}")

    q: "deque[str]" = deque([seed_id])
    seen: set[str] = {seed_id}
    manifest: list[dict] = []
    saved = skipped = 0

    while q and saved < n_pages:
        pid = q.popleft()
        url = f"{base}/tree/{tree}/individual/{pid}"
        html = f.get(url)
        if not html:
            skipped += 1
            print(f"  ⚠ {pid}: keine Antwort (übersprungen)")
            continue

        # Roh-HTML immer sichern — auch private/gelöschte Seiten sind für die
        # Parser-Eichung wertvoll (zeigen, wie webtrees Fehlerfälle ausliefert).
        (out_dir / f"{pid}.html").write_text(html, encoding="utf-8")
        try:
            p = parse_individual(html, url)
            parse_error = ""
        except Exception as exc:           # noqa: BLE001 — als Befund sichern
            p = {"id": pid, "url": url}
            parse_error = str(exc)
        (out_dir / f"{pid}.json").write_text(
            json.dumps({**p, "_parse_error": parse_error} if parse_error else p,
                       indent=2, ensure_ascii=False),
            encoding="utf-8")

        saved += 1
        manifest.append({
            "id": pid, "url": url,
            "name": p.get("name", ""),
            "html_bytes": len(html),
            "parse_error": parse_error,
        })
        flag = " ⚠PARSE-FEHLER" if parse_error else ""
        print(f"  [{saved}/{n_pages}] {pid}  {p.get('name', '')[:42]}{flag}")

        # Nachbarn einreihen: erst die nahe Familie (repräsentativ + verbunden),
        # dann weiter verlinkte Personen als Auffüllung für mehr Seiten-Varianz.
        near = (p.get("parents", []) + p.get("children", [])
                + p.get("spouses_ids", []) + p.get("siblings", []))
        for nid in near + p.get("related", []):
            if nid and nid not in seen:
                seen.add(nid)
                q.append(nid)

    (out_dir / "_manifest.json").write_text(
        json.dumps({
            "seed_url": seed_url, "host": host, "tree": tree,
            "requested": n_pages, "saved": saved, "skipped": skipped,
            "parse_errors": sum(1 for m in manifest if m["parse_error"]),
            "pages": manifest,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8")

    errs = sum(1 for m in manifest if m["parse_error"])
    print(f"\nFertig: {saved} Seiten gespeichert"
          + (f", {skipped} übersprungen" if skipped else "")
          + (f", {errs} mit Parser-Fehler" if errs else ""))
    print(f"Ordner   : {out_dir}")
    print(f"Manifest : {out_dir / '_manifest.json'}")
    print("→ Diesen Ordner zippen und zur Parser-Verbesserung zurückgeben.")
    return out_dir


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


# ── list-sites subcommand ─────────────────────────────────────────────────────

def list_sites():
    """Scan all webtrees_*.db files in the script directory and print a summary."""
    dbs = list(SCRIPT_DIR.glob("webtrees_*.db"))
    # Also include legacy webtrees_crawl.db
    legacy = SCRIPT_DIR / "webtrees_crawl.db"
    if legacy.exists() and legacy not in dbs:
        dbs.append(legacy)
    if not dbs:
        print("Keine webtrees-Datenbanken gefunden in:", SCRIPT_DIR)
        return
    print(f"{'DB':<38} {'Personen':>9} {'Seed-ID':<14} {'Offen':>6}  {'Letzter Lauf'}")
    print("-" * 90)
    for db_file in sorted(dbs):
        try:
            conn = sqlite3.connect(str(db_file))
            person_count = conn.execute("SELECT COUNT(*) FROM wt_persons").fetchone()[0]
            open_frontier = conn.execute(
                "SELECT COUNT(*) FROM wt_frontier WHERE done=0").fetchone()[0]
            try:
                meta = conn.execute(
                    "SELECT seed_id, last_run FROM wt_crawl_meta ORDER BY last_run DESC LIMIT 1"
                ).fetchone()
                seed_id  = meta[0] if meta else "—"
                last_run = (meta[1] or "—")[:19] if meta else "—"
            except Exception:
                seed_id = last_run = "—"
            conn.close()
            print(f"{db_file.name:<38} {person_count:>9} {seed_id:<14} {open_frontier:>6}  {last_run}")
        except Exception:
            print(f"{db_file.name:<38} {'—':>9} {'—':<14} {'—':>6}  (noch leer / kein crawl)")


# ── profiles subcommand ───────────────────────────────────────────────────────

def list_profiles():
    """List all saved profiles from webtrees_profiles.json."""
    profiles = _load_profiles()
    if not profiles:
        print("Keine gespeicherten Profile gefunden.")
        print(f"Profile-Datei: {PROFILES_FILE}")
        return
    for name, cfg in profiles.items():
        print(f"\n[{name}]")
        for k, v in cfg.items():
            print(f"  {k}: {v}")


# ── GEDCOM-Export ─────────────────────────────────────────────────────────────

def _ged_name(p: dict) -> str:
    """'Vorname /Nachname/' aus given_name/surname, Fallback = name-Feld."""
    given = (p.get("given_name") or "").strip()
    surn  = (p.get("surname") or "").strip()
    if given or surn:
        return f"{given} /{surn}/".strip()
    raw = (p.get("name") or "").strip()
    if not raw:
        return "Unbekannt"
    # Steht im name-Feld schon ein /Nachname/? Dann unverändert lassen.
    if "/" in raw:
        return raw
    parts = raw.split()
    if len(parts) == 1:
        return f"/{parts[0]}/"
    return f"{' '.join(parts[:-1])} /{parts[-1]}/"


def _ged_event(tag: str, date: str, place: str) -> list[str]:
    lines = [f"1 {tag}"]
    if date:
        lines.append(f"2 DATE {date}")
    if place:
        lines.append(f"2 PLAC {place}")
    return lines if len(lines) > 1 else []


def _fact_lines(f: dict, level: int, map_place) -> list[str]:
    """Eine Tatsache (aus parse_facts) als GEDCOM-Ereigniszeilen.

    level = Ereignisebene (1 für Personen-Events, 1 für FAM-MARR). Datum/Ort,
    Matricula als Quelle (@S2@) am Ereignis, Notiz (Pate/Patin/Zeuge) als NOTE.
    Religion wird als NOTE mitgeführt (RELI ist in GEDCOM keine Ereignis-
    Untertatsache). OCCU/RELI tragen ihren Wert direkt am Tag.
    """
    tag = f.get("tag") or "EVEN"
    val = (f.get("value") or "").strip()
    sub = level + 1
    if tag == "OCCU":
        head = f"{level} OCCU {val[:90]}" if val else f"{level} OCCU"
        lines = [head]
    elif tag == "RELI":
        lines = [f"{level} RELI {val[:90]}" if val else f"{level} RELI"]
    elif tag == "EVEN":
        lines = [f"{level} EVEN", f"{sub} TYPE {f.get('label','')[:90]}"]
    else:
        lines = [f"{level} {tag}"]
    date = (f.get("date") or "").strip()
    if date:
        lines.append(f"{sub} DATE {date}")
    place = (f.get("place") or "").strip()
    if place:
        lines.append(f"{sub} PLAC {map_place(place)}")
    note = (f.get("note") or "").strip()
    mat_url = (f.get("matricula_url") or "").strip()
    if mat_url or "matricula" in note.lower():
        page = note or mat_url
        if mat_url and mat_url not in page:
            page = f"{page} {mat_url}".strip()
        lines += [f"{sub} SOUR @S2@", f"{sub+1} PAGE {page[:240]}"]
    # Notiz (Pate/Patin/Zeuge/Religion/Arbeitgeber/Adresse) erhalten —
    # FTM zeigt NOTEs zuverlässig und sie überleben das Verschmelzen.
    note_bits = []
    if f.get("religion"):
        note_bits.append(f"Religion: {f['religion']}")
    if f.get("witnesses"):
        note_bits.append(f"Zeugen: {f['witnesses']}")
    if f.get("employer"):
        note_bits.append(f"Arbeitgeber: {f['employer']}")
    if f.get("address"):
        note_bits.append(f"Adresse: {f['address']}")
    if note:
        note_bits.append(note)
    if note_bits:
        lines.append(f"{sub} NOTE {'; '.join(note_bits)[:255]}")
    return lines


def export_gedcom(db_path: Path, out_path: str,
                  tree_source: str | None = None) -> tuple[int, int]:
    """Schreibt die in `db_path` gecrawlten Personen als GEDCOM-5.5.1-Datei.

    Baut FAM-Records aus parents_json/spouses_json. Es werden NUR Personen
    referenziert, die auch tatsächlich gecrawlt wurden (keine offenen Refs).
    Orte werden – falls eine Ortskonkordanz hinterlegt ist – auf die Standard-
    namen abgebildet; der Anverwandte-Link wird je Person ausgegeben.
    Rückgabe: (anzahl_personen, anzahl_familien).
    """
    try:
        from ancestry.core.place_concordance import map_place as _map_place
    except Exception:
        def _map_place(x):
            return x
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Datenbank nicht gefunden: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM wt_persons"
    params: tuple = ()
    if tree_source:
        q += " WHERE tree_source = ?"
        params = (tree_source,)
    rows = conn.execute(q, params).fetchall()
    conn.close()

    persons = {r["id"]: dict(r) for r in rows if r["id"]}
    if not persons:
        raise ValueError("Keine Personen in der Datenbank (erst crawlen).")

    def _ids(p: dict, col: str) -> list[str]:
        try:
            vals = json.loads(p.get(col) or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
        # Nur gecrawlte IDs → keine offenen GEDCOM-Referenzen
        return [v for v in vals if v in persons]

    # ── Familien aus Eltern-/Partner-Verknüpfungen ableiten ──────────────
    families: dict[str, dict] = {}
    parentset_to_fam: dict[frozenset, str] = {}
    seq = 0

    def family_for(parent_ids: list[str]) -> str:
        nonlocal seq
        key = frozenset(parent_ids)
        if key in parentset_to_fam:
            return parentset_to_fam[key]
        seq += 1
        fid = f"F{seq}"
        fam = {"husb": None, "wife": None, "chil": set()}
        for pid in parent_ids:
            sex = persons[pid].get("sex")
            if sex == "M" and not fam["husb"]:
                fam["husb"] = pid
            elif sex == "F" and not fam["wife"]:
                fam["wife"] = pid
            elif not fam["husb"]:
                fam["husb"] = pid
            elif not fam["wife"]:
                fam["wife"] = pid
        families[fid] = fam
        parentset_to_fam[key] = fid
        return fid

    # 1. Kind → Elternfamilie
    for pid, p in persons.items():
        par = _ids(p, "parents_json")
        if par:
            families[family_for(par)]["chil"].add(pid)

    # 2. Paare ohne (gecrawlte) Kinder trotzdem als Familie führen
    for pid, p in persons.items():
        for sp in _ids(p, "spouses_json"):
            family_for([pid, sp])

    # FAMC/FAMS-Zuordnung
    from collections import defaultdict as _dd
    famc: dict[str, list[str]] = _dd(list)
    fams: dict[str, list[str]] = _dd(list)
    for fid, fam in families.items():
        if fam["husb"]:
            fams[fam["husb"]].append(fid)
        if fam["wife"]:
            fams[fam["wife"]].append(fid)
        for ch in fam["chil"]:
            famc[ch].append(fid)

    def _facts(p: dict) -> list[dict]:
        try:
            fl = json.loads(p.get("facts_json") or "[]")
            return fl if isinstance(fl, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    # ── Heirats-Ereignisse → richtiger Familie zuordnen ──────────────────
    # Schlüssel = frozenset({partner_a, partner_b}); so findet jede generierte
    # FAM (über husb/wife) ihr MARR mit Datum/Ort/Quelle/Notiz wieder.
    marr_by_pair: dict[frozenset, dict] = {}
    for pid, p in persons.items():
        for f in _facts(p):
            if f.get("tag") != "MARR":
                continue
            sp = f.get("spouse_id")
            if not sp:
                continue
            key = frozenset((pid, sp))
            # bevorzugt den Eintrag mit Datum (beide Partner tragen das Faktum)
            if key not in marr_by_pair or (f.get("date") and not marr_by_pair[key].get("date")):
                marr_by_pair[key] = f

    # ── Schreiben ────────────────────────────────────────────────────────
    out: list[str] = [
        "0 HEAD",
        "1 SOUR gedcom-analyzer-crawler",
        "2 VERS 1.0",
        "2 NAME webtrees-Crawler (crawl_webtrees.py)",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "1 LANG German",
    ]

    for pid, p in sorted(persons.items()):
        out.append(f"0 @{pid}@ INDI")
        out.append(f"1 NAME {_ged_name(p)}")
        sex = p.get("sex")
        if sex in ("M", "F"):
            out.append(f"1 SEX {sex}")
        # ── Lebensereignisse ──────────────────────────────────────────────
        person_sour: list[str] = []
        facts = _facts(p)
        if facts:
            # Reichhaltiger Pfad: jede (Nicht-Heirats-)Tatsache als Ereignis,
            # inkl. Taufe/Begräbnis/Beruf, Matricula-Quelle + Pate/Patin/Zeuge.
            # Sicherstellen, dass es eine BIRT/DEAT gibt (aus Skalar-Feldern),
            # falls die Fakten-Tabelle sie nicht enthielt.
            have = {f.get("tag") for f in facts}
            for f in facts:
                if f.get("tag") == "MARR":
                    continue            # MARR kommt in den FAM-Record
                out.extend(_fact_lines(f, 1, _map_place))
            if "BIRT" not in have and (p.get("birth_date") or p.get("birth_year")):
                out.extend(_ged_event("BIRT", p.get("birth_date") or p.get("birth_year"),
                                      _map_place(p.get("birth_place") or "")))
            if "DEAT" not in have and (p.get("death_date") or p.get("death_year")):
                out.extend(_ged_event("DEAT", p.get("death_date") or p.get("death_year"),
                                      _map_place(p.get("death_place") or "")))
        else:
            # Fallback (Altdaten ohne Fakten): Matricula-Belege heuristisch routen
            try:
                mat = json.loads(p.get("matricula_json") or "[]")
            except (json.JSONDecodeError, TypeError):
                mat = []

            def _mat_page(m):
                ref = (m.get("ref") or "").strip() if isinstance(m, dict) else str(m).strip()
                url = (m.get("url_old") or "").strip() if isinstance(m, dict) else ""
                return " ".join(x for x in (ref, url) if x).strip()[:240]

            def _mat_type(m):
                r = ((m.get("ref") or "") if isinstance(m, dict) else str(m)).lower()
                if any(k in r for k in ("heirat", "trau", "ehe", "copul")):
                    return "marr"
                if any(k in r for k in ("tod", "sterb", "begräb", "beerd", "todes")):
                    return "deat"
                return "birt"

            birt = _ged_event("BIRT", p.get("birth_date") or p.get("birth_year") or "",
                              _map_place(p.get("birth_place") or ""))
            deat = _ged_event("DEAT", p.get("death_date") or p.get("death_year") or "",
                              _map_place(p.get("death_place") or ""))
            for m in mat:
                page = _mat_page(m)
                if not page:
                    continue
                t = _mat_type(m)
                if t == "birt" and birt:
                    birt += ["2 SOUR @S2@", f"3 PAGE {page}"]
                elif t == "deat" and deat:
                    deat += ["2 SOUR @S2@", f"3 PAGE {page}"]
                else:
                    person_sour += ["1 SOUR @S2@", f"2 PAGE {page}"]
            out.extend(birt)
            out.extend(deat)

            if p.get("occupation"):
                out.append(f"1 OCCU {str(p['occupation'])[:90]}")
            _notes = p.get("notes")
            for nt in (_notes if isinstance(_notes, list) else ([_notes] if _notes else [])):
                if str(nt).strip():
                    out.append(f"1 NOTE {str(nt).strip()[:240]}")

        for fid in famc.get(pid, []):
            out.append(f"1 FAMC @{fid}@")
        for fid in fams.get(pid, []):
            out.append(f"1 FAMS @{fid}@")
        out.extend(person_sour)

        if p.get("url"):
            out.append("1 SOUR @S1@")
            out.append(f"2 PAGE {p['url']}")
            # Link zusätzlich als NOTE — FTM übernimmt das zuverlässig und es
            # bleibt beim Verschmelzen der Dublette erhalten.
            out.append(f"1 NOTE Anverwandte: {p['url']}")

    for fid, fam in sorted(families.items(), key=lambda kv: int(kv[0][1:])):
        out.append(f"0 @{fid}@ FAM")
        if fam["husb"]:
            out.append(f"1 HUSB @{fam['husb']}@")
        if fam["wife"]:
            out.append(f"1 WIFE @{fam['wife']}@")
        for ch in sorted(fam["chil"]):
            out.append(f"1 CHIL @{ch}@")
        # Heirat (Datum/Ort/Quelle/Notiz) aus den Fakten der Partner
        if fam["husb"] and fam["wife"]:
            mf = marr_by_pair.get(frozenset((fam["husb"], fam["wife"])))
            if mf:
                out.extend(_fact_lines(mf, 1, _map_place))

    out += [
        "0 @S1@ SOUR",
        "1 TITL Webtrees-Stammbaum (gecrawlt)",
        "1 AUTH crawl_webtrees.py",
        "0 @S2@ SOUR",
        "1 TITL Matricula-Kirchenbücher",
        "1 AUTH data.matricula-online.eu",
    ]
    out.append("0 TRLR")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print(f"GEDCOM gespeichert: {out_path}")
    print(f"  {len(persons)} Personen, {len(families)} Familien")
    return len(persons), len(families)


def main(argv):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")

    d = sub.add_parser("dump");  d.add_argument("url")

    cr = sub.add_parser("crawl")
    cr.add_argument("url", nargs="?", default=None,
                    help="Seed-URL der Start-Person (kann auch im Profil stehen)")
    cr.add_argument("--mode", choices=["up", "down", "both"], default=None,
                    help="up=Vorfahren, down=Nachkommen, both=erst auf- dann abwärts")
    cr.add_argument("--max", type=int, default=None,
                    help="Max. Seiten pro Lauf (Default 300, schonend)")
    cr.add_argument("--delay", type=float, default=None,
                    help="Mindestpause zw. Anfragen in s (Default 4.0 + Jitter)")
    cr.add_argument("--place", default=None,
                    help="Nachkommen nur im Ort weiterverfolgen (Komma-Liste, "
                         "z.B. 'Osnabrück,Hagen,Oesede,Ostercappeln')")
    cr.add_argument("--year-min", type=int, default=None)
    cr.add_argument("--year-max", type=int, default=None)
    cr.add_argument("--db", default=None,
                    help="Pfad zur SQLite-DB (überschreibt den automatischen Namen)")
    cr.add_argument("--auth", default=None,
                    help="HTTP Basic Auth als 'user:pass'")
    cr.add_argument("--cookies", default=None,
                    help="Pfad zu einer Cookie-JSON-Datei (Cookie Editor Format)")
    cr.add_argument("--login-url", default=None,
                    help="URL des webtrees-Login-Formulars für form-based Login")
    cr.add_argument("--login-user", default=None,
                    help="Benutzername für form-based Login")
    cr.add_argument("--login-pass", default=None,
                    help="Passwort für form-based Login")
    cr.add_argument("--profile", default=None,
                    help="Gespeichertes Profil laden (CLI-Args überschreiben)")
    cr.add_argument("--save-profile", default=None, metavar="NAME",
                    help="Aktuelle CLI-Args als Profil speichern")
    cr.add_argument("--discover", action="store_true", default=False,
                    help="Nach regulären Phasen: related_json aller Seiten nach "
                         "unbekannten Personen scannen und nachladen (findet via "
                         "Endogamie verbundene Vettern die keine Vorfahren/Kinder sind)")
    cr.add_argument("--extra-seeds", nargs="+", metavar="URL", default=None,
                    help="Webtrees-Individual-URLs gezielt hinzufügen (z.B. bekannte "
                         "Vettern die vom Hauptcrawl übersprungen wurden)")
    cr.add_argument("--reset-stale", action="store_true", default=False,
                    help="Seiten neu laden, bei denen child_names_json Kinder nennt "
                         "aber children_json leer ist (behebt Parsing-Fehler)")

    tr = sub.add_parser("training",
                        help="Stichprobe echter Seiten als HTML+JSON sichern "
                             "(zum Eichen/Verbessern des Parsers)")
    tr.add_argument("url", nargs="?", default=None,
                    help="Seed-URL der Start-Person (kann auch im Profil stehen)")
    tr.add_argument("--profile", default=None,
                    help="Gespeichertes Profil laden (für Seed-URL/Login/Delay)")
    tr.add_argument("--n", type=int, default=100,
                    help="Anzahl Seiten (Default 100)")
    tr.add_argument("--delay", type=float, default=None,
                    help="Mindestpause zw. Anfragen in s (Default aus Profil/4.0)")
    tr.add_argument("--out", default=None,
                    help="Zielordner (Default: tools/webtrees_training/<host>/)")
    tr.add_argument("--auth", default=None, help="HTTP Basic Auth als 'user:pass'")
    tr.add_argument("--cookies", default=None, help="Pfad zu einer Cookie-JSON-Datei")
    tr.add_argument("--login-url", default=None, help="webtrees-Login-Formular-URL")
    tr.add_argument("--login-user", default=None, help="Benutzername für Login")
    tr.add_argument("--login-pass", default=None, help="Passwort für Login")

    sub.add_parser("matricula", help="Matricula-Belege + reparierte URLs ausgeben")
    sub.add_parser("profiles", help="Alle gespeicherten Profile auflisten")
    sub.add_parser("list-sites", help="Alle lokalen webtrees-DBs auflisten")

    ge = sub.add_parser("export-gedcom",
                        help="Gecrawlte Personen als GEDCOM-Datei (.ged) exportieren")
    ge.add_argument("--out", default=None,
                    help="Ausgabedatei (.ged); Default: <db-name>.ged")
    ge.add_argument("--db", default=None,
                    help="Pfad zur SQLite-DB (sonst über --profile oder Default)")
    ge.add_argument("--profile", default=None,
                    help="Profil-DB verwenden (z.B. anverwandte)")
    ge.add_argument("--tree-source", default=None,
                    help="Nur Personen dieser tree_source exportieren")

    args = ap.parse_args(argv[1:])

    if args.cmd == "dump":
        dump(args.url)

    elif args.cmd == "crawl":
        # Start with defaults
        cfg = {
            "seed_url":   None,
            "mode":       "both",
            "max":        300,
            "delay":      4.0,
            "place":      "",
            "year_min":   0,
            "year_max":   0,
            "db":         None,
            "auth":       None,
            "cookies":    None,
            "login_url":  None,
            "login_user": None,
            "login_pass": None,
        }

        # Load profile if requested
        if args.profile:
            profiles = _load_profiles()
            if args.profile not in profiles:
                print(f"Profil '{args.profile}' nicht gefunden. Verfügbar: "
                      f"{list(profiles.keys())}")
                sys.exit(1)
            prof = profiles[args.profile]
            # Profile key "seed_url" maps to positional url
            if "seed_url" in prof:
                cfg["seed_url"] = prof["seed_url"]
            for k in ("mode", "max", "delay", "place", "year_min", "year_max",
                      "db", "auth", "cookies", "login_url", "login_user", "login_pass"):
                if k in prof and prof[k] is not None:
                    cfg[k] = prof[k]
            # Backward compat: anverwandte profile uses webtrees_crawl.db
            if args.profile == "anverwandte" and cfg.get("db") is None:
                legacy = SCRIPT_DIR / "webtrees_crawl.db"
                if legacy.exists():
                    cfg["db"] = str(legacy)

        # CLI args override profile (only if explicitly provided)
        if args.url is not None:
            cfg["seed_url"] = args.url
        if args.mode is not None:
            cfg["mode"] = args.mode
        if args.max is not None:
            cfg["max"] = args.max
        if args.delay is not None:
            cfg["delay"] = args.delay
        if args.place is not None:
            cfg["place"] = args.place
        if args.year_min is not None:
            cfg["year_min"] = args.year_min
        if args.year_max is not None:
            cfg["year_max"] = args.year_max
        if args.db is not None:
            cfg["db"] = args.db
        if args.auth is not None:
            cfg["auth"] = args.auth
        if args.cookies is not None:
            cfg["cookies"] = args.cookies
        if args.login_url is not None:
            cfg["login_url"] = args.login_url
        if args.login_user is not None:
            cfg["login_user"] = args.login_user
        if args.login_pass is not None:
            cfg["login_pass"] = args.login_pass

        if not cfg["seed_url"]:
            print("Fehler: Seed-URL fehlt (als Argument oder im Profil angeben).")
            sys.exit(1)

        # Resolve DB path
        if cfg["db"]:
            db_path = Path(cfg["db"])
        else:
            db_path = _db_path_for_url(cfg["seed_url"])

        # Save profile if requested
        if args.save_profile:
            profiles = _load_profiles()
            profiles[args.save_profile] = {
                "seed_url":   cfg["seed_url"],
                "mode":       cfg["mode"],
                "delay":      cfg["delay"],
                "max":        cfg["max"],
                "place":      cfg["place"],
                "year_min":   cfg["year_min"],
                "year_max":   cfg["year_max"],
                "db":         str(db_path),
                "auth":       cfg["auth"],
                "cookies":    cfg["cookies"],
                "login_url":  cfg["login_url"],
                "login_user": cfg["login_user"],
                "login_pass": cfg["login_pass"],
            }
            _save_profiles(profiles)
            print(f"Profil '{args.save_profile}' gespeichert in {PROFILES_FILE}")

        places = [s.strip() for s in (cfg["place"] or "").split(",") if s.strip()]
        crawl(cfg["seed_url"],
              max_pages=cfg["max"],
              delay=cfg["delay"],
              mode=cfg["mode"],
              place_filter=places,
              year_min=cfg["year_min"],
              year_max=cfg["year_max"],
              db_path=db_path,
              auth=cfg["auth"],
              cookies=cfg["cookies"],
              login_url=cfg["login_url"],
              login_user=cfg["login_user"],
              login_pass=cfg["login_pass"],
              discover=args.discover,
              extra_seeds=args.extra_seeds,
              reset_stale=args.reset_stale)

    elif args.cmd == "training":
        # Seed-URL/Login/Delay primär aus dem Profil, CLI-Args überschreiben.
        seed_url = args.url
        delay = args.delay if args.delay is not None else 4.0
        auth, cookies = args.auth, args.cookies
        login_url, login_user, login_pass = (
            args.login_url, args.login_user, args.login_pass)
        if args.profile:
            profiles = _load_profiles()
            if args.profile not in profiles:
                print(f"Profil '{args.profile}' nicht gefunden. Verfügbar: "
                      f"{list(profiles.keys())}")
                sys.exit(1)
            prof = profiles[args.profile]
            seed_url = seed_url or prof.get("seed_url")
            if args.delay is None and prof.get("delay") is not None:
                delay = prof["delay"]
            auth = auth or prof.get("auth")
            cookies = cookies or prof.get("cookies")
            login_url = login_url or prof.get("login_url")
            login_user = login_user or prof.get("login_user")
            login_pass = login_pass or prof.get("login_pass")
        if not seed_url:
            print("Fehler: Seed-URL fehlt (als Argument oder via --profile).")
            sys.exit(1)
        training_run(seed_url, n_pages=args.n, delay=delay, out_dir=args.out,
                     auth=auth, cookies=cookies, login_url=login_url,
                     login_user=login_user, login_pass=login_pass)

    elif args.cmd == "export-gedcom":
        # DB-Pfad bestimmen: --db > --profile > Default
        db_path = None
        if args.db:
            db_path = Path(args.db)
        elif args.profile:
            profiles = _load_profiles()
            prof = profiles.get(args.profile)
            if not prof:
                print(f"Profil '{args.profile}' nicht gefunden. Verfügbar: "
                      f"{list(profiles.keys())}")
                sys.exit(1)
            if prof.get("db"):
                db_path = Path(prof["db"])
            elif prof.get("seed_url"):
                db_path = _db_path_for_url(prof["seed_url"])
            if args.profile == "anverwandte" and (db_path is None or not db_path.exists()):
                legacy = SCRIPT_DIR / "webtrees_crawl.db"
                if legacy.exists():
                    db_path = legacy
        if db_path is None:
            db_path = DB_PATH
        out_path = args.out or str(Path(db_path).with_suffix(".ged"))
        try:
            export_gedcom(db_path, out_path, tree_source=args.tree_source)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Fehler: {exc}")
            sys.exit(1)

    elif args.cmd == "matricula":
        matricula_report()

    elif args.cmd == "profiles":
        list_profiles()

    elif args.cmd == "list-sites":
        list_sites()

    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
