"""Gemeinsame-Vorfahren-Panel-Mixin für MatchesTab (Sub-Tab 4).

Vierter Baustein der Mixin-Aufteilung (siehe _matches_wikitree.py für die
Begründung). Eigenständig: eigene Widgets (_anc_status_var, _anc_tree),
liest nur die Ancestry-match_ancestors-Tabelle, keine Aufrufe in andere
Panels hinein.

Erwartet von der Host-Klasse (MatchesTab): self._state (AppState),
self._selected_match.
"""
from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import ttk

from ancestry.gui.widgets.theme import COLORS
from ancestry.models import DnaMatch

log = logging.getLogger(__name__)


class AncestorsPanelMixin:
    """Sub-Tab 4: Gemeinsame Vorfahren (aus Ancestry match_ancestors-Tabelle)."""

    def _build_ancestors_panel(self, parent):
        """Sub-Tab 4: Gemeinsame Vorfahren (aus Ancestry match_ancestors-Tabelle)."""
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._anc_status_var = tk.StringVar(value="")
        ttk.Label(tb, textvariable=self._anc_status_var,
                  foreground=COLORS["primary"]).pack(side="left")

        cols = ("name", "birth", "death", "rel_sample", "rel_match", "path_sample")
        self._anc_tree = ttk.Treeview(parent, columns=cols,
                                       show="headings", selectmode="browse")
        widths   = {"name": 200, "birth": 45, "death": 45,
                    "rel_sample": 140, "rel_match": 140, "path_sample": 90}
        labels   = {"name": "Vorfahre", "birth": "Geb.", "death": "Gest.",
                    "rel_sample": "Verwandtschaft (Proband)",
                    "rel_match":  "Verwandtschaft (Match)",
                    "path_sample": "Ahnen-Pfad"}
        anchors  = {"birth": "center", "death": "center", "path_sample": "center"}
        for col in cols:
            self._anc_tree.heading(col, text=labels[col])
            self._anc_tree.column(col, width=widths[col],
                                   anchor=anchors.get(col, "w"),
                                   stretch=(col in ("name", "rel_sample", "rel_match")))
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._anc_tree.yview)
        self._anc_tree.configure(yscrollcommand=sy.set)
        self._anc_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=2)
        sy.pack(side="right", fill="y", pady=2)

    def _load_ancestors_panel(self, match: DnaMatch):
        """Füllt den Gemeinsame-Vorfahren-Tab für den ausgewählten Match (im Hintergrund)."""
        self._anc_tree.delete(*self._anc_tree.get_children())
        def _worker():
            try:
                rows = self._state.db.get_ancestors_for_match(match.match_guid)
            except Exception as e:
                log.debug("get_ancestors_for_match %s: %s", match.match_guid[:8], e)
                rows = []
            self.after(0, lambda: self._fill_ancestors_panel(match, rows))
        threading.Thread(target=_worker, daemon=True).start()

    def _fill_ancestors_panel(self, match: DnaMatch, rows):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != match.match_guid:
            return
        self._anc_tree.delete(*self._anc_tree.get_children())
        if not rows:
            self._anc_status_var.set(self._state.t("md.anc_none"))
            return
        self._anc_status_var.set(
            f"{len(rows)} gemeinsame Vorfahren  ·  {match.display_name}")
        for r in rows:
            self._anc_tree.insert("", "end", values=(
                r.get("ancestor_name", ""),
                r.get("birth_year") or "—",
                r.get("death_year") or "—",
                r.get("relationship_to_sample", ""),
                r.get("relationship_to_match", ""),
                r.get("kinship_path_sample", ""),
            ))
