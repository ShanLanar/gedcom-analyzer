"""'Zuletzt geöffnet'-Mixin für AncestryDnaApp (D1).

Erster Baustein der Mixin-Aufteilung von AncestryDnaApp
(ancestry/gui/app.py) — reine Wartbarkeits-Refaktorierung, keine
Verhaltensänderung. Als ersten Kandidaten gewählt, weil er nur ein eigenes
Attribut braucht (_recent_menu, von _build_menu angelegt) und reine
Datei-I/O + Menü-Rebuild macht, ohne selbst zentrale App-Attribute zu
erzeugen.

Erwartet von der Host-Klasse (AncestryDnaApp): self._state (AppState),
self._recent_menu (tk.Menu, von _build_menu angelegt), self._set_status,
self._save_ui_settings, self._ensure_gedcom_loaded,
self._on_gedcom_loaded_update_header.
"""
from __future__ import annotations

import logging
import os

from tkinter import messagebox

log = logging.getLogger(__name__)


class RecentFilesMixin:
    """D1: 'Zuletzt geöffnet'-Menü + GEDCOM-Pfad von außen setzen."""

    def _recent_files_load(self) -> list:
        """Liest die zuletzt geöffneten Dateipfade aus user_prefs (recent_0 … recent_4)."""
        paths = []
        try:
            with self._state.db._cursor() as cur:
                for i in range(5):
                    row = cur.execute(
                        "SELECT value FROM user_prefs WHERE key=?", (f"recent_{i}",)
                    ).fetchone()
                    if row and row[0]:
                        paths.append(row[0])
        except Exception:
            pass
        return paths

    def _recent_files_save(self, path: str) -> None:
        """Speichert path vorne in die Liste der zuletzt geöffneten Dateien (max. 5)."""
        if not path:
            return
        try:
            existing = self._recent_files_load()
            # Duplikate entfernen, neuen Pfad vorne einfügen, auf 5 begrenzen
            updated = [path] + [p for p in existing if p != path]
            updated = updated[:5]
            with self._state.db._cursor() as cur:
                for i in range(5):
                    val = updated[i] if i < len(updated) else ""
                    cur.execute(
                        "INSERT OR REPLACE INTO user_prefs (key, value) VALUES (?, ?)",
                        (f"recent_{i}", val),
                    )
        except Exception:
            pass
        self.after(0, self._recent_menu_rebuild)

    def _recent_menu_rebuild(self) -> None:
        """Baut das 'Zuletzt geöffnet'-Untermenü neu auf."""
        menu = getattr(self, "_recent_menu", None)
        if menu is None:
            return
        try:
            menu.delete(0, "end")
            paths = self._recent_files_load()
            if not paths:
                menu.add_command(label="(keine Einträge)", state="disabled")
                return
            for p in paths:
                label = os.path.basename(p) if p else p
                menu.add_command(
                    label=label,
                    command=lambda fp=p: self._open_recent_file(fp),
                )
        except Exception:
            pass

    def _open_recent_file(self, path: str) -> None:
        """Öffnet eine zuletzt verwendete Datei (GEDCOM oder ähnliches)."""
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showwarning("Datei nicht gefunden",
                                   f"Die Datei wurde nicht gefunden:\n{path}")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in (".ged", ".gedcom"):
            self._save_ui_settings(gedcom_path=path)
            self._set_status(f"GEDCOM vorbelegt: {os.path.basename(path)}")
            self._gedcom = None  # Cache verwerfen
            self._ensure_gedcom_loaded(self._on_gedcom_loaded_update_header)
        else:
            self._set_status(f"Unbekanntes Dateiformat: {ext}")

    def _set_gedcom(self, path: str):
        """Setzt den GEDCOM-Pfad von außen (z.B. aus dem Start-Tab)."""
        try:
            import os as _os
            if path and _os.path.exists(path):
                self._save_ui_settings(gedcom_path=path)
                self._set_status(f"GEDCOM-Pfad aktualisiert: {_os.path.basename(path)}")
        except (OSError, ValueError) as e:
            log.debug("change_gedcom_settings save: %s", e)
