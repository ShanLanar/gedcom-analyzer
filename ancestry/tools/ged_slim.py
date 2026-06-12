"""
ged_slim.py – GEDCOM-Reduktionswerkzeug
========================================
Entfernt genealogisch weniger relevante Tags aus großen GEDCOM-Dateien
und behält alle strukturell wichtigen Daten für:
  - DNA-Analyse / Verwandtschaftsgrade
  - Migrationsanalyse (Orts- und Zeitdaten)
  - Netzwerkanalyse (Familienverknüpfungen)
  - Statistik, Lebensdaten, besondere Ereignisse

Standardmäßig entfernte Tags (konfigurierbar):
  SOUR-Verweise    → Quellenbelege (nicht die Quellenrecords selbst)
  MAP/LATI/LONG    → Koordinatenblöcke
  _LINK            → externe URL-Links
  SSN              → Sozialversicherungsnummern (Datenschutz)

Autor: ged_slim v1.0
Lizenz: frei verwendbar
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import re
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ---------------------------------------------------------------------------
# Konfiguration & Datenmodell
# ---------------------------------------------------------------------------

@dataclass
class SlimConfig:
    """Konfiguration für den Reduktionsprozess."""
    input_path: str = ""
    output_path: str = ""

    # Zu entfernende Level-1-Blöcke (innerhalb INDI/FAM)
    remove_l1_tags: set = field(default_factory=lambda: {"SSN"})

    # Zu entfernende Sub-Tags (in jedem Kontext, Level 2+)
    remove_sub_tags: set = field(default_factory=lambda: {
        "MAP", "LATI", "LONG",   # Koordinaten
        "_LINK",                  # externe Links
    })

    # SOUR-Verweise aus INDI/FAM entfernen (nicht die globalen SOUR-Records)
    remove_inline_sour: bool = True

    # SOUR-Verweise in Unterblöcken (NAME, RESI, BIRT, DEAT …) entfernen
    remove_sub_sour: bool = True

    # Globale SOUR-Records behalten (empfohlen: True)
    keep_global_sour: bool = True

    # Globale NOTE-Records behalten
    keep_global_note: bool = True

    # SSN entfernen (Datenschutz)
    remove_ssn: bool = True

    # Encoding-Handling
    input_encoding: str = "utf-8-sig"
    output_encoding: str = "utf-8"


@dataclass
class SlimStats:
    """Statistiken des Reduktionsprozesses."""
    lines_total: int = 0
    lines_written: int = 0
    lines_removed: int = 0
    indi_count: int = 0
    fam_count: int = 0
    sour_refs_removed: int = 0
    map_blocks_removed: int = 0
    link_removed: int = 0
    ssn_removed: int = 0
    sub_tag_removed: int = 0
    size_before_mb: float = 0.0
    size_after_mb: float = 0.0
    duration_sec: float = 0.0

    def reduction_pct(self) -> float:
        if self.lines_total == 0:
            return 0.0
        return 100.0 * self.lines_removed / self.lines_total

    def size_reduction_pct(self) -> float:
        if self.size_before_mb == 0:
            return 0.0
        return 100.0 * (1 - self.size_after_mb / self.size_before_mb)


# ---------------------------------------------------------------------------
# Kernlogik: GEDCOM-Parser / Reducer
# ---------------------------------------------------------------------------

class GedcomReducer:
    """
    Liest eine GEDCOM-Datei zeilenweise und schreibt eine reduzierte Version.
    Arbeitet streamingbasiert, ohne die gesamte Datei in den Speicher zu laden.
    """

    # Tags, die als "Koordinaten-Subbaum" gelten (unter PLAC oder frei)
    COORD_TAGS = {"MAP", "LATI", "LONG"}

    def __init__(self, config: SlimConfig, log_callback=None, progress_callback=None):
        self.cfg = config
        self.log = log_callback or (lambda msg: None)
        self.progress = progress_callback or (lambda pct: None)
        self.stats = SlimStats()
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self) -> SlimStats:
        """Hauptroutine. Gibt SlimStats zurück."""
        cfg = self.cfg
        t0 = time.time()

        in_path = Path(cfg.input_path)
        out_path = Path(cfg.output_path)

        self.stats.size_before_mb = in_path.stat().st_size / 1024 / 1024
        total_bytes = in_path.stat().st_size

        self.log(f"Eingabe:  {in_path.name}  ({self.stats.size_before_mb:.1f} MB)")
        self.log(f"Ausgabe:  {out_path}")
        self.log("Starte Reduktion …\n")

        bytes_read = 0
        last_pct = -1

        # Zustandsmaschine
        # current_record: 'INDI', 'FAM', 'SOUR', 'NOTE', 'OTHER'
        current_record = "OTHER"
        # skip_block_level: wenn gesetzt, alle Zeilen mit level >= skip_block_level überspringen
        skip_block_level: Optional[int] = None
        # Für MAP-Koordinaten-Erkennung: Level des PLAC-Tags (MAP folgt direkt danach)
        # skip gilt auch für koordinaten unter PLAC auf level n → überspringen level n+1 MAP-Block

        with open(in_path, "rb") as fin, \
             open(out_path, "w", encoding=cfg.output_encoding, newline="\r\n") as fout:

            for raw_line in fin:
                if self._cancel.is_set():
                    self.log("\n[ABGEBROCHEN]")
                    break

                bytes_read += len(raw_line)
                line = raw_line.decode(cfg.input_encoding, errors="replace").rstrip("\r\n")
                self.stats.lines_total += 1

                # Fortschritt
                pct = int(100 * bytes_read / total_bytes)
                if pct != last_pct:
                    self.progress(pct)
                    last_pct = pct

                # Parse Zeile
                m = re.match(r'^(\d+) (@\S+@ )?(\w+|_\w+)(.*)', line)
                if not m:
                    # Nicht-Standard-Zeile (z.B. BOM-Reste, Leerzeilen) → durchlassen
                    fout.write(line + "\r\n")
                    self.stats.lines_written += 1
                    continue

                level = int(m.group(1))
                xref = (m.group(2) or "").strip()
                tag = m.group(3)
                rest = m.group(4)

                # --- Level 0: neuer Record ---
                if level == 0:
                    skip_block_level = None
                    if tag == "INDI":
                        current_record = "INDI"
                        self.stats.indi_count += 1
                    elif tag == "FAM":
                        current_record = "FAM"
                        self.stats.fam_count += 1
                    elif tag == "SOUR":
                        current_record = "SOUR"
                    elif tag == "NOTE":
                        current_record = "NOTE"
                    else:
                        current_record = "OTHER"
                    self._write(fout, line)
                    continue

                # --- Innerhalb eines Blocks: prüfen ob wir im Skip-Modus ---
                if skip_block_level is not None:
                    if level >= skip_block_level:
                        # Diese Zeile gehört noch zum übersprungenen Block
                        self._skip(tag)
                        continue
                    else:
                        # Block beendet
                        skip_block_level = None

                # --- Filterregeln ---

                # Koordinaten (MAP, LATI, LONG) auf beliebigem Level
                if tag in self.COORD_TAGS:
                    skip_block_level = level + 1
                    self._skip(tag)
                    self.stats.map_blocks_removed += 1
                    continue

                # _LINK auf beliebigem Level
                if tag == "_LINK":
                    skip_block_level = level + 1
                    self._skip(tag)
                    self.stats.link_removed += 1
                    continue

                # SSN (Level 1, in INDI)
                if tag == "SSN" and cfg.remove_ssn and current_record == "INDI":
                    skip_block_level = level + 1
                    self._skip(tag)
                    self.stats.ssn_removed += 1
                    continue

                # Sonstige konfigurierte Level-1-Tags
                if level == 1 and tag in (cfg.remove_l1_tags - {"SSN"}) and \
                        current_record in ("INDI", "FAM"):
                    skip_block_level = level + 1
                    self._skip(tag)
                    self.stats.sub_tag_removed += 1
                    continue

                # SOUR-Verweise (Level 1) in INDI/FAM
                if tag == "SOUR" and level == 1 and cfg.remove_inline_sour and \
                        current_record in ("INDI", "FAM"):
                    # Nur Verweise (@S123@), nicht inline-Sour ohne Xref
                    if "@" in rest:
                        skip_block_level = level + 1
                        self._skip(tag)
                        self.stats.sour_refs_removed += 1
                        continue

                # SOUR-Verweise (Level 2+) in Unter-Tags von INDI/FAM
                if tag == "SOUR" and level >= 2 and cfg.remove_sub_sour and \
                        current_record in ("INDI", "FAM"):
                    if "@" in rest:
                        skip_block_level = level + 1
                        self._skip(tag)
                        self.stats.sour_refs_removed += 1
                        continue

                # Zeile schreiben
                self._write(fout, line)

        # Nachbearbeitung
        self.stats.lines_removed = self.stats.lines_total - self.stats.lines_written
        self.stats.size_after_mb = out_path.stat().st_size / 1024 / 1024
        self.stats.duration_sec = time.time() - t0

        self.log(self._format_summary())
        self.progress(100)
        return self.stats

    def _write(self, fout, line: str):
        fout.write(line + "\r\n")
        self.stats.lines_written += 1

    def _skip(self, tag: str):
        self.stats.lines_removed += 1

    def _format_summary(self) -> str:
        s = self.stats
        lines = [
            "─" * 50,
            "ERGEBNIS",
            "─" * 50,
            f"Personen (INDI):      {s.indi_count:>10,}",
            f"Familien (FAM):       {s.fam_count:>10,}",
            "",
            f"Zeilen gesamt:        {s.lines_total:>10,}",
            f"Zeilen behalten:      {s.lines_written:>10,}",
            f"Zeilen entfernt:      {s.lines_removed:>10,}  ({s.reduction_pct():.1f} %)",
            "",
            f"  davon SOUR-Verweise:{s.sour_refs_removed:>10,}",
            f"  davon MAP/LATI/LONG:{s.map_blocks_removed:>10,}",
            f"  davon _LINK:        {s.link_removed:>10,}",
            f"  davon SSN:          {s.ssn_removed:>10,}",
            f"  davon sonstige:     {s.sub_tag_removed:>10,}",
            "",
            f"Größe vorher:         {s.size_before_mb:>8.1f} MB",
            f"Größe nachher:        {s.size_after_mb:>8.1f} MB",
            f"Reduktion:            {s.size_reduction_pct():>8.1f} %",
            "",
            f"Dauer:                {s.duration_sec:>8.1f} s",
            "─" * 50,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class GedSlimApp(tk.Tk):
    """Hauptfenster der GED Slim Anwendung."""

    ACCENT = "#2563eb"
    BG = "#f8fafc"
    CARD = "#ffffff"
    TEXT = "#1e293b"
    MUTED = "#64748b"
    SUCCESS = "#16a34a"
    WARN = "#d97706"
    DANGER = "#dc2626"

    def __init__(self):
        super().__init__()
        self.title("GED Slim – GEDCOM Reduktionswerkzeug")
        self.geometry("860x720")
        self.minsize(700, 580)
        self.configure(bg=self.BG)

        self.config_obj = SlimConfig()
        self._reducer: Optional[GedcomReducer] = None
        self._thread: Optional[threading.Thread] = None

        self._build_ui()
        self._setup_logging()

    # --- UI-Aufbau ---

    def _build_ui(self):
        # Titel
        hdr = tk.Frame(self, bg=self.ACCENT, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="GED Slim", font=("Helvetica", 18, "bold"),
                 bg=self.ACCENT, fg="white").pack(side=tk.LEFT, padx=16)
        tk.Label(hdr, text="GEDCOM-Reduktion für genealogische Analyse",
                 font=("Helvetica", 10), bg=self.ACCENT, fg="#bfdbfe").pack(side=tk.LEFT)

        # Hauptbereich
        main = tk.Frame(self, bg=self.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        # Linke Spalte: Einstellungen
        left = tk.Frame(main, bg=self.BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 12))

        self._build_file_section(left)
        self._build_options_section(left)
        self._build_buttons(left)

        # Rechte Spalte: Log
        right = tk.Frame(main, bg=self.BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_log_section(right)

        # Fortschrittsleiste unten
        self._build_progress()

    def _card(self, parent, title: str) -> tuple[tk.Frame, tk.Frame]:
        """Erstellt eine Card mit Titel und gibt (outer, inner) zurück."""
        outer = tk.Frame(parent, bg=self.BG, pady=4)
        outer.pack(fill=tk.X)
        tk.Label(outer, text=title, font=("Helvetica", 9, "bold"),
                 bg=self.BG, fg=self.MUTED).pack(anchor=tk.W)
        inner = tk.Frame(outer, bg=self.CARD, relief=tk.FLAT,
                         bd=1, highlightthickness=1,
                         highlightbackground="#e2e8f0", padx=10, pady=8)
        inner.pack(fill=tk.X)
        return outer, inner

    def _build_file_section(self, parent):
        _, card = self._card(parent, "DATEIEN")

        # Eingabe
        tk.Label(card, text="Eingabe-GEDCOM:", bg=self.CARD,
                 fg=self.TEXT, font=("Helvetica", 9)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self._var_input = tk.StringVar()
        entry_in = tk.Entry(card, textvariable=self._var_input, width=34,
                            font=("Courier", 9), relief=tk.FLAT,
                            bg="#f1f5f9", fg=self.TEXT)
        entry_in.grid(row=1, column=0, sticky=tk.EW, pady=(0, 4))
        tk.Button(card, text="…", command=self._browse_input, width=3,
                  bg=self.ACCENT, fg="white", relief=tk.FLAT,
                  activebackground="#1d4ed8").grid(row=1, column=1, padx=(4, 0), pady=(0, 4))

        # Ausgabe
        tk.Label(card, text="Ausgabe-GEDCOM:", bg=self.CARD,
                 fg=self.TEXT, font=("Helvetica", 9)).grid(row=2, column=0, sticky=tk.W, pady=2)
        self._var_output = tk.StringVar()
        entry_out = tk.Entry(card, textvariable=self._var_output, width=34,
                             font=("Courier", 9), relief=tk.FLAT,
                             bg="#f1f5f9", fg=self.TEXT)
        entry_out.grid(row=3, column=0, sticky=tk.EW, pady=(0, 2))
        tk.Button(card, text="…", command=self._browse_output, width=3,
                  bg=self.ACCENT, fg="white", relief=tk.FLAT,
                  activebackground="#1d4ed8").grid(row=3, column=1, padx=(4, 0), pady=(0, 2))
        card.columnconfigure(0, weight=1)

    def _build_options_section(self, parent):
        _, card = self._card(parent, "FILTEROPTIONEN")

        self._opt_sour_inline = tk.BooleanVar(value=True)
        self._opt_sour_sub = tk.BooleanVar(value=True)
        self._opt_map = tk.BooleanVar(value=True)
        self._opt_link = tk.BooleanVar(value=True)
        self._opt_ssn = tk.BooleanVar(value=True)

        opts = [
            (self._opt_sour_inline, "SOUR-Verweise (Level 1) in INDI/FAM entfernen",
             "Quellenreferenzen direkt an Personen/Familien"),
            (self._opt_sour_sub,    "SOUR-Verweise in Unterblöcken entfernen",
             "Quellenrefs unter NAME, BIRT, RESI, DEAT …"),
            (self._opt_map,         "MAP / LATI / LONG entfernen",
             "GPS-Koordinaten (kein Verlust für Textanalyse)"),
            (self._opt_link,        "_LINK entfernen",
             "Externe URL-Links zu Ancestry, Matricula etc."),
            (self._opt_ssn,         "SSN entfernen (Datenschutz)",
             "Sozialversicherungsnummern"),
        ]

        for i, (var, label, hint) in enumerate(opts):
            row = tk.Frame(card, bg=self.CARD)
            row.pack(fill=tk.X, pady=1)
            cb = tk.Checkbutton(row, variable=var, bg=self.CARD,
                                activebackground=self.CARD,
                                text=label, font=("Helvetica", 9),
                                fg=self.TEXT, anchor=tk.W)
            cb.pack(side=tk.TOP, anchor=tk.W)
            tk.Label(row, text=f"  ↳ {hint}", font=("Helvetica", 8),
                     bg=self.CARD, fg=self.MUTED).pack(anchor=tk.W)

    def _build_buttons(self, parent):
        btn_frame = tk.Frame(parent, bg=self.BG, pady=8)
        btn_frame.pack(fill=tk.X)

        self._btn_start = tk.Button(btn_frame, text="▶  Reduktion starten",
                                    command=self._start, font=("Helvetica", 10, "bold"),
                                    bg=self.SUCCESS, fg="white", relief=tk.FLAT,
                                    activebackground="#15803d", pady=6, padx=12)
        self._btn_start.pack(side=tk.LEFT)

        self._btn_cancel = tk.Button(btn_frame, text="■  Abbrechen",
                                     command=self._cancel, font=("Helvetica", 10),
                                     bg=self.DANGER, fg="white", relief=tk.FLAT,
                                     activebackground="#b91c1c", pady=6, padx=12,
                                     state=tk.DISABLED)
        self._btn_cancel.pack(side=tk.LEFT, padx=(8, 0))

        tk.Button(btn_frame, text="Log leeren", command=self._clear_log,
                  font=("Helvetica", 9), bg="#e2e8f0", fg=self.TEXT,
                  relief=tk.FLAT, pady=6).pack(side=tk.RIGHT)

    def _build_log_section(self, parent):
        tk.Label(parent, text="LOG  &  STATISTIK", font=("Helvetica", 9, "bold"),
                 bg=self.BG, fg=self.MUTED).pack(anchor=tk.W)
        self._log_text = scrolledtext.ScrolledText(
            parent, font=("Courier", 8), bg="#0f172a", fg="#94a3b8",
            insertbackground="white", relief=tk.FLAT, state=tk.DISABLED,
            wrap=tk.WORD
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)
        # Tag-Farben für Log
        self._log_text.tag_config("info",    foreground="#94a3b8")
        self._log_text.tag_config("success", foreground="#4ade80")
        self._log_text.tag_config("warn",    foreground="#fbbf24")
        self._log_text.tag_config("error",   foreground="#f87171")
        self._log_text.tag_config("head",    foreground="#60a5fa")

    def _build_progress(self):
        pframe = tk.Frame(self, bg=self.BG, pady=4)
        pframe.pack(fill=tk.X, padx=16, pady=(0, 8))
        self._progress_var = tk.IntVar(value=0)
        self._progress_lbl = tk.Label(pframe, text="Bereit.", font=("Helvetica", 8),
                                      bg=self.BG, fg=self.MUTED, anchor=tk.W)
        self._progress_lbl.pack(fill=tk.X)
        self._progress_bar = ttk.Progressbar(pframe, variable=self._progress_var,
                                             maximum=100, length=400)
        self._progress_bar.pack(fill=tk.X)

    # --- Logging ---

    def _setup_logging(self):
        """Leitet Python-logging in das GUI-Textfeld."""
        class GuiHandler(logging.Handler):
            def __init__(self_, app):
                super().__init__()
                self_.app = app
            def emit(self_, record):
                msg = self_.format(record)
                self_.app._append_log(msg + "\n", "info")

        self._logger = logging.getLogger("ged_slim")
        self._logger.setLevel(logging.DEBUG)
        handler = GuiHandler(self)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s",
                                               datefmt="%H:%M:%S"))
        self._logger.addHandler(handler)

    def _append_log(self, msg: str, tag: str = "info"):
        """Thread-sicher in das Log-Widget schreiben."""
        def _do():
            self._log_text.configure(state=tk.NORMAL)
            # Einfärben nach Schlüsselwörtern
            t = tag
            ml = msg.lower()
            if "ergebnis" in ml or "reduktion" in ml or "fertig" in ml:
                t = "success"
            elif "fehler" in ml or "error" in ml:
                t = "error"
            elif "warnung" in ml or "warn" in ml:
                t = "warn"
            elif msg.startswith("─"):
                t = "head"
            self._log_text.insert(tk.END, msg, t)
            self._log_text.see(tk.END)
            self._log_text.configure(state=tk.DISABLED)
        self.after(0, _do)

    def _clear_log(self):
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    # --- Datei-Browser ---

    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="GEDCOM-Eingabedatei wählen",
            filetypes=[("GEDCOM", "*.ged *.gedcom"), ("Alle", "*.*")]
        )
        if path:
            self._var_input.set(path)
            # Ausgabepfad automatisch vorschlagen
            p = Path(path)
            self._var_output.set(str(p.parent / (p.stem + "_slim.ged")))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Ausgabedatei wählen",
            defaultextension=".ged",
            filetypes=[("GEDCOM", "*.ged"), ("Alle", "*.*")]
        )
        if path:
            self._var_output.set(path)

    # --- Steuerung ---

    def _start(self):
        inp = self._var_input.get().strip()
        out = self._var_output.get().strip()

        if not inp:
            messagebox.showerror("Fehler", "Bitte eine Eingabedatei wählen.")
            return
        if not Path(inp).is_file():
            messagebox.showerror("Fehler", f"Datei nicht gefunden:\n{inp}")
            return
        if not out:
            messagebox.showerror("Fehler", "Bitte eine Ausgabedatei angeben.")
            return
        if inp == out:
            messagebox.showerror("Fehler", "Eingabe und Ausgabe dürfen nicht gleich sein.")
            return

        # Config zusammenbauen
        cfg = SlimConfig(
            input_path=inp,
            output_path=out,
            remove_inline_sour=self._opt_sour_inline.get(),
            remove_sub_sour=self._opt_sour_sub.get(),
            remove_ssn=self._opt_ssn.get(),
            remove_sub_tags=set(),
        )
        if self._opt_map.get():
            cfg.remove_sub_tags |= {"MAP", "LATI", "LONG"}
        if self._opt_link.get():
            cfg.remove_sub_tags |= {"_LINK"}

        # UI-Zustand
        self._btn_start.configure(state=tk.DISABLED)
        self._btn_cancel.configure(state=tk.NORMAL)
        self._progress_var.set(0)
        self._set_status("Läuft …")

        # Reducer starten
        self._reducer = GedcomReducer(
            config=cfg,
            log_callback=lambda msg: self._append_log(msg + "\n", "info"),
            progress_callback=self._on_progress,
        )

        def worker():
            try:
                stats = self._reducer.run()
                self.after(0, lambda: self._on_done(stats))
            except Exception as exc:
                self._append_log(f"FEHLER: {exc}\n", "error")
                self.after(0, self._on_error)

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _cancel(self):
        if self._reducer:
            self._reducer.cancel()
        self._set_status("Abbrechen …")

    def _on_progress(self, pct: int):
        self.after(0, lambda: self._progress_var.set(pct))
        self.after(0, lambda: self._set_status(f"Verarbeite … {pct} %"))

    def _on_done(self, stats: SlimStats):
        self._btn_start.configure(state=tk.NORMAL)
        self._btn_cancel.configure(state=tk.DISABLED)
        self._progress_var.set(100)
        msg = (f"Fertig! {stats.size_before_mb:.1f} MB → {stats.size_after_mb:.1f} MB "
               f"(−{stats.size_reduction_pct():.0f} %)  in {stats.duration_sec:.0f} s")
        self._set_status(msg)
        messagebox.showinfo("GED Slim – Fertig", msg)

    def _on_error(self):
        self._btn_start.configure(state=tk.NORMAL)
        self._btn_cancel.configure(state=tk.DISABLED)
        self._set_status("Fehler aufgetreten – siehe Log.")

    def _set_status(self, text: str):
        self._progress_lbl.configure(text=text)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main():
    app = GedSlimApp()
    app.mainloop()


if __name__ == "__main__":
    main()
