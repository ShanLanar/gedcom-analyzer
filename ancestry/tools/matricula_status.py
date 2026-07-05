#!/usr/bin/env python3
"""
Matricula-Fortschritts-Status pro Pfarrei.

Liest matricula_parishes.db (parishes, kirchenbuecher, matricula_page_scans)
und berechnet pro Pfarrei, wie viele Seiten transkribiert sind.

Status-Logik:
  fertig    – alle Bücher haben eine bekannte Seitenanzahl (total_pages)
              und jede Seite ist 'done'
  teilweise – mindestens eine Seite 'done', aber nicht alles
  offen     – noch keine Seite gescannt

total_pages wird von scan_matricula_kirchspiel.py beim ersten Scan eines
Buchs persistiert; vorher ist der Gesamtumfang unbekannt (pages_total=None).

CLI:
  python -m ancestry.tools.matricula_status
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

PARISH_DB = Path(__file__).resolve().parent / "matricula_parishes.db"
ARCHION_DB   = Path(__file__).resolve().parent / "archion_archives.db"
ARCHION_JSON = Path(__file__).resolve().parent / "archion_archives.json"

STATUS_DONE    = "fertig"
STATUS_PARTIAL = "teilweise"
STATUS_OPEN    = "offen"


def _open(db_path: Path | str | None = None) -> sqlite3.Connection | None:
    p = Path(db_path) if db_path else PARISH_DB
    if not p.exists():
        return None
    db = sqlite3.connect(str(p), timeout=30.0)
    db.row_factory = sqlite3.Row
    # WAL + busy_timeout: dieser Lese-Zugriff (GUI-Statusanzeige) darf einen
    # gleichzeitig laufenden CLI-Scan (scan_matricula_kirchspiel) nicht mit
    # 'database is locked' blockieren.
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
    except sqlite3.OperationalError:
        pass
    return db


def get_dioceses(db_path: Path | str | None = None) -> list[dict]:
    """Gibt alle bekannten Diözesen aus der DB zurück.

    Jeder Eintrag: {path, slug, country, name, url}
    Drei Fallbacks für Altdaten (scrape_matricula_osnabrueck.py):
    1. dioceses-Tabelle (neuer universeller Scraper)
    2. parishes.diocese-Spalte (wenn befüllt)
    3. kirchenbuecher.book_id-Parsing (immer vorhanden, z.B. "deutschland/osnabrueck/...")
    """
    db = _open(db_path)
    if db is None:
        return []
    try:
        # 1. Bevorzugt: dioceses-Tabelle
        try:
            rows = db.execute(
                "SELECT path, slug, country, name, url FROM dioceses ORDER BY country, name"
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass
        # 2. Fallback: eindeutige diocese-Werte aus parishes-Tabelle
        try:
            rows = db.execute(
                "SELECT DISTINCT diocese AS path FROM parishes WHERE diocese!='' ORDER BY diocese"
            ).fetchall()
            if rows:
                return [{"path": r[0], "slug": r[0].split("/")[-1],
                         "country": r[0].split("/")[0] if "/" in r[0] else "?",
                         "name": r[0], "url": ""} for r in rows]
        except sqlite3.OperationalError:
            pass
        # 3. Letzter Fallback: Diözese aus kirchenbuecher.book_id ableiten
        #    book_id-Format: "land/diözese/pfarrei/buch" → "land/diözese" als Pfad
        try:
            rows = db.execute(
                "SELECT DISTINCT book_id FROM kirchenbuecher WHERE book_id LIKE '%/%/%'"
            ).fetchall()
            seen: set[str] = set()
            result = []
            for (bid,) in rows:
                parts = bid.split("/")
                if len(parts) >= 3:
                    dioc_path = "/".join(parts[:2])   # z.B. "deutschland/osnabrueck"
                    if dioc_path not in seen:
                        seen.add(dioc_path)
                        slug = parts[1]               # z.B. "osnabrueck"
                        result.append({
                            "path": dioc_path,
                            "slug": slug,
                            "country": parts[0],
                            "name": slug.replace("-", " ").title(),
                            "url": "",
                        })
            if result:
                return sorted(result, key=lambda d: d["path"])
        except sqlite3.OperationalError:
            pass
        return []
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()


def get_archion_archives(db_path: Path | str | None = None) -> list[dict]:
    """Archion-Archivkatalog als Fallback-Quelle (evangelische Kirchenbücher).

    Rund 40 % der deutschen evangelischen Kirchenbücher liegen nicht bei
    Matricula, sondern nur bei Archion. Diese Funktion liest den von
    scrape_archion_archives.py erzeugten Katalog (DB bevorzugt, sonst JSON) und
    liefert je Archiv: {id, region, name, url, confession, source='archion'}.
    Fehlt der Katalog, kommt eine leere Liste zurück (kein Absturz)."""
    p = Path(db_path) if db_path else ARCHION_DB
    if p.exists():
        try:
            db = sqlite3.connect(str(p))
            db.row_factory = sqlite3.Row
            try:
                rows = db.execute(
                    "SELECT id, region, name, url, confession "
                    "FROM archion_archives ORDER BY region, name"
                ).fetchall()
            finally:
                db.close()
            return [{**dict(r), "source": "archion"} for r in rows]
        except sqlite3.OperationalError:
            pass
    # JSON-Fallback (region → [archive, …])
    if ARCHION_JSON.exists():
        try:
            import json
            data = json.loads(ARCHION_JSON.read_text(encoding="utf-8"))
            out: list[dict] = []
            for region, archives in (data or {}).items():
                for a in archives:
                    out.append({
                        "id":         a.get("id", ""),
                        "region":     region,
                        "name":       a.get("name", ""),
                        "url":        a.get("url", ""),
                        "confession": a.get("confession", "evang"),
                        "source":     "archion",
                    })
            return sorted(out, key=lambda d: (d["region"], d["name"]))
        except Exception:
            pass
    return []


def get_parish_status(db_path: Path | str | None = None,
                      diocese: str | None = None) -> list[dict]:
    """Liste aller Pfarreien mit Scan-Fortschritt, alphabetisch sortiert.

    diocese — optionaler Filter auf eine Diözese (z.B. 'deutschland/osnabrueck').
    Jeder Eintrag: {id, name, diocese, n_books, pages_done, pages_total, status}
    pages_total ist None solange nicht jedes Buch eine bekannte
    Seitenanzahl hat."""
    db = _open(db_path)
    if db is None:
        return []
    try:
        # total_pages existiert erst nach dem ersten Scan-Lauf
        has_totals = any(
            r[1] == "total_pages"
            for r in db.execute("PRAGMA table_info(kirchenbuecher)")
        )
        total_col = "kb.total_pages" if has_totals else "NULL"
        diocese_where = "AND p.diocese=?" if diocese else ""
        params = (diocese,) if diocese else ()
        rows = db.execute(f"""
            SELECT p.id, p.name, p.diocese,
                   COUNT(DISTINCT kb.book_id)            AS n_books,
                   COUNT(DISTINCT CASE WHEN {total_col} IS NULL
                                       THEN kb.book_id END) AS n_books_unsized,
                   COALESCE(SUM({total_col}), 0)         AS pages_total,
                   COALESCE((
                       SELECT COUNT(*) FROM matricula_page_scans mps
                       WHERE mps.status = 'done'
                         AND mps.book_id IN (
                             SELECT book_id FROM kirchenbuecher
                             WHERE parish_id = p.id)
                   ), 0)                                  AS pages_done
            FROM parishes p
            LEFT JOIN kirchenbuecher kb ON kb.parish_id = p.id
            WHERE 1=1 {diocese_where}
            GROUP BY p.id, p.name
            ORDER BY p.name
        """, params).fetchall()
    except sqlite3.OperationalError:
        # Matricula-Schema (parishes/kirchenbuecher) noch nicht angelegt –
        # Katalog wurde nie importiert. Leer statt Absturz.
        return []
    finally:
        db.close()

    out = []
    for r in rows:
        n_books   = r["n_books"]
        done      = r["pages_done"]
        total     = r["pages_total"] if (n_books and not r["n_books_unsized"]) else None
        if total and done >= total:
            status = STATUS_DONE
        elif done > 0:
            status = STATUS_PARTIAL
        else:
            status = STATUS_OPEN
        out.append({
            "id": r["id"], "name": r["name"],
            "diocese": r["diocese"] if "diocese" in r.keys() else "",
            "n_books": n_books,
            "pages_done": done, "pages_total": total, "status": status,
        })
    return out


def format_parish_label(p: dict) -> str:
    """Dropdown-Beschriftung: Status-Symbol + Name + Fortschritt."""
    if p["status"] == STATUS_DONE:
        mark, suffix = "✓", "fertig"
    elif p["status"] == STATUS_PARTIAL:
        mark = "◐"
        if p["pages_total"]:
            suffix = f"{p['pages_done']}/{p['pages_total']} Seiten"
        else:
            suffix = f"{p['pages_done']} Seiten"
    else:
        mark, suffix = "○", f"{p['n_books']} Bücher" if p["n_books"] else "keine Bücher"
    return f"{mark} {p['name']}  ({suffix})"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zeigt den Matricula-Scan-Fortschritt pro Pfarrei aus der "
                    "matricula_parishes.db an.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Alle Pfarreien aus der Standard-DB:
  python -m ancestry.tools.matricula_status

  # Nur eine bestimmte Diözese:
  python -m ancestry.tools.matricula_status --diocese deutschland/osnabrueck

  # Andere Datenbank:
  python -m ancestry.tools.matricula_status --db /pfad/zu/matricula_parishes.db
""",
    )
    parser.add_argument(
        "--db",
        metavar="DATEI",
        default=None,
        help=f"Pfad zur Pfarrei-Datenbank (Standard: {PARISH_DB}).",
    )
    parser.add_argument(
        "--diocese", "-d",
        metavar="DIÖZESE",
        default=None,
        help="Filtert auf eine bestimmte Diözese (z.B. 'deutschland/osnabrueck').",
    )
    return parser.parse_args()


if __name__ == "__main__":
    _args = _parse_args()
    _db = _args.db or None
    dioceses = get_dioceses(_db)
    if not dioceses:
        print(f"Keine Pfarrei-DB gefunden: {_args.db or PARISH_DB}")
        print("Zuerst ausführen: python -m ancestry.tools.scrape_matricula --diocese osnabrueck")
    else:
        print(f"Bekannte Diözesen ({len(dioceses)}):")
        for d in dioceses:
            print(f"  {d['path']}")
        print()
    parishes = get_parish_status(_db, diocese=_args.diocese)
    for p in parishes:
        print(format_parish_label(p))
