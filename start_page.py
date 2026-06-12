# -*- coding: utf-8 -*-
"""
start_page.py — Zentrale Startseite der Genealogie-Suite.

Zeigt und verwaltet alle Pfad-Einstellungen:
  • GEDCOM-Datei + Root-ID   (für beide Tools)
  • Ancestry CSV             (optional, für DNA-Match-Analyzer)
  • MyHeritage CSV           (optional)
  • GEDmatch TSV             (optional)
  • Datenbank-Status         (ancestry_dna.db + Matricula)
  • Erklärungen: Woher kommen die Dateien? (Cookie Editor, Genealogy Assistant …)

Wird von unified.py als erster Reiter eingebettet.
Kommuniziert per Callbacks: on_gedcom_change(path, root_id)
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

import importlib as _il
import sys as _sys
# Immer Root-config laden, unabhängig von sys.path-Reihenfolge.
# WICHTIG: kein importlib.util-Fallback — cfg muss dasselbe Objekt wie
# tasks._runner.cfg sein, damit DEFAULT_CONFIG-Änderungen propagiert werden.
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_cached = _sys.modules.get("config")
if _cached is None or not hasattr(_cached, "FONT_HEAD"):
    _sys.modules.pop("config", None)
    if _ROOT_DIR not in _sys.path:
        _sys.path.insert(0, _ROOT_DIR)
import config as cfg

# Pfade (relativ zur Repo-Wurzel)
_ROOT        = os.path.dirname(os.path.abspath(__file__))
_ANCESTRY_DB = os.path.join(_ROOT, "ancestry", "ancestry_dna.db")
_PARISH_JSON = os.path.join(_ROOT, "ancestry", "tools", "matricula_parishes.json")


# ── Farben — direkt hardcoded (config-Swap in unified.py kann ancestry/config laden) ─
P = {
    "bg":     cfg.BG,
    "bg2":    cfg.BG2,
    "bg3":    cfg.BG3,
    "fg":     cfg.FG,
    "dim":    cfg.FG_DIM,
    "acc":    cfg.ACCENT,
    "green":  cfg.GREEN,
    "yellow": cfg.YELLOW,
    "red":    cfg.RED,
    "orange": cfg.ORANGE,
}

# ── Hilfe-Texte (Woher bekomme ich was?) ─────────────────────────────────────
_HELP_TEXTS = {
    "gedfile": (
        "GEDCOM-Datei (.ged oder .ftm)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Woher?\n"
        "• Ancestry: Stammbaum öffnen → Einstellungen → GEDCOM exportieren\n"
        "• Family Tree Maker: Datei → Exportieren → GEDCOM\n"
        "• MacFamilyTree / Gramps: Datei → Exportieren → GEDCOM 5.5\n\n"
        "Format: GEDCOM 5.5 (.ged) oder Family Tree Maker .ftm\n"
        "Empfehlung: Immer aus Family Tree Maker exportieren,\n"
        "da FTM und Ancestry bidirektional synchronisieren.\n\n"
        "Workflow:\n"
        "  1. Änderungen in FTM oder Ancestry vornehmen\n"
        "  2. In FTM: Datei → Export → GEDCOM\n"
        "  3. Hier neu laden → ersetzt Stammbaumdaten,\n"
        "     DNA-Matches bleiben erhalten."
    ),
    "root_id": (
        "Root-Person-ID\n"
        "━━━━━━━━━━━━━━\n"
        "Die Person, von der aus alle Verwandtschaftsgrade\n"
        "berechnet werden (typisch: Sie selbst).\n\n"
        "Format: @I251@ (GEDCOM-interne ID)\n\n"
        "Finden:\n"
        "• In Family Tree Maker: Person rechtsklick → Eigenschaften\n"
        "  → 'Datensatz-ID' (z.B. I251)\n"
        "• Im GEDCOM: 0 @I251@ INDI → die Zahl nach @I\n"
        "• Im Viewer: Person suchen → ID steht in der Detailansicht\n\n"
        "Exclude-ID: Person, die bei der Cousin-Berechnung\n"
        "übersprungen wird (z.B. adoptierter Zweig)."
    ),
    "ancestry_csv": (
        "Ancestry DNA-Matches CSV\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Woher?\n"
        "  ancestry.com → DNA → DNA-Matches\n"
        "  → Oben rechts: Download-Symbol\n"
        "  → 'Alle Matches herunterladen'\n\n"
        "Enthält: Name, cM, Verwandtschaft, Match-GUID,\n"
        "gemeinsame Vorfahren (sofern angegeben)\n\n"
        "Alternative (Ancestry-Login automatisch):\n"
        "  Im DNA-Matches-Tab → Login → Herunterladen\n\n"
        "Tipp: Ancestry-Login über Cookie Editor:\n"
        "  1. Cookie Editor (Chrome/Firefox Extension) installieren\n"
        "  2. Bei ancestry.com eingeloggt sein\n"
        "  3. Cookie Editor → Export → Als JSON speichern\n"
        "  4. Im DNA-Matches-Tab: Methode 2 → Cookie-Datei wählen"
    ),
    "mh_csv": (
        "MyHeritage DNA-Matches CSV\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Woher?\n"
        "  myheritage.de → DNA → DNA-Matches\n"
        "  → Oben rechts: ↓ Download-Symbol\n"
        "  → 'Als CSV herunterladen'\n\n"
        "Dateiname: z.B.\n"
        "  'Andreas Kovermann D-44D71...csv'\n\n"
        "Enthält: Match Name, Shared DNA (cM),\n"
        "Shared Segments, Ancestral Surnames,\n"
        "Locations, Match-URL mit GUID\n\n"
        "Tipp — Genealogy Assistant:\n"
        "  Das Browser-Plugin 'Genealogy Assistant' fügt\n"
        "  auf den MH-Match-Seiten zusätzliche Buttons\n"
        "  hinzu (z.B. Download CSV für Shared Matches).\n"
        "  Für den Scraper (fetch_mh_shared_matches.py)\n"
        "  wird dieser Button NICHT benötigt — der Scraper\n"
        "  nutzt die native MH-API."
    ),
    "gedmatch_tsv": (
        "GEDmatch Matches TSV\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Woher?\n"
        "  gedmatch.com → One-to-Many\n"
        "  → Ergebnisse werden angezeigt\n"
        "  → Seite als .tsv/.csv speichern\n\n"
        "Oder: gedmatch.com → Tier 1 Tools\n"
        "  → Automatic Clustering → CSV exportieren\n\n"
        "Alternative (direkter Paste):\n"
        "  ancestry/tools/gedmatch_paste_to_tsv.py\n"
        "  Kopiert den GEDmatch-Output aus dem Browser\n"
        "  und konvertiert ihn in ein TSV.\n\n"
        "Format: Kit-Nr, Name, cM, Segmente,\n"
        "Größtes Segment, Geburtsjahr-Schätzung"
    ),
    "matricula": (
        "Matricula — Kirchenbuch-Pfarrei-Daten\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Was ist das?\n"
        "  data.matricula-online.eu enthält digitalisierte\n"
        "  Kirchenbücher aus dem deutschsprachigen Raum.\n"
        "  Die Pfarrei-Datenbank für das Bistum Osnabrück\n"
        "  umfasst 169 Pfarreien mit Konfession, Gründungs-\n"
        "  datum und Mutterpfarrei-Hierarchie.\n\n"
        "Wozu brauche ich das?\n"
        "  Im DNA-Viewer markiert die Suite:\n"
        "  ✝K = Pfarrei katholisch (blau)\n"
        "  ✝E = Pfarrei evangelisch (grün)\n"
        "  → Filter nach Konfession (Ohio-Kath. vs. Texas-Ev.)\n\n"
        "Laden:\n"
        "  'Matricula laden' → startet den Scraper\n"
        "  (einmaliger Lauf, ~5 Min., benötigt Internet)"
    ),
    "cookie_editor": (
        "Cookie Editor — Browser-Extension\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Warum brauche ich das?\n"
        "  Ancestry und MyHeritage lassen keinen\n"
        "  automatischen Passwort-Login über Skripte zu.\n"
        "  Cookie Editor exportiert die Login-Session\n"
        "  aus dem Browser als JSON-Datei.\n\n"
        "Installation:\n"
        "  Chrome: Extensions → Cookie Editor (Erweiterung)\n"
        "  Firefox: Add-ons → Cookie Editor\n\n"
        "Verwendung:\n"
        "  1. Bei ancestry.com normal einloggen\n"
        "  2. Cookie Editor öffnen (Extension-Icon)\n"
        "  3. 'Export' → 'Export as JSON'\n"
        "  4. Datei speichern (z.B. ancestry_cookies.json)\n"
        "  5. Im DNA-Matches-Tab: Login → Methode 2 →\n"
        "     Cookie-Datei auswählen\n\n"
        "Gilt auch für MH:\n"
        "  ancestry/tools/fetch_mh_shared_matches.py\n"
        "  --profile-dir für dauerhaften Chromium-Login"
    ),
}


# ── DB-Statistiken ─────────────────────────────────────────────────────────────

def _db_stats() -> dict:
    stats = {"matches": 0, "shared": 0, "gedcom": 0, "kits": 0, "db_size": ""}
    if not os.path.exists(_ANCESTRY_DB):
        return stats
    try:
        sz = os.path.getsize(_ANCESTRY_DB)
        stats["db_size"] = f"{sz / 1_048_576:.1f} MB"
        con = sqlite3.connect(_ANCESTRY_DB, timeout=3)
        for tbl, key in [
            ("dna_matches",    "matches"),
            ("shared_matches", "shared"),
            ("gedcom_persons", "gedcom"),
            ("dna_kits",       "kits"),
        ]:
            try:
                stats[key] = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            except Exception:
                pass
        con.close()
    except Exception:
        pass
    return stats


def _parish_count() -> int:
    if not os.path.exists(_PARISH_JSON):
        return 0
    try:
        import json
        with open(_PARISH_JSON, encoding="utf-8") as f:
            return len(json.load(f))
    except Exception:
        return 0


# ── Hilfe-Popup ───────────────────────────────────────────────────────────────

def _show_help_popup(parent: tk.Widget, key: str, title: str):
    """Öffnet ein kleines Info-Fenster mit dem Hilfetext."""
    text = _HELP_TEXTS.get(key, "Kein Hilfetext verfügbar.")
    win = tk.Toplevel(parent)
    win.title(f"ⓘ  {title}")
    win.configure(bg=P["bg2"])
    win.resizable(False, False)
    win.grab_set()
    tk.Label(win, text=text, bg=P["bg2"], fg=P["fg"],
             font=cfg.FONT_MAIN, justify="left",
             wraplength=420, padx=20, pady=16).pack()
    tk.Button(win, text="Schließen", bg=P["bg3"], fg=P["dim"],
              font=cfg.FONT_MAIN, relief="flat", padx=10,
              command=win.destroy).pack(pady=(0, 12))
    win.bind("<Escape>", lambda _e: win.destroy())
    # Fenster nahe dem auslösenden Widget positionieren
    try:
        x = parent.winfo_rootx() + parent.winfo_width() + 8
        y = parent.winfo_rooty()
        win.geometry(f"+{x}+{y}")
    except Exception:
        pass


class StartPage(tk.Frame):
    """
    Zentrale Startseite der Genealogie-Suite.

    on_gedcom_change  Callable(gedcom_path: str, root_id: str)
    """

    def __init__(self, master=None, on_gedcom_change=None):
        self._embedded = master is not None
        if master is None:
            master = tk.Tk()
        super().__init__(master, bg=P["bg"])
        root = self.winfo_toplevel()
        if not self._embedded:
            root.title("Genealogie-Suite — Start")
            root.geometry("1180x760")
            root.configure(bg=P["bg"])
        self.pack(fill="both", expand=True)

        self._on_gedcom_change = on_gedcom_change
        self._vars: dict[str, tk.StringVar] = {}
        self._build()
        self.after(200, self._refresh_status)

    # ── UI-Aufbau ──────────────────────────────────────────────────────────────

    def _build(self):
        # Titelzeile
        hdr = tk.Frame(self, bg=P["bg2"], pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🏠  Genealogie-Suite — Einstellungen & Start",
                 bg=P["bg2"], fg=P["acc"], font=cfg.FONT_HEAD).pack(side="left", padx=14)
        self._status_lbl = tk.Label(hdr, text="", bg=P["bg2"],
                                     fg=P["dim"], font=("Segoe UI", 8))
        self._status_lbl.pack(side="right", padx=12)

        # Hauptbereich: linke Spalte (Felder) + rechte Spalte (Info)
        body = tk.Frame(self, bg=P["bg"])
        body.pack(fill="both", expand=True, padx=10, pady=6)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left  = tk.Frame(body, bg=P["bg"])
        right = tk.Frame(body, bg=P["bg"])
        left .grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=0, column=1, sticky="nsew")

        self._build_left(left)
        self._build_right(right)

        # Protokoll
        lf = tk.Frame(self, bg=P["bg2"])
        lf.pack(fill="x", padx=10, pady=(0, 6))
        tk.Label(lf, text="Protokoll", bg=P["bg2"], fg=P["dim"],
                 font=("Segoe UI", 8)).pack(anchor="w", padx=6, pady=(4, 0))
        self._log = scrolledtext.ScrolledText(
            lf, bg="#13131f", fg=P["fg"], font=cfg.FONT_MONO,
            state="disabled", relief="flat", height=5)
        self._log.pack(fill="x", padx=4, pady=(0, 4))
        for tag, col in [("ok", P["green"]), ("err", P["red"]),
                          ("warn", P["yellow"]), ("info", P["acc"])]:
            self._log.tag_configure(tag, foreground=col)

    def _build_left(self, parent):
        # ── GEDCOM ──────────────────────────────────────────────────────────
        self._section(parent, "📄  GEDCOM — Stammbaumdatei  (wird von BEIDEN Werkzeugen benötigt)")
        box = tk.Frame(parent, bg=P["bg2"], padx=10, pady=8)
        box.pack(fill="x", pady=(0, 8))

        # Datei-Zeile
        r0 = tk.Frame(box, bg=P["bg2"])
        r0.pack(fill="x", pady=2)
        self._lbl(r0, "Stammbaumdatei:", 18)
        v = self._var("gedfile", cfg.DEFAULT_CONFIG.get("gedfile", ""))
        tk.Entry(r0, textvariable=v, bg=P["bg3"], fg=P["fg"],
                 font=cfg.FONT_MONO, relief="flat", width=44).pack(side="left", padx=4)
        tk.Button(r0, text="…", bg=P["bg3"], fg=P["fg"],
                  font=cfg.FONT_MAIN, relief="flat", padx=6,
                  command=self._browse_gedcom).pack(side="left")
        self._help_btn(r0, "gedfile", "GEDCOM-Format / Woher?")

        # Zuletzt
        r1 = tk.Frame(box, bg=P["bg2"])
        r1.pack(fill="x", pady=2)
        self._lbl(r1, "Zuletzt:", 18, small=True)
        self._recent_var = tk.StringVar(value="")
        self._recent_cb = ttk.Combobox(r1, textvariable=self._recent_var,
                                        state="readonly", width=43,
                                        font=("Segoe UI", 8))
        self._recent_cb.pack(side="left", padx=4)
        self._recent_cb.bind("<<ComboboxSelected>>", self._on_recent_select)
        self._refresh_recent()

        # Root-ID / Exclude-ID
        r2 = tk.Frame(box, bg=P["bg2"])
        r2.pack(fill="x", pady=2)
        self._lbl(r2, "Root-ID:", 18)
        self._var("root_id", cfg.DEFAULT_CONFIG.get("root_id", ""))
        tk.Entry(r2, textvariable=self._vars["root_id"], bg=P["bg3"], fg=P["fg"],
                 font=cfg.FONT_MONO, relief="flat", width=14).pack(side="left", padx=4)
        self._help_btn(r2, "root_id", "Was ist die Root-ID?")
        self._lbl(r2, "Exclude-ID:", 0, pad_l=14)
        self._var("exclude_id", cfg.DEFAULT_CONFIG.get("exclude_id", ""))
        tk.Entry(r2, textvariable=self._vars["exclude_id"], bg=P["bg3"], fg=P["fg"],
                 font=cfg.FONT_MONO, relief="flat", width=14).pack(side="left", padx=4)

        # Buttons
        br = tk.Frame(box, bg=P["bg2"])
        br.pack(fill="x", pady=(8, 0))
        self._btn_load_ged = tk.Button(
            br, text="▶ GEDCOM laden & analysieren",
            bg=P["acc"], fg="#fff", font=cfg.FONT_HEAD, relief="flat", padx=12,
            command=self._load_gedcom)
        self._btn_load_ged.pack(side="left")
        tk.Button(br, text="↺ Pfad merken  (kein Reload)",
                  bg=P["bg3"], fg=P["dim"], font=cfg.FONT_MAIN, relief="flat", padx=8,
                  command=self._apply_paths).pack(side="left", padx=8)

        # DNA-Quellen-CSV-Import wurde in den Werkzeuge-Tab verschoben
        # (Ancestry/MyHeritage/GEDmatch). Hier nur noch GEDCOM + Pfade + Login.

    def _build_right(self, parent):
        # ── Datenbank-Status ─────────────────────────────────────────────────
        self._section(parent, "📊  Datenbank-Status")
        sb = tk.Frame(parent, bg=P["bg2"], padx=10, pady=8)
        sb.pack(fill="x", pady=(0, 8))

        self._stat_labels: dict[str, tk.Label] = {}
        for key, text in [
            ("db_size",  "ancestry_dna.db:"),
            ("kits",     "DNA-Kits:"),
            ("matches",  "Matches:"),
            ("shared",   "Shared Matches:"),
            ("gedcom",   "GEDCOM-Personen:"),
            ("parishes", "Matricula-Orte:"),
        ]:
            row = tk.Frame(sb, bg=P["bg2"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=text, bg=P["bg2"], fg=P["dim"],
                     font=cfg.FONT_MONO, width=20, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="—", bg=P["bg2"], fg=P["fg"],
                            font=cfg.FONT_MONO, anchor="w")
            lbl.pack(side="left")
            self._stat_labels[key] = lbl

        tk.Button(sb, text="↺ Aktualisieren",
                  bg=P["bg3"], fg=P["dim"], font=cfg.FONT_MAIN, relief="flat",
                  command=self._refresh_status).pack(anchor="w", pady=(6, 0))

        # ── Tools / Schnellzugriff ────────────────────────────────────────────
        self._section(parent, "🔧  Tools & Schnellzugriff")
        tb = tk.Frame(parent, bg=P["bg2"], padx=10, pady=8)
        tb.pack(fill="x", pady=(0, 8))

        for txt, bg, cmd, hkey, htitle in [
            ("🏘 Matricula laden",   "#5d4037", self._run_matricula,
             "matricula",    "Matricula — Kirchenbuch-Pfarreien"),
            ("① Erste Schritte",     P["bg3"],  self._open_welcome,
             None, None),
            ("? Hilfe",              P["bg3"],  self._open_help,
             None, None),
        ]:
            row = tk.Frame(tb, bg=P["bg2"])
            row.pack(fill="x", pady=2)
            tk.Button(row, text=txt, bg=bg,
                      fg="#fff" if bg not in (P["bg3"], P["bg2"]) else P["acc"],
                      font=cfg.FONT_MAIN, relief="flat", padx=8, anchor="w",
                      width=22, command=cmd).pack(side="left")
            if hkey:
                self._help_btn(row, hkey, htitle)

        # ── Kurzübersicht Pfade ───────────────────────────────────────────────
        self._section(parent, "📁  Verzeichnisse")
        pb = tk.Frame(parent, bg=P["bg2"], padx=10, pady=6)
        pb.pack(fill="x")
        for label, path in [
            ("Ausgabe:",      cfg.DIRS.get("output", "")),
            ("Protokolle:",   cfg.DIRS.get("logs",   "")),
            ("DNA-Datenbank:", _ANCESTRY_DB),
            ("Matricula-JSON:", _PARISH_JSON),
        ]:
            row = tk.Frame(pb, bg=P["bg2"])
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, bg=P["bg2"], fg=P["dim"],
                     font=("Segoe UI", 8), width=16, anchor="w").pack(side="left")
            exists = os.path.exists(path)
            color  = P["fg"] if exists else P["red"]
            short  = os.path.basename(path) if path else "—"
            tk.Label(row, text=short, bg=P["bg2"], fg=color,
                     font=("Segoe UI", 8), anchor="w").pack(side="left")
            if not exists:
                tk.Label(row, text="⚠ fehlt", bg=P["bg2"], fg=P["yellow"],
                         font=("Segoe UI", 8)).pack(side="left", padx=4)

    # ── Widget-Helfer ─────────────────────────────────────────────────────────

    def _section(self, parent, title: str):
        tk.Label(parent, text=title, bg=P["bg"], fg=P["acc"],
                 font=cfg.FONT_HEAD, anchor="w").pack(fill="x", pady=(10, 2))

    def _lbl(self, parent, text, width=0, small=False, pad_l=0):
        kw = {"bg": P["bg2"], "fg": P["dim"], "anchor": "w"}
        if width:
            kw["width"] = width
        if small:
            kw["font"] = ("Segoe UI", 8)
        else:
            kw["font"] = cfg.FONT_MONO
        if pad_l:
            tk.Label(parent, text=text, **kw).pack(side="left", padx=(pad_l, 0))
        else:
            tk.Label(parent, text=text, **kw).pack(side="left")

    def _help_btn(self, parent, key: str, title: str):
        """Kleines ⓘ-Button, das ein Hilfe-Popup öffnet."""
        btn = tk.Button(parent, text="ⓘ", bg=P["bg2"], fg=P["dim"],
                        font=("Segoe UI", 9), relief="flat", padx=4, bd=0,
                        cursor="question_arrow")
        btn.configure(command=lambda: _show_help_popup(btn, key, title))
        btn.pack(side="left", padx=2)

    def _var(self, key: str, default: str = "") -> tk.StringVar:
        if key not in self._vars:
            self._vars[key] = tk.StringVar(value=default)
        return self._vars[key]

    def _log_msg(self, msg: str, tag: str = ""):
        def _do():
            self._log.configure(state="normal")
            ts = time.strftime("%H:%M:%S")
            self._log.insert("end", f"[{ts}] {msg}\n", tag or "")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    # ── Datei-Auswahl ──────────────────────────────────────────────────────────

    def _refresh_recent(self):
        self._recent_cb["values"] = cfg.get_recent_files()

    def _on_recent_select(self, _e=None):
        val = self._recent_var.get()
        if val:
            self._vars["gedfile"].set(val)
            self._recent_var.set("")
            self._notify_gedcom_change()

    def _browse_gedcom(self):
        cur  = self._vars["gedfile"].get()
        idir = os.path.dirname(cur) if cur else ""
        path = filedialog.askopenfilename(
            title="Stammbaumdatei wählen", initialdir=idir or None,
            filetypes=[
                ("Alle unterstützten Formate", "*.ged *.GED *.ftm *.FTM *.ftmb"),
                ("GEDCOM", "*.ged *.GED"),
                ("Family Tree Maker", "*.ftm *.ftmb"),
                ("Alle Dateien", "*.*"),
            ])
        if path:
            self._vars["gedfile"].set(path)
            self._notify_gedcom_change()

    # ── Synchronisation ───────────────────────────────────────────────────────

    def _notify_gedcom_change(self):
        if self._on_gedcom_change:
            try:
                self._on_gedcom_change(
                    self._vars["gedfile"].get(),
                    self._vars["root_id"].get(),
                )
            except Exception:
                pass

    def _apply_paths(self):
        ged = self._vars["gedfile"].get().strip()
        rid = self._vars["root_id"].get().strip()
        eid = self._vars["exclude_id"].get().strip()
        cfg.DEFAULT_CONFIG["gedfile"]    = ged
        cfg.FILES["gedfile"]             = ged
        cfg.DEFAULT_CONFIG["root_id"]    = rid
        cfg.ROOT_ID                      = rid
        cfg.DEFAULT_CONFIG["exclude_id"] = eid
        cfg.EXCLUDE_ID                   = eid
        save = {"gedfile": ged, "root_id": rid, "exclude_id": eid}
        cfg.save_overrides(save)
        self._refresh_recent()
        self._notify_gedcom_change()
        self._log_msg("Pfade gespeichert.", tag="ok")

    # ── Aktionen ──────────────────────────────────────────────────────────────

    def _load_gedcom(self):
        self._apply_paths()
        ged = self._vars["gedfile"].get().strip()
        if not ged or not os.path.exists(ged):
            self._log_msg(f"Datei nicht gefunden: {ged}", tag="err")
            return
        self._btn_load_ged.configure(state="disabled", text="… läuft")
        self._log_msg(f"Lade GEDCOM: {os.path.basename(ged)} …", tag="info")

        def _run():
            try:
                import importlib
                runner = importlib.import_module("tasks._runner")
                runner.load_gedcom(progress_cb=lambda m, **k:
                                   self._log_msg(m, tag=k.get("tag", "")))
                self._log_msg("GEDCOM erfolgreich geladen.", tag="ok")
                self.after(0, self._refresh_status)
            except Exception as exc:
                self._log_msg(f"Fehler: {exc}", tag="err")
            finally:
                self.after(0, lambda: self._btn_load_ged.configure(
                    state="normal", text="▶ GEDCOM laden & analysieren"))

        threading.Thread(target=_run, daemon=True).start()

    def _refresh_status(self):
        stats = _db_stats()
        pc    = _parish_count()
        self._stat_labels["db_size"] .configure(
            text=stats["db_size"] or "— (nicht angelegt)")
        self._stat_labels["kits"]    .configure(text=str(stats["kits"]))
        self._stat_labels["matches"] .configure(text=f"{stats['matches']:,}")
        self._stat_labels["shared"]  .configure(text=f"{stats['shared']:,}")
        self._stat_labels["gedcom"]  .configure(text=f"{stats['gedcom']:,}")
        self._stat_labels["parishes"].configure(
            text=f"{pc} Orte" if pc else "—  (Matricula-Scraper noch nicht gelaufen)")
        self._status_lbl.configure(text=f"Stand: {time.strftime('%H:%M:%S')}")

    def _run_matricula(self):
        self._log_msg("Starte Matricula-Scraper (benötigt Internet) …", tag="info")

        def _run():
            import subprocess
            import sys as _sys
            script = os.path.join(_ROOT, "ancestry", "tools",
                                  "scrape_matricula_osnabrueck.py")
            proc = subprocess.Popen(
                [_sys.executable, script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                self._log_msg(line.rstrip())
            rc = proc.wait()
            self._log_msg(
                f"Matricula-Scraper beendet (Code {rc}).",
                tag="ok" if rc == 0 else "err")
            self.after(0, self._refresh_status)

        threading.Thread(target=_run, daemon=True).start()

    def _open_welcome(self):
        # Im eingebetteten Modus: AhnenApp aus dem Geschwister-Tab suchen
        for widget in self.winfo_toplevel().winfo_children():
            if hasattr(widget, "_open_welcome"):
                widget._open_welcome(); return
        from tkinter import messagebox
        messagebox.showinfo("Erste Schritte",
                            "Starten Sie die Suite über unified.py.")

    def _open_help(self):
        for widget in self.winfo_toplevel().winfo_children():
            if hasattr(widget, "_open_help"):
                widget._open_help(); return

    # ── API für unified.py ────────────────────────────────────────────────────

    def get_gedcom_path(self) -> str:
        return self._vars.get("gedfile", tk.StringVar()).get()

    def get_root_id(self) -> str:
        return self._vars.get("root_id", tk.StringVar()).get()

    def mainloop(self, *a, **k):
        self.winfo_toplevel().mainloop(*a, **k)


if __name__ == "__main__":
    page = StartPage()
    page.mainloop()
