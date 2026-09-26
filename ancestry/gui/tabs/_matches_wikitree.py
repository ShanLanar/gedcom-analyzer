"""WikiTree-Sub-Tab-Mixin für MatchesTab.

Erster Baustein der Mixin-Aufteilung der (sehr großen) MatchesTab-Klasse in
ancestry/gui/tabs/matches.py — reine Wartbarkeits-Refaktorierung, keine
Verhaltensänderung. Dieser Mixin ist bewusst als erster Kandidat gewählt,
weil er komplett eigenständig ist: eigene Widgets (_wt_status_var,
_wt_search_btn, _wt_tree), keine Aufrufe in andere Panels hinein, keine
anderen Panels rufen etwas HIERAUS außer den beiden öffentlichen Einstiegen
_build_wikitree_panel()/_load_wikitree_panel() (von MatchesTab._build_detail_
panel bzw. MatchesTab._on_match_select aus aufgerufen).

Erwartet von der Host-Klasse (MatchesTab): self._state (AppState),
self._selected_match (aktuell gewählter DnaMatch).
"""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Optional
from urllib.parse import quote

from ancestry.gui.widgets.theme import COLORS
from ancestry.models import DnaMatch


class WikiTreePanelMixin:
    """WikiTree-Sub-Tab: Direktsuche + gespeicherte Treffer für den Match."""

    def _build_wikitree_panel(self, parent):
        """Sub-Tab 6: WikiTree-Direktsuche und gespeicherte Treffer."""
        t  = self._state.t
        lw = self._state.lang_widgets

        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._wt_status_var = tk.StringVar(value=t("md.wt_no_match"))
        ttk.Label(tb, textvariable=self._wt_status_var,
                  foreground=COLORS["primary"]).pack(side="left")
        _sv_btn = tk.StringVar(value=t("md.wt_search"))
        self._wt_search_btn = ttk.Button(tb, textvariable=_sv_btn,
                                          command=self._wt_open_search, state="disabled")
        self._wt_search_btn.pack(side="right", padx=4)
        lw.append((_sv_btn, "md.wt_search"))

        cols = ("confidence", "wt_id", "name", "birth", "death", "location", "link")
        self._wt_tree = ttk.Treeview(parent, columns=cols, show="headings",
                                      selectmode="browse")
        for col, lbl, w, anchor in [
            ("confidence", "Konfidenz",  80, "center"),
            ("wt_id",      "WikiTree-ID",100, "w"),
            ("name",       "Name",       200, "w"),
            ("birth",      "Geb.",        55, "center"),
            ("death",      "Gest.",       55, "center"),
            ("location",   "Ort",        150, "w"),
            ("link",       "Profil",      60, "center"),
        ]:
            self._wt_tree.heading(col, text=lbl)
            self._wt_tree.column(col, width=w, anchor=anchor,
                                  stretch=(col == "name"))
        self._wt_tree.tag_configure("HOCH",   foreground=COLORS.get("success", "#198754"))
        self._wt_tree.tag_configure("MITTEL", foreground=COLORS.get("primary", "#1a73e8"))
        self._wt_tree.tag_configure("NIEDRIG",foreground="#888888")
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._wt_tree.yview)
        self._wt_tree.configure(yscrollcommand=sy.set)
        self._wt_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=2)
        sy.pack(side="right", fill="y", pady=2)
        self._wt_tree.bind("<Double-1>", self._wt_open_profile)

    def _load_wikitree_panel(self, match: Optional[DnaMatch]):
        """Füllt den WikiTree-Tab für den ausgewählten Match."""
        if not hasattr(self, "_wt_tree"):
            return
        self._wt_tree.delete(*self._wt_tree.get_children())
        t = self._state.t
        if match is None:
            self._wt_status_var.set(t("md.wt_no_match"))
            self._wt_search_btn.configure(state="disabled")
            return
        self._wt_search_btn.configure(state="normal")
        # Versuche gespeicherte WikiTree-Zeilen aus dem Runner-State
        rows: list = []
        try:
            import tasks._runner as _runner
            all_rows = _runner._state.get("wikitree_rows") or []
            guid = match.match_guid
            rows = [r for r in all_rows
                    if isinstance(r, (list, tuple)) and len(r) >= 2 and r[1] == guid]
        except Exception:
            rows = []
        if not rows:
            self._wt_status_var.set(t("md.wt_no_data"))
            return
        self._wt_status_var.set(f"{len(rows)} WikiTree-Treffer  ·  {match.display_name}")
        for r in rows:
            # WIKITREE_HEADERS = [Konfidenz, Match-GUID, WikiTree-ID, Name, Geb., Gest.,
            #                      Geburtsort, Sterbeort, URL, …]
            conf = r[0] if len(r) > 0 else ""
            wt_id = r[2] if len(r) > 2 else ""
            name = r[3] if len(r) > 3 else ""
            birth = r[4] if len(r) > 4 else ""
            death = r[5] if len(r) > 5 else ""
            loc   = r[6] if len(r) > 6 else ""
            url   = r[8] if len(r) > 8 else ""
            tag = conf if conf in ("HOCH", "MITTEL", "NIEDRIG") else ""
            self._wt_tree.insert("", "end", tags=(tag,) if tag else (), values=(
                conf, wt_id, name, birth, death, loc,
                "→ öffnen" if url else "—",
            ), iid=None)
            if url:
                # URL in row-Daten speichern für Doppelklick
                self._wt_tree.set(self._wt_tree.get_children()[-1], "link", "→ öffnen")
                self._wt_tree.item(self._wt_tree.get_children()[-1], tags=(tag or "", url))

    def _wt_open_search(self):
        """Öffnet die WikiTree-Suche für den ausgewählten Match im Browser."""
        match = self._selected_match
        if not match:
            return
        name = match.display_name or ""
        parts = name.split()
        if len(parts) >= 2:
            first = parts[0]
            last  = parts[-1]
        elif parts:
            first, last = "", parts[0]
        else:
            first, last = "", ""
        q = f"{first}+{last}".strip("+")
        url = f"https://www.wikitree.com/index.php?title=Special:SearchPerson&q={quote(q)}"
        webbrowser.open(url)

    def _wt_open_profile(self, _event=None):
        """Doppelklick auf einen WikiTree-Treffer → Profil im Browser öffnen."""
        sel = self._wt_tree.selection()
        if not sel:
            return
        tags = self._wt_tree.item(sel[0], "tags")
        # Der zweite Tag ist die URL (wenn gesetzt)
        url = tags[1] if len(tags) >= 2 and tags[1].startswith("http") else None
        if url:
            webbrowser.open(url)
        else:
            wt_id = self._wt_tree.set(sel[0], "wt_id")
            if wt_id:
                webbrowser.open(f"https://www.wikitree.com/wiki/{quote(wt_id)}")
