# -*- coding: utf-8 -*-
"""
main.py – Ahnen-Analyse-Framework
GUI-Einstiegspunkt (tkinter, Dark Theme, Task-Registry, Threading).
Architektur nach ARCHITECTURE.md (ABE Tool-Framework).
"""

import argparse
import importlib
import inspect
import os
import sys
import threading
import time

# ── Config laden (Overrides vor allem anderen) ─────────────────────────────────
from config import apply_overrides
apply_overrides()
import config as cfg

# ── Logger initialisieren ──────────────────────────────────────────────────────
from lib.logger import setup_logging
logger = setup_logging(cfg.FILES.get("log_file"), log_level="INFO")

# ── Task-Registry ──────────────────────────────────────────────────────────────

TASKS = [
    # ── Vorbereitung ───────────────────────────────────────────────────────────
    {
        "id":      "load_gedcom",
        "name":    "GEDCOM laden",
        "desc":    "Liest GEDCOM (.ged) oder Family Tree Maker (.ftm) – Pflicht.",
        "fn":      "tasks._runner:load_gedcom",
        "default": True,
        "group":   "Vorbereitung",
    },
    {
        "id":      "load_cache",
        "name":    "State-Cache laden (Inkrementell)",
        "desc":    "Lädt zwischengespeicherten _state — übersprigt alle Analysen, wenn GEDCOM unverändert.",
        "fn":      "tasks._runner:load_state_cache",
        "default": False,
        "group":   "Vorbereitung",
    },
    {
        "id":      "save_cache",
        "name":    "State-Cache speichern",
        "desc":    "Persistiert den aktuellen _state nach ~/.ahnen-cache.pkl.",
        "fn":      "tasks._runner:save_state_cache",
        "default": False,
        "group":   "Export",
    },
    # ── Hauptanalysen ──────────────────────────────────────────────────────────
    {
        "id":      "cousins",
        "name":    "Verwandtschafts-/Cousin-Analyse",
        "desc":    "Berechnet Beziehungen aller Personen zur Root-Person.",
        "fn":      "tasks._runner:run_cousins",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "endogamy",
        "name":    "Endogamie & Top-Ahnen",
        "desc":    "Endogamie-Score pro Ort, Ahnen ohne eigene Eltern.",
        "fn":      "tasks._runner:run_endogamy",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "migration",
        "name":    "Migrationsrouten (Detail + Compressed + Wellen + Korrelation)",
        "desc":    "Vollständige Migrationsanalyse inkl. Emigrationsjahre.",
        "fn":      "tasks._runner:run_migration",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "military",
        "name":    "Militäranalyse",
        "desc":    "Erkennt ✠ ★ ⚔-Symbole, Kriege, Einheiten, Dienstgrade.",
        "fn":      "tasks._runner:run_military",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "demographics",
        "name":    "Demografische Statistiken",
        "desc":    "Lebenserwartung, Heiratsalter, Kindersterblichkeit nach Epoche.",
        "fn":      "tasks._runner:run_demographics",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "surnames",
        "name":    "Familiennamen & Geburtsländer",
        "desc":    "Häufigkeits- und Länderanalyse.",
        "fn":      "tasks._runner:run_surnames_and_countries",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "genetics",
        "name":    "Genetik (Inzucht + Pedigree Collapse)",
        "desc":    "Wright's F Inzuchtkoeffizient und Stammbaum-Implosion.",
        "fn":      "tasks._runner:run_genetics",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "history",
        "name":    "Historischer Kontext & Überlebenszeitanalyse",
        "desc":    "19 Ereignisse 1618–1973, Kaplan-Meier-Kohorten.",
        "fn":      "tasks._runner:run_history",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "names",
        "name":    "Namensmorphologie (Kölner Phonetik)",
        "desc":    "Schreibvarianten automatisch gruppiert.",
        "fn":      "tasks._runner:run_names",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "data_quality",
        "name":    "Datenvollständigkeits-Score",
        "desc":    "0–100 Punkte pro Person, Nachname, Epoche.",
        "fn":      "tasks._runner:run_data_quality",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "network",
        "name":    "Familiennetzwerkanalyse",
        "desc":    "Degree Centrality, Betweenness, Brückenpersonen.",
        "fn":      "tasks._runner:run_network",
        "default": False,
        "group":   "Extras",
    },
    {
        "id":      "osnabrueck",
        "name":    "Osnabrück-Region Spezialanalyse",
        "desc":    "Wallenhorst, GMH, Hagen a.T.W., Osnabrück u.a.",
        "fn":      "tasks._runner:run_osnabrueck",
        "default": True,
        "group":   "Extras",
    },
    # ── Neue Analysen ──────────────────────────────────────────────────────────
    {
        "id":      "anomalies",
        "name":    "Anomalien & Doubletten & Inseln",
        "desc":    "Implausible Daten, potenzielle Duplikate, unverbundene Personen.",
        "fn":      "tasks._runner:run_anomalies",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "dna_cm",
        "name":    "DNA-cM-Schätzung",
        "desc":    "Erwartete gemeinsame cM pro Verwandten (aus Kinship-Koeffizient).",
        "fn":      "tasks._runner:run_dna_cm",
        "default": False,
        "group":   "Analysen",
    },
    {
        "id":      "sibling_namedrift",
        "name":    "Geschwister-Statistiken & Namensdrift",
        "desc":    "Geburtsabstände in Familien + Vor-/Namenstrends über Zeit.",
        "fn":      "tasks._runner:run_sibling_and_namedrift",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "seasonality",
        "name":    "Saisonalität (Monatsverteilung)",
        "desc":    "Geburts-/Heirats-/Sterbe-/Empfängnis-Monate pro Epoche.",
        "fn":      "tasks._runner:run_seasonality",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "snapshot",
        "name":    "Stichjahr-Snapshot + Generationen-Overlap",
        "desc":    "Wer lebte zu Stichjahren / wie viele Generationen parallel.",
        "fn":      "tasks._runner:run_snapshot",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "spatial",
        "name":    "Räumliche Lebensgeschichte",
        "desc":    "Heirats-Migration, Lebens-Triangulation, Sesshaftigkeit, Nachname×Region.",
        "fn":      "tasks._runner:run_spatial",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "family_structure",
        "name":    "Erweiterte Familienstruktur",
        "desc":    "Mehrfachehen, Altersdifferenz, Reproduktivspanne, Kinderlosigkeit, Zwillinge.",
        "fn":      "tasks._runner:run_family_structure",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "lineage",
        "name":    "Linien-Analysen (Y, Mt, Quartile, Aussterben)",
        "desc":    "Paternale/maternale Linie, 4-Quartile-Vergleich, Verzweigung, Aussterben.",
        "fn":      "tasks._runner:run_lineage",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "naming_sociology",
        "name":    "Namens-Soziologie (Patronyme, Junioren)",
        "desc":    "Patronym-Erkennung, Junior-Detektor, Familien-Vornamen-Pool.",
        "fn":      "tasks._runner:run_naming_sociology",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "imputation",
        "name":    "Daten-Imputation (fehlende Daten)",
        "desc":    "Schätzt fehlende Geburtsdaten aus Eltern/Kindern/Ehepartner/Geschwistern.",
        "fn":      "tasks._runner:run_imputation",
        "default": False,
        "group":   "Analysen",
    },
    {
        "id":      "cohort_extensions",
        "name":    "Krisen-Kohorten & Eltern-Verlust",
        "desc":    "Lebenslauf von Kriegs/Hungerjahrgängen + Alter beim Tod der Eltern.",
        "fn":      "tasks._runner:run_cohort_extensions",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "research_helpers",
        "name":    "Forschungs-Helfer (Brickwalls, Vorschläge, Quellen)",
        "desc":    "Personen-Recherche-Ziele, automat. Forschungs-Vorschläge, SOUR/OBJE-Inventar.",
        "fn":      "tasks._runner:run_research_helpers",
        "default": True,
        "group":   "Analysen",
    },
    {
        "id":      "onomastics_endogamy",
        "name":    "Onomastik & Endogamie-Bigraph",
        "desc":    "Religiöse/regionale Namensmuster + Surname×Surname-Heirats-Netz.",
        "fn":      "tasks._runner:run_onomastics_and_endogamy_net",
        "default": True,
        "group":   "Analysen",
    },
    # ── Export ─────────────────────────────────────────────────────────────────
    {
        "id":      "export_excel",
        "name":    "Excel-Export",
        "desc":    f"Schreibt alle Sheets nach {cfg.FILES['output_xlsx']}.",
        "fn":      "tasks._runner:run_export_excel",
        "default": True,
        "group":   "Export",
    },
    {
        "id":      "export_json",
        "name":    "JSON-Export",
        "desc":    f"Speichert Metadaten nach {cfg.FILES['output_json']}.",
        "fn":      "tasks._runner:run_export_json",
        "default": True,
        "group":   "Export",
    },
    {
        "id":      "export_html",
        "name":    "HTML-Übersicht",
        "desc":    f"Selbsterklärende Übersicht nach {cfg.FILES['interactive_html']}.",
        "fn":      "tasks._runner:run_export_html",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_timeline",
        "name":    "HTML-Timeline",
        "desc":    f"Chronologische Ereignis-Zeitlinie nach {cfg.FILES['timeline_html']}.",
        "fn":      "tasks._runner:run_export_timeline",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_graphml",
        "name":    "GraphML-Export",
        "desc":    f"Netzwerk für Gephi/yEd nach {cfg.FILES['output_graphml']}.",
        "fn":      "tasks._runner:run_export_graphml",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_fanchart",
        "name":    "Fan-Chart SVG",
        "desc":    "Radialer Ahnenfächer (Generationen 1–7) als SVG.",
        "fn":      "tasks._runner:run_export_fanchart",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_dashboard",
        "name":    "HTML-Dashboard mit Charts",
        "desc":    "Interaktives Single-File-Dashboard (Chart.js, Tabs).",
        "fn":      "tasks._runner:run_export_dashboard",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_heatmap",
        "name":    "Geburts-Heatmap (Leaflet)",
        "desc":    "Welt-Karte der Geburtsorte nach Land + Jahrhundert.",
        "fn":      "tasks._runner:run_export_heatmap",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_descendants",
        "name":    "Subtree: Nachfahren der Root als GEDCOM",
        "desc":    "Schreibt nur Nachfahren-Stammbaum als eigene .ged-Datei.",
        "fn":      "tasks._runner:run_export_subtree_descendants",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_ancestors",
        "name":    "Subtree: Vorfahren der Root als GEDCOM",
        "desc":    "Schreibt nur Vorfahren-Stammbaum als eigene .ged-Datei.",
        "fn":      "tasks._runner:run_export_subtree_ancestors",
        "default": False,
        "group":   "Export",
    },
    {
        "id":      "export_sankey",
        "name":    "Migrations-Sankey (HTML)",
        "desc":    "Migrationsflüsse als SVG-Sankey-Diagramm.",
        "fn":      "tasks._runner:run_export_sankey",
        "default": False,
        "group":   "Export",
    },
]

GROUP_ORDER = {"Vorbereitung": 0, "Analysen": 1, "Extras": 2, "Export": 3}


# ── Task-Dispatch ──────────────────────────────────────────────────────────────

def _call_task(fn_spec: str, progress_cb, stop_event=None):
    module_path, func_name = fn_spec.rsplit(":", 1)
    mod  = importlib.import_module(module_path)
    fn   = getattr(mod, func_name)
    sig  = inspect.signature(fn)
    kwargs = {"progress_cb": progress_cb}
    if "stop_event" in sig.parameters and stop_event is not None:
        kwargs["stop_event"] = stop_event
    fn(**kwargs)


# ── App ────────────────────────────────────────────────────────────────────────
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk


class AhnenApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Ahnen-Analyse v9.0")
        self.geometry("1100x720")
        self.configure(bg=cfg.BG)
        self._running = False
        self._stop_event = threading.Event()
        self._task_vars: dict[str, tk.BooleanVar] = {}
        self._build_ui()

    # ── UI-Aufbau ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=cfg.BG2, pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🧬 Ahnen-Analyse v9.0", bg=cfg.BG2, fg=cfg.ACCENT,
                 font=cfg.FONT_HEAD).pack(side="left", padx=12)
        self._status_lbl = tk.Label(hdr, text="Bereit", bg=cfg.BG2, fg=cfg.FG_DIM,
                                     font=cfg.FONT_MAIN)
        self._status_lbl.pack(side="right", padx=12)

        # Hauptbereich
        main = tk.Frame(self, bg=cfg.BG)
        main.pack(fill="both", expand=True)

        # Linke Spalte
        left = tk.Frame(main, bg=cfg.BG2, width=260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        canvas = tk.Canvas(left, bg=cfg.BG2, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=cfg.BG2)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_resize(e):
            canvas.itemconfig(win_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        def _scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        # Mausrad nur binden, wenn der Cursor über der Task-Liste ist —
        # bind_all würde sonst das Scrollen im Log-Widget kapern.
        inner.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _scroll))
        inner.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

        self._build_task_list(inner)

        # Schaltflächen
        btn_frame = tk.Frame(left, bg=cfg.BG2, pady=6)
        btn_frame.pack(fill="x", side="bottom")
        for text, cmd in [("Alle", self._sel_all),
                           ("Keine", self._sel_none),
                           ("Standard", self._sel_default)]:
            tk.Button(btn_frame, text=text, bg=cfg.BG3, fg=cfg.FG,
                      font=cfg.FONT_MAIN, relief="flat",
                      command=cmd).pack(side="left", padx=4, pady=4)

        # Rechte Seite: Pfad + Log + Fortschritt
        right = tk.Frame(main, bg=cfg.BG)
        right.pack(side="left", fill="both", expand=True)

        path_frame = tk.Frame(right, bg=cfg.BG2, pady=4)
        path_frame.pack(fill="x")
        tk.Label(path_frame, text="Stammbaumdatei:", bg=cfg.BG2, fg=cfg.FG_DIM,
                 font=cfg.FONT_MONO).pack(side="left", padx=8)
        self._path_var = tk.StringVar(value=cfg.DEFAULT_CONFIG["gedfile"])
        tk.Entry(path_frame, textvariable=self._path_var, bg=cfg.BG3, fg=cfg.FG,
                 font=cfg.FONT_MONO, relief="flat", width=48).pack(
            side="left", padx=4)
        tk.Button(path_frame, text="Durchsuchen…", bg=cfg.BG3, fg=cfg.FG,
                  font=cfg.FONT_MAIN, relief="flat",
                  command=self._browse_gedcom).pack(side="left", padx=4)

        # Zuletzt geöffnete Dateien + Ancestry-Vorschlag
        recent_frame = tk.Frame(right, bg=cfg.BG2, pady=2)
        recent_frame.pack(fill="x")
        tk.Label(recent_frame, text="Zuletzt:", bg=cfg.BG2, fg=cfg.FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=8)
        self._recent_var = tk.StringVar(value="")
        self._recent_menu = ttk.Combobox(
            recent_frame, textvariable=self._recent_var,
            state="readonly", width=55, font=("Segoe UI", 8))
        self._recent_menu.pack(side="left", padx=4)
        self._recent_menu.bind("<<ComboboxSelected>>", self._on_recent_select)
        self._refresh_recent()
        # Ancestry-Export im Download-Ordner suchen und vorschlagen
        self.after(600, self._suggest_ancestry_export)

        # Root-/Exclude-ID
        ids_frame = tk.Frame(right, bg=cfg.BG2, pady=4)
        ids_frame.pack(fill="x")
        tk.Label(ids_frame, text="Root-ID:", bg=cfg.BG2, fg=cfg.FG_DIM,
                 font=cfg.FONT_MONO).pack(side="left", padx=8)
        self._root_id_var = tk.StringVar(value=cfg.DEFAULT_CONFIG["root_id"])
        tk.Entry(ids_frame, textvariable=self._root_id_var, bg=cfg.BG3,
                 fg=cfg.FG, font=cfg.FONT_MONO, relief="flat",
                 width=12).pack(side="left", padx=4)
        tk.Label(ids_frame, text="Exclude-ID:", bg=cfg.BG2, fg=cfg.FG_DIM,
                 font=cfg.FONT_MONO).pack(side="left", padx=(16, 8))
        self._excl_id_var = tk.StringVar(value=cfg.DEFAULT_CONFIG["exclude_id"])
        tk.Entry(ids_frame, textvariable=self._excl_id_var, bg=cfg.BG3,
                 fg=cfg.FG, font=cfg.FONT_MONO, relief="flat",
                 width=12).pack(side="left", padx=4)

        self._log = scrolledtext.ScrolledText(
            right, bg="#13131f", fg=cfg.FG, font=cfg.FONT_MONO,
            state="disabled", relief="flat")
        self._log.pack(fill="both", expand=True, padx=4, pady=4)
        for tag, color in [("ok", cfg.GREEN), ("err", cfg.RED),
                             ("warn", cfg.YELLOW), ("info", cfg.ORANGE),
                             ("dim", cfg.FG_DIM)]:
            self._log.tag_configure(tag, foreground=color)

        # Fortschritt
        prog_frame = tk.Frame(right, bg=cfg.BG, pady=2)
        prog_frame.pack(fill="x")
        self._prog_lbl = tk.Label(prog_frame, text="", bg=cfg.BG,
                                   fg=cfg.FG_DIM, font=cfg.FONT_MONO)
        self._prog_lbl.pack(side="left", padx=8)
        self._pbar = ttk.Progressbar(right, mode="determinate",
                                      style="Accent.Horizontal.TProgressbar")
        self._pbar.pack(fill="x", padx=8, pady=2)

        # Footer
        footer = tk.Frame(self, bg=cfg.BG2, pady=6)
        footer.pack(fill="x", side="bottom")
        self._btn_start = tk.Button(
            footer, text="▶ Starten", bg=cfg.ACCENT, fg="#fff",
            font=cfg.FONT_HEAD, relief="flat", padx=16,
            command=self._start)
        self._btn_start.pack(side="left", padx=8)
        self._btn_stop = tk.Button(
            footer, text="■ Abbrechen", bg=cfg.RED, fg="#fff",
            font=cfg.FONT_HEAD, relief="flat", padx=16,
            command=self._stop, state="disabled")
        self._btn_stop.pack(side="left", padx=4)
        tk.Button(footer, text="Log löschen", bg=cfg.BG3, fg=cfg.FG,
                  font=cfg.FONT_MAIN, relief="flat",
                  command=self._clear_log).pack(side="right", padx=8)

    def _build_task_list(self, parent):
        grouped: dict = {}
        for task in TASKS:
            grouped.setdefault(task["group"], []).append(task)
        for group in sorted(grouped, key=lambda g: GROUP_ORDER.get(g, 9)):
            tk.Label(parent, text=group.upper(), bg=cfg.BG2,
                     fg=cfg.ACCENT, font=cfg.FONT_HEAD,
                     anchor="w").pack(fill="x", padx=8, pady=(10, 2))
            for task in grouped[group]:
                var = tk.BooleanVar(value=task["default"])
                self._task_vars[task["id"]] = var
                cb = tk.Checkbutton(parent, text=task["name"], variable=var,
                                    bg=cfg.BG2, fg=cfg.FG, selectcolor=cfg.BG3,
                                    activebackground=cfg.BG2,
                                    font=cfg.FONT_MAIN, anchor="w")
                cb.pack(fill="x", padx=8)
                tk.Label(parent, text=f"  {task['desc']}", bg=cfg.BG2,
                         fg=cfg.FG_DIM, font=("Segoe UI", 8),
                         anchor="w", wraplength=220).pack(fill="x", padx=16)

    # ── Selektion ──────────────────────────────────────────────────────────────

    # ── Datei-Auswahl ──────────────────────────────────────────────────────────

    def _refresh_recent(self):
        recent = cfg.get_recent_files()
        self._recent_menu["values"] = recent
        if recent and not self._recent_var.get():
            self._recent_var.set("")

    def _on_recent_select(self, _event=None):
        val = self._recent_var.get()
        if val:
            self._path_var.set(val)
            self._recent_var.set("")

    def _suggest_ancestry_export(self):
        """Sucht im Download-Ordner nach aktuellen Ancestry-GEDCOM-Exporten."""
        import glob
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(downloads):
            return
        now = time.time()
        candidates = []
        for p in glob.glob(os.path.join(downloads, "*.ged")):
            try:
                age_days = (now - os.path.getmtime(p)) / 86400
                if age_days > 7:
                    continue
                # Ancestry-Header prüfen (erste 256 Bytes)
                with open(p, "rb") as f:
                    head = f.read(256).decode("utf-8-sig", errors="ignore")
                if "ancestry" in head.lower() or "SOUR Ancestry" in head:
                    candidates.append((age_days, p))
            except OSError:
                continue
        if not candidates:
            return
        candidates.sort()
        newest = candidates[0][1]
        current = self._path_var.get()
        if current and os.path.exists(current):
            return  # Bereits eine gültige Datei gesetzt
        self._path_var.set(newest)
        self._append_log(
            f"Ancestry-Export gefunden: {os.path.basename(newest)} "
            f"(letzte {candidates[0][0]:.1f} Tage) → automatisch gesetzt.",
            tag="info")

    def _browse_gedcom(self):
        initial = self._path_var.get() or cfg.DEFAULT_CONFIG.get("gedfile", "")
        initial_dir = os.path.dirname(initial) if initial else ""
        path = filedialog.askopenfilename(
            title="Stammbaumdatei wählen",
            initialdir=initial_dir or None,
            filetypes=[
                ("Alle unterstützten Formate",
                 "*.ged *.GED *.ftm *.FTM *.ftmb *.FTMB"),
                ("GEDCOM-Dateien", "*.ged *.GED"),
                ("Family Tree Maker", "*.ftm *.ftmb"),
                ("Alle Dateien", "*.*"),
            ])
        if path:
            self._path_var.set(path)
            self._refresh_recent()

    def _sel_all(self):
        for v in self._task_vars.values(): v.set(True)

    def _sel_none(self):
        for v in self._task_vars.values(): v.set(False)

    def _sel_default(self):
        for task in TASKS:
            self._task_vars[task["id"]].set(task["default"])

    # ── Log-Ausgabe ────────────────────────────────────────────────────────────

    def _append_log(self, msg: str, tag: str = ""):
        def _do():
            self._log.configure(state="normal")
            ts = time.strftime("%H:%M:%S")
            self._log.insert("end", f"[{ts}] {msg}\n", tag or "")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _set_status(self, text: str):
        self.after(0, lambda: self._status_lbl.configure(text=text))

    # ── Start / Stop ───────────────────────────────────────────────────────────

    def _start(self):
        selected = [t for t in TASKS
                    if self._task_vars.get(t["id"], tk.BooleanVar()).get()]
        if not selected:
            self._append_log("Kein Task ausgewählt.", tag="warn")
            return
        selected.sort(key=lambda t: (GROUP_ORDER.get(t.get("group", ""), 9),
                                     t["id"]))
        # GUI-Werte in Config einpflegen
        gedfile = self._path_var.get().strip()
        root_id = self._root_id_var.get().strip() or cfg.DEFAULT_CONFIG["root_id"]
        excl_id = self._excl_id_var.get().strip() or cfg.DEFAULT_CONFIG["exclude_id"]
        cfg.DEFAULT_CONFIG["gedfile"]    = gedfile
        cfg.FILES["gedfile"]              = gedfile
        cfg.DEFAULT_CONFIG["root_id"]    = root_id
        cfg.DEFAULT_CONFIG["exclude_id"] = excl_id
        cfg.ROOT_ID    = root_id
        cfg.EXCLUDE_ID = excl_id
        # Persistieren + Recent-Files-Liste aktualisieren
        cfg.save_overrides({
            "gedfile":    gedfile,
            "root_id":    root_id,
            "exclude_id": excl_id,
        })
        self.after(0, self._refresh_recent)
        self._running = True
        self._stop_event.clear()
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal", text="■ Abbrechen")
        self._pbar.configure(mode="determinate", maximum=len(selected), value=0)

        thread = threading.Thread(target=self._worker, args=(selected,), daemon=True)
        thread.start()

    # ── Worker ─────────────────────────────────────────────────────────────────
    def _worker(self, tasks):
        from tasks._runner import AbortedError
        had_errors = False
        aborted = False
        total = len(tasks)
        for i, task in enumerate(tasks):
            if not self._running:
                break
            self._append_log(f"── {task['name']} …", tag="info")
            self._set_status(f"[{i+1}/{total}] {task['name']}")
            try:
                def cb(msg, tag=""):
                    self._append_log(msg, tag=tag)
                _call_task(task["fn"], progress_cb=cb,
                           stop_event=self._stop_event)
            except AbortedError as exc:
                self._append_log(str(exc), tag="warn")
                aborted = True
                break
            except Exception as exc:
                self._append_log(f"FEHLER in '{task['name']}': {exc}", tag="err")
                had_errors = True
            self.after(0, lambda v=i + 1: self._pbar.configure(value=v))
        if aborted or not self._running:
            self._append_log("Abgebrochen.", tag="warn")
        self.after(0, self._finish, had_errors)

    def _stop(self):
        self._running = False
        self._stop_event.set()
        # Sofortiges Feedback, ohne auf den nächsten is_aborted()-Check zu warten.
        self._btn_stop.configure(state="disabled", text="… stoppt")
        self._set_status("Abbrechen …")

    def _finish(self, had_errors: bool):
        self._pbar.configure(value=0)
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled", text="■ Abbrechen")
        tag = "warn" if had_errors else "ok"
        msg = "Abgeschlossen mit Warnungen." if had_errors else "Alle Tasks erfolgreich."
        self._append_log(msg, tag=tag)
        self._set_status(msg)


# ── CLI-Modus ──────────────────────────────────────────────────────────────────

def _cli_main(argv: list[str] | None = None) -> int | None:
    """Headless-Batch-Modus. Gibt einen Exit-Code zurück oder None, falls
    die GUI gestartet werden soll."""
    parser = argparse.ArgumentParser(
        prog="gedcom-analyzer",
        description="GEDCOM-Analyse-Framework (GUI oder Headless)")
    parser.add_argument("--batch", action="store_true",
                        help="GUI überspringen und Tasks in der Konsole ausführen")
    parser.add_argument("--tasks", default="",
                        help="Komma-getrennte Task-IDs (leer = alle Default-Tasks)")
    parser.add_argument("--gedfile", help="Pfad zur GEDCOM-Datei (override config)")
    parser.add_argument("--root-id", help="Root-Person-ID (override config)")
    parser.add_argument("--exclude-id", help="Exclude-ID (override config)")
    parser.add_argument("--list-tasks", action="store_true",
                        help="Verfügbare Tasks ausgeben und beenden")
    # Interaktive Sub-Tools (eigene Befehle, kein Task-Run nötig)
    parser.add_argument("--mrca", nargs=2, metavar=("ID_A", "ID_B"),
                        help="Most-Recent-Common-Ancestor zweier Personen finden")
    parser.add_argument("--merge", nargs=2, metavar=("FILE_A", "FILE_B"),
                        help="Zwei GEDCOM-Dateien zusammenführen")
    parser.add_argument("--merge-out", default="merged.ged",
                        help="Output-Pfad für --merge (default: merged.ged)")
    parser.add_argument("--predict-cm", type=float, metavar="CM",
                        help="DNA-cM-Wert in Verwandtschafts-Wahrscheinlichkeiten umrechnen")
    args = parser.parse_args(argv)

    # ── Eigenständige CLI-Sub-Tools ────────────────────────────────────────
    if args.predict_cm is not None:
        from tasks.dna_predict import predict_relationship_from_cm
        result = predict_relationship_from_cm(args.predict_cm)
        print(f"\nDNA-Vorhersage für {args.predict_cm:.0f} cM:")
        for label, prob in result:
            bar = "█" * int(prob * 30)
            print(f"  {label:35s} {prob*100:5.1f}%  {bar}")
        return 0

    if args.mrca:
        from tasks.mrca import mrca_cli
        ged = args.gedfile or cfg.DEFAULT_CONFIG["gedfile"]
        return mrca_cli(["--gedfile", ged,
                          "--id-a", args.mrca[0],
                          "--id-b", args.mrca[1]])

    if args.merge:
        from tasks.merge_trees import merge_gedcoms
        _, n_merged = merge_gedcoms(args.merge[0], args.merge[1], args.merge_out,
                                     progress_cb=lambda m, **k: print(m))
        print(f"\nMerge abgeschlossen: {args.merge_out} (Doubletten gemerged: {n_merged})")
        return 0

    if args.list_tasks:
        for t in TASKS:
            default = "*" if t["default"] else " "
            print(f"  {default} {t['id']:25s} [{t['group']:13s}] {t['name']}")
        print("\n* = Default-Task. Mit --tasks <id1,id2,…> einschränken.")
        return 0

    if not args.batch:
        return None

    # Konfig-Overrides aus CLI
    if args.gedfile:
        cfg.DEFAULT_CONFIG["gedfile"] = args.gedfile
        cfg.FILES["gedfile"] = args.gedfile
    if args.root_id:
        cfg.DEFAULT_CONFIG["root_id"] = args.root_id
        cfg.ROOT_ID = args.root_id
    if args.exclude_id:
        cfg.DEFAULT_CONFIG["exclude_id"] = args.exclude_id
        cfg.EXCLUDE_ID = args.exclude_id

    if args.tasks:
        wanted = {x.strip() for x in args.tasks.split(",") if x.strip()}
        unknown = wanted - {t["id"] for t in TASKS}
        if unknown:
            print(f"Unbekannte Task-ID(s): {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            return 2
        selected = [t for t in TASKS if t["id"] in wanted]
    else:
        selected = [t for t in TASKS if t["default"]]
    selected.sort(key=lambda t: (GROUP_ORDER.get(t.get("group", ""), 9),
                                  t["id"]))

    _PREFIX = {"ok": "[OK]  ", "err": "[ERR] ", "warn": "[WARN]"}

    def cb(msg, tag=""):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {_PREFIX.get(tag, '      ')}{msg}", flush=True)

    print(f"Starte {len(selected)} Task(s) im CLI-Modus")
    had_errors = False
    from tasks._runner import AbortedError
    for i, task in enumerate(selected):
        print(f"\n── [{i + 1}/{len(selected)}] {task['name']} ──", flush=True)
        try:
            _call_task(task["fn"], progress_cb=cb)
        except AbortedError as exc:
            print(f"[WARN] {exc}", file=sys.stderr)
            return 130
        except Exception as exc:
            print(f"[ERR] FEHLER in '{task['name']}': {exc}", file=sys.stderr)
            had_errors = True
    return 1 if had_errors else 0


# ── Entry-Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rc = _cli_main()
    if rc is not None:
        sys.exit(rc)
    # Sicherstellen, dass Verzeichnisse existieren
    for d in cfg.DIRS.values():
        os.makedirs(d, exist_ok=True)
    app = AhnenApp()
    app.mainloop()
