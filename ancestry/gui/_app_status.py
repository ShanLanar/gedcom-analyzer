"""Status-/Fortschritts-Mixin für AncestryDnaApp (Statusleiste, Spinner,
Download-Fortschritt, aktueller Kit-GUID).

Zehnter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). `_set_status` wird von praktisch jedem anderen Mixin
aufgerufen — die Extraktion ändert daran nichts, da Methodenauflösung
über die MRO unabhängig davon funktioniert, welche Basisklasse die
Methode definiert. `_spinner_idx` ist reiner Übergangszustand der
Spinner-Animation und wird nirgends außerhalb dieser Datei initialisiert
oder gelesen (immer per `getattr(..., 0)`).

Erwartet von der Host-Klasse (AncestryDnaApp): self._status_bar,
self._status_var, self._download_tab.
"""
from __future__ import annotations

from typing import Optional


class StatusMixin:
    """Statusleiste (inkl. Spinner-Animation), Download-Fortschritt, Kit-GUID."""

    def _set_status(self, msg: str, level: str = "default"):
        if hasattr(self, "_status_bar"):
            self._status_bar.set(msg, level)
        else:
            # Fallback während __init__ bevor _status_bar gebaut wird
            if hasattr(self, "_status_var"):
                self._status_var.set(msg)
        if msg.endswith("…"):
            self._animate_status_spinner()
        else:
            self._spinner_idx = 0

    def _animate_status_spinner(self):
        """Zeigt einen rotierenden Spinner für Status-Nachrichten mit "…"."""
        if self._status_var.get().endswith("…"):
            spinners = ["◐ ", "◓ ", "◑ ", "◒ "]
            idx = getattr(self, "_spinner_idx", 0)
            base_msg = self._status_var.get()[2:-3]  # Entferne Spinner + "…"
            self._status_var.set(f"{spinners[idx]}{base_msg}…")
            self._spinner_idx = (idx + 1) % 4
            self.after(150, self._animate_status_spinner)

    def _on_progress(self, fetched, total, label):
        """Delegation stub — updates DownloadTab progress display."""
        self._download_tab.on_progress(fetched, total, label)

    def _get_kit_guid(self) -> Optional[str]:
        if getattr(self, "_download_tab", None) is not None:
            return self._download_tab.get_kit_guid()
        return None
