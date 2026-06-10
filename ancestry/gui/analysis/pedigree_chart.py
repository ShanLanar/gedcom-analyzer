"""
pedigree_chart.py — Ahnentafel-Diagramm (Webtrees-Stil).

Zeigt 3–6 Generationen als scrollbares Canvas-Diagramm:
  • Proband links → Vorfahren nach rechts
  • Kästchen: Name, Lebensdaten, Verwandtschaftsgrad, DNA-Match-Hinweis
  • Bei Anverwandte-Treffer: geteiltes Kästchen (beide Datensätze sichtbar)
  • Klick auf Kästchen → Detailpanel rechts (GEDCOM | Anverwandte nebeneinander)
  • L-förmige Verbindungslinien wie Webtrees
"""
from __future__ import annotations

import logging
import math
import tkinter as tk
from tkinter import ttk

log = logging.getLogger(__name__)

# ── Layout ────────────────────────────────────────────────────────────────────

BOX_W   = 200
BOX_H   = 68   # ohne Anverwandte-Zeile
BOX_H2  = 108  # mit Anverwandte-Zeile
GAP_X   = 56
GAP_Y   = 8
MARGIN  = 14

# Farben
C_MALE   = "#bdd7ee"   # hellblau
C_FEMALE = "#f4b8c8"   # hellrosa
C_UNK    = "#dde0e5"   # grau
C_ANVER  = "#c8ebd0"   # hellgrün (Anverwandte-Block)
C_ANVER_BD = "#5caa6f"
C_LINE   = "#8899aa"
C_CONN   = "#aabbcc"
C_DNA    = "#e8a020"    # Gold für DNA-Match-Hinweis
C_BORDER_SEL = "#2244cc"
C_TEXT   = "#1a1a2e"
C_MUTED  = "#666680"


# ── Kinship-Label (Deutsch) ───────────────────────────────────────────────────

def _kinship(sosa: int) -> str:
    if sosa <= 0:
        return ""
    if sosa == 1:
        return "Proband"
    gen = int(math.log2(sosa))
    is_male = (sosa % 2 == 0)
    sx = "vater" if is_male else "mutter"
    if gen == 1:
        return "Vater" if is_male else "Mutter"
    if gen == 2:
        side = "paternal. " if sosa in (4, 5) else "maternal. "
        return f"Groß{sx}"
    if gen == 3:
        return f"Urgroß{sx}"
    pre = "-".join(["Ur"] * (gen - 2))
    return f"{pre}groß{sx}"


def _gen_label(gen: int) -> str:
    labels = {0: "Proband", 1: "Eltern", 2: "Großeltern",
              3: "Urgroßeltern", 4: "Ur-Urgroßeltern", 5: "3×Urgroßeltern",
              6: "4×Urgroßeltern"}
    return labels.get(gen, f"{gen}. Generation")


# ── Datenladen ────────────────────────────────────────────────────────────────

def _load_ancestors(db, test_guid: str | None, max_gen: int = 5) -> dict[int, dict]:
    """Lädt direkte Vorfahren (Sosa 1 … 2^max_gen − 1) aus gedcom_persons."""
    max_sosa = 2**max_gen - 1
    persons: dict[int, dict] = {}
    ged_ids: list[str] = []

    try:
        with db._cursor() as cur:
            rows = cur.execute(
                """SELECT ged_id, given_name, surname, sex,
                          birth_year, birth_place, death_year, death_place, sosa_number
                   FROM gedcom_persons
                   WHERE sosa_number BETWEEN 1 AND ?
                     AND source = 'gedcom'
                   ORDER BY sosa_number""",
                (max_sosa,),
            ).fetchall()
    except Exception as e:
        log.debug("pedigree_chart load: %s", e)
        return {}

    for ged_id, gn, sn, sex, by, bp, dy, dp, sosa in rows:
        persons[sosa] = {
            "ged_id": ged_id, "given_name": gn or "", "surname": sn or "",
            "sex": sex or "", "birth_year": by, "birth_place": bp or "",
            "death_year": dy, "death_place": dp or "",
            "anverwandte": None, "dna_cm": None,
        }
        ged_ids.append(ged_id)

    if not ged_ids:
        return persons

    # Anverwandte-Treffer (bestes Match je GEDCOM-Person)
    try:
        ph = ",".join("?" * len(ged_ids))
        with db._cursor() as cur:
            xrows = cur.execute(
                f"""SELECT x.ged_id_primary,
                           a.given_name, a.surname, a.sex,
                           a.birth_year, a.birth_place, a.death_year, a.death_place,
                           x.score
                    FROM gedcom_person_xref x
                    JOIN gedcom_persons a ON a.ged_id = x.ged_id_other
                    WHERE x.ged_id_primary IN ({ph})
                      AND x.source_other = 'anverwandte'
                      AND x.status != 'rejected'
                    ORDER BY x.score DESC""",
                ged_ids,
            ).fetchall()
        seen: set[str] = set()
        for gid_primary, ag, asn, asex, aby, abp, ady, adp, sc in xrows:
            if gid_primary in seen:
                continue
            seen.add(gid_primary)
            for p in persons.values():
                if p["ged_id"] == gid_primary:
                    p["anverwandte"] = {
                        "given_name": ag or "", "surname": asn or "",
                        "birth_year": aby, "birth_place": abp or "",
                        "death_year": ady, "score": sc,
                    }
                    break
    except Exception as e:
        log.debug("pedigree_chart xref: %s", e)

    # DNA cM via gedcom_links (höchster cM-Wert je Vorfahre)
    if test_guid:
        try:
            with db._cursor() as cur:
                dna_rows = cur.execute(
                    """SELECT gl.ged_id, MAX(m.cm)
                       FROM gedcom_links gl
                       JOIN matches m
                         ON m.match_guid = gl.match_guid
                        AND m.test_guid  = gl.test_guid
                       WHERE gl.test_guid = ?
                       GROUP BY gl.ged_id""",
                    (test_guid,),
                ).fetchall()
            ged_to_cm = {r[0]: float(r[1]) for r in dna_rows if r[1]}
            for p in persons.values():
                cm = ged_to_cm.get(p["ged_id"])
                if cm:
                    p["dna_cm"] = cm
        except Exception as e:
            log.debug("pedigree_chart dna_cm: %s", e)

    return persons


# ── Canvas-Widget ─────────────────────────────────────────────────────────────

class PedigreeCanvas(tk.Canvas):
    """Canvas, das die Ahnentafel zeichnet und Klick-Events weitergibt."""

    def __init__(self, master, on_select=None, **kw):
        super().__init__(master, **kw)
        self._on_select = on_select   # callback(sosa, person_dict)
        self._box_items: dict[int, list[int]] = {}   # sosa → canvas item IDs
        self._sosa_map: dict[int, dict] = {}
        self._selected: int | None = None
        self.bind("<Button-1>", self._on_click)
        self.bind("<MouseWheel>",    self._on_scroll_y)
        self.bind("<Shift-MouseWheel>", self._on_scroll_x)
        self.bind("<Button-4>",  self._on_scroll_y)
        self.bind("<Button-5>",  self._on_scroll_y)

    # ── public ───────────────────────────────────────────────────────────────

    def render(self, persons: dict[int, dict], max_gen: int = 5) -> None:
        self.delete("all")
        self._box_items.clear()
        self._sosa_map = persons
        self._selected = None
        if not persons:
            self.create_text(
                200, 100,
                text="Keine Vorfahren gefunden.\nBitte zuerst GEDCOM laden und\nWurzelperson setzen.",
                font=("Segoe UI", 11), fill=C_MUTED, anchor="nw",
            )
            return

        # Leinwandgröße berechnen
        n_leaf = 2 ** (max_gen - 1)
        bh_max = BOX_H2  # worst-case Höhe (mit Anverwandte)
        row_h  = bh_max + GAP_Y
        total_h = n_leaf * row_h + GAP_Y + MARGIN * 2
        total_w = max_gen * (BOX_W + GAP_X) + MARGIN * 2

        self.configure(scrollregion=(0, 0, total_w, total_h))

        # Generationsbezeichnungen als Spaltenköpfe
        for g in range(max_gen):
            x_col = MARGIN + g * (BOX_W + GAP_X)
            self.create_text(
                x_col + BOX_W // 2, MARGIN - 2,
                text=_gen_label(g),
                font=("Segoe UI", 7, "bold"), fill=C_MUTED, anchor="s",
            )

        # Kästchen + Verbindungen zeichnen
        for sosa, person in sorted(persons.items()):
            gen = int(math.log2(sosa))
            if gen >= max_gen:
                continue
            x, y = self._box_pos(sosa, max_gen, total_h)
            bh = BOX_H2 if person.get("anverwandte") else BOX_H
            self._draw_box(sosa, x, y, BOX_W, bh, person)
            # Verbindung zu Eltern zeichnen
            if gen < max_gen - 1:
                self._draw_connectors(sosa, max_gen, total_h)

        self._apply_selection(self._selected)

    # ── Positionsberechnung ───────────────────────────────────────────────────

    def _box_pos(self, sosa: int, max_gen: int, total_h: int) -> tuple[int, int]:
        gen = int(math.log2(sosa))
        n_in_gen = 2**gen
        idx = sosa - n_in_gen          # 0-basierter Index in dieser Generation
        spacing = total_h / n_in_gen
        y_center = (idx + 0.5) * spacing
        bh = BOX_H2 if self._sosa_map.get(sosa, {}).get("anverwandte") else BOX_H
        y_top = int(y_center - bh / 2)
        x = MARGIN + gen * (BOX_W + GAP_X)
        return x, y_top

    def _box_center_y(self, sosa: int, max_gen: int, total_h: int) -> int:
        gen = int(math.log2(sosa))
        n_in_gen = 2**gen
        idx = sosa - n_in_gen
        spacing = total_h / n_in_gen
        return int((idx + 0.5) * spacing)

    # ── Kästchen zeichnen ─────────────────────────────────────────────────────

    def _draw_box(self, sosa: int, x: int, y: int,
                  w: int, h: int, person: dict) -> None:
        sex = person.get("sex", "")
        bg  = C_MALE if sex == "M" else C_FEMALE if sex == "F" else C_UNK
        bd  = "#7799bb" if sex == "M" else "#bb7799" if sex == "F" else "#999aaa"
        ids = []

        # Rahmen + Hintergrund
        ids.append(self.create_rectangle(
            x, y, x + w, y + h, fill=bg, outline=bd, width=1, tags=f"box_{sosa}"))

        # DNA-Match-Streifen oben
        if person.get("dna_cm"):
            ids.append(self.create_rectangle(
                x, y, x + w, y + 4, fill=C_DNA, outline="", tags=f"box_{sosa}"))

        # Name (fett)
        name = f"{person['given_name']} {person['surname']}".strip() or "?"
        if len(name) > 26:
            name = name[:24] + "…"
        ids.append(self.create_text(
            x + 8, y + 9,
            text=name, anchor="nw",
            font=("Segoe UI", 9, "bold"), fill=C_TEXT, tags=f"box_{sosa}"))

        # Kinship-Label rechts oben
        kin = _kinship(sosa)
        ids.append(self.create_text(
            x + w - 5, y + 4,
            text=kin, anchor="ne",
            font=("Segoe UI", 6), fill=C_MUTED, tags=f"box_{sosa}"))

        # Lebensdaten
        life = _life_line(person)
        ids.append(self.create_text(
            x + 8, y + 24,
            text=life, anchor="nw",
            font=("Segoe UI", 8), fill=C_TEXT, tags=f"box_{sosa}"))

        # Geburtsort (gekürzt)
        if person.get("birth_place"):
            place = person["birth_place"].split(",")[0][:28]
            ids.append(self.create_text(
                x + 8, y + 37,
                text=f"📍 {place}", anchor="nw",
                font=("Segoe UI", 7), fill=C_MUTED, tags=f"box_{sosa}"))

        # DNA-cM-Badge
        if person.get("dna_cm"):
            ids.append(self.create_text(
                x + w - 5, y + h - (42 if person.get("anverwandte") else 6),
                text=f"🧬 {person['dna_cm']:.0f} cM", anchor="se",
                font=("Segoe UI", 7, "bold"), fill=C_DNA, tags=f"box_{sosa}"))

        # Sosa-Nummer klein
        ids.append(self.create_text(
            x + 5, y + h - (42 if person.get("anverwandte") else 6),
            text=f"#{sosa}", anchor="sw",
            font=("Segoe UI", 6), fill=C_MUTED, tags=f"box_{sosa}"))

        # Anverwandte-Block (untere Hälfte)
        if person.get("anverwandte"):
            anv = person["anverwandte"]
            sep_y = y + BOX_H - 2
            ids.append(self.create_rectangle(
                x, sep_y, x + w, y + BOX_H2,
                fill=C_ANVER, outline=C_ANVER_BD, width=1, tags=f"box_{sosa}"))
            anv_name = f"{anv['given_name']} {anv['surname']}".strip()
            if len(anv_name) > 24:
                anv_name = anv_name[:22] + "…"
            ids.append(self.create_text(
                x + 8, sep_y + 4,
                text=f"≈ {anv_name}", anchor="nw",
                font=("Segoe UI", 8, "bold"), fill="#1a5c2a", tags=f"box_{sosa}"))
            anv_life = _life_line(anv)
            ids.append(self.create_text(
                x + 8, sep_y + 18,
                text=anv_life, anchor="nw",
                font=("Segoe UI", 7), fill="#2d6e3a", tags=f"box_{sosa}"))
            sc = anv.get("score", 0)
            ids.append(self.create_text(
                x + w - 5, sep_y + 4,
                text=f"✓ {sc:.0%}", anchor="ne",
                font=("Segoe UI", 6), fill="#2d6e3a", tags=f"box_{sosa}"))

        self._box_items[sosa] = ids

    # ── Verbindungslinien ─────────────────────────────────────────────────────

    def _draw_connectors(self, sosa: int, max_gen: int, total_h: int) -> None:
        sr = self.cget("scrollregion")
        if not sr:
            return
        _, _, _, th = (int(v) for v in str(sr).split())
        total_h = th

        gen  = int(math.log2(sosa))
        x_right = MARGIN + gen * (BOX_W + GAP_X) + BOX_W   # rechte Kante dieses Kästchens
        x_next  = MARGIN + (gen + 1) * (BOX_W + GAP_X)      # linke Kante nächste Spalte
        mid_x   = x_right + (x_next - x_right) // 2

        cy_child = self._box_center_y(sosa, max_gen, total_h)

        for child_sosa_mult, parent_sosa in ((2, sosa * 2), (1, sosa * 2 + 1)):
            cy_parent = self._box_center_y(parent_sosa, max_gen, total_h)
            color = C_CONN if parent_sosa in self._sosa_map else "#cccccc"
            dash  = () if parent_sosa in self._sosa_map else (4, 4)

            # Kind → Mitte horizontal
            self.create_line(x_right, cy_child, mid_x, cy_child,
                             fill=color, width=1, dash=dash)
            # Mitte → Elternteil horizontal
            self.create_line(mid_x, cy_parent, x_next, cy_parent,
                             fill=color, width=1, dash=dash)

        # vertikale Verbindungsstange
        cy_father = self._box_center_y(sosa * 2,     max_gen, total_h)
        cy_mother = self._box_center_y(sosa * 2 + 1, max_gen, total_h)
        self.create_line(mid_x, cy_father, mid_x, cy_mother,
                         fill=C_CONN, width=1)

    # ── Selektion ─────────────────────────────────────────────────────────────

    def _apply_selection(self, sosa: int | None) -> None:
        for s, ids in self._box_items.items():
            if not ids:
                continue
            # Erstes Item ist immer der Rahmen
            outline = C_BORDER_SEL if s == sosa else (
                "#7799bb" if self._sosa_map.get(s, {}).get("sex") == "M"
                else "#bb7799" if self._sosa_map.get(s, {}).get("sex") == "F"
                else "#999aaa"
            )
            width = 2 if s == sosa else 1
            try:
                self.itemconfig(ids[0], outline=outline, width=width)
            except tk.TclError:
                pass

    # ── Events ───────────────────────────────────────────────────────────────

    def _on_click(self, event: tk.Event) -> None:
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        hit = self.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        for item in reversed(hit):
            tags = self.gettags(item)
            for tag in tags:
                if tag.startswith("box_"):
                    sosa = int(tag[4:])
                    self._selected = sosa
                    self._apply_selection(sosa)
                    if self._on_select and sosa in self._sosa_map:
                        self._on_select(sosa, self._sosa_map[sosa])
                    return

    def _on_scroll_y(self, event: tk.Event) -> None:
        if event.num == 4 or event.delta > 0:
            self.yview_scroll(-3, "units")
        else:
            self.yview_scroll(3, "units")

    def _on_scroll_x(self, event: tk.Event) -> None:
        if event.delta > 0:
            self.xview_scroll(-3, "units")
        else:
            self.xview_scroll(3, "units")


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _life_line(p: dict) -> str:
    by = p.get("birth_year")
    dy = p.get("death_year")
    parts = []
    if by:
        parts.append(f"*{by}")
    if dy:
        parts.append(f"†{dy}")
    return "  ".join(parts) if parts else "(Daten fehlen)"


def _fmt_place(place: str | None, maxlen: int = 35) -> str:
    if not place:
        return "–"
    return place if len(place) <= maxlen else place[:maxlen - 1] + "…"


# ── Detailpanel ───────────────────────────────────────────────────────────────

def _build_detail_panel(frame: tk.Frame, sosa: int, person: dict) -> None:
    """Füllt das Detailpanel mit GEDCOM- und Anverwandte-Daten."""
    for w in frame.winfo_children():
        w.destroy()

    title = f"#{sosa}  {person['given_name']} {person['surname']}  —  {_kinship(sosa)}"
    ttk.Label(frame, text=title, font=("Segoe UI", 10, "bold"),
              wraplength=450, justify="left").pack(anchor="w", padx=8, pady=(8, 4))

    ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=8)

    cols = ttk.Frame(frame)
    cols.pack(fill="x", padx=8, pady=6)

    # GEDCOM-Block
    gf = ttk.LabelFrame(cols, text="GEDCOM (eigener Stammbaum)")
    gf.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
    _detail_block(gf, person, "#1a3a6e")

    # Anverwandte-Block
    anv = person.get("anverwandte")
    if anv:
        af = ttk.LabelFrame(cols, text="Anverwandte (externer Treffer)")
        af.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        _detail_block(af, anv, "#1a5c2a")
        sc = anv.get("score", 0)
        ttk.Label(af, text=f"Match-Score: {sc:.1%}",
                  font=("Segoe UI", 8, "bold"), foreground="#2d8a3a").pack(anchor="w", padx=6)
    else:
        af = ttk.LabelFrame(cols, text="Anverwandte", foreground="#999")
        af.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        ttk.Label(af, text="Kein Anverwandte-Treffer\nfür diese Person.",
                  foreground="#999", font=("Segoe UI", 8),
                  justify="center").pack(padx=20, pady=20)

    cols.columnconfigure(0, weight=1)
    cols.columnconfigure(1, weight=1)

    # DNA-Block
    if person.get("dna_cm"):
        ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=8)
        df = ttk.Frame(frame)
        df.pack(fill="x", padx=8, pady=4)
        ttk.Label(df, text=f"🧬 DNA-Treffer: {person['dna_cm']:.0f} cM",
                  font=("Segoe UI", 9, "bold"), foreground="#c07010").pack(anchor="w")
        ttk.Label(df, text="(Maximaler cM-Wert eines Matches, der auf diesen Vorfahren verlinkt)",
                  font=("Segoe UI", 7), foreground="#888").pack(anchor="w")

    # Verwandtschaftsgrad
    ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=8)
    rf = ttk.Frame(frame)
    rf.pack(fill="x", padx=8, pady=4)
    gen = int(math.log2(sosa)) if sosa >= 1 else 0
    exp_cm = _expected_cm(sosa)
    lines = [
        f"Sosa-Nr.:           {sosa}",
        f"Generation:        {gen}  ({_gen_label(gen)})",
        f"Verwandtschaftsgrad: {_kinship(sosa)}",
        f"Erwartete cM:       {exp_cm:.0f} cM  (autosomale Schätzung)",
    ]
    for ln in lines:
        ttk.Label(rf, text=ln, font=("Segoe UI", 8)).pack(anchor="w")


def _detail_block(parent: tk.Widget, p: dict, accent: str) -> None:
    rows = [
        ("Vorname",       p.get("given_name") or "–"),
        ("Nachname",      p.get("surname") or "–"),
        ("Geschlecht",    {"M": "männlich", "F": "weiblich"}.get(p.get("sex", ""), "unbekannt")),
        ("Geburtsjahr",   str(p["birth_year"]) if p.get("birth_year") else "–"),
        ("Geburtsort",    _fmt_place(p.get("birth_place"))),
        ("Sterbejahr",    str(p["death_year"]) if p.get("death_year") else "–"),
        ("Sterbeort",     _fmt_place(p.get("death_place"))),
    ]
    for label, val in rows:
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=6, pady=1)
        ttk.Label(row, text=f"{label}:", width=13, anchor="e",
                  font=("Segoe UI", 8), foreground="#555").pack(side="left")
        ttk.Label(row, text=val, font=("Segoe UI", 8, "bold"),
                  foreground=accent, wraplength=150, anchor="w").pack(side="left", padx=4)


def _expected_cm(sosa: int) -> float:
    """Grobe autosomale cM-Schätzung anhand des Verwandtschaftsgrades (Sosa-Nr.)."""
    if sosa <= 0:
        return 0.0
    gen = int(math.log2(sosa))
    # Erwartungswert: 3400 cM / 2^gen (vereinfachte Formel)
    return 3400.0 / (2**gen) if gen > 0 else 0.0


# ── Hauptfenster ──────────────────────────────────────────────────────────────

def show_pedigree_chart(app) -> None:
    """Öffnet das Ahnentafel-Diagramm-Fenster."""
    import threading
    from tkinter import messagebox

    db = getattr(app, "_db", None)
    if db is None:
        messagebox.showwarning("Kein Datenbankzugang", "Bitte zuerst einloggen.")
        return

    test_guid = None
    try:
        test_guid = app._current_guid()
    except Exception:
        pass

    win = tk.Toplevel(app)
    win.title("🌳 Ahnentafel")
    win.geometry("1200x720")
    win.resizable(True, True)

    # ── Toolbar ───────────────────────────────────────────────────────────────
    tb = ttk.Frame(win, relief="flat")
    tb.pack(fill="x", padx=8, pady=(6, 0))

    ttk.Label(tb, text="Generationen:").pack(side="left")
    gen_var = tk.IntVar(value=5)
    gen_spin = ttk.Spinbox(tb, from_=3, to=7, textvariable=gen_var, width=4)
    gen_spin.pack(side="left", padx=(2, 10))

    reload_btn = ttk.Button(tb, text="↻ Neu laden")
    reload_btn.pack(side="left", padx=4)

    ttk.Label(tb, text="  |  Klick auf Kästchen → Details rechts",
              foreground="#666", font=("Segoe UI", 8)).pack(side="left")

    # Legende
    leg = ttk.Frame(tb)
    leg.pack(side="right")
    for col, txt in ((C_MALE, "Mann"), (C_FEMALE, "Frau"),
                     (C_ANVER, "Anverwandte-Match"), (C_DNA, "DNA-Treffer")):
        tk.Label(leg, text="  ■", foreground=col,
                 font=("Segoe UI", 9, "bold"), bg=win.cget("bg")).pack(side="left")
        ttk.Label(leg, text=txt, font=("Segoe UI", 7)).pack(side="left")

    ttk.Separator(win, orient="horizontal").pack(fill="x", padx=8, pady=(4, 0))

    # ── Haupt-Bereich (Canvas links / Detail rechts) ──────────────────────────
    paned = ttk.PanedWindow(win, orient="horizontal")
    paned.pack(fill="both", expand=True, padx=4, pady=4)

    # Canvas + Scrollbars
    canvas_frame = ttk.Frame(paned)
    paned.add(canvas_frame, weight=3)

    vc = ttk.Scrollbar(canvas_frame, orient="vertical")
    hc = ttk.Scrollbar(canvas_frame, orient="horizontal")
    vc.pack(side="right",  fill="y")
    hc.pack(side="bottom", fill="x")

    chart = PedigreeCanvas(
        canvas_frame, bg="#f2f4f8",
        highlightthickness=0,
        yscrollcommand=vc.set,
        xscrollcommand=hc.set,
    )
    chart.pack(fill="both", expand=True)
    vc.configure(command=chart.yview)
    hc.configure(command=chart.xview)

    # Detailpanel
    detail_outer = ttk.Frame(paned, relief="flat")
    paned.add(detail_outer, weight=1)

    detail_scroll = ttk.Scrollbar(detail_outer, orient="vertical")
    detail_scroll.pack(side="right", fill="y")

    detail_canvas = tk.Canvas(detail_outer, yscrollcommand=detail_scroll.set,
                              bg=win.cget("bg"), highlightthickness=0)
    detail_canvas.pack(fill="both", expand=True)
    detail_scroll.configure(command=detail_canvas.yview)

    detail_inner = ttk.Frame(detail_canvas)
    dwin = detail_canvas.create_window(0, 0, anchor="nw", window=detail_inner)

    def _on_detail_resize(evt):
        detail_canvas.itemconfig(dwin, width=evt.width)
    detail_canvas.bind("<Configure>", _on_detail_resize)

    def _on_detail_inner_resize(evt):
        detail_canvas.configure(scrollregion=detail_canvas.bbox("all"))
    detail_inner.bind("<Configure>", _on_detail_inner_resize)

    ttk.Label(detail_inner, text="← Person anklicken",
              foreground="#aaa", font=("Segoe UI", 9),
              justify="center").pack(expand=True, pady=40)

    # ── Zeichnen ──────────────────────────────────────────────────────────────
    _persons: list[dict] = [{}]

    def _render() -> None:
        max_g = gen_var.get()
        persons = _load_ancestors(db, test_guid, max_gen=max_g)
        _persons[0] = persons
        win.after(0, lambda: chart.render(persons, max_gen=max_g))

    def _on_person_select(sosa: int, person: dict) -> None:
        _build_detail_panel(detail_inner, sosa, person)
        detail_canvas.yview_moveto(0)

    chart.configure(on_select=_on_person_select)
    reload_btn.configure(command=lambda: threading.Thread(target=_render, daemon=True).start())

    # Initialer Ladevorgang
    threading.Thread(target=_render, daemon=True).start()
