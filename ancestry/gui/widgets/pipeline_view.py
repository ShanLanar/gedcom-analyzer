"""ancestry/gui/widgets/pipeline_view.py — Horizontale Pipeline-Box-Leiste.

Zeigt eine Reihe von farbigen, anklickbaren Quellen-Kacheln.
Beim Klick klappt darunter ein Detail-Panel auf; ein zweiter
Klick schließt es wieder. Der Inhalt jeder Kachel wird über
einen Builder-Callback eingefügt – das Widget selbst importiert
keinen tool-spezifischen Code.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class DataSourcePipeline(tk.Frame):
    """Horizontale Quellen-Pipeline mit aufklappbaren Detail-Panels.

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
                    fills the detail panel with controls / buttons
    colors:
        dict with bg, light, text, text_dim for the widget background;
        matches the dict returned by AppState.colors()
    """

    def __init__(
        self,
        parent: tk.Widget,
        sources: list[dict],
        colors: dict | None = None,
    ):
        c = colors or {}
        self._bg  = c.get("bg",       "#F0F4F8")
        self._bg2 = c.get("light",    "#D6E4F0")
        self._fg  = c.get("text",     "#1A1A2E")
        self._dim = c.get("text_dim", "#888888")

        super().__init__(parent, bg=self._bg)
        self._sources = sources
        self._active:  str | None          = None
        self._box_btns: dict[str, tk.Button] = {}

        self._bar_frame   = tk.Frame(self, bg=self._bg)
        self._bar_frame.pack(fill="x", pady=(0, 2))

        self._panel_host = tk.Frame(self, bg=self._bg)
        self._panel_host.pack(fill="x")

        self._build_bar()

    # ── Bar ──────────────────────────────────────────────────────────────────

    def _build_bar(self):
        for i, src in enumerate(self._sources):
            if i > 0:
                tk.Label(
                    self._bar_frame, text="→",
                    bg=self._bg, fg="#999999",
                    font=("Segoe UI", 11),
                ).pack(side="left", padx=1)

            color = src.get("color", "#4a6fa5")
            btn = tk.Button(
                self._bar_frame,
                text=f"{src.get('icon', '')}\n{src['label']}\n{src.get('sub', '')}",
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
            self._reset_box(self._active)
        self._active = None

    def _show_panel(self, src_id: str):
        for w in self._panel_host.winfo_children():
            w.destroy()
        if self._active:
            self._reset_box(self._active)

        src = next((s for s in self._sources if s["id"] == src_id), None)
        if src is None:
            return
        self._active = src_id
        self._highlight_box(src_id, src.get("color", "#4a6fa5"))

        color = src.get("color", "#4a6fa5")

        # Header bar
        hdr = tk.Frame(self._panel_host, bg=color)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text=f"{src.get('icon', '')}  {src['label']}  —  {src.get('sub', '')}",
            bg=color, fg="#ffffff",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=10, pady=6)
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

        # Description
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

        # Content via builder callback
        content = ttk.Frame(self._panel_host)
        content.pack(fill="x", padx=8, pady=4)
        builder = src.get("builder")
        if callable(builder):
            builder(content)

    # ── Visual state helpers ──────────────────────────────────────────────────

    def _highlight_box(self, src_id: str, color: str):
        btn = self._box_btns.get(src_id)
        if btn:
            btn.configure(
                relief="solid", bd=2,
                highlightthickness=2,
                highlightbackground="#ffffff",
                highlightcolor="#ffffff",
            )

    def _reset_box(self, src_id: str):
        btn = self._box_btns.get(src_id)
        if btn:
            btn.configure(relief="flat", bd=0, highlightthickness=0)

    @staticmethod
    def _lighten(hex_color: str) -> str:
        try:
            r = min(255, int(hex_color[1:3], 16) + 40)
            g = min(255, int(hex_color[3:5], 16) + 40)
            b = min(255, int(hex_color[5:7], 16) + 40)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color
