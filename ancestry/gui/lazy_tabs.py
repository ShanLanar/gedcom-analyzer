"""
Lazy-Loading für GUI-Tabs: Tabs werden erst beim Klick instantiiert.

Das spart Startup-Zeit erheblich, da schwere Tab-Klassen nicht beim Appstart
importiert und gebaut werden, sondern nur bei Bedarf.
"""

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Type, Any

log = logging.getLogger(__name__)


class LazyTabPlaceholder(ttk.Frame):
    """Placeholder-Tab, der beim Klick die echte Tab-Klasse lädt und instantiiert."""

    def __init__(
        self,
        notebook: ttk.Notebook,
        tab_class: Type[ttk.Frame],
        tab_label: str,
        *args,
        **kwargs,
    ):
        super().__init__(notebook)
        self.notebook = notebook
        self.tab_class = tab_class
        self.tab_label = tab_label
        self.args = args
        self.kwargs = kwargs
        self._real_tab: Optional[ttk.Frame] = None
        self._loaded = False

        # Show loading message
        ttk.Label(
            self,
            text=f"⏳ {tab_label} wird geladen...",
            font=("TkDefaultFont", 12),
            foreground="#666",
        ).pack(expand=True)

        # Schedule the load when the tab becomes visible
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add=True)

    def _on_tab_changed(self, event=None):
        """Callback wenn Tab-Auswahl geändert wird."""
        if self._loaded:
            return

        current_tab = self.notebook.nametowidget(self.notebook.select())
        if current_tab is self or current_tab.winfo_children() and current_tab.winfo_children()[0] is self:
            self._load_real_tab()

    def _load_real_tab(self):
        """Lazy-lade die echte Tab-Klasse und ersetze den Placeholder."""
        if self._loaded:
            return

        try:
            log.info(f"Lazy-loading tab: {self.tab_label}")
            self._real_tab = self.tab_class(self.notebook, *self.args, **self.kwargs)
            self._real_tab.pack(fill="both", expand=True)

            # Notebook-Index dieses Tabs
            tab_index = self.notebook.index(self)

            # Ersetze Placeholder durch echte Tab
            self.notebook.forget(self)
            self.notebook.insert(tab_index, self._real_tab, text=self.tab_label)
            self.notebook.select(self._real_tab)

            self._loaded = True
            log.info(f"Tab loaded: {self.tab_label}")
        except Exception as e:
            log.exception(f"Fehler beim Laden von Tab {self.tab_label}")
            ttk.Label(
                self,
                text=(
                    f"❌ Fehler beim Laden von {self.tab_label}\n\n"
                    f"{type(e).__name__}: {e}\n\n"
                    "Details stehen im Log."
                ),
                foreground="#b00020",
                justify="left",
                padding=24,
            ).pack(anchor="nw")


def create_lazy_tab(
    notebook: ttk.Notebook,
    tab_class: Type[ttk.Frame],
    tab_label: str,
    *args,
    **kwargs,
) -> ttk.Frame:
    """Erstellt einen Lazy-Loading-Tab.

    Args:
        notebook: Parent Notebook
        tab_class: Die Klasse des echten Tabs
        tab_label: Label für den Tab
        *args, **kwargs: Argumente für tab_class()

    Returns:
        LazyTabPlaceholder (wird beim Klick durch echte Tab ersetzt)
    """
    placeholder = LazyTabPlaceholder(notebook, tab_class, tab_label, *args, **kwargs)
    notebook.add(placeholder, text=tab_label)
    return placeholder
