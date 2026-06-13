"""Globales Hell/Dunkel-Umschalten für die Genealogie-Suite.

Start- und Stammbaum-Auswertung-Reiter nutzen rohe tk-Widgets mit fest gesetzten
Dunkelfarben (config.py / cfg.*). Ein Live-Wechsel auf Light geht daher nur per
Farb-Substitution über den Widgetbaum: bekannte Dunkel-Hex werden gegen die
entsprechenden Hell-Hex getauscht (und umgekehrt). Pro Widget abgesichert –
schlimmstenfalls bleibt ein Widget unverfärbt, es crasht nichts.

Die DNA-Matches-App themt sich selbst über ttk-Styles (set_theme); deren Farben
stehen NICHT in dieser Map und werden vom Rethemer nicht angefasst.
"""
from __future__ import annotations

# Dunkel-Hex (wie in config.py)  →  Hell-Hex (Schema wie DNA-Matches Light)
_DARK_TO_LIGHT = {
    "#1e1e2e": "#f0f4f8",   # BG     Fensterhintergrund
    "#2a2a3e": "#ffffff",   # BG2    Panels/Karten
    "#232336": "#e3e9f2",   # BG3    Eingabefelder
    "#7c7cf8": "#1f4e79",   # ACCENT
    "#50fa7b": "#2e7d32",   # GREEN
    "#ff5555": "#c62828",   # RED
    "#f1fa8c": "#b58b00",   # YELLOW
    "#ffb86c": "#e07b00",   # ORANGE
    "#cdd6f4": "#1a1a2e",   # FG     Text
    "#6c7086": "#5a6072",   # FG_DIM
}
_LIGHT_TO_DARK = {v: k for k, v in _DARK_TO_LIGHT.items()}

# tk-Optionen, die eine Farbe tragen können
_COLOR_OPTS = (
    "background", "bg", "foreground", "fg",
    "highlightbackground", "highlightcolor",
    "insertbackground", "selectbackground", "selectforeground",
    "activebackground", "activeforeground", "disabledforeground",
    "troughcolor", "readonlybackground",
)


def _map(to_light: bool) -> dict:
    return _DARK_TO_LIGHT if to_light else _LIGHT_TO_DARK


def _retheme_widget(w, cmap: dict) -> None:
    for opt in _COLOR_OPTS:
        try:
            cur = str(w.cget(opt)).lower()
        except Exception:
            continue
        if cur in cmap:
            try:
                w.configure(**{opt: cmap[cur]})
            except Exception:
                pass


def retheme_tree(widget, to_light: bool) -> None:
    """Färbt widget und alle Kinder rekursiv um (Dunkel↔Hell)."""
    cmap = _map(to_light)
    stack = [widget]
    while stack:
        w = stack.pop()
        _retheme_widget(w, cmap)
        try:
            stack.extend(w.winfo_children())
        except Exception:
            pass
