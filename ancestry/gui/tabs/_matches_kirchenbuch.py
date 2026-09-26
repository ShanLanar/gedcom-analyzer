"""Kirchenbuch-Sub-Tab-Mixin für MatchesTab.

Zweiter Baustein der Mixin-Aufteilung (siehe _matches_wikitree.py für die
Begründung). Eigenständig: eigene Widgets (_kb_gen_var, _kb_surnames_var,
_kb_tree), keine Aufrufe in andere Panels hinein. Zwei Einstiege von außen
(MatchesTab._build_detail_panel bzw. MatchesTab._on_match_select).

Erwartet von der Host-Klasse (MatchesTab): self._state (AppState),
self._selected_match, self._get_test_guid() (Callback aus dem Konstruktor).
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from ancestry.gui.widgets.theme import COLORS
from ancestry.models import DnaMatch


class KirchenbuchPanelMixin:
    """Kirchenbuch-Sub-Tab: Treffer für Nachnamen aus der Match-Ahnentafel."""

    def _build_kirchenbuch_panel(self, parent):
        """Sub-Tab 5: Kirchenbuch-Treffer für Nachnamen aus der Match-Ahnentafel."""
        t  = self._state.t
        lw = self._state.lang_widgets

        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        _sv = tk.StringVar(value=t("md.kb_min_gen"))
        ttk.Label(tb, textvariable=_sv).pack(side="left")
        lw.append((_sv, "md.kb_min_gen"))
        self._kb_gen_var = tk.StringVar(value="2")
        ttk.Entry(tb, textvariable=self._kb_gen_var, width=3).pack(side="left", padx=4)
        _sv = tk.StringVar(value=t("md.kb_reload"))
        ttk.Button(tb, textvariable=_sv,
                   command=lambda: self._load_kirchenbuch_panel(self._selected_match)).pack(
                   side="left", padx=4)
        lw.append((_sv, "md.kb_reload"))
        self._kb_surnames_var = tk.StringVar(value="")
        ttk.Label(tb, textvariable=self._kb_surnames_var,
                  foreground="#666666", wraplength=300).pack(side="left", padx=(12, 0))

        cols = ("book_id", "year", "entry_type", "person", "person2",
                "father", "mother", "village", "match")
        self._kb_tree = ttk.Treeview(parent, columns=cols, show="headings",
                                      selectmode="browse")
        for col, lbl, w, anchor in [
            ("book_id",    "Kirchenbuch",    160, "w"),
            ("year",       "Jahr",            50, "center"),
            ("entry_type", "Art",             60, "w"),
            ("person",     "Person",         170, "w"),
            ("person2",    "Person 2",       130, "w"),
            ("father",     "Vater",          130, "w"),
            ("mother",     "Mutter",         130, "w"),
            ("village",    "Ort",             90, "w"),
            ("match",      "Treffer-Name",    90, "w"),
        ]:
            self._kb_tree.heading(col, text=lbl)
            self._kb_tree.column(col, width=w, anchor=anchor,
                                  stretch=(col in ("person","book_id")))
        self._kb_tree.tag_configure("exact",   foreground=COLORS.get("primary","#1a73e8"))
        self._kb_tree.tag_configure("phonetic",foreground=COLORS.get("text","#333"))
        sy = ttk.Scrollbar(parent, orient="vertical", command=self._kb_tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=self._kb_tree.xview)
        self._kb_tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self._kb_tree.pack(side="left", fill="both", expand=True, padx=(6, 0))
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")

    def _load_kirchenbuch_panel(self, match: Optional[DnaMatch]):
        """Füllt den Kirchenbuch-Tab für den ausgewählten Match (im Hintergrund).

        Die NER-Suche macht zwei nicht-indizierbare LIKE-Scans über matrikula_ner;
        deshalb läuft sie im Worker-Thread statt auf dem GUI-Thread."""
        self._kb_tree.delete(*self._kb_tree.get_children())
        self._kb_surnames_var.set("")
        if match is None:
            return
        try:
            min_gen = int(self._kb_gen_var.get() or 2)
        except ValueError:
            min_gen = 2
        test_guid = self._get_test_guid()
        guid = match.match_guid
        self._kb_surnames_var.set("…")

        def _worker():
            bundle: dict = {}
            try:
                with self._state.db._cursor() as cur:
                    ner_count = cur.execute("SELECT COUNT(*) FROM matrikula_ner").fetchone()[0]
                    mat_count = cur.execute(
                        "SELECT COUNT(*) FROM source_matrikula_entries").fetchone()[0]
                if mat_count > 0 and ner_count == 0:
                    bundle["status"] = ("⚠  Kirchenbücher vorhanden, aber NER noch nicht "
                                        "extrahiert → Matricula-Tab → „NER extrahieren“")
                    self.after(0, lambda: self._fill_kirchenbuch_panel(guid, bundle))
                    return
            except Exception:
                pass
            try:
                from ancestry.core.matricula_bridge import (
                    _pedigree_surnames, find_matricula_for_match)
                surnames = _pedigree_surnames(self._state.db, test_guid, guid, min_gen)
                bundle["surnames"] = surnames
                if surnames:
                    bundle["hits"] = find_matricula_for_match(
                        self._state.db, test_guid, guid, min_generation=min_gen)
            except Exception as e:
                bundle["error"] = str(e)
            self.after(0, lambda: self._fill_kirchenbuch_panel(guid, bundle))

        threading.Thread(target=_worker, daemon=True, name="kb-panel").start()

    def _fill_kirchenbuch_panel(self, guid, bundle):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != guid:
            return
        t = self._state.t
        self._kb_tree.delete(*self._kb_tree.get_children())
        if "status" in bundle:
            self._kb_surnames_var.set(bundle["status"])
            return
        if "error" in bundle:
            self._kb_surnames_var.set(f"Fehler: {bundle['error']}")
            return
        surnames = bundle.get("surnames") or []
        if not surnames:
            self._kb_surnames_var.set(t("md.kb_no_ped"))
            return
        self._kb_surnames_var.set(
            f"{t('md.kb_surnames')} {', '.join(surnames[:8])}"
            + (" …" if len(surnames) > 8 else ""))
        hits = bundle.get("hits") or []
        if not hits:
            self._kb_surnames_var.set(
                f"{t('md.kb_no_hits')}  ({t('md.kb_surnames')} {', '.join(surnames[:4])})")
            return
        for h in hits:
            # Buchpfad kürzen: "deutschland/osnabrueck/ostercappeln/b1" → "ostercappeln/b1"
            book = h.get("book_id") or ""
            parts = book.split("/")
            book_short = "/".join(parts[-2:]) if len(parts) >= 2 else book
            tag = "exact" if h.get("exact_match") else "phonetic"
            self._kb_tree.insert("", "end", tags=(tag,), values=(
                book_short,
                h.get("event_year") or "—",
                h.get("entry_type") or "—",
                h.get("person_name") or "—",
                h.get("person2_name") or "",
                h.get("father_name") or "",
                h.get("mother_name") or "",
                h.get("village") or "",
                h.get("name_raw") or "",
            ))
