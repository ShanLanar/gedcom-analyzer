"""
ml_origin.py — ML-Herkunftsmodell ("zweite Meinung").

Trainiert auf den ~130.000 GEDCOM-Personen (gedcom_persons): jede liefert
ein gelabeltes Paar (Nachname [+ Geburtsjahr] -> Region). Das Modell lernt
daraus die Zuordnung Nachname/Phonetik/Zeit -> Herkunftsregion und sagt sie
für DNA-Match-Ahnen voraus.

Es ist bewusst UNABHÄNGIG von der regelbasierten infer_match_origins():
beide Ergebnisse werden getrennt gespeichert (probable_origin vs. ml_origin)
und im Tool nebeneinander angezeigt.

Modell: TF-IDF über Zeichen-n-Gramme des Nachnamens (+ Jahr-Bucket-Token)
-> Logistische Regression (liefert Wahrscheinlichkeiten für Top-k Regionen).
Schnell und treffsicher bei 130k Beispielen und vielen Klassen.

scikit-learn ist eine optionale Abhängigkeit:  pip install scikit-learn

API:
    train(db, min_region=20, progress_cb=None) -> dict   # Metriken
    load() -> bool
    predict_region(surname, birth_year=None, top=3) -> list[(region, prob)]
    apply_to_matches(db, test_guid, progress_cb=None) -> int
"""
from __future__ import annotations
import os
import pickle
import logging
from pathlib import Path
from collections import Counter, defaultdict

log = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent / "origin_model.pkl"

_MODEL = None  # im Speicher gehaltenes geladenes Modell


def _sklearn():
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        return TfidfVectorizer, LogisticRegression, Pipeline
    except ImportError as e:
        raise RuntimeError(
            "scikit-learn ist nicht installiert. Bitte ausführen:\n"
            "    pip install scikit-learn\n"
            f"(Originalfehler: {e})")


def _region_of(birth_place: str):
    """Region aus Geburtsort ableiten (gleiche Logik wie die Regel-Inferenz)."""
    try:
        from core.bridge import _extract_region
    except Exception:
        try:
            from bridge import _extract_region
        except Exception:
            def _extract_region(s):  # einfacher Fallback
                parts = [p.strip() for p in (s or "").split(",") if p.strip()]
                return parts[-2] if len(parts) >= 2 else (parts[-1] if parts else "")
    return _extract_region(birth_place or "")


def _year_bucket(year) -> str:
    """Grobes Zeit-Token; Namen/Orte verschieben sich über Jahrhunderte."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return "yNA"
    return f"y{(y // 50) * 50}"


def _featurize(surname: str, birth_year=None) -> str:
    """Textrepräsentation: Nachname + Jahr-Bucket-Token. Der Vectorizer
    bildet daraus Zeichen-n-Gramme; das Jahr-Token bleibt als Wort erhalten."""
    sn = (surname or "").strip().lower()
    return f"{sn} {_year_bucket(birth_year)}"


# ── Training ──────────────────────────────────────────────────────────────────

def train(db, min_region: int = 20, sources=None, dedupe: bool = True,
          progress_cb=None) -> dict:
    """Trainiert das Modell auf gedcom_persons. min_region verwirft seltene
    Regionen (Rauschen). Gibt Metriken zurück und speichert das Modell.

    sources: zugelassene Quellen (None = alle: gedcom + anverwandte + wikitree).
    dedupe:  verknüpfte Duplikate nur einmal zählen (über gedcom_person_xref),
             damit dieselbe Person das Training nicht verzerrt.
    """
    TfidfVectorizer, LogisticRegression, Pipeline = _sklearn()

    def p(m):
        if progress_cb:
            try: progress_cb(m)
            except Exception as e: log.debug("progress_cb train: %s", e)

    p("Lese Personen (quellenbewusst, dedupliziert) …")
    if dedupe:
        try:
            from core.bridge import iter_unique_persons
        except ImportError:
            from bridge import iter_unique_persons
        rows = [r for r in iter_unique_persons(db, sources=sources)
                if (r.get("surname") or "").strip() and (r.get("birth_place") or "").strip()]
    else:
        with db._cursor() as cur:
            q = ("SELECT surname, birth_year, birth_place FROM gedcom_persons "
                 "WHERE TRIM(surname)<>'' AND TRIM(birth_place)<>''")
            if sources:
                ph = ",".join("?" * len(sources))
                q += f" AND source IN ({ph})"
                rows = [dict(r) for r in cur.execute(q, list(sources)).fetchall()]
            else:
                rows = [dict(r) for r in cur.execute(q).fetchall()]

    X_txt, y = [], []
    for r in rows:
        reg = _region_of(r["birth_place"])
        if not reg:
            continue
        X_txt.append(_featurize(r["surname"], r["birth_year"]))
        y.append(reg)

    if not y:
        raise RuntimeError("Keine (Nachname, Region)-Paare gefunden. "
                           "Wurde ein GEDCOM importiert?")

    # seltene Regionen verwerfen
    counts = Counter(y)
    keep = {r for r, n in counts.items() if n >= min_region}
    X_txt, y = zip(*[(x, t) for x, t in zip(X_txt, y) if t in keep])
    X_txt, y = list(X_txt), list(y)
    p(f"{len(y)} Trainingspaare, {len(keep)} Regionen (>= {min_region}).")

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                  min_df=2, sublinear_tf=True)),
        ("clf",   LogisticRegression(max_iter=300, C=4.0, n_jobs=-1)),
    ])

    p("Trainiere Modell … (kann bei 130k Personen 1–2 Min dauern)")
    pipe.fit(X_txt, y)

    # einfache Trainingsgüte (kein Holdout — nur Indikator)
    train_acc = pipe.score(X_txt, y)
    p(f"Training fertig. Trainings-Genauigkeit: {train_acc:.1%}")

    payload = {"pipe": pipe, "regions": sorted(keep),
               "n_train": len(y), "train_acc": train_acc}
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(payload, f)
    global _MODEL
    _MODEL = payload
    p(f"Modell gespeichert: {MODEL_PATH}")
    return {"n_train": len(y), "n_regions": len(keep), "train_acc": train_acc}


# ── Laden & Vorhersage ────────────────────────────────────────────────────────

def load() -> bool:
    global _MODEL
    if _MODEL is not None:
        return True
    if not MODEL_PATH.exists():
        return False
    try:
        with open(MODEL_PATH, "rb") as f:
            _MODEL = pickle.load(f)
        return True
    except Exception as e:
        log.warning("ml_origin: Modell laden fehlgeschlagen: %s", e)
        return False


def predict_region(surname: str, birth_year=None, top: int = 3):
    """Top-k (Region, Wahrscheinlichkeit) für einen Nachnamen."""
    if not load():
        return []
    pipe = _MODEL["pipe"]
    proba = pipe.predict_proba([_featurize(surname, birth_year)])[0]
    classes = pipe.classes_
    order = proba.argsort()[::-1][:top]
    return [(classes[i], float(proba[i])) for i in order]


# ── Auf Matches anwenden ──────────────────────────────────────────────────────

def apply_to_matches(db, test_guid: str, progress_cb=None) -> int:
    """Sagt für jeden Match (über seine Pedigree-Nachnamen) eine Region voraus
    und speichert sie in matches.ml_origin (JSON). Gibt die Zahl gelabelter
    Matches zurück."""
    import json
    if not load():
        raise RuntimeError("Kein trainiertes Modell. Bitte zuerst train() laufen lassen.")

    def p(m):
        if progress_cb:
            try: progress_cb(m)
            except Exception as e: log.debug("progress_cb apply: %s", e)

    with db._cursor() as cur:
        rows = cur.execute(
            "SELECT match_guid, surname, birth_year, generation FROM match_pedigree "
            "WHERE test_guid=? AND TRIM(surname)<>'' AND generation>=2",
            (test_guid,)).fetchall()

    # pro Match: Wahrscheinlichkeiten der Ahnen aufsummieren (1/Generation gewichtet)
    per_match = defaultdict(lambda: defaultdict(float))
    surnames  = defaultdict(list)
    for r in rows:
        mg  = r["match_guid"]
        gen = max(1, int(r["generation"] or 2))
        w   = 1.0 / gen
        for region, prob in predict_region(r["surname"], r["birth_year"], top=3):
            per_match[mg][region] += prob * w
        surnames[mg].append(r["surname"])

    saved = 0
    for mg, region_scores in per_match.items():
        if not region_scores:
            continue
        total = sum(region_scores.values()) or 1.0
        ranked = sorted(((reg, sc / total) for reg, sc in region_scores.items()),
                        key=lambda x: -x[1])[:3]
        top_region, top_prob = ranked[0]
        payload = {
            "region": top_region,
            "prob":   round(top_prob, 3),
            "alts":   [{"region": r, "prob": round(pr, 3)} for r, pr in ranked[1:]],
            "surnames": list(dict.fromkeys(surnames[mg]))[:6],
        }
        db.set_ml_origin(mg, json.dumps(payload, ensure_ascii=False))
        saved += 1
        if saved % 500 == 0:
            p(f"ML-Herkunft: {saved} Matches gelabelt …")

    p(f"ML-Herkunft fertig: {saved} Matches gelabelt.")
    return saved
