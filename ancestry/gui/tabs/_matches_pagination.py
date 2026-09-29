"""Seiten-Navigation-Mixin für MatchesTab (P3/S2-6): Vor-/Zurück-Blättern
und scroll-getriggerte Pagination der Match-Tabelle.

Dreizehnter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Reine Navigation über bereits in __init__/
_fill_match_table gesetzte Zustandsattribute — keine eigenen.

Erwartet von der Host-Klasse (MatchesTab): self._current_offset,
self._has_next_page, self._MAX_DISPLAY_ROWS, self._match_count_var,
self._tree, self._do_refresh().
"""
from __future__ import annotations


class PaginationMixin:
    """Vor-/Zurück-Blättern und scroll-getriggerte Pagination der Match-Tabelle."""

    # ── P3: Seiten-Navigation (Pagination) ──────────────────────────────────
    def _page_next(self):
        """Nächste Seite — nur wenn aktuelle Seite voll war (mehr Treffer da)."""
        if getattr(self, "_has_next_page", False):
            self._current_offset += self._MAX_DISPLAY_ROWS
            page = self._current_offset // self._MAX_DISPLAY_ROWS + 1
            if hasattr(self, "_match_count_var"):
                self._match_count_var.set(f"Lade Seite {page} …")
            self._do_refresh()

    def _page_prev(self):
        if self._current_offset > 0:
            self._current_offset = max(0, self._current_offset - self._MAX_DISPLAY_ROWS)
            page = self._current_offset // self._MAX_DISPLAY_ROWS + 1
            if hasattr(self, "_match_count_var"):
                self._match_count_var.set(f"Lade Seite {page} …")
            self._do_refresh()

    # ── S2-6: Scroll-getriggerte Pagination ─────────────────────────────────

    def _on_match_scroll(self, event):
        """Windows-Mausrad: delta > 0 = nach oben, < 0 = nach unten."""
        if event.delta < 0:
            self._on_match_scroll_down(event)
        else:
            self._on_match_scroll_up(event)

    def _on_match_scroll_up(self, event):
        """Scroll past first row → previous page."""
        if not self._tree.get_children():
            return
        if self._tree.yview()[0] <= 0.0:
            self._page_prev()

    def _on_match_scroll_down(self, event):
        """Scroll past last row → next page."""
        if not self._tree.get_children():
            return
        if self._tree.yview()[1] >= 1.0:
            self._page_next()
