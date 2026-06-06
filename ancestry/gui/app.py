"""
Ancestry DNA Tool – Hauptfenster (Tkinter).

Tabs:
  1. Login         – Einloggen per Passwort oder Cookie-Datei
  2. Herunterladen – Matches + Shared Matches
  3. Matches       – Tabellenansicht; Shared-Match-Panel pro Match
  4. Cluster       – Leeds-Clustering-Ansicht
  5. Statistiken   – Kennzahlen
"""

import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import config as cfg
from core.auth import AncestryAuth
from core.api import AncestryApiClient
from core.database import Database
from core.scraper import Scraper, DownloadResult
from core.export import export_csv, export_shared_csv, export_xlsx
from core.cluster import build_clusters, suggest_grandparent_lines
from models import DnaKit, DnaMatch, SharedMatch

log = logging.getLogger(__name__)

COLORS = {
    "primary" : "#1F4E79",
    "accent"  : "#2E75B6",
    "light"   : "#D6E4F0",
    "bg"      : "#F0F4F8",
    "text"    : "#1A1A2E",
    "success" : "#217A3C",
    "warning" : "#C85000",
    "white"   : "#FFFFFF",
    "cluster" : ["#FFD6D6","#D6F5E3","#D6E4FF","#FFF3CD","#F0D6FF","#D6F0FF"],
}


class AncestryDnaApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Ancestry DNA Tool")
        self.geometry("1200x760")
        self.minsize(960, 620)
        self.configure(bg=COLORS["bg"])

        self._auth    : Optional[AncestryAuth]      = None
        self._client  : Optional[AncestryApiClient] = None
        self._scraper : Optional[Scraper]           = None
        self._db      : Database                    = Database(cfg.DB_FILE)
        self._kit_map : dict[str, str]              = {}
        self._matches : list[DnaMatch]              = []
        self._current_test_guid : Optional[str]     = None

        self._build_style()
        self._build_menu()
        self._build_main()
        self._refresh_match_table()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._load_settings)

    # ── Styling ───────────────────────────────────────────────────────────────

    def _build_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook",         background=COLORS["bg"])
        s.configure("TNotebook.Tab",     padding=[14, 6],
                    background=COLORS["light"], foreground=COLORS["text"],
                    font=("Segoe UI", 10))
        s.map("TNotebook.Tab",
              background=[("selected", COLORS["primary"])],
              foreground=[("selected", COLORS["white"])])
        s.configure("TFrame",            background=COLORS["bg"])
        s.configure("TLabel",            background=COLORS["bg"],
                    foreground=COLORS["text"], font=("Segoe UI", 10))
        s.configure("Header.TLabel",     background=COLORS["primary"],
                    foreground=COLORS["white"], font=("Segoe UI", 13, "bold"), padding=10)
        s.configure("Bold.TLabel",       background=COLORS["bg"],
                    font=("Segoe UI", 10, "bold"))
        s.configure("Success.TLabel",    background=COLORS["bg"],
                    foreground=COLORS["success"], font=("Segoe UI", 10, "bold"))
        s.configure("Warning.TLabel",    background=COLORS["bg"],
                    foreground=COLORS["warning"], font=("Segoe UI", 10, "bold"))
        s.configure("TButton",           font=("Segoe UI", 10), padding=6)
        s.configure("TProgressbar",      troughcolor=COLORS["light"],
                    background=COLORS["accent"])
        s.configure("Treeview",          rowheight=24, font=("Segoe UI", 9))
        s.configure("Treeview.Heading",  font=("Segoe UI", 9, "bold"),
                    background=COLORS["primary"], foreground=COLORS["white"])

    # ── Menü ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self)
        self.configure(menu=mb)

        fm = tk.Menu(mb, tearoff=False)
        fm.add_command(label="Matches als CSV …",           command=self._export_csv)
        fm.add_command(label="Matches als XLSX …",          command=self._export_xlsx)
        fm.add_command(label="Shared Matches als CSV …",    command=self._export_shared_csv)
        fm.add_command(label="Alles als XLSX (2 Blätter)…", command=self._export_all_xlsx)
        fm.add_separator()
        fm.add_command(label="Namen importieren (JSON/CSV) …", command=self._import_names)
        fm.add_separator()
        fm.add_command(label="Beenden", command=self._on_close)
        mb.add_cascade(label="Datei", menu=fm)

        vm = tk.Menu(mb, tearoff=False)
        vm.add_command(label="Tabelle aktualisieren", command=self._refresh_match_table)
        vm.add_command(label="Cluster neu berechnen", command=self._refresh_cluster)
        mb.add_cascade(label="Ansicht", menu=vm)

        am = tk.Menu(mb, tearoff=False)
        am.add_command(label="Gemeinsame Vorfahren (Überlagerung) …",
                       command=self._show_ancestor_groups)
        am.add_command(label="Vorfahren-Gruppen als CSV …",
                       command=self._export_ancestor_groups)
        am.add_separator()
        am.add_command(label="Ahnentafel des Matches anzeigen …",
                       command=self._show_match_pedigree)
        am.add_command(label="Pedigree-Überlagerung (Cluster) …",
                       command=self._show_pedigree_overlay)
        am.add_separator()
        am.add_command(label="Eigenen Baum (GEDCOM) abgleichen …",
                       command=self._match_own_tree)
        am.add_command(label="Shared-Cluster (Triangulation) …",
                       command=self._show_shared_clusters)
        am.add_separator()
        am.add_command(label="Shared Matches zurücksetzen (neu laden) …",
                       command=self._reset_shared_matches)
        am.add_command(label="Namens-Versuche zurücksetzen (alle erneut) …",
                       command=self._reset_name_attempts)
        mb.add_cascade(label="Auswertung", menu=am)

        hm = tk.Menu(mb, tearoff=False)
        hm.add_command(label="Über …", command=self._show_about)
        mb.add_cascade(label="Hilfe", menu=hm)

    # ── Hauptlayout ───────────────────────────────────────────────────────────

    def _build_main(self):
        ttk.Label(self, text="🧬  Ancestry DNA Tool",
                  style="Header.TLabel").pack(fill="x")

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=8, pady=8)

        tabs = [
            ("_tab_login",    "  🔑 Login  "),
            ("_tab_download", "  ⬇ Herunterladen  "),
            ("_tab_matches",  "  🧬 Matches  "),
            ("_tab_cluster",  "  🌳 Cluster  "),
            ("_tab_stats",    "  📊 Statistiken  "),
        ]
        for attr, label in tabs:
            frame = ttk.Frame(self._nb)
            setattr(self, attr, frame)
            self._nb.add(frame, text=label)

        self._build_tab_login()
        self._build_tab_download()
        self._build_tab_matches()
        self._build_tab_cluster()
        self._build_tab_stats()

        self._status_var = tk.StringVar(value="Bereit.")
        ttk.Label(self, textvariable=self._status_var,
                  relief="sunken", anchor="w", padding=(6, 2)).pack(fill="x", side="bottom")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1: LOGIN
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_login(self):
        f = self._tab_login
        p = {"padx": 16, "pady": 8}

        ttk.Label(f, text="Methode 1: Automatischer Login",
                  style="Bold.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", **p)
        ttk.Label(f, text="E-Mail:").grid(row=1, column=0, sticky="e", **p)
        self._email_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._email_var, width=36).grid(row=1, column=1, sticky="w", **p)
        ttk.Label(f, text="Passwort:").grid(row=2, column=0, sticky="e", **p)
        self._pw_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw_var, show="•", width=36).grid(row=2, column=1, sticky="w", **p)
        ttk.Button(f, text="Einloggen", command=self._do_login).grid(row=3, column=1, sticky="w", **p)

        ttk.Separator(f, orient="horizontal").grid(row=4, column=0, columnspan=3,
                                                    sticky="ew", padx=16, pady=12)

        ttk.Label(f, text="Methode 2: Cookie-Datei (empfohlen)",
                  style="Bold.TLabel").grid(row=5, column=0, columnspan=3, sticky="w", **p)
        ttk.Label(f, text=(
            "1. Chrome/Firefox-Extension »Cookie-Editor« installieren\n"
            "2. Auf ancestry.com einloggen\n"
            "3. Cookie-Editor → Export → JSON → speichern\n"
            "4. Datei hier auswählen"
        ), foreground="#555555").grid(row=6, column=0, columnspan=3, sticky="w", padx=16)
        self._cookie_file_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._cookie_file_var, width=36,
                  state="readonly").grid(row=7, column=1, sticky="w", **p)
        ttk.Button(f, text="Datei wählen …",
                   command=self._choose_cookie_file).grid(row=7, column=0, sticky="e", **p)
        ttk.Button(f, text="Mit Cookies einloggen",
                   command=self._do_login_cookies).grid(row=8, column=1, sticky="w", **p)

        ttk.Separator(f, orient="horizontal").grid(row=9, column=0, columnspan=3,
                                                    sticky="ew", padx=16, pady=12)
        ttk.Label(f, text="Manuelle Kit-GUID",
                  style="Bold.TLabel").grid(row=10, column=0, columnspan=3, sticky="w", **p)
        ttk.Label(f, text="URL: ancestry.com/dna/tests/<GUID>/matches",
                  foreground="#555555").grid(row=11, column=0, columnspan=3, sticky="w", padx=16)
        self._manual_guid_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._manual_guid_var, width=44).grid(
            row=12, column=1, sticky="w", **p)
        ttk.Button(f, text="GUID übernehmen",
                   command=self._use_manual_guid).grid(row=12, column=0, sticky="e", **p)

        self._login_status_var = tk.StringVar(value="Nicht eingeloggt.")
        self._login_status_lbl = ttk.Label(f, textvariable=self._login_status_var,
                                           style="Warning.TLabel")
        self._login_status_lbl.grid(row=13, column=0, columnspan=3, **p)
        f.columnconfigure(1, weight=1)

    def _do_login(self):
        e, pw = self._email_var.get().strip(), self._pw_var.get()
        if not e or not pw:
            messagebox.showwarning("Eingabe fehlt", "E-Mail und Passwort eingeben.")
            return
        threading.Thread(target=self._login_thread, args=(e, pw, "password"),
                         daemon=True).start()

    def _do_login_cookies(self):
        path = self._cookie_file_var.get().strip()
        if not path:
            messagebox.showwarning("Keine Datei", "Bitte Cookie-Datei auswählen.")
            return
        threading.Thread(target=self._login_thread, args=(path, None, "cookie"),
                         daemon=True).start()

    def _login_thread(self, arg1, arg2, method):
        auth = AncestryAuth()
        ok = auth.login_password(arg1, arg2) if method == "password" else auth.login_cookies(arg1)
        if ok:
            self._auth = auth
            self._client = AncestryApiClient(auth.get_session())
            self._after_login()
        else:
            self.after(0, lambda: self._set_login_status(
                "❌ Login fehlgeschlagen.", success=False))

    def _after_login(self):
        uid  = self._auth.uid or "?"
        kits = []
        if self._auth.uid:
            kits = self._client.get_dna_kits(self._auth.uid)
            if not kits:
                guid = self._client.detect_kit_from_uid(self._auth.uid)
                if guid:
                    kits = [DnaKit(guid=guid, name="Mein DNA-Test")]
        for kit in kits:
            self._kit_map[kit.name] = kit.guid
            self._db.upsert_kit(kit)

        def _upd():
            self._set_login_status(
                f"✅ Eingeloggt (UID: {uid[:16]}…) | {len(kits)} Kit(s)", success=True)
            self._set_status("Login erfolgreich.")
            self._update_kit_combo()
            self._nb.select(1)
            self._save_settings()
        self.after(0, _upd)

    def _choose_cookie_file(self):
        p = filedialog.askopenfilename(title="Cookie-JSON wählen",
                                        filetypes=[("JSON", "*.json"), ("Alle", "*.*")])
        if p:
            self._cookie_file_var.set(p)

    def _use_manual_guid(self):
        guid = self._manual_guid_var.get().strip()
        if not guid:
            messagebox.showwarning("Keine GUID", "Bitte eine Kit-GUID eingeben.")
            return
        name = f"Manuell ({guid[:8]}…)"
        self._kit_map[name] = guid
        self._update_kit_combo()
        self._current_test_guid = guid
        self._save_settings()
        self._set_status(f"Kit-GUID gespeichert.")

    def _set_login_status(self, msg, success=True):
        self._login_status_var.set(msg)
        self._login_status_lbl.configure(
            style="Success.TLabel" if success else "Warning.TLabel")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2: HERUNTERLADEN
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_download(self):
        f = self._tab_download
        p = {"padx": 14, "pady": 6}

        # Kit-Auswahl
        ttk.Label(f, text="DNA-Kit:", style="Bold.TLabel").grid(row=0, column=0, sticky="e", **p)
        self._kit_var = tk.StringVar()
        self._kit_combo = ttk.Combobox(f, textvariable=self._kit_var, width=46, state="readonly")
        self._kit_combo.grid(row=0, column=1, columnspan=2, sticky="w", **p)
        self._update_kit_combo()

        # ── Bereich A: Matches ────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=1, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        ttk.Label(f, text="A: Matches herunterladen",
                  style="Bold.TLabel").grid(row=2, column=0, columnspan=4, sticky="w", **p)

        ttk.Label(f, text="Filter:").grid(row=3, column=0, sticky="e", **p)
        self._filter_var = tk.StringVar(value="ALL")
        ff = ttk.Frame(f); ff.grid(row=3, column=1, sticky="w", **p)
        for val, lbl in [("ALL","Alle"),("STARRED","Markierte"),
                          ("CLOSE","Nahe"),("DISTANT","Entfernte")]:
            ttk.Radiobutton(ff, text=lbl, variable=self._filter_var, value=val).pack(
                side="left", padx=5)

        ttk.Label(f, text="Sortierung:").grid(row=4, column=0, sticky="e", **p)
        self._sort_var = tk.StringVar(value="RELATIONSHIP")
        sf = ttk.Frame(f); sf.grid(row=4, column=1, sticky="w", **p)
        for val, lbl in [("RELATIONSHIP","Nach Beziehung"),("SHARED_CM","Nach cM")]:
            ttk.Radiobutton(sf, text=lbl, variable=self._sort_var, value=val).pack(
                side="left", padx=5)

        bf = ttk.Frame(f); bf.grid(row=5, column=0, columnspan=4, sticky="w", **p)
        self._start_btn = ttk.Button(bf, text="▶ Matches starten",
                                      command=self._start_matches)
        self._start_btn.pack(side="left", padx=4)
        self._stop_btn = ttk.Button(bf, text="⏹ Stoppen",
                                     command=self._stop_download, state="disabled")
        self._stop_btn.pack(side="left", padx=4)
        self._only_new_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bf, text="✨ Nur neue (inkrementell)",
                        variable=self._only_new_var).pack(side="left", padx=14)
        self._fetch_names_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bf, text="👤 Volle Namen versuchen (oft von Ancestry blockiert)",
                        variable=self._fetch_names_var).pack(side="left", padx=14)

        # ── Bereich A2: Namen nachladen (profileData-Bulk-API) ────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=6, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        ttk.Label(f, text="A2: Namen & Stammbaum nachladen",
                  style="Bold.TLabel").grid(row=7, column=0, columnspan=4, sticky="w", **p)
        ttk.Label(f, text=(
            "Lädt Namen, Geschlecht, Stammbaum-Status/-Größe und ob ein\n"
            "gemeinsamer Vorfahre existiert (20 Matches pro Anfrage).\n"
            "Danach: 'Vorfahren & Orte' + 'Ahnentafeln' laden für ALLE Matches\n"
            "mit Baum (nicht nur Ancestrys erkannte) – dann Auswertung/GEDCOM-Abgleich."
        ), foreground="#555555").grid(row=8, column=0, columnspan=4, sticky="w", padx=14)

        sf_names = ttk.Frame(f); sf_names.grid(row=9, column=0, columnspan=4, sticky="w", **p)
        ttk.Label(sf_names, text="Nur ab (cM):").pack(side="left")
        self._names_min_cm_var = tk.StringVar(value="0")
        ttk.Entry(sf_names, textvariable=self._names_min_cm_var, width=6).pack(side="left", padx=6)

        bf_names = ttk.Frame(f); bf_names.grid(row=10, column=0, columnspan=4, sticky="w", **p)
        self._names_start_btn = ttk.Button(bf_names, text="▶ Namen & Stammbaum laden",
                                            command=self._start_fetch_names)
        self._names_start_btn.pack(side="left", padx=4)
        self._names_stop_btn = ttk.Button(bf_names, text="⏹ Stoppen",
                                           command=self._stop_download, state="disabled")
        self._names_stop_btn.pack(side="left", padx=4)
        self._anc_start_btn = ttk.Button(bf_names, text="▶ Vorfahren & Orte laden",
                                         command=self._start_fetch_ancestors)
        self._anc_start_btn.pack(side="left", padx=(16,4))
        self._ped_start_btn = ttk.Button(bf_names, text="▶ Ahnentafeln laden",
                                         command=self._start_fetch_pedigrees)
        self._ped_start_btn.pack(side="left", padx=4)

        # ── Bereich B: Shared Matches ─────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=11, column=0, columnspan=4, sticky="ew", padx=14, pady=6)
        ttk.Label(f, text="B: Shared Matches herunterladen",
                  style="Bold.TLabel").grid(row=12, column=0, columnspan=4, sticky="w", **p)
        ttk.Label(f, text=(
            "Lädt für jeden gespeicherten Match dessen gemeinsame Matches mit cM-Werten.\n"
            "Empfehlung: erst Matches (A) herunterladen, dann Shared Matches (B).\n"
            "Ab 20 cM sinnvoll – erfasst auch entferntere Verwandte.\n"
            "Tipp: Höherer cM-Wert = deutlich weniger primäre Matches = viel schneller (kann sonst Stunden dauern)."
        ), foreground="#555555").grid(row=13, column=0, columnspan=4, sticky="w", padx=14)

        sf2 = ttk.Frame(f); sf2.grid(row=14, column=0, columnspan=4, sticky="w", **p)
        ttk.Label(sf2, text="Nur primäre Matches ab (cM):").pack(side="left")
        self._shared_min_cm_var = tk.StringVar(value="20")
        ttk.Entry(sf2, textvariable=self._shared_min_cm_var, width=6).pack(
            side="left", padx=6)
        self._skip_existing_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(sf2, text="Bereits geholte überspringen",
                         variable=self._skip_existing_var).pack(side="left", padx=12)

        bf2 = ttk.Frame(f); bf2.grid(row=15, column=0, columnspan=4, sticky="w", **p)
        self._shared_start_btn = ttk.Button(bf2, text="▶ Shared Matches starten",
                                             command=self._start_shared)
        self._shared_start_btn.pack(side="left", padx=4)
        self._shared_stop_btn = ttk.Button(bf2, text="⏹ Stoppen",
                                            command=self._stop_download, state="disabled")
        self._shared_stop_btn.pack(side="left", padx=4)

        # ── Fortschritt ───────────────────────────────────────────────────────
        ttk.Separator(f, orient="horizontal").grid(
            row=16, column=0, columnspan=4, sticky="ew", padx=14, pady=4)
        ttk.Label(f, text="Fortschritt:").grid(row=17, column=0, sticky="e", **p)
        self._progress_var = tk.DoubleVar()
        ttk.Progressbar(f, variable=self._progress_var, maximum=100, length=380).grid(
            row=17, column=1, sticky="w", **p)
        self._progress_lbl = tk.StringVar(value="—")
        ttk.Label(f, textvariable=self._progress_lbl).grid(row=17, column=2, sticky="w", **p)

        # ── Log ───────────────────────────────────────────────────────────────
        ttk.Label(f, text="Protokoll:", style="Bold.TLabel").grid(
            row=18, column=0, sticky="ne", padx=14, pady=(10, 4))
        lf = ttk.Frame(f); lf.grid(row=18, column=1, columnspan=3, sticky="nsew",
                                     padx=14, pady=4)
        self._log_text = tk.Text(lf, height=12, width=72, font=("Consolas", 9),
                                  bg="#1E1E2E", fg="#A0D0FF", state="disabled", relief="flat")
        sc = ttk.Scrollbar(lf, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sc.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        sc.pack(side="right", fill="y")

        f.columnconfigure(1, weight=1)
        f.rowconfigure(13, weight=1)
        self._install_gui_log_handler()

    def _install_gui_log_handler(self):
        widget = self._log_text

        class GUIHandler(logging.Handler):
            def __init__(self, w):
                super().__init__()
                self._w = w
            def emit(self, record):
                msg   = self.format(record) + "\n"
                color = {"DEBUG":"#888888","INFO":"#A0D0FF",
                         "WARNING":"#FFD080","ERROR":"#FF8080"}.get(record.levelname,"#A0D0FF")
                try:
                    def _ins():
                        self._w.configure(state="normal")
                        self._w.insert("end", msg, record.levelname)
                        self._w.tag_config(record.levelname, foreground=color)
                        self._w.see("end")
                        self._w.configure(state="disabled")
                    self._w.after(0, _ins)
                except Exception:
                    pass

        h = GUIHandler(widget)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(h)

    def _update_kit_combo(self):
        names = list(self._kit_map.keys())
        self._kit_combo["values"] = names
        if names and not self._kit_var.get():
            self._kit_combo.current(0)

    def _get_kit_guid(self) -> Optional[str]:
        return self._kit_map.get(self._kit_var.get())

    def _start_matches(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                 on_progress=self._on_progress,
                                 on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                 on_done=self._on_done)
        if self._fetch_names_var.get():
            self._set_status("Hinweis: 'Volle Namen' lädt jeden Match einzeln – "
                             "das kann bei vielen Matches sehr lange dauern.")
        self._scraper.start_matches(guid, self._filter_var.get(), self._sort_var.get(),
                                     only_new=self._only_new_var.get(),
                                     fetch_names=self._fetch_names_var.get())

    def _start_shared(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        total_matches = self._db.get_match_count(guid)
        if total_matches == 0:
            messagebox.showwarning("Keine Matches",
                                   "Erst Matches herunterladen (Schritt A).")
            return
        try:
            min_cm = float(self._shared_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 90.0

        self._current_test_guid = guid
        self._shared_start_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                 on_progress=self._on_progress,
                                 on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                 on_done=self._on_shared_done)
        self._scraper.start_shared(guid, min_cm, self._skip_existing_var.get())

    def _start_fetch_names(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        try:
            min_cm = float(self._names_min_cm_var.get() or 0)
        except ValueError:
            min_cm = 0.0
        self._current_test_guid = guid
        self._names_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_names_done(r)))
        self._scraper.start_fetch_names(guid, min_cm)

    def _on_names_done(self, result: "DownloadResult"):
        self._names_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Namen", result.message)

    def _start_fetch_ancestors(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._anc_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_ancestors_done(r)))
        self._scraper.start_fetch_ancestors(guid, self._a2_min_cm())

    def _on_ancestors_done(self, result: "DownloadResult"):
        self._anc_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Vorfahren", result.message)

    def _start_fetch_pedigrees(self):
        guid = self._get_kit_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen oder GUID eingeben.")
            return
        if not self._client:
            messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
            return
        self._current_test_guid = guid
        self._ped_start_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="normal")
        self._progress_var.set(0)
        self._scraper = Scraper(self._client, self._db,
                                on_progress=self._on_progress,
                                on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                on_done=lambda r: self.after(0, lambda: self._on_pedigrees_done(r)))
        self._scraper.start_fetch_pedigrees(guid, self._a2_min_cm())

    def _a2_min_cm(self) -> float:
        """cM-Schwelle aus dem A2-Feld 'Nur ab (cM)'."""
        try:
            return float(self._names_min_cm_var.get() or 0)
        except (ValueError, AttributeError):
            return 0.0

    def _on_pedigrees_done(self, result: "DownloadResult"):
        self._ped_start_btn.configure(state="normal")
        self._names_stop_btn.configure(state="disabled")
        self._refresh_match_table()
        messagebox.showinfo("Ahnentafeln", result.message)

    # ── Überlagerung: gemeinsame Vorfahren ─────────────────────────────────────

    def _current_guid(self):
        return self._get_kit_guid() or getattr(self, "_current_test_guid", None)

    def _show_ancestor_groups(self):
        guid = self._current_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        groups = self._db.get_ancestor_groups(guid, min_matches=2)
        if not groups:
            messagebox.showinfo("Keine Daten",
                "Noch keine geteilten Vorfahren gefunden.\n"
                "Erst 'Vorfahren & Orte laden' ausführen.")
            return

        win = tk.Toplevel(self)
        win.title("Gemeinsame Vorfahren – Überlagerung")
        win.geometry("820x560")

        ttk.Label(win, text=(f"{len(groups)} Vorfahren werden von mehreren Matches "
                             f"geteilt – Klick zeigt die Matches:"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

        pane = ttk.PanedWindow(win, orient="vertical"); pane.pack(fill="both", expand=True, padx=10, pady=6)
        top = ttk.Frame(pane); pane.add(top, weight=3)
        bot = ttk.Frame(pane); pane.add(bot, weight=2)

        cols = ("anc","year","count")
        tv = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse")
        for c,(lbl,w) in {"anc":("Gemeinsamer Vorfahr",420),"year":("*Jahr",90),
                          "count":("# Matches",90)}.items():
            tv.heading(c, text=lbl); tv.column(c, width=w,
                       anchor=("center" if c!="anc" else "w"))
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(top, orient="vertical", command=tv.yview); sb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=sb.set)

        self._anc_groups = {}
        for g in groups:
            iid = tv.insert("", "end", values=(g["ancestor_name"], g["birth_year"], g["count"]))
            self._anc_groups[iid] = g

        ttk.Label(bot, text="Matches dieses Vorfahren:",
                  style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bot, height=8, wrap="word", font=("Segoe UI", 9))
        detail.pack(fill="both", expand=True)

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            g = self._anc_groups.get(sel[0])
            detail.delete("1.0","end")
            if not g: return
            detail.insert("end", f"{g['ancestor_name']}  (*{g['birth_year'] or '?'})  "
                                 f"– {g['count']} Matches:\n\n")
            for guid_m, name, path, cm in sorted(g["matches"], key=lambda x:-(x[3] or 0)):
                detail.insert("end", f"  • {name or guid_m[:8]}   "
                                     f"{cm:.0f} cM   Pfad: {path or '?'}\n")
        tv.bind("<<TreeviewSelect>>", on_sel)

    def _export_ancestor_groups(self):
        guid = self._current_guid()
        if not guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        groups = self._db.get_ancestor_groups(guid, min_matches=2)
        if not groups:
            messagebox.showinfo("Keine Daten", "Noch keine geteilten Vorfahren gefunden.")
            return
        path = filedialog.asksaveasfilename(
            title="Vorfahren-Gruppen speichern", defaultextension=".csv",
            filetypes=[("CSV","*.csv")])
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow(["Gemeinsamer Vorfahr","*Jahr","Anzahl Matches","Match","cM","Pfad"])
            for g in groups:
                for guid_m, name, pth, cm in sorted(g["matches"], key=lambda x:-(x[3] or 0)):
                    w.writerow([g["ancestor_name"], g["birth_year"], g["count"],
                                name or guid_m, f"{cm:.0f}" if cm else "", pth or ""])
        messagebox.showinfo("Export", f"{len(groups)} Vorfahren-Gruppen gespeichert.")
        self._set_status(f"Vorfahren-Gruppen exportiert: {len(groups)}")

    # ── Ahnentafel eines Matches ────────────────────────────────────────────────

    def _show_match_pedigree(self):
        if not self._selected_match:
            messagebox.showinfo("Kein Match", "Bitte zuerst einen Match in der Tabelle wählen.")
            return
        guid = self._selected_match.match_guid
        test_guid = self._current_guid()
        rows = self._db.get_pedigree_for_match(test_guid, guid)
        if not rows:
            messagebox.showinfo("Keine Ahnentafel",
                "Für diesen Match ist noch keine Ahnentafel geladen.\n"
                "Erst '▶ Ahnentafeln laden' ausführen (Match braucht einen Baum).")
            return

        # Gemeinsame Vorfahren (= wo der Match in DEINEM Baum hängt)
        common = self._db.get_ancestors_for_match(guid)

        win = tk.Toplevel(self)
        win.title(f"Ahnentafel – {self._selected_match.display_name}")
        win.geometry("800x600")
        ttk.Label(win, text=(f"{len(rows)} Vorfahren von "
                             f"{self._selected_match.display_name}:"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

        # ── Anknüpfungspunkt zu deinem Baum ─────────────────────────────────────
        if common:
            box = ttk.LabelFrame(win, text="🔗 Verbindung zu deinem Baum")
            box.pack(fill="x", padx=10, pady=(0,6))
            for a in common:
                yr = a.get("birth_year") or "?"
                mine = a.get("kinship_path_sample") or "?"
                rel = a.get("relationship_to_sample") or ""
                ttk.Label(box, text=(f"  • {a.get('ancestor_name','?')} (*{yr}) – "
                                     f"deine Linie: {mine}"
                                     + (f"  ({rel})" if rel else ""))).pack(anchor="w")
        else:
            ttk.Label(win, text="(Kein gemeinsamer Vorfahr geladen – ggf. "
                                "'▶ Vorfahren & Orte laden' ausführen.)",
                      foreground="#888888").pack(anchor="w", padx=12)

        # Namen+Jahr der gemeinsamen Vorfahren zum Markieren in der Tafel
        common_keys = set()
        for a in common:
            nm = (a.get("ancestor_name") or "").lower()
            common_keys.add((nm, (a.get("birth_year") or "")))

        cols = ("gen", "rel", "name", "birth", "death")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c,(lbl,w) in {"gen":("Gen.",45), "rel":("Linie",90),
                          "name":("Name",300), "birth":("* Geburt",150),
                          "death":("† Tod",150)}.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=("w" if c in ("name","birth","death") else "center"))
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=6)
        sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y", pady=6); tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("common", background="#fff3b0")  # gemeinsamer Vorfahr

        def _rel(path):
            if path == "":
                return "Match"
            return path  # z.B. FMF

        def _is_common(name, year):
            nl = name.lower()
            for cn, cy in common_keys:
                if not cn:
                    continue
                # Treffer wenn Nachname enthalten und Jahr passt (oder Jahr fehlt)
                if (nl in cn or cn in nl) and (not year or not cy or year == cy):
                    return True
            return False

        for r in rows:
            name = (f"{r['given_name']} {r['surname']}".strip()) or "(lebend/privat)"
            b = " ".join(x for x in (r["birth_date"] or r["birth_year"],
                                     r["birth_place"]) if x).strip()
            d = " ".join(x for x in (r["death_date"] or r["death_year"],
                                     r["death_place"]) if x).strip()
            tags = ("common",) if _is_common(name, r["birth_year"] or "") else ()
            tv.insert("", "end", values=(r["generation"], _rel(r["ahnen_path"]),
                                         name, b, d), tags=tags)

    def _show_pedigree_overlay(self):
        """Cluster: Vorfahren, die in mehreren Match-Ahnentafeln vorkommen."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Pedigree-Überlagerung – Cluster über alle Ahnentafeln")
        win.geometry("860x600")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="Gruppieren nach:", style="Bold.TLabel").pack(side="left")
        mode_var = tk.StringVar(value="person")
        for val, lbl in (("person","Person (Name+Jahr)"),
                         ("surname","Nachname (Sippe)"),
                         ("place","Geburtsort")):
            ttk.Radiobutton(top, text=lbl, value=val, variable=mode_var).pack(side="left", padx=6)
        ttk.Label(top, text="  ab").pack(side="left")
        minm_var = tk.StringVar(value="2")
        ttk.Spinbox(top, from_=2, to=99, width=4, textvariable=minm_var).pack(side="left", padx=4)
        ttk.Label(top, text="Matches").pack(side="left")

        info = ttk.Label(win, text="", style="Bold.TLabel")
        info.pack(anchor="w", padx=10, pady=(4,2))

        pane = ttk.PanedWindow(win, orient="vertical"); pane.pack(fill="both", expand=True, padx=10, pady=6)
        tframe = ttk.Frame(pane); pane.add(tframe, weight=3)
        bframe = ttk.Frame(pane); pane.add(bframe, weight=2)

        cols = ("label","detail","count")
        tv = ttk.Treeview(tframe, columns=cols, show="headings", selectmode="browse")
        for c,(lbl,w) in {"label":("Vorfahr / Cluster",470),"detail":("Info",150),
                          "count":("# Matches",90)}.items():
            tv.heading(c, text=lbl); tv.column(c, width=w,
                       anchor=("center" if c=="count" else "w"))
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview); sb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=sb.set)

        ttk.Label(bframe, text="Matches dieses Clusters:",
                  style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bframe, height=8, wrap="word", font=("Segoe UI", 9))
        detail.pack(fill="both", expand=True)

        store = {}
        def reload(*_):
            try:
                mm = max(2, int(minm_var.get() or 2))
            except ValueError:
                mm = 2
            groups = self._db.get_pedigree_groups(test_guid, min_matches=mm,
                                                  mode=mode_var.get())
            tv.delete(*tv.get_children()); store.clear()
            for g in groups:
                iid = tv.insert("", "end", values=(g["label"], g["detail"], g["count"]))
                store[iid] = g
            info.configure(text=(f"{len(groups)} Cluster werden von ≥{mm} Matches geteilt."
                                 if groups else
                                 "Keine Überlagerung gefunden – erst '▶ Ahnentafeln laden' ausführen."))
        mode_var.trace_add("write", reload)
        minm_var.trace_add("write", reload)

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            g = store.get(sel[0]); detail.delete("1.0","end")
            if not g: return
            detail.insert("end", f"{g['label']} {g['detail']} – {g['count']} Matches:\n\n")
            for guid_m, name, path, gen, cm in sorted(g["matches"], key=lambda x:-(x[4] or 0)):
                detail.insert("end", f"  • {name or guid_m[:8]}   "
                                     f"{(cm or 0):.0f} cM   (Gen {gen}, Linie {path or '?'})\n")
        tv.bind("<<TreeviewSelect>>", on_sel)
        reload()

    def _show_shared_clusters(self):
        """Triangulations-Cluster aus den Shared Matches (Connected Components)."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return

        win = tk.Toplevel(self)
        win.title("Shared-Cluster – Triangulationsgruppen")
        win.geometry("820x600")

        top = ttk.Frame(win); top.pack(fill="x", padx=10, pady=(10,4))
        ttk.Label(top, text="cM-Fenster:", style="Bold.TLabel").pack(side="left")
        lo_var = tk.StringVar(value="20"); hi_var = tk.StringVar(value="400")
        ttk.Entry(top, textvariable=lo_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="bis").pack(side="left")
        ttk.Entry(top, textvariable=hi_var, width=6).pack(side="left", padx=4)
        ttk.Label(top, text="cM   (sehr enge/weite Matches verbinden alles)").pack(side="left")

        info = ttk.Label(win, text="", style="Bold.TLabel")
        info.pack(anchor="w", padx=10, pady=(4,2))

        pane = ttk.PanedWindow(win, orient="vertical"); pane.pack(fill="both", expand=True, padx=10, pady=6)
        tframe = ttk.Frame(pane); pane.add(tframe, weight=2)
        bframe = ttk.Frame(pane); pane.add(bframe, weight=3)

        tv = ttk.Treeview(tframe, columns=("cluster","size"), show="headings", selectmode="browse")
        tv.heading("cluster", text="Cluster"); tv.column("cluster", width=120, anchor="center")
        tv.heading("size", text="Mitglieder"); tv.column("size", width=100, anchor="center")
        tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(tframe, orient="vertical", command=tv.yview); sb.pack(side="right", fill="y")
        tv.configure(yscrollcommand=sb.set)

        ttk.Label(bframe, text="Mitglieder des Clusters:", style="Bold.TLabel").pack(anchor="w", pady=(4,2))
        detail = tk.Text(bframe, height=10, wrap="word", font=("Segoe UI", 9))
        detail.pack(fill="both", expand=True)

        store = {}
        def reload(*_):
            try:
                lo = float(lo_var.get() or 0); hi = float(hi_var.get() or 9999)
            except ValueError:
                lo, hi = 20.0, 400.0
            clusters = self._db.get_shared_clusters(test_guid, lo, hi)
            tv.delete(*tv.get_children()); store.clear()
            for i, c in enumerate(clusters, 1):
                iid = tv.insert("", "end", values=(f"Cluster {i}", c["size"]))
                store[iid] = c
            info.configure(text=(f"{len(clusters)} Cluster gefunden "
                                 f"({lo:.0f}–{hi:.0f} cM)." if clusters else
                                 "Keine Cluster – erst Shared Matches laden (Schritt B)."))
        ttk.Button(top, text="↻", width=3, command=reload).pack(side="left", padx=8)

        def dock_in_tree():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo("Kein Cluster", "Bitte einen Cluster wählen.")
                return
            c = store.get(sel[0])
            if not c:
                return
            guids = [g for g, _n, _cm in c["members"]]
            # Gemeinsame Vorfahren des Clusters (Personen, von ≥2 geteilt)
            groups = self._db.get_pedigree_groups(
                test_guid, min_matches=2, mode="person", only_guids=guids)
            if not groups:
                messagebox.showinfo("Keine gemeinsame Linie",
                    "Dieser Cluster hat keine von ≥2 Mitgliedern geteilten Vorfahren.\n"
                    "Ggf. erst Ahnentafeln dieser Matches laden.")
                return

            def _after_load(ged):
                from core.treematch import Person, render_kinship
                index, amap = ged["index"], ged["amap"]
                hits = []
                for g in groups:
                    yr = g["detail"].replace("*", "").strip()
                    q = Person(g["label"], "", yr or None, "")
                    # label ist 'Vorname Nachname' → in Person aufteilen
                    parts = g["label"].rsplit(" ", 1)
                    if len(parts) == 2:
                        q = Person(parts[0], parts[1], yr or None, "")
                    if not q.stoks:
                        continue
                    own, score = index.best_match(q, min_score=0.6)
                    if own:
                        path = amap.get(own.ref)
                        hits.append((g["count"], score, g["label"], g["detail"],
                                     own.display, path))
                hits.sort(key=lambda h: (h[5] is None, len(h[5]) if h[5] else 99,
                                         -h[0], -h[1]))
                self.after(0, lambda: self._show_cluster_dock(c, hits))

            self._set_status("Suche Cluster-Linie in deinem Baum …")
            self._ensure_gedcom_loaded(_after_load)

        ttk.Button(top, text="🔗 Cluster-Linie in meinem Baum suchen",
                   command=dock_in_tree).pack(side="left", padx=8)

        def deepen_cluster():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo("Kein Cluster", "Bitte einen Cluster wählen.")
                return
            c = store.get(sel[0])
            if not c:
                return
            guids = [g for g, _n, _cm in c["members"]]
            if not messagebox.askyesno(
                    "Cluster tiefer laden",
                    f"Für {len(guids)} Cluster-Matches tiefere Ahnentafeln "
                    f"(bis 8 Generationen) laden?\n\n"
                    "Nötig für entfernte Cousins (gemeinsamer Vorfahr >5 Gen.).\n"
                    "Dauert etwas (mehrere Calls pro Match)."):
                return
            if not self._client:
                messagebox.showwarning("Nicht eingeloggt", "Bitte zuerst einloggen.")
                return
            self._scraper = Scraper(self._client, self._db,
                                    on_progress=self._on_progress,
                                    on_status=lambda m: self.after(0, lambda: self._set_status(m)),
                                    on_done=lambda r: self.after(0, lambda: messagebox.showinfo(
                                        "Tiefe Ahnentafeln", r.message + "\n\nJetzt erneut "
                                        "'Cluster-Linie suchen'.")))
            self._scraper.start_deepen_pedigrees(test_guid, guids)

        ttk.Button(top, text="⤓ Cluster tiefer laden (8 Gen.)",
                   command=deepen_cluster).pack(side="left", padx=4)

        def on_sel(_):
            sel = tv.selection()
            if not sel: return
            c = store.get(sel[0]); detail.delete("1.0","end")
            if not c: return
            guids = [g for g, _n, _cm in c["members"]]
            detail.insert("end", f"{c['size']} Matches in dieser Gruppe "
                                 f"(wahrscheinlich gemeinsame Ahnenlinie):\n")
            for guid, name, cm in c["members"]:
                detail.insert("end", f"  • {name or guid[:8]}   {(cm or 0):.0f} cM\n")

            # Gemeinsame Vorfahren-Linien INNERHALB des Clusters – das ist die
            # belastbare Linie, die bei dir andocken muss.
            detail.insert("end", "\n── Gemeinsame Vorfahren im Cluster "
                                 "(von ≥2 Mitgliedern geteilt) ──\n")
            found = False
            for mode, titel in (("person", "Personen"), ("surname", "Nachnamen"),
                                ("place", "Orte")):
                groups = self._db.get_pedigree_groups(
                    test_guid, min_matches=2, mode=mode, only_guids=guids)
                if not groups:
                    continue
                found = True
                detail.insert("end", f"\n{titel}:\n")
                for g in groups[:12]:
                    detail.insert("end", f"  • {g['label']} {g['detail']}"
                                         f"  ({g['count']}/{c['size']} Matches)\n")
            if not found:
                detail.insert("end", "  (keine geteilten Vorfahren – ggf. erst "
                                     "Ahnentafeln für diese Matches laden)\n")
        tv.bind("<<TreeviewSelect>>", on_sel)
        reload()

    def _show_cluster_dock(self, cluster, hits):
        """Zeigt, wo die gemeinsame Linie eines Clusters in deinem Baum andockt."""
        from core.treematch import render_kinship
        win = tk.Toplevel(self)
        win.title("Cluster-Linie → Andockpunkt in deinem Baum")
        win.geometry("820x520")
        ttk.Label(win, text=(f"Cluster mit {cluster['size']} Matches – "
                             f"gemeinsame Vorfahren gegen deinen Baum abgeglichen:"),
                  style="Bold.TLabel").pack(anchor="w", padx=10, pady=(10,4))

        direct = [h for h in hits if h[5] is not None]
        if direct:
            best = direct[0]
            kin = render_kinship(best[5])
            ttk.Label(win, text=(f"➡  Wahrscheinlicher Andockpunkt: {best[4]}  "
                                 f"({kin})"),
                      style="Bold.TLabel", foreground=COLORS.get("primary","#1b5e20")
                      ).pack(anchor="w", padx=10, pady=(0,6))
        else:
            ttk.Label(win, text=("Kein Treffer auf deiner direkten Ahnenlinie – "
                                 "untenstehende Kandidaten sind Seitenlinien/Vorschläge."),
                      foreground="#a05a00").pack(anchor="w", padx=10, pady=(0,6))

        cols = ("shared","cab","line","anchor")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        for c,(lbl,w) in {"shared":("Cluster-Vorfahr",240),"cab":("geteilt von",90),
                          "line":("Deine Linie",200),"anchor":("Person in deinem Baum",200)}.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=("center" if c=="cab" else "w"))
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=6)
        sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y", pady=6); tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("direct", background="#d8f0d8")

        for count, score, label, detail, owndisp, path in hits:
            kin = render_kinship(path) if path is not None else "— (Seitenlinie)"
            tag = ("direct",) if path is not None else ()
            tv.insert("", "end", tags=tag, values=(
                f"{label} {detail}".strip(),
                f"{count}/{cluster['size']}", kin, owndisp))
        if not hits:
            tv.insert("", "end", values=("(keine Treffer im Baum)", "", "", ""))

    def _reset_name_attempts(self):
        """Setzt die Fehlversuch-Zähler zurück, damit übersprungene Profile beim
        nächsten 'Namen laden' erneut versucht werden."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        n = self._db.reset_name_attempts(test_guid)
        self._set_status(f"Namens-Versuche zurückgesetzt: {n} Matches.")
        messagebox.showinfo("Zurückgesetzt",
            f"{n} Matches werden beim nächsten 'Namen & Stammbaum laden' "
            "erneut versucht.")

    def _reset_shared_matches(self):
        """Leert die Shared-Matches-Tabelle (alte, mit falschem Endpunkt geladene
        Daten) – danach Schritt B neu ausführen."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        if not messagebox.askyesno(
                "Shared Matches zurücksetzen",
                "Alle gespeicherten Shared Matches dieses Kits löschen?\n\n"
                "Nötig, um die fehlerhaften Alt-Daten (ganze Liste) zu entfernen.\n"
                "Danach Tab »Herunterladen« → Schritt B erneut ausführen."):
            return
        n = self._db.reset_shared_matches(test_guid)
        self._set_status(f"Shared Matches zurückgesetzt: {n} Zeilen gelöscht.")
        messagebox.showinfo("Zurückgesetzt",
            f"{n} Shared-Match-Zeilen gelöscht.\n"
            "Jetzt Schritt B (Shared Matches herunterladen) neu starten.")

    def _match_own_tree(self):
        """Gleicht alle geladenen Match-Ahnentafeln gegen den eigenen GEDCOM ab
        und zeigt, wo jeder Match in DEINEM Baum hängt."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte zuerst ein DNA-Kit wählen.")
            return
        peds = self._db.get_all_pedigrees(test_guid)
        if not peds:
            messagebox.showinfo("Keine Ahnentafeln",
                "Noch keine Ahnentafeln geladen. Erst '▶ Ahnentafeln laden' ausführen.")
            return
        def _after_load(ged):
            import threading
            from core.treematch import Person, render_kinship
            index, amap = ged["index"], ged["amap"]

            def _worker():
                results = []
                items = list(peds.items())
                for i, (guid, info) in enumerate(items, 1):
                    cands = []  # (score, ped_row, own_person, self_path)
                    for r in info["rows"]:
                        q = Person(r["given_name"], r["surname"],
                                   r["birth_year"], r["birth_place"])
                        if not q.stoks:
                            continue
                        own, score = index.best_match(q, min_score=0.6)
                        if own:
                            cands.append((score, r, own, amap.get(own.ref)))
                    if cands:
                        # MRCA: Direktlinie bevorzugen, davon der jüngste; sonst Score.
                        direct = [c for c in cands if c[3] is not None]
                        if direct:
                            best = min(direct, key=lambda c: (len(c[3]), -c[0]))
                        else:
                            best = max(cands, key=lambda c: (c[0], -c[1]["generation"]))
                        kin = render_kinship(best[3]) if best[3] is not None else ""
                        results.append((info["name"], info["cm"], best, kin,
                                        info.get("linked", False)))
                    if i % 20 == 0 or i == len(items):
                        self.after(0, lambda i=i: self._set_status(
                            f"GEDCOM-Abgleich: {i}/{len(items)} Matches geprüft …"))
                results.sort(key=lambda x: (-(x[2][0]), -(x[1] or 0)))
                self.after(0, lambda: self._show_gedcom_results(
                    results, len(ged["people"]), len(peds)))

            threading.Thread(target=_worker, daemon=True, name="gedcom-match").start()

        self._ensure_gedcom_loaded(_after_load)

    def _ensure_gedcom_loaded(self, on_ready):
        """Lädt den eigenen GEDCOM (mit Cache) + baut Index/Ahnen-Map, dann
        ruft on_ready(ged_dict) auf dem Main-Thread. ged_dict hat: people, index,
        individuals, families, amap, path."""
        cached = getattr(self, "_gedcom", None)
        if cached:
            on_ready(cached)
            return
        path = filedialog.askopenfilename(
            title="Eigenen Stammbaum wählen (GEDCOM)",
            filetypes=[("GEDCOM", "*.ged *.gedcom"), ("Alle", "*.*")])
        if not path:
            return
        import tkinter.simpledialog as sd
        default_root = getattr(self, "_gedcom_root_name", "") or ""
        root_name = (sd.askstring(
            "Deine Wurzelperson",
            "Wie heißt DU (bzw. die Wurzelperson) im Baum?\n"
            "Vorname Nachname – für die Linien-Benennung (leer = ohne).",
            initialvalue=default_root) or "").strip()
        self._gedcom_root_name = root_name

        import threading
        self._set_status("GEDCOM wird geladen … (läuft im Hintergrund)")

        def _worker():
            try:
                from core.treematch import (load_gedcom_full, TreeIndex,
                                            build_ancestor_map, find_root_candidate)
                people, individuals, families = load_gedcom_full(path)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror(
                    "GEDCOM-Fehler", f"Konnte GEDCOM nicht laden:\n{e}"))
                return
            if not people:
                self.after(0, lambda: messagebox.showwarning(
                    "Leer", "Kein verwertbarer Inhalt im GEDCOM."))
                return
            index = TreeIndex(people)
            amap = {}
            if root_name:
                rid, rscore = find_root_candidate(people, root_name)
                if rid and rscore >= 0.6:
                    amap = build_ancestor_map(rid, individuals, families)
                    log.info("Wurzelperson erkannt (score %.2f), %d Vorfahren",
                             rscore, len(amap))
            ged = dict(path=path, people=people, index=index,
                       individuals=individuals, families=families, amap=amap)
            self._gedcom = ged
            self.after(0, lambda: self._set_status(
                f"Eigener Baum geladen & gecacht: {len(people)} Personen."))
            self.after(0, lambda: on_ready(ged))

        threading.Thread(target=_worker, daemon=True, name="gedcom-load").start()

    def _show_gedcom_results(self, results, n_people, n_peds):
        win = tk.Toplevel(self)
        win.title("GEDCOM-Abgleich – wo hängt jeder Match in deinem Baum?")
        win.geometry("960x600")
        n_new = sum(1 for r in results if not r[4])
        hdr = ttk.Label(win, text=(
            f"Eigener Baum: {n_people} Personen · {len(results)} von {n_peds} "
            f"Matches verankert · davon {n_new} noch NICHT in Ancestry verknüpft "
            f"(orange = neue Leads):"),
            style="Bold.TLabel")
        hdr.pack(anchor="w", padx=10, pady=(10,4))

        cols = ("link","match","cm","anchor","abirth","kin","line","score")
        tv = ttk.Treeview(win, columns=cols, show="headings")
        heads = {"link":("Verknüpft",75),"match":("Match",170),"cm":("cM",50),
                 "anchor":("Anknüpfung in deinem Baum",190),
                 "abirth":("* Anknüpfung",120),
                 "kin":("Deine Linie",170),"line":("Match-Linie",75),
                 "score":("Sicherheit",65)}
        for c,(lbl,w) in heads.items():
            tv.heading(c, text=lbl)
            tv.column(c, width=w, anchor=("center" if c in ("cm","line","score","link") else "w"))
        tv.pack(side="left", fill="both", expand=True, padx=(10,0), pady=6)
        sb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        sb.pack(side="right", fill="y", pady=6); tv.configure(yscrollcommand=sb.set)
        tv.tag_configure("strong", background="#d8f0d8")
        tv.tag_configure("newlead", background="#fde9c8")  # neu: noch nicht verknüpft

        for name, cm, (score, r, own, _p), kin, linked in results:
            ab = " ".join(x for x in (str(own.year or ""), own.place) if x).strip()
            if linked:
                tag = ("strong",) if score >= 0.8 else ()
            else:
                tag = ("newlead",)
            tv.insert("", "end", tags=tag, values=(
                "✓ im Baum" if linked else "neu?",
                name or "?", f"{(cm or 0):.0f}", own.display, ab,
                kin or "—", r["ahnen_path"] or "?", f"{score:.2f}"))

        self._set_status(f"GEDCOM-Abgleich: {len(results)}/{n_peds} Matches verankert.")

    def _stop_download(self):
        if self._scraper:
            self._scraper.stop()
        self._stop_btn.configure(state="disabled")
        self._shared_stop_btn.configure(state="disabled")
        self._names_stop_btn.configure(state="disabled")

    def _on_progress(self, fetched, total, label):
        pct = min(100.0, (fetched / max(total, 1)) * 100)
        def _u():
            self._progress_var.set(pct)
            self._progress_lbl.set(f"{fetched} / ~{total}  –  {label[:45]}")
        self.after(0, _u)

    def _on_done(self, result: DownloadResult):
        def _u():
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._refresh_match_table()
            self._refresh_stats()
            if result.success:
                messagebox.showinfo("Fertig", result.message)
        self.after(0, _u)

    def _on_shared_done(self, result: DownloadResult):
        def _u():
            self._shared_start_btn.configure(state="normal")
            self._shared_stop_btn.configure(state="disabled")
            self._set_status(("✅ " if result.success else "⚠️ ") + result.message)
            self._refresh_stats()
            if result.success:
                messagebox.showinfo("Shared Matches fertig", result.message)
        self.after(0, _u)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3: MATCHES
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_matches(self):
        f = self._tab_matches

        # Filter-Leiste
        fl = ttk.Frame(f); fl.pack(fill="x", padx=10, pady=6)
        ttk.Label(fl, text="Suche:").pack(side="left", padx=(0,4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_match_table())
        ttk.Entry(fl, textvariable=self._search_var, width=20).pack(side="left")

        ttk.Label(fl, text="  Beziehung:").pack(side="left", padx=(10,4))
        self._rel_var = tk.StringVar(value="(alle)")
        self._rel_combo = ttk.Combobox(fl, textvariable=self._rel_var, width=22, state="readonly")
        self._rel_combo.pack(side="left")
        self._rel_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_match_table())

        ttk.Label(fl, text="  min cM:").pack(side="left", padx=(10,4))
        self._min_cm_var = tk.StringVar(value="0")
        ttk.Entry(fl, textvariable=self._min_cm_var, width=6).pack(side="left")
        ttk.Button(fl, text="↩", width=3, command=self._refresh_match_table).pack(side="left", padx=2)

        self._starred_var = tk.BooleanVar()
        ttk.Checkbutton(fl, text="Markierte", variable=self._starred_var,
                         command=self._refresh_match_table).pack(side="left", padx=(10,0))
        self._tree_var = tk.BooleanVar()
        ttk.Checkbutton(fl, text="Mit Stammbaum", variable=self._tree_var,
                         command=self._refresh_match_table).pack(side="left", padx=6)

        self._match_count_var = tk.StringVar(value="")
        ttk.Label(fl, textvariable=self._match_count_var,
                  foreground=COLORS["primary"]).pack(side="right", padx=8)
        ttk.Button(fl, text="↻", command=self._refresh_match_table).pack(side="right", padx=4)

        # Haupt-Pane
        pane = ttk.PanedWindow(f, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=4)

        left = ttk.Frame(pane); pane.add(left, weight=3)
        right = ttk.Frame(pane); pane.add(right, weight=2)

        self._build_match_tree(left)
        self._build_detail_panel(right)

    def _build_match_tree(self, parent):
        cols = ("name","guid","note","cm","seg","rel","tree","ca","starred")
        self._tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        for col, (label, width, anchor) in {
            "name"   : ("Name / ID",   190, "w"),
            "guid"   : ("GUID",         95, "w"),
            "note"   : ("Bemerkung",   150, "w"),
            "cm"     : ("cM",           65, "e"),
            "seg"    : ("Seg.",          45, "e"),
            "rel"    : ("Beziehung",   150, "w"),
            "tree"   : ("Stammbaum",   140, "w"),
            "ca"     : ("Vorfahre",     70, "center"),
            "starred": ("⭐",            40, "center"),
        }.items():
            self._tree.heading(col, text=label, command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor, stretch=(col == "name"))

        self._tree.tag_configure("close",   background="#D6F5E3")
        self._tree.tag_configure("starred", background="#FFF3CD")
        self._tree.tag_configure("no_tree", foreground="#999999")

        sy = ttk.Scrollbar(parent, orient="vertical",   command=self._tree.yview)
        sx = ttk.Scrollbar(parent, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1); parent.columnconfigure(0, weight=1)
        self._tree.bind("<<TreeviewSelect>>", self._on_match_select)
        self._tree.bind("<Button-3>", self._on_match_rightclick)
        self._sort_col = "cm"; self._sort_asc = False

    def _build_detail_panel(self, parent):
        # Oberer Teil: Matchdetails
        detail_nb = ttk.Notebook(parent)
        detail_nb.pack(fill="both", expand=True)

        # Sub-Tab 1: Info + Notiz
        info_frame = ttk.Frame(detail_nb)
        detail_nb.add(info_frame, text="Info & Notiz")

        self._detail_name_var = tk.StringVar(value="—")
        ttk.Label(info_frame, textvariable=self._detail_name_var,
                  font=("Segoe UI", 11, "bold"), wraplength=260).pack(anchor="w", padx=8, pady=(6,2))

        inf = ttk.Frame(info_frame); inf.pack(fill="x", padx=8)
        self._detail_fields: dict[str, tk.StringVar] = {}
        for lbl in ("cM","Segmente","Längstes Seg.","Beziehung",
                    "Konfidenz","Stammbaum","Gem. Vorfahre","Geschlecht",
                    "Letzter Login"):
            row = ttk.Frame(inf); row.pack(fill="x", pady=1)
            ttk.Label(row, text=lbl + ":", width=15, anchor="e",
                      foreground="#555555").pack(side="left")
            var = tk.StringVar(value="—")
            ttk.Label(row, textvariable=var, anchor="w").pack(side="left", padx=4)
            self._detail_fields[lbl] = var

        ttk.Separator(info_frame, orient="horizontal").pack(fill="x", padx=8, pady=6)
        ttk.Label(info_frame, text="Notiz:", style="Bold.TLabel").pack(anchor="w", padx=8)
        self._note_text = tk.Text(info_frame, height=5, font=("Segoe UI", 9),
                                   wrap="word", relief="solid", borderwidth=1)
        self._note_text.pack(fill="x", padx=8, pady=4)
        ttk.Button(info_frame, text="💾 Notiz speichern",
                   command=self._save_note).pack(anchor="w", padx=8, pady=2)
        ttk.Button(info_frame, text="🔗 In Ancestry öffnen",
                   command=self._open_in_ancestry).pack(anchor="w", padx=8, pady=2)

        # Sub-Tab 2: Shared Matches
        sm_frame = ttk.Frame(detail_nb)
        detail_nb.add(sm_frame, text="Shared Matches")
        self._build_shared_panel(sm_frame)

        self._selected_match: Optional[DnaMatch] = None

    def _build_shared_panel(self, parent):
        """Panel für Shared Matches des ausgewählten primären Matches."""
        # Toolbar
        tb = ttk.Frame(parent); tb.pack(fill="x", padx=6, pady=4)
        self._sm_count_var = tk.StringVar(value="Kein Match ausgewählt.")
        ttk.Label(tb, textvariable=self._sm_count_var,
                  foreground=COLORS["primary"]).pack(side="left")

        # Tabelle
        cols = ("name","cm","cmab","rel")
        self._sm_tree = ttk.Treeview(parent, columns=cols, show="headings",
                                      selectmode="browse", height=14)
        for col, (lbl, w, anchor) in {
            "name": ("Shared Match",     170, "w"),
            "cm"  : ("cM mit dir",        75, "e"),
            "cmab": ("cM mit Match",      80, "e"),
            "rel" : ("Beziehung zu dir", 130, "w"),
        }.items():
            self._sm_tree.heading(col, text=lbl)
            self._sm_tree.column(col, width=w, anchor=anchor, stretch=(col=="name"))

        sy = ttk.Scrollbar(parent, orient="vertical", command=self._sm_tree.yview)
        self._sm_tree.configure(yscrollcommand=sy.set)
        self._sm_tree.pack(side="left", fill="both", expand=True, padx=(6,0), pady=4)
        sy.pack(side="right", fill="y", pady=4)

    def _refresh_match_table(self, *_):
        try:
            min_cm = float(self._min_cm_var.get() or 0)
        except ValueError:
            min_cm = 0.0

        rels = self._db.get_distinct_relationships()
        self._rel_combo["values"] = ["(alle)"] + rels

        col_map = {"name":"display_name","guid":"match_guid","note":"tag_surname",
                   "cm":"shared_cm","seg":"shared_segments",
                   "rel":"predicted_relationship","tree":"tree_size",
                   "ca":"has_common_ancestor","starred":"starred"}
        sort_col = col_map.get(self._sort_col, "shared_cm")

        self._matches = self._db.get_matches(
            search        = self._search_var.get().strip() or None,
            relationship  = self._rel_var.get() if hasattr(self,"_rel_var") else None,
            starred_only  = self._starred_var.get() if hasattr(self,"_starred_var") else False,
            has_tree_only = self._tree_var.get() if hasattr(self,"_tree_var") else False,
            min_cm        = min_cm,
            sort_col      = sort_col,
            sort_asc      = self._sort_asc,
        )
        self._match_count_var.set(f"{len(self._matches)} Match(es)")
        self._tree.delete(*self._tree.get_children())
        for m in self._matches:
            tags = []
            if m.starred: tags.append("starred")
            if m.predicted_relationship.lower() in (
                "parent","child","sibling","aunt/uncle","first cousin",
                "1st cousin","half sibling","close"): tags.append("close")
            if not m.has_tree: tags.append("no_tree")

            # Stammbaum-Spalte: Status (+ Personenzahl falls vorhanden)
            status = getattr(m, "tree_status", "") or ""
            if status and m.tree_size:
                tree_txt = f"{status} ({m.tree_size})"
            elif status:
                tree_txt = status
            elif m.has_tree:
                tree_txt = f"✓ ({m.tree_size})" if m.tree_size else "✓"
            else:
                tree_txt = "—"

            self._tree.insert("", "end", iid=m.match_guid, tags=tags, values=(
                m.display_name,
                m.match_guid[:8],
                m.tag_surname or "",
                f"{m.shared_cm:.1f}" if m.shared_cm else "—",
                m.shared_segments or "—",
                m.predicted_relationship or "—",
                tree_txt,
                "👪" if getattr(m, "has_common_ancestor", False) else "—",
                "⭐" if m.starred else "",
            ))

    def _on_match_rightclick(self, event):
        """Kontextmenü bei Rechtsklick auf einen Match."""
        item = self._tree.identify_row(event.y)
        if not item:
            return
        self._tree.selection_set(item)
        match = next((m for m in self._matches if m.match_guid == item), None)
        if not match:
            return

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="🔗 In Ancestry öffnen",
            command=self._open_in_ancestry)
        menu.add_command(
            label="📋 Match-GUID kopieren",
            command=lambda: (self.clipboard_clear(),
                             self.clipboard_append(match.match_guid)))
        menu.add_separator()
        menu.add_command(
            label="⭐ Als Mutterseite markieren",
            command=lambda: self._set_custom_rel(match, "maternal"))
        menu.add_command(
            label="⭐ Als Vaterseite markieren",
            command=lambda: self._set_custom_rel(match, "paternal"))
        menu.add_command(
            label="✏️  Name eintragen …",
            command=lambda: self._prompt_name(match))
        menu.tk_popup(event.x_root, event.y_root)

    def _set_custom_rel(self, match, rel: str):
        self._db.update_note(match.match_guid,
                             match.note or "")
        with self._db._cursor() as cur:
            cur.execute("UPDATE matches SET custom_relationship=? WHERE match_guid=?",
                        (rel, match.match_guid))
        self._set_status(f"{match.display_name} → {rel}")
        self._refresh_match_table()

    def _prompt_name(self, match):
        """Einfacher Dialog um einen Namen manuell einzutragen."""
        import tkinter.simpledialog as sd
        name = sd.askstring(
            "Name eintragen",
            "Name eintragen (cM: " + str(round(match.shared_cm)) + ")",
            initialvalue=match.display_name if match.display_name != "Anonym" else "",
            parent=self,
        )
        if name is not None and name.strip():
            with self._db._cursor() as cur:
                cur.execute("UPDATE matches SET display_name=? WHERE match_guid=?",
                            (name.strip(), match.match_guid))
            self._set_status(f"Name gespeichert: {name.strip()}")
            self._refresh_match_table()

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = col in ("name","rel")
        self._refresh_match_table()

    @staticmethod
    def _tree_detail_text(match) -> str:
        status = getattr(match, "tree_status", "") or ""
        if status and match.tree_size:
            return f"{status} ({match.tree_size} Personen)"
        if status:
            return status
        if match.has_tree:
            return f"Ja ({match.tree_size})" if match.tree_size else "Ja"
        return "Nein"

    def _on_match_select(self, _):
        sel = self._tree.selection()
        if not sel: return
        match = next((m for m in self._matches if m.match_guid == sel[0]), None)
        if not match: return
        self._selected_match = match

        # Detail-Felder befüllen
        self._detail_name_var.set(match.display_name)
        for lbl, val in [
            ("cM",             f"{match.shared_cm:.2f}"),
            ("Segmente",       str(match.shared_segments)),
            ("Längstes Seg.",  f"{match.longest_segment:.2f} cM"),
            ("Beziehung",      match.predicted_relationship or "—"),
            ("Konfidenz",      match.confidence or "—"),
            ("Stammbaum",      self._tree_detail_text(match)),
            ("Gem. Vorfahre",  "Ja 👪" if getattr(match, "has_common_ancestor", False) else "Nein"),
            ("Geschlecht",     {"M":"♂ männlich","F":"♀ weiblich"}.get(
                                   getattr(match, "gender", ""), "—")),
            ("Letzter Login",  match.last_login[:10] if match.last_login else "—"),
        ]:
            self._detail_fields[lbl].set(val)

        self._note_text.delete("1.0","end")
        self._note_text.insert("1.0", match.note or "")

        # Shared Matches laden
        self._load_shared_panel(match)

    def _load_shared_panel(self, match: DnaMatch):
        """Lädt Shared Matches für den ausgewählten primären Match."""
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        shared = self._db.get_shared_matches(test_guid, match.match_guid)
        self._sm_tree.delete(*self._sm_tree.get_children())

        if not shared:
            fetched = self._db.is_shared_fetched(test_guid, match.match_guid)
            self._sm_count_var.set(
                "Shared Matches wurden abgefragt, aber keine gefunden."
                if fetched else
                "Noch nicht heruntergeladen. → Tab »Herunterladen« → Schritt B"
            )
            return

        self._sm_count_var.set(f"{len(shared)} Shared Match(es) mit {match.display_name}")
        for sm in shared:
            self._sm_tree.insert("", "end", values=(
                sm.display_name_b or "(unbekannt)",
                f"{sm.shared_cm_b:.0f}" if sm.shared_cm_b else "—",
                f"{sm.shared_cm_ab:.0f}" if sm.shared_cm_ab else "—",
                sm.relationship_b or "—",
            ))

    def _open_in_ancestry(self):
        """Öffnet den aktuellen Match in Ancestry im Browser."""
        if not self._selected_match:
            return
        test_guid  = self._current_test_guid or self._get_kit_guid()
        match_guid = self._selected_match.match_guid
        if not test_guid or not match_guid:
            return
        import webbrowser
        url = (f"https://www.ancestry.com/discoveryui-matches/compare"
               f"/{test_guid}/with/{match_guid}")
        webbrowser.open(url)
        self._set_status(f"Ancestry geöffnet: {self._selected_match.display_name}")

    def _save_note(self):
        if not self._selected_match: return
        note = self._note_text.get("1.0","end").strip()
        self._db.update_note(self._selected_match.match_guid, note)
        self._selected_match.note = note
        self._set_status(f"Notiz gespeichert: {self._selected_match.display_name}")

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4: CLUSTER
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_cluster(self):
        f = self._tab_cluster

        # Einstellungen
        cf = ttk.Frame(f); cf.pack(fill="x", padx=14, pady=8)
        ttk.Label(cf, text="Primäre cM von:").pack(side="left")
        self._cluster_min_cm_var = tk.StringVar(value="20")
        ttk.Entry(cf, textvariable=self._cluster_min_cm_var, width=6).pack(side="left", padx=6)
        ttk.Label(cf, text="bis:").pack(side="left", padx=(4,4))
        self._cluster_max_cm_var = tk.StringVar(value="400")
        ttk.Entry(cf, textvariable=self._cluster_max_cm_var, width=6).pack(side="left")
        ttk.Label(cf, text="Min. cM Shared:").pack(side="left", padx=(14,4))
        self._cluster_shared_cm_var = tk.StringVar(value="20")
        ttk.Entry(cf, textvariable=self._cluster_shared_cm_var, width=6).pack(side="left")
        ttk.Button(cf, text="🔄 Cluster berechnen",
                   command=self._refresh_cluster).pack(side="left", padx=14)
        self._cluster_count_var = tk.StringVar(value="")
        ttk.Label(cf, textvariable=self._cluster_count_var,
                  foreground=COLORS["primary"]).pack(side="left")

        # Interpretation
        self._cluster_text_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self._cluster_text_var,
                  foreground="#444466", font=("Segoe UI", 9),
                  wraplength=900, justify="left").pack(anchor="w", padx=14, pady=(0,6))

        # Pane: Cluster-Liste + Mitglieder
        pane = ttk.PanedWindow(f, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=14, pady=4)

        # Linke Seite: Cluster-Liste
        left = ttk.LabelFrame(pane, text="Cluster", padding=6)
        pane.add(left, weight=1)
        self._cluster_list = ttk.Treeview(left, columns=("cid","count","max_cm","top"),
                                           show="headings", selectmode="browse")
        for col, (lbl, w) in {
            "cid"    : ("Cluster", 55),
            "count"  : ("Matches",  60),
            "max_cm" : ("Max cM",   70),
            "top"    : ("Top-Match",200),
        }.items():
            self._cluster_list.heading(col, text=lbl)
            self._cluster_list.column(col, width=w, stretch=(col=="top"))
        sy1 = ttk.Scrollbar(left, orient="vertical", command=self._cluster_list.yview)
        self._cluster_list.configure(yscrollcommand=sy1.set)
        self._cluster_list.pack(side="left", fill="both", expand=True)
        sy1.pack(side="right", fill="y")
        self._cluster_list.bind("<<TreeviewSelect>>", self._on_cluster_select)

        # Rechte Seite: Mitglieder
        right = ttk.LabelFrame(pane, text="Cluster-Mitglieder", padding=6)
        pane.add(right, weight=2)
        self._member_tree = ttk.Treeview(right, columns=("name","cm","rel"),
                                          show="headings", selectmode="browse")
        for col, (lbl, w, anchor) in {
            "name": ("Name",    240, "w"),
            "cm"  : ("cM",      70, "e"),
            "rel" : ("Beziehung",160,"w"),
        }.items():
            self._member_tree.heading(col, text=lbl)
            self._member_tree.column(col, width=w, anchor=anchor, stretch=(col=="name"))
        sy2 = ttk.Scrollbar(right, orient="vertical", command=self._member_tree.yview)
        self._member_tree.configure(yscrollcommand=sy2.set)
        self._member_tree.pack(side="left", fill="both", expand=True)
        sy2.pack(side="right", fill="y")

        self._clusters: dict = {}

    def _refresh_cluster(self):
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return
        try:
            min_prim   = float(self._cluster_min_cm_var.get() or 20)
            max_prim   = float(self._cluster_max_cm_var.get() or 400)
            min_shared = float(self._cluster_shared_cm_var.get() or 20)
        except ValueError:
            min_prim, max_prim, min_shared = 20.0, 400.0, 20.0

        shared_data = self._db.get_all_shared_for_cluster(
            test_guid, min_prim, min_shared,
            max_cm_primary=max_prim, max_cm_shared=max_prim)
        if not shared_data:
            messagebox.showinfo("Keine Daten",
                                "Keine Shared Matches im gewählten cM-Bereich.\n\n"
                                "Mögliche Ursachen:\n"
                                "• Noch keine Shared Matches heruntergeladen "
                                "(Tab Herunterladen → B)\n"
                                f"• Keine primären Matches zwischen {min_prim:.0f} "
                                f"und {max_prim:.0f} cM — Bereich anpassen.")
            return

        self._clusters = build_clusters(shared_data, min_prim, min_shared,
                                        max_cm_primary=max_prim)
        self._cluster_count_var.set(f"{len(self._clusters)} Cluster")
        self._cluster_text_var.set(suggest_grandparent_lines(self._clusters))

        # Cluster-Liste füllen
        self._cluster_list.delete(*self._cluster_list.get_children())
        cluster_colors = COLORS["cluster"]
        for cid, members in self._clusters.items():
            cms   = [m["cm"] for m in members]
            color = cluster_colors[(cid - 1) % len(cluster_colors)]
            self._cluster_list.insert("", "end", iid=str(cid),
                                       tags=(f"c{cid}",),
                                       values=(f"#{cid}", len(members),
                                               f"{max(cms):.0f}",
                                               members[0]["name"] if members else ""))
            self._cluster_list.tag_configure(f"c{cid}", background=color)

        self._member_tree.delete(*self._member_tree.get_children())

    def _on_cluster_select(self, _):
        sel = self._cluster_list.selection()
        if not sel: return
        cid = int(sel[0])
        members = self._clusters.get(cid, [])
        self._member_tree.delete(*self._member_tree.get_children())
        color = COLORS["cluster"][(cid - 1) % len(COLORS["cluster"])]
        self._member_tree.tag_configure("row", background=color)
        for m in members:
            self._member_tree.insert("", "end", tags=("row",),
                                      values=(m["name"], f"{m['cm']:.1f}", m.get("rel","")))

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 5: STATISTIKEN
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tab_stats(self):
        f = self._tab_stats
        ttk.Button(f, text="↻ Aktualisieren",
                   command=self._refresh_stats).pack(anchor="ne", padx=14, pady=8)

        kz = ttk.LabelFrame(f, text="Kennzahlen", padding=10)
        kz.pack(fill="x", padx=14, pady=4)

        self._stat_vars: dict[str, tk.StringVar] = {}
        labels = [
            ("total",              "Gesamtzahl Matches"),
            ("max_cm",             "Höchste cM"),
            ("avg_cm",             "Ø cM"),
            ("starred_count",      "Markierte"),
            ("with_tree",          "Mit Stammbaum"),
            ("with_note",          "Mit Notiz"),
            ("shared_total",       "Shared-Match-Einträge"),
            ("shared_primary_count","Primäre m. Shared"),
        ]
        for i, (key, lbl) in enumerate(labels):
            ttk.Label(kz, text=lbl + ":", foreground="#555555").grid(
                row=i // 4, column=(i % 4) * 2, sticky="e", padx=(14,4), pady=3)
            var = tk.StringVar(value="—")
            ttk.Label(kz, textvariable=var, font=("Segoe UI", 10, "bold"),
                      foreground=COLORS["primary"]).grid(
                row=i // 4, column=(i % 4) * 2 + 1, sticky="w")
            self._stat_vars[key] = var

        rf = ttk.LabelFrame(f, text="Beziehungsverteilung (Top 10)", padding=10)
        rf.pack(fill="both", expand=True, padx=14, pady=4)
        self._rel_tree = ttk.Treeview(rf, columns=("rel","count"), show="headings", height=10)
        self._rel_tree.heading("rel",   text="Beziehung")
        self._rel_tree.heading("count", text="Anzahl")
        self._rel_tree.column("rel",    width=300)
        self._rel_tree.column("count",  width=80, anchor="e")
        self._rel_tree.pack(fill="both", expand=True)
        self._refresh_stats()

    def _refresh_stats(self):
        stats = self._db.get_statistics()
        for key, var in self._stat_vars.items():
            v = stats.get(key)
            var.set(f"{v:.1f}" if isinstance(v, float) else str(v) if v is not None else "—")
        self._rel_tree.delete(*self._rel_tree.get_children())
        for rel, cnt in stats.get("relationship_breakdown", []):
            self._rel_tree.insert("", "end", values=(rel, cnt))

    # ─────────────────────────────────────────────────────────────────────────
    # Export
    # ─────────────────────────────────────────────────────────────────────────

    def _export_csv(self):
        matches = self._db.get_matches()
        if not matches:
            messagebox.showinfo("Keine Daten", "Keine Matches vorhanden.")
            return
        p = filedialog.asksaveasfilename(title="Matches als CSV",
            defaultextension=".csv", filetypes=[("CSV","*.csv"),("Alle","*.*")],
            initialfile="ancestry_dna_matches.csv")
        if p:
            export_csv(matches, p)
            messagebox.showinfo("Fertig", f"{len(matches)} Matches → {p}")

    def _export_shared_csv(self):
        test_guid = self._current_test_guid or self._get_kit_guid()
        if not test_guid:
            messagebox.showwarning("Kein Kit", "Bitte DNA-Kit auswählen.")
            return
        with self._db._cursor() as cur:
            cur.execute("SELECT * FROM shared_matches WHERE test_guid=? ORDER BY shared_cm_b DESC",
                        (test_guid,))
            rows = cur.fetchall()
        if not rows:
            messagebox.showinfo("Keine Daten", "Keine Shared Matches in der Datenbank.")
            return
        from models import SharedMatch
        shared = [SharedMatch.from_db_row(dict(r)) for r in rows]
        matches = {m.match_guid: m.display_name for m in self._db.get_matches(test_guid=test_guid)}

        p = filedialog.asksaveasfilename(title="Shared Matches als CSV",
            defaultextension=".csv", filetypes=[("CSV","*.csv"),("Alle","*.*")],
            initialfile="ancestry_shared_matches.csv")
        if p:
            export_shared_csv(shared, p, matches)
            messagebox.showinfo("Fertig", f"{len(shared)} Shared Matches → {p}")

    def _export_xlsx(self):
        matches = self._db.get_matches()
        if not matches:
            messagebox.showinfo("Keine Daten", "Keine Matches vorhanden.")
            return
        p = filedialog.asksaveasfilename(title="Matches als XLSX",
            defaultextension=".xlsx", filetypes=[("XLSX","*.xlsx"),("Alle","*.*")],
            initialfile="ancestry_dna_matches.xlsx")
        if p:
            export_xlsx(matches, p)
            messagebox.showinfo("Fertig", f"{len(matches)} Matches → {p}")

    def _export_all_xlsx(self):
        test_guid = self._current_test_guid or self._get_kit_guid()
        matches = self._db.get_matches(test_guid=test_guid)
        if not matches:
            messagebox.showinfo("Keine Daten", "Keine Matches vorhanden.")
            return
        shared, name_map = [], {}
        if test_guid:
            with self._db._cursor() as cur:
                cur.execute("SELECT * FROM shared_matches WHERE test_guid=? ORDER BY shared_cm_b DESC",
                            (test_guid,))
                from models import SharedMatch
                shared = [SharedMatch.from_db_row(dict(r)) for r in cur.fetchall()]
            name_map = {m.match_guid: m.display_name for m in matches}

        p = filedialog.asksaveasfilename(title="Alles als XLSX exportieren",
            defaultextension=".xlsx", filetypes=[("XLSX","*.xlsx"),("Alle","*.*")],
            initialfile="ancestry_dna_komplett.xlsx")
        if p:
            export_xlsx(matches, p, shared if shared else None, name_map)
            messagebox.showinfo("Fertig",
                                f"{len(matches)} Matches + {len(shared)} Shared Matches → {p}")

    # ─────────────────────────────────────────────────────────────────────────
    # Hilfsmethoden
    # ─────────────────────────────────────────────────────────────────────────

    def _import_names(self):
        """
        Importiert Namen aus JSON (Browser-DOM-Export).
        Filtert Rausch-Eintraege wie "This match is connected..." heraus.
        Dedupliziert pro sampleId: bester Name gewinnt.
        """
        path = filedialog.askopenfilename(
            title="Namen-Datei importieren",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv"), ("Alle", "*.*")],
        )
        if not path:
            return

        import json, csv, re

        # Muster die KEIN echter Name sind
        NOISE_PATTERNS = [
            "this match is connected",
            "public linked tree",
            "unlinked tree",
            "private tree",
            "no tree",
        ]

        def is_noise(name: str) -> bool:
            n = name.lower().strip()
            return any(n.startswith(p) for p in NOISE_PATTERNS)

        def name_quality(name: str) -> int:
            """Hoehere Zahl = besserer Name. Echter Name > Benutzername > Initialen."""
            if is_noise(name):
                return -1
            # Initialen wie "J. M." = niedrige Qualitaet
            if re.match(r'^[A-Z]\.\s+[A-Z]\.$', name.strip()):
                return 1
            # Echter Name (Vor- + Nachname) = hohe Qualitaet
            if ' ' in name and not name.startswith('@'):
                return 3
            return 2  # Benutzername

        # Einlesen
        raw: list[tuple[str, str]] = []
        try:
            if path.lower().endswith(".json"):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # Listen-Format: [{"sampleId": "...", "name": "..."}, ...]
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        sid  = (item.get("sampleId") or item.get("sample_id")
                                or item.get("guid", "")).strip()
                        name = (item.get("name") or item.get("displayName")
                                or item.get("matchName") or item.get("managedName")
                                or "").strip()
                        if sid and name:
                            raw.append((sid, name))
                elif isinstance(data, dict):
                    # Dict-Format (profileData-Antwort):
                    #   {"<sid>": {"matchName": "...", "managedName": "..."}, ...}
                    #   oder {"<sid>": "Name", ...}
                    for sid, info in data.items():
                        sid = (sid or "").strip()
                        if isinstance(info, dict):
                            name = (info.get("matchName") or info.get("managedName")
                                    or info.get("name") or info.get("displayName")
                                    or "").strip()
                        else:
                            name = str(info or "").strip()
                        if sid and name:
                            raw.append((sid, name))
            else:
                with open(path, encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        sid  = (row.get("sampleId") or row.get("match_guid", "")).strip()
                        name = (row.get("name") or row.get("display_name", "")).strip()
                        if sid and name:
                            raw.append((sid, name))
        except Exception as e:
            messagebox.showerror("Import-Fehler", str(e))
            return

        # Deduplizieren: bester Name pro sampleId
        best: dict[str, tuple[str, int]] = {}
        for sid, name in raw:
            q = name_quality(name)
            if q < 0:
                continue
            if sid not in best or q > best[sid][1]:
                best[sid] = (name, q)

        if not best:
            messagebox.showinfo("Kein Ergebnis",
                                "Keine gueltigen Namen gefunden.")
            return

        # In DB schreiben. Ueberschrieben werden nur Platzhalter:
        # leer/Anonym/NULL, Gender-Suffixe und das 8-stellige GUID-Kuerzel
        # (z.B. "BEC4AE66"), das matchList ohne echten Namen speichert.
        # Manuell eingetragene echte Namen bleiben unangetastet.
        HEX8 = "[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]" \
               "[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]"
        updated = skipped = 0
        with self._db._cursor() as cur:
            for sid, (name, _) in best.items():
                cur.execute(
                    "UPDATE matches SET display_name=? "
                    "WHERE match_guid=? "
                    "AND (display_name='' OR display_name='Anonym' "
                    "     OR display_name IS NULL "
                    "     OR display_name LIKE '% (m.)' "
                    "     OR display_name LIKE '% (w.)' "
                    f"     OR display_name GLOB '{HEX8}')",
                    (name, sid)
                )
                if cur.rowcount:
                    updated += 1
                else:
                    skipped += 1

        self._refresh_match_table()
        msg = (str(len(raw)) + " Roheintraege, "
               + str(len(best)) + " eindeutige Matches, "
               + str(updated) + " aktualisiert"
               + (" (" + str(skipped) + " uebersprungen)" if skipped else ""))
        messagebox.showinfo("Import abgeschlossen", msg)
        self._set_status("Namen: " + str(updated) + " importiert")


    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _get_kit_guid(self) -> Optional[str]:
        return self._kit_map.get(self._kit_var.get()) if hasattr(self,"_kit_var") else None

    def _show_about(self):
        messagebox.showinfo("Über",
            "Ancestry DNA Tool v2\n\n"
            "Features: Matches + Shared Matches + Leeds-Clustering\n"
            "Datenbank: " + cfg.DB_FILE)

    # ── Persistente Einstellungen ──────────────────────────────────────────────

    def _load_settings(self):
        """Lädt gespeicherte Einstellungen (Cookie-Pfad, Kit-GUID)."""
        import json, os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'settings.json')
        try:
            with open(path, encoding='utf-8') as f:
                s = json.load(f)
            if s.get('cookie_file'):
                self._cookie_file_var.set(s['cookie_file'])
            if s.get('manual_guid'):
                self._manual_guid_var.set(s['manual_guid'])
                # Automatisch als Kit registrieren
                guid = s['manual_guid']
                name = 'Gespeichertes Kit (' + guid[:8] + '...)'
                self._kit_map[name] = guid
                self._update_kit_combo()
                self._current_test_guid = guid
            if s.get('last_kit_name') and s['last_kit_name'] in self._kit_map:
                self._kit_var.set(s['last_kit_name'])
            self._set_status('Einstellungen geladen.')
        except (FileNotFoundError, Exception):
            pass

    def _save_settings(self):
        """Speichert aktuelle Einstellungen."""
        import json, os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'settings.json')
        s = {
            'cookie_file' : self._cookie_file_var.get(),
            'manual_guid' : self._manual_guid_var.get(),
            'last_kit_name': self._kit_var.get(),
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning('Einstellungen konnten nicht gespeichert werden: %s', e)

    def _on_close(self):
        if self._scraper and self._scraper.is_running():
            if not messagebox.askyesno("Beenden?", "Download läuft noch. Wirklich beenden?"):
                return
            self._scraper.stop()
        self._save_settings()
        self._db.close()
        self.destroy()
