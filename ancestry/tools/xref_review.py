#!/usr/bin/env python3
"""
Querbezüge (Duplikat-Verknüpfungen) prüfen und bestätigen/ablehnen.

Zeigt verknüpfte Personen-Paare aus gedcom_person_xref nebeneinander –
standardmäßig die grenzwertigen (Score nahe der Schwelle), die am ehesten
eine manuelle Entscheidung brauchen.

Aufruf:
  python xref_review.py                 # grenzwertige (0.72–0.85) auflisten
  python xref_review.py --all           # alle auflisten
  python xref_review.py --lo 0.7 --hi 0.8
  python xref_review.py --confirm <primary> <other>
  python xref_review.py --reject  <primary> <other>
  python xref_review.py -i               # interaktiv durchgehen (j/n/q)
"""
import sys
import argparse
from pathlib import Path

ANCESTRY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ANCESTRY_DIR))
sys.path.insert(0, str(ANCESTRY_DIR / "core"))
DB_PATH = ANCESTRY_DIR / "ancestry_dna.db"


def _fmt(prefix, r):
    g = r[f"{prefix}_given"] or ""
    s = r[f"{prefix}_surname"] or ""
    by = r[f"{prefix}_by"] or "?"
    dy = r[f"{prefix}_dy"] or "?"
    bp = r[f"{prefix}_bp"] or ""
    dp = r[f"{prefix}_dp"] or ""
    return f"{g} {s}  *{by} †{dy}  [{bp}{(' → '+dp) if dp else ''}]"


def show(r):
    print(f"  Score {r['score']:.3f}  [{r['status']}]  ({r['source_other']})")
    print(f"    A {r['ged_id_primary']:18} {_fmt('a', r)}")
    print(f"    B {r['ged_id_other']:18} {_fmt('b', r)}")


def main():
    from database import Database
    from core import bridge
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--lo", type=float, default=0.72)
    ap.add_argument("--hi", type=float, default=0.85)
    ap.add_argument("--status", default="")
    ap.add_argument("--source", default="")
    ap.add_argument("-i", "--interactive", action="store_true")
    ap.add_argument("--confirm", nargs=2, metavar=("PRIMARY", "OTHER"))
    ap.add_argument("--reject", nargs=2, metavar=("PRIMARY", "OTHER"))
    args = ap.parse_args()

    db = Database(str(DB_PATH))
    try:
        if args.confirm:
            bridge.set_xref_status(db, args.confirm[0], args.confirm[1], "confirmed")
            print("bestätigt."); return
        if args.reject:
            bridge.set_xref_status(db, args.reject[0], args.reject[1], "rejected")
            print("abgelehnt."); return

        lo, hi = (0.0, 1.0) if args.all else (args.lo, args.hi)
        pairs = bridge.get_xref_pairs(db, status=args.status, lo=lo, hi=hi,
                                      source=args.source)
        print(f"{len(pairs)} Querbezüge (Score {lo}–{hi}"
              f"{', '+args.status if args.status else ''}):\n")

        if args.interactive:
            for r in pairs:
                if r["status"] != "auto":
                    continue
                show(r)
                ans = input("    Dieselbe Person? [j]a / [n]ein / [s]kip / [q]uit: ").strip().lower()
                if ans == "q":
                    break
                if ans == "j":
                    bridge.set_xref_status(db, r["ged_id_primary"], r["ged_id_other"], "confirmed")
                    print("    → bestätigt")
                elif ans == "n":
                    bridge.set_xref_status(db, r["ged_id_primary"], r["ged_id_other"], "rejected")
                    print("    → abgelehnt")
                print()
        else:
            for r in pairs:
                show(r); print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
