# -*- coding: utf-8 -*-
"""
tasks/dfd_lookup.py — Digitales Familiennamenwörterbuch Deutschlands (DFD).

https://www.namenforschung.net/dfd/woerterbuch/liste/

Das DFD (Mainzer Akademie, Laufzeit 2012–2035) enthält wissenschaftliche
Artikel zu deutschen Familiennamen mit:
  • Häufigkeit & Rang (Telekom-Basis 2005, ~45 Mio. Anschlüsse)
  • Etymologie (Sprachstufe, Grundwort, Motivklasse)
  • Verbreitung (Karte + Textbeschreibung)
  • Laut-/Schreibvarianten
  • Historische Belege (älteste Erwähnungen)
  • Namentyp (Berufsname, Wohnstättenname, Patronym …)

Technisches Backend:
  TYPO3 CMS → Extension-Controller "Names" → eXist XML-DB
  URL-Muster: ?tx_dfd_names[query]=<NAME>&tx_dfd_names[action]=list
              ?tx_dfd_names[name]=<ID>&tx_dfd_names[action]=show&cHash=<HASH>

Strategie dieses Moduls
  1. Für jeden eindeutigen Nachnamen im GEDCOM → DFD-Such-URL (immer)
  2. Optional: HTML-Abruf mit Browser-Headers → Artikel parsen
       • Schritt A: Suchliste laden → Artikel-URL (mit cHash) extrahieren
       • Schritt B: Artikel laden → Häufigkeit, Typ, Etymologie, Varianten
     Scheitert der Abruf (403 aus Cloud-Umgebung), bleibt die URL stehen.
  3. Varianten fließen in den Phonetik-Vergleich der Namen-Analyse zurück
     (abgelegt in _state["dfd_variants"]: dict surname → set[variant]).

Kein Schreibzugriff auf GEDCOM / Datenbank.
"""

import html as _html_mod
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VARIANTS_JSON = os.path.join(_HERE, "data", "dfd_variants.json")

_BASE       = "https://www.namenforschung.net"
_LIST_URL   = _BASE + "/dfd/woerterbuch/liste/"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_DELAY      = 1.8   # Sekunden zwischen Anfragen
_MAX_NAMES  = 300   # Maximale Anzahl Nachnamen für API-Calls

DFD_LOOKUP_HEADERS = [
    "Nachname (GEDCOM)", "DFD-Artikel vorhanden",
    "Häufigkeit (D, ~2005)", "Rang (D)",
    "Namentyp", "Etymologie (Kurzfassung)",
    "Bekannte Varianten (DFD)",
    "DFD-Link",
]

# Varianten-Cache: surname → {variant1, variant2, ...}
# Wird von run_dfd_lookup befüllt und von _runner ins _state geschrieben.
dfd_variants_cache: dict[str, set[str]] = {}


# ── HTTP-Helfer ───────────────────────────────────────────────────────────────

def _get_html(url: str) -> str | None:
    """Fetch HTML mit Browser-User-Agent. None bei Fehler / 403."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    req.add_header("Accept", "text/html,application/xhtml+xml,*/*;q=0.8")
    req.add_header("Accept-Language", "de-DE,de;q=0.9,en;q=0.8")
    req.add_header("Referer", _BASE + "/")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", ct)
            if m:
                charset = m.group(1)
            return resp.read().decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


# ── Minimal-HTML-Parser ───────────────────────────────────────────────────────

class _TextCollector(HTMLParser):
    """Sammelt Text-Content aller Elemente; unterstützt Basis-Suche."""

    def __init__(self):
        super().__init__()
        self._stack: list[tuple[str, dict]] = []
        self.segments: list[tuple[str, dict, str]] = []  # (tag, attrs, text)
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        if self._stack:
            self._flush()
        self._stack.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        self._flush()
        if self._stack and self._stack[-1][0] == tag:
            self._stack.pop()

    def handle_data(self, data):
        self._buf += data

    def _flush(self):
        if self._stack and self._buf.strip():
            tag, attrs = self._stack[-1]
            self.segments.append((tag, attrs, self._buf.strip()))
        self._buf = ""


def _collect_links(html: str) -> list[tuple[str, str]]:
    """Gibt [(href, link_text), ...] zurück."""
    links = []
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                         html, re.IGNORECASE | re.DOTALL):
        href = m.group(1)
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        links.append((href, text))
    return links


def _clean(s: str) -> str:
    s = _html_mod.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


# ── DFD-URL-Bauer ─────────────────────────────────────────────────────────────

def _search_url(surname: str) -> str:
    """Erzeugt die DFD-Such-URL für einen Nachnamen (kein cHash nötig)."""
    params = {
        "tx_dfd_names[query]":      surname,
        "tx_dfd_names[action]":     "list",
        "tx_dfd_names[controller]": "Names",
    }
    return _LIST_URL + "?" + urllib.parse.urlencode(params)


# ── Schritt A: Suchergebnis-Seite → Artikel-Link ─────────────────────────────

def _find_article_link(surname: str, html: str) -> str | None:
    """Sucht in der Ergebnisliste nach einem Link zum passenden Artikel."""
    sn_lower = surname.lower()
    for href, text in _collect_links(html):
        # Link muss auf die Liste-Seite mit action=show verweisen
        if "action%5D=show" not in href and "action]=show" not in href:
            continue
        # Linktext soll den Nachnamen enthalten (Groß-/Klein egal)
        if sn_lower in text.lower():
            if href.startswith("/"):
                return _BASE + href
            return href
    return None


# ── Schritt B: Artikel-Seite parsen ──────────────────────────────────────────

_FREQUENCY_RE = re.compile(
    r'(?:H[äa]ufigkeit|Frequenz|H[äa]ufigkeitsklasse)[:\s]*([0-9.,\s]+)',
    re.IGNORECASE)
_RANK_RE = re.compile(
    r'(?:Rang|Platz)[:\s#]*([0-9.]+)',
    re.IGNORECASE)
_TYPE_KEYWORDS = {
    "Berufsname", "Wohnst[äa]ttenname", "Patronym", "Matronym",
    "Herkunftsname", "Übername", "Spottname", "Rufname",
    "Hausname", "Hofname",
}
_TYPE_RE = re.compile(
    r'\b(' + '|'.join(_TYPE_KEYWORDS) + r')\b', re.IGNORECASE)


def _parse_article(surname: str, html: str) -> dict:
    """Extrahiert strukturierte Daten aus einem DFD-Artikel."""
    result: dict = {
        "frequency": "",
        "rank":      "",
        "type":      "",
        "etymology": "",
        "variants":  set(),
    }

    # Roher Text (HTML-Tags entfernt)
    raw_text = re.sub(r'<[^>]+>', ' ', html)
    raw_text = _html_mod.unescape(raw_text)
    raw_text = re.sub(r'\s+', ' ', raw_text)

    # Häufigkeit
    m = _FREQUENCY_RE.search(raw_text)
    if m:
        result["frequency"] = m.group(1).strip()[:30]

    # Rang
    m = _RANK_RE.search(raw_text)
    if m:
        result["rank"] = m.group(1).strip()[:10]

    # Namentyp
    types_found = set()
    for m in _TYPE_RE.finditer(raw_text):
        types_found.add(m.group(1).capitalize())
    result["type"] = ", ".join(sorted(types_found))[:80]

    # Etymologie: erster Absatz nach einem typischen Keyword
    etym_m = re.search(
        r'(?:Etymologie|Herkunft|Grundwort)[:\s]+([\w\s,;.()/-]{20,300})',
        raw_text, re.IGNORECASE)
    if etym_m:
        result["etymology"] = etym_m.group(1).strip()[:200]

    # Varianten: suche nach Laut-/Schreibvarianten-Sektion
    var_m = re.search(
        r'(?:Varianten?|Schreibvarianten?|Lautvarianten?)[:\s]+([\w\s,;/\-]+)',
        raw_text, re.IGNORECASE)
    if var_m:
        raw_vars = var_m.group(1)
        # Einzelne Namen extrahieren (≥ 3 Buchstaben, Anfangsbuchstabe groß)
        for w in re.split(r'[,;\s/]+', raw_vars):
            w = w.strip()
            if len(w) >= 3 and w[0].isupper():
                result["variants"].add(w)

    # Sicherheits-Fallback: Namen auf der Seite die ähnlich wie der gesuchte klingen
    # (gleicher Anfangsbuchstabe, 3–20 Zeichen, großgeschrieben)
    if not result["variants"]:
        for m2 in re.finditer(r'\b([A-ZÄÖÜ][a-zäöüß]{2,19})\b', raw_text):
            candidate = m2.group(1)
            if candidate.lower() != surname.lower() and _similar_enough(candidate, surname):
                result["variants"].add(candidate)

    return result


_PHON_EQUIV: dict[str, str] = {
    # Kölner Phonetik Klassen → erster Buchstabe normalisieren
    "C": "K", "Q": "K",          # /k/
    "V": "F", "W": "F",          # /f/
    "Y": "I",                    # /j/ → /i/
    "PH": "F",
}


def _normalize_first(ch: str) -> str:
    return _PHON_EQUIV.get(ch.upper(), ch.upper())


def _similar_enough(a: str, b: str) -> bool:
    """Grobe Ähnlichkeit: phonetisch gleicher Anfang + Levenshtein ≤ 3."""
    if not a or not b:
        return False
    if _normalize_first(a[0]) != _normalize_first(b[0]):
        return False
    # Simple Levenshtein
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > 3:
        return False
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            dp[j] = min(prev[j] + 1, dp[j - 1] + 1,
                        prev[j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
    return dp[n] <= 3


# ── Nachnamen aus GEDCOM sammeln ──────────────────────────────────────────────

def _collect_surnames(individuals: dict) -> list[str]:
    """Eindeutige Nachnamen aus dem GEDCOM, sortiert nach Häufigkeit."""
    freq: dict[str, int] = {}
    for pdata in individuals.values():
        name = pdata.get("NAME") or ""
        m = re.search(r'/([^/]+)/', name)
        if not m:
            continue
        sn = re.sub(r'[✠★⚔‡]', '', m.group(1)).strip()
        sn = re.sub(r'\s+', ' ', sn)
        if sn and len(sn) >= 2:
            freq[sn] = freq.get(sn, 0) + 1
    # Häufigste zuerst
    return [sn for sn, _ in sorted(freq.items(), key=lambda x: -x[1])]


# ── Haupt-Funktion ────────────────────────────────────────────────────────────

def run_dfd_lookup(individuals: dict, progress_cb=None,
                   max_names: int = _MAX_NAMES,
                   scrape: bool = True) -> tuple[list, dict[str, set[str]]]:
    """Recherchiert DFD-Einträge für alle Nachnamen im GEDCOM.

    Gibt zurück:
        (rows, variants_dict)
        rows          — Sheet-Zeilen für Excel-Export
        variants_dict — {surname: {variant1, variant2, …}} für Phonetik-Match
    """
    p = progress_cb or (lambda m, **kw: None)
    p("DFD-Namenforschung: Nachnamen sammeln …")

    surnames = _collect_surnames(individuals)
    p(f"  {len(surnames):,} eindeutige Nachnamen, davon max. {max_names} abgefragt")

    rows: list = []
    variants: dict[str, set[str]] = {}
    scraped_ok = 0

    for i, sn in enumerate(surnames[:max_names]):
        if i % 20 == 0 and i:
            p(f"  … {i}/{min(len(surnames), max_names)} Namen, {scraped_ok} mit DFD-Daten")

        search_url = _search_url(sn)
        article_link = ""
        data: dict = {}

        if scrape:
            # Schritt A: Suchliste
            html_list = _get_html(search_url)
            time.sleep(_DELAY)

            if html_list:
                article_link = _find_article_link(sn, html_list) or ""
                if article_link:
                    # Schritt B: Artikel
                    html_art = _get_html(article_link)
                    time.sleep(_DELAY)
                    if html_art:
                        data = _parse_article(sn, html_art)
                        scraped_ok += 1

        # Varianten in den Cache
        if data.get("variants"):
            variants[sn] = data["variants"]

        rows.append([
            sn,
            "ja" if article_link else ("geprüft, nicht gefunden" if scrape else "–"),
            data.get("frequency", ""),
            data.get("rank", ""),
            data.get("type", ""),
            data.get("etymology", ""),
            "; ".join(sorted(data.get("variants", set())))[:120],
            article_link or search_url,
        ])

    # Varianten persistent speichern, damit bridge/_text.py sie laden kann
    if variants:
        try:
            os.makedirs(os.path.dirname(_VARIANTS_JSON), exist_ok=True)
            with open(_VARIANTS_JSON, "w", encoding="utf-8") as f:
                json.dump({k: sorted(v) for k, v in variants.items()},
                          f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    mode = f"(davon {scraped_ok} mit Artikel-Inhalt)" if scrape else "(URL-Modus)"
    p(f"DFD-Lookup abgeschlossen: {len(rows):,} Nachnamen {mode}", tag="ok")
    return rows, variants
