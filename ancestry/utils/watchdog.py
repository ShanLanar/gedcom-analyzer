"""Hang-Watchdog: erkennt ein eingefrorenes GUI und schreibt einen Stack-Dump.

Hintergrund: friert die Tkinter-Hauptschleife ein (langer synchroner Aufruf
auf dem Main-Thread), zeigt Windows nur noch „Keine Rückmeldung" — ohne Hinweis,
WO es hängt. Dieser Watchdog macht das sichtbar:

* Der Main-Thread ruft im Sekundentakt :func:`beat` auf (Tk-``after``-Herzschlag).
* Ein Hintergrund-Thread prüft, ob der letzte Herzschlag zu lange her ist.
  Ist das GUI länger als ``timeout`` Sekunden stumm, kippt er ALLE Thread-Stacks
  (inkl. Main-Thread = die hängende Stelle) in ``hang_traceback.log``.

Rein diagnostisch, ändert kein Verhalten. Der Thread ist ein Daemon und kostet
im Normalbetrieb nichts außer einem schlafenden Thread.
"""
from __future__ import annotations

import faulthandler
import threading
import time

# monotonic() ist in Skripten hier verfügbar; wird nur im Prozess verwendet.
_last_beat = [time.monotonic()]
_armed = [False]


def beat() -> None:
    """Vom GUI-Main-Thread im Sekundentakt aufrufen (Lebenszeichen)."""
    _last_beat[0] = time.monotonic()


def arm(logfile: str, timeout: float = 30.0, check_every: float = 2.0) -> None:
    """Startet den Watchdog einmalig. ``logfile`` wird bei einem Freeze
    beschrieben (überschrieben pro Freeze-Fenster)."""
    if _armed[0]:
        return
    _armed[0] = True
    # Startzeitpunkt als erster „Herzschlag": auch ein Hänger BEIM Aufbau
    # (bevor das erste Tk-``after`` läuft) wird so erkannt.
    _last_beat[0] = time.monotonic()

    def _watch() -> None:
        dumped = False
        while True:
            time.sleep(check_every)
            stale = time.monotonic() - _last_beat[0]
            if stale > timeout:
                if not dumped:      # nur einmal je Freeze-Fenster schreiben
                    try:
                        with open(logfile, "w", encoding="utf-8") as f:
                            f.write(
                                f"=== GUI eingefroren: seit {stale:.0f}s kein "
                                f"Herzschlag vom Main-Thread ===\n"
                                "Der Main-Thread-Stack unten zeigt die hängende "
                                "Stelle:\n\n"
                            )
                            faulthandler.dump_traceback(file=f, all_threads=True)
                    except Exception:
                        pass
                    dumped = True
            else:
                dumped = False      # GUI wieder lebendig → nächsten Freeze erneut dumpen

    threading.Thread(target=_watch, daemon=True, name="hang-watchdog").start()
