"""Tastaturkürzel-Mixin für AncestryDnaApp.

Zweiter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Als zweiten Kandidaten gewählt, weil es reine dünne
Delegations-Wrapper sind — kein eigenes Zustandsattribut, nur Aufrufe in
den aktiven Tab bzw. andere bereits vorhandene App-Methoden hinein.

Erwartet von der Host-Klasse (AncestryDnaApp): self._nb (ttk.Notebook),
self._matches_tab, self._selected_match, self._export_all_xlsx,
self._export_xlsx.
"""
from __future__ import annotations

from tkinter import ttk


class ShortcutsMixin:
    """Tastaturkürzel: Suche fokussieren, Tab aktualisieren, Filter leeren, Export."""

    def _active_tab(self):
        """Gibt die aktuell sichtbare Tab-Instanz zurück (oder None)."""
        try:
            return self._nb.nametowidget(self._nb.select())
        except Exception:
            return None

    def _bind_shortcuts(self):
        root = self.winfo_toplevel()
        # A3: Tastaturkürzel
        self.bind_all("<Control-f>", lambda _: self._shortcut_focus_search())
        self.bind_all("<F5>",        lambda _: self._shortcut_refresh())
        self.bind_all("<Escape>",    lambda _: self._shortcut_clear_filter())
        self.bind_all("<Control-e>", lambda _: self._shortcut_export())
        # Ältere globale Kürzel beibehalten
        root.bind("<Control-E>", lambda _: self._export_all_xlsx())
        root.bind("<Control-m>", lambda _: self._shortcut_toggle_star())

    def _refresh_current_tab(self):
        """F5: aktuellen Tab aktualisieren."""
        try:
            tab = self._nb.nametowidget(self._nb.select())
            if hasattr(tab, "refresh"):
                tab.refresh()
            elif hasattr(tab, "_refresh"):
                tab._refresh()
        except Exception:
            pass

    def _shortcut_toggle_star(self):
        """Ctrl+M: ausgewählten Match markieren/demarkieren."""
        try:
            if self._selected_match and self._matches_tab is not None:
                self._matches_tab._toggle_starred_match(self._selected_match)
        except Exception:
            pass

    def _shortcut_focus_search(self):
        """Ctrl+F: Suchfeld im aktiven Tab fokussieren (oder Matches-Tab als Fallback)."""
        try:
            tab = self._active_tab()
            fn = getattr(tab, "focus_search", None)
            if callable(fn):
                fn()
                return
            # Fallback: Matches-Tab-Suchfeld direkt suchen
            if self._matches_tab is not None and hasattr(self._matches_tab, "_search_var"):
                def _find_entry(w):
                    for c in w.winfo_children():
                        if isinstance(c, ttk.Entry):
                            return c
                        found = _find_entry(c)
                        if found:
                            return found
                    return None
                entry = _find_entry(self._matches_tab)
                if entry:
                    entry.focus_set()
        except Exception:
            pass

    def _shortcut_refresh(self):
        """F5: on_show() oder refresh() des aktiven Tabs aufrufen."""
        try:
            tab = self._active_tab()
            fn = getattr(tab, "on_show", None) or getattr(tab, "refresh", None)
            if callable(fn):
                fn()
        except Exception:
            pass

    def _shortcut_clear_filter(self):
        """Escape: clear_filter() des aktiven Tabs aufrufen."""
        try:
            tab = self._active_tab()
            fn = getattr(tab, "clear_filter", None)
            if callable(fn):
                fn()
        except Exception:
            pass

    def _shortcut_export(self):
        """Ctrl+E: export_current() des aktiven Tabs aufrufen; Fallback: XLSX-Export."""
        try:
            tab = self._active_tab()
            fn = getattr(tab, "export_current", None)
            if callable(fn):
                fn()
            else:
                self._export_xlsx()
        except Exception:
            pass
