"""Wiederverwendbarer Hover-Tooltip für Tkinter-Widgets.

Verwendung:
    from ancestry.gui.widgets.tooltip import tooltip
    tooltip(my_button, "Was dieser Button tut")

Der Tooltip erscheint nach kurzer Verzögerung beim Überfahren und verschwindet
beim Verlassen oder Klick. Bewusst robust gehalten (defensives try/except), damit
ein Tooltip nie die eigentliche Bedienung stören kann.
"""
from __future__ import annotations

import tkinter as tk


class Tooltip:
    """Bindet einen Hover-Tooltip an ein Widget."""

    def __init__(self, widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        try:
            self._after_id = self.widget.after(self.delay, self._show)
        except Exception:
            self._after_id = None

    def _show(self):
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{int(x)}+{int(y)}")
            tk.Label(tip, text=self.text, justify="left",
                     background="#ffffe0", foreground="#222222",
                     relief="solid", borderwidth=1,
                     font=("Segoe UI", 8)).pack(ipadx=4, ipady=2)
            self._tip = tip
        except Exception:
            # Im Zweifel lieber keinen Tooltip als einen Absturz
            self._tip = None

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


def tooltip(widget, text: str, delay: int = 500) -> Tooltip:
    """Bequemer Helfer: hängt einen Tooltip mit festem Text an ``widget``."""
    return Tooltip(widget, text, delay)


def register_tooltip(widget, key: str, state, delay: int = 500) -> Tooltip:
    """Zweisprachiger Tooltip über das Übersetzungssystem.

    Liest den Text aus ``translate(key, state.lang)`` und registriert den
    Tooltip in ``state.lang_tooltips``, damit _apply_lang() ihn beim
    Sprachwechsel (de/en) aktualisiert.
    """
    from ancestry.gui.widgets.theme import translate
    lang = getattr(state, "lang", "de")
    tip = Tooltip(widget, translate(key, lang), delay)
    try:
        state.lang_tooltips.append((tip, key))
    except AttributeError:
        pass
    return tip
