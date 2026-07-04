"""
Segment triangulation for DNA genealogy.

A Triangulation Group (TG) is a set of DNA matches who:
  1. All share overlapping segments on the same chromosomal region, and
  2. Are confirmed to share DNA with each other (via shared_matches table).

Connected components (not cliques) are used: if A-B and B-C share, all
three form one TG even without a direct A-C record, which mirrors typical
genealogical practice.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ancestry.core.database import Database

log = logging.getLogger(__name__)

X_CHROMOSOME = 23


def chromosome_label(chrom: int) -> str:
    """23 → 'X' (Konvention aus import_segments.py), sonst die Nummer."""
    return "X" if chrom == X_CHROMOSOME else str(chrom)


def _seg_density(seg: dict) -> float:
    """cM pro Basenpaar eines Segments (0 wenn Länge/cM unbekannt)."""
    span = (seg.get("end_location") or 0) - (seg.get("start_location") or 0)
    cm = seg.get("length_cm") or 0
    return (cm / span) if span > 0 and cm > 0 else 0.0


def _overlap_cm(a: dict, b: dict, overlap_bp: int) -> float:
    """Schätzt die überlappenden cM aus der mittleren cM/bp-Dichte beider
    Segmente. Fehlt bei beiden die Dichte (keine cM/Spanne), fällt es auf die
    grobe 1-cM-je-Mbp-Faustregel zurück, damit nichts unbeabsichtigt wegfällt."""
    densities = [d for d in (_seg_density(a), _seg_density(b)) if d > 0]
    if densities:
        avg = sum(densities) / len(densities)
        return overlap_bp * avg
    return overlap_bp / 1_000_000.0


def _common_region_subgroups(members: list[dict]) -> list[list[dict]]:
    """Zerlegt eine (ketten-verbundene) Segment-Komponente in maximale
    Untergruppen, die einen GEMEINSAMEN überlappenden Bereich teilen.

    Hat die ganze Komponente eine gemeinsame Schnittmenge (max start < min
    end), wird sie unverändert zurückgegeben. Andernfalls entsprechen die
    maximalen gemeinsam-überlappenden Mengen bei Intervallen genau den aktiven
    Mengen an den Segment-Startpunkten (Intervallgraphen sind perfekt). Es
    werden nur maximale Mengen der Größe ≥ 2 zurückgegeben (keine, die Teilmenge
    einer anderen ist)."""
    rs = max(m["start_location"] for m in members)
    re = min(m["end_location"] for m in members)
    if re > rs:
        return [members]

    groups: list[list[dict]] = []
    for p in sorted({m["start_location"] for m in members}):
        active = [m for m in members
                  if m["start_location"] <= p <= m["end_location"]]
        if len(active) >= 2:
            groups.append(active)

    # Nur maximale Gruppen behalten (keine echten Teilmengen einer anderen)
    maximal: list[list[dict]] = []
    for g in groups:
        gset = {id(m) for m in g}
        if any(gset < {id(m) for m in h} for h in groups):
            continue
        if any(gset == {id(m) for m in h} for h in maximal):
            continue
        maximal.append(g)
    return maximal


def build_triangulation_groups(
    db: "Database",
    test_guid: str,
    min_cm: float = 7.0,
    min_overlap_cm: float = 5.0,
) -> list[dict]:
    """
    Return a list of Triangulation Groups for *test_guid*.

    Each TG dict has:
      chromosome   int
      region_start int   (intersection start of all member segments)
      region_end   int   (intersection end of all member segments)
      members      list of dicts: {match_guid, length_cm, start, end}
    """
    segments = db.get_segments(test_guid, min_cm=min_cm)
    if not segments:
        return []

    # Nur Paare unter den Matches laden, die tatsächlich Segmente tragen —
    # begrenzt den RAM-Bedarf auf die (kleine) Segment-Population statt der
    # gesamten Match-Tabelle (relevant bei 300k+ Matches).
    seg_guids = {s["match_guid"] for s in segments}
    shared_pairs = db.get_shared_pairs_set(test_guid, guids=seg_guids)

    by_chrom: dict[int, list[dict]] = defaultdict(list)
    for seg in segments:
        by_chrom[seg["chromosome"]].append(seg)

    tgs: list[dict] = []

    for chrom in sorted(by_chrom):
        segs = sorted(by_chrom[chrom], key=lambda s: s["start_location"])
        n = len(segs)
        if n < 2:
            continue

        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        for i in range(n):
            for j in range(i + 1, n):
                if segs[j]["start_location"] > segs[i]["end_location"]:
                    break
                overlap_start = max(segs[i]["start_location"], segs[j]["start_location"])
                overlap_end   = min(segs[i]["end_location"],   segs[j]["end_location"])
                overlap_bp = overlap_end - overlap_start
                if overlap_bp <= 0:
                    continue
                # Overlap in cM (genetische Karte) messen, nicht in bp: die
                # frühere bp<cM*1e6-Prüfung unterstellte fix 1 cM = 1 Mbp, was
                # regional stark schwankt (v. a. auf dem X). Wir schätzen die
                # Overlap-cM aus der cM/bp-Dichte der beiden Segmente.
                if _overlap_cm(segs[i], segs[j], overlap_bp) < min_overlap_cm:
                    continue
                pair = frozenset({segs[i]["match_guid"], segs[j]["match_guid"]})
                if pair in shared_pairs:
                    union(i, j)

        comp: dict[int, list[int]] = defaultdict(list)
        for idx in range(n):
            comp[find(idx)].append(idx)

        emitted: set[frozenset] = set()
        for indices in comp.values():
            if len(indices) < 2:
                continue
            members = [segs[k] for k in indices]
            # Echte TG verlangen einen GEMEINSAMEN überlappenden Bereich, nicht
            # nur Kettenkonnektivität (A–B, B–C ohne A∩C). Hat die Komponente
            # eine gemeinsame Schnittmenge, ist sie eine TG; sonst wird sie in
            # Untergruppen mit gemeinsamem Bereich zerlegt (kein Aufblähen auf
            # das ganze Chromosom mehr).
            for sub in _common_region_subgroups(members):
                if len(sub) < 2:
                    continue
                key = frozenset(id(s) for s in sub)
                if key in emitted:
                    continue
                emitted.add(key)
                region_start = max(s["start_location"] for s in sub)
                region_end   = min(s["end_location"]   for s in sub)
                tgs.append({
                    "chromosome":   chrom,
                    "chromosome_label": chromosome_label(chrom),
                    "region_start": region_start,
                    "region_end":   region_end,
                    "members": [
                        {
                            "match_guid": s["match_guid"],
                            "length_cm":  s["length_cm"],
                            "start":      s["start_location"],
                            "end":        s["end_location"],
                        }
                        for s in sub
                    ],
                })

    tgs.sort(key=lambda t: (t["chromosome"], t["region_start"]))
    return tgs


def annotate_tg_candidate_mrca(
    db: "Database",
    test_guid: str,
    tgs: list[dict],
) -> list[dict]:
    """
    Annotate each Triangulation Group with its likely Most-Recent Common
    Ancestor(s) (MRCA), derived from the GEDCOM bridge (`gedcom_links`).

    Genealogische Begründung
    -------------------------
    Alle Mitglieder einer TG erben *dasselbe* Ahnen-Segment auf derselben
    chromosomalen Region. DNA-Genealogie folgert daraus: sie stammen mit hoher
    Wahrscheinlichkeit von *einem* gemeinsamen Vorfahren ab (dem MRCA der
    Gruppe). Wenn nun ≥2 verschiedene Mitglieder einer TG laut Bridge auf
    *dieselbe* GEDCOM-Person (`ged_id`) zeigen, ist das ein sich gegenseitig
    bestätigender Beleg (corroborating evidence): unabhängige Matches, die
    dasselbe Segment teilen, deuten auf denselben Ahnen — genau die Person, die
    das geteilte Segment plausibel erklärt. Je mehr Mitglieder auf dieselbe
    ged_id zeigen (und je höher deren Match-Score), desto stärker der Beleg.

    Für jede TG wird `candidate_mrca` gesetzt: eine nach `member_count` (desc),
    dann `avg_score` (desc) sortierte Liste von Dicts
    ``{ged_id, name, year, member_count, avg_score}``. ``name`` ist
    ``"ged_given ged_surname"``. Es werden nur Kandidaten mit
    ``member_count >= 2`` behalten, gedeckelt auf die Top 5. Gibt es keinen,
    ist ``candidate_mrca == []``.

    Reine SELECTs, fail-soft: bei einem DB-Fehler wird die jeweilige TG mit
    ``candidate_mrca = []`` versehen und es geht weiter. Gibt dieselbe (in
    place annotierte) ``tgs``-Liste zurück.
    """
    for tg in tgs:
        tg["candidate_mrca"] = []
        guids = list({m["match_guid"] for m in tg.get("members", []) if m.get("match_guid")})
        if not guids:
            continue
        try:
            # {ged_id: [name, year, set(member_guids), [scores]]}
            agg: dict[str, dict] = {}
            # IN-Liste sicherheitshalber chunken (SQLite-Variablen-Limit), auch
            # wenn eine TG praktisch nie >900 Mitglieder hat.
            for start in range(0, len(guids), 900):
                chunk = guids[start:start + 900]
                placeholders = ",".join("?" * len(chunk))
                with db._cursor() as cur:
                    rows = cur.execute(
                        f"SELECT match_guid, ged_id, ged_given, ged_surname, "
                        f"ged_year, total_score "
                        f"FROM gedcom_links "
                        f"WHERE test_guid = ? AND match_guid IN ({placeholders})",
                        (test_guid, *chunk),
                    ).fetchall()
                for r in rows:
                    ged_id = r["ged_id"]
                    if not ged_id:
                        continue
                    slot = agg.setdefault(
                        ged_id,
                        {
                            "name": (f"{r['ged_given'] or ''} "
                                     f"{r['ged_surname'] or ''}").strip(),
                            "year": r["ged_year"],
                            "members": set(),
                            "scores": [],
                        },
                    )
                    slot["members"].add(r["match_guid"])
                    slot["scores"].append(float(r["total_score"] or 0.0))

            candidates = []
            for ged_id, slot in agg.items():
                member_count = len(slot["members"])
                if member_count < 2:
                    continue
                scores = slot["scores"]
                avg_score = sum(scores) / len(scores) if scores else 0.0
                candidates.append({
                    "ged_id":       ged_id,
                    "name":         slot["name"],
                    "year":         slot["year"],
                    "member_count": member_count,
                    "avg_score":    round(avg_score, 1),
                })

            candidates.sort(key=lambda c: (-c["member_count"], -c["avg_score"]))
            tg["candidate_mrca"] = candidates[:5]
        except Exception as e:
            log.debug("annotate_tg_candidate_mrca: %s", e)
            tg["candidate_mrca"] = []

    return tgs
