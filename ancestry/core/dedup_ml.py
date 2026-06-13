"""Personendubletten-Erkennung: Feature-Extraktion, Blocking und Klassifikation.

Wiederverwendet die bewährten String-Ähnlichkeiten aus bridge/_text (Kölner
Phonetik, Levenshtein, Namens-/Orts-Ähnlichkeit) und die Nachnamen-Seltenheit
(seltener Name → stärkeres Dubletten-Signal). Labels für ein trainiertes Modell
kommen aus gedcom_person_xref: status='confirmed' = Dublette (1),
status='rejected' = keine Dublette (0).

Ohne trainiertes Modell / ohne scikit-learn liefert rule_score() einen
regelbasierten Baseline-Score (kompatibel zur bisherigen compute_link_score-
Gewichtung). find_duplicates() nutzt Blocking über koelner_code, damit nicht
O(n²) Paare verglichen werden.
"""
from __future__ import annotations

import hashlib
import logging
import pickle
from collections import defaultdict
from pathlib import Path

from ancestry.core.bridge._text import (_norm, _koelner, _levenshtein,
                                        _name_sim, _place_sim)

log = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent / "dedup_model.pkl"
HASH_PATH = MODEL_PATH.with_suffix(".sha256")

FEATURE_NAMES = ["surname_exact", "surname_koelner", "surname_lev", "given_sim",
                 "year_diff", "year_close", "place_sim", "surname_rarity",
                 "sex_match"]

_MODEL = None


# ── Features ──────────────────────────────────────────────────────────────────

def surname_frequency(db) -> dict:
    """{surname_norm: Anzahl} über gedcom_persons – für die Nachnamen-Seltenheit."""
    freq: dict[str, int] = {}
    try:
        with db._cursor() as cur:
            for r in cur.execute("SELECT surname_norm, COUNT(*) c FROM gedcom_persons "
                                 "WHERE surname_norm != '' GROUP BY surname_norm"):
                freq[r["surname_norm"]] = r["c"]
    except Exception as e:
        log.debug("surname_frequency: %s", e)
    return freq


def pair_features(a: dict, b: dict, surname_freq: dict | None = None) -> list[float]:
    """Merkmalsvektor für ein Personenpaar (Reihenfolge = FEATURE_NAMES)."""
    na, nb = _norm(a.get("surname") or ""), _norm(b.get("surname") or "")
    surname_exact = 1.0 if na and na == nb else 0.0
    surname_koelner = 1.0 if na and nb and _koelner(na) == _koelner(nb) else 0.0
    maxlen = max(len(na), len(nb), 1)
    surname_lev = 1.0 - _levenshtein(na, nb) / maxlen
    given_sim = _name_sim(a.get("given_name") or "", b.get("given_name") or "")
    ya, yb = a.get("birth_year"), b.get("birth_year")
    try:
        yd = abs(int(ya) - int(yb)) if ya and yb else 99
    except (TypeError, ValueError):
        yd = 99
    year_diff = min(yd, 99) / 99.0
    year_close = 1.0 if yd <= 3 else 0.0
    place_sim = _place_sim(a.get("birth_place") or "", b.get("birth_place") or "")
    freq = (surname_freq or {}).get(na, 0)
    surname_rarity = 1.0 / (1.0 + freq)
    sx_a, sx_b = (a.get("sex") or ""), (b.get("sex") or "")
    sex_match = 1.0 if sx_a and sx_a == sx_b else 0.0
    return [surname_exact, surname_koelner, surname_lev, given_sim, year_diff,
            year_close, place_sim, surname_rarity, sex_match]


def rule_score(feats: list[float]) -> float:
    """Regelbasierter Baseline-Score (0–1), wenn kein ML-Modell vorliegt."""
    f = dict(zip(FEATURE_NAMES, feats))
    score = 0.45 * max(f["surname_exact"], 0.85 * f["surname_koelner"], f["surname_lev"])
    score += 0.25 * f["given_sim"]
    score += 0.20 * f["year_close"]
    score += 0.10 * f["place_sim"]
    score += 0.05 * f["surname_rarity"] * f["surname_exact"]
    return min(1.0, score)


# ── Blocking + Kandidaten ─────────────────────────────────────────────────────

def _all_persons(db) -> list[dict]:
    with db._cursor() as cur:
        rows = cur.execute(
            "SELECT ged_id, given_name, surname, surname_norm, koelner_code, "
            "sex, birth_year, birth_place, source FROM gedcom_persons").fetchall()
    return [dict(r) for r in rows]


def candidate_pairs(persons: list[dict], max_year_diff: int = 4):
    """Erzeugt Vergleichspaare nur innerhalb gleicher Kölner-Phonetik-Blöcke
    (Blocking) und nahem Geburtsjahr – statt aller O(n²) Paare."""
    blocks: dict[str, list[dict]] = defaultdict(list)
    for p in persons:
        code = p.get("koelner_code") or _koelner(p.get("surname_norm") or "")
        if code:
            blocks[code].append(p)
    for members in blocks.values():
        n = len(members)
        if n < 2 or n > 400:        # Riesenblöcke (häufige Namen) überspringen
            continue
        for i in range(n):
            for j in range(i + 1, n):
                a, b = members[i], members[j]
                if str(a["ged_id"]) == str(b["ged_id"]):
                    continue
                ya, yb = a.get("birth_year"), b.get("birth_year")
                if ya and yb:
                    try:
                        if abs(int(ya) - int(yb)) > max_year_diff:
                            continue
                    except (TypeError, ValueError):
                        pass
                yield a, b


def find_duplicates(db, threshold: float = 0.6, limit: int = 500) -> list[dict]:
    """Findet wahrscheinliche Dubletten-Paare (Blocking + Modell/Regel-Score)."""
    persons = _all_persons(db)
    freq = surname_frequency(db)
    use_model = load()
    out = []
    for a, b in candidate_pairs(persons):
        feats = pair_features(a, b, freq)
        score = predict_proba(feats) if use_model else rule_score(feats)
        if score >= threshold:
            out.append({
                "ged_id_a": a["ged_id"], "name_a": f"{a.get('given_name','')} {a.get('surname','')}".strip(),
                "ged_id_b": b["ged_id"], "name_b": f"{b.get('given_name','')} {b.get('surname','')}".strip(),
                "birth_a": a.get("birth_year"), "birth_b": b.get("birth_year"),
                "source_a": a.get("source", "gedcom"), "source_b": b.get("source", "gedcom"),
                "place_a": a.get("birth_place", ""), "place_b": b.get("birth_place", ""),
                "score": round(score, 3),
                "source": "model" if use_model else "rule",
            })
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


# ── Training & Vorhersage (optional, scikit-learn) ────────────────────────────

def _person_map(db) -> dict:
    return {str(p["ged_id"]): p for p in _all_persons(db)}


def training_pairs(db):
    """(features, label) aus gedcom_person_xref: confirmed→1, rejected→0."""
    pm = _person_map(db)
    freq = surname_frequency(db)
    X, y = [], []
    try:
        with db._cursor() as cur:
            rows = cur.execute(
                "SELECT ged_id_primary, ged_id_other, status FROM gedcom_person_xref "
                "WHERE status IN ('confirmed','rejected')").fetchall()
    except Exception:
        return X, y
    for r in rows:
        a, b = pm.get(str(r["ged_id_primary"])), pm.get(str(r["ged_id_other"]))
        if not a or not b:
            continue
        X.append(pair_features(a, b, freq))
        y.append(1 if r["status"] == "confirmed" else 0)
    return X, y


def train(db, progress_cb=None) -> dict:
    """Trainiert einen Logistik-Klassifikator aus den bestätigten/abgelehnten
    Xref-Labels. Gibt Kennzahlen zurück oder {'error': …}."""
    try:
        from sklearn.linear_model import LogisticRegression
    except Exception:
        return {"error": "scikit-learn nicht installiert"}
    X, y = training_pairs(db)
    if len(set(y)) < 2 or len(y) < 10:
        return {"error": f"zu wenige Labels ({len(y)}; brauche beide Klassen)"}
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X, y)
    acc = clf.score(X, y)
    payload = {"clf": clf, "features": FEATURE_NAMES}
    raw = pickle.dumps(payload)
    MODEL_PATH.write_bytes(raw)
    HASH_PATH.write_text(hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii")
    global _MODEL
    _MODEL = payload
    return {"n_train": len(y), "n_pos": sum(y), "train_acc": round(acc, 3)}


def load() -> bool:
    global _MODEL
    if _MODEL is not None:
        return True
    if not MODEL_PATH.exists():
        return False
    try:
        raw = MODEL_PATH.read_bytes()
        if HASH_PATH.exists():
            if hashlib.sha256(raw).hexdigest() != HASH_PATH.read_text(encoding="ascii").strip():
                log.error("dedup_ml: SHA-256 stimmt nicht — Modell verworfen.")
                return False
        _MODEL = pickle.loads(raw)
        return True
    except Exception as e:
        log.error("dedup_ml: Modell laden fehlgeschlagen: %s", e)
        return False


def predict_proba(feats: list[float]) -> float:
    if not load():
        return rule_score(feats)
    try:
        return float(_MODEL["clf"].predict_proba([feats])[0][1])
    except Exception:
        return rule_score(feats)
