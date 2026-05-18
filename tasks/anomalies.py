# -*- coding: utf-8 -*-
"""tasks/anomalies.py – Anomalie-, Duplikat- und Insel-Erkennung"""

from collections import deque
from lib.gedcom import safe_extract_year

CURRENT_YEAR = 2026

ANOMALY_HEADERS = ["Person-ID", "Name", "Geburtsjahr", "Typ", "Schwere", "Detail"]
DUPLICATE_HEADERS = ["ID 1", "Name 1", "ID 2", "Name 2", "Geburtsjahr", "Konfidenz %", "Grund"]
ISLAND_HEADERS = ["Person-ID", "Name", "Geburtsjahr", "Familien (FAMC+FAMS)", "Bemerkung"]

_SEVERITY_ORDER = {"KRITISCH": 0, "WARNUNG": 1, "HINWEIS": 2}


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _name(pdata: dict) -> str:
    return (pdata.get("NAME") or "").strip()


def _birth_year(pdata: dict):
    return safe_extract_year((pdata.get("BIRT") or {}).get("DATE"))


def _death_year(pdata: dict):
    return safe_extract_year((pdata.get("DEAT") or {}).get("DATE"))


def _marr_year(fam: dict):
    return safe_extract_year(fam.get("MARR_DATE"))


def _add(rows: list, pid: str, pdata: dict, typ: str, schwere: str, detail: str):
    rows.append([pid, _name(pdata), _birth_year(pdata) or "", typ, schwere, detail])


# ── Anomalie-Erkennung ─────────────────────────────────────────────────────────

def detect_anomalies(individuals, families, progress_cb=None):
    """Prüft auf unplausible Datenkombinationen und gibt Zeilen mit
    ANOMALY_HEADERS zurück, sortiert nach Schwere (KRITISCH zuerst)
    und aufsteigendem Geburtsjahr."""
    p = progress_cb or (lambda m, **kw: None)
    p("Anomalie-Erkennung …")

    rows = []

    # ── Personenbezogene Checks ────────────────────────────────────────────────
    for pid, pdata in individuals.items():
        by = _birth_year(pdata)
        dy = _death_year(pdata)
        name = _name(pdata)

        if by and dy and by > dy:
            _add(rows, pid, pdata, "Geburt nach Tod", "KRITISCH",
                 f"Geburtsjahr {by} > Sterbejahr {dy}")

        if by and by > CURRENT_YEAR:
            _add(rows, pid, pdata, "Geburtsjahr in der Zukunft", "KRITISCH",
                 f"Geburtsjahr {by} > {CURRENT_YEAR}")

        if dy and dy > CURRENT_YEAR + 1:
            _add(rows, pid, pdata, "Sterbejahr in der Zukunft", "KRITISCH",
                 f"Sterbejahr {dy} > {CURRENT_YEAR + 1}")

        if by and dy and dy > by:
            age = dy - by
            if age > 110:
                _add(rows, pid, pdata, "Unrealistisches Alter", "WARNUNG",
                     f"Lebensalter {age} Jahre ({by}–{dy})")

    # ── Familienbezogene Checks ────────────────────────────────────────────────
    for fam_id, fam in families.items():
        husb_id = fam.get("HUSB")
        wife_id = fam.get("WIFE")
        children = fam.get("CHIL", [])
        marr_y = _marr_year(fam)

        husb = individuals.get(husb_id) if husb_id else None
        wife = individuals.get(wife_id) if wife_id else None

        husb_by = _birth_year(husb) if husb else None
        husb_dy = _death_year(husb) if husb else None
        wife_by = _birth_year(wife) if wife else None
        wife_dy = _death_year(wife) if wife else None

        # Heiratsalter
        if marr_y:
            if husb and husb_by:
                marr_age = marr_y - husb_by
                if marr_age < 14:
                    _add(rows, husb_id, husb, "Heirat mit niedrigem Alter", "WARNUNG",
                         f"Heiratsalter ca. {marr_age} Jahre (Heirat {marr_y})")
                elif marr_age > 90:
                    _add(rows, husb_id, husb, "Heirat im hohen Alter", "HINWEIS",
                         f"Heiratsalter ca. {marr_age} Jahre (Heirat {marr_y})")
            if wife and wife_by:
                marr_age = marr_y - wife_by
                if marr_age < 14:
                    _add(rows, wife_id, wife, "Heirat mit niedrigem Alter", "WARNUNG",
                         f"Heiratsalter ca. {marr_age} Jahre (Heirat {marr_y})")
                elif marr_age > 90:
                    _add(rows, wife_id, wife, "Heirat im hohen Alter", "HINWEIS",
                         f"Heiratsalter ca. {marr_age} Jahre (Heirat {marr_y})")

            # Heirat nach Tod eines Ehepartners
            if husb and husb_dy and marr_y > husb_dy:
                _add(rows, husb_id, husb, "Heirat nach eigenem Tod", "WARNUNG",
                     f"Heiratsjahr {marr_y} nach Sterbejahr {husb_dy}")
            if wife and wife_dy and marr_y > wife_dy:
                _add(rows, wife_id, wife, "Heirat nach eigenem Tod", "WARNUNG",
                     f"Heiratsjahr {marr_y} nach Sterbejahr {wife_dy}")

        # ── Kindbezogene Checks innerhalb der Familie ──────────────────────────
        child_birth_years = []
        for cid in children:
            child = individuals.get(cid)
            if not child:
                continue
            cby = _birth_year(child)
            if cby:
                child_birth_years.append(cby)

            # Kind nach Mutter-Tod
            if wife and wife_dy and cby and cby > wife_dy:
                _add(rows, cid, child, "Kind nach Mutter-Tod geboren", "KRITISCH",
                     f"Kind {cby} – Mutter {wife_id} starb {wife_dy}")

            # Alter der Mutter bei Geburt
            if wife and wife_by and cby:
                mother_age = cby - wife_by
                if mother_age < 12:
                    _add(rows, cid, child, "Mutter zu jung bei Geburt", "KRITISCH",
                         f"Mutter {wife_id}: Alter ca. {mother_age} Jahre bei Geburt {cby}")
                elif mother_age > 55:
                    _add(rows, cid, child, "Mutter zu alt bei Geburt", "WARNUNG",
                         f"Mutter {wife_id}: Alter ca. {mother_age} Jahre bei Geburt {cby}")

            # Alter des Vaters bei Geburt
            if husb and husb_by and cby:
                father_age = cby - husb_by
                if father_age < 12:
                    _add(rows, cid, child, "Vater zu jung bei Geburt", "KRITISCH",
                         f"Vater {husb_id}: Alter ca. {father_age} Jahre bei Geburt {cby}")
                elif father_age > 80:
                    _add(rows, cid, child, "Vater zu alt bei Geburt", "WARNUNG",
                         f"Vater {husb_id}: Alter ca. {father_age} Jahre bei Geburt {cby}")

            # Postumes Kind (> 1 Jahr nach Vater-Tod)
            if husb and husb_dy and cby and cby > husb_dy + 1:
                _add(rows, cid, child, "Posthume Geburt", "HINWEIS",
                     f"Kind {cby} – Vater {husb_id} starb {husb_dy} "
                     f"(Differenz: {cby - husb_dy} Jahre)")

        # Geschwister-Geburtsabstand > 25 Jahre
        if len(child_birth_years) >= 2:
            child_birth_years_sorted = sorted(child_birth_years)
            for i in range(len(child_birth_years_sorted) - 1):
                gap = child_birth_years_sorted[i + 1] - child_birth_years_sorted[i]
                if gap > 25:
                    # Melde für die Familie auf dem jüngsten Kind mit diesem Abstand
                    representative_cid = None
                    for cid in children:
                        child = individuals.get(cid)
                        if child and _birth_year(child) == child_birth_years_sorted[i + 1]:
                            representative_cid = cid
                            break
                    if representative_cid and representative_cid in individuals:
                        rc = individuals[representative_cid]
                        _add(rows, representative_cid, rc,
                             "Großer Geschwisterabstand", "HINWEIS",
                             f"Abstand {gap} Jahre in Familie {fam_id} "
                             f"({child_birth_years_sorted[i]}–{child_birth_years_sorted[i+1]})")

    # ── Sortierung: Schwere, dann Geburtsjahr ──────────────────────────────────
    def _sort_key(row):
        sev = _SEVERITY_ORDER.get(row[4], 99)
        by = row[2]
        return (sev, by if isinstance(by, int) else 9999)

    rows.sort(key=_sort_key)
    p(f"Anomalien: {len(rows)} gefunden", tag="ok")
    return rows


# ── Duplikat-Erkennung ─────────────────────────────────────────────────────────

# Vornamen-Synonyme für die Doubletten-Heuristik. Mappt regionale/dialektale
# Kurz- und Variantenformen auf einen kanonischen Stammnamen. Quelle: gängige
# deutsche Namens-Synonyme aus genealogischen Standard-Werken.
_GIVEN_SYNONYMS = {
    # Johannes-Familie
    "HANS": "JOHANNES", "JOHANN": "JOHANNES", "JOHANNES": "JOHANNES",
    "HANNES": "JOHANNES", "HENNES": "JOHANNES", "JOH": "JOHANNES",
    "JOHN": "JOHANNES", "JEAN": "JOHANNES",
    # Heinrich
    "HEINRICH": "HEINRICH", "HEINZ": "HEINRICH", "HENRY": "HEINRICH",
    "HEIN": "HEINRICH", "HENRI": "HEINRICH", "HARRY": "HEINRICH",
    # Friedrich
    "FRIEDRICH": "FRIEDRICH", "FRITZ": "FRIEDRICH", "FREDI": "FRIEDRICH",
    "FRIEDEL": "FRIEDRICH",
    # Wilhelm
    "WILHELM": "WILHELM", "WILLI": "WILHELM", "WILLY": "WILHELM",
    "WILLEM": "WILHELM",
    # Karl
    "KARL": "KARL", "CARL": "KARL", "CHARLES": "KARL", "KARLI": "KARL",
    # Jakob
    "JAKOB": "JAKOB", "JACOB": "JAKOB", "KOBI": "JAKOB",
    # Georg
    "GEORG": "GEORG", "JÖRG": "GEORG", "JÜRGEN": "GEORG", "GEORGE": "GEORG",
    # Peter / Paul
    "PETER": "PETER", "PETRUS": "PETER",
    "PAUL": "PAUL", "PAULUS": "PAUL",
    # Michael
    "MICHAEL": "MICHAEL", "MICHEL": "MICHAEL", "MIKE": "MICHAEL",
    # August
    "AUGUST": "AUGUST", "AUGUSTE": "AUGUST", "GUSTL": "AUGUST",
    # Anna / Maria / Elisabeth
    "ANNA": "ANNA", "ANNE": "ANNA", "ÄNNE": "ANNA", "ANNI": "ANNA",
    "MARIA": "MARIA", "MARIE": "MARIA", "MAREN": "MARIA", "MARI": "MARIA",
    "ELISABETH": "ELISABETH", "ELISE": "ELISABETH", "LISBETH": "ELISABETH",
    "LIESE": "ELISABETH", "BETTY": "ELISABETH", "ELSE": "ELISABETH",
    "ELLA": "ELISABETH",
    "KATHARINA": "KATHARINA", "KÄTHE": "KATHARINA", "KATRIN": "KATHARINA",
    "TRINE": "KATHARINA", "KATE": "KATHARINA",
    "MARGARETHA": "MARGARETHA", "MARGARETE": "MARGARETHA", "GRETE": "MARGARETHA",
    "MARGRET": "MARGARETHA", "GRETCHEN": "MARGARETHA",
    "GERTRUD": "GERTRUD", "TRUDE": "GERTRUD", "TRUDI": "GERTRUD",
    "WILHELMINE": "WILHELMINE", "MINNA": "WILHELMINE", "MINA": "WILHELMINE",
    "FRIEDA": "FRIEDA", "FRIEDERIKE": "FRIEDA", "FRIEDL": "FRIEDA",
}


def _canonical_given(first_given: str) -> str:
    """Bringt einen Vornamen auf seinen Stamm-Namen (z.B. Hans → JOHANNES).
    Gibt den Original-Vornamen zurück, wenn kein Synonym hinterlegt ist."""
    if not first_given:
        return ""
    key = first_given.strip().upper()
    return _GIVEN_SYNONYMS.get(key, key)


def _levenshtein(a: str, b: str) -> int:
    """Berechnet die Levenshtein-Distanz zwischen zwei Strings."""
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)
    if len_a == 0:
        return len_b
    if len_b == 0:
        return len_a
    # Einzeilige DP-Matrix
    prev = list(range(len_b + 1))
    for i in range(1, len_a + 1):
        curr = [i] + [0] * len_b
        for j in range(1, len_b + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[len_b]


def _parse_name_parts(name_str: str):
    """Gibt (surname_norm, given_norm) zurück.
    Nachname aus GEDCOM /Nachname/ extrahiert, Rest ist Vornamen."""
    name = (name_str or "").strip()
    surname = ""
    given = ""
    if "/" in name:
        parts = name.split("/")
        given = parts[0].strip()
        surname = parts[1].strip() if len(parts) >= 2 else ""
        if not given and len(parts) >= 3:
            given = parts[2].strip()
    else:
        words = name.split()
        if words:
            surname = words[-1]
            given = " ".join(words[:-1])
    return surname.lower(), given.lower()


def _confidence(sn_a: str, sn_b: str, gn_a: str, gn_b: str,
                 by_a, by_b) -> tuple[int, list]:
    """Berechnet Konfidenz (0–99) und Begründungsliste."""
    score = 0
    reasons = []

    # Nachname
    if sn_a and sn_b:
        if sn_a == sn_b:
            score += 40
            reasons.append("gleicher Nachname")
        else:
            lev = _levenshtein(sn_a, sn_b)
            if lev == 1:
                score += 25
                reasons.append(f"Nachname ähnlich (Lev={lev})")
            elif lev == 2:
                score += 10
                reasons.append(f"Nachname ähnlich (Lev={lev})")

    # Vorname (erstes Token vergleichen für Effizienz)
    fn_a = gn_a.split()[0] if gn_a.split() else gn_a
    fn_b = gn_b.split()[0] if gn_b.split() else gn_b
    if fn_a and fn_b:
        if fn_a == fn_b:
            score += 40
            reasons.append("gleicher Vorname")
        else:
            lev = _levenshtein(fn_a, fn_b)
            if lev == 1:
                score += 25
                reasons.append(f"Vorname ähnlich (Lev={lev})")
            elif lev == 2:
                score += 10
                reasons.append(f"Vorname ähnlich (Lev={lev})")

    # Geburtsjahr
    if by_a is not None and by_b is not None:
        diff = abs(by_a - by_b)
        if diff == 0:
            score += 20
            reasons.append(f"gleiches Geburtsjahr ({by_a})")
        elif diff == 1:
            score += 10
            reasons.append(f"Geburtsjahr ±1 ({by_a}/{by_b})")
        elif diff == 2:
            score += 5
            reasons.append(f"Geburtsjahr ±2 ({by_a}/{by_b})")
        elif diff > 5:
            score -= 20
            reasons.append(f"Geburtsjahr Differenz {diff} Jahre")

    return min(score, 99), reasons


def detect_duplicates(individuals, progress_cb=None):
    """Findet potenzielle Duplikate anhand von Name und Geburtsjahr.
    Gibt Zeilen mit DUPLICATE_HEADERS zurück, sortiert nach Konfidenz."""
    p = progress_cb or (lambda m, **kw: None)
    p("Duplikat-Erkennung …")

    # Parsed name cache
    parsed: dict = {}
    for pid, pdata in individuals.items():
        sn, gn = _parse_name_parts(_name(pdata))
        parsed[pid] = (sn, gn, _birth_year(pdata))

    # Gruppierung nach normiertem Nachname (erste 3 Buchstaben als Bucket)
    buckets: dict = {}
    for pid, (sn, gn, by) in parsed.items():
        if not sn:
            continue
        key = sn[:3]
        buckets.setdefault(key, []).append(pid)

    rows = []
    seen_pairs: set = set()

    for bucket_pids in buckets.values():
        if len(bucket_pids) < 2:
            continue
        for i in range(len(bucket_pids)):
            for j in range(i + 1, len(bucket_pids)):
                pid_a = bucket_pids[i]
                pid_b = bucket_pids[j]
                pair = (min(pid_a, pid_b), max(pid_a, pid_b))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                sn_a, gn_a, by_a = parsed[pid_a]
                sn_b, gn_b, by_b = parsed[pid_b]

                # Vorfilter: Nachname muss Levenshtein-nah sein
                if _levenshtein(sn_a, sn_b) > 2:
                    continue

                # Vorname: erst Levenshtein, dann Synonym-Vergleich als Fallback
                fn_a = gn_a.split()[0] if gn_a.split() else gn_a
                fn_b = gn_b.split()[0] if gn_b.split() else gn_b
                fn_a_canon = _canonical_given(fn_a)
                fn_b_canon = _canonical_given(fn_b)
                # Synonym-Pfad: kanonische Form stimmt überein, aber die
                # Schreibung unterscheidet sich (z. B. Karl/Carl, Hans/Johannes)
                via_synonym = (fn_a_canon and fn_a_canon == fn_b_canon
                                 and fn_a.upper() != fn_b.upper())
                if fn_a and fn_b and _levenshtein(fn_a, fn_b) > 2 and not via_synonym:
                    continue

                # Geburtsjahr-Filter (falls beide bekannt)
                if by_a is not None and by_b is not None:
                    if abs(by_a - by_b) > 2:
                        continue

                conf, reasons = _confidence(sn_a, sn_b, gn_a, gn_b, by_a, by_b)
                # Synonym-Treffer gibt zusätzlichen Konfidenz-Boost
                if via_synonym:
                    conf = min(99, conf + 20)
                    reasons.append(f"Vornamen-Synonym ({fn_a}↔{fn_b}→{fn_a_canon})")
                if conf < 40:
                    continue

                pa = individuals[pid_a]
                pb = individuals[pid_b]
                birth_disp = (by_a or by_b or "")
                rows.append([
                    pid_a, _name(pa),
                    pid_b, _name(pb),
                    birth_disp, conf,
                    "; ".join(reasons),
                ])

    rows.sort(key=lambda r: r[5], reverse=True)
    p(f"Potenzielle Duplikate: {len(rows)} gefunden", tag="ok")
    return rows


# ── Insel-Erkennung (Unreachable Persons) ─────────────────────────────────────

def detect_islands(root_id, individuals, families, progress_cb=None):
    """BFS von root_id durch Familien-Links (FAMC + FAMS → HUSB/WIFE/CHIL).
    Gibt alle Personen zurück, die von root_id aus nicht erreichbar sind,
    sortiert nach Geburtsjahr."""
    p = progress_cb or (lambda m, **kw: None)
    p("Insel-Erkennung (BFS) …")

    if root_id not in individuals:
        p(f"Root-ID {root_id!r} nicht in individuals – alle Personen sind Inseln.",
          tag="warn")
        reachable = set()
    else:
        # BFS: adjacency über Familien
        reachable: set = set()
        queue = deque([root_id])
        reachable.add(root_id)

        while queue:
            pid = queue.popleft()
            pdata = individuals.get(pid, {})

            # Über FAMC: Eltern und Geschwister
            for fam_id in pdata.get("FAMC", []):
                fam = families.get(fam_id, {})
                if not fam:
                    continue
                for related in (fam.get("HUSB"), fam.get("WIFE")):
                    if related and related not in reachable and related in individuals:
                        reachable.add(related)
                        queue.append(related)
                for sib in fam.get("CHIL", []):
                    if sib and sib not in reachable and sib in individuals:
                        reachable.add(sib)
                        queue.append(sib)

            # Über FAMS: Ehepartner und Kinder
            for fam_id in pdata.get("FAMS", []):
                fam = families.get(fam_id, {})
                if not fam:
                    continue
                for related in (fam.get("HUSB"), fam.get("WIFE")):
                    if related and related not in reachable and related in individuals:
                        reachable.add(related)
                        queue.append(related)
                for child in fam.get("CHIL", []):
                    if child and child not in reachable and child in individuals:
                        reachable.add(child)
                        queue.append(child)

    rows = []
    for pid, pdata in individuals.items():
        if pid in reachable:
            continue
        by = _birth_year(pdata)
        famc = pdata.get("FAMC", [])
        fams = pdata.get("FAMS", [])
        fam_count = len(famc) + len(fams)
        fam_ids_str = ", ".join(famc + fams) if fam_count else "keine"

        if fam_count == 0:
            bemerkung = "Keine Familienverknüpfung"
        else:
            bemerkung = f"Verknüpft, aber von Root {root_id!r} nicht erreichbar"

        rows.append([pid, _name(pdata), by or "", fam_ids_str, bemerkung])

    rows.sort(key=lambda r: r[2] if isinstance(r[2], int) else 9999)
    p(f"Inseln: {len(rows)} nicht erreichbare Personen", tag="ok")
    return rows
