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

        # ── Abschnitt A: Webtrees ─────────────────────────────────────────
        sec = self._tool_section(inner, "⬇  Webtrees-Stammbaum")
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Profil:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_wt_profile, width=16).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="--discover (ganzer Baum)",
                        variable=self._tl_wt_discover).pack(side="left")
        self._tool_action(sec, "Öffentlichen Baum crawlen", "wt_crawl",
                          self._tl_cmd_wt_crawl)
        ttk.Button(sec, text="🗑 DB löschen",
                   command=self._wt_delete_db).pack(anchor="w", pady=(0, 2))
        self._tool_action(sec, "Crawl → Datenbank importieren", "wt_import",
                          lambda: [sys.executable, "-u", _tool("import_webtrees.py")])
        self._tool_action(sec, "💾 Als GEDCOM-Datei exportieren", "wt_export",
                          self._tl_cmd_wt_export)
        # Testlauf: echte Seiten als HTML+JSON sichern (Roh-Daten zum Eichen
        # des Parsers — Ordner zippen und zurückgeben). Schreibt nicht in die DB.
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Seiten:").pack(side="left")
        ttk.Spinbox(row, from_=10, to=1000, increment=10, width=6,
                    textvariable=self._tl_wt_trainn).pack(side="left", padx=(4, 8))
        ttk.Label(row, text="HTML+JSON lokal in tools/webtrees_training/",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left")
        self._tool_action(sec, "🧪 Testlauf: Seiten lokal sichern", "wt_training",
                          self._tl_cmd_wt_training)

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
        ttk.Checkbutton(row2, text="nur Bilder laden, kein OCR (--dry-run)",
                        variable=self._tl_mat_dryrun).pack(side="left")
        self._tool_action(sec, "2 · Seiten scannen (Claude Vision)", "mat_scan",
                          self._tl_cmd_mat_scan,
                          on_start=self._mat_reset_progress,
                          on_line=self._mat_on_line)
        self._tool_action(sec, "🔁 Re-Transkription (lokale Bilder)", "mat_retranscribe",
                          self._tl_cmd_mat_retranscribe,
                          on_start=self._mat_reset_progress,
                          on_line=self._mat_on_line)
        # Fortschrittsanzeige
        prog_row = ttk.Frame(sec); prog_row.pack(fill="x", pady=(4, 0))
        self._mat_prog_label = ttk.Label(prog_row, text="", width=12, anchor="e")
        self._mat_prog_label.pack(side="left")
        self._mat_prog_bar = ttk.Progressbar(prog_row, mode="determinate", length=200)
        self._mat_prog_bar.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._tool_action(sec, "🌐 Matricula-Viewer öffnen (Port 5000)", "mat_viewer",
                          lambda: [sys.executable, "-u", _tool("matricula_viewer.py")])

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
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Match-CSV:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_match_csv, width=24).pack(side="left", padx=4)
        ttk.Button(row, text="…", width=3,
                   command=lambda: self._tl_pick(self._tl_match_csv, "CSV", "*.csv")
                   ).pack(side="left")
        ttk.Button(sec, text="🔗 Anverwandte-Matches importieren",
                   command=self._import_match_csv).pack(anchor="w", pady=(2, 0))

        # ── Abschnitt E: Extras / Viewer ──────────────────────────────────
        sec = self._tool_section(inner, "🧰  Extras")
        self._tool_action(sec, "GEDCOM verkleinern (GED Slim)", "ged_slim",
                          None, gui=_tool("ged_slim.py"))
        self._tool_action(sec, "Matricula-Web-Viewer (Port 5000)", "mat_viewer",
                          lambda: [sys.executable, "-u", _tool("matricula_viewer.py")],
                          on_start=lambda: self.after(2500, lambda: webbrowser.open("http://localhost:5000")))
        self._tool_action(sec, "Entity-Browser (Port 5001)", "entity",
                          lambda: [sys.executable, "-u", _tool("entity_browser.py")])
        self._tool_action(sec, "📦 Korpus für LLM bündeln (OCR+GEDCOM+Belege)", "llm_bundle",
                          lambda: [sys.executable, "-u", "-m",
                                   "ancestry.tools.bundle_for_llm"])

        # ── Abschnitt F: Ortskonkordanz (Anverwandte → Standardorte) ──────────
        sec = self._tool_section(inner, "🗺  Ortskonkordanz")
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Button(row, text="✏ Orte bearbeiten",
                   command=self._open_place_editor).pack(side="left", padx=(0, 8))
        ttk.Label(row, text="Rohorte anzeigen, automatische Normalisierung prüfen "
                             "und manuelle Überschreibungen setzen.",
                  foreground=self._state.colors().get("text_dim", "#888888")
                  ).pack(side="left")
        self._tool_action(sec, "📤 Anverwandte-Orte exportieren (für KI)", "conc_exp",
                          lambda: [sys.executable, "-u", "-m",
                                   "ancestry.core.place_concordance", "--export"])
        row = ttk.Frame(sec); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Mapping-Datei:").pack(side="left")
        ttk.Entry(row, textvariable=self._tl_conc, width=24).pack(side="left", padx=4)
        ttk.Button(row, text="…", width=3,
                   command=lambda: self._tl_pick(self._tl_conc, "JSON/CSV", "*.json *.csv")
                   ).pack(side="left")
        self._tool_action(sec, "📥 Ortskonkordanz importieren", "conc_imp",
                          self._tl_cmd_conc_import)

    # ── Match-CSV importieren ─────────────────────────────────────────────
    def _import_match_csv(self):
        import threading
        from tkinter import messagebox
        csv_path = self._tl_match_csv.get().strip()
        if not csv_path:
            messagebox.showinfo("Match-Import", "Bitte zuerst eine CSV-Datei auswählen.",
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
            item = self._mat_listbox.get(i).strip().lstrip("✓◐○ ")
            slug = item.split()[0]
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
        """Lädt Pfarrei-Liste mit Scan-Status aus DB in die Listbox."""
        try:
            import sqlite3
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

            self._mat_listbox.delete(0, "end")
            for parish_id, total, done in rows:
                slug = parish_id.split("/")[-1]
                if total and total > 0:
                    pct = int(done * 100 / total)
                    if pct >= 100:
                        label = f"✓ {slug}  ({done}/{total})"
                    elif done > 0:
                        label = f"◐ {slug}  ({done}/{total})"
                    else:
                        label = f"○ {slug}"
                else:
                    label = f"○ {slug}"
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

    # ── Ortskonkordanz-Editor ─────────────────────────────────────────────
    def _open_place_editor(self):
        from pathlib import Path
        from ancestry.tools.crawl_webtrees import SCRIPT_DIR
        from ancestry.gui.analysis.place_editor import PlaceEditorDialog
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
            ttk.Button(row, text="▶ Öffnen",
                       command=lambda g=gui: self._tool_launch_gui(g)
                       ).pack(side="left", padx=2)
            return
        btn_stop = ttk.Button(row, text="■", width=3, state="disabled")
        btn_start = ttk.Button(row, text="▶ Start")
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
            messagebox.showinfo("DB löschen", "Keine Crawl-Datenbank gefunden.", parent=self)
            return
        names = "\n".join(str(p.name) for p in found)
        if not messagebox.askyesno(
                "DB löschen",
                f"Folgende Datei(en) unwiderruflich löschen?\n\n{names}",
                icon="warning", parent=self):
            return
        for p in found:
            try:
                p.unlink()
            except OSError as exc:
                messagebox.showerror("Fehler", f"{p.name}: {exc}", parent=self)
                return
        messagebox.showinfo("DB löschen", f"Gelöscht:\n{names}", parent=self)

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
                                   "Bitte mindestens eine Pfarrei auswählen.",
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
                                   "Bitte mindestens eine Pfarrei auswählen.",
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
                                   "Bitte mindestens eine Pfarrei auswählen.",
                                   parent=self)
            return []
        cmd = [sys.executable, "-u", _tool("scan_matricula_kirchspiel.py"),
               "--retranscribe", "--parish"] + parishes
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
