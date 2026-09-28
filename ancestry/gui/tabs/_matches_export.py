"""Export-Mixin für MatchesTab (C2): exportiert alle aktuell gefilterten
Matches (ohne Seitenlimit) als CSV oder XLSX.

Neunter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Eine einzelne, in sich geschlossene
Methode — liest denselben Filterzustand wie `_refresh_match_table_inner`
(bleibt in matches.py), definiert aber keine eigenen Attribute.

Erwartet von der Host-Klasse (MatchesTab): self._state, self._min_cm_var,
self._sort_col, self._sort_asc, self._search_var, self._get_test_guid(),
self._ALL_SOURCES_LABEL, self._matches_kit_var/_matches_kit_guid_map
(optional, per hasattr/getattr).
"""
from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional


class ExportMatchesMixin:
    """CSV-/XLSX-Export aller gefilterten Matches ohne Seitenlimit."""

    def _export_matches(self) -> None:
        """C2: Exportiert alle gefilterten Matches als CSV oder XLSX."""
        import os

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx")],
            title="Matches exportieren",
        )
        if not path:
            return

        # Alle gefilterten Matches ohne LIMIT laden
        try:
            min_cm = float(self._min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            min_cm = 0.0

        col_map = {"name": "display_name", "guid": "match_guid", "note": "tag_surname",
                   "cm": "shared_cm", "seg": "shared_segments",
                   "rel": "predicted_relationship", "tree": "tree_size",
                   "ged": "match_guid", "ca": "has_common_ancestor", "starred": "starred"}
        sort_col = col_map.get(self._sort_col, "shared_cm")

        active_kit: Optional[str] = None
        selected_kit_name = ""
        if hasattr(self, "_matches_kit_var") and self._matches_kit_var.get():
            selected_kit_name = self._matches_kit_var.get()
            active_kit = self._matches_kit_guid_map.get(selected_kit_name)
        all_sources_mode = (selected_kit_name == self._ALL_SOURCES_LABEL)
        if not all_sources_mode and not active_kit:
            active_kit = self._get_test_guid()

        _cv = getattr(self, "_chip_vars", {})
        _pm = getattr(self, "_side_var", tk.StringVar()).get() or None
        if _cv.get("pat", tk.BooleanVar()).get():
            _pm = "paternal"
        elif _cv.get("mat", tk.BooleanVar()).get():
            _pm = "maternal"
        _source = getattr(self, "_active_source", None)
        _clustered = _cv.get("clustered", tk.BooleanVar()).get()

        try:
            rows = self._state.db.get_matches(
                test_guid=active_kit,
                all_sources=all_sources_mode,
                search=self._search_var.get().strip() or None,
                relationship=self._rel_var.get() if hasattr(self, "_rel_var") else None,
                starred_only=self._starred_var.get() if hasattr(self, "_starred_var") else False,
                has_tree_only=self._tree_var.get() if hasattr(self, "_tree_var") else False,
                min_cm=min_cm,
                hide_endogamy=getattr(self, "_hide_endo_var", tk.BooleanVar()).get(),
                paternal_maternal=_pm,
                new_only=_cv.get("new", tk.BooleanVar()).get(),
                source=_source,
                clustered_only=_clustered,
                sort_col=sort_col,
                sort_asc=self._sort_asc,
                limit=None,
                offset=0,
            )
        except Exception as exc:
            messagebox.showerror("Fehler", f"Datenbankfehler beim Export:\n{exc}")
            return

        headers = ["Name", "cM", "Segmente", "Beziehung", "Stammbaum",
                   "Seite", "Quelle", "GEDCOM-Treffer", "Notiz", "Favorit"]

        def _row_vals(m) -> list:
            return [
                m.display_name or "",
                f"{m.shared_cm:.1f}" if m.shared_cm else "",
                m.shared_segments or "",
                m.predicted_relationship or "",
                f"{'Ja' if m.has_tree else 'Nein'} ({m.tree_size})" if m.tree_size else ("Ja" if m.has_tree else "Nein"),
                getattr(m, "paternal_maternal", "") or "",
                getattr(m, "source", "ancestry") or "ancestry",
                m.tag_surname or "",
                m.note or "",
                "Ja" if m.starred else "",
            ]

        try:
            if path.endswith(".xlsx"):
                try:
                    import openpyxl
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.append(headers)
                    for m in rows:
                        ws.append(_row_vals(m))
                    wb.save(path)
                except ImportError:
                    messagebox.showerror(
                        "Fehler",
                        "openpyxl nicht installiert — bitte als CSV speichern.")
                    return
            else:
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    for m in rows:
                        w.writerow(_row_vals(m))
            messagebox.showinfo("Export", f"{len(rows)} Matches exportiert:\n{os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Fehler", f"Fehler beim Speichern:\n{exc}")
