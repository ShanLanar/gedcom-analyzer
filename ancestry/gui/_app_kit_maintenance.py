"""Kit-/Link-Wartungs-Mixin für AncestryDnaApp: aktiver Kit-GUID,
GEDCOM-Einstellungen neu wählen, 'View in tree'-Links nachziehen,
Fehlversuch-/Shared-Matches-Reset.

Dreizehnter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für
die Begründung). `_current_guid` wird von vielen anderen Mixins aufgerufen
(analysis dialogs, genealogy export …) — das ändert nichts an der
Extrahierbarkeit, da `self._current_guid()` per MRO aufgelöst wird,
unabhängig davon welche Basisklasse die Methode definiert.
`self._scraper = Scraper(...)` in `_refresh_links` ist eine Neuzuweisung
des in `__init__` initialisierten Attributs (`self._scraper = None`),
genau wie bereits in AnalysisDialogsMixin._run_deepen_pedigrees.

Erwartet von der Host-Klasse (AncestryDnaApp): self._download_tab,
self._state, self._db, self._client, self._names_stop_btn, self._scraper,
self._gedcom, self._t(), self._set_status(), self._get_kit_guid(),
self._on_progress(), self._refresh_match_table(), self._ensure_gedcom_loaded().
"""
from __future__ import annotations

from tkinter import messagebox

from ancestry.core.scraper import Scraper


class KitMaintenanceMixin:
    """Aktiver Kit-GUID, Link-Refresh, Reset-Aktionen (Namen/Shared Matches)."""

    def _current_guid(self):
        dl = self._download_tab.get_kit_guid() if self._download_tab else None
        return dl or self._state.current_test_guid

    def _change_gedcom_settings(self):
        """GEDCOM-Datei + Wurzelperson neu wählen (überschreibt die gemerkten)."""
        self._gedcom = None   # Cache verwerfen → Neuladen
        self._ensure_gedcom_loaded(
            lambda ged: self._set_status(
                f"GEDCOM/Wurzelperson gesetzt: {len(ged['people'])} Personen, "
                f"{len(ged['amap'])} Vorfahren auf deiner Linie."),
            force_ask=True)

    def _refresh_links(self):
        """Zieht 'View in tree' + gemeinsamer Vorfahr für ALLE Matches nach."""
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        if not self._client:
            messagebox.showwarning(self._t("dlg.not_logged"), self._t("dlg.m_login_first"))
            return
        self._state.current_test_guid = guid
        self._names_stop_btn.configure(state="normal")
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: (
                                    self._names_stop_btn.configure(state="disabled"),
                                    self._refresh_match_table(),
                                    messagebox.showinfo(self._t("dlg.links"), r.message))))
        self._scraper.start_refresh_links(guid)

    def _reset_name_attempts(self):
        """Setzt die Fehlversuch-Zähler zurück, damit übersprungene Profile beim
        nächsten 'Namen laden' erneut versucht werden."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        n = self._db.reset_name_attempts(test_guid)
        self._set_status(f"Namens-Versuche zurückgesetzt: {n} Matches.")
        messagebox.showinfo(self._t("dlg.reset_done"),
            f"{n} Matches werden beim nächsten 'Namen & Stammbaum laden' "
            "erneut versucht.")

    def _reset_shared_matches(self):
        """Leert die Shared-Matches-Tabelle (alte, mit falschem Endpunkt geladene
        Daten) – danach Schritt B neu ausführen."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        if not messagebox.askyesno(
                self._t("dlg.reset_shared"),
                self._t("dlg.m_reset_shared")):
            return
        n = self._db.reset_shared_matches(test_guid)
        self._set_status(f"Shared Matches zurückgesetzt: {n} Zeilen gelöscht.")
        messagebox.showinfo(self._t("dlg.reset_done"),
            f"{n} Shared-Match-Zeilen gelöscht.\n"
            "Jetzt Schritt B (Shared Matches herunterladen) neu starten.")
