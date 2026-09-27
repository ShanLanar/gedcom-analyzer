"""Einstellungs- und Sprach-Mixin für AncestryDnaApp (UI-Settings-Datei
`data/ui_settings.json` + Sprachumschaltung DE/EN).

Neunter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). `_save_ui_settings`/`_load_ui_settings` sind reine
Datei-I/O-Helfer ohne eigenen Zustand; die Sprachmethoden lesen/schreiben
nur `self._lang`, das bereits in AncestryDnaApp.__init__ initialisiert
wird (hier nur Umschaltung, keine Erstdefinition).

Erwartet von der Host-Klasse (AncestryDnaApp): self._lang, self._state,
self._nb, self._lang_nb_tabs/_lang_headings/_lang_widgets/_lang_menus/
_lang_inner_nb_tabs, self._set_status(), optional self._lang_btn.
"""
from __future__ import annotations

import logging
import tkinter as tk

from ancestry.gui.widgets.theme import translate

log = logging.getLogger(__name__)


class SettingsMixin:
    """UI-Einstellungen (JSON-Datei) und Sprachumschaltung DE/EN."""

    def _settings_path(self):
        import os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(base, "data")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "ui_settings.json")

    def _load_ui_settings(self) -> dict:
        import json
        import os
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_ui_settings(self, **kw):
        import json
        s = self._load_ui_settings(); s.update(kw)
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.debug("Settings speichern fehlgeschlagen: %s", e)
            self._set_status(f"⚠ UI-Einstellungen speichern: {e}", "warn")
        # P20: GEDCOM-Pfad in config_user.json spiegeln, damit tasks/_runner.py
        # dieselbe Datei sieht wie die GUI.
        if "gedcom_path" in kw and kw["gedcom_path"]:
            try:
                import config as _cfg
                _cfg.save_overrides({"gedfile": kw["gedcom_path"]})
            except Exception as e:
                log.debug("config_user.json sync fehlgeschlagen: %s", e)
                self._set_status(f"⚠ config_user.json sync: {e}", "warn")

    # ── Sprache / Localisation ────────────────────────────────────────────

    def _t(self, key: str) -> str:
        return translate(key, self._lang)

    def _update_lang_btn(self):
        if hasattr(self, "_lang_btn"):
            self._lang_btn.configure(
                text="🌐 → EN" if self._lang == "de" else "🌐 → DE")

    def _toggle_lang(self):
        self._lang = "en" if self._lang == "de" else "de"
        self._apply_lang()
        self._save_ui_settings(lang=self._lang)

    def set_language(self, lang: str):
        """Setzt die Sprache explizit (für die globale Sprachauswahl)."""
        self._lang = "en" if str(lang).lower().startswith("en") else "de"
        self._state.lang = self._lang
        try:
            self._apply_lang()
            self._save_ui_settings(lang=self._lang)
        except Exception:
            pass

    def _apply_lang(self):
        self._update_lang_btn()
        for frame, key in self._lang_nb_tabs:
            try:
                self._nb.tab(frame, text=self._t(key))
            except tk.TclError:
                pass
        for tv, col, key in self._lang_headings:
            try:
                tv.heading(col, text=self._t(key))
            except tk.TclError:
                pass
        for item in self._lang_widgets:
            widget, key = item[0], item[1]
            suffix = item[2] if len(item) > 2 else ""
            try:
                text = self._t(key) + suffix
                if isinstance(widget, tk.StringVar):
                    widget.set(text)
                else:
                    widget.configure(text=text)
            except tk.TclError:
                pass
        for menu, index, key in self._lang_menus:
            try:
                menu.entryconfigure(index, label=self._t(key))
            except tk.TclError:
                pass
        for nb, frame, key in self._lang_inner_nb_tabs:
            try:
                nb.tab(frame, text=self._t(key))
            except tk.TclError:
                pass
        for tip, key in self._state.lang_tooltips:
            tip.text = self._t(key)

    def _load_lang_setting(self):
        lang = self._load_ui_settings().get("lang", "de")
        if lang in ("de", "en"):
            self._lang = lang
            self._apply_lang()
