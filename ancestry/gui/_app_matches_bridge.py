"""Matches-Tab-Brücke-Mixin für AncestryDnaApp ('TAB 3: MATCHES').

Sechster Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Reine Delegations-Stubs an self._matches_tab — genau wie
ShortcutsMixin (_app_shortcuts.py) rufen sie nur in den bereits vorhandenen
Tab hinein und erzeugen kein eigenes Zustandsattribut.

Erwartet von der Host-Klasse (AncestryDnaApp): self._matches_tab,
self._set_status().
"""
from __future__ import annotations

from typing import Optional

from ancestry.models import DnaMatch


class MatchesBridgeMixin:
    """Delegations-Stubs für den Matches-Tab (Tabelle, Kit-Combo,
    GEDCOM-Treffer-Panel, aktuell gewählter Match)."""

    def _refresh_match_table(self, *_):
        """Delegation stub — aktualisiert die Match-Tabelle im Matches-Tab."""
        if getattr(self, "_matches_tab", None) is None:
            return  # Tab noch nicht aufgebaut (Aufruf während früherem Tab-Init)
        self._matches_tab.refresh()

    def _update_matches_kit_combo(self):
        """Delegation stub — befüllt den Kit-Selektor im Matches-Tab."""
        if getattr(self, "_matches_tab", None) is None:
            return  # Tab noch nicht aufgebaut; after(300, …) füllt später nach
        self._matches_tab.update_kit_combo()
        self._set_status("Fertig", "ok")

    def _load_gedcom_link_panel(self, match: DnaMatch):
        """Delegation stub — füllt den GEDCOM-Treffer-Tab im Matches-Tab."""
        if getattr(self, "_matches_tab", None) is None:
            return
        self._matches_tab.load_gedcom_link_panel(match)

    @property
    def _selected_match(self) -> Optional[DnaMatch]:
        """Aktuell gewählter Match — lebt im Matches-Tab."""
        tab = getattr(self, "_matches_tab", None)
        return tab.selected_match if tab is not None else None
