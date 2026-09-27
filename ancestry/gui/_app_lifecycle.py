"""Lebenszyklus-Mixin für AncestryDnaApp (Cookie/GUID-Einstellungen laden
und speichern, Fenster schließen, Aufräumen, Live-Statuszeile).

Elfter und letzter Baustein der Mixin-Aufteilung (siehe
_app_recent_files.py für die Begründung). `_load_settings`/`_save_settings`
verwalten `settings.json` (Cookie-Pfad, manuelle GUID) — zu unterscheiden
von `_load_ui_settings`/`_save_ui_settings` (SettingsMixin,
`data/ui_settings.json`). Keine eigenen Zustandsattribute; alle Methoden
lesen/schreiben ausschließlich bereits in __init__ angelegte Attribute.

Erwartet von der Host-Klasse (AncestryDnaApp): self._cookie_file_var,
self._manual_guid_var, self._kit_var, self._kit_map, self._state,
self._download_tab, self._matricula_tab, self._scraper, self._embedded,
self._nb, self._startup_gedcom_path, self._db, self._t(), self._set_status(),
self._load_ui_settings()/self._save_ui_settings().
"""
from __future__ import annotations

import logging
import os
from tkinter import messagebox

from ancestry.paths import DB_PATH

log = logging.getLogger(__name__)


class LifecycleMixin:
    """settings.json (Cookie/GUID), Fenster schließen/Aufräumen, Live-Statuszeile."""

    # ── Persistente Einstellungen ────────────────────────────────────────

    def _load_settings(self):
        """Lädt gespeicherte Einstellungen (Cookie-Pfad, Kit-GUID)."""
        import json
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'settings.json')
        try:
            with open(path, encoding='utf-8') as f:
                s = json.load(f)
            if s.get('cookie_file'):
                self._cookie_file_var.set(s['cookie_file'])
            if s.get('manual_guid'):
                self._manual_guid_var.set(s['manual_guid'])
                # Automatisch als Kit registrieren
                guid = s['manual_guid']
                name = 'Gespeichertes Kit (' + guid[:8] + '...)'
                self._kit_map[name] = guid
                self._download_tab.update_kit_combo()
                self._state.current_test_guid = guid
            if s.get('last_kit_name') and s['last_kit_name'] in self._kit_map:
                self._kit_var.set(s['last_kit_name'])
            self._set_status('Einstellungen geladen.')
        except (FileNotFoundError, Exception):
            pass

        # UI-Einstellungen: Fenstergeometrie + aktiver Tab
        st = self._load_ui_settings()
        geom = st.get("window_geometry")
        if geom and not self._embedded:
            try:
                self.winfo_toplevel().geometry(geom)
            except Exception:
                pass
        tab_idx = st.get("active_tab")
        if tab_idx is not None:
            try:
                self.after(100, lambda: self._nb.select(int(tab_idx)))
            except Exception:
                pass

        # GEDCOM-Pfad aus Kommandozeile vorbelegen (überschreibt ui_settings nur wenn nötig)
        if self._startup_gedcom_path:
            import os as _os
            if _os.path.exists(self._startup_gedcom_path):
                st = self._load_ui_settings()
                if not st.get("gedcom_path"):
                    self._save_ui_settings(gedcom_path=self._startup_gedcom_path)
                    self._set_status(
                        f"GEDCOM vorbelegt: {_os.path.basename(self._startup_gedcom_path)}")

    def _save_settings(self):
        """Speichert aktuelle Einstellungen."""
        import json
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'settings.json')
        s = {
            'cookie_file' : self._cookie_file_var.get(),
            'manual_guid' : self._manual_guid_var.get(),
            'last_kit_name': self._kit_var.get(),
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning('Einstellungen konnten nicht gespeichert werden: %s', e)
            self._set_status(f"⚠ Einstellungen speichern: {e}", "warn")

    def _on_close(self):
        dl_running = self._download_tab.is_running() if self._download_tab else False
        mat_running = self._matricula_tab.is_running() if self._matricula_tab else False
        if dl_running or mat_running or (self._scraper and self._scraper.is_running()):
            what = "Matricula-Scan" if mat_running and not dl_running else "Download"
            if not messagebox.askyesno(self._t("dlg.quit_q"), f"{what} läuft noch. Wirklich beenden?"):
                return
            if self._download_tab:
                self._download_tab.stop_download()
            if self._matricula_tab:
                self._matricula_tab._stop_scan()
            if self._scraper:
                self._scraper.stop()
        self._save_ui_settings(window_geometry=self.winfo_toplevel().winfo_geometry())
        self.shutdown()
        self.winfo_toplevel().destroy()

    def shutdown(self):
        """Aufräumen ohne Fenster zu zerstören – für die eingebettete Nutzung."""
        try: self._save_settings()
        except Exception as e: log.debug("shutdown _save_settings: %s", e)
        try: self._db.close()
        except Exception as e: log.debug("shutdown _db.close: %s", e)

    # ── A2: Live-Zähler-Statuszeile ──────────────────────────────────────

    def _update_statusbar(self):
        """Liest DB-Zähler und aktualisiert die Live-Statuszeile. Auto-Refresh 30s."""
        try:
            db = self._state.db
            with db._cursor() as cur:
                n_matches = cur.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            with db._cursor() as cur:
                n_persons = cur.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
            # DB-Dateigröße
            db_path = getattr(db, "db_file", None) or str(DB_PATH)
            if db_path and os.path.exists(db_path):
                size_bytes = os.path.getsize(db_path)
                if size_bytes >= 1_048_576:
                    size_str = f"{size_bytes / 1_048_576:.1f} MB"
                else:
                    size_str = f"{size_bytes / 1024:.0f} KB"
            else:
                size_str = "–"
            text = (f"Matches: {n_matches} | Personen: {n_persons} | DB: {size_str}")
            if hasattr(self, "_live_bar_var"):
                self._live_bar_var.set(text)
        except Exception:
            pass
        # Auto-Refresh alle 30 s
        try:
            self.after(30_000, self._update_statusbar)
        except Exception:
            pass
