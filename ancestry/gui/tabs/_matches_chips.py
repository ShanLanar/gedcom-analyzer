"""Filter-Chips-Mixin für MatchesTab (Toolbar-Chips: Favorit, Baum-Link,
≥200cM, väterlich/mütterlich, neu, Quelle, geclustert).

Sechster Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Die Chip-Buttons selbst werden weiterhin
in `_build` (Konstruktor-Aufbau, bleibt in matches.py) erzeugt und in
`self._chip_vars`/`self._chip_btns` abgelegt — diese Methoden lesen und
mutieren nur deren Inhalt, definieren aber keine eigenen Attribute.

Erwartet von der Host-Klasse (MatchesTab): self._chip_vars, self._chip_btns,
self._starred_var, self._tree_var, self._min_cm_var, self._active_source,
self.refresh().
"""
from __future__ import annotations

import tkinter as tk

from ancestry.gui.widgets.theme import COLORS


class ChipFilterMixin:
    """Toolbar-Filter-Chips: Favorit, Baum, cM-Schwelle, Seite, Quelle, Cluster."""

    def _chip_starred(self):
        self._starred_var.set(self._chip_vars["star"].get())
        self.refresh()

    def _chip_tree(self):
        self._tree_var.set(self._chip_vars["tree"].get())
        self.refresh()

    def _chip_cm200(self):
        self._min_cm_var.set("200" if self._chip_vars["cm200"].get() else "0")
        self.refresh()

    def _chip_pat(self):
        if self._chip_vars["pat"].get():
            self._chip_vars["mat"].set(False)
            self._chip_btns["mat"].configure(bg=COLORS["light"], fg=COLORS["text"])
        self.refresh()

    def _chip_mat(self):
        if self._chip_vars["mat"].get():
            self._chip_vars["pat"].set(False)
            self._chip_btns["pat"].configure(bg=COLORS["light"], fg=COLORS["text"])
        self.refresh()

    def _chip_new(self):
        self.refresh()

    _SOURCE_CHIP_KEYS = ("anc", "mh", "gm", "ftd")

    def _chip_source(self, src: str):
        """Quell-Filter: nur einen Quell-Chip aktiv halten."""
        currently_active = self._active_source == src and self._chip_vars.get(
            {"ancestry": "anc", "myheritage": "mh",
             "gedmatch": "gm", "ftdna": "ftd"}.get(src, "anc"), tk.BooleanVar()
        ).get()
        # Alle Quell-Chips zurücksetzen
        key_for = {"ancestry": "anc", "myheritage": "mh",
                   "gedmatch": "gm", "ftdna": "ftd"}
        for s, k in key_for.items():
            if k in self._chip_vars:
                self._chip_vars[k].set(False)
            if k in self._chip_btns:
                self._chip_btns[k].configure(bg=COLORS["light"], fg=COLORS["text"])
        if currently_active:
            # Zweiter Klick auf denselben → deaktivieren
            self._active_source = None
        else:
            self._active_source = src
            k = key_for[src]
            if k in self._chip_vars:
                self._chip_vars[k].set(True)
            if k in self._chip_btns:
                self._chip_btns[k].configure(bg=COLORS["primary"], fg=COLORS["white"])
        self.refresh()

    def _chip_clustered(self):
        self.refresh()

    def _toggle_chip(self, key: str, cmd):
        new_val = not self._chip_vars[key].get()
        self._chip_vars[key].set(new_val)
        btn = self._chip_btns[key]
        if new_val:
            btn.configure(bg=COLORS["primary"], fg=COLORS["white"])
        else:
            btn.configure(bg=COLORS["light"], fg=COLORS["text"])
        cmd()
