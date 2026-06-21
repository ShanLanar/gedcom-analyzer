"""Login-Tab: Passwort- und Cookie-Login für das Ancestry-DNA-Tool."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from ancestry.core.api import AncestryApiClient
from ancestry.core.auth import AncestryAuth
from ancestry.core.cookie_capture import capture_from_chrome, capture_from_firefox
from ancestry.gui.state import AppState
from ancestry.gui.widgets.theme import register_lang
from ancestry.gui.widgets.tooltip import register_tooltip
from ancestry.models import DnaKit


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

        # ── Cookie-Datei-Login ─────────────────────────────────────────────
        _sv = tk.StringVar(value=t("lg.meth2"))
        ttk.Label(f, textvariable=_sv, style="Bold.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", **p)
        lw.append((_sv, "lg.meth2"))
        register_lang(self._state, ttk.Label(f, text=(
            self._state.t("lg.cookie_steps")
        ), foreground="#555555"), "lg.cookie_steps").grid(row=6, column=0, columnspan=3, sticky="w", padx=16)
        # Drop-Zone für Cookie-JSON (optionales tkinterdnd2; fallback: reguläres Entry)
        try:
            import tkinterdnd2 as _dnd
            _dnd_ok = True
        except ImportError:
            _dnd_ok = False

        if _dnd_ok:
            drop_lbl = tk.Label(
                f, textvariable=self._cookie_file_var,
                width=36, anchor="w", relief="groove",
                bg="#2a2a3e", fg="#A0D0FF", cursor="hand2",
                font=("Consolas", 9),
            )
            drop_lbl.grid(row=7, column=1, sticky="ew", **p)
            try:
                drop_lbl.drop_target_register(_dnd.DND_FILES)
                drop_lbl.dnd_bind("<<Drop>>", self._on_file_drop)
            except Exception:
                pass
            self._drop_widget: tk.Widget = drop_lbl
        else:
            _entry = ttk.Entry(f, textvariable=self._cookie_file_var, width=36,
                               state="readonly")
            _entry.grid(row=7, column=1, sticky="w", **p)
            self._drop_widget = _entry

        _sv = tk.StringVar(value=t("lg.choose"))
        _b = ttk.Button(f, textvariable=_sv, command=self._choose_cookie_file)
        _b.grid(row=7, column=0, sticky="e", **p)
        register_tooltip(_b, "tt.lg_choose", self._state)
        lw.append((_sv, "lg.choose"))
        login_row = ttk.Frame(f)
        login_row.grid(row=8, column=1, sticky="w", **p)
        _sv = tk.StringVar(value=t("lg.login_ck"))
        _b = ttk.Button(login_row, textvariable=_sv, command=self._do_login_cookies)
        _b.pack(side="left", padx=(0, 8))
        register_tooltip(_b, "tt.lg_login", self._state)
        lw.append((_sv, "lg.login_ck"))
        ttk.Button(
            login_row, text="🌐 Chrome",
            command=self._capture_chrome,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            login_row, text="🦊 Firefox",
            command=self._capture_firefox,
        ).pack(side="left")

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
        _b = ttk.Button(f, textvariable=_sv, command=self._use_manual_guid)
        _b.grid(row=12, column=0, sticky="e", **p)
        register_tooltip(_b, "tt.lg_guid", self._state)
        lw.append((_sv, "lg.use_guid"))

        self._status_var = tk.StringVar(value="Nicht eingeloggt.")
        self._status_lbl = ttk.Label(f, textvariable=self._status_var,
                                     style="Warning.TLabel")
        self._status_lbl.grid(row=13, column=0, columnspan=3, **p)
        f.columnconfigure(1, weight=1)

    # ── Browser-Capture ───────────────────────────────────────────────────────

    def _capture_chrome(self):
        self.set_status("🌐 Chrome wird gestartet …", success=True)
        threading.Thread(target=self._run_capture, args=("chrome",), daemon=True).start()

    def _capture_firefox(self):
        self.set_status("🦊 Firefox-Cookies werden gelesen …", success=True)
        threading.Thread(target=self._run_capture, args=("firefox",), daemon=True).start()

    def _run_capture(self, backend: str):
        from ancestry.core.cookie_capture import _default_save_path
        # Reuse the already-configured path so refreshed cookies land in the same file
        existing = self._cookie_file_var.get().strip()
        save_path = existing if (existing and os.path.isdir(os.path.dirname(existing))) \
            else str(_default_save_path("ancestry"))

        def _status(msg: str):
            self.after(0, lambda m=msg: self.set_status(m, success=not m.startswith("❌")))

        if backend == "chrome":
            ok = capture_from_chrome("ancestry", save_path, _status)
        else:
            ok = capture_from_firefox("ancestry", save_path, _status)

        if ok:
            self.after(0, lambda p=save_path: self._on_capture_done(p))

    def _on_capture_done(self, save_path: str):
        self._cookie_file_var.set(save_path)
        self.set_status("✅ Cookies importiert — Login wird gestartet …", success=True)
        self._do_login_cookies()

    # ── Drag-and-Drop ─────────────────────────────────────────────────────────

    def _on_file_drop(self, event):
        path = event.data.strip().strip("{}")
        if os.path.isfile(path) and path.lower().endswith(".json"):
            self._cookie_file_var.set(path)
            self._status_var.set("Datei eingelesen — bitte »Cookie-Login« klicken.")
        else:
            self._status_var.set("Bitte eine .json-Cookie-Datei einwerfen.")

    # ── Login-Logik ───────────────────────────────────────────────────────────

    def _do_login_cookies(self):
        path = self._cookie_file_var.get().strip()
        if not path:
            messagebox.showwarning(self._state.t("lg.no_file_t"), self._state.t("lg.m_choose_cookie"))
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
        try:
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
        except Exception as e:
            self.after(0, lambda err=str(e): self.set_status(
                f"❌ Login fehlgeschlagen: {err}", success=False))

    def _login_done(self, auth: AncestryAuth, client: AncestryApiClient, kits: list):
        uid = auth.uid or "?"
        self.set_status(
            f"✅ Eingeloggt (UID: {uid[:16]}…) | {len(kits)} Kit(s)", success=True)
        self._on_login_success(auth, client, kits)
        self._on_status("Login erfolgreich.")
        self._on_switch_tab(1)

    def _choose_cookie_file(self):
        p = filedialog.askopenfilename(title=self._state.t("lg.t_cookie"),
                                       filetypes=[("JSON", "*.json"), ("Alle", "*.*")])
        if p:
            self._cookie_file_var.set(p)

    def _use_manual_guid(self):
        guid = self._manual_guid_var.get().strip()
        if not guid:
            messagebox.showwarning(self._state.t("lg.no_guid_t"), self._state.t("lg.m_enter_guid"))
            return
        name = f"Manuell ({guid[:8]}…)"
        self._state.kit_map[name] = guid
        self._on_login_success(None, None, [])
        self.set_status(f"✅ Kit-GUID gespeichert ({guid[:8]}…)", success=True)
        self._on_status("Kit-GUID gespeichert.")
        self._on_switch_tab(1)

    def set_status(self, msg: str, success: bool = True):
        self._status_var.set(msg)
        self._status_lbl.configure(style="Success.TLabel" if success else "Warning.TLabel")
