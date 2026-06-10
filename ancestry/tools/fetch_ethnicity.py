"""Lädt Ethnizitäts-/Herkunftsdaten von Ancestry.com und MyHeritage.

Erkennt automatisch die SSR-JSON-Struktur der beiden Portale und
normalisiert auf: [{"label": str, "pct": float, "source": str}].
"""
from __future__ import annotations

import json
import re
import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# Kürzere Anzeigebezeichnungen für bekannte Regionen
_LABEL_MAP = {
    "germanic europe":                    "Germanisch",
    "germany":                            "Deutschland",
    "eastern europe & russia":            "Osteuropa & Russland",
    "eastern europe":                     "Osteuropa",
    "scandinavia":                        "Skandinavien",
    "england & northwestern europe":      "England & NW-Europa",
    "england":                            "England",
    "jewish diaspora":                    "Jüdische Diaspora",
    "ashkenazi jewish":                   "Aschkenasisch-Jüdisch",
    "irish":                              "Irisch",
    "french":                             "Französisch",
    "baltic":                             "Baltisch",
    "iberian peninsula":                  "Iberische Halbinsel",
    "italy":                              "Italien",
    "central asia":                       "Zentralasien",
    "south asian":                        "Südasien",
}


def _shorten(label: str) -> str:
    return _LABEL_MAP.get(label.lower().strip(), label)


# SSR-Extraktions-Patterns (absteigend nach Häufigkeit)
_PATTERNS = [
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>',
    r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;',
    r'window\.__APP_STATE__\s*=\s*(\{.*?\})\s*;',
    r'window\.MH_APP_DATA\s*=\s*(\{.*?\})\s*;',
    r'<script[^>]+type=["\']application/json["\'][^>]*>\s*(\{.*?\})\s*</script>',
    r'window\.Ancestry\s*=\s*(\{.*?\})\s*;',
]

_REGION_KEYS = ("categories", "ethnicities", "ethnicity_groups",
                "regions", "ethnicComposition", "compositions",
                "ethnicityGroups", "results", "ethnicity")


def _is_region(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    has_name = any(k in item for k in ("name", "categoryName", "label", "ethnicity", "regionName"))
    has_pct  = any(k in item for k in ("percentage", "pct", "percent", "value"))
    return has_name and has_pct


def _find_regions(data: Any, depth: int = 0) -> list[dict]:
    """Sucht rekursiv nach einer Liste von Ethnizitäts-Regionen."""
    if depth > 10:
        return []
    if isinstance(data, dict):
        for key in _REGION_KEYS:
            val = data.get(key)
            if isinstance(val, list) and val and any(_is_region(i) for i in val[:3]):
                return val
            if isinstance(val, dict):
                found = _find_regions(val, depth + 1)
                if found:
                    return found
        for val in data.values():
            found = _find_regions(val, depth + 1)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_regions(item, depth + 1)
            if found:
                return found
    return []


def _parse_html(html: str) -> list[dict]:
    """Extrahiert Regions-Daten aus beliebigem SSR-HTML."""
    for pat in _PATTERNS:
        m = re.search(pat, html, re.DOTALL | re.IGNORECASE)
        if m:
            try:
                data = json.loads(m.group(1))
                regions = _find_regions(data)
                if regions:
                    return regions
            except (json.JSONDecodeError, ValueError):
                continue
    # Fallback: alle script-Inhalte mit Ethnizitäts-Keywords durchsuchen
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        txt = m.group(1).strip()
        if not any(kw in txt for kw in ('ethnicit', 'percentage', 'categor', 'percent')):
            continue
        for obj_m in re.finditer(r'\{[^<]{80,}', txt):
            for suffix in ('', '}', '}}', '}}}'):
                try:
                    data = json.loads(obj_m.group(0) + suffix)
                    regions = _find_regions(data)
                    if regions:
                        return regions
                except (json.JSONDecodeError, ValueError):
                    continue
    return []


def _normalize(item: dict, source: str) -> Optional[dict]:
    label = (item.get("categoryName") or item.get("regionName") or
             item.get("name") or item.get("label") or item.get("ethnicity") or "")
    pct = (item.get("percentage") or item.get("pct") or
           item.get("percent") or item.get("value") or 0)
    label = str(label).strip()
    if not label:
        return None
    try:
        pct = float(pct)
    except (ValueError, TypeError):
        return None
    if pct <= 0 or pct > 100:
        return None
    return {
        "label":  _shorten(label),
        "pct":    round(pct, 1),
        "source": source,
    }


# ── Ancestry ─────────────────────────────────────────────────────────────────

def fetch_ancestry_ethnicity(session, test_guid: str) -> list[dict]:
    """Ruft Ethnizitäts-Auswertung vom Ancestry DNA Origins-Portal ab.

    Benötigt eine authentifizierte requests.Session (self._state.client._s).
    """
    url = f"https://www.ancestry.com/dna/origins/{test_guid}/regions"
    try:
        r = session.get(url, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            log.warning("Ancestry Ethnizität: HTTP %s für %s", r.status_code, test_guid)
            return []
        items = _parse_html(r.text)
        result = [n for i in items if (n := _normalize(i, "ancestry")) is not None]
        return sorted(result, key=lambda x: -x["pct"])
    except Exception as e:
        log.warning("fetch_ancestry_ethnicity: %s", e)
        return []


# ── MyHeritage ───────────────────────────────────────────────────────────────

def fetch_myheritage_ethnicity(kit_guid: str,
                                cookie_file: Optional[Path] = None) -> list[dict]:
    """Ruft Ethnizitäts-Auswertung vom MyHeritage DNA Portal ab.

    Baut die Session aus der MH-Cookie-Datei auf (wie download_myheritage.py).
    """
    from requests import Session as RSession
    if cookie_file is None:
        try:
            from ancestry.paths import ROOT
            cookie_file = ROOT / "ancestry" / "data" / "myheritage_cookies.json"
        except ImportError:
            return []
    if not Path(cookie_file).exists():
        log.info("MH-Cookie-Datei nicht gefunden: %s", cookie_file)
        return []
    try:
        raw = json.loads(Path(cookie_file).read_text(encoding="utf-8"))
        cookies = ({c["name"]: c["value"] for c in raw if "name" in c}
                   if isinstance(raw, list) else raw)
        sess = RSession()
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
        url = f"https://www.myheritage.com/dna/ethnicity/{kit_guid}"
        r = sess.get(url, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            log.warning("MH Ethnizität: HTTP %s", r.status_code)
            return []
        items = _parse_html(r.text)
        result = [n for i in items if (n := _normalize(i, "myheritage")) is not None]
        return sorted(result, key=lambda x: -x["pct"])
    except Exception as e:
        log.warning("fetch_myheritage_ethnicity: %s", e)
        return []


# ── Kombiniert ───────────────────────────────────────────────────────────────

def fetch_all_ethnicity(
    test_guid: str,
    mh_kit_guid: str = "",
    ancestry_session=None,
    cookie_file: Optional[Path] = None,
) -> list[dict]:
    """Lädt Ethnizitätsdaten von Ancestry und MyHeritage und kombiniert sie."""
    results: list[dict] = []
    if ancestry_session and test_guid:
        results.extend(fetch_ancestry_ethnicity(ancestry_session, test_guid))
    if mh_kit_guid:
        results.extend(fetch_myheritage_ethnicity(mh_kit_guid, cookie_file))
    return results


# ── Ancestry Traits ───────────────────────────────────────────────────────────

_TRAIT_KEYS = ("traits", "traitResults", "traitsList", "dnaTraits",
               "ancestryTraits", "predictionResults")


def _find_traits(data: Any, depth: int = 0) -> list[dict]:
    """Sucht rekursiv nach einer Traits-Liste."""
    if depth > 10:
        return []
    if isinstance(data, dict):
        for key in _TRAIT_KEYS:
            val = data.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                if any(k in val[0] for k in ("traitName", "name", "trait", "label")):
                    return val
            if isinstance(val, dict):
                found = _find_traits(val, depth + 1)
                if found:
                    return found
        for val in data.values():
            found = _find_traits(val, depth + 1)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_traits(item, depth + 1)
            if found:
                return found
    return []


def _normalize_trait(item: dict) -> Optional[dict]:
    name = (item.get("traitName") or item.get("name") or
            item.get("trait") or item.get("label") or "")
    result = (item.get("result") or item.get("prediction") or
              item.get("value") or item.get("phenotype") or "")
    # pct der wahrscheinlichsten Kategorie
    pct = (item.get("percentage") or item.get("probability") or
           item.get("likelihood") or item.get("percent") or None)
    name = str(name).strip()
    result = str(result).strip()
    if not name:
        return None
    out: dict = {"name": name, "result": result}
    if pct is not None:
        try:
            out["pct"] = round(float(pct), 1)
        except (ValueError, TypeError):
            pass
    return out


def fetch_ancestry_traits(session, test_guid: str) -> list[dict]:
    """Ruft DNA-Traits (phänotypische Merkmale) vom Ancestry Traits-Portal ab."""
    url = f"https://www.ancestry.com/dna/traits/{test_guid}"
    try:
        r = session.get(url, timeout=30, allow_redirects=True)
        if r.status_code != 200:
            log.warning("Ancestry Traits: HTTP %s", r.status_code)
            return []
        items: list[dict] = []
        for pat in _PATTERNS:
            m = re.search(pat, r.text, re.DOTALL | re.IGNORECASE)
            if m:
                try:
                    data = json.loads(m.group(1))
                    items = _find_traits(data)
                    if items:
                        break
                except (json.JSONDecodeError, ValueError):
                    continue
        result = [n for i in items if (n := _normalize_trait(i)) is not None]
        return result
    except Exception as e:
        log.warning("fetch_ancestry_traits: %s", e)
        return []
