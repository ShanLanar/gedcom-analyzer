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
    # min_cm auch für die Shared-Pair-Schwelle verwenden (statt Repo-Default 7),
    # damit Segment-Filter und Paar-Filter konsistent sind.
    shared_pairs = db.get_shared_pairs_set(test_guid, min_cm=min_cm, guids=seg_guids)

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
                # Qualitätsflag: bilden ALLE Mitglieder-Paare ein shared-Paar
                # (echte Clique = stärkste Triangulation), oder nur transitiv
                # verbunden? Ändert die Gruppierung nicht, macht die Güte sichtbar.
                sub_guids = [s["match_guid"] for s in sub]
                is_clique = all(
                    frozenset({a, b}) in shared_pairs
                    for x, a in enumerate(sub_guids)
                    for b in sub_guids[x + 1:]
                )
                tgs.append({
                    "chromosome":   chrom,
                    "chromosome_label": chromosome_label(chrom),
                    "region_start": region_start,
                    "region_end":   region_end,
                    "clique":       is_clique,
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


# ── Geschwister-Segmentabgleich (Rekonstruktion ohne Eltern-Kit) ──────────────

def _group_overlap_cm(group: list[dict], overlap_bp: int) -> float:
    """Wie _overlap_cm, aber für eine ganze Gruppe (>=2) statt nur ein Paar:
    Durchschnitt der cM/bp-Dichten aller Mitglieder mit bekannter Dichte."""
    densities = [d for d in (_seg_density(s) for s in group) if d > 0]
    if densities:
        return overlap_bp * (sum(densities) / len(densities))
    return overlap_bp / 1_000_000.0


def find_sibling_shared_segments(
    db: "Database",
    kit_guids: list[str],
    min_cm: float = 7.0,
    min_overlap_cm: float = 5.0,
) -> list[dict]:
    """Findet Drittanbieter-Matches, die bei ZWEI ODER MEHR der angegebenen
    Kits (typischerweise Geschwister) auf ÜBERLAPPENDEN Segmenten erscheinen.

    Genealogische Begründung
    -------------------------
    Geschwister erben von jedem Elternteil ~50 % der DNA, aber bei jedem
    Kind eine ANDERE Rekombination. Teilt ein Match X mit ZWEI Geschwistern
    ein ÜBERLAPPENDES Segment an derselben chromosomalen Stelle, können beide
    dieses Stück nur identisch geerbt haben, wenn es an dieser Stelle NICHT
    rekombiniert wurde — starkes Indiz, dass X über einen gemeinsamen Vorfahren
    JENSEITS der Eltern (Großeltern-Ebene oder weiter) verwandt ist. Das
    grenzt die Linie ein, OHNE dass ein Eltern-Kit vorliegen muss — deckt also
    genau den Fall ab, für den die Eltern-Kit-Phasing (get_paternal_maternal_
    overlap) nicht greift.

    Parameters
    ----------
    kit_guids:
        Mindestens 2 DNA-Kit-GUIDs (Geschwister-Kits). Kits ohne importierte
        Segmentdaten tragen einfach nichts bei (Ancestry liefert keine
        Segmentpositionen — braucht GEDmatch/MyHeritage/FTDNA-Import).
    min_cm:
        Mindestlänge je Einzelsegment (Rauschfilter, wie bei build_
        triangulation_groups).
    min_overlap_cm:
        Mindest-Overlap in cM (nicht bp — cM/bp schwankt regional), damit
        zufällige kleine Überschneidungen nicht mitzählen.

    Returns
    -------
    list[dict]
        Je gemeinsam bestätigtem Segment: ``{match_guid, chromosome,
        chromosome_label, region_start, region_end, siblings}``, wobei
        ``siblings`` eine Liste ``{test_guid, length_cm, start, end}`` ist
        (eine pro beitragendem Kit). Sortiert nach Chromosom, dann Start.
    """
    if len(kit_guids) < 2:
        return []

    # Segmente je (match_guid, chromosome) über ALLE Kits sammeln.
    by_key: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for kit_guid in kit_guids:
        for seg in db.get_segments(kit_guid, min_cm=min_cm):
            by_key[(seg["match_guid"], seg["chromosome"])].append(
                {**seg, "test_guid": kit_guid})

    results: list[dict] = []
    emitted: set[frozenset] = set()
    for (match_guid, chrom), segs in sorted(by_key.items()):
        if len({s["test_guid"] for s in segs}) < 2:
            continue  # nur bei EINEM Geschwister → keine Kreuzbestätigung möglich

        segs_sorted = sorted(segs, key=lambda s: s["start_location"])
        for group in _common_region_subgroups(segs_sorted):
            distinct_kits = {s["test_guid"] for s in group}
            if len(distinct_kits) < 2:
                continue  # Untergruppe stammt nur von einem einzigen Kit

            region_start = max(s["start_location"] for s in group)
            region_end = min(s["end_location"] for s in group)
            overlap_bp = region_end - region_start
            if overlap_bp <= 0:
                continue
            if _group_overlap_cm(group, overlap_bp) < min_overlap_cm:
                continue

            key = frozenset((s["test_guid"], s["start_location"], s["end_location"])
                            for s in group)
            if key in emitted:
                continue
            emitted.add(key)

            results.append({
                "match_guid":        match_guid,
                "chromosome":        chrom,
                "chromosome_label":  chromosome_label(chrom),
                "region_start":      region_start,
                "region_end":        region_end,
                "siblings": [
                    {"test_guid": s["test_guid"], "length_cm": s["length_cm"],
                     "start": s["start_location"], "end": s["end_location"]}
                    for s in group
                ],
            })

    results.sort(key=lambda r: (r["chromosome"], r["region_start"]))
    return results


# ── Hypothetischer Baum (Herleitung eines vermuteten Vorfahren) ──────────────

def build_hypothetical_tree_data(
    db: "Database",
    test_guid: str,
    tg: dict,
    candidate_ged_id: str,
) -> dict | None:
    """Baut die Datengrundlage für den 'Hypothetischen Baum' einer
    Triangulationsgruppe: ein bereits im eigenen GEDCOM bekannter Vorfahre
    (``candidate_ged_id``, typischerweise aus ``annotate_tg_candidate_mrca``)
    als vermuteter gemeinsamer Ursprung, darunter alle TG-Mitglieder als
    vermutete Nachkommen.

    Genealogische Einordnung
    -------------------------
    Der Vorfahre selbst ist real und im eigenen Baum dokumentiert — die
    HYPOTHESE betrifft nur, DASS er der gemeinsame Vorfahre für GENAU DIESE
    Triangulationsgruppe ist. Mitglieder, die per ``gedcom_links`` bereits mit
    exakt diesem ``ged_id`` verknüpft sind, gelten als "bestätigt" (diese
    Verknüpfung entstand unabhängig vom Segment-Overlap, über Namens-/
    Pedigree-Abgleich). Mitglieder OHNE eine solche Verknüpfung sind reine
    "Hypothese": ihre Zugehörigkeit stützt sich ausschließlich auf das
    geteilte DNA-Segment (der Overlap + die Shared-Match-Bestätigung, die die
    TG selbst begründen), nicht auf dokumentierte Abstammung.

    Returns
    -------
    dict mit:
      ``ancestor``:   ``{ged_id, given_name, surname, sex, birth_year,
                       birth_place, death_year, death_place, ahnen_path,
                       sosa}``
      ``confirmed``:  TG-Mitglieder (``match_guid, display_name, length_cm,
                      start, end``), zusätzlich per ``gedcom_links`` mit dem
                      Vorfahren verknüpft — nach ``length_cm`` absteigend.
      ``hypothesis``: TG-Mitglieder ohne diese Verknüpfung (nur DNA-Beleg) —
                      nach ``length_cm`` absteigend.

    ``None``, wenn ``candidate_ged_id`` nicht in ``gedcom_persons`` existiert.
    Reine SELECTs, fail-soft bei DB-Fehlern (siehe ``annotate_tg_candidate_mrca``).
    """
    try:
        with db._cursor() as cur:
            row = cur.execute(
                "SELECT ged_id, given_name, surname, sex, birth_year, "
                "birth_place, death_year, death_place FROM gedcom_persons "
                "WHERE ged_id=?", (candidate_ged_id,)
            ).fetchone()
    except Exception as e:
        log.debug("build_hypothetical_tree_data ancestor: %s", e)
        return None
    if not row:
        return None

    ahnen_path = ""
    confirmed_guids: set[str] = set()
    try:
        with db._cursor() as cur:
            link_rows = cur.execute(
                "SELECT match_guid, ahnen_path FROM gedcom_links "
                "WHERE test_guid=? AND ged_id=?",
                (test_guid, candidate_ged_id),
            ).fetchall()
        for r in link_rows:
            confirmed_guids.add(r["match_guid"])
            if not ahnen_path and r["ahnen_path"]:
                ahnen_path = r["ahnen_path"]
    except Exception as e:
        log.debug("build_hypothetical_tree_data links: %s", e)

    from ancestry.core.bridge import path_to_sosa
    ancestor = {
        "ged_id":      row["ged_id"],
        "given_name":  row["given_name"] or "",
        "surname":     row["surname"] or "",
        "sex":         row["sex"] or "",
        "birth_year":  row["birth_year"],
        "birth_place": row["birth_place"] or "",
        "death_year":  row["death_year"],
        "death_place": row["death_place"] or "",
        "ahnen_path":  ahnen_path,
        "sosa":        path_to_sosa(ahnen_path) if ahnen_path else 0,
    }

    names: dict[str, str] = {}
    member_guids = [m["match_guid"] for m in tg.get("members", [])]
    if member_guids:
        try:
            names = {m.match_guid: m.display_name for m in db.get_matches(
                test_guid=test_guid, guid_filter=member_guids)}
        except Exception as e:
            log.debug("build_hypothetical_tree_data names: %s", e)

    confirmed: list[dict] = []
    hypothesis: list[dict] = []
    for m in tg.get("members", []):
        guid = m["match_guid"]
        entry = {
            "match_guid":   guid,
            "display_name": names.get(guid, guid[:12]),
            "length_cm":    m["length_cm"],
            "start":        m["start"],
            "end":          m["end"],
        }
        (confirmed if guid in confirmed_guids else hypothesis).append(entry)

    confirmed.sort(key=lambda e: -e["length_cm"])
    hypothesis.sort(key=lambda e: -e["length_cm"])

    return {"ancestor": ancestor, "confirmed": confirmed, "hypothesis": hypothesis}
