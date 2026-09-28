"""Zeilen-Aktionen-Mixin für MatchesTab: Endogamie-Cluster-Zuweisung,
manuelle Beziehungs-/Namens-Korrektur, Favoriten-Stern (mit Undo).

Zehnter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Alle Methoden bearbeiten einen einzelnen
Match-Datensatz (aus dem Kontextmenü, das in `_on_match_rightclick`
bleibt) und rufen danach `_refresh_and_reselect`, damit Auswahl und
Scroll-Position erhalten bleiben. `self._pending_reselect` wird hier
gesetzt, aber ausschließlich in `_fill_match_table` (bleibt in
matches.py) gelesen und zurückgesetzt.

Erwartet von der Host-Klasse (MatchesTab): self._state, self._get_test_guid(),
self._set_status(), self._do_refresh(), self._load_ui_settings()/
self._save_ui_settings(), self._ged_link_var (nicht hier verwendet, nur
zur Vollständigkeit der Nachbarmethoden).
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

log = logging.getLogger(__name__)

try:
    from ancestry.gui.undo import UndoStack as _UndoStack
    _UNDO = _UndoStack.get()
except Exception:
    _UNDO = None


class RowActionsMixin:
    """Endogamie-Cluster, manuelle Beziehung/Name, Favoriten-Stern (mit Undo)."""

    def _set_endogamy_cluster(self, match):
        """Dialog: Endogamie-Cluster-Namen eingeben oder aus bekannten wählen."""
        known = self._load_ui_settings().get("endogamy_clusters", [])
        current = getattr(match, "endogamy_cluster", "") or ""

        dlg = tk.Toplevel(self)
        dlg.title("Endogamie-Cluster zuweisen")
        dlg.geometry("420x180")
        dlg.grab_set()
        dlg.resizable(False, False)

        ttk.Label(dlg, text=f"Match: {match.display_name}",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(12,2))
        ttk.Label(dlg,
                  text="Cluster-Name (z. B. 'Ostercappeln/Seymour') — "
                       "leer lassen zum Entfernen:").pack(anchor="w", padx=14)

        var = tk.StringVar(value=current)
        cb = ttk.Combobox(dlg, textvariable=var, values=known, width=38)
        cb.pack(padx=14, pady=8, fill="x")
        cb.focus()

        def _save():
            name = var.get().strip()
            self._state.db.set_endogamy_cluster(match.match_guid, name)
            match.endogamy_cluster = name
            if name and name not in known:
                known.append(name)
                self._save_ui_settings(endogamy_clusters=known)
            self._refresh_and_reselect(match.match_guid)
            dlg.destroy()

        bf = ttk.Frame(dlg); bf.pack(anchor="e", padx=14, pady=4)
        ttk.Button(bf, text=self._state.t("dlg.cancel"), command=dlg.destroy).pack(side="left", padx=4)
        ttk.Button(bf, text=self._state.t("dlg.save"), command=_save).pack(side="left")
        dlg.bind("<Return>", lambda _: _save())

    def _clear_endogamy_cluster(self, match):
        self._state.db.set_endogamy_cluster(match.match_guid, "")
        match.endogamy_cluster = ""
        self._refresh_and_reselect(match.match_guid)

    def _auto_flag_endogamy(self):
        """Markiert Endogamie-verdächtige Matches (viele kurze Segmente)
        automatisch als endogamy_cluster='(auto)'."""
        guid = self._get_test_guid()
        if not guid:
            messagebox.showwarning(self._state.t("dlg.no_kit"),
                                   self._state.t("dlg.m_choose_kit"))
            return
        n = self._state.db.auto_flag_endogamy(guid)
        self.refresh()
        self._set_status(self._state.t("mf.endo_auto_done").format(n=n))
        messagebox.showinfo(self._state.t("mf.endo_auto"),
                            self._state.t("mf.endo_auto_done").format(n=n))

    def _refresh_and_reselect(self, guid: str):
        """Aktualisiert die Tabelle und stellt Auswahl + Scroll-Position wieder her,
        damit man nach einer Bearbeitung tief in der Liste nicht den Platz verliert.
        Die Tabelle wird asynchron befüllt — die Auswahl setzt _fill_match_table."""
        self._pending_reselect = guid
        # Seite NICHT zurücksetzen — der bearbeitete Match liegt auf der
        # aktuellen Seite und soll sichtbar bleiben.
        self._do_refresh()

    def _set_custom_rel(self, match, rel: str):
        self._state.db.update_note(match.match_guid,
                                   match.note or "")
        with self._state.db._cursor() as cur:
            cur.execute("UPDATE matches SET custom_relationship=? WHERE match_guid=?",
                        (rel, match.match_guid))
        self._set_status(f"{match.display_name} → {rel}")
        self._refresh_and_reselect(match.match_guid)

    def _prompt_name(self, match):
        """Einfacher Dialog um einen Namen manuell einzutragen."""
        import tkinter.simpledialog as sd
        name = sd.askstring(
            "Name eintragen",
            "Name eintragen (cM: " + str(round(match.shared_cm)) + ")",
            initialvalue=match.display_name if match.display_name != "Anonym" else "",
            parent=self,
        )
        if name is not None and name.strip():
            with self._state.db._cursor() as cur:
                cur.execute("UPDATE matches SET display_name=? WHERE match_guid=?",
                            (name.strip(), match.match_guid))
            self._set_status(f"Name gespeichert: {name.strip()}")
            self._refresh_and_reselect(match.match_guid)

    def _toggle_starred_match(self, match):
        """Toggles the starred flag for a match and updates the table display."""
        try:
            old_starred = bool(match.starred)
            new_state = self._state.db.toggle_starred(match.match_guid)
            match.starred = new_state
            status_label = "Zu Favoriten hinzugefügt" if new_state else "Aus Favoriten entfernt"
            self._set_status(f"{match.display_name}: {status_label}")
            self._refresh_and_reselect(match.match_guid)
            if _UNDO is not None:
                _name = getattr(match, "display_name", str(match.match_guid))
                _was = old_starred
                _now = new_state
                _m = match
                _UNDO.push(
                    f"Stern {'setzen' if _now else 'entfernen'}: {_name}",
                    lambda: self._set_starred(_m, _was),
                    lambda: self._set_starred(_m, _now),
                )
        except Exception as e:
            log.warning("toggle_starred failed: %s", e)

    def _set_starred(self, match, value: bool):
        """Setzt den Stern-Status ohne Undo-Eintrag (für Undo/Redo)."""
        try:
            self._state.db.set_match_starred(match.match_guid, value)
            match.starred = value
            self._do_refresh()
        except Exception as e:
            log.debug("_set_starred: %s", e)
