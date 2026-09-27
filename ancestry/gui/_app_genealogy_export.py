"""Genealogie-Austausch-Mixin für AncestryDnaApp: GEDCOM-/Gramps-Export der
Vorfahren-Gruppen und MyTrueAncestry-CSV-Import (Populationsverteilung,
Eltern-Vergleich Basis 1/Basis 2).

Zwölfter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Reine Dialog-/Export-Methoden ohne eigene Zustandsattribute —
lesen nur self._db/self._current_guid()/self._t() und öffnen eigene
Toplevel-Fenster mit lokalem Zustand.

Erwartet von der Host-Klasse (AncestryDnaApp): self._db, self._t(),
self._current_guid().
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ancestry.gui.widgets.theme import COLORS


class GenealogyExportMixin:
    """GEDCOM-/Gramps-Export der Vorfahren-Gruppen, MyTrueAncestry-Import."""

    def _export_gedcom(self):
        """Exportiert Vorfahren-Gruppen als GEDCOM 5.5.1."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        try:
            groups = self._db.get_pedigree_groups(test_guid, min_matches=2, mode="person")
        except Exception as e:
            messagebox.showerror(self._t("dlg.db_error"), str(e))
            return
        if not groups:
            messagebox.showinfo(self._t("dlg.no_data"),
                                self._t("dlg.m_no_anc_groups"))
            return
        p = filedialog.asksaveasfilename(
            title=self._t("dlg.t_export_gedcom"),
            defaultextension=".ged",
            filetypes=[("GEDCOM", "*.ged"), ("Alle", "*.*")],
            initialfile="ancestry_dna_ancestors.ged")
        if not p:
            return
        try:
            from ancestry.core.gedcom_export import export_gedcom
            # Enrich groups with ancestor data
            enriched = []
            for g in groups:
                ancestors = []
                for guid, name, path, gen, cm in g.get("matches", []):
                    rows = self._db.get_pedigree_for_match(test_guid, guid)
                    for r in rows:
                        ancestors.append(r)
                enriched.append({**g, "ancestors": ancestors})
            n = export_gedcom(enriched, p)
            messagebox.showinfo(self._t("dlg.done"), f"{n} Personen als GEDCOM exportiert → {p}")
        except ImportError:
            messagebox.showerror(self._t("dlg.error"), self._t("dlg.m_gedexport_missing"))
        except Exception as e:
            messagebox.showerror(self._t("dlg.error"), str(e))

    def _export_gramps(self):
        """Exportiert Vorfahren-Gruppen als Gramps XML 1.7.1."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        try:
            groups = self._db.get_pedigree_groups(test_guid, min_matches=2, mode="person")
        except Exception as e:
            messagebox.showerror(self._t("dlg.db_error"), str(e))
            return
        if not groups:
            messagebox.showinfo(self._t("dlg.no_data"), self._t("dlg.m_no_anc_groups"))
            return
        p = filedialog.asksaveasfilename(
            title=self._t("dlg.t_export_gramps"),
            defaultextension=".gramps",
            filetypes=[("Gramps XML", "*.gramps"), ("Alle", "*.*")],
            initialfile="ancestry_dna_ancestors.gramps")
        if not p:
            return
        try:
            from ancestry.core.gramps_export import export_gramps
            n = export_gramps(groups, p, mask_living=True)
            messagebox.showinfo(
                self._t("dlg.done"),
                f"{n} Personen als Gramps XML exportiert → {p}\n"
                "Lebende Personen wurden als [privat] maskiert (DSGVO).")
        except Exception as e:
            messagebox.showerror(self._t("dlg.error"), str(e))

    def _import_mta(self):
        """Importiert MyTrueAncestry CSV-Export."""
        p = filedialog.askopenfilename(
            title=self._t("dlg.t_import_mta"),
            filetypes=[("CSV", "*.csv"), ("Alle", "*.*")])
        if not p:
            return
        try:
            from ancestry.core.mta_import import parse_mta_csv
            rows = parse_mta_csv(p)
        except Exception as e:
            messagebox.showerror(self._t("dlg.import_error"), str(e))
            return
        if not rows:
            messagebox.showwarning(self._t("dlg.no_data"), self._t("dlg.m_no_csv"))
            return

        win = tk.Toplevel(self)
        win.title("MyTrueAncestry – Populationsverteilung")
        win.geometry("820x560")
        head = ttk.Frame(win)
        head.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(head, text=f"MyTrueAncestry: {len(rows)} Populationen importiert",
                  style="Bold.TLabel").pack(side="left", anchor="w")
        ttk.Button(head, text="⚖ Basis 2 (Mutter) vergleichen …",
                   command=lambda: self._mta_compare_parents(rows)).pack(
            side="right")

        # Group by era and draw bar chart
        from collections import defaultdict
        era_scores: dict = defaultdict(float)
        for r in rows:
            era_scores[r["era"]] += r["score"]

        era_colors = {
            "Neolithic": "#4CAF50", "Bronze Age": "#FF9800",
            "Iron Age / Historical": "#9C27B0", "Medieval": "#2196F3",
            "Modern": "#F44336", "Ancient / Other": "#795548",
        }

        c = tk.Canvas(win, height=160, bg=COLORS["bg"], highlightthickness=0)
        c.pack(fill="x", padx=10, pady=6)

        def draw_era_bars(_=None):
            c.delete("all")
            W = c.winfo_width() or 780; H = 140
            total = sum(era_scores.values()) or 1
            sorted_eras = sorted(era_scores.items(), key=lambda x: -x[1])
            x = 10
            for era, score in sorted_eras:
                bw = max(5, int((W - 20) * score / total))
                col = era_colors.get(era, "#999999")
                c.create_rectangle(x, 20, x + bw, 80, fill=col, outline="white", width=1)
                if bw > 40:
                    c.create_text(x + bw // 2, 50, text=f"{score:.1f}%",
                                  font=("Segoe UI", 8, "bold"), fill="white")
                c.create_text(x + bw // 2, 95, text=era[:15],
                              font=("Segoe UI", 7), fill=COLORS["text"], angle=45 if bw < 60 else 0)
                x += bw + 2

        c.bind("<Configure>", draw_era_bars)
        win.after(100, draw_era_bars)

        # Detail table
        cols = ("pop","score","dist","era")
        tv = ttk.Treeview(win, columns=cols, show="headings", height=12)
        for col, (lbl, w, a) in {
            "pop":   ("Population", 300, "w"),
            "score": ("Score %",     80, "e"),
            "dist":  ("Distance",    80, "e"),
            "era":   ("Ära",        200, "w"),
        }.items():
            tv.heading(col, text=lbl); tv.column(col, width=w, anchor=a)
        sy = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sy.set)
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=4)
        sy.pack(side="right", fill="y", pady=4)
        for r in sorted(rows, key=lambda x: -x["score"])[:50]:
            tv.insert("", "end", values=(
                r["population"][:45], f"{r['score']:.2f}",
                f"{r['distance']:.4f}", r["era"]))

    def _mta_compare_parents(self, self_rows):
        """Lädt eine zweite MTA-CSV (Basis 2 = Mutter) und ordnet jede
        Population einer Elternseite zu (väterlich/mütterlich/beide)."""
        p = filedialog.askopenfilename(
            title="Basis 2 (Mutter-Kit) – MyTrueAncestry CSV",
            filetypes=[("CSV", "*.csv"), ("Alle", "*.*")])
        if not p:
            return
        try:
            from ancestry.core.mta_import import (
                classify_parental_origin,
                parse_mta_csv,
            )
            base2 = parse_mta_csv(p)
        except Exception as e:
            messagebox.showerror(self._t("dlg.import_error"), str(e))
            return
        if not base2:
            messagebox.showwarning(self._t("dlg.no_data"), self._t("dlg.m_no_csv"))
            return

        result = classify_parental_origin(self_rows, base2)
        win = tk.Toplevel(self)
        win.title("MTA – Eltern-Vergleich (Basis 1 vs. Basis 2)")
        win.geometry("760x560")
        ttk.Label(win, text=f"Eltern-Zuordnung über {len(result)} Populationen "
                            f"(Näherung: väterlich ≈ 2·eigen − mütterlich)",
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10, 4))

        cols = ("pop", "self", "mat", "pat", "origin")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for col, (lbl, w, a) in {
            "pop":    ("Population",     280, "w"),
            "self":   ("Eigen %",         80, "e"),
            "mat":    ("Mütterlich %",   100, "e"),
            "pat":    ("Väterlich ≈ %",  110, "e"),
            "origin": ("Seite",          100, "center"),
        }.items():
            tv.heading(col, text=lbl)
            tv.column(col, width=w, anchor=a)
        tv.tag_configure("mütterlich", background="#FFE0EC")
        tv.tag_configure("väterlich", background="#E0ECFF")
        tv.tag_configure("beide", background="#E8F5E9")
        sy = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sy.set)
        tv.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
        sy.pack(side="right", fill="y", pady=4)
        for r in result:
            tv.insert("", "end", tags=(r["origin"],), values=(
                r["population"][:45], f"{r['self_score']:.1f}",
                f"{r['maternal_score']:.1f}", f"{r['paternal_estimate']:.1f}",
                r["origin"]))
