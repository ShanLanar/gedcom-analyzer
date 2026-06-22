"""Phasing-Dashboard (4-Quadrant Eltern-Zuordnung) für DNA-Matches.

Zeigt Matches in 4 Quadranten:
  Q1: Maternal, Known (paternal_maternal == "maternal")
  Q2: Paternal, Known (paternal_maternal == "paternal")
  Q3: Maternal, Inferred (cluster inference, paternal_maternal leer)
  Q4: Paternal, Inferred

Drag-Drop zur Umlagerung zwischen Quadranten mit DB-Update.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Optional

from ancestry.gui.widgets.theme import COLORS

if TYPE_CHECKING:
    from ancestry.core.database import Database


class PhasingDashboard(tk.Toplevel):
    """4-Quadrant Canvas-Dialog für Phasing/Eltern-Zuordnung."""

    def __init__(
        self,
        parent: tk.Widget,
        kit_guid: str,
        db: Database,
        inferred_side_map: Optional[dict] = None,
    ):
        super().__init__(parent)
        self.title("Phasing-Dashboard – Eltern-Zuordnung")
        self.geometry("1000x700")
        self.kit_guid = kit_guid
        self.db = db
        self.inferred_side_map = inferred_side_map or {}

        self._build()
        self._load_matches()

    def _build(self):
        """Baut UI mit Titelbar und Canvas-Quadranten."""
        # Titelbar
        title_frame = ttk.Frame(self)
        title_frame.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(
            title_frame,
            text="Quadrant-Ansicht: Drag-Drop zum Verschieben, speichert zu DB",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            title_frame,
            text=(
                "🔵 Blau = Paternal | 🔴 Rosa = Maternal | "
                "Oben = Bekannt | Unten = Inferiert"
            ),
            foreground="#666",
        ).pack(anchor="w")

        # Canvas mit 4 Quadranten
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(
            canvas_frame, bg="white", relief="solid", bd=1, highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        self._drag_data = {"item": None, "x0": 0, "y0": 0}
        self._matches_by_quad = {
            "Q1": [],  # Maternal, Known
            "Q2": [],  # Paternal, Known
            "Q3": [],  # Maternal, Inferred
            "Q4": [],  # Paternal, Inferred
        }
        self._item_to_match = {}

    def _on_canvas_resize(self, event):
        """Neuzeichnen bei Größenänderung."""
        self.after(100, self._redraw_canvas)

    def _redraw_canvas(self):
        """Zeichnet Quadranten-Layout."""
        self.canvas.delete("all")
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 100 or h < 100:
            return

        mx, my = w // 2, h // 2

        # Quadranten: Q1 (oben-links), Q2 (oben-rechts), Q3 (unten-links), Q4 (unten-rechts)
        quads = {
            "Q1": (0, 0, mx, my, "#f5d6d6", "Maternal\nKnown"),
            "Q2": (mx, 0, w, my, "#cfe0f5", "Paternal\nKnown"),
            "Q3": (0, my, mx, h, "#fae5d6", "Maternal\nInferred"),
            "Q4": (mx, my, w, h, "#d6e8f5", "Paternal\nInferred"),
        }

        # Hintergrund + Labels
        for qid, (x0, y0, x1, y1, bg, label) in quads.items():
            self.canvas.create_rectangle(
                x0, y0, x1, y1, fill=bg, outline="#999", width=2, tags=f"quad_{qid}"
            )
            self.canvas.create_text(
                (x0 + x1) // 2,
                (y0 + y1) // 2 - 40,
                text=label,
                font=("TkDefaultFont", 12, "bold"),
                foreground="#333",
            )

        # Matches zeichnen
        for qid in ["Q1", "Q2", "Q3", "Q4"]:
            self._draw_quad_matches(qid, quads[qid])

    def _draw_quad_matches(self, qid: str, quad_bbox: tuple):
        """Zeichnet Matches für einen Quadranten."""
        x0, y0, x1, y1, _, _ = quad_bbox
        matches = self._matches_by_quad[qid]

        pad = 10
        max_w = (x1 - x0 - 2 * pad) // 2 if (x1 - x0) > 200 else (x1 - x0 - 2 * pad)
        card_h = 60
        col_w = max_w + 20
        cols = max(1, (x1 - x0 - 2 * pad) // col_w) if col_w > 0 else 1

        for i, match in enumerate(matches):
            row, col = divmod(i, cols) if cols > 0 else (0, 0)
            cx = x0 + pad + col * col_w + (max_w // 2)
            cy = y0 + 80 + row * (card_h + 10)

            if cy + card_h > y1 - 10:
                continue  # Aus Bereich

            # Karte zeichnen
            color = "#1565c0" if qid.endswith("2") or qid.endswith("4") else "#d32f2f"
            card_id = self.canvas.create_rectangle(
                cx - max_w // 2,
                cy - card_h // 2,
                cx + max_w // 2,
                cy + card_h // 2,
                fill=color,
                outline="#333",
                width=1,
                tags=f"match_{match['match_guid']}",
            )

            # Text: display_name, shared_cm, cluster_id
            name = match.get("display_name", "?")[:20]
            shared_cm = match.get("shared_cm", 0)
            cluster = match.get("cluster_id", "—")
            text = f"{name}\n{shared_cm:.0f} cM | {cluster}"

            text_id = self.canvas.create_text(
                cx,
                cy,
                text=text,
                font=("TkDefaultFont", 8),
                fill="white",
                justify="center",
                tags=f"match_text_{match['match_guid']}",
            )

            self._item_to_match[card_id] = (match, qid)
            self._item_to_match[text_id] = (match, qid)

    def _on_canvas_click(self, event):
        """Start Drag."""
        item = self.canvas.find_closest(event.x, event.y)[0]
        if item in self._item_to_match:
            self._drag_data["item"] = item
            self._drag_data["x0"] = event.x
            self._drag_data["y0"] = event.y

    def _on_canvas_drag(self, event):
        """Während Drag: visuell verschieben."""
        item = self._drag_data["item"]
        if item is None:
            return
        dx = event.x - self._drag_data["x0"]
        dy = event.y - self._drag_data["y0"]
        self.canvas.move(item, dx, dy)
        self._drag_data["x0"] = event.x
        self._drag_data["y0"] = event.y

    def _on_canvas_release(self, event):
        """Nach Drag-Ende: neuen Quadranten bestimmen, DB updaten."""
        item = self._drag_data["item"]
        if item is None:
            return

        if item not in self._item_to_match:
            self._drag_data["item"] = None
            self.canvas.delete("all")
            self._redraw_canvas()
            return

        match, old_qid = self._item_to_match[item]
        new_qid = self._get_quad_from_coords(event.x, event.y)

        # Neue Seite bestimmen
        new_side = None
        if new_qid == "Q1" or new_qid == "Q3":
            new_side = "maternal"
        elif new_qid == "Q2" or new_qid == "Q4":
            new_side = "paternal"

        if new_qid != old_qid and new_side:
            # DB updaten
            try:
                with self.db._cursor() as cur:
                    cur.execute(
                        "UPDATE matches SET paternal_maternal = ? WHERE match_guid = ?",
                        (new_side, match["match_guid"]),
                    )
                # Lokal updaten
                self._matches_by_quad[old_qid].remove(match)
                match["paternal_maternal"] = new_side
                self._matches_by_quad[new_qid].append(match)

                self.canvas.delete("all")
                self._redraw_canvas()
            except Exception as e:
                messagebox.showerror("DB-Fehler", f"Konnte Match nicht updaten: {e}")

        self._drag_data["item"] = None

    def _get_quad_from_coords(self, x: int, y: int) -> str:
        """Bestimmt Quadranten aus Canvas-Koordinaten."""
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        mx, my = w // 2, h // 2

        if x < mx and y < my:
            return "Q1"
        elif x >= mx and y < my:
            return "Q2"
        elif x < mx and y >= my:
            return "Q3"
        else:
            return "Q4"

    def _load_matches(self):
        """Lädt Matches aus DB in Quadranten."""
        try:
            with self.db._cursor() as cur:
                cur.execute(
                    """SELECT match_guid, display_name, shared_cm, paternal_maternal
                       FROM matches WHERE test_guid = ?
                       ORDER BY shared_cm DESC""",
                    (self.kit_guid,),
                )
                rows = cur.fetchall()

            for row in rows:
                match = {
                    "match_guid": row["match_guid"],
                    "display_name": row["display_name"],
                    "shared_cm": row["shared_cm"],
                    "paternal_maternal": row["paternal_maternal"] or "",
                    "cluster_id": self.inferred_side_map.get(
                        row["match_guid"], "—"
                    ),
                }

                pm = match.get("paternal_maternal", "")
                # Q1: maternal + known, Q2: paternal + known, Q3/Q4: inferred
                if pm == "maternal":
                    qid = "Q1"
                elif pm == "paternal":
                    qid = "Q2"
                elif self.inferred_side_map.get(row["match_guid"]) == "maternal":
                    qid = "Q3"
                else:
                    qid = "Q4"

                self._matches_by_quad[qid].append(match)

            self._redraw_canvas()
        except Exception as e:
            messagebox.showerror(
                "Fehler beim Laden", f"Konnte Matches nicht laden: {e}"
            )
