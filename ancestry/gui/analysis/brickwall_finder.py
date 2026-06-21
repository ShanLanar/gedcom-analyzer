"""
ancestry/gui/analysis/brickwall_finder.py — Interaktiver Brick-Wall-Finder.

Bringt die bestehende Offline-Analyse aus ``tasks/brickwalls.py`` in die GUI:
gut dokumentierte Personen ohne bekannte Eltern werden als hochpriore
Forschungsziele ("Brick Walls") in einer Treeview aufgelistet, sortiert nach
Recherche-Wert. Die Erkennung läuft im Hintergrund-Thread, damit der Dialog
bei großen Bäumen nicht einfriert.

Verwendung (aus dem Werkzeuge-Tab):
    show_brickwall_finder(self, self._state, set_status=...)
"""
from __future__ import annotations

import logging
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

log = logging.getLogger(__name__)

# Spalten: (interner Schlüssel, Überschrift, Breite, Ausrichtung)
_COLUMNS = [
    ("score", "Recherche-Wert", 110, "center"),
    ("name", "Name", 230, "w"),
    ("byear", "Geb.-Jahr", 80, "center"),
    ("bplace", "Geb.-Ort", 210, "w"),
    ("children", "#Nachkommen", 95, "center"),
    ("missing", "fehlend (Vater/Mutter)", 150, "w"),
]


def _resolve_gedcom_path(state) -> str:
    """Ermittelt den Pfad zur geladenen GEDCOM-Datei.

    Reihenfolge: ausdrücklich vorbelegter Startpfad → gemerkte UI-Einstellung
    (ancestry/data/ui_settings.json). Gibt "" zurück, wenn nichts gefunden."""
    # 1) Vom Start-Tab vorbelegter Pfad
    path = (getattr(state, "startup_gedcom_path", "") or "").strip()
    if path and os.path.exists(path):
        return path

    # 2) Gemerkte UI-Einstellungen (gleiche Logik wie GedcomApp._settings_path)
    try:
        import json

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # → ancestry/
        settings = os.path.join(base, "data", "ui_settings.json")
        with open(settings, encoding="utf-8") as fh:
            data = json.load(fh)
        cand = (data.get("gedcom_path") or "").strip() if isinstance(data, dict) else ""
        if cand and os.path.exists(cand):
            return cand
    except (OSError, ValueError):
        pass
    return ""


def show_brickwall_finder(parent, state, set_status=None) -> None:
    """Öffnet den Brick-Wall-Finder-Dialog.

    parent     – aufrufendes Widget (für Toplevel + ``after``); i. d. R. der Tab.
    state      – AppState (für Sprache/Farben/Pfad-Auflösung).
    set_status – optionaler Callback ``set_status(msg)`` für die Statuszeile.
    """
    def _status(msg: str) -> None:
        if callable(set_status):
            try:
                set_status(msg)
            except Exception:
                pass

    gedcom_path = _resolve_gedcom_path(state)
    if not gedcom_path:
        messagebox.showinfo(
            "Brick-Wall-Finder",
            "Es ist kein GEDCOM geladen.\n\n"
            "Bitte zuerst im Start-Tab eine GEDCOM-/FTM-Datei wählen "
            "(bzw. „🌳 GEDCOM abgleichen“ im Matches-Tab ausführen) und "
            "dann den Brick-Wall-Finder erneut öffnen.",
            parent=parent)
        return

    win = tk.Toplevel(parent)
    win.title("🧱 Brick-Wall-Finder – gut dokumentierte Ahnen ohne bekannte Eltern")
    win.geometry("980x600")

    # ── Kopfzeile / Erklärung ────────────────────────────────────────────────
    head = ttk.Frame(win)
    head.pack(fill="x", padx=12, pady=(10, 2))
    ttk.Label(
        head,
        text="Personen ohne verknüpfte Eltern, sortiert nach Recherche-Wert "
             "(je höher, desto lohnender). Doppelklick kopiert die Person-ID.",
        wraplength=900, justify="left",
    ).pack(anchor="w")

    count_lbl = ttk.Label(win, text="lädt …", font=("Segoe UI", 10, "bold"))
    count_lbl.pack(anchor="w", padx=12, pady=(2, 4))

    # ── Treeview ─────────────────────────────────────────────────────────────
    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True, padx=(12, 0), pady=(0, 4))
    cols = tuple(c[0] for c in _COLUMNS)
    tv = ttk.Treeview(frame, columns=cols, show="headings")
    for key, heading, width, anchor in _COLUMNS:
        tv.heading(key, text=heading)
        tv.column(key, width=width, anchor=anchor)
    tv.pack(side="left", fill="both", expand=True)
    sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
    sb.pack(side="right", fill="y")
    tv.configure(yscrollcommand=sb.set)

    # Mapping Treeview-Item → Person-ID (für Doppelklick/Clipboard)
    id_by_item: dict[str, str] = {}

    def _on_double(_event=None):
        sel = tv.selection()
        if not sel:
            return
        pid = id_by_item.get(sel[0], "")
        if not pid:
            return
        try:
            win.clipboard_clear()
            win.clipboard_append(pid)
        except tk.TclError:
            pass
        _status(f"Person-ID {pid} in die Zwischenablage kopiert.")

    tv.bind("<Double-1>", _on_double)

    # ── Hintergrund-Erkennung ────────────────────────────────────────────────
    def _fill(rows: list) -> None:
        if not win.winfo_exists():
            return
        tv.delete(*tv.get_children())
        id_by_item.clear()
        for r in rows:
            # rows aus detect_brickwalls():
            # [pid, name, byear, bplace, dyear, score, children, parent_span, bemerkung]
            pid, name, byear, bplace, _dyear, score, children = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
            display_name = (name or "").replace("/", "").strip() or "(ohne Namen)"
            item = tv.insert("", "end", values=(
                score,
                display_name,
                byear or "",
                bplace or "",
                children,
                "Vater + Mutter",
            ))
            id_by_item[item] = str(pid)
        count_lbl.configure(
            text=f"{len(rows)} Brick Walls (Recherche-Wert ≥ 50) – "
                 f"sortiert absteigend.")
        _status(f"Brick-Wall-Finder: {len(rows)} Personen gefunden.")

    def _fail(msg: str) -> None:
        if not win.winfo_exists():
            return
        count_lbl.configure(text="Fehler beim Laden.")
        messagebox.showerror("Brick-Wall-Finder",
                             f"GEDCOM konnte nicht analysiert werden:\n{msg}",
                             parent=win)

    def _worker() -> None:
        try:
            from lib.gedcom import robust_load_gedcom
            from tasks.brickwalls import detect_brickwalls
            individuals, families = robust_load_gedcom(gedcom_path)
            rows = detect_brickwalls(individuals, families)
        except Exception as exc:  # noqa: BLE001 – an die GUI weiterreichen
            log.exception("Brick-Wall-Erkennung fehlgeschlagen")
            msg = str(exc)
            parent.after(0, lambda m=msg: _fail(m))
            return
        # detect_brickwalls sortiert bereits nach Recherche-Wert absteigend.
        parent.after(0, lambda r=rows: _fill(r))

    _status("Brick-Wall-Finder: analysiere GEDCOM …")
    threading.Thread(target=_worker, daemon=True, name="brickwall_finder").start()
