"""Statistik-Tab-Brücke-Mixin für AncestryDnaApp ('TAB 5: STATISTIKEN').

Siebter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Reine Delegations-Stubs an self._stats_tab, gleiches Muster
wie MatchesBridgeMixin (_app_matches_bridge.py).

Erwartet von der Host-Klasse (AncestryDnaApp): self._state (AppState),
self._stats_tab, self._nb (ttk.Notebook).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class StatsBridgeMixin:
    """Delegations-Stubs für den Statistik-Tab (Invalidierung + Lazy-Neuberechnung)."""

    def _refresh_stats(self):
        # Nach einem Download: Statistik als veraltet markieren und alle
        # Listener benachrichtigen; on_show() sorgt für Neuberechnung beim
        # nächsten Öffnen des Reiters (oder sofort, wenn er gerade sichtbar ist).
        self._state.notify_data_changed("download")

    def _on_nb_tab_changed(self, _evt=None):
        """Berechnet die Statistik beim Öffnen des Statistik-Reiters
        (nur wenn als veraltet markiert — siehe StatsTab.on_show())."""
        tab = getattr(self, "_stats_tab", None)
        if tab is None:
            return
        try:
            if self._nb.nametowidget(self._nb.select()) is tab:
                tab.on_show()
        except Exception as e:
            log.debug("nb tab-changed stats on_show: %s", e)

    def _invalidate_stats(self):
        """Markiert die Statistik als veraltet (z. B. nach GEDCOM-Änderung)
        und berechnet sofort neu, falls der Reiter gerade sichtbar ist."""
        tab = getattr(self, "_stats_tab", None)
        if tab is None:
            return
        tab.mark_dirty()
        try:
            if self._nb.nametowidget(self._nb.select()) is tab:
                tab.on_show()
        except Exception as e:
            log.debug("invalidate_stats on_show: %s", e)
