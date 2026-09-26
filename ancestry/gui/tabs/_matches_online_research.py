"""Online-Recherche-Panel-Mixin für MatchesTab (C3).

Dritter Baustein der Mixin-Aufteilung (siehe _matches_wikitree.py für die
Begründung). Eigenständig: eigene Widgets (_online_research_frame,
_online_research_btns), reine Link-Öffner ohne Rückwirkung auf andere Panels.

Erwartet von der Host-Klasse (MatchesTab): self._selected_match.
"""
from __future__ import annotations

import webbrowser
from tkinter import ttk
from typing import Optional
from urllib.parse import quote_plus

from ancestry.models import DnaMatch


class OnlineResearchPanelMixin:
    """C3: Externe Recherche-Links (FamilySearch, Grabstein.de, Geni, …)."""

    def _build_online_research_panel(self, parent):
        """C3: Baut den Block mit Online-Recherche-Buttons im Detail-Panel."""
        lf = ttk.LabelFrame(parent, text="🔗 Online-Recherche")
        lf.pack(fill="x", padx=8, pady=(0, 4))
        self._online_research_frame = lf

        # 5 Buttons in einem Grid (2 Zeilen × 3 Spalten)
        _link_defs = [
            ("FamilySearch", self._open_research_familysearch),
            ("Grabstein.de",  self._open_research_grabstein),
            ("Geni",          self._open_research_geni),
            ("MyHeritage",    self._open_research_myheritage),
            ("WikiTree",      self._open_research_wikitree),
        ]
        self._online_research_btns: list[ttk.Button] = []
        for i, (label, cmd) in enumerate(_link_defs):
            btn = ttk.Button(lf, text=label, command=cmd, state="disabled", width=12)
            btn.grid(row=i // 3, column=i % 3, padx=3, pady=2, sticky="w")
            self._online_research_btns.append(btn)

    def _update_online_research_panel(self, match: Optional[DnaMatch]):
        """C3: Aktiviert/deaktiviert die Recherche-Buttons je nach Selektion."""
        state = "normal" if match else "disabled"
        for btn in getattr(self, "_online_research_btns", []):
            btn.configure(state=state)

    def _open_research_familysearch(self):
        """FamilySearch-Suche nach dem Match-Nachnamen."""
        m = self._selected_match
        if not m:
            return
        name = m.display_name or ""
        if not name or name in ("Anonym", "?"):
            return
        lastname = name.split()[-1]
        webbrowser.open(
            f"https://www.familysearch.org/search/record/results?q.surname={quote_plus(lastname)}"
        )

    def _open_research_grabstein(self):
        """Grabstein.de-Suche nach dem Match-Nachnamen."""
        m = self._selected_match
        if not m:
            return
        name = m.display_name or ""
        if not name or name in ("Anonym", "?"):
            return
        lastname = name.split()[-1]
        webbrowser.open(f"https://www.grabstein.de/suche/?ln={quote_plus(lastname)}")

    def _open_research_geni(self):
        """Geni-Suche nach dem Match-Namen."""
        m = self._selected_match
        if not m:
            return
        name = m.display_name or ""
        if not name or name in ("Anonym", "?"):
            return
        webbrowser.open(
            f"https://www.geni.com/search?search_type=people&names={quote_plus(name)}"
        )

    def _open_research_myheritage(self):
        """MyHeritage-Namensuche."""
        m = self._selected_match
        if not m:
            return
        name = m.display_name or ""
        if not name or name in ("Anonym", "?"):
            return
        webbrowser.open(
            f"https://www.myheritage.de/names/search?name={quote_plus(name)}"
        )

    def _open_research_wikitree(self):
        """WikiTree-Suche nach dem Match-Namen."""
        m = self._selected_match
        if not m:
            return
        name = m.display_name or ""
        if not name or name in ("Anonym", "?"):
            return
        webbrowser.open(
            f"https://www.wikitree.com/index.php?search=&name={quote_plus(name)}"
        )
