"""ancestry/gui/widgets/pipeline_view.py — Horizontale Pipeline-Box-Leiste.

Zeigt eine Reihe von farbigen, anklickbaren Quellen-Kacheln.
Live-Status (✓ N Datensätze / ○ nicht geladen) wird per update_status()
von außen gesetzt.  Datenfrische-Ampel (🟢/🟡/🔴) wird per
update_freshness() oder _load_pipeline_runs() befüllt.
"""
from __future__ import annotations

import datetime
import tkinter as tk
from tkinter import ttk

from ancestry.gui.widgets.tooltip import tooltip as _tooltip

# Farben für Status-Zustände in der Zusammenfassungszeile
_OK_FG   = "#217A3C"   # grün
_WARN_FG = "#C85000"   # orange
_EMPTY_FG = "#888888"  # grau


class DataSourcePipeline(tk.Frame):
    """Horizontale Quellen-Pipeline mit Live-Status und aufklappbaren Detail-Panels.

    Parameters
    ----------
    sources:
        list of dicts with keys:
          id      – unique string key
          icon    – emoji / short text
          label   – main caption
          sub     – subtitle (e.g. '.ged / .ftm')
          color   – background hex for the box
          desc    – bilingual description shown in the panel header area
          builder – callable(frame: ttk.Frame) -> None
    colors:
        dict with bg, light, text, text_dim — matches AppState.colors()
    """

    def __init__(
        self,
        parent: tk.Widget,
        sources: list[dict],
        colors: dict | None = None,
        state=None,
    ):
        c = colors or {}
        self._bg  = c.get("bg",       "#F0F4F8")
        self._bg2 = c.get("light",    "#D6E4F0")
        self._fg  = c.get("text",     "#1A1A2E")
        self._dim = c.get("text_dim", "#888888")

        super().__init__(parent, bg=self._bg)
        self._state        = state
        self._sources      = sources
        self._active:       str | None            = None
        self._box_btns:     dict[str, tk.Button]  = {}
        self._orig_colors:  dict[str, str]        = {}
        self._status_cache: dict[str, tuple[str, str]] = {}
        self._freshness_cache: dict[str, str]     = {}   # {source_id: last_run ISO}
        self._tile_tooltips:   dict[str, object]  = {}   # {source_id: Tooltip}

        # ── Zusammenfassungszeile (wird nach update_status gefüllt) ────────
        self._summary_var = tk.StringVar(value="")
        summary_bar = tk.Frame(self, bg=self._bg)
        summary_bar.pack(fill="x", pady=(0, 4))
        self._summary_lbl = tk.Label(
            summary_bar,
            textvariable=self._summary_var,
            bg=self._bg,
            fg=self._dim,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self._summary_lbl.pack(side="left")

        # Platzhalter während des Ladens
        self._summary_var.set("…  Lade Status")

        # ── Kachel-Leiste ──────────────────────────────────────────────────
        self._bar_frame = tk.Frame(self, bg=self._bg)
        self._bar_frame.pack(fill="x", pady=(0, 2))

        self._panel_host = tk.Frame(self, bg=self._bg)
        self._panel_host.pack(fill="x")

        self._build_bar()

    # ── Kacheln bauen ─────────────────────────────────────────────────────────

    def _build_bar(self):
        for i, src in enumerate(self._sources):
            if i > 0:
                tk.Label(
                    self._bar_frame, text="→",
                    bg=self._bg, fg="#aaaaaa",
                    font=("Segoe UI", 10),
                ).pack(side="left", padx=1)

            color = src.get("color", "#4a6fa5")
            self._orig_colors[src["id"]] = color
            fresh = self._freshness_icon(self._freshness_cache.get(src["id"]))

            btn = tk.Button(
                self._bar_frame,
                text=f"{fresh} {src.get('icon', '')}\n{src['label']}\n○",
                bg=color,
                fg="#ffffff",
                activebackground=self._lighten(color),
                activeforeground="#ffffff",
                font=("Segoe UI", 8, "bold"),
                relief="flat",
                bd=0,
                padx=10,
                pady=7,
                cursor="hand2",
                command=lambda s=src: self._toggle(s["id"]),
                justify="center",
                wraplength=82,
            )
            btn.pack(side="left", padx=1)
            self._box_btns[src["id"]] = btn
            self._tile_tooltips[src["id"]] = _tooltip(
                btn, self._freshness_tooltip(self._freshness_cache.get(src["id"]))
            )

    # ── Live-Status ───────────────────────────────────────────────────────────

    def update_status(self, statuses: dict[str, tuple[str, str]]):
        """Aktualisiert Kacheln mit Live-Daten.

        Parameters
        ----------
        statuses:
            {src_id: (text, state)}
            text  – z. B. '3.841 Matches' oder 'nicht geladen'
            state – 'ok' | 'empty' | 'warn'
        """
        self._status_cache = statuses
        ok_count = sum(1 for _, s in statuses.values() if s == "ok")
        total    = len(self._sources)

        for src in self._sources:
            sid = src["id"]
            if sid not in statuses:
                continue
            text, state = statuses[sid]
            btn   = self._box_btns.get(sid)
            if btn is None:
                continue

            icon  = src.get("icon", "")
            label = src["label"]
            orig  = self._orig_colors.get(sid, "#4a6fa5")
            fresh = self._freshness_icon(self._freshness_cache.get(sid))

            if state == "ok":
                badge  = "✓"
                bg     = self._darken(orig, 25)   # eingerichtet → etwas dunkler / ruhiger
                fg_btn = "#ccffcc"                  # leicht grüne Schrift für den Status
            elif state == "warn":
                badge  = "⚠"
                bg     = orig
                fg_btn = "#ffe080"
            else:
                badge  = "○"
                bg     = orig                       # original Farbe = Aufmerksamkeit
                fg_btn = "#ffffff"

            btn.configure(
                text=f"{fresh} {badge}  {icon}\n{label}\n{text}",
                bg=bg,
                activebackground=self._lighten(bg),
            )
            # Status-Zeile bekommt eigene Farbe → nur über font/fg möglich wenn fg global;
            # wir setzen fg global auf weiß, der badge oben signalisiert den Zustand.
            btn.configure(fg="#ffffff")

        # Zusammenfassungszeile
        if ok_count == total:
            self._summary_var.set(f"✓  Alle {total} Quellen eingerichtet")
            self._summary_lbl.configure(fg=_OK_FG)
        elif ok_count == 0:
            nxt = next((s["label"] for s in self._sources
                        if statuses.get(s["id"], ("", "empty"))[1] != "ok"), "")
            self._summary_var.set(
                f"○  Noch keine Daten geladen  ·  Als nächstes: {nxt} einrichten"
            )
            self._summary_lbl.configure(fg=_WARN_FG)
        else:
            missing = [s["label"] for s in self._sources
                       if statuses.get(s["id"], ("", "empty"))[1] != "ok"]
            self._summary_var.set(
                f"{ok_count} von {total} eingerichtet  ·  Fehlt: {', '.join(missing)}"
            )
            self._summary_lbl.configure(fg=_WARN_FG)

    # ── Toggle / Panel ────────────────────────────────────────────────────────

    def _toggle(self, src_id: str):
        if self._active == src_id:
            self._hide_panel()
        else:
            self._show_panel(src_id)

    def _hide_panel(self):
        for w in self._panel_host.winfo_children():
            w.destroy()
        if self._active:
            self._restore_box(self._active)
        self._active = None

    def _show_panel(self, src_id: str):
        for w in self._panel_host.winfo_children():
            w.destroy()
        if self._active:
            self._restore_box(self._active)

        src = next((s for s in self._sources if s["id"] == src_id), None)
        if src is None:
            return
        self._active = src_id
        self._highlight_box(src_id)

        color = src.get("color", "#4a6fa5")

        # Status-Info für den Panel-Header
        cached = self._status_cache.get(src_id, ("", "empty"))
        status_text, status_state = cached
        status_badge = "✓" if status_state == "ok" else ("⚠" if status_state == "warn" else "○")

        # Header
        hdr = tk.Frame(self._panel_host, bg=color)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=f"{src.get('icon', '')}  {src['label']}",
            bg=color, fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=10, pady=6)
        # Status-Badge im Header
        badge_fg = "#ccffcc" if status_state == "ok" else "#ffe080" if status_state == "warn" else "#cccccc"
        tk.Label(
            hdr,
            text=f"{status_badge} {status_text}",
            bg=color, fg=badge_fg,
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 10))
        tk.Button(
            hdr, text="✕",
            bg=color, fg="#ffffff",
            activebackground=self._lighten(color),
            activeforeground="#ffffff",
            relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            command=self._hide_panel,
        ).pack(side="right", padx=8, pady=4)

        # Beschreibung
        desc = src.get("desc", "")
        if desc:
            desc_bg = tk.Frame(self._panel_host, bg=self._bg2)
            desc_bg.pack(fill="x")
            tk.Label(
                desc_bg, text=desc,
                bg=self._bg2, fg=self._fg,
                justify="left", wraplength=700,
                font=("Segoe UI", 9),
                pady=5, padx=10,
            ).pack(anchor="w")

        # Inhalt per Builder-Callback
        content = ttk.Frame(self._panel_host)
        content.pack(fill="x", padx=8, pady=4)
        builder = src.get("builder")
        if callable(builder):
            builder(content)

    # ── Visual state helpers ──────────────────────────────────────────────────

    def _highlight_box(self, src_id: str):
        btn = self._box_btns.get(src_id)
        if btn:
            btn.configure(relief="solid", bd=2,
                          highlightthickness=2,
                          highlightbackground="#ffffff",
                          highlightcolor="#ffffff")

    def _restore_box(self, src_id: str):
        btn = self._box_btns.get(src_id)
        if btn:
            btn.configure(relief="flat", bd=0, highlightthickness=0)

    @staticmethod
    def _lighten(hex_color: str, amount: int = 40) -> str:
        try:
            r = min(255, int(hex_color[1:3], 16) + amount)
            g = min(255, int(hex_color[3:5], 16) + amount)
            b = min(255, int(hex_color[5:7], 16) + amount)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    @staticmethod
    def _darken(hex_color: str, amount: int = 30) -> str:
        try:
            r = max(0, int(hex_color[1:3], 16) - amount)
            g = max(0, int(hex_color[3:5], 16) - amount)
            b = max(0, int(hex_color[5:7], 16) - amount)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color
