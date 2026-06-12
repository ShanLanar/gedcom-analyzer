"""Matricula-Tab: Kirchenbuch-Scans pro Pfarrei starten und überwachen.

Läuft als eigener Subprozess (scan_matricula_kirchspiel.py) und damit
parallel zu Ancestry-/MyHeritage-Downloads — Tageslimits der DNA-Portale
blockieren die Kirchenbuch-Erschließung nicht.

Pfarrei-Auswahl per Dropdown; fertig transkribierte Pfarreien sind in der
Übersicht ausgegraut und mit ✓ markiert. Optional wird nach Abschluss einer
Pfarrei automatisch die nächste offene gestartet (Warteschlangen-Prinzip).
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import COLORS
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
        self._build()
        self._poll_log()

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        t  = self._state.t
        lw = self._state.lang_widgets

        top = ttk.Frame(self); top.pack(fill="x", padx=14, pady=(10, 4))

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

        bar = ttk.Frame(self); bar.pack(fill="x", padx=14, pady=4)
        self._start_btn = ttk.Button(bar, text=t("mat.start"), command=self._start_scan)
        self._start_btn.pack(side="left")
        lw.append((self._start_btn, "mat.start"))
        self._stop_btn = ttk.Button(bar, text=t("mat.stop"),
                                    command=self._stop_scan, state="disabled")
        self._stop_btn.pack(side="left", padx=6)
        lw.append((self._stop_btn, "mat.stop"))
        _btn = ttk.Button(bar, text=t("mat.refresh"), command=self.refresh_parishes)
        _btn.pack(side="left", padx=6)
        lw.append((_btn, "mat.refresh"))

        self._autonext_var = tk.BooleanVar(value=False)
        _sv = tk.StringVar(value=t("mat.autonext"))
        cb = ttk.Checkbutton(bar, variable=self._autonext_var, textvariable=_sv)
        cb.pack(side="left", padx=(16, 0))
        lw.append((_sv, "mat.autonext"))

        # Pfarreien-Übersicht: fertig = ✓ + ausgegraut
        _sv = tk.StringVar(value=t("mat.overview"))
        ttk.Label(self, textvariable=_sv, style="Bold.TLabel").pack(
            anchor="w", padx=14, pady=(8, 2))
        lw.append((_sv, "mat.overview"))

        mid = ttk.Frame(self); mid.pack(fill="both", expand=True, padx=14, pady=(0, 4))
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
        self._log = tk.Text(self, height=10, wrap="word",
                            font=("Consolas", 9), state="disabled")
        self._log.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self.refresh_parishes()

    # ── Pfarrei-Status ────────────────────────────────────────────────────────

    def refresh_parishes(self):
        """Dropdown + Übersicht aus matricula_parishes.db neu laden."""
        parishes = mstat.get_parish_status()
        self._tv.delete(*self._tv.get_children())
        self._label_to_id.clear()

        if not parishes:
            self._parish_combo.configure(values=[])
            self._start_btn.configure(state="disabled")
            self._log_line(self._state.t("mat.no_db"))
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
            # Fertige Pfarreien nicht als "nächste" anbieten
            if p["status"] != mstat.STATUS_DONE:
                combo_values.append(label)

        self._parish_combo.configure(values=combo_values)
        if combo_values and not self._parish_var.get():
            # Teilweise gescannte zuerst vorschlagen (Wiederaufnahme)
            partial = [v for v in combo_values if v.startswith("◐")]
            self._parish_var.set(partial[0] if partial else combo_values[0])

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
            messagebox.showinfo("Matricula", "Bitte eine Pfarrei wählen.")
            return
        if self.is_running():
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            if not messagebox.askyesno(
                "API-Key fehlt",
                "ANTHROPIC_API_KEY ist nicht gesetzt.\n\n"
                "Ohne diesen Schlüssel kann Claude Vision die Kirchenbuch-Seiten nicht "
                "transkribieren — der Scan wird nach dem ersten Bild fehlschlagen.\n\n"
                "Trotzdem starten? (Sinnvoll nur bei --dry-run oder Re-Transkription "
                "von bereits vorhandenen Bildern.)"
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

    def _poll_log(self):
        try:
            while True:
                line = self._log_queue.get_nowait()
                if line.startswith("__EXIT__"):
                    self._on_scan_exit(int(line[8:] or 0))
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
