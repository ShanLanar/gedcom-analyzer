"""Kleinere, verstreute Dialog-Methoden für AncestryDnaApp (Cluster-Zeitleiste,
Info-/Kurzbefehle-Dialog).

Fünfter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Jede dieser drei Methoden hat genau eine Aufrufstelle (Menü
bzw. Tab-Callback) und keine eigenen Zustandsattribute — komplett isoliert
von den umliegenden (deutlich stärker verflochtenen) Methodengruppen, in
denen sie bisher lediglich physisch lagen.

Erwartet von der Host-Klasse (AncestryDnaApp): self._t().
"""
from __future__ import annotations

from tkinter import messagebox

from ancestry.paths import DB_PATH


class MiscDialogsMixin:
    """Cluster-Zeitleiste, Info-Dialog, Tastaturkürzel-Übersicht."""

    def _show_cluster_timeline(self):
        from ancestry.gui.analysis.cluster_views import show_cluster_timeline
        show_cluster_timeline(self)

    def _show_about(self):
        messagebox.showinfo(self._t("dlg.about_title"),
            self._t("dlg.about_body") + "\n" + str(DB_PATH))

    def _show_shortcuts(self):
        messagebox.showinfo(self._t("mn.shortcuts").rstrip(" …"),
                            self._t("dlg.shortcuts_body"))
