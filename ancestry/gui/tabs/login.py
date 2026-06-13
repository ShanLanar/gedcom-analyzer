"""Login-Tab: Passwort- und Cookie-Login für das Ancestry-DNA-Tool."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ancestry.core.auth import AncestryAuth
from ancestry.core.api import AncestryApiClient
from ancestry.models import DnaKit
from ancestry.gui.state import AppState


class LoginTab(ttk.Frame):
    """Login-Tab des Ancestry-DNA-Tools.

    Parameters
    ----------
    parent:
        ttk.Frame aus dem Notebook.
    state:
        Gemeinsamer App-Zustand.
    on_login_success:
        Callback nach erfolgreichem Login: ``(auth, client, kits) -> None``.
    on_status:
        Callback für die App-Statuszeile: ``(msg: str) -> None``.
    on_switch_tab:
        Callback um den Notebook-Tab zu wechseln: ``(index: int) -> None``.
    """

    def __init__(
        self,
        parent: tk.Widget,
        state: AppState,
        on_login_success: Callable,
        on_status: Callable[[str], None],
        on_switch_tab: Callable[[int], None],
        cookie_var: Optional[tk.StringVar] = None,
        guid_var: Optional[tk.StringVar] = None,
        auto_login: bool = True,
    ):
        super().__init__(parent)
        self._state           = state
        self._on_login_success = on_login_success
        self._on_status        = on_status
        self._on_switch_tab    = on_switch_tab
        # Optional von der App geteilte Vars (Persistenz über settings.json)
        self._cookie_file_var = cookie_var if cookie_var is not None else tk.StringVar()
        self._manual_guid_var = guid_var if guid_var is not None else tk.StringVar()
        self._auto_login      = auto_login
        self._auto_login_done = False
        self._build()
        # Auto-Login, sobald eine Cookie-JSON hinterlegt ist. Verzögert, damit
        # _load_settings der App den gespeicherten Pfad zuerst setzen kann
        # (läuft dort ~200 ms nach Start).
        if self._auto_login:
            self.after(1000, self._maybe_auto_login)

    # ── Aufbau ───────────────────────────────────────────────────────────────

    def _build(self):
        f  = self
        t  = self._state.t
        lw = self._state.lang_widgets
        p  = {"padx": 16, "pady": 8}

        _sv = tk.StringVar(value=t("lg.meth2"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", **p)
        lw.append((_sv, "lg.meth2"))
        ttk.Label(f, text=(
            "1. Chrome/Firefox-Extension »Cookie-Editor« installieren\n"
            "2. Auf ancestry.com einloggen\n"
            "3. Cookie-Editor → Export → JSON → speichern\n"
            "4. Datei hier auswählen"
        ), foreground="#555555").grid(row=6, column=0, columnspan=3, sticky="w", padx=16)
        ttk.Entry(f, textvariable=self._cookie_file_var, width=36,
                  state="readonly").grid(row=7, column=1, sticky="w", **p)
        _sv = tk.StringVar(value=t("lg.choose"))
        ttk.Button(f, textvariable=_sv, command=self._choose_cookie_file).grid(
            row=7, column=0, sticky="e", **p)
        lw.append((_sv, "lg.choose"))
        _sv = tk.StringVar(value=t("lg.login_ck"))
        ttk.Button(f, textvariable=_sv, command=self._do_login_cookies).grid(
            row=8, column=1, sticky="w", **p)
        lw.append((_sv, "lg.login_ck"))

        ttk.Separator(f, orient="horizontal").grid(
            row=9, column=0, columnspan=3, sticky="ew", padx=16, pady=12)
        _sv = tk.StringVar(value=t("lg.manual"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(
            row=10, column=0, columnspan=3, sticky="w", **p)
        lw.append((_sv, "lg.manual"))
        ttk.Label(f, text="URL: ancestry.com/dna/tests/<GUID>/matches",
                  foreground="#555555").grid(row=11, column=0, columnspan=3, sticky="w", padx=16)
        ttk.Entry(f, textvariable=self._manual_guid_var, width=44).grid(
            row=12, column=1, sticky="w", **p)
        _sv = tk.StringVar(value=t("lg.use_guid"))
        ttk.Button(f, textvariable=_sv, command=self._use_manual_guid).grid(
            row=12, column=0, sticky="e", **p)
        lw.append((_sv, "lg.use_guid"))

        self._status_var = tk.StringVar(value="Nicht eingeloggt.")
        self._status_lbl = ttk.Label(f, textvariable=self._status_var,
                                     style="Warning.TLabel")
        self._status_lbl.grid(row=13, column=0, columnspan=3, **p)
        f.columnconfigure(1, weight=1)

    # ── Login-Logik ───────────────────────────────────────────────────────────

    def _do_login_cookies(self):
        path = self._cookie_file_var.get().strip()
        if not path:
            messagebox.showwarning("Keine Datei", "Bitte Cookie-Datei auswählen.")
            return
        threading.Thread(target=self._login_thread, args=(path, None, "cookie"),
                         daemon=True).start()

    def _maybe_auto_login(self):
        """Einmaliger Auto-Login beim Start, wenn eine Cookie-JSON hinterlegt ist.

        Liest den (ggf. erst nach dem Aufbau gesetzten) Cookie-Pfad live. Schlägt
        der Login fehl (z. B. abgelaufene Cookies), bleibt der manuelle Weg offen.
        """
        if self._auto_login_done:
            return
        path = self._cookie_file_var.get().strip()
        if not path or not os.path.exists(path):
            return
        self._auto_login_done = True
        self.set_status("🔄 Auto-Login mit gespeicherter Cookie-Datei …", success=True)
        threading.Thread(target=self._login_thread, args=(path, None, "cookie"),
                         daemon=True).start()

    def _login_thread(self, arg1, arg2, method):
        auth = AncestryAuth()
        ok = auth.login_password(arg1, arg2) if method == "password" else auth.login_cookies(arg1)
        if ok:
            client = AncestryApiClient(auth.get_session())
            kits: list[DnaKit] = []
            if auth.uid:
                kits = client.get_dna_kits(auth.uid)
                if not kits:
                    guid = client.detect_kit_from_uid(auth.uid)
                    if guid:
                        kits = [DnaKit(guid=guid, name="Mein DNA-Test")]
            self.after(0, lambda a=auth, c=client, k=kits: self._login_done(a, c, k))
        else:
            self.after(0, lambda: self.set_status("❌ Login fehlgeschlagen.", success=False))

    def _login_done(self, auth: AncestryAuth, client: AncestryApiClient, kits: list):
        uid = auth.uid or "?"
        self.set_status(
            f"✅ Eingeloggt (UID: {uid[:16]}…) | {len(kits)} Kit(s)", success=True)
        self._on_login_success(auth, client, kits)
        self._on_status("Login erfolgreich.")
        self._on_switch_tab(1)

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
        self._state.kit_map[name] = guid
        self._on_login_success(None, None, [])
        self._on_status("Kit-GUID gespeichert.")

    def set_status(self, msg: str, success: bool = True):
        self._status_var.set(msg)
        self._status_lbl.configure(style="Success.TLabel" if success else "Warning.TLabel")
