#!/usr/bin/env python3
"""
Genealogie-Suite — vereintes Hauptfenster (3 Reiter)

  🏠 Start        – Pfadeinstellungen, GEDCOM laden, DNA-Quellen, DB-Status
  🌳 Stammbaum    – GEDCOM-Analyzer (main.py / AhnenApp)
  🧬 DNA-Matches  – DNA-Match-Analyzer (ancestry/gui/app.py / AncestryDnaApp)

Die drei Reiter teilen dasselbe Dark-Theme (cfg-Farben).
GEDCOM-Pfad und Root-ID, die im Start-Tab gesetzt werden, werden live in
beide Analyse-Reiter propagiert.

Die drei Reiter teilen dasselbe Dark-Theme (cfg-Farben).
GEDCOM-Pfad und Root-ID, die im Start-Tab gesetzt werden, werden live in
beide Analyse-Reiter propagiert.
"""
from __future__ import annotations

import logging
import os
import sys
import importlib
import pkgutil
import traceback
import tkinter as tk
from tkinter import ttk

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.abspath(__file__))


# ── Import-Helfer ──────────────────────────────────────────────────────────────

def _eager_import_analyzer():
    """Lädt Root-config + alle tasks./lib.-Module."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import config as _root_config          # noqa: F401
    from config import apply_overrides
    apply_overrides()
    from main import AhnenApp

    for pkg in ("tasks", "lib"):
        pkg_dir = os.path.join(ROOT, pkg)
        if not os.path.isdir(pkg_dir):
            continue
        for mod in pkgutil.walk_packages([pkg_dir], prefix=f"{pkg}."):
            try:
                importlib.import_module(mod.name)
            except Exception as e:
                log.debug("Modul übersprungen %s: %s", mod.name, e)
    return AhnenApp


def _load_dna_app():
    """DNA-App laden (ancestry.endpoints statt config — kein Swap mehr nötig)."""
    from ancestry.gui.app import AncestryDnaApp
    return AncestryDnaApp


# ── Reiter-Fehlerplatzhalter ───────────────────────────────────────────────────

def _error_tab(parent: tk.Frame, title: str, exc: Exception) -> None:
    msg = f"⚠  {title}\n\n{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
    tk.Label(parent, text=msg, justify="left", fg="#ff5555",
             font=("Consolas", 9), wraplength=900, anchor="nw",
             bg="#1e1e2e").pack(fill="both", expand=True, padx=20, pady=20)


# ── Dark-Theme für ttk.Notebook ───────────────────────────────────────────────

def _apply_notebook_style(root: tk.Tk) -> None:
    """Färbt Notebook-Reiter im Dark-Theme ein."""
    # Farben direkt (vor config-Import, der tiefer im main-Block erfolgt)
    BG    = "#1e1e2e"
    BG2   = "#2a2a3e"
    BG3   = "#232336"
    ACC   = "#7c7cf8"   # noqa: F841
    FG    = "#cdd6f4"
    DIM   = "#6c7086"
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TNotebook",
                    background=BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab",
                    background=BG2, foreground=DIM,
                    padding=[14, 6], borderwidth=0,
                    font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", BG3), ("active", BG3)],
              foreground=[("selected", FG),  ("active", FG)],
              expand=[("selected", [0, 0, 0, 2])])
    style.configure("TFrame",   background=BG)
    style.configure("TLabel",   background=BG,  foreground=FG)
    style.configure("TCombobox",
                    fieldbackground=BG3, background=BG3,
                    foreground=FG, arrowcolor=FG)
    style.configure("Vertical.TScrollbar",
                    background=BG2, troughcolor=BG, arrowcolor=DIM, borderwidth=0)
    style.configure("Horizontal.TScrollbar",
                    background=BG2, troughcolor=BG, arrowcolor=DIM, borderwidth=0)
    style.configure("Accent.Horizontal.TProgressbar",
                    background=ACC, troughcolor=BG2, borderwidth=0)

    # Titelzeile & Fenster-Hintergrund
    root.configure(bg=BG)
    root.option_add("*Background",       BG)
    root.option_add("*Foreground",       FG)
    root.option_add("*Font",             "Segoe\\ UI 10")
    root.option_add("*highlightThickness", "0")


# ── Hauptfunktion ──────────────────────────────────────────────────────────────

def main():
    # ── Imports ────────────────────────────────────────────────────────────────
    AhnenApp = None
    _ahnen_exc: Exception = RuntimeError("not loaded")
    try:
        AhnenApp = _eager_import_analyzer()
        _ahnen_exc = None
    except Exception as exc:
        log.exception("Analyzer-Import fehlgeschlagen")
        _ahnen_exc = exc

    AncestryDnaApp = None
    _dna_exc: Exception = RuntimeError("not loaded")
    try:
        AncestryDnaApp = _load_dna_app()
        _dna_exc = None
    except Exception as exc:
        log.exception("DNA-App-Import fehlgeschlagen")
        _dna_exc = exc

    import config as cfg  # Root-config (Farben, Pfade)

    # ── Tk-Fenster ─────────────────────────────────────────────────────────────
    root = tk.Tk()
    root.title("Genealogie-Suite")
    root.geometry("1380x880")
    root.minsize(1100, 700)

    _apply_notebook_style(root)

    # ── Steuerleiste oben rechts (Theme-Umschalter) ────────────────────────────
    from lib import theming
    _theme = {"light": (cfg.DEFAULT_CONFIG.get("theme", "dark") == "light")}

    topbar = tk.Frame(root, bg=cfg.BG)
    topbar.pack(side="top", fill="x")
    _theme_btn = tk.Button(
        topbar, font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
        padx=12, pady=4, cursor="hand2")
    _theme_btn.pack(side="right", padx=8, pady=4)

    def _refresh_theme_btn():
        if _theme["light"]:
            _theme_btn.configure(text="🌙 Dunkel", bg="#1f4e79", fg="#ffffff",
                                 activebackground="#163a5a", activeforeground="#fff")
        else:
            _theme_btn.configure(text="🌞 Hell", bg="#2a2a3e", fg="#cdd6f4",
                                 activebackground="#3a3a52", activeforeground="#fff")

    def _apply_theme(to_light: bool):
        _theme["light"] = to_light
        try:
            theming.retheme_tree(root, to_light)
        except Exception:
            log.exception("retheme_tree fehlgeschlagen")
        if dna_obj is not None:
            try:
                dna_obj.set_theme(dark=not to_light)
            except Exception:
                log.exception("DNA-Theme setzen fehlgeschlagen")
        _refresh_theme_btn()
        try:
            cfg.DEFAULT_CONFIG["theme"] = "light" if to_light else "dark"
            cfg.save_overrides({"theme": cfg.DEFAULT_CONFIG["theme"]})
        except Exception:
            pass

    def _toggle_theme_global():
        _apply_theme(not _theme["light"])

    _theme_btn.configure(command=_toggle_theme_global)
    _refresh_theme_btn()

    # ── Notebook mit 3 Reitern ─────────────────────────────────────────────────
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    tab_start = ttk.Frame(nb, style="TFrame")
    tab_ged   = ttk.Frame(nb, style="TFrame")
    tab_dna   = ttk.Frame(nb, style="TFrame")

    nb.add(tab_start, text="  🏠 Start  ")
    nb.add(tab_ged,   text="  🌳 Stammbaum-Auswertung  ")
    nb.add(tab_dna,   text="  🧬 DNA-Matches  ")

    # ── Start-Reiter (Zuerst, damit on_gedcom_change-Callback gebaut werden kann)
    ahnen_obj: AhnenApp | None = None       # type: ignore[valid-type]
    dna_obj:   AncestryDnaApp | None = None  # type: ignore[valid-type]

    def _on_gedcom_change(ged_path: str, root_id: str):
        """Propagiert Pfad-Änderungen vom Start-Tab in beide Analyse-Tabs."""
        if ahnen_obj is not None:
            try:
                ahnen_obj._path_var.set(ged_path)
                ahnen_obj._root_id_var.set(root_id)
            except Exception:
                pass
        if dna_obj is not None:
            try:
                dna_obj._set_gedcom(ged_path)
            except Exception:
                pass

    from start_page import StartPage
    try:
        start_obj = StartPage(master=tab_start,
                               on_gedcom_change=_on_gedcom_change)
    except Exception as exc:
        log.exception("StartPage fehlgeschlagen")
        _error_tab(tab_start, "Start-Seite konnte nicht geladen werden", exc)
        start_obj = None

    # ── Stammbaum-Reiter ──────────────────────────────────────────────────────
    if AhnenApp is None:
        _error_tab(tab_ged, "GEDCOM-Analyzer konnte nicht geladen werden", _ahnen_exc)
    else:
        try:
            ahnen_obj = AhnenApp(master=tab_ged)
            # Start-Tab mit aktuellem GEDCOM-Pfad des Analyzers synchronisieren
            if start_obj is not None:
                try:
                    ged_path = cfg.DEFAULT_CONFIG.get("gedfile", "")
                    start_obj._vars["gedfile"].set(ged_path)
                    start_obj._vars["root_id"].set(cfg.DEFAULT_CONFIG.get("root_id", ""))
                    start_obj._vars["exclude_id"].set(
                        cfg.DEFAULT_CONFIG.get("exclude_id", ""))
                except Exception:
                    pass
        except Exception as exc:
            log.exception("AhnenApp-Init fehlgeschlagen")
            _error_tab(tab_ged, "GEDCOM-Analyzer-Fehler beim Start", exc)

    # ── DNA-Reiter ────────────────────────────────────────────────────────────
    if AncestryDnaApp is None:
        _error_tab(tab_dna, "DNA-Tool konnte nicht geladen werden", _dna_exc)
    else:
        try:
            dna_obj = AncestryDnaApp(master=tab_dna)
        except Exception as exc:
            log.exception("AncestryDnaApp-Init fehlgeschlagen")
            _error_tab(tab_dna, "DNA-Tool-Fehler beim Start", exc)
            dna_obj = None

    # ── Ancestry-Login in den Start-Tab einhängen ─────────────────────────────
    # Der Login lebt jetzt auf dem Start-Tab; das Widget kommt aus dem DNA-Tool
    # (teilt dessen AppState/Login-Handler), daher erst nach dna_obj einhängen.
    if start_obj is not None and dna_obj is not None:
        try:
            start_obj.mount_login(dna_obj.make_login_widget)
        except Exception:
            log.exception("Login-Einhängung in den Start-Tab fehlgeschlagen")

    # ── Tab-Wechsel-Event: Status im Start-Tab aktualisieren ──────────────────
    def _on_tab_change(event=None):
        if start_obj is not None:
            try:
                idx = nb.index(nb.select())
                if idx == 0:
                    start_obj._refresh_status()
            except Exception:
                pass
    nb.bind("<<NotebookTabChanged>>", _on_tab_change)

    # ── Fenster schließen ─────────────────────────────────────────────────────
    def _on_close():
        if dna_obj is not None:
            try:
                dna_obj.shutdown()
            except Exception:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)

    # Persistiertes Theme anwenden (Default dunkel). Verzögert, damit alle
    # Reiter fertig aufgebaut sind, bevor der Widgetbaum umgefärbt wird.
    if _theme["light"]:
        root.after(150, lambda: _apply_theme(True))

    root.mainloop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("\nFehler — Eingabetaste zum Beenden ...")
