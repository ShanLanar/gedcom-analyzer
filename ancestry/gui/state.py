"""Gemeinsamer Laufzeitstatus für alle GUI-Tabs."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from ancestry.core.database import Database
from ancestry.gui.widgets.theme import COLORS, COLORS_DARK, translate


@dataclass
class AppState:
    """Hält alle Daten, die mehr als ein Tab benötigt.

    Tabs erhalten im Konstruktor eine Referenz auf diese Instanz und
    registrieren ihre sprachreaktiven Widgets in den lang_*-Listen.
    """

    db: Database

    # Laufzeitstatus (mutable)
    lang:              str   = "de"
    dark_mode:         bool  = False

    # Sprach-Registrierungs-Listen — werden von _apply_lang in app.py ausgelesen
    lang_widgets:       list = field(default_factory=list)   # (widget_or_sv, key[, suffix])
    lang_headings:      list = field(default_factory=list)   # (tv, col, key)
    lang_nb_tabs:       list = field(default_factory=list)   # (frame, key)
    lang_menus:         list = field(default_factory=list)   # (menu, index, key)
    lang_inner_nb_tabs: list = field(default_factory=list)   # (notebook, frame, key)
    lang_tooltips:      list = field(default_factory=list)   # (Tooltip, key)

    # Download-Thread-Koordination
    pause_event: threading.Event = field(default_factory=lambda: _set_event())

    # Shared runtime state
    auth:               Optional[object] = None
    client:             Optional[object] = None
    scraper:            Optional[object] = None
    kit_map:            dict             = field(default_factory=dict)
    matches_kit_guid_map: dict           = field(default_factory=dict)
    matches:            list             = field(default_factory=list)
    current_test_guid:  Optional[str]    = None
    startup_gedcom_path: str             = ""

    dl_counters: dict  = field(default_factory=lambda: {"matches": 0, "trees": 0, "shared": 0, "errors": 0})
    dl_t0:       float = 0.0
    dl_total:    int   = 1

    # Daten-Änderungs-Listener (Download, Import)
    _data_change_listeners: list = field(default_factory=list)

    def register_data_change(self, cb: Callable) -> None:
        """Registriert einen Callback für Datenänderungen (Download, Import)."""
        self._data_change_listeners.append(cb)

    def notify_data_changed(self, source: str = "") -> None:
        """Benachrichtigt alle Listener über eine Datenänderung."""
        for cb in self._data_change_listeners:
            try:
                cb(source)
            except Exception:
                pass

    def t(self, key: str) -> str:
        return translate(key, self.lang)

    def colors(self) -> dict:
        return COLORS_DARK if self.dark_mode else COLORS


def _set_event() -> threading.Event:
    e = threading.Event()
    e.set()
    return e
