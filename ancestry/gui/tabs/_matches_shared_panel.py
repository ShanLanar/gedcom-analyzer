"""Shared-Matches-Panel-Mixin für MatchesTab: lädt und zeigt die Shared
Matches des aktuell ausgewählten primären Matches im Detail-Panel.

Fünfzehnter und letzter Baustein der Mixin-Aufteilung (siehe MatchesTab-
Docstring in matches.py für die Übersicht) — der verbleibende Rest von
MatchesTab (__init__, `_build*`, `_fill_match_table`, `_on_match_select`
als zentraler Dispatcher) ist untrennbar mit dem Konstruktor bzw.
miteinander verwoben. Keine eigenen Zustandsattribute.

Erwartet von der Host-Klasse (MatchesTab): self._state, self._get_test_guid(),
self._selected_match, self._sm_count_var, self._sm_tree.
"""
from __future__ import annotations

import threading

from ancestry.models import DnaMatch


class SharedPanelMixin:
    """Lädt und befüllt das Shared-Matches-Panel des Detail-Bereichs."""

    def _load_shared_panel(self, match: DnaMatch):
        """Lädt Shared Matches für den ausgewählten primären Match (im Hintergrund)."""
        test_guid = self._get_test_guid()
        if not test_guid:
            return
        self._sm_count_var.set("…")
        def _worker():
            shared = self._state.db.get_shared_matches(test_guid, match.match_guid)
            self.after(0, lambda: self._fill_shared_panel(match, shared, test_guid))
        threading.Thread(target=_worker, daemon=True).start()

    def _fill_shared_panel(self, match: DnaMatch, shared, test_guid: str):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != match.match_guid:
            return
        self._sm_tree.delete(*self._sm_tree.get_children())
        if not shared:
            fetched = self._state.db.is_shared_fetched(test_guid, match.match_guid)
            self._sm_count_var.set(
                "Shared Matches wurden abgefragt, aber keine gefunden."
                if fetched else
                "Noch nicht heruntergeladen. → Tab »Herunterladen« → Schritt B"
            )
            return
        self._sm_count_var.set(f"{len(shared)} Shared Match(es) mit {match.display_name}")
        for sm in shared:
            self._sm_tree.insert("", "end", values=(
                sm.display_name_b or "(unbekannt)",
                f"{sm.shared_cm_b:.0f}" if sm.shared_cm_b else "—",
                f"{sm.shared_cm_ab:.0f}" if sm.shared_cm_ab else "—",
                sm.relationship_b or "—",
            ))
