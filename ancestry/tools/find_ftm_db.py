#!/usr/bin/env python3
"""
find_ftm_db.py — entpackte FTM-Arbeits-SQLite-DB auf der Platte finden

Neuere Family-Tree-Maker-Versionen (MacKiev, FTM 2019/2024) speichern die
.ftm-Datei NICHT mehr als blankes SQLite, sondern komprimiert/verschlüsselt.
Erst beim Öffnen entpackt FTM den Baum in eine Arbeits-SQLite-Datenbank.

Dieses Werkzeug durchsucht die typischen FTM-Verzeichnisse (und optional
beliebige Wurzeln) nach Dateien mit SQLite-Magic-Header und prüft, ob sie
nach einer FTM-Datenbank aussehen (Tabellen wie Individual/PersonName/Fact).

Am besten aufrufen, WÄHREND der Baum in FTM geöffnet ist — dann liegt die
entpackte Arbeits-DB vor.

Aufruf:
  python find_ftm_db.py
  python find_ftm_db.py --root "D:/Eigene Daten/Dokumente"
  python find_ftm_db.py --root C:/Users/theng/AppData --min-mb 1
  python find_ftm_db.py --all          # auch Nicht-FTM-SQLite zeigen
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_SQLITE_MAGIC = b"SQLite format 3\x00"

# Tabellen, an denen wir eine FTM-Datenbank erkennen (lowercase).
_FTM_TABLE_HINTS = {
    "individual", "person", "personname", "name",
    "fact", "facttype", "place", "childrelationship",
}


def _is_sqlite(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(16) == _SQLITE_MAGIC
    except OSError:
        return False


def _ftm_score(path: Path) -> tuple[int, list[str]]:
    """Anzahl FTM-typischer Tabellen + Tabellenliste (für die Anzeige)."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error:
        try:
            conn = sqlite3.connect(str(path))
        except sqlite3.Error:
            return 0, []
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    except sqlite3.DatabaseError:
        return 0, []
    finally:
        conn.close()
    tables = [r[0] for r in rows]
    lower = {t.lower() for t in tables}
    score = len(_FTM_TABLE_HINTS & lower)
    return score, tables


def _default_roots() -> list[Path]:
    """Typische Orte, an denen FTM-Daten/Arbeitskopien liegen (Windows)."""
    roots: list[Path] = []
    home = Path.home()
    candidates = [
        home / "Documents" / "Family Tree Maker",
        home / "Dokumente" / "Family Tree Maker",
        home / "AppData" / "Local" / "Software MacKiev",
        home / "AppData" / "Roaming" / "Software MacKiev",
        home / "AppData" / "Local" / "Temp",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Software MacKiev",
    ]
    for c in candidates:
        if c and str(c) != "Software MacKiev" and c.exists():
            roots.append(c)
    return roots


def scan(roots: list[Path], min_mb: float = 0.0,
         show_all: bool = False) -> list[dict]:
    seen: set[Path] = set()
    hits: list[dict] = []
    min_bytes = int(min_mb * 1024 * 1024)

    for root in roots:
        if not root.exists():
            print(f"  (übersprungen, existiert nicht: {root})")
            continue
        print(f"  Durchsuche: {root}")
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                p = Path(dirpath) / fn
                if p in seen:
                    continue
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                if size < min_bytes:
                    continue
                if not _is_sqlite(p):
                    continue
                seen.add(p)
                score, tables = _ftm_score(p)
                if score == 0 and not show_all:
                    continue
                try:
                    mtime = datetime.fromtimestamp(p.stat().st_mtime)
                except OSError:
                    mtime = None
                hits.append({
                    "path": p,
                    "size_mb": size / 1024 / 1024,
                    "mtime": mtime,
                    "ftm_score": score,
                    "table_count": len(tables),
                })
    hits.sort(key=lambda h: (-h["ftm_score"], -h["size_mb"]))
    return hits


def main():
    ap = argparse.ArgumentParser(
        description="Findet die entpackte FTM-Arbeits-SQLite-DB.")
    ap.add_argument("--root", action="append", default=None,
                    help="Zusätzliches Wurzelverzeichnis (mehrfach möglich)")
    ap.add_argument("--min-mb", type=float, default=0.5,
                    help="Mindestgröße in MB (Standard: 0.5)")
    ap.add_argument("--all", action="store_true",
                    help="Auch SQLite-Dateien ohne FTM-Tabellen anzeigen")
    args = ap.parse_args()

    roots = [Path(r) for r in (args.root or [])]
    roots.extend(_default_roots())
    if not roots:
        print("Keine Suchverzeichnisse. Mit --root einen Pfad angeben.")
        sys.exit(1)

    print("🔍 Suche nach entpackter FTM-SQLite-DB …")
    print("   (am besten mit GEÖFFNETEM Baum in FTM ausführen)\n")
    hits = scan(roots, min_mb=args.min_mb, show_all=args.all)

    if not hits:
        print("\n❌ Keine passende SQLite-DB gefunden.")
        print("   • Ist der Baum gerade in FTM geöffnet?")
        print("   • Mit --root einen anderen Pfad (z.B. AppData) absuchen.")
        print("   • Notfalls: in FTM nach GEDCOM exportieren und das .ged importieren.")
        return

    print(f"\n✅ {len(hits)} SQLite-Datei(en) gefunden "
          f"(nach FTM-Wahrscheinlichkeit sortiert):\n")
    for h in hits:
        ts = h["mtime"].strftime("%Y-%m-%d %H:%M") if h["mtime"] else "?"
        flag = "★ FTM" if h["ftm_score"] >= 3 else f"  {h['ftm_score']} FTM-Tab."
        print(f"  [{flag}]  {h['size_mb']:8.1f} MB  {ts}  "
              f"({h['table_count']} Tabellen)")
        print(f"           {h['path']}")
    best = hits[0]
    if best["ftm_score"] >= 3:
        print("\n➡  Wahrscheinlichste FTM-DB:")
        print(f"   {best['path']}")
        print("\n   Direkt importieren mit:")
        print(f'   python import_ftm_bridge.py "{best["path"]}" --source ftm')


if __name__ == "__main__":
    main()
