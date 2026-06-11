"""LoginTabMixin – Tab 1: Login-Logik für AncestryDnaApp."""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ancestry.core.auth import AncestryAuth
from ancestry.core.api import AncestryApiClient
from ancestry.models import DnaKit


class LoginTabMixin:
    """Mixin mit allen Login-Tab-Methoden für AncestryDnaApp."""

    def _build_tab_login(self):
        f = self._tab_login
        p = {"padx": 16, "pady": 8}

        _sv = tk.StringVar(value=self._t("lg.meth1"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.meth1"))

        _sv = tk.StringVar(value=self._t("lg.email"))
        ttk.Label(f, textvariable=_sv).grid(row=1, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.email"))
        self._email_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._email_var, width=36).grid(row=1, column=1, sticky="w", **p)

        _sv = tk.StringVar(value=self._t("lg.password"))
        ttk.Label(f, textvariable=_sv).grid(row=2, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.password"))
        self._pw_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._pw_var, show="•", width=36).grid(row=2, column=1, sticky="w", **p)

        _sv = tk.StringVar(value=self._t("lg.login_btn"))
        ttk.Button(f, textvariable=_sv, command=self._do_login).grid(row=3, column=1, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.login_btn"))

        ttk.Separator(f, orient="horizontal").grid(row=4, column=0, columnspan=3,
                                                    sticky="ew", padx=16, pady=12)

        _sv = tk.StringVar(value=self._t("lg.meth2"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=5, column=0, columnspan=3, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.meth2"))
        ttk.Label(f, text=(
            "1. Chrome/Firefox-Extension »Cookie-Editor« installieren\n"
            "2. Auf ancestry.com einloggen\n"
            "3. Cookie-Editor → Export → JSON → speichern\n"
            "4. Datei hier auswählen"
        ), foreground="#555555").grid(row=6, column=0, columnspan=3, sticky="w", padx=16)
        self._cookie_file_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._cookie_file_var, width=36,
                  state="readonly").grid(row=7, column=1, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("lg.choose"))
        ttk.Button(f, textvariable=_sv,
                   command=self._choose_cookie_file).grid(row=7, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.choose"))
        _sv = tk.StringVar(value=self._t("lg.login_ck"))
        ttk.Button(f, textvariable=_sv,
                   command=self._do_login_cookies).grid(row=8, column=1, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.login_ck"))

        ttk.Separator(f, orient="horizontal").grid(row=9, column=0, columnspan=3,
                                                    sticky="ew", padx=16, pady=12)
        _sv = tk.StringVar(value=self._t("lg.manual"))
        ttk.Label(f, textvariable=_sv,
                  style="Bold.TLabel").grid(row=10, column=0, columnspan=3, sticky="w", **p)
        self._lang_widgets.append((_sv, "lg.manual"))
        ttk.Label(f, text="URL: ancestry.com/dna/tests/<GUID>/matches",
                  foreground="#555555").grid(row=11, column=0, columnspan=3, sticky="w", padx=16)
        self._manual_guid_var = tk.StringVar()
        ttk.Entry(f, textvariable=self._manual_guid_var, width=44).grid(
            row=12, column=1, sticky="w", **p)
        _sv = tk.StringVar(value=self._t("lg.use_guid"))
        ttk.Button(f, textvariable=_sv,
                   command=self._use_manual_guid).grid(row=12, column=0, sticky="e", **p)
        self._lang_widgets.append((_sv, "lg.use_guid"))

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
        self._set_status("Kit-GUID gespeichert.")

    def _set_login_status(self, msg, success=True):
        self._login_status_var.set(msg)
        self._login_status_lbl.configure(
            style="Success.TLabel" if success else "Warning.TLabel")
