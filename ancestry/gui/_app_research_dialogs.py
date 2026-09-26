"""Zweiter Analyse-Dialoge-Mixin für AncestryDnaApp ('Neue Analyse-Methoden':
Ahnentafel-Lücken, Ahnentafel-Chart, Endogamie, Populationsstatistik,
Forschungs-Dashboard, Cluster-Copilot, Nachnamen-Matrix, Entity-Review,
NER-Suche).

Vierter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Wie AnalysisDialogsMixin (_app_analysis_dialogs.py): reine
Dialog-Öffner, meist dünne Delegationen an ancestry/gui/analysis/*, keine
eigenen Zustandsattribute außer dem lokalen Fenster-State innerhalb einer
einzelnen Methode.

Erwartet von der Host-Klasse (AncestryDnaApp): self._db, self._t().
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ResearchDialogsMixin:
    """Ahnentafel-Lücken/-Chart, Endogamie, Populationsstatistik,
    Forschungs-Dashboard, Cluster-Copilot, Nachnamen-Matrix, Entity-Review,
    NER-Suche."""

    def _show_pedigree_gaps(self):
        from ancestry.gui.analysis.pedigree import show_pedigree_gaps
        show_pedigree_gaps(self)

    def _show_pedigree_chart(self):
        from ancestry.gui.analysis.pedigree_chart import show_pedigree_chart
        show_pedigree_chart(self)

    def _show_endogamy_analysis(self):
        from ancestry.gui.analysis.mrca import show_endogamy_analysis
        show_endogamy_analysis(self)

    def _show_population_stats(self):
        from ancestry.gui.analysis.population import show_population_stats
        show_population_stats(self)

    def _show_research_dashboard(self):
        from ancestry.gui.analysis.research_dashboard import show_research_dashboard
        show_research_dashboard(self)

    def _copilot_explain_cluster(self):
        """Öffnet ein Popup das den ausgewählten Cluster via Claude erklärt."""
        from tkinter import messagebox, scrolledtext

        from ancestry.core.ai_copilot import (
            availability_hint,
            cluster_prompt,
            explain_async,
            is_available,
        )

        clusters = getattr(self, "_clusters", {}) or {}
        if not clusters:
            messagebox.showinfo(self._t("dlg.explain_cluster"),
                                self._t("dlg.m_do_clustering"))
            return

        win = tk.Toplevel(self)
        win.title("🤖 Cluster-Copilot")
        win.geometry("620x440")

        top = ttk.Frame(win)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="Cluster:").pack(side="left")
        opts = [f"#{cid}  ({len(members)} Mitglieder)"
                for cid, members in sorted(clusters.items())]
        sel = tk.StringVar(value=opts[0] if opts else "")
        cb = ttk.Combobox(top, textvariable=sel, values=opts, width=28, state="readonly")
        cb.pack(side="left", padx=6)

        btn_var = tk.StringVar(value="🤖 Erklären")
        btn = ttk.Button(top, textvariable=btn_var,
                         state="normal" if is_available() else "disabled")
        btn.pack(side="left", padx=6)

        txt = scrolledtext.ScrolledText(win, wrap="word", font=("Segoe UI", 9),
                                        state="disabled", bg="#fafafa")
        txt.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        hint = availability_hint()
        if hint:
            txt.configure(state="normal")
            txt.insert("end", hint)
            txt.configure(state="disabled")

        def _explain():
            raw = sel.get()
            try:
                cid = int(raw.split("#")[1].split()[0])
            except (IndexError, ValueError):
                return
            members = clusters.get(cid, [])
            prompt = cluster_prompt(cid, members)
            if not prompt:
                return
            btn.configure(state="disabled")
            btn_var.set("⏳ Claude denkt …")
            txt.configure(state="normal")
            txt.delete("1.0", "end")

            def _chunk(t: str) -> None:
                win.after(0, lambda c=t: _append(c))

            def _done(_: str) -> None:
                win.after(0, _finish)

            def _append(t: str) -> None:
                txt.configure(state="normal")
                txt.insert("end", t)
                txt.see("end")

            def _finish() -> None:
                txt.configure(state="disabled")
                btn.configure(state="normal")
                btn_var.set("🤖 Erklären")

            explain_async(prompt, on_chunk=_chunk, on_done=_done)

        btn.configure(command=_explain)

    def _show_surname_matrix(self):
        """Öffnet die Nachnamen-Ähnlichkeits-Matrix."""
        from ancestry.gui.analysis.surname_matrix_view import show_surname_matrix
        show_surname_matrix(self)

    def _show_entity_review(self):
        from ancestry.gui.analysis.entity_review import open_entity_review
        open_entity_review(self, self._db)

    def _show_ner_search(self):
        from ancestry.gui.analysis.ner_search import show_ner_search
        show_ner_search(self, self._db)
