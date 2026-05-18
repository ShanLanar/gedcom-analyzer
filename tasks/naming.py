# -*- coding: utf-8 -*-
"""tasks/naming.py – Patronymik-, Junior- und Familien-Namenspool-Analysen."""

import re
from collections import Counter, defaultdict

from lib.gedcom import safe_extract_year
from lib.helpers import safe_extract_family_name


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

_SYMBOLS = ["✠", "★", "⚔", "‡", "‼"]


def _clean_name(name: str) -> str:
    if not name:
        return ""
    out = str(name)
    for s in _SYMBOLS:
        out = out.replace(s, " ")
    out = re.sub(r"\bmig\.\S*", "", out, flags=re.IGNORECASE)
    return out.strip()


def _given_tokens(name: str) -> list:
    """Liefert die Vornamen (alle Token vor /Nachname/) als Liste."""
    cleaned = _clean_name(name)
    if not cleaned:
        return []
    if "/" in cleaned:
        before = cleaned.split("/", 1)[0]
    else:
        # Kein /Surname/ – behandle den letzten Token als Nachname.
        words = cleaned.split()
        before = " ".join(words[:-1]) if len(words) > 1 else cleaned
    return [t for t in before.split() if t]


def _first_given(name: str) -> str:
    toks = _given_tokens(name)
    return toks[0] if toks else ""


def _father_id(pdata: dict, families: dict) -> str | None:
    for fid in pdata.get("FAMC", []) or []:
        fam = families.get(fid)
        if fam and fam.get("HUSB"):
            return fam["HUSB"]
    return None


def _birth_year(pdata: dict) -> int | None:
    birt = pdata.get("BIRT") or {}
    return birt.get("YEAR") or safe_extract_year(birt.get("DATE"))


# ── Patronymik-Erkennung ───────────────────────────────────────────────────────

PATRONYM_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr",
    "Vater-Vorname", "Übereinstimmung-Position",
]

_PATRONYM_CAP = 50_000


def detect_patronyms(individuals, families, progress_cb=None) -> list:
    """Findet Personen, deren mittlerer Vorname dem Rufnamen des Vaters
    entspricht (klassisches Patronym in Mitteleuropa).
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Patronymik-Analyse …")

    rows: list = []

    for pid, pdata in individuals.items():
        if not pdata.get("FAMC"):
            continue
        father_id = _father_id(pdata, families)
        if not father_id:
            continue
        father = individuals.get(father_id)
        if not father:
            continue

        father_first = _first_given(father.get("NAME") or "")
        if not father_first:
            continue

        child_givens = _given_tokens(pdata.get("NAME") or "")
        if len(child_givens) <= 1:
            continue

        f_low = father_first.lower()
        match_pos = None
        for idx in range(1, len(child_givens)):
            if child_givens[idx].lower() == f_low:
                match_pos = idx + 1  # 1-basiert: 2., 3., …
                break

        if match_pos is None:
            continue

        rows.append([
            pid,
            _clean_name(pdata.get("NAME") or ""),
            _birth_year(pdata) or "",
            father_first,
            f"{match_pos}.",
        ])

        if len(rows) >= _PATRONYM_CAP:
            break

    rows.sort(key=lambda r: (-(r[2] if isinstance(r[2], int) else -10**9)))
    p(f"Patronymik: {len(rows)} Treffer", tag="ok")
    return rows


# ── Junior-Erkennung ───────────────────────────────────────────────────────────

JUNIOR_HEADERS = [
    "Person-ID", "Name", "Geburtsjahr",
    "Vater-ID", "Vater-Name", "Vater-Geburtsjahr",
    "Übereinstimmung (Vorname)",
]


def detect_juniors(individuals, families, progress_cb=None) -> list:
    """Findet Personen, deren erster Vorname identisch mit dem ersten Vornamen
    des Vaters ist ("Junior"-Muster).
    """
    p = progress_cb or (lambda m, **kw: None)
    p("Junior-Analyse …")

    rows: list = []

    for pid, pdata in individuals.items():
        if not pdata.get("FAMC"):
            continue
        father_id = _father_id(pdata, families)
        if not father_id:
            continue
        father = individuals.get(father_id)
        if not father:
            continue

        child_first = _first_given(pdata.get("NAME") or "")
        father_first = _first_given(father.get("NAME") or "")
        if not child_first or not father_first:
            continue
        if child_first.lower() != father_first.lower():
            continue

        rows.append([
            pid,
            _clean_name(pdata.get("NAME") or ""),
            _birth_year(pdata) or "",
            father_id,
            _clean_name(father.get("NAME") or ""),
            _birth_year(father) or "",
            child_first,
        ])

    rows.sort(key=lambda r: (-(r[2] if isinstance(r[2], int) else -10**9)))
    p(f"Junioren: {len(rows)} Treffer", tag="ok")
    return rows


# ── Familien-Namenspool ────────────────────────────────────────────────────────

FAMILY_NAME_POOL_HEADERS = [
    "Nachname", "Anzahl Bearer", "Distinkte Vornamen",
    "Top-5 Vornamen (mit Anzahl)", "Wiederverwendungs-Quote %",
]


def analyze_family_name_pool(individuals, families, progress_cb=None,
                              top_n: int = 100) -> list:
    """Analysiert pro Nachname den Pool wiederverwendeter Vornamen."""
    p = progress_cb or (lambda m, **kw: None)
    p("Familien-Namenspool-Analyse …")

    by_surname: dict = defaultdict(list)
    for pdata in individuals.values():
        name = pdata.get("NAME") or ""
        if not name:
            continue
        sn = safe_extract_family_name(name)
        if not sn:
            continue
        first = _first_given(name)
        if not first:
            continue
        by_surname[sn].append(first)

    rows: list = []
    for sn, firsts in by_surname.items():
        total = len(firsts)
        if total < 5:
            continue
        # Vergleich case-insensitiv, Anzeige in Originalform der ersten
        # Vorkommnis.
        lower_to_display: dict = {}
        lower_counter: Counter = Counter()
        for f in firsts:
            low = f.lower()
            lower_counter[low] += 1
            lower_to_display.setdefault(low, f)

        distinct = len(lower_counter)
        top5 = lower_counter.most_common(5)
        top5_str = ", ".join(f"{lower_to_display[n]} ({c})" for n, c in top5)
        reuse = (total - distinct) / total * 100 if total else 0.0

        rows.append([
            sn, total, distinct, top5_str, round(reuse, 1),
        ])

    rows.sort(key=lambda r: r[1], reverse=True)
    rows = rows[:top_n]

    p(f"Familien-Namenspool: {len(rows)} Nachnamen (≥ 5 Bearer)", tag="ok")
    return rows
