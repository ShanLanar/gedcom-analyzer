"""ToolsTab – Tab „🔧 Werkzeuge" für das Ancestry-DNA-Tool.

Bündelt die eigenständigen CLI-Tools (Webtrees-Crawl, Matricula, MyHeritage,
Importe, GED Slim, Web-Viewer) mit Start-/Stop-Knöpfen und Live-Log direkt in
der Haupt-App, statt sie nur über die Kommandozeile erreichbar zu machen.

Bewusst ohne DB-Zugriffe beim Aufbau, damit der Tab den Programmstart nicht
verlangsamt – alle schweren Aktionen laufen als Subprozess im Hintergrund.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, scrolledtext, ttk

from ancestry.gui.state import AppState
from ancestry.gui.widgets.pipeline_view import DataSourcePipeline
from ancestry.gui.widgets.theme import register_lang
from ancestry.gui.widgets.tooltip import register_tooltip
from ancestry.gui.widgets.tutorial_guide import TutorialGuide
from ancestry.paths import ROOT

_WIKI_PATH = os.path.join(str(ROOT), "WIKI.md")

_TOOLS_DIR = os.path.join(str(ROOT), "ancestry", "tools")

_MAT_LAST_PARISH = os.path.join(_TOOLS_DIR, ".mat_last_parish")


def _tool(name: str) -> str:
    return os.path.join(_TOOLS_DIR, name)


def _utf8_env() -> dict:
    """Erzwingt UTF-8-stdout in Tool-Subprozessen.

    Viele Tools geben Emojis/Unicode aus; unter Windows ist die Konsole sonst
    cp1252 und der Prozess stirbt mit UnicodeEncodeError. PYTHONUTF8/-IOENCODING
    schalten den Kind-Prozess auf UTF-8."""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


class ToolsTab(ttk.Frame):
    """Werkzeuge-/Import-Tab des Ancestry-DNA-Tools."""

    def __init__(self, parent: tk.Widget, state: AppState):
        super().__init__(parent)
        self._state = state
        self._tool_procs: dict[str, subprocess.Popen | None] = {}
        self._build()

    def _build(self):
        f = self

        # ── Kopf / Kurzhilfe ──────────────────────────────────────────────
        head = ttk.Frame(f)
        head.pack(fill="x", padx=14, pady=(10, 4))
        register_lang(self._state, ttk.Label(head, text=self._state.t("tl.header"),
                  font=("Segoe UI", 13, "bold")), "tl.header").pack(side="left")
        ttk.Label(head, text="  Externe Sammel-/Import-Tools – laufen im "
                             "Hintergrund, fortsetzbar, jederzeit per ■ stoppbar.",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left", padx=(8, 0))
        _b = register_lang(self._state, ttk.Button(head, text=self._state.t("tl.b_guide"), command=self._open_wiki), "tl.b_guide")
        _b.pack(side="right")
        register_tooltip(_b, "tt.tl_guide", self._state)
        self._tutorial = TutorialGuide(self, self._state)
        _bt = ttk.Button(head, text="❓ Tutorial", command=self._open_tutorial)
        _bt.pack(side="right", padx=(0, 6))
        register_tooltip(_bt, "tt.tl_tutorial", self._state)

        # ── Anleitung / empfohlener Ablauf ────────────────────────────────
        guide = register_lang(self._state, ttk.LabelFrame(f, text=self._state.t("tl.guide_frame"), padding=8), "tl.guide_frame")
        guide.pack(fill="x", padx=14, pady=(2, 6))
        steps = (
            "① Start-Tab: GEDCOM + Wurzelperson wählen   "
            "② Login-Tab: Ancestry-Cookie laden\n"
            "③ Herunterladen: Matches + Ahnentafeln laden   "
            "④ Matches-Tab: „🌳 GEDCOM abgleichen\"\n"
            "⑤ Cluster-Tab: Cluster bilden + Seite zuweisen   "
            "⑥ Hier: weitere Quellen ergänzen (siehe unten)"
        )
        ttk.Label(guide, text=steps, justify="left",
                  foreground=self._state.colors().get("text", "#333333")).pack(anchor="w")
        register_lang(self._state, ttk.Label(guide, text=self._state.t("tl.note"),
                  justify="left", wraplength=820,
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ), "tl.note").pack(anchor="w", pady=(4, 0))

        # ── Aufteilung: links Aktionen (scrollbar), rechts Live-Log ───────
        body = ttk.Panedwindow(f, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(2, 10))

        left_wrap = ttk.Frame(body)
        body.add(left_wrap, weight=3)
        right_wrap = ttk.Frame(body)
        body.add(right_wrap, weight=2)

        # Scrollbarer Aktionsbereich
        canvas = tk.Canvas(left_wrap, highlightthickness=0,
                           bg=self._state.colors().get("bg", "#ffffff"))
        vsb = ttk.Scrollbar(left_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(inner_id, width=e.width))
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Live-Log rechts
        ttk.Label(right_wrap, text="Live-Log",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 2))
        self._tool_log = scrolledtext.ScrolledText(
            right_wrap, height=10, wrap="word", state="disabled",
            bg="#13131f", fg="#e8eaed", font=("Consolas", 9), relief="flat")
        self._tool_log.pack(fill="both", expand=True)
        clear = ttk.Button(right_wrap, text="Log leeren",
                           command=self._tool_log_clear)
        clear.pack(anchor="e", pady=(4, 0))
        register_tooltip(clear, "tt.tl_logclear", self._state)

        # ── Eingabefelder (Profile/Pfarrei/IDs/Dateien) ───────────────────
        self._tl_wt_profile = tk.StringVar(value="anverwandte")
        self._tl_wt_discover = tk.BooleanVar(value=True)
        self._tl_wt_trainn = tk.StringVar(value="100")
        self._tl_mat_parish = tk.StringVar(value="")   # compat – wird durch Listbox ersetzt
        self._tl_mat_dryrun = tk.BooleanVar(value=False)
        self._tl_mh_csv = tk.StringVar(value="")
        self._tl_mh_mincm = tk.StringVar(value="20")
        self._tl_mh_repair = tk.BooleanVar(value=False)
        self._tl_imp_mh = tk.StringVar(value="")
        self._tl_imp_gm = tk.StringVar(value="")
        self._tl_wk_id = tk.StringVar(value="")
        self._tl_match_csv = tk.StringVar(value="")
        self._tl_conc = tk.StringVar(value="")
        self._tl_ftm_file = tk.StringVar(value="")
        self._tl_ftm_source = tk.StringVar(value="ftm")
        self._tl_ftm_no_link = tk.BooleanVar(value=False)
        self._tl_diff_out = tk.StringVar(value="")
        self._tl_diff_include_new = tk.BooleanVar(value=True)
        self._tl_ftdna_csv = tk.StringVar(value="")
        self._tl_mat_diocese = tk.StringVar(value="")

        # ── Pipeline: Datenquellen-Übersicht ──────────────────────────────
        pipe_lf = self._tool_section(inner, "🔌  Datenquellen-Pipeline")
        self._pipeline = DataSourcePipeline(
            pipe_lf,
            self._pipeline_sources(),
            colors=self._state.colors(),
        )
        self._pipeline.pack(fill="x", pady=(0, 2))
        # Status 800 ms nach Aufbau im Hintergrund laden
        self.after(800, self._load_pipeline_status)

        # ── Abschnitt A0c: Matricula-Priorität ───────────────────────────
        sec = self._tool_section(inner, "📊  Matricula-Priorität (Pfarrei-Statistik)")
        ttk.Label(sec,
                  text="Welche Kirchengemeinde hat die meisten Anverwandte-Belege? "
                       "→ Transkriptions-Reihenfolge.",
                  foreground=self._state.colors().get("text_dim", "#888888"),
                  wraplength=380).pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Diözese-Filter:").pack(side="left")
        self._tl_mat_prio_diocese = tk.StringVar(value="")
        ttk.Entry(row, textvariable=self._tl_mat_prio_diocese, width=16).pack(
            side="left", padx=(4, 10))
        ttk.Label(row, text="(leer = alle)",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left")
        row2 = ttk.Frame(sec); row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Top:").pack(side="left")
        self._tl_mat_prio_top = tk.StringVar(value="30")
        ttk.Spinbox(row2, from_=0, to=500, increment=10, width=6,
                    textvariable=self._tl_mat_prio_top).pack(side="left", padx=(4, 10))
        ttk.Label(row2, text="CSV:",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left")
        self._tl_mat_prio_csv = tk.StringVar(value="")
        ttk.Entry(row2, textvariable=self._tl_mat_prio_csv, width=14).pack(
            side="left", padx=(4, 2))
        ttk.Button(row2, text="…", width=3,
                   command=lambda: self._tl_pick_save(
                       self._tl_mat_prio_csv, "CSV", "*.csv")).pack(side="left")
        self._tool_action(sec, "📊 Pfarrei-Priorität auswerten", "mat_prio",
                          self._tl_cmd_mat_prio)

        # ── Abschnitt B: Matricula ────────────────────────────────────────
        sec = self._tool_section(inner, "⛪  Matricula-Kirchenbücher")
        # Pfarrei-Listbox (Mehrfachauswahl)
        lb_hdr = ttk.Frame(sec); lb_hdr.pack(fill="x")
        ttk.Label(lb_hdr, text="Pfarreien (Strg+Klick = Mehrfach):").pack(side="left")
        ttk.Button(lb_hdr, text="↺", width=3,
                   command=self._mat_refresh_parishes).pack(side="right")
        lb_wrap = ttk.Frame(sec); lb_wrap.pack(fill="x", pady=(2, 4))
        lb_vsb = ttk.Scrollbar(lb_wrap, orient="vertical")
        self._mat_listbox = tk.Listbox(
            lb_wrap, height=5, selectmode="extended",
            yscrollcommand=lb_vsb.set, exportselection=False,
            font=("Consolas", 9))
        lb_vsb.configure(command=self._mat_listbox.yview)
        self._mat_listbox.pack(side="left", fill="x", expand=True)
        lb_vsb.pack(side="left", fill="y")
        self.after(500, self._mat_refresh_parishes)
        self._tool_action(sec, "0 · Pfarrei-Katalog (einmalig)", "mat_cat",
                          lambda: [sys.executable, "-u", _tool("scrape_matricula_osnabrueck.py")])
        self._tool_action(sec, "1 · Bücherverzeichnis holen", "mat_books",
                          self._tl_cmd_mat_books)
        row2 = ttk.Frame(sec); row2.pack(fill="x", pady=(2, 0))
        register_lang(self._state, ttk.Checkbutton(row2, text=self._state.t("tl.c_dryrun"),
                        variable=self._tl_mat_dryrun), "tl.c_dryrun").pack(side="left")
        self._tool_action(sec, "2 · Seiten scannen (Claude Vision)", "mat_scan",
                          self._tl_cmd_mat_scan,
                          on_start=self._mat_reset_progress,
                          on_line=self._mat_on_line)
        self._tool_action(sec, "🔁 Re-Transkription (lokale Bilder)", "mat_retranscribe",
                          self._tl_cmd_mat_retranscribe,
                          on_start=self._mat_reset_progress,
                          on_line=self._mat_on_line)
        self._tool_action(sec, "📄 Kirchenbücher als PDF bündeln", "mat_pdf",
                          self._tl_cmd_mat_pdf)
        # Fortschrittsanzeige
        prog_row = ttk.Frame(sec); prog_row.pack(fill="x", pady=(4, 0))
        self._mat_prog_label = ttk.Label(prog_row, text="", width=12, anchor="e")
        self._mat_prog_label.pack(side="left")
        self._mat_prog_bar = ttk.Progressbar(prog_row, mode="determinate", length=200)
        self._mat_prog_bar.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._tool_action(sec, "🌐 Matricula-Viewer öffnen (Port 5000)", "mat_viewer",
                          lambda: [sys.executable, "-u", _tool("matricula_viewer.py")],
                          on_start=lambda: self.after(2500, lambda: webbrowser.open("http://localhost:5000")))

        # ── Abschnitt E: Extras / Viewer ──────────────────────────────────
        sec = self._tool_section(inner, "🧰  Extras")
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        _bw = ttk.Button(row, text="🧱 Brick-Wall-Finder",
                         command=self._open_brickwall_finder)
        _bw.pack(side="left", padx=(0, 8))
        _tk = ttk.Button(row, text="🗂 Aufgaben (To-Dos)",
                         command=self._open_research_tasks)
        _tk.pack(side="left", padx=(0, 8))
        ttk.Label(row, text="Gut dokumentierte Ahnen ohne bekannte Eltern "
                            "(hochpriore Forschungsziele).",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left")
        self._tool_action(sec, "GEDCOM verkleinern (GED Slim)", "ged_slim",
                          None, gui=_tool("ged_slim.py"))
        self._tool_action(sec, "Entity-Browser (Port 5001)", "entity",
                          lambda: [sys.executable, "-u", _tool("entity_browser.py")])
        self._tool_action(sec, "📦 Korpus für LLM bündeln (OCR+GEDCOM+Belege)", "llm_bundle",
                          lambda: [sys.executable, "-u", "-m",
                                   "ancestry.tools.bundle_for_llm"])

        # ── Abschnitt F: Ortskonkordanz (Anverwandte → Standardorte) ──────────
        sec = self._tool_section(inner, "🗺  Ortskonkordanz")
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        _b = ttk.Button(row, text="✏ Orte bearbeiten", command=self._open_place_editor)
        _b.pack(side="left", padx=(0, 8))
        register_tooltip(_b, "tt.tl_places", self._state)
        register_lang(self._state, ttk.Label(row, text=self._state.t("tl.places_hint"),
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ), "tl.places_hint").pack(side="left")
        self._tool_action(sec, "📤 Anverwandte-Orte exportieren (für KI)", "conc_exp",
                          lambda: [sys.executable, "-u", "-m",
                                   "ancestry.core.place_concordance", "--export"])
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        register_lang(self._state, ttk.Label(row, text=self._state.t("tl.mapping_file")), "tl.mapping_file").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_conc, width=24).pack(side="left", padx=4)
        _pb = ttk.Button(row, text="…", width=3,
                   command=lambda: self._tl_pick(self._tl_conc, "JSON/CSV", "*.json *.csv")
                   )
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        self._tool_action(sec, "📥 Ortskonkordanz importieren", "conc_imp",
                          self._tl_cmd_conc_import)

    # ── Tutorial ──────────────────────────────────────────────────────────
    def _open_tutorial(self):
        self._tutorial.start()

    # ── Pipeline-Status (Live-Abfrage aus DB) ─────────────────────────────
    def _load_pipeline_status(self):
        """Fragt Datensatz-Zählungen im Hintergrund ab und aktualisiert die Kacheln."""
        import threading

        def _query():
            statuses: dict[str, tuple[str, str]] = {}
            try:
                db = getattr(self._state, "db", None)
                if db is None:
                    self.after(3000, self._load_pipeline_status)
                    return

                src_counts:   dict[str, int] = {}
                match_counts: dict[str, int] = {}

                try:
                    with db._cursor() as cur:
                        for src, cnt in cur.execute(
                            "SELECT COALESCE(source,''), COUNT(*) "
                            "FROM gedcom_persons GROUP BY source"
                        ):
                            src_counts[src] = cnt
                except Exception:
                    pass

                try:
                    with db._cursor() as cur:
                        for src, cnt in cur.execute(
                            "SELECT COALESCE(source,''), COUNT(*) "
                            "FROM matches GROUP BY source"
                        ):
                            match_counts[src] = cnt
                except Exception:
                    pass

                def _ok(n: int, unit: str) -> tuple[str, str]:
                    return (f"{n:,} {unit}", "ok") if n else (unit.rstrip("e") + " – leer", "empty")

                # GEDCOM/FTM
                n = src_counts.get("gedcom", 0) + src_counts.get("ftm", 0)
                statuses["gedcom"] = (f"{n:,} Personen", "ok") if n else ("nicht geladen", "empty")

                # Ancestry — Summe aller Matches, die nicht einer anderen Plattform gehören
                known = {"ftdna", "myheritage", "gedmatch"}
                ancestry_n = sum(v for k, v in match_counts.items() if k not in known)
                statuses["ancestry"] = (f"{ancestry_n:,} Matches", "ok") if ancestry_n else ("nicht geladen", "empty")

                # Webtrees
                n = src_counts.get("webtrees", 0) + src_counts.get("anverwandte", 0)
                statuses["webtrees"] = (f"{n:,} Personen", "ok") if n else ("nicht geladen", "empty")

                # Matricula
                try:
                    from ancestry.tools import matricula_status as _mstat
                    _mat_p = _mstat.get_parish_status()
                    _mat_done = sum(1 for _p in _mat_p if _p["status"] == _mstat.STATUS_DONE)
                    if _mat_p:
                        statuses["matricula"] = (
                            f"{len(_mat_p)} Pfarreien ({_mat_done} fertig)", "ok")
                    else:
                        statuses["matricula"] = ("nicht geladen", "empty")
                except Exception:
                    statuses["matricula"] = ("nicht verfügbar", "empty")

                # MyHeritage
                n = match_counts.get("myheritage", 0)
                statuses["myheritage"] = (f"{n:,} Matches", "ok") if n else ("nicht geladen", "empty")

                # GEDmatch
                n = match_counts.get("gedmatch", 0)
                statuses["gedmatch"] = (f"{n:,} Matches", "ok") if n else ("nicht geladen", "empty")

                # FTDNA
                n = match_counts.get("ftdna", 0)
                statuses["ftdna"] = (f"{n:,} Matches", "ok") if n else ("nicht geladen", "empty")

                # WikiTree
                n = src_counts.get("wikitree", 0)
                statuses["wikitree"] = (f"{n:,} Profile", "ok") if n else ("nicht geladen", "empty")

            except Exception:
                pass

            if statuses and hasattr(self, "_pipeline") and self._pipeline.winfo_exists():
                self.after(0, lambda s=statuses: self._pipeline.update_status(s))

        threading.Thread(target=_query, daemon=True, name="pipeline_status").start()

    def refresh_pipeline_status(self):
        """Kann von außen aufgerufen werden, um den Status neu zu laden."""
        self._load_pipeline_status()

    # ── Pipeline: Quellen-Definitionen ────────────────────────────────────
    def _pipeline_sources(self) -> list[dict]:
        return [
            {
                "id": "gedcom",
                "icon": "🗂",
                "label": "GEDCOM/FTM",
                "sub": ".ged / .ftm",
                "color": "#1F4E79",
                "desc": (
                    "[DE] Eigenen Stammbaum als GEDCOM laden oder FTM-Direktbrücke verwenden.\n"
                    "FTM 2014–2017: .ftm direkt; FTM 2024 (MacKiev): in FTM → Datei → Exportieren → GEDCOM.\n"
                    "[EN] Load your own tree as GEDCOM or use the FTM direct bridge.\n"
                    "FTM 2014–2017: .ftm directly; FTM 2024 (MacKiev): in FTM → File → Export → GEDCOM."
                ),
                "builder": self._src_gedcom,
            },
            {
                "id": "ancestry",
                "icon": "🧬",
                "label": "Ancestry",
                "sub": "Cookie / Login",
                "color": "#155724",
                "desc": (
                    "[DE] Ancestry-DNA-Matches werden über den Login-Tab (Cookie-Export) heruntergeladen.\n"
                    "Vollständige Anleitung im Login-Tab und im Herunterladen-Tab.\n"
                    "[EN] Ancestry DNA matches are downloaded via the Login tab (cookie export).\n"
                    "Full guide in the Login tab and the Download tab."
                ),
                "builder": self._src_ancestry,
            },
            {
                "id": "webtrees",
                "icon": "🌳",
                "label": "Webtrees",
                "sub": "Stammbaum",
                "color": "#4A148C",
                "desc": (
                    "[DE] Öffentlichen Webtrees-Stammbaum crawlen und in die Datenbank importieren.\n"
                    "Voraussetzung: Netzwerkzugang zur Webtrees-Instanz und gültiges Profil.\n"
                    "[EN] Crawl a public Webtrees family tree and import it into the database.\n"
                    "Prerequisite: network access to the Webtrees instance and a valid profile."
                ),
                "builder": self._src_webtrees,
            },
            {
                "id": "matricula",
                "icon": "⛪",
                "label": "Matricula",
                "sub": "Kirchenbücher",
                "color": "#5D4037",
                "desc": (
                    "[DE] Kirchenbücher aus Matricula-Online herunterladen und transkribieren.\n"
                    "Bistums-Katalog laden → Pfarrei wählen → Bücher scannen (Claude Vision).\n"
                    "[EN] Download and transcribe church books from Matricula-Online.\n"
                    "Load diocese catalog → select parish → scan books (Claude Vision)."
                ),
                "builder": self._src_matricula,
            },
            {
                "id": "myheritage",
                "icon": "💙",
                "label": "MyHeritage",
                "sub": "DNA-Matches",
                "color": "#B45309",
                "desc": (
                    "[DE] MyHeritage DNA-Matches herunterladen (Browser-Login nötig) oder\n"
                    "eine vorhandene Match-CSV direkt importieren.\n"
                    "[EN] Download MyHeritage DNA matches (browser login required) or\n"
                    "import an existing match CSV directly."
                ),
                "builder": self._src_myheritage,
            },
            {
                "id": "gedmatch",
                "icon": "🔗",
                "label": "GEDmatch",
                "sub": "TSV-Import",
                "color": "#880E4F",
                "desc": (
                    "[DE] GEDmatch One-to-Many-Ergebnisse als TSV importieren.\n"
                    "gedmatch.com → One-to-Many → Download → TSV-Datei hier wählen.\n"
                    "[EN] Import GEDmatch One-to-Many results as TSV.\n"
                    "gedmatch.com → One-to-Many → Download → choose TSV file here."
                ),
                "builder": self._src_gedmatch,
            },
            {
                "id": "ftdna",
                "icon": "🔬",
                "label": "FTDNA",
                "sub": "Family Finder",
                "color": "#006064",
                "desc": (
                    "[DE] FTDNA Family-Finder-Matches als CSV importieren.\n"
                    "ftdna.com → Family Finder → Matches → Herunterladen (oben rechts) → CSV.\n"
                    "[EN] Import FTDNA Family Finder matches as CSV.\n"
                    "ftdna.com → Family Finder → Matches → Download (top right) → CSV."
                ),
                "builder": self._src_ftdna,
            },
            {
                "id": "wikitree",
                "icon": "🌐",
                "label": "WikiTree",
                "sub": "Vorfahren-API",
                "color": "#1A237E",
                "desc": (
                    "[DE] WikiTree-Vorfahren via öffentliche API importieren.\n"
                    "WikiTree-ID aus der URL ablesen: wikitree.com/wiki/Kovermann-123 → ID = Kovermann-123.\n"
                    "[EN] Import WikiTree ancestors via the public API.\n"
                    "Read the WikiTree ID from the URL: wikitree.com/wiki/Kovermann-123 → ID = Kovermann-123."
                ),
                "builder": self._src_wikitree,
            },
        ]

    # ── Pipeline: Builder-Callbacks ───────────────────────────────────────

    def _src_gedcom(self, frame: ttk.Frame):
        # FTM-Direktbrücke
        ttk.Label(frame, text="FTM- oder GEDCOM-Datei:",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Entry(row, textvariable=self._tl_ftm_file, width=28).pack(side="left", padx=(0, 2))
        _pb = ttk.Button(row, text="…", width=3,
                         command=lambda: self._tl_pick(
                             self._tl_ftm_file, "FTM/GEDCOM",
                             "*.ftm *.ftmb *.FTM *.FTMB *.ged *.gedcom"))
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        row2 = ttk.Frame(frame); row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Quelle:").pack(side="left")
        ttk.Entry(row2, textvariable=self._tl_ftm_source, width=14).pack(
            side="left", padx=(4, 10))
        ttk.Checkbutton(row2, text="nur importieren (kein Querbezug)",
                        variable=self._tl_ftm_no_link).pack(side="left")
        self._tool_action(frame, "🔀 FTM/GEDCOM → Bridge importieren", "ftm_bridge",
                          self._tl_cmd_ftm_bridge)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=6)

        # Diff-Export
        ttk.Label(frame, text="Anverwandte → FTM Diff-Export:",
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(frame,
                  text="Exportiert nur die Felder, die Anverwandte hat und FTM nicht "
                       "→ in FTM importieren (Datei → Import → Merge).",
                  foreground=self._state.colors().get("text_dim", "#888888"),
                  wraplength=480).pack(anchor="w", pady=(0, 2))
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Ausgabe .ged:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_diff_out, width=22).pack(
            side="left", padx=(4, 2))
        _pb2 = ttk.Button(row, text="…", width=3, command=self._tl_diff_pick_out)
        _pb2.pack(side="left")
        register_tooltip(_pb2, "tt.pick_file", self._state)
        ttk.Label(row, text="(leer = neben DB)",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left", padx=(6, 0))
        row2 = ttk.Frame(frame); row2.pack(fill="x", pady=2)
        ttk.Checkbutton(row2, text="Fehlende Verwandte einschließen (BFS von Cousins)",
                        variable=self._tl_diff_include_new).pack(side="left")
        self._tool_action(frame, "📤 Diff-GEDCOM erzeugen", "diff_anv_ftm",
                          self._tl_cmd_diff_anv_ftm)
        self._tool_action(frame, "🧪 1 Cousin testen (FTM-Merge prüfen)", "diff_anv_ftm_test",
                          self._tl_cmd_diff_anv_ftm_test)

    def _src_ancestry(self, frame: ttk.Frame):
        dim = self._state.colors().get("text_dim", "#888888")
        ttk.Label(frame,
                  text=(
                      "Ancestry-Login erfolgt im Login-Tab (Cookie-Export aus dem Browser).\n"
                      "Matches werden im Herunterladen-Tab abgerufen.\n\n"
                      "Ancestry login happens in the Login tab (browser cookie export).\n"
                      "Matches are downloaded in the Download tab."
                  ),
                  foreground=dim,
                  wraplength=520,
                  justify="left",
                  ).pack(anchor="w", padx=4, pady=8)

    def _src_webtrees(self, frame: ttk.Frame):
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Profil:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_wt_profile, width=16).pack(
            side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="--discover (ganzer Baum)",
                        variable=self._tl_wt_discover).pack(side="left")
        self._tool_action(frame, "Öffentlichen Baum crawlen", "wt_crawl",
                          self._tl_cmd_wt_crawl)
        _b = register_lang(self._state,
                           ttk.Button(frame, text=self._state.t("tl.b_dbdel"),
                                      command=self._wt_delete_db),
                           "tl.b_dbdel")
        _b.pack(anchor="w", pady=(0, 2))
        register_tooltip(_b, "tt.tl_dbdel", self._state)
        self._tool_action(frame, "Crawl → Datenbank importieren", "wt_import",
                          lambda: [sys.executable, "-u", _tool("import_webtrees.py")])
        self._tool_action(frame, "💾 Als GEDCOM-Datei exportieren", "wt_export",
                          self._tl_cmd_wt_export)
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Seiten:").pack(side="left")
        ttk.Spinbox(row, from_=10, to=1000, increment=10, width=6,
                    textvariable=self._tl_wt_trainn).pack(side="left", padx=(4, 8))
        ttk.Label(row, text="HTML+JSON lokal in tools/webtrees_training/",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left")
        self._tool_action(frame, "🧪 Testlauf: Seiten lokal sichern", "wt_training",
                          self._tl_cmd_wt_training)

    def _src_matricula(self, frame: ttk.Frame):
        dim = self._state.colors().get("text_dim", "#888888")
        try:
            from ancestry.tools import matricula_status as mstat
            dioceses = mstat.get_dioceses()
            parishes = mstat.get_parish_status()
            done_p = sum(1 for p in parishes if p["status"] == mstat.STATUS_DONE)
            if dioceses:
                info = (f"{len(dioceses)} Bistum/Archiv · {len(parishes)} Pfarreien"
                        f" ({done_p} fertig transkribiert)")
            else:
                info = "Noch keine Bestände geladen — Bistums-Katalog starten."
        except Exception:
            info = "Status nicht verfügbar"
        ttk.Label(frame, text=info, foreground=dim, wraplength=460).pack(
            anchor="w", pady=(0, 6))

        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Bistum-Slug:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_mat_diocese, width=18).pack(
            side="left", padx=(4, 8))
        ttk.Label(row,
                  text="z. B. osnabrueck · muenster · paderborn\n"
                       "(leer = alle Bistümer auflisten)",
                  foreground=dim, justify="left").pack(side="left")
        self._tool_action(frame, "⛪ Bistums-Katalog laden", "mat_cat_v2",
                          self._tl_cmd_mat_catalog)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=6)
        ttk.Button(
            frame,
            text="→ Zum Matricula-Tab wechseln",
            command=self._jump_to_matricula_tab,
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text="Dort: Pfarrei wählen, Bücher scannen (Claude Vision), "
                 "Viewer, NER-Personensuche.",
            foreground=dim, wraplength=460, justify="left",
        ).pack(anchor="w", pady=(2, 0))

    def _src_myheritage(self, frame: ttk.Frame):
        self._tool_action(frame, "1 · Matchliste herunterladen", "mh_dl",
                          lambda: [sys.executable, "-u", _tool("download_myheritage.py")])
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Match-CSV:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_mh_csv, width=26).pack(side="left", padx=4)
        _pb = ttk.Button(row, text="…", width=3,
                         command=lambda: self._tl_pick(self._tl_mh_csv, "CSV", "*.csv"))
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        opt = ttk.Frame(frame); opt.pack(fill="x", pady=2)
        ttk.Label(opt, text="ab cM:").pack(side="left")
        ttk.Spinbox(opt, from_=6, to=200, increment=5, width=5,
                    textvariable=self._tl_mh_mincm).pack(side="left", padx=(2, 10))
        register_lang(self._state,
                      ttk.Checkbutton(opt, text=self._state.t("tl.c_incomplete"),
                                      variable=self._tl_mh_repair),
                      "tl.c_incomplete").pack(side="left")
        self._tool_action(frame, "2 · Gemeinsame Matches laden", "mh_shared",
                          self._tl_cmd_mh_shared)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=4)

        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="MH-CSV importieren:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_imp_mh, width=22).pack(side="left", padx=4)
        _pb2 = ttk.Button(row, text="…", width=3,
                          command=lambda: self._tl_pick(self._tl_imp_mh, "CSV", "*.csv"))
        _pb2.pack(side="left")
        register_tooltip(_pb2, "tt.pick_file", self._state)
        self._tool_action(frame, "MyHeritage-CSV → DB", "imp_mh",
                          lambda: [sys.executable, "-u", _tool("import_mh_csv.py")]
                          + self._arg(self._tl_imp_mh))

    def _src_gedmatch(self, frame: ttk.Frame):
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="GEDmatch TSV/CSV:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_imp_gm, width=24).pack(side="left", padx=4)
        _pb = ttk.Button(row, text="…", width=3,
                         command=lambda: self._tl_pick(self._tl_imp_gm, "TSV/CSV", "*.*"))
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        self._tool_action(frame, "GEDmatch-TSV → DB", "imp_gm",
                          lambda: [sys.executable, "-u", _tool("import_gedmatch.py")]
                          + self._arg(self._tl_imp_gm))

    def _src_ftdna(self, frame: ttk.Frame):
        ttk.Label(frame,
                  text="ftdna.com → Family Finder → Matches → Herunterladen (oben rechts) → CSV",
                  foreground=self._state.colors().get("text_dim", "#888888"),
                  ).pack(anchor="w", pady=(0, 2))
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="FTDNA matches.csv:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_ftdna_csv, width=24).pack(side="left", padx=4)
        _pb = ttk.Button(row, text="…", width=3,
                         command=lambda: self._tl_pick(self._tl_ftdna_csv, "CSV", "*.csv"))
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        self._tool_action(frame, "🔬 FTDNA Matches → DB importieren", "imp_ftdna",
                          self._tl_cmd_ftdna_import)

    def _src_wikitree(self, frame: ttk.Frame):
        row = ttk.Frame(frame); row.pack(fill="x", pady=2)
        ttk.Label(row, text="WikiTree-ID:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_wk_id, width=20).pack(side="left", padx=4)
        ttk.Label(row, text="z. B. Kovermann-123",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left")
        self._tool_action(frame, "WikiTree → DB", "imp_wk",
                          self._tl_cmd_wikitree)

        ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=4)

        row2 = ttk.Frame(frame); row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Match-CSV:").pack(side="left")
        ttk.Entry(row2, textvariable=self._tl_match_csv, width=24).pack(side="left", padx=4)
        _pb = ttk.Button(row2, text="…", width=3,
                         command=lambda: self._tl_pick(self._tl_match_csv, "CSV", "*.csv"))
        _pb.pack(side="left")
        register_tooltip(_pb, "tt.pick_file", self._state)
        _b = register_lang(self._state,
                           ttk.Button(frame, text=self._state.t("tl.b_impmatch"),
                                      command=self._import_match_csv),
                           "tl.b_impmatch")
        _b.pack(anchor="w", pady=(2, 0))
        register_tooltip(_b, "tt.tl_impmatch", self._state)

    # ── FTDNA-Import ──────────────────────────────────────────────────────
    def _tl_cmd_ftdna_import(self) -> list[str]:
        csv = self._tl_ftdna_csv.get().strip()
        if not csv:
            from tkinter import messagebox
            messagebox.showwarning(
                "FTDNA CSV fehlt",
                self._state.t("dl.m_choose_csv"),
                parent=self)
            return []
        return [sys.executable, "-u", _tool("import_ftdna_matches.py"), csv]

    # ── Match-CSV importieren ─────────────────────────────────────────────
    def _import_match_csv(self):
        import threading
        from tkinter import messagebox
        csv_path = self._tl_match_csv.get().strip()
        if not csv_path:
            messagebox.showinfo("Match-Import", self._state.t("dl.m_choose_csv"),
                                parent=self)
            return

        def _bg():
            try:
                from ancestry.core.bridge.gedcom_import import import_match_csv
                ins, upd = import_match_csv(self._state.db, csv_path)
                self.after(0, lambda: messagebox.showinfo(
                    "Match-Import",
                    f"Fertig: {ins} neu, {upd} aktualisiert.",
                    parent=self))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda m=msg: messagebox.showerror(
                    "Match-Import", f"Fehler:\n{m}", parent=self))

        threading.Thread(target=_bg, daemon=True, name="match_csv_import").start()

    # ── Matricula-Hilfsroutinen ───────────────────────────────────────────
    def _mat_get_parishes(self) -> list[str]:
        """Gibt Slugs der selektierten Pfarreien zurück."""
        result = []
        if not hasattr(self, "_mat_listbox"):
            return result
        for i in self._mat_listbox.curselection():
            item = self._mat_listbox.get(i).strip()
            if item.startswith("──"):   # Bistums-Überschrift überspringen
                continue
            item = item.lstrip("✓◐○ ")
            slug = item.split()[0]
            if slug:
                result.append(slug)
        return result

    def _mat_save_last_parish(self):
        parishes = self._mat_get_parishes()
        if parishes:
            try:
                with open(_MAT_LAST_PARISH, "w", encoding="utf-8") as f:
                    f.write(parishes[0])
            except Exception:
                pass

    def _mat_refresh_parishes(self):
        """Lädt Pfarrei-Liste mit Scan-Status aus DB in die Listbox.

        Bei mehreren Bistümern werden Pfarreien unter Bistums-Überschriften
        gruppiert und eingerückt angezeigt."""
        try:
            import sqlite3
            from collections import defaultdict

            from ancestry.tools.scan_matricula_kirchspiel import PARISH_DB
            if not PARISH_DB.exists():
                return
            conn = sqlite3.connect(str(PARISH_DB))
            rows = conn.execute("""
                SELECT kb.parish_id,
                       SUM(COALESCE(kb.total_pages, 0)) AS total,
                       COUNT(CASE WHEN mps.status='done' THEN 1 END) AS done
                FROM kirchenbuecher kb
                LEFT JOIN matricula_page_scans mps ON mps.book_id = kb.book_id
                GROUP BY kb.parish_id
                ORDER BY kb.parish_id
            """).fetchall()
            conn.close()

            # Letzte Auswahl + gespeicherte Pfarrei merken
            prev: set[str] = set()
            for i in self._mat_listbox.curselection():
                item = self._mat_listbox.get(i).strip().lstrip("✓◐○ ")
                prev.add(item.split()[0])
            try:
                with open(_MAT_LAST_PARISH, encoding="utf-8") as f:
                    prev.add(f.read().strip())
            except Exception:
                pass

            # Gruppieren nach Bistum (alles außer letztem Pfad-Segment)
            diocese_map: dict[str, list] = defaultdict(list)
            for parish_id, total, done in rows:
                parts = parish_id.split("/")
                diocese = "/".join(parts[:-1]) if len(parts) > 1 else ""
                diocese_map[diocese].append((parish_id, total, done))

            self._mat_listbox.delete(0, "end")
            multi = len(diocese_map) > 1

            for diocese in sorted(diocese_map):
                if multi:
                    dioc_slug = diocese.split("/")[-1].upper() if diocese else "UNBEKANNT"
                    self._mat_listbox.insert("end", f"── {dioc_slug} ──")
                    hdr_idx = self._mat_listbox.size() - 1
                    self._mat_listbox.itemconfig(hdr_idx, fg="#777777",
                                                 selectbackground="#e0e0e0",
                                                 selectforeground="#777777")

                indent = "  " if multi else ""
                for parish_id, total, done in diocese_map[diocese]:
                    slug = parish_id.split("/")[-1]
                    if total and total > 0:
                        pct = int(done * 100 / total)
                        if pct >= 100:
                            label = f"{indent}✓ {slug}  ({done}/{total})"
                        elif done > 0:
                            label = f"{indent}◐ {slug}  ({done}/{total})"
                        else:
                            label = f"{indent}○ {slug}"
                    else:
                        label = f"{indent}○ {slug}"
                    self._mat_listbox.insert("end", label)
                    if slug in prev:
                        self._mat_listbox.selection_set("end")
        except Exception:
            pass

    def _mat_reset_progress(self):
        self._mat_save_last_parish()
        if hasattr(self, "_mat_prog_bar"):
            self._mat_prog_bar.configure(mode="determinate", value=0, maximum=100)
        if hasattr(self, "_mat_prog_label"):
            self._mat_prog_label.configure(text="")

    def _mat_on_line(self, line: str) -> str | None:
        """Filtert ##PROG##-Zeilen und aktualisiert die Progressbar."""
        if line.startswith("##PROG## "):
            try:
                cur_s, tot_s = line.strip()[9:].split("/")
                current, total = int(cur_s), int(tot_s)
                if total > 0 and hasattr(self, "_mat_prog_bar"):
                    self._mat_prog_bar.configure(
                        mode="determinate", maximum=total, value=current)
                    self._mat_prog_label.configure(text=f"{current}/{total}")
            except Exception:
                pass
            return None   # nicht in den Log schreiben
        return line

    def _jump_to_matricula_tab(self):
        """Wechselt zum Matricula-Tab im Haupt-Notebook."""
        try:
            nb = self.nametowidget(self.winfo_parent())
            from ancestry.gui.tabs.matricula import MatriculaTab
            for tab_id in nb.tabs():
                try:
                    if isinstance(nb.nametowidget(tab_id), MatriculaTab):
                        nb.select(tab_id)
                        return
                except Exception:
                    continue
            for tab_id in nb.tabs():
                if "matricula" in nb.tab(tab_id, "text").lower():
                    nb.select(tab_id)
                    return
        except Exception:
            pass

    # ── Brick-Wall-Finder ─────────────────────────────────────────────────
    def _open_brickwall_finder(self):
        from ancestry.gui.analysis.brickwall_finder import show_brickwall_finder
        show_brickwall_finder(
            self, self._state,
            set_status=lambda msg: self._tool_append(msg + "\n"))

    # ── Research-To-Do-Manager (B1) ───────────────────────────────────────
    def _open_research_tasks(self):
        from ancestry.gui.analysis.research_tasks_view import show_research_tasks
        show_research_tasks(
            self, self._state,
            set_status=lambda msg: self._tool_append(msg + "\n"))

    # ── Ortskonkordanz-Editor ─────────────────────────────────────────────
    def _open_place_editor(self):
        from pathlib import Path

        from ancestry.gui.analysis.place_editor import PlaceEditorDialog
        from ancestry.tools.crawl_webtrees import SCRIPT_DIR
        dbs = list(SCRIPT_DIR.glob("webtrees_*.db"))
        legacy = SCRIPT_DIR / "webtrees_crawl.db"
        if legacy.exists() and legacy not in dbs:
            dbs.append(legacy)
        PlaceEditorDialog(self, dbs)

    # ── Anleitung öffnen ───────────────────────────────────────────────────
    def _open_wiki(self):
        """Öffnet WIKI.md im Standardprogramm (Windows) bzw. im Browser."""
        if not os.path.exists(_WIKI_PATH):
            self._tool_append(f"⚠ Anleitung nicht gefunden: {_WIKI_PATH}\n")
            return
        try:
            os.startfile(_WIKI_PATH)            # type: ignore[attr-defined]  (Windows)
        except AttributeError:
            webbrowser.open(f"file://{_WIKI_PATH}")
        except Exception as exc:
            self._tool_append(f"⚠ Konnte Anleitung nicht öffnen: {exc}\n")

    # ── UI-Bausteine ──────────────────────────────────────────────────────
    def _tool_section(self, parent, title: str) -> ttk.Frame:
        lf = ttk.LabelFrame(parent, text=title, padding=8)
        lf.pack(fill="x", expand=True, pady=(0, 8), padx=2)
        return lf

    def _tool_action(self, parent, label: str, key: str,
                     build_cmd, gui: str | None = None, on_start=None, on_line=None):
        """Eine Tool-Zeile: Beschriftung + ▶ Start + ■ Stop."""
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=34, anchor="w").pack(side="left")
        if gui:
            _open = register_lang(self._state, ttk.Button(row, text=self._state.t("tl.b_open"),
                               command=lambda g=gui: self._tool_launch_gui(g)), "tl.b_open")
            _open.pack(side="left", padx=2)
            register_tooltip(_open, "tt.tl_open", self._state)
            return
        btn_stop = ttk.Button(row, text="■", width=3, state="disabled")
        btn_start = ttk.Button(row, text="▶ Start")
        register_tooltip(btn_start, "tt.tl_start", self._state)
        register_tooltip(btn_stop, "tt.tl_stop", self._state)
        btn_start.configure(command=lambda: self._tool_run(
            key, build_cmd(), btn_start, btn_stop, on_start=on_start, on_line=on_line))
        btn_stop.configure(command=lambda: self._tool_kill(key))
        btn_start.pack(side="left", padx=2)
        btn_stop.pack(side="left")

    # ── Argument-/Datei-Helfer ────────────────────────────────────────────
    @staticmethod
    def _arg(var: tk.StringVar) -> list[str]:
        v = var.get().strip()
        return [v] if v else []

    def _tl_pick(self, var: tk.StringVar, label: str, pattern: str):
        p = filedialog.askopenfilename(
            title=f"{label}-Datei wählen",
            filetypes=[(label, pattern), ("Alle Dateien", "*.*")])
        if p:
            var.set(p)

    # ── FTM-Direktbrücke ──────────────────────────────────────────────────
    def _tl_cmd_ftm_bridge(self) -> list[str]:
        ftm = self._tl_ftm_file.get().strip()
        if not ftm:
            from tkinter import messagebox
            messagebox.showwarning(
                "FTM-Datei fehlt",
                "Bitte zuerst eine .ftm-Datei auswählen.",
                parent=self)
            return []
        cmd = [sys.executable, "-u",
               _tool("import_ftm_bridge.py"),
               ftm,
               "--source", self._tl_ftm_source.get().strip() or "ftm"]
        if self._tl_ftm_no_link.get():
            cmd.append("--no-link")
        return cmd

    # ── Anverwandte → FTM Diff ────────────────────────────────────────────
    def _tl_diff_pick_out(self):
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(
            title="Diff-GEDCOM speichern unter",
            defaultextension=".ged",
            initialfile="diff_anv_ftm.ged",
            filetypes=[("GEDCOM", "*.ged"), ("Alle Dateien", "*.*")])
        if p:
            self._tl_diff_out.set(p)

    def _tl_cmd_diff_anv_ftm(self) -> list[str]:
        cmd = [sys.executable, "-u", _tool("diff_anv_ftm.py")]
        out = self._tl_diff_out.get().strip()
        if out:
            cmd += ["-o", out]
        if not self._tl_diff_include_new.get():
            cmd.append("--no-new")
        return cmd

    def _tl_cmd_diff_anv_ftm_test(self) -> list[str]:
        return [sys.executable, "-u", _tool("diff_anv_ftm.py"), "--test-one"]

    def _tl_cmd_mat_catalog(self) -> list[str]:
        """Lädt Bistums-Katalog von Matricula-Online (universal scraper)."""
        diocese = self._tl_mat_diocese.get().strip()
        cmd = [sys.executable, "-u", "-m", "ancestry.tools.scrape_matricula"]
        if diocese:
            cmd += ["--diocese", diocese]
        return cmd

    # ── Matricula-Priorität ───────────────────────────────────────────────
    def _tl_pick_save(self, var: tk.StringVar, label: str, pattern: str):
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(
            title=f"{label} speichern unter",
            filetypes=[(label, pattern), ("Alle Dateien", "*.*")])
        if p:
            var.set(p)

    def _tl_cmd_mat_prio(self) -> list[str]:
        cmd = [sys.executable, "-u", _tool("matricula_prio.py")]
        dio = self._tl_mat_prio_diocese.get().strip()
        if dio:
            cmd += ["--diocese", dio]
        top = self._tl_mat_prio_top.get().strip()
        if top and top != "0":
            cmd += ["--top", top]
        csv_out = self._tl_mat_prio_csv.get().strip()
        if csv_out:
            cmd += ["--csv", csv_out]
        return cmd

    # ── Befehlszeilen ─────────────────────────────────────────────────────
    def _tl_cmd_wt_crawl(self) -> list[str]:
        cmd = [sys.executable, "-u", _tool("crawl_webtrees.py"), "crawl",
               "--profile", self._tl_wt_profile.get().strip() or "anverwandte",
               "--max", "0"]
        if self._tl_wt_discover.get():
            cmd.append("--discover")
        return cmd

    def _wt_delete_db(self):
        from pathlib import Path
        from tkinter import messagebox

        from ancestry.tools.crawl_webtrees import SCRIPT_DIR
        profile = self._tl_wt_profile.get().strip() or "anverwandte"
        candidates = [
            SCRIPT_DIR / f"webtrees_{profile}.db",
            SCRIPT_DIR / "webtrees_crawl.db",
        ]
        found = [p for p in candidates if p.exists()]
        if not found:
            messagebox.showinfo(self._state.t("tl.dbdel_t"), self._state.t("tl.m_no_crawl_db"), parent=self)
            return
        names = "\n".join(str(p.name) for p in found)
        if not messagebox.askyesno(
                self._state.t("tl.dbdel_t"),
                f"Folgende Datei(en) unwiderruflich löschen?\n\n{names}",
                icon="warning", parent=self):
            return
        for p in found:
            try:
                p.unlink()
            except OSError as exc:
                messagebox.showerror(self._state.t("dlg.error"), f"{p.name}: {exc}", parent=self)
                return
        messagebox.showinfo(self._state.t("tl.dbdel_t"), f"Gelöscht:\n{names}", parent=self)

    def _tl_cmd_wt_export(self) -> list[str]:
        profile = self._tl_wt_profile.get().strip() or "anverwandte"
        out = filedialog.asksaveasfilename(
            title=self._state.t("tl.t_save_gedcom"), defaultextension=".ged",
            initialfile=f"{profile}.ged",
            filetypes=[("GEDCOM", "*.ged"), ("Alle Dateien", "*.*")])
        if not out:
            return []
        return [sys.executable, "-u", _tool("crawl_webtrees.py"),
                "export-gedcom", "--profile", profile, "--out", out]

    def _tl_cmd_wt_training(self) -> list[str]:
        profile = self._tl_wt_profile.get().strip() or "anverwandte"
        n = (self._tl_wt_trainn.get() or "").strip() or "100"
        return [sys.executable, "-u", _tool("crawl_webtrees.py"), "training",
                "--profile", profile, "--n", n]

    def _tl_cmd_mat_books(self) -> list[str]:
        from tkinter import messagebox
        parishes = self._mat_get_parishes()
        if not parishes:
            messagebox.showwarning("Pfarrei erforderlich",
                                   self._state.t("tl.m_choose_parish"),
                                   parent=self)
            return []
        cmd = [sys.executable, "-u", _tool("fetch_matricula_books.py")]
        cmd += ["--parish"] + parishes
        return cmd

    def _tl_cmd_mat_scan(self) -> list[str]:
        from tkinter import messagebox
        parishes = self._mat_get_parishes()
        if not parishes:
            messagebox.showwarning("Pfarrei erforderlich",
                                   self._state.t("tl.m_choose_parish"),
                                   parent=self)
            return []
        cmd = [sys.executable, "-u", _tool("scan_matricula_kirchspiel.py"),
               "--parish"] + parishes
        if self._tl_mat_dryrun.get():
            cmd.append("--dry-run")
        return cmd

    def _tl_cmd_mat_retranscribe(self) -> list[str]:
        from tkinter import messagebox
        parishes = self._mat_get_parishes()
        if not parishes:
            messagebox.showwarning("Pfarrei erforderlich",
                                   self._state.t("tl.m_choose_parish"),
                                   parent=self)
            return []
        cmd = [sys.executable, "-u", _tool("scan_matricula_kirchspiel.py"),
               "--retranscribe", "--parish"] + parishes
        return cmd

    def _tl_cmd_mat_pdf(self) -> list[str]:
        parishes = self._mat_get_parishes()
        cmd = [sys.executable, "-u", _tool("bundle_matricula_pdf.py")]
        if parishes:
            cmd += ["--parish"] + parishes
        return cmd

    def _tl_cmd_mh_shared(self) -> list[str]:
        csv = self._tl_mh_csv.get().strip()
        if not csv:
            self._tool_append("⚠ Bitte zuerst eine Match-CSV wählen.\n")
            return []
        cmd = [sys.executable, "-u", _tool("fetch_mh_shared_matches.py"),
               "--csv", csv]
        mincm = (self._tl_mh_mincm.get() or "").strip()
        if mincm:
            cmd += ["--min-cm", mincm]
        if self._tl_mh_repair.get():
            # Matches mit < 10 Shared Matches (oft abgebrochen) neu laden
            cmd += ["--repair-threshold", "10"]
        return cmd

    def _tl_cmd_conc_import(self) -> list[str]:
        path = self._tl_conc.get().strip()
        if not path:
            self._tool_append("⚠ Bitte zuerst die Mapping-Datei (JSON/CSV) wählen.\n")
            return []
        return [sys.executable, "-u", "-m", "ancestry.core.place_concordance",
                "--import", path]

    def _tl_cmd_wikitree(self) -> list[str]:
        key = self._tl_wk_id.get().strip()
        if not key:
            self._tool_append("⚠ Bitte eine WikiTree-ID angeben (z. B. Kovermann-123).\n")
            return []
        return [sys.executable, "-u", _tool("import_wikitree.py"), key,
                "--depth", "6"]

    # ── Subprozess-Steuerung ──────────────────────────────────────────────
    def _tool_launch_gui(self, script: str):
        if not os.path.exists(script):
            self._tool_append(f"⚠ Nicht gefunden: {script}\n")
            return
        try:
            subprocess.Popen([sys.executable, script], cwd=str(ROOT),
                             start_new_session=True, env=_utf8_env())
            self._tool_append(f"▶ Eigenes Fenster gestartet: {os.path.basename(script)}\n")
        except Exception as exc:
            self._tool_append(f"⚠ Fehler: {exc}\n")

    def _tool_run(self, key: str, cmd: list[str],
                  btn_start: ttk.Button, btn_stop: ttk.Button, on_start=None, on_line=None):
        if not cmd:
            return
        if self._tool_procs.get(key):
            self._tool_append(f"… {key} läuft bereits.\n")
            return
        self._tool_append("▶ " + " ".join(cmd) + "\n")
        btn_start.configure(state="disabled")
        btn_stop.configure(state="normal")
        q: queue.Queue[str | None] = queue.Queue()

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
                env=_utf8_env())
        except Exception as exc:
            self._tool_append(f"⚠ Fehler: {exc}\n")
            btn_start.configure(state="normal")
            btn_stop.configure(state="disabled")
            return

        self._tool_procs[key] = proc
        if on_start:
            on_start()

        def _reader(p: subprocess.Popen):
            assert p.stdout
            for line in p.stdout:
                q.put(line)
            p.wait()
            q.put(None)
        threading.Thread(target=_reader, args=(proc,), daemon=True).start()

        def _poll():
            while True:
                try:
                    line = q.get_nowait()
                except queue.Empty:
                    break
                if line is None:
                    rc = proc.returncode
                    self._tool_append(f"✓ Fertig ({key}, RC {rc})\n\n")
                    self._tool_procs[key] = None
                    btn_start.configure(state="normal")
                    btn_stop.configure(state="disabled")
                    return
                if on_line is not None:
                    line = on_line(line)
                if line is not None:
                    self._tool_append(line)
            self.after(400, _poll)
        self.after(400, _poll)

    def _tool_kill(self, key: str):
        proc = self._tool_procs.get(key)
        if not proc:
            return
        try:
            proc.terminate()
            self._tool_append(f"■ Stop-Signal an {key} gesendet.\n")
        except Exception as exc:
            self._tool_append(f"⚠ Stop fehlgeschlagen: {exc}\n")

    # ── Log ───────────────────────────────────────────────────────────────
    def _tool_append(self, text: str):
        if not hasattr(self, "_tool_log") or not self._tool_log.winfo_exists():
            return
        self._tool_log.configure(state="normal")
        self._tool_log.insert("end", text)
        self._tool_log.see("end")
        self._tool_log.configure(state="disabled")

    def _tool_log_clear(self):
        self._tool_log.configure(state="normal")
        self._tool_log.delete("1.0", "end")
        self._tool_log.configure(state="disabled")
