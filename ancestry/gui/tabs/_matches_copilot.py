"""Cross-Quellen-Hinweis + Claude-Copilot-Mixin für MatchesTab: zeigt
gleichnamige Matches aus anderen Quellen (P15) und erklärt den gewählten
Match per Claude-Copilot.

Zwölfter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Beide Bereiche sind Detail-Panel-
Erweiterungen, die nur beim Auswählen eines Matches getriggert werden
(`_on_match_select`, bleibt in matches.py) bzw. per Button. Keine
eigenen Zustandsattribute.

Erwartet von der Host-Klasse (MatchesTab): self._state, self._get_test_guid(),
self._selected_match, self._cross_source_sep/_cross_source_frame/
_cross_source_label_var (in _build_detail_panel angelegt, bleibt in
matches.py).
"""
from __future__ import annotations

import threading
import tkinter as tk

from ancestry.models import DnaMatch


class CopilotMixin:
    """Cross-Quellen-Duplikat-Hinweis (P15) und Claude-Copilot-Erklärung."""

    def _load_cross_source_hint(self, match: "DnaMatch"):
        """P15: Lädt gleichnamige Matches aus anderen Quellen im Hintergrund
        und zeigt sie als Duplikat-Hinweis unter den Buttons an."""
        # Reset: Separator + Frame verstecken bis Ergebnis da
        self._cross_source_sep.pack_forget()
        self._cross_source_frame.pack_forget()
        self._cross_source_label_var.set("")

        display_name = match.display_name or ""
        current_source = getattr(match, "source", None) or "ancestry"
        test_guid = self._get_test_guid() or ""
        match_guid = match.match_guid

        def _worker(dn=display_name, src=current_source, tg=test_guid, mg=match_guid):
            try:
                with self._state.db._cursor() as cur:
                    rows = cur.execute(
                        "SELECT COALESCE(source, 'ancestry') AS source, "
                        "shared_cm, relationship_label "
                        "FROM matches "
                        "WHERE display_name = ? "
                        "  AND COALESCE(source, 'ancestry') != ? "
                        "  AND (test_guid IS NULL OR test_guid = ?) "
                        "ORDER BY shared_cm DESC LIMIT 5",
                        (dn, src, tg),
                    ).fetchall()
            except Exception:
                rows = []
            self.after(0, lambda: self._fill_cross_source_hint(mg, rows))

        threading.Thread(target=_worker, daemon=True, name="cross-source").start()

    def _fill_cross_source_hint(self, match_guid: str, rows):
        """Befüllt (oder versteckt) den Cross-Quellen-Hinweis nach Abfrage."""
        # Stale-Guard
        if not self._selected_match or self._selected_match.match_guid != match_guid:
            return
        if not rows:
            self._cross_source_sep.pack_forget()
            self._cross_source_frame.pack_forget()
            return

        _src_label = {
            "ancestry":   "Ancestry",
            "myheritage": "MyHeritage",
            "gedmatch":   "GEDmatch",
            "ftdna":      "FamilyTreeDNA",
        }
        parts = []
        for row in rows:
            src_name = _src_label.get(row[0], row[0])
            cm_val   = row[1]
            rel_val  = row[2]
            if cm_val:
                entry = f"{src_name} ({cm_val:.0f} cM"
                if rel_val:
                    entry += f" · {rel_val}"
                entry += ")"
            else:
                entry = src_name
            parts.append(entry)

        text = "🔗 Auch in: " + "  |  ".join(parts)
        self._cross_source_label_var.set(text)

        # Separator + Frame erst jetzt einblenden (nach den Buttons)
        self._cross_source_sep.pack(fill="x", padx=8, pady=(4, 2))
        self._cross_source_frame.pack(fill="x", padx=4, pady=(0, 4))

    def _copilot_explain_match(self):
        """Erklärt den ausgewählten Match via Claude-Copilot."""
        from tkinter import scrolledtext
        from ancestry.core.ai_copilot import (
            availability_hint, explain_async, is_available, match_prompt,
        )
        match = self._selected_match
        if match is None:
            return
        win = tk.Toplevel(self)
        win.title(f"🤖 KI-Erklärung: {match.display_name}")
        win.geometry("580x380")
        txt = scrolledtext.ScrolledText(win, wrap="word", font=("Segoe UI", 9),
                                        state="disabled", bg="#fafafa")
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        hint = availability_hint()
        if hint:
            txt.configure(state="normal")
            txt.insert("end", hint)
            txt.configure(state="disabled")
            return
        # Sammle Kontext
        try:
            shared = self._state.db.get_shared_matches(
                self._get_test_guid(), match.match_guid)
            shared_count = len(shared) if shared else 0
        except Exception:
            shared_count = 0
        try:
            from ancestry.core.matricula_bridge import _pedigree_surnames
            surnames = _pedigree_surnames(
                self._state.db, self._get_test_guid(), match.match_guid, 2)
        except Exception:
            surnames = []
        prompt = match_prompt(
            match_name=match.display_name or "",
            shared_cm=float(match.shared_cm or 0),
            predicted_rel=match.predicted_relationship or "",
            shared_count=shared_count,
            pedigree_names=surnames[:8],
        )
        txt.configure(state="normal")
        txt.insert("end", "Claude analysiert …\n\n")
        txt.configure(state="disabled")
        def _chunk(t):
            win.after(0, lambda c=t: _append(c))
        def _done(_):
            pass
        def _append(t):
            txt.configure(state="normal")
            txt.insert("end", t)
            txt.see("end")
            txt.configure(state="disabled")
        explain_async(prompt, on_chunk=_chunk, on_done=_done, max_tokens=350)
