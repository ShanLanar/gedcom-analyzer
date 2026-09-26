"""GEDmatch-Segment-Panel-Mixin für MatchesTab (Sub-Tab 7).

Fünfter Baustein der Mixin-Aufteilung (siehe _matches_wikitree.py für die
Begründung). Eigenständig: eigenes Widget (_seg_tree), reine DB-Lesezugriffe
auf dna_segments/gedmatch_bridge/mh_match_relationships, keine Aufrufe in
andere Panels hinein.

Erwartet von der Host-Klasse (MatchesTab): self._state (AppState),
self._selected_match.
"""
from __future__ import annotations

import webbrowser
from tkinter import ttk
from typing import Optional

from ancestry.models import DnaMatch


class SegmentsPanelMixin:
    """Sub-Tab 7: GEDmatch-Segment-Browser + MyHeritage-Beziehungsprognose."""

    def _build_segments_panel(self, parent):
        """Sub-Tab 7: GEDmatch-Segment-Browser."""
        seg_cols = ("chr", "start", "end", "cm", "snps")
        self._seg_tree = ttk.Treeview(parent, columns=seg_cols,
                                      show="headings", height=6)
        for col, label, width in [("chr", "Chr", 35), ("start", "Start", 80),
                                   ("end", "Ende", 80), ("cm", "cM", 50),
                                   ("snps", "SNPs", 55)]:
            self._seg_tree.heading(col, text=label)
            self._seg_tree.column(col, width=width,
                                  anchor="center" if col == "chr" else "e")
        seg_sb = ttk.Scrollbar(parent, orient="vertical",
                               command=self._seg_tree.yview)
        self._seg_tree.configure(yscrollcommand=seg_sb.set)
        self._seg_tree.pack(side="left", fill="both", expand=True)
        seg_sb.pack(side="left", fill="y")

        seg_btn_row = ttk.Frame(parent)
        seg_btn_row.pack(fill="x", pady=(2, 0))
        ttk.Button(seg_btn_row, text="🔗 In GEDmatch öffnen",
                   command=self._open_gedmatch_segments).pack(side="left", padx=4)

    def _load_segments(self, match: DnaMatch):
        """Lädt Chromosomen-Segmente für einen Match aus dna_segments."""
        if not hasattr(self, "_seg_tree"):
            return
        for item in self._seg_tree.get_children():
            self._seg_tree.delete(item)
        try:
            with self._state.db._cursor() as cur:
                try:
                    rows = cur.execute(
                        "SELECT chromosome, start_location, end_location, "
                        "length_cm, snp_count "
                        "FROM dna_segments WHERE match_guid=? "
                        "ORDER BY chromosome, start_location",
                        (match.match_guid,)
                    ).fetchall()
                except Exception:
                    rows = []
                for r in rows:
                    vals = (r[0], r[1], r[2],
                            f"{r[3]:.1f}" if r[3] else "",
                            r[4] or "")
                    self._seg_tree.insert("", "end", values=vals)
        except Exception:
            pass

    def _open_gedmatch_segments(self):
        """Öffnet GEDmatch-Segment-Browser für den ausgewählten Match."""
        m = self._selected_match
        if not m:
            return
        try:
            with self._state.db._cursor() as cur:
                r = cur.execute(
                    "SELECT gedmatch_kit_id FROM gedmatch_bridge "
                    "WHERE match_guid=? LIMIT 1",
                    (m.match_guid,)
                ).fetchone()
            if r:
                kit = r[0] if r else None
                if kit:
                    webbrowser.open(
                        f"https://www.gedmatch.com/one-to-one-api.php?kit1={kit}")
                    return
        except Exception:
            pass
        webbrowser.open("https://www.gedmatch.com")

    def _load_mh_relationship(self, match: DnaMatch) -> Optional[str]:
        """Lädt MyHeritage-Beziehungsprognose für diesen Match."""
        try:
            with self._state.db._cursor() as cur:
                r = cur.execute(
                    "SELECT relationship_class, relationship_degree, probability "
                    "FROM mh_match_relationships "
                    "WHERE match_guid=? ORDER BY probability DESC LIMIT 1",
                    (match.match_guid,)
                ).fetchone()
            if r:
                rel_class  = r[0] or ""
                rel_degree = r[1] or ""
                prob       = r[2]
                label = " ".join(filter(None, [rel_class, rel_degree])) or "?"
                if prob:
                    return f"{label}  ({prob:.0%})"
                return label
        except Exception:
            pass
        return None
