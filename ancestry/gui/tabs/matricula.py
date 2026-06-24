"""Matricula-Tab: Kirchenbuch-Scans pro Pfarrei starten und überwachen.

Läuft als eigener Subprozess (scan_matricula_kirchspiel.py) und damit
parallel zu Ancestry-/MyHeritage-Downloads — Tageslimits der DNA-Portale
blockieren die Kirchenbuch-Erschließung nicht.

Pfarrei-Auswahl per Dropdown; fertig transkribierte Pfarreien sind in der
Übersicht ausgegraut und mit ✓ markiert. Optional wird nach Abschluss einer
Pfarrei automatisch die nächste offene gestartet (Warteschlangen-Prinzip).
"""

from __future__ import annotations

import csv
import datetime
import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import COLORS
from ancestry.gui.widgets.tooltip import register_tooltip

log = logging.getLogger(__name__)
from ancestry.tools import matricula_status as mstat


class MatriculaTab(ttk.Frame):
    """Matricula-Kirchenbuch-Tab."""

    BOOK_TYPES = ["(alle)", "Taufe", "Heirat", "Tod"]

    def __init__(
        self,
        parent: tk.Widget,
        state: AppState,
        set_status: Callable[[str], None],
    ):
        super().__init__(parent)
        self._state = state
        self._set_status = set_status
        self._proc: Optional[subprocess.Popen] = None
        self._log_queue: "queue.Queue[str]" = queue.Queue()
        self._stop_requested = False
        self._label_to_id: dict[str, str] = {}
        self._search_after_id: Optional[str] = None
        self._build()
        self._poll_log()
        self._state.register_data_change(
            lambda src: self.after(0, self.refresh_parishes) if src == "mat_catalog" else None
        )

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        t  = self._state.t
        lw = self._state.lang_widgets

        # ── Outer Notebook: "Pfarreien" + "Korrekturen" ──────────────────────
        self._outer_nb = ttk.Notebook(self)
        self._outer_nb.pack(fill="both", expand=True)

        pfarreien_frame = ttk.Frame(self._outer_nb)
        self._outer_nb.add(pfarreien_frame, text="📋 Pfarreien")

        korrekturen_frame = ttk.Frame(self._outer_nb)
        self._outer_nb.add(korrekturen_frame, text="✏ Korrekturen")

        self._build_pfarreien_tab(pfarreien_frame, t, lw)
        self._build_corrections_tab(korrekturen_frame)

        # Defensiv: ein Fehler beim Pfarrei-Laden darf die gesamte App-Init
        # nicht abbrechen (z. B. fehlendes Matricula-Schema).
        try:
            self.refresh_parishes()
        except Exception:
            log.exception("refresh_parishes beim Tab-Aufbau fehlgeschlagen")

    def _build_pfarreien_tab(self, parent: tk.Widget, t, lw):
        """Bisheriger Pfarreien-Inhalt, nun in eigenem Sub-Tab."""

        # ── Bistums-Übersicht ─────────────────────────────────────────────────
        self._overview_frame: tk.Frame | None = None
        self._build_diocese_overview(parent)

        # ── Bistums-Zeile ─────────────────────────────────────────────────────
        dioc_row = ttk.Frame(parent); dioc_row.pack(fill="x", padx=14, pady=(10, 2))
        ttk.Label(dioc_row, text="Bistum/Archiv:", style="Bold.TLabel").pack(side="left")
        self._diocese_var = tk.StringVar(value="(alle)")
        self._diocese_combo = ttk.Combobox(
            dioc_row, textvariable=self._diocese_var, width=42, state="readonly")
        self._diocese_combo.pack(side="left", padx=(6, 12))
        self._diocese_combo.bind("<<ComboboxSelected>>", self._on_diocese_changed)
        ttk.Button(dioc_row, text="Katalog laden",
                   command=self._start_catalog_scraper).pack(side="left", padx=(0, 6))
        register_tooltip(
            ttk.Label(dioc_row,
                      text="ⓘ scrape_matricula.py --diocese <slug>",
                      foreground="#888888", font=("Segoe UI", 8)),
            "tt.mat_catalog", self._state
        )

        # ── Pfarrei-Zeile ─────────────────────────────────────────────────────
        top = ttk.Frame(parent); top.pack(fill="x", padx=14, pady=(2, 4))

        _sv = tk.StringVar(value=t("mat.next"))
        ttk.Label(top, textvariable=_sv, style="Bold.TLabel").pack(side="left")
        lw.append((_sv, "mat.next"))
        self._parish_var = tk.StringVar()
        self._parish_combo = ttk.Combobox(
            top, textvariable=self._parish_var, width=52, state="readonly")
        self._parish_combo.pack(side="left", padx=(6, 12))

        _sv = tk.StringVar(value=t("mat.booktype"))
        ttk.Label(top, textvariable=_sv).pack(side="left")
        lw.append((_sv, "mat.booktype"))
        self._booktype_var = tk.StringVar(value=self.BOOK_TYPES[0])
        ttk.Combobox(top, textvariable=self._booktype_var, width=10,
                     state="readonly", values=self.BOOK_TYPES).pack(side="left", padx=6)

        bar = ttk.Frame(parent); bar.pack(fill="x", padx=14, pady=4)
        self._start_btn = ttk.Button(bar, text=t("mat.start"), command=self._start_scan)
        self._start_btn.pack(side="left")
        register_tooltip(self._start_btn, "tt.mat_start", self._state)
        lw.append((self._start_btn, "mat.start"))
        self._stop_btn = ttk.Button(bar, text=t("mat.stop"),
                                    command=self._stop_scan, state="disabled")
        self._stop_btn.pack(side="left", padx=6)
        register_tooltip(self._stop_btn, "tt.mat_stop", self._state)
        lw.append((self._stop_btn, "mat.stop"))
        _btn = ttk.Button(bar, text=t("mat.refresh"), command=self.refresh_parishes)
        _btn.pack(side="left", padx=6)
        register_tooltip(_btn, "tt.mat_refresh", self._state)
        lw.append((_btn, "mat.refresh"))
        self._ner_btn = ttk.Button(bar, text="NER extrahieren", command=self._extract_ner)
        self._ner_btn.pack(side="left", padx=6)
        register_tooltip(self._ner_btn, "tt.mat_ner", self._state)
        ttk.Button(bar, text="🔍 NER-Suche",
                   command=self._show_ner_search).pack(side="left", padx=6)
        ttk.Button(bar, text="📥 Export (CSV/XLSX)",
                   command=self._export_entries).pack(side="left", padx=6)

        self._autonext_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=t("mat.autonext"))
        cb = ttk.Checkbutton(bar, variable=self._autonext_var, textvariable=_sv)
        cb.pack(side="left", padx=(16, 0))
        lw.append((_sv, "mat.autonext"))

        self._auto_ner_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, variable=self._auto_ner_var,
                        text="Auto-NER").pack(side="left", padx=(8, 0))

        # OCR-Backend-Anzeige (MATRICULA_OCR_BACKEND, read-only info)
        _ocr_backend = os.environ.get("MATRICULA_OCR_BACKEND", "claude")
        _ocr_color = {"claude": "#b45309", "tesseract": "#166534", "kraken": "#1e40af"}.get(
            _ocr_backend, "#374151")
        _ocr_lbl = ttk.Label(bar, text=f"OCR: {_ocr_backend}",
                             foreground=_ocr_color, font=("Segoe UI", 8, "bold"))
        _ocr_lbl.pack(side="right", padx=(0, 4))
        register_tooltip(_ocr_lbl, "tt.mat_ocr", self._state)

        # Pfarreien-Übersicht: fertig = ✓ + ausgegraut
        _sv = tk.StringVar(value=t("mat.overview"))
        ttk.Label(parent, textvariable=_sv, style="Bold.TLabel").pack(
            anchor="w", padx=14, pady=(8, 2))
        lw.append((_sv, "mat.overview"))

        mid = ttk.Frame(parent); mid.pack(fill="both", expand=True, padx=14, pady=(0, 4))
        cols = ("parish", "books", "pages", "status")
        self._tv = ttk.Treeview(mid, columns=cols, show="headings", height=8,
                                selectmode="browse")
        for col, lbl, w, anchor in [
            ("parish", "Pfarrei",      280, "w"),
            ("books",  "Bücher",        70, "center"),
            ("pages",  "Seiten",       120, "center"),
            ("status", "Status",       110, "center"),
        ]:
            self._tv.heading(col, text=lbl)
            self._tv.column(col, width=w, anchor=anchor)
        self._tv.tag_configure("done", foreground="#999999")
        self._tv.tag_configure("partial", foreground=COLORS.get("primary", "#1a73e8"))
        self._tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self._tv.yview)
        sb.pack(side="right", fill="y")
        self._tv.configure(yscrollcommand=sb.set)
        self._tv.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Log
        self._log = tk.Text(parent, height=10, wrap="word",
                            font=("Consolas", 9), state="disabled")
        self._log.pack(fill="both", expand=True, padx=14, pady=(4, 10))

    # ── OCR-Korrektur-Tab ─────────────────────────────────────────────────────

    def _build_corrections_tab(self, parent: tk.Widget):
        """Tab für OCR-Korrektur ungeprüfter Einträge."""
        # Filter controls
        ctrl = ttk.Frame(parent)
        ctrl.pack(fill="x", padx=8, pady=4)
        ttk.Label(ctrl, text="Nur unkorrigierte:").pack(side="left")
        self._corr_only_open = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, variable=self._corr_only_open).pack(side="left", padx=4)
        ttk.Label(ctrl, text="  Buchtyp:").pack(side="left")
        self._corr_booktype_var = tk.StringVar(value="(alle)")
        ttk.Combobox(ctrl, textvariable=self._corr_booktype_var, width=10,
                     state="readonly",
                     values=["(alle)"] + self.BOOK_TYPES[1:]).pack(side="left", padx=4)
        ttk.Button(ctrl, text="🔄 Laden",
                   command=self._load_corrections).pack(side="left", padx=8)

        # Treeview listing entries
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        cols = ("book_id", "book_type", "person", "date", "status")
        self._corr_tree = ttk.Treeview(
            list_frame, columns=cols, show="headings", height=10,
            selectmode="extended",
        )
        self._corr_tree.heading("book_id",   text="Buch-ID")
        self._corr_tree.heading("book_type", text="Buchtyp")
        self._corr_tree.heading("person",    text="Person")
        self._corr_tree.heading("date",      text="Datum")
        self._corr_tree.heading("status",    text="Status")
        self._corr_tree.column("book_id",   width=160)
        self._corr_tree.column("book_type", width=70)
        self._corr_tree.column("person",    width=160)
        self._corr_tree.column("date",      width=90)
        self._corr_tree.column("status",    width=90, anchor="center")

        sb = ttk.Scrollbar(list_frame, orient="vertical",
                           command=self._corr_tree.yview)
        self._corr_tree.configure(yscrollcommand=sb.set)
        self._corr_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self._corr_tree.bind("<<TreeviewSelect>>", self._on_corr_select)

        # Edit area
        edit_frame = ttk.LabelFrame(parent, text="Transkription bearbeiten", padding=8)
        edit_frame.pack(fill="x", padx=8, pady=4)

        self._corr_text = tk.Text(edit_frame, height=5, wrap="word",
                                  font=("Segoe UI", 9))
        self._corr_text.pack(fill="x")

        btn_row = ttk.Frame(edit_frame)
        btn_row.pack(fill="x", pady=(4, 0))
        ttk.Button(btn_row, text="💾 Korrektur speichern",
                   command=self._save_correction).pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="✓ Als korrekt markieren",
                   command=lambda: self._save_correction(mark_correct=True)).pack(side="left")
        self._corr_id_var = tk.IntVar(value=-1)

        # Batch-Buttons für Mehrfachauswahl
        batch_row = ttk.Frame(edit_frame)
        batch_row.pack(fill="x", pady=(4, 0))
        ttk.Label(batch_row, text="Mehrfachauswahl:",
                  font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))
        ttk.Button(batch_row, text="✓ Alle ausgewählten bestätigen",
                   command=self._batch_confirm).pack(side="left", padx=(0, 6))
        ttk.Button(batch_row, text="✗ Alle ausgewählten ablehnen",
                   command=self._batch_reject).pack(side="left")

        # Status-Zeile
        self._corr_status_var = tk.StringVar(value="")
        ttk.Label(edit_frame, textvariable=self._corr_status_var,
                  foreground="#555555", font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))

    def _load_corrections(self):
        """Lädt Einträge aus source_matrikula_entries in den Korrektur-Treeview."""
        only_open = self._corr_only_open.get()
        book_filter = self._corr_booktype_var.get()

        rows: list = []
        try:
            with self._state.db._cursor() as cur:
                # Prüfe ob Tabelle vorhanden
                cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='source_matrikula_entries'"
                )
                if cur.fetchone() is None:
                    self._corr_status_var.set("Keine OCR-Daten verfügbar.")
                    return

                where_parts = []
                params: list = []
                if only_open:
                    where_parts.append(
                        "(corrected_at IS NULL OR corrected_at = '')"
                    )
                if book_filter and book_filter != "(alle)":
                    where_parts.append("entry_type = ?")
                    params.append(book_filter)

                where_sql = ("WHERE " + " AND ".join(where_parts)
                             if where_parts else "")
                rows = cur.execute(
                    f"""
                    SELECT entry_id, book_id, entry_type, person_name,
                           event_date, corrected_at
                    FROM source_matrikula_entries
                    {where_sql}
                    ORDER BY entry_id ASC
                    LIMIT 500
                    """,
                    params,
                ).fetchall()
        except Exception as exc:
            self._corr_status_var.set(f"Fehler: {exc}")
            return

        for item in self._corr_tree.get_children():
            self._corr_tree.delete(item)

        for r in rows:
            entry_id, book_id, entry_type, person_name, event_date, corrected_at = r
            status = "✓ korrigiert" if corrected_at else "○ offen"
            self._corr_tree.insert(
                "", "end", iid=str(entry_id),
                values=(
                    book_id or "",
                    entry_type or "",
                    person_name or "",
                    event_date or "",
                    status,
                ),
            )
        self._corr_status_var.set(f"{len(rows)} Einträge geladen.")

    def _on_corr_select(self, _event=None):
        """Zeigt den Transkriptions-Text des gewählten Eintrags im Textfeld."""
        sel = self._corr_tree.selection()
        if not sel:
            return
        rid = int(sel[0])
        self._corr_id_var.set(rid)
        try:
            with self._state.db._cursor() as cur:
                row = cur.execute(
                    "SELECT notes, raw_json FROM source_matrikula_entries"
                    " WHERE entry_id = ?",
                    (rid,),
                ).fetchone()
            if row:
                # Bevorzuge notes; falls leer, extrahiere raw_text aus raw_json
                text = row[0] or ""
                if not text and row[1]:
                    import json as _json
                    try:
                        text = _json.loads(row[1]).get("raw_text", "")
                    except Exception:
                        pass
                self._corr_text.delete("1.0", "end")
                self._corr_text.insert("1.0", text)
        except Exception:
            pass

    def _save_correction(self, mark_correct: bool = False):
        """Speichert die bearbeitete Transkription zurück in die DB."""
        rid = self._corr_id_var.get()
        if rid < 0:
            return
        new_text = self._corr_text.get("1.0", "end").strip()
        now = datetime.datetime.now().isoformat()
        try:
            with self._state.db._cursor() as cur:
                # Prüfe ob Spalte corrected_by existiert (Migrations-Guard)
                col_sql = (
                    "UPDATE source_matrikula_entries"
                    " SET notes = ?, corrected_at = ?, corrected_by = ?"
                    " WHERE entry_id = ?"
                )
                try:
                    cur.execute(col_sql, (new_text, now, "gui", rid))
                except Exception:
                    # Fallback ohne corrected_by
                    cur.execute(
                        "UPDATE source_matrikula_entries"
                        " SET notes = ?, corrected_at = ?"
                        " WHERE entry_id = ?",
                        (new_text, now, rid),
                    )
        except Exception as exc:
            messagebox.showerror("Fehler", str(exc), parent=self)
            return
        self._corr_status_var.set(
            f"Eintrag {rid} gespeichert ({'als korrekt markiert' if mark_correct else 'bearbeitet'})."
        )
        self._load_corrections()

    def _batch_apply(self, mark_correct: bool) -> None:
        """Wendet Bestätigung/Ablehnung auf alle selektierten Treeview-Zeilen an."""
        sel = self._corr_tree.selection()
        if not sel:
            self._corr_status_var.set("Keine Einträge ausgewählt.")
            return

        now = datetime.datetime.now().isoformat()
        saved = 0
        errors: list[str] = []
        for iid in sel:
            rid = int(iid)
            try:
                with self._state.db._cursor() as cur:
                    try:
                        cur.execute(
                            "UPDATE source_matrikula_entries"
                            " SET corrected_at = ?, corrected_by = ?"
                            " WHERE entry_id = ?",
                            (now, "gui", rid),
                        )
                    except Exception:
                        cur.execute(
                            "UPDATE source_matrikula_entries"
                            " SET corrected_at = ?"
                            " WHERE entry_id = ?",
                            (now, rid),
                        )
                saved += 1
            except Exception as exc:
                errors.append(f"{rid}: {exc}")

        action = "bestätigt" if mark_correct else "abgelehnt"
        msg = f"{saved} Korrekturen {action}."
        if errors:
            msg += f" Fehler: {'; '.join(errors[:3])}"
        self._corr_status_var.set(msg)
        self._load_corrections()

    def _batch_confirm(self) -> None:
        """Bestätigt alle ausgewählten Einträge als korrekt."""
        self._batch_apply(mark_correct=True)

    def _batch_reject(self) -> None:
        """Lehnt alle ausgewählten Einträge ab (setzt corrected_at ohne Textänderung)."""
        self._batch_apply(mark_correct=False)

    # ── CSV/XLSX-Export ───────────────────────────────────────────────────────

    def _export_entries(self) -> None:
        """Exportiert Kirchenbuch-Einträge der aktuellen Pfarrei als CSV oder XLSX."""
        # Dateiformat-Auswahl
        filetypes = [("CSV-Datei", "*.csv")]
        try:
            import openpyxl  # noqa: F401
            filetypes.append(("Excel-Datei", "*.xlsx"))
        except ImportError:
            pass

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Kirchenbuch-Einträge exportieren",
            defaultextension=".csv",
            filetypes=filetypes,
        )
        if not path:
            return

        # Aktuell gewählte Pfarrei bestimmen
        parish_label = self._parish_var.get()
        parish_id = self._label_to_id.get(parish_label)

        columns = [
            "entry_id", "book_id", "entry_type", "person_name",
            "event_date", "notes", "corrected_at", "corrected_by",
        ]
        try:
            with self._state.db._cursor() as cur:
                # Prüfe ob Tabelle vorhanden
                cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='source_matrikula_entries'"
                )
                if cur.fetchone() is None:
                    messagebox.showwarning("Export", "Keine OCR-Daten verfügbar.", parent=self)
                    return

                # Verfügbare Spalten ermitteln (Migrations-Schutz)
                col_info = cur.execute(
                    "PRAGMA table_info(source_matrikula_entries)"
                ).fetchall()
                existing_cols = {row[1] for row in col_info}
                export_cols = [c for c in columns if c in existing_cols]

                if not export_cols:
                    messagebox.showwarning("Export", "Tabelle hat keine bekannten Spalten.",
                                          parent=self)
                    return

                where_sql = ""
                params: list = []
                if parish_id:
                    # parish_id ist in source_matrikula_books, nicht direkt in entries —
                    # prüfe ob parish_id-Spalte direkt existiert oder via book_id joinen
                    if "parish_id" in existing_cols:
                        where_sql = "WHERE parish_id = ?"
                        params.append(parish_id)

                col_list = ", ".join(export_cols)
                rows = cur.execute(
                    f"SELECT {col_list} FROM source_matrikula_entries {where_sql}"
                    " ORDER BY entry_id",
                    params,
                ).fetchall()

        except Exception as exc:
            messagebox.showerror("Export-Fehler", str(exc), parent=self)
            return

        n = len(rows)
        path_lower = path.lower()

        try:
            if path_lower.endswith(".xlsx"):
                import openpyxl

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Kirchenbuch"
                ws.append(export_cols)
                for row in rows:
                    ws.append(list(row))
                wb.save(path)
            else:
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(export_cols)
                    writer.writerows(rows)

        except Exception as exc:
            messagebox.showerror("Export-Fehler", f"Schreiben fehlgeschlagen:\n{exc}",
                                 parent=self)
            return

        short_path = Path(path).name
        self._set_status(f"✓ {n} Einträge exportiert nach {short_path}")
        self._log_line(f"✓ Export: {n} Einträge → {path}")

    # ── Bistums-Übersicht ─────────────────────────────────────────────────────

    def _build_diocese_overview(self, parent_frame: tk.Widget):
        """Kompakte visuelle Bistums-Übersicht am oberen Rand des Tabs."""
        lf = ttk.LabelFrame(parent_frame, text="📋 Bistums-Übersicht", padding=6)
        lf.pack(fill="x", padx=14, pady=(8, 2))
        self._overview_frame = lf
        self._render_diocese_tiles(lf)

    def _render_diocese_tiles(self, container: tk.Widget):
        """Tiles in *container* aufbauen (beim Refresh wird der Inhalt ersetzt)."""
        for child in container.winfo_children():
            child.destroy()

        bg = self._state.colors().get("bg", "#F0F4F8")
        dioceses = mstat.get_dioceses()

        if not dioceses:
            tk.Label(
                container,
                text=(
                    "Noch keine Bistümer geladen. "
                    "Bistums-Katalog im Werkzeuge-Tab starten."
                ),
                foreground="#AAAAAA",
                background=bg,
            ).pack(anchor="w", pady=2)
            return

        # --- Pfarrei-Status einmal laden und nach Diözesen-Pfad aggregieren ---
        all_parishes = mstat.get_parish_status()
        counts: dict[str, dict[str, int]] = {}
        for p in all_parishes:
            key = p["diocese"]
            if key not in counts:
                counts[key] = {"total": 0, "done": 0, "partial": 0, "open_": 0}
            counts[key]["total"] += 1
            if p["status"] == mstat.STATUS_DONE:
                counts[key]["done"] += 1
            elif p["status"] == mstat.STATUS_PARTIAL:
                counts[key]["partial"] += 1
            else:
                counts[key]["open_"] += 1

        # --- Scrollbarer Bereich (horizontal per Canvas) ----------------------
        outer = tk.Frame(container, background=bg)
        outer.pack(fill="x", expand=False)

        canvas = tk.Canvas(outer, height=120, highlightthickness=0, background=bg)
        canvas.pack(side="left", fill="x", expand=True)

        vsb = ttk.Scrollbar(outer, orient="horizontal", command=canvas.xview)
        vsb.pack(side="bottom", fill="x")
        canvas.configure(xscrollcommand=vsb.set)

        inner = tk.Frame(canvas, background=bg)
        canvas_window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Canvas-Breite dem inneren Frame anpassen (wenn wenig Tiles)
            req = inner.winfo_reqwidth()
            canvas_w = canvas.winfo_width()
            canvas.itemconfigure(canvas_window, width=max(req, canvas_w))

        inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_configure)

        # Mousewheel horizontal scrollen (Windows/Linux)
        def _on_wheel(evt):
            canvas.xview_scroll(int(-1 * (evt.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _on_wheel)

        # --- Je Diözese ein Tile bauen ----------------------------------------
        COL_GREEN  = "#217A3C"
        COL_ORANGE = "#C85000"
        COL_GRAY   = "#AAAAAA"

        for col_idx, d in enumerate(dioceses):
            diocese_path = d["path"]
            name = d.get("name") or d["path"]
            if len(name) > 20:
                name = name[:19] + "…"

            c = counts.get(diocese_path, {"total": 0, "done": 0, "partial": 0, "open_": 0})
            total    = c["total"]
            done_n   = c["done"]
            partial_n = c["partial"]
            open_n   = c["open_"]

            tile = tk.Frame(inner, relief="groove", bd=1, padx=6, pady=4, background=bg)
            tile.grid(row=0, column=col_idx, padx=4, pady=4, sticky="n")

            # Zeile 1: Name fett
            tk.Label(tile, text=name, font=("Segoe UI", 9, "bold"),
                     background=bg).pack(anchor="w")

            # Zeile 2: Zähler
            summary = (
                f"{total} Pfarreien · {done_n} fertig / "
                f"{partial_n} teilw. / {open_n} offen"
            )
            tk.Label(tile, text=summary, font=("Segoe UI", 8),
                     background=bg, foreground="#555555").pack(anchor="w")

            # Mini-Fortschrittsbalken (rot | orange | grün)
            bar_w = 120
            bar_h = 8
            bar_canvas = tk.Canvas(tile, width=bar_w, height=bar_h,
                                   highlightthickness=0, background=COL_GRAY)
            bar_canvas.pack(anchor="w", pady=(2, 4))
            if total > 0:
                pct_done    = done_n    / total
                pct_partial = partial_n / total
                x_open      = 0
                x_partial   = int(bar_w * (open_n / total))
                x_done      = x_partial + int(bar_w * pct_partial)
                x_end       = x_done   + int(bar_w * pct_done)
                # Grau (offen) ist der Canvas-Hintergrund selbst
                if x_partial > x_open:
                    bar_canvas.create_rectangle(
                        x_open, 0, x_partial, bar_h, fill=COL_GRAY, outline="")
                if x_done > x_partial:
                    bar_canvas.create_rectangle(
                        x_partial, 0, x_done, bar_h, fill=COL_ORANGE, outline="")
                if x_end > x_done:
                    bar_canvas.create_rectangle(
                        x_done, 0, x_end, bar_h, fill=COL_GREEN, outline="")

            # "Katalog laden"-Button
            slug = d.get("slug") or d["path"]

            def _load_catalog(s=slug, d_path=diocese_path, d_name=d.get("name", "")):
                # Bistum im Dropdown setzen
                label = (
                    f"{s}  —  {d_name}"
                    if d_name and d_name != d_path
                    else d_path
                )
                values = list(self._diocese_combo.cget("values"))
                if label in values:
                    self._diocese_var.set(label)
                else:
                    # Fallback: nach slug suchen
                    match = next((v for v in values if v.startswith(s + "  —  ")
                                  or v == d_path), None)
                    if match:
                        self._diocese_var.set(match)
                    else:
                        self._diocese_var.set(d_path)
                self.refresh_parishes()
                self._start_catalog_scraper()

            ttk.Button(tile, text="Katalog laden",
                       command=_load_catalog).pack(anchor="w")

    def _refresh_diocese_overview(self):
        """Overview-Tiles neu aufbauen (nach parish-Refresh aufrufen)."""
        if self._overview_frame is not None and self._overview_frame.winfo_exists():
            self._render_diocese_tiles(self._overview_frame)

    # ── Debounced-Suche ───────────────────────────────────────────────────────

    def _on_diocese_changed(self, _event=None):
        """Debounced Handler für Bistum-Combobox-Auswahl (350 ms Verzögerung)."""
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None
        self._search_after_id = self.after(350, self._do_search)

    def _do_search(self):
        """Führt die Pfarrei-Aktualisierung nach Debounce-Delay aus."""
        self._search_after_id = None
        self.refresh_parishes()

    # ── Pfarrei-Status ────────────────────────────────────────────────────────

    def refresh_parishes(self):
        """Dropdown + Übersicht aus matricula_parishes.db neu laden."""
        # Bistümer-Liste aktualisieren
        dioceses = mstat.get_dioceses()
        dioc_labels = ["(alle)"] + [
            f"{d['slug']}  —  {d['name']}" if d.get("name") and d["name"] != d["path"]
            else d["path"]
            for d in dioceses
        ]
        cur_dioc = self._diocese_var.get()
        self._diocese_combo.configure(values=dioc_labels)
        if cur_dioc not in dioc_labels:
            self._diocese_var.set("(alle)")

        # Diözesen-Filter bestimmen
        diocese_filter: Optional[str] = None
        if cur_dioc and cur_dioc != "(alle)":
            # Slug aus dem Label extrahieren
            slug = cur_dioc.split("  —  ")[0].strip()
            # In DB-Pfad übersetzen (z.B. "osnabrueck" → "deutschland/osnabrueck")
            diocese_filter = next(
                (d["path"] for d in dioceses if d["slug"] == slug or d["path"] == slug),
                None)

        parishes = mstat.get_parish_status(diocese=diocese_filter)
        self._tv.delete(*self._tv.get_children())
        self._label_to_id.clear()

        if not parishes:
            self._parish_combo.configure(values=[])
            self._start_btn.configure(state="disabled")
            if not dioceses:
                self._log_line(self._state.t("mat.no_db"))
            else:
                self._log_line("Für dieses Bistum wurden noch keine Pfarreien gescrapt.")
            self._refresh_diocese_overview()
            return
        self._start_btn.configure(state="normal" if self._proc is None else "disabled")

        combo_values = []
        for p in parishes:
            label = mstat.format_parish_label(p)
            self._label_to_id[label] = p["id"]
            total = p["pages_total"]
            pages = (f"{p['pages_done']}/{total}" if total
                     else (str(p["pages_done"]) if p["pages_done"] else "—"))
            tag = ("done" if p["status"] == mstat.STATUS_DONE
                   else "partial" if p["status"] == mstat.STATUS_PARTIAL else "")
            self._tv.insert("", "end", values=(p["name"], p["n_books"] or "—",
                                               pages, p["status"]),
                            tags=(tag,) if tag else ())
            if p["status"] != mstat.STATUS_DONE:
                combo_values.append(label)

        self._parish_combo.configure(values=combo_values)
        if combo_values and not self._parish_var.get():
            partial = [v for v in combo_values if v.startswith("◐")]
            self._parish_var.set(partial[0] if partial else combo_values[0])
        self._refresh_diocese_overview()

    def _start_catalog_scraper(self):
        """Startet scrape_matricula.py für das gewählte Bistum."""
        if self.is_running():
            messagebox.showwarning("Läuft", "Es läuft bereits ein Scan-Prozess.")
            return
        cur = self._diocese_var.get()
        if cur == "(alle)" or not cur:
            messagebox.showinfo(
                "Bistum wählen",
                "Bitte zuerst ein Bistum im Dropdown auswählen.\n\n"
                "Oder starten Sie scrape_matricula.py manuell ohne --diocese\n"
                "um alle verfügbaren Bistümer aufzulisten.")
            return
        slug = cur.split("  —  ")[0].strip()
        args = [sys.executable, "-m", "ancestry.tools.scrape_matricula",
                "--diocese", slug]
        self._log_line(f"Starte Katalog-Scraper: {' '.join(args)}")
        try:
            self._proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(Path(sys.executable).resolve().parent.parent),
            )
            self._stop_requested = False
            self._start_btn.configure(state="disabled")
            self._stop_btn.configure(state="normal")
            threading.Thread(target=self._pump_output, daemon=True,
                             name="matricula-catalog").start()
        except Exception as e:
            self._log_line(f"Fehler beim Starten: {e}")
            self._proc = None

    def _on_tree_select(self, _event=None):
        sel = self._tv.selection()
        if not sel:
            return
        name = self._tv.item(sel[0], "values")[0]
        for label in self._parish_combo["values"]:
            if name in label:
                self._parish_var.set(label)
                break

    # ── Scan-Subprozess ───────────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _start_scan(self):
        label = self._parish_var.get()
        parish_id = self._label_to_id.get(label, "")
        if not parish_id:
            messagebox.showinfo("Matricula", self._state.t("mat.m_choose_parish"))
            return
        if self.is_running():
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            if not messagebox.askyesno(
                self._state.t("mat.api_missing_t"),
                self._state.t("mat.m_no_api_key")
            ):
                return
            self._log_line("⚠ ANTHROPIC_API_KEY nicht gesetzt — Scan ohne Transkription.")

        cmd = [sys.executable, "-u", "-m", "ancestry.tools.scan_matricula_kirchspiel",
               "--parish", parish_id]
        bt = self._booktype_var.get()
        if bt and bt != "(alle)":
            cmd += ["--book-type", bt]

        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        self._stop_requested = False
        try:
            self._proc = subprocess.Popen(
                cmd, cwd=repo_root,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1)
        except Exception as e:
            messagebox.showerror("Matricula", f"Start fehlgeschlagen: {e}")
            self._proc = None
            return

        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._set_status(f"Matricula-Scan läuft: {parish_id}")
        self._log_line(f"▶ {' '.join(cmd)}")
        threading.Thread(target=self._pump_output, daemon=True,
                         name="matricula-scan").start()

    def _pump_output(self):
        proc = self._proc
        try:
            for line in proc.stdout:
                self._log_queue.put(line.rstrip("\n"))
        except Exception:
            pass
        rc = proc.wait()
        self._log_queue.put(f"__EXIT__{rc}")

    def _stop_scan(self):
        self._stop_requested = True
        if self.is_running():
            self._proc.terminate()
            self._log_line("⏹ Scan wird beendet … (Fortschritt bleibt gespeichert, "
                           "Wiederaufnahme jederzeit möglich)")

    def _on_scan_exit(self, rc: int):
        self._proc = None
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self.refresh_parishes()
        if rc == 0 and not self._stop_requested:
            self._set_status("Matricula-Scan abgeschlossen.")
            if self._auto_ner_var.get():
                self.after(800, self._extract_ner)
            if self._autonext_var.get():
                nxt = [v for v in self._parish_combo["values"]]
                if nxt:
                    self._parish_var.set(nxt[0])
                    self._log_line(f"→ automatisch weiter mit: {nxt[0]}")
                    self.after(2000, self._start_scan)
                else:
                    self._log_line("✓ Alle Pfarreien fertig.")
        else:
            self._set_status(f"Matricula-Scan beendet (Code {rc}).")

    def _show_ner_search(self):
        try:
            from ancestry.gui.analysis.ner_search import show_ner_search
            show_ner_search(self.winfo_toplevel(), self._state.db)
        except Exception as exc:
            messagebox.showerror("NER-Suche", f"Fehler beim Öffnen der NER-Suche:\n{exc}",
                                 parent=self)

    def _extract_ner(self):
        if self.is_running():
            messagebox.showinfo("NER", "Bitte warte bis der Scan abgeschlossen ist.")
            return
        self._ner_btn.configure(state="disabled")
        self._log_line("▶ NER-Extraktion gestartet …")

        def _run():
            try:
                from ancestry.tools.extract_matrikula_ner import extract_ner
                result = extract_ner()
                self._log_queue.put(
                    f"NER fertig: {result.get('persons', 0)} Personen aus "
                    f"{result.get('entries', 0)} Einträgen "
                    f"({result.get('skipped', 0)} übersprungen)")
            except Exception as exc:
                self._log_queue.put(f"NER-Fehler: {exc}")
            self._log_queue.put("__NER_DONE__")

        threading.Thread(target=_run, daemon=True, name="matricula-ner").start()

    def _poll_log(self):
        try:
            while True:
                line = self._log_queue.get_nowait()
                if line.startswith("__EXIT__"):
                    self._on_scan_exit(int(line[8:] or 0))
                elif line == "__NER_DONE__":
                    self._ner_btn.configure(state="normal")
                else:
                    self._log_line(line)
        except queue.Empty:
            pass
        self.after(250, self._poll_log)

    def _log_line(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        # Log begrenzen, damit lange Scans den Speicher nicht fluten
        if int(self._log.index("end-1c").split(".")[0]) > 2000:
            self._log.delete("1.0", "500.0")
        self._log.configure(state="disabled")
