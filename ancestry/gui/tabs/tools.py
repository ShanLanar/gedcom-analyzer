"""ToolsTab – Tab „🔧 Werkzeuge" für das Ancestry-DNA-Tool.

Bündelt die eigenständigen CLI-Tools (Webtrees-Crawl, Matricula, MyHeritage,
Importe, GED Slim, Web-Viewer) mit Start-/Stop-Knöpfen und Live-Log direkt in
der Haupt-App, statt sie nur über die Kommandozeile erreichbar zu machen.

Bewusst ohne DB-Zugriffe beim Aufbau, damit der Tab den Programmstart nicht
verlangsamt – alle schweren Aktionen laufen als Subprozess im Hintergrund.
"""
from __future__ import annotations

import os
import sys
import queue
import threading
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

from ancestry.paths import ROOT
from ancestry.gui.state import AppState

_WIKI_PATH = os.path.join(str(ROOT), "WIKI.md")

_TOOLS_DIR = os.path.join(str(ROOT), "ancestry", "tools")


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
        ttk.Label(head, text="🔧 Werkzeuge & Import",
                  font=("Segoe UI", 13, "bold")).pack(side="left")
        ttk.Label(head, text="  Externe Sammel-/Import-Tools – laufen im "
                             "Hintergrund, fortsetzbar, jederzeit per ■ stoppbar.",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left", padx=(8, 0))
        ttk.Button(head, text="📖 Anleitung öffnen",
                   command=self._open_wiki).pack(side="right")

        # ── Anleitung / empfohlener Ablauf ────────────────────────────────
        guide = ttk.LabelFrame(f, text="📋 Anleitung – empfohlener Ablauf", padding=8)
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
        ttk.Label(guide, text="Hinweis: Viele Tools brauchen vorher einen Login im Browser "
                              "(Ancestry/MyHeritage) bzw. eine gewählte Datei. "
                              "Vollständige Schritt-für-Schritt-Anleitung: „📖 Anleitung öffnen\".",
                  justify="left", wraplength=820,
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(anchor="w", pady=(4, 0))

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

        # ── Eingabefelder (Profile/Pfarrei/IDs/Dateien) ───────────────────
        self._tl_wt_profile = tk.StringVar(value="anverwandte")
        self._tl_wt_discover = tk.BooleanVar(value=True)
        self._tl_mat_parish = tk.StringVar(value="")
        self._tl_mh_csv = tk.StringVar(value="")
        self._tl_mh_mincm = tk.StringVar(value="20")
        self._tl_mh_repair = tk.BooleanVar(value=False)
        self._tl_imp_mh = tk.StringVar(value="")
        self._tl_imp_gm = tk.StringVar(value="")
        self._tl_wk_id = tk.StringVar(value="")

        # ── Abschnitt A: Webtrees ─────────────────────────────────────────
        sec = self._tool_section(inner, "⬇  Webtrees-Stammbaum")
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Profil:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_wt_profile, width=16).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="--discover (ganzer Baum)",
                        variable=self._tl_wt_discover).pack(side="left")
        self._tool_action(sec, "Öffentlichen Baum crawlen", "wt_crawl",
                          self._tl_cmd_wt_crawl)
        self._tool_action(sec, "Crawl → Datenbank importieren", "wt_import",
                          lambda: [sys.executable, "-u", _tool("import_webtrees.py")])
        self._tool_action(sec, "💾 Als GEDCOM-Datei exportieren", "wt_export",
                          self._tl_cmd_wt_export)

        # ── Abschnitt B: Matricula ────────────────────────────────────────
        sec = self._tool_section(inner, "⛪  Matricula-Kirchenbücher")
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Pfarrei (optional):").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_mat_parish, width=22).pack(side="left", padx=4)
        self._tool_action(sec, "0 · Pfarrei-Katalog (einmalig)", "mat_cat",
                          lambda: [sys.executable, "-u", _tool("scrape_matricula_osnabrueck.py")])
        self._tool_action(sec, "1 · Bücherverzeichnis holen", "mat_books",
                          self._tl_cmd_mat_books)
        self._tool_action(sec, "2 · Seiten scannen (Claude Vision)", "mat_scan",
                          self._tl_cmd_mat_scan)

        # ── Abschnitt C: MyHeritage ───────────────────────────────────────
        sec = self._tool_section(inner, "🧬  MyHeritage-DNA")
        self._tool_action(sec, "1 · Matchliste herunterladen", "mh_dl",
                          lambda: [sys.executable, "-u", _tool("download_myheritage.py")])
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Match-CSV:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_mh_csv, width=26).pack(side="left", padx=4)
        ttk.Button(row, text="…", width=3,
                   command=lambda: self._tl_pick(self._tl_mh_csv, "CSV", "*.csv")
                   ).pack(side="left")
        # cM-Schwelle + unvollständige nachholen
        opt = ttk.Frame(sec); opt.pack(fill="x", pady=2)
        ttk.Label(opt, text="ab cM:").pack(side="left")
        ttk.Spinbox(opt, from_=6, to=200, increment=5, width=5,
                    textvariable=self._tl_mh_mincm).pack(side="left", padx=(2, 10))
        ttk.Checkbutton(opt, text="unvollständige (<10) nachholen",
                        variable=self._tl_mh_repair).pack(side="left")
        self._tool_action(sec, "2 · Gemeinsame Matches laden", "mh_shared",
                          self._tl_cmd_mh_shared)

        # ── Abschnitt D: Importe ──────────────────────────────────────────
        sec = self._tool_section(inner, "📥  Weitere Importe")
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="MH-CSV:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_imp_mh, width=24).pack(side="left", padx=4)
        ttk.Button(row, text="…", width=3,
                   command=lambda: self._tl_pick(self._tl_imp_mh, "CSV", "*.csv")
                   ).pack(side="left")
        self._tool_action(sec, "MyHeritage-CSV → DB", "imp_mh",
                          lambda: [sys.executable, "-u", _tool("import_mh_csv.py")]
                          + self._arg(self._tl_imp_mh))
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="GEDmatch:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_imp_gm, width=24).pack(side="left", padx=4)
        ttk.Button(row, text="…", width=3,
                   command=lambda: self._tl_pick(self._tl_imp_gm, "TSV/CSV", "*.*")
                   ).pack(side="left")
        self._tool_action(sec, "GEDmatch-TSV → DB", "imp_gm",
                          lambda: [sys.executable, "-u", _tool("import_gedmatch.py")]
                          + self._arg(self._tl_imp_gm))
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="WikiTree-ID:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_wk_id, width=18).pack(side="left", padx=4)
        self._tool_action(sec, "WikiTree → DB", "imp_wk",
                          self._tl_cmd_wikitree)

        # ── Abschnitt E: Extras / Viewer ──────────────────────────────────
        sec = self._tool_section(inner, "🧰  Extras")
        self._tool_action(sec, "GEDCOM verkleinern (GED Slim)", "ged_slim",
                          None, gui=_tool("ged_slim.py"))
        self._tool_action(sec, "Matricula-Web-Viewer (Port 5000)", "mat_viewer",
                          lambda: [sys.executable, "-u", _tool("matricula_viewer.py")])
        self._tool_action(sec, "Entity-Browser (Port 5001)", "entity",
                          lambda: [sys.executable, "-u", _tool("entity_browser.py")])
        self._tool_action(sec, "📦 Korpus für LLM bündeln (OCR+GEDCOM+Belege)", "llm_bundle",
                          lambda: [sys.executable, "-u", "-m",
                                   "ancestry.tools.bundle_for_llm"])

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
                     build_cmd, gui: str | None = None):
        """Eine Tool-Zeile: Beschriftung + ▶ Start + ■ Stop."""
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=34, anchor="w").pack(side="left")
        if gui:
            ttk.Button(row, text="▶ Öffnen",
                       command=lambda g=gui: self._tool_launch_gui(g)
                       ).pack(side="left", padx=2)
            return
        btn_stop = ttk.Button(row, text="■", width=3, state="disabled")
        btn_start = ttk.Button(row, text="▶ Start")
        btn_start.configure(command=lambda: self._tool_run(
            key, build_cmd(), btn_start, btn_stop))
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

    # ── Befehlszeilen ─────────────────────────────────────────────────────
    def _tl_cmd_wt_crawl(self) -> list[str]:
        cmd = [sys.executable, "-u", _tool("crawl_webtrees.py"), "crawl",
               "--profile", self._tl_wt_profile.get().strip() or "anverwandte"]
        if self._tl_wt_discover.get():
            cmd.append("--discover")
        return cmd

    def _tl_cmd_wt_export(self) -> list[str]:
        profile = self._tl_wt_profile.get().strip() or "anverwandte"
        out = filedialog.asksaveasfilename(
            title="GEDCOM speichern unter", defaultextension=".ged",
            initialfile=f"{profile}.ged",
            filetypes=[("GEDCOM", "*.ged"), ("Alle Dateien", "*.*")])
        if not out:
            return []
        return [sys.executable, "-u", _tool("crawl_webtrees.py"),
                "export-gedcom", "--profile", profile, "--out", out]

    def _tl_cmd_mat_books(self) -> list[str]:
        cmd = [sys.executable, "-u", _tool("fetch_matricula_books.py")]
        p = self._tl_mat_parish.get().strip()
        if p:
            cmd += ["--parish", p]
        return cmd

    def _tl_cmd_mat_scan(self) -> list[str]:
        cmd = [sys.executable, "-u", _tool("scan_matricula_kirchspiel.py")]
        p = self._tl_mat_parish.get().strip()
        if p:
            cmd += ["--parish", p]
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
                  btn_start: ttk.Button, btn_stop: ttk.Button):
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
