"""Verwandtschafts-/Filter-Persistenz-Mixin für MatchesTab: Shared-cM-
Project-Zusammenfassung, Top-3-Wahrscheinlichkeitsbalken, Filter-Profile
speichern/laden (A4), cM-Beziehungs-Predictor (C1).

Achter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). Thematisch zusammengehörend: alle
Methoden drehen sich um die Einordnung eines cM-Werts in eine
Verwandtschaftswahrscheinlichkeit (Anzeige) bzw. um das Persistieren der
Filter-Auswahl. Keine eigenen Zustandsattribute — `self._current_offset`
wird nur zurückgesetzt (bereits in __init__ initialisiert).

Erwartet von der Host-Klasse (MatchesTab): self._rel_prob_canvas,
self._min_cm_var, self._search_var, self._cm_ranges, self._pref_get()/
self._pref_set(), self._do_refresh(), optional self._rel_var/self._side_var/
self._cm_predictor_var/self._cm_predict_labels (per hasattr/getattr).
"""
from __future__ import annotations

import tkinter as tk

from ancestry.gui.widgets.theme import COLORS


class RelationshipPredictorMixin:
    """cM-Verwandtschaftsanzeige (Zusammenfassung, Wahrscheinlichkeitsbalken,
    Predictor) und Filter-Profile speichern/laden."""

    @staticmethod
    def _rel_cm_summary(cm: float) -> str:
        """Shared-cM-Project-Verteilung als Einzeiler, z.B.
        '70% 2. Cousin · 19% Halb-1C · 11% …'."""
        try:
            from ancestry.core.shared_cm import summary_line
            return summary_line(cm, top=3) if cm and cm > 0 else "—"
        except ImportError:
            return "—"

    def _update_rel_prob(self, cm: float):
        """Draw top-3 relationship probability bars on the canvas
        (Shared cM Project 4.0 distribution)."""
        c = self._rel_prob_canvas
        c.delete("all")
        if cm <= 0:
            return
        w = c.winfo_width() or 260
        h = c.winfo_height() or 52
        try:
            from ancestry.core.shared_cm import relationship_probabilities
            probs = relationship_probabilities(cm, top=3)
            scored = [(p["probability"], p["labels"][0]) for p in probs]
        except ImportError:
            scored = []
        if not scored:
            return
        total = sum(s for s, _ in scored) or 1.0
        colors = [COLORS["primary"], COLORS["accent"], COLORS["light"]]
        bar_h = (h - 6) // 3
        for i, (score, label) in enumerate(scored):
            pct = score / total
            y0 = 3 + i * (bar_h + 2)
            bar_w = max(4, int((w - 130) * pct))
            c.create_rectangle(2, y0, bar_w + 2, y0 + bar_h,
                                fill=colors[i], outline="")
            c.create_text(bar_w + 6, y0 + bar_h // 2,
                          text=f"{label}  {pct*100:.0f}%",
                          anchor="w", font=("Segoe UI", 8),
                          fill=COLORS["text"])

    # ── A4: Filter-Profile speichern / laden ─────────────────────────────────

    def _save_filter_profile(self) -> None:
        """A4: Aktuelle Filter-Einstellungen in user_prefs persistieren."""
        self._pref_set("filter_matches_min_cm", self._min_cm_var.get())
        self._pref_set("filter_matches_search", self._search_var.get())
        self._pref_set("filter_matches_rel", getattr(self, "_rel_var", tk.StringVar()).get())
        self._pref_set("filter_matches_side", getattr(self, "_side_var", tk.StringVar()).get())

    def _load_filter_profile(self) -> None:
        """A4: Gespeicherte Filter-Einstellungen aus user_prefs wiederherstellen."""
        mc = self._pref_get("filter_matches_min_cm")
        if mc:
            self._min_cm_var.set(mc)
        st = self._pref_get("filter_matches_search")
        if st:
            self._search_var.set(st)
        rel = self._pref_get("filter_matches_rel")
        if rel and hasattr(self, "_rel_var"):
            self._rel_var.set(rel)
        side = self._pref_get("filter_matches_side")
        if side and hasattr(self, "_side_var"):
            self._side_var.set(side)
        self._current_offset = 0
        self._do_refresh()

    # ── C1: cM-Beziehungs-Predictor ─────────────────────────────────────────

    def _predict_relationship(self, cm: float) -> str:
        """C1: Ermittelt möglichen Verwandtschaftsgrad aus cM-Wert.

        Nutzt die EINE kanonische Bereichstabelle (self._cm_ranges, von der App
        durchgereicht) — keine eigene zweite cM-Tabelle mehr (Deduplizierung).
        """
        for lo, hi, label, _gen in self._cm_ranges:
            if lo <= cm <= hi:
                return label
        return "Sehr entfernte Verwandtschaft oder kein Verwandter"

    def _update_cm_predictor(self, cm: float, shared_segments: int = 0,
                             longest_segment: float = 0.0) -> None:
        """C1: Aktualisiert Predictor-Label + Top-5-Panel im Detail-Panel.

        Zeigt die wahrscheinlichsten Grade mit 95%-Konfidenzintervall (statt
        einer trügerischen Punktschätzung): 1750 cM ist z. B. sowohl
        Halbgeschwister als auch Großelternteil. Segmentzahl/längstes Segment
        des Matches fließen als Endogamie-Hinweis ein (viele kurze Segmente →
        echte Verwandtschaft vermutlich entfernter als die rohe cM-Zahl zeigt).

        Speist zwei Widgets aus DERSELBEN Berechnung (früher zwei gleichnamige
        Methoden in dieser Klasse — die zweite überschrieb beim Klassenaufbau
        die erste, wodurch das 5-Zeilen-Panel _cm_predict_labels nie befüllt
        wurde und dauerhaft leer blieb):
          - _cm_predictor_var:    eine Zeile, Top 2, im Status-Detailfeld.
          - _cm_predict_labels:   bis zu 5 Zeilen im "Mögliche Verwandtschaft"-
            Panel.
        """
        try:
            from tasks.dna_predict import predict_relationship_detailed
            top = (predict_relationship_detailed(
                cm, shared_segments=shared_segments or None,
                longest_segment=longest_segment or None)
                if cm and cm > 0 else [])
        except Exception:
            top = []

        if hasattr(self, "_cm_predictor_var"):
            if not (cm and cm > 0):
                self._cm_predictor_var.set("—")
            elif top:
                parts = [f"{d['label']} ({d['ci_low']:.0f}–{d['ci_high']:.0f} cM)"
                         for d in top[:2]]
                text = f"~{cm:.0f} cM  →  " + "  ·  ".join(parts)
                if top[0]["endogamy_factor"] > 1.01:
                    text += (f"  ⚠ Segmentform spricht für Endogamie "
                            f"(korrigiert: ~{top[0]['effective_cm']:.0f} cM)")
                self._cm_predictor_var.set(text)
            else:
                # Außerhalb aller Verteilungen → Bereichstabelle als Fallback
                self._cm_predictor_var.set(
                    f"~{cm:.0f} cM  →  {self._predict_relationship(cm)}")

        if hasattr(self, "_cm_predict_labels"):
            for i, lbl in enumerate(self._cm_predict_labels):
                if i < len(top):
                    d = top[i]
                    lbl.configure(text=(
                        f"  {d['probability']*100:.0f}%  {d['label']} "
                        f"({d['ci_low']:.0f}–{d['ci_high']:.0f} cM)"))
                else:
                    lbl.configure(text="")
