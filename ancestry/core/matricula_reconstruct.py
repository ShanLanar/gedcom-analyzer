"""
Familien-Rekonstruktion aus Kirchenbuch-NER-Einträgen.

Die NER-Extraktion (extract_matrikula_ner.py) liefert einzelne Personen-
Erwähnungen pro Eintrag (Täufling, Vater, Pate, Zeuge, Verstorbener …), aber
ohne zu wissen, welche Erwähnungen dieselbe reale Person meinen. Ein Pate
„Hans Meyer" (1734) und ein Bräutigam „Hans Meyer" (1756) aus demselben Ort
sind mit hoher Wahrscheinlichkeit dieselbe Person.

Dieses Modul gruppiert Erwähnungen zu Identitäts-Kandidaten anhand einer
einfachen, transparenten Heuristik:

  * gleicher phonetischer Code (Kölner Phonetik) ODER gleicher normierter Name,
  * gleicher Ort (falls bei beiden angegeben),
  * Ereignisjahre innerhalb eines plausiblen Lebensfensters (Standard 60 Jahre).

Bewusst konservativ: es werden nur *Kandidaten* vorgeschlagen, keine
Verschmelzung erzwungen — die genealogische Bewertung bleibt beim Nutzer.
"""

from __future__ import annotations

from collections import defaultdict

# Standard-Lebensfenster: Erwähnungen, deren Ereignisjahre weiter auseinander
# liegen, gehören eher zu verschiedenen (gleichnamigen) Personen.
DEFAULT_LIFE_WINDOW = 60


def _key(row: dict) -> str:
    """Blocking-Schlüssel: phonetischer Code, sonst normierter Name."""
    return (row.get("koeln_code") or "").strip() \
        or (row.get("name_norm") or "").strip().lower() \
        or (row.get("name_raw") or "").strip().lower()


def _place(row: dict) -> str:
    return (row.get("ort") or "").strip().lower()


def _year(row: dict):
    y = row.get("event_year")
    try:
        return int(y) if y else None
    except (TypeError, ValueError):
        return None


def _compatible(a: dict, b: dict, life_window: int) -> bool:
    """True, wenn zwei Erwähnungen plausibel dieselbe Person sein können."""
    pa, pb = _place(a), _place(b)
    if pa and pb and pa != pb:
        return False
    ya, yb = _year(a), _year(b)
    if ya is not None and yb is not None and abs(ya - yb) > life_window:
        return False
    return True


def reconstruct_identities(rows: list[dict],
                           life_window: int = DEFAULT_LIFE_WINDOW) -> list[dict]:
    """Gruppiert NER-Erwähnungen zu Identitäts-Kandidaten.

    Parameters
    ----------
    rows:
        NER-Zeilen mit mindestens ``name_raw``; optional ``koeln_code``,
        ``name_norm``, ``ort``, ``event_year``, ``rolle``, ``book_id``.
    life_window:
        Maximaler Jahresabstand zweier Erwähnungen derselben Person.

    Returns
    -------
    list[dict]
        Je Kandidat mit ≥2 Erwähnungen ein Dict:
        ``{name, mentions, roles, places, year_min, year_max, size}``.
        Absteigend nach Erwähnungszahl sortiert. Einzel-Erwähnungen werden
        nicht ausgegeben (kein Rekonstruktions-Mehrwert).
    """
    blocks: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        k = _key(r)
        if k:
            blocks[k].append(r)

    candidates: list[dict] = []
    for _key_val, group in blocks.items():
        # Innerhalb eines Blocks per Union-Find nach Orts-/Jahres-Kompatibilität
        # zu Untergruppen verschmelzen (gleicher Name, aber evtl. zwei Personen).
        n = len(group)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n):
            for j in range(i + 1, n):
                if _compatible(group[i], group[j], life_window):
                    parent[find(i)] = find(j)

        subgroups: dict[int, list[dict]] = defaultdict(list)
        for idx in range(n):
            subgroups[find(idx)].append(group[idx])

        for members in subgroups.values():
            if len(members) < 2:
                continue
            years = [y for y in (_year(m) for m in members) if y is not None]
            places = sorted({_place(m) for m in members if _place(m)})
            roles  = sorted({(m.get("rolle") or "").strip()
                             for m in members if m.get("rolle")})
            name = max((m.get("name_raw") or "" for m in members), key=len)
            candidates.append({
                "name":     name,
                "size":     len(members),
                "mentions": members,
                "roles":    roles,
                "places":   places,
                "year_min": min(years) if years else None,
                "year_max": max(years) if years else None,
            })

    candidates.sort(key=lambda c: c["size"], reverse=True)
    return candidates
