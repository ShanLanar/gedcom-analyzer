"""Tastatur-Navigation + Spalten-Persistenz-Mixin für MatchesTab (U1/U3).

Vierzehnter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Pfeiltasten-Navigation in der Match-
Tabelle, Escape-Reset des Suchfelds, Spaltenbreiten-Persistenz bei
Resize sowie der statische Stammbaum-Status-Text-Helfer. Keine eigenen
Zustandsattribute.

Erwartet von der Host-Klasse (MatchesTab): self._tree, self._search_var,
self._save_ui_settings(), self._pref_set(), self.refresh().
"""
from __future__ import annotations


class TreeNavigationMixin:
    """Pfeiltasten-/Escape-Navigation, Spaltenbreiten-Persistenz, Stammbaum-Text."""

    def _on_tree_configure(self, _event):
        """U3: Speichert Spaltenbreiten bei Resize-Events."""
        widths = {}
        for col in ("name","guid","note","cm","seg","rel","tree","ged","ca","starred","side"):
            widths[col] = self._tree.column(col, "width")
        self._save_ui_settings(column_widths=widths)
        # A1: auch in user_prefs persistieren
        for col, w in widths.items():
            self._pref_set(f"matches_col_{col}", str(w))

    def _on_escape_pressed(self):
        """U1: Escape-Taste leert Suche-Feld und resetiert Filter."""
        self._search_var.set("")
        self.refresh()

    def _on_prev_match(self):
        """U1: Linke Pfeiltaste: Vorheriger Match."""
        sel = self._tree.selection()
        if not sel:
            return
        children = self._tree.get_children()
        try:
            idx = children.index(sel[0])
            if idx > 0:
                prev_item = children[idx - 1]
                self._tree.selection_set(prev_item)
                self._tree.see(prev_item)
        except (ValueError, IndexError):
            pass

    def _on_next_match(self):
        """U1: Rechte Pfeiltaste: Nächster Match."""
        sel = self._tree.selection()
        if not sel:
            return
        children = self._tree.get_children()
        try:
            idx = children.index(sel[0])
            if idx < len(children) - 1:
                next_item = children[idx + 1]
                self._tree.selection_set(next_item)
                self._tree.see(next_item)
        except (ValueError, IndexError):
            pass

    @staticmethod
    def _tree_detail_text(match) -> str:
        status = getattr(match, "tree_status", "") or ""
        if status and match.tree_size:
            return f"{status} ({match.tree_size} Personen)"
        if status:
            return status
        if match.has_tree:
            return f"Ja ({match.tree_size})" if match.tree_size else "Ja"
        return "Nein"
