"""Globale Statusleiste — zeigt App-Zustände (Bereit / Lädt / Warnung / Fehler)."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

_COLORS = {
    "ok":      "#217A3C",
    "warn":    "#C85000",
    "error":   "#B00000",
    "default": "#666666",
}


class StatusBar(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._var = tk.StringVar(value="Bereit")
        self._lbl = tk.Label(self, textvariable=self._var,
                             anchor="w", font=("Segoe UI", 8),
                             fg=_COLORS["default"], bg=self.cget("bg"),
                             padx=8, pady=2)
        self._lbl.pack(fill="x")

    def set(self, msg: str, level: str = "default"):
        self._var.set(msg)
        self._lbl.configure(fg=_COLORS.get(level, _COLORS["default"]))

    def clear(self):
        self.set("Bereit", "default")
