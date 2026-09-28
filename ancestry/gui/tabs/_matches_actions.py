"""Detail-Panel-Aktionen-Mixin für MatchesTab: Chromosomen-Browser,
Aufgaben-Dialog, Ancestry-/FamilySearch-Links öffnen, Notiz und
Recherche-Checkliste speichern.

Siebter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Sechs kleine, unabhängige Aktionen des
Detail-Panels, alle an den aktuell gewählten Match gebunden. Keine
eigenen Zustandsattribute.

Erwartet von der Host-Klasse (MatchesTab): self._selected_match,
self._state, self._get_test_guid(), self._set_status(), self._note_text,
self._checklist_vars.
"""
from __future__ import annotations

import logging
import webbrowser
from tkinter import messagebox
from urllib.parse import quote

log = logging.getLogger(__name__)


class DetailActionsMixin:
    """Chromosomen-Browser, Aufgaben, externe Links, Notiz/Checkliste speichern."""

    def _open_chromosome_browser(self):
        """Öffnet den Chromosomen-Browser (B4) für den ausgewählten Match."""
        if not self._selected_match:
            return
        test_guid = self._get_test_guid()
        if not test_guid:
            return
        try:
            from ancestry.gui.analysis.chromosome_browser import show_chromosome_browser
            show_chromosome_browser(self, self._state, test_guid,
                                    self._selected_match.match_guid,
                                    self._selected_match.display_name or "")
        except Exception as e:
            log.debug("chromosome browser: %s", e)

    def _open_match_tasks(self):
        """Öffnet den Aufgaben-Dialog (B1), eingeschränkt auf den Match."""
        if not self._selected_match:
            return
        try:
            from ancestry.gui.analysis.research_tasks_view import show_research_tasks
            show_research_tasks(self, self._state, entity_type="match",
                                entity_key=self._selected_match.match_guid,
                                entity_label=self._selected_match.display_name or "")
        except Exception as e:
            log.debug("match tasks: %s", e)

    def _open_in_ancestry(self):
        """Öffnet den aktuellen Match in Ancestry im Browser."""
        if not self._selected_match:
            return
        test_guid  = self._get_test_guid()
        match_guid = self._selected_match.match_guid
        if not test_guid or not match_guid:
            return
        url = (f"https://www.ancestry.com/discoveryui-matches/compare"
               f"/{test_guid}/with/{match_guid}")
        webbrowser.open(url)
        self._set_status(f"Ancestry geöffnet: {self._selected_match.display_name}")

    def _save_note(self):
        if not self._selected_match: return
        note = self._note_text.get("1.0","end").strip()
        self._state.db.update_note(self._selected_match.match_guid, note)
        self._selected_match.note = note
        self._set_status(f"Notiz gespeichert: {self._selected_match.display_name}")

    def _save_checklist(self, changed_index: int):
        """Save research checklist state as bitmask to DB."""
        if not self._selected_match:
            return
        flags = sum(1 << i for i, v in enumerate(self._checklist_vars) if v.get())
        try:
            self._state.db.update_research_flags(self._selected_match.match_guid, flags)
        except Exception as e:
            log.debug("Checklist speichern: %s", e)

    def _open_familysearch(self):
        """Search FamilySearch for the selected match's name."""
        if not self._selected_match:
            return
        name = self._selected_match.display_name or ""
        if not name or name in ("Anonym", "?"):
            messagebox.showinfo(self._state.t("mf.no_name_t"), self._state.t("mf.m_no_name"))
            return
        url = f"https://www.familysearch.org/search/record/results?q.surname={quote(name.split()[-1])}"
        webbrowser.open(url)
