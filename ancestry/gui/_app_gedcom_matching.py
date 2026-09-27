"""GEDCOM-Abgleich-Mixin für AncestryDnaApp: Laden/Cachen des eigenen
GEDCOM-Baums, Bulk-/Einzel-Abgleich der Matches dagegen, Setup-Checkliste,
Duplikat-Querbezüge und Seiten-Zuweisung (väterlich/mütterlich).

Fünfzehnter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für
die Begründung) und der letzte thematisch klar abgrenzbare: der
verbleibende Rest von AncestryDnaApp (__init__, Menü-/Fensteraufbau,
Login-Callback) ist untrennbar mit dem Konstruktor verwoben.

`self._gedcom` (Cache-Dict: path/people/index/individuals/families/amap)
wird ausschließlich hier definiert (in `_ensure_gedcom_loaded`) — alle
anderen Stellen im Code lesen ihn nur über `getattr(self, "_gedcom", None)`
und bleiben unverändert, unabhängig davon, welche Basisklasse ihn setzt.

Erwartet von der Host-Klasse (AncestryDnaApp): self._db, self._state,
self._t(), self._set_status(), self._get_kit_guid(), self._current_guid(),
self._refresh_match_table(), self._load_gedcom_link_panel(),
self._selected_match, self._cluster_tab, self._persons_tab,
self._load_ui_settings()/self._save_ui_settings(), self._recent_files_save(),
self._invalidate_stats(), self._startup_gedcom_path, self._ged_link_status.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

log = logging.getLogger(__name__)


class GedcomMatchingMixin:
    """Eigener GEDCOM-Baum: Laden/Cachen, Bulk-Abgleich, Duplikate, Seiten."""

    def _match_own_tree(self):
        """Gleicht alle geladenen Match-Ahnentafeln gegen den eigenen GEDCOM ab
        und zeigt, wo jeder Match in DEINEM Baum hängt."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        peds = self._db.get_all_pedigrees(test_guid)
        if not peds:
            messagebox.showinfo(self._t("dlg.no_pedigrees"),
                self._t("dlg.m_no_pedigrees"))
            return
        def _after_load(ged):
            import threading

            from ancestry.core.treematch import Person, mrca_on_direct_line, render_kinship
            index, amap = ged["index"], ged["amap"]
            indi, fams = ged.get("individuals", {}), ged.get("families", {})

            # Cluster-Lookup einmalig vor dem Thread aufbauen (kein Threading-Problem)
            cluster_lookup: dict[str, int] = {}
            for cid, members in getattr(self, "_clusters", {}).items():
                for m in members:
                    cluster_lookup[m["guid"]] = cid

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
                        if best[3] is not None:
                            kin = render_kinship(best[3])
                        else:
                            # Seitenverwandter → im Baum hochklettern zur direkten Linie
                            _mid, mpath = mrca_on_direct_line(
                                best[2].ref, indi, fams, amap)
                            kin = (render_kinship(mpath) + " (über Seitenlinie)"
                                   if mpath is not None else "")
                        results.append((info["name"], info["cm"], best, kin,
                                        info.get("linked", False), guid))
                    if i % 20 == 0 or i == len(items):
                        self.after(0, lambda i=i: self._set_status(
                            f"GEDCOM-Abgleich: {i}/{len(items)} Matches geprüft …"))
                results.sort(key=lambda x: (-(x[2][0]), -(x[1] or 0)))
                self.after(0, lambda: self._show_gedcom_results(
                    results, len(ged["people"]), len(peds), cluster_lookup))

            threading.Thread(target=_worker, daemon=True, name="gedcom-match").start()

        self._ensure_gedcom_loaded(_after_load)

    def _maybe_show_checklist(self):
        """Zeigt beim ersten Start eine Setup-Checkliste, wenn noch keine Daten vorhanden sind."""
        import os

        # Nicht anzeigen, wenn der Nutzer die Anzeige unterdrückt hat
        if self._load_ui_settings().get("hide_checklist"):
            return

        # Match-Anzahl prüfen
        try:
            n_matches = len(self._db.get_matches())
        except Exception:
            n_matches = 0

        # Wenn bereits Matches vorhanden → kein Onboarding nötig
        if n_matches > 0:
            return

        # GEDCOM geladen?
        st = self._load_ui_settings()
        gedcom_path = st.get("gedcom_path", "") or ""
        gedcom_ok = bool(
            self._state.startup_gedcom_path
            or self._startup_gedcom_path
            or (gedcom_path and os.path.exists(gedcom_path))
        )

        # Dialog aufbauen
        dlg = tk.Toplevel(self)
        dlg.title("Erste Schritte – Ancestry DNA Analyzer")
        dlg.resizable(False, False)
        dlg.grab_set()

        # Intro-Text
        tk.Label(
            dlg,
            text="Willkommen! Hier sind die nächsten Schritte, um die App einzurichten:",
            font=("TkDefaultFont", 10, "bold"),
            wraplength=420,
            justify="left",
            padx=18,
            pady=12,
        ).pack(anchor="w")

        # Checkliste
        checklist_frame = tk.Frame(dlg, padx=18, pady=4)
        checklist_frame.pack(fill="x")

        steps = [
            (gedcom_ok,  "1. GEDCOM-Datei laden  (Menü: Datei → GEDCOM öffnen)"),
            (False,      "2. Ancestry-Login  (Tab: Herunterladen → Einloggen)"),
            (False,      "3. DNA-Matches herunterladen  (Tab: Herunterladen)"),
            (False,      "4. Matches analysieren  (Tab: Matches)"),
        ]
        for done, text in steps:
            icon = "✓" if done else "○"
            color = "#217A3C" if done else "#C85000"
            tk.Label(
                checklist_frame,
                text=f"  {icon}  {text}",
                fg=color,
                font=("TkDefaultFont", 10),
                justify="left",
                anchor="w",
            ).pack(anchor="w", pady=2)

        # Separator
        ttk.Separator(dlg, orient="horizontal").pack(fill="x", padx=12, pady=8)

        # "Nicht mehr anzeigen"-Checkbutton
        hide_var = tk.BooleanVar(value=False)
        bottom_frame = tk.Frame(dlg, padx=12, pady=4)
        bottom_frame.pack(fill="x")
        tk.Checkbutton(
            bottom_frame,
            text="Nicht mehr anzeigen",
            variable=hide_var,
        ).pack(side="left")

        def _close():
            if hide_var.get():
                self._save_ui_settings(hide_checklist=True)
            dlg.destroy()

        tk.Button(
            bottom_frame,
            text="OK – Los geht's",
            command=_close,
            font=("TkDefaultFont", 10, "bold"),
            bg="#217A3C",
            fg="white",
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="right")

        # Dialog zentrieren relativ zum Hauptfenster
        self.update_idletasks()
        dlg.update_idletasks()
        px = self.winfo_toplevel().winfo_x()
        py = self.winfo_toplevel().winfo_y()
        pw = self.winfo_toplevel().winfo_width()
        ph = self.winfo_toplevel().winfo_height()
        dw = dlg.winfo_width()
        dh = dlg.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        dlg.geometry(f"+{x}+{y}")

    def _ensure_gedcom_loaded(self, on_ready, force_ask=False):
        """Lädt den eigenen GEDCOM (mit Cache) + baut Index/Ahnen-Map, dann
        ruft on_ready(ged_dict) auf dem Main-Thread. GEDCOM-Pfad und Wurzelperson
        werden persistent gemerkt (data/ui_settings.json) – kein erneutes Fragen."""
        import os
        cached = getattr(self, "_gedcom", None)
        if cached and not force_ask:
            on_ready(cached)
            return

        st = self._load_ui_settings()
        path = st.get("gedcom_path") if not force_ask else None
        root_name = st.get("gedcom_root", "") or ""

        # GEDCOM-Pfad: gemerkten nutzen, wenn er noch existiert – sonst fragen.
        if not path or not os.path.exists(path):
            path = filedialog.askopenfilename(
                title=self._t("dlg.t_choose_own_tree"),
                filetypes=[("GEDCOM", "*.ged *.gedcom"), ("Alle", "*.*")])
            if not path:
                return

        # Wurzelperson: gemerkte nutzen; nur fragen, wenn keine bekannt (oder force).
        if force_ask or not root_name:
            import tkinter.simpledialog as sd
            root_name = (sd.askstring(
                "Deine Wurzelperson",
                "Wie heißt DU (bzw. die Wurzelperson) im Baum?\n"
                "Vorname Nachname – wird dauerhaft gemerkt (leer = ohne).",
                initialvalue=root_name) or "").strip()

        self._gedcom_root_name = root_name
        self._save_ui_settings(gedcom_path=path, gedcom_root=root_name)
        # D1: Pfad in "Zuletzt geöffnet" aufnehmen
        self._recent_files_save(path)

        import threading
        self._set_status("GEDCOM wird geladen … (läuft im Hintergrund)")

        def _worker():
            try:
                from ancestry.core.treematch import (
                    TreeIndex,
                    build_ancestor_map,
                    find_root_candidate,
                    load_gedcom_full,
                )
                people, individuals, families = load_gedcom_full(path)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror(
                    self._t("dlg.ged_error"), f"Konnte GEDCOM nicht laden:\n{e}"))
                return
            if not people:
                self.after(0, lambda: messagebox.showwarning(
                    self._t("dlg.empty"), self._t("dlg.m_ged_empty")))
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

    def _show_gedcom_results(self, results, n_people, n_peds, cluster_lookup=None):
        from ancestry.gui.analysis.gedcom_results import show_gedcom_results
        show_gedcom_results(self, results, n_people, n_peds, cluster_lookup)

    def _run_gedcom_match_all(self):
        """Bulk-Abgleich aller Matches gegen den GEDCOM-Baum."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo(self._t("dlg.gedcom"), self._t("md.ged_none"))
            return
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Bulk-Abgleich läuft …")
        self._set_status("GEDCOM-Abgleich läuft…")

        def _worker():
            try:
                from ancestry.core import bridge
                bridge.ensure_tables(self._db)
                if bridge.get_gedcom_person_count(self._db) == 0:
                    bridge.import_gedcom_persons(
                        self._db, ged["individuals"], ged.get("path", ""),
                        families=ged.get("families") or {})
                total = bridge.run_match_all(self._db, test_guid)
                self.after(0, lambda: self._ged_link_status.set(
                    f"Bulk-Abgleich fertig: {total} Treffer gesamt"))
                self.after(0, lambda: self._set_status(
                    f"GEDCOM-Abgleich fertig: {total} Treffer", "ok"))
                # Match-Tabelle aktualisieren (🌳N-Spalte) + aktuelle Detail-Ansicht
                self.after(0, self._refresh_match_table)
                self.after(0, lambda: self._state.notify_data_changed("import"))
                if self._selected_match:
                    self.after(0, lambda: self._load_gedcom_link_panel(self._selected_match))
            except Exception as exc:
                log.warning("bridge bulk: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))
                self.after(0, lambda exc=exc: self._set_status(f"Fehler: {exc}", "error"))

        import threading
        threading.Thread(target=_worker, daemon=True, name="bridge-bulk").start()

    def _on_gedcom_loaded_update_header(self, ged: dict):
        """Callback nach _ensure_gedcom_loaded: GEDCOM-Dateiname in Header zeigen."""
        import os
        path = ged.get("path", "")
        name = os.path.basename(path) if path else "—"
        n = len(ged.get("people", {}))
        if hasattr(self, "_ged_file_var"):
            self._ged_file_var.set(f"{name}  ({n} Personen)")
        # GEDCOM hat sich geändert → Statistik als veraltet markieren.
        self._invalidate_stats()
        # Personen-Tab: gecachte Wurzel-/Vorfahren-Karte verwerfen (neue Wurzel).
        if self._persons_tab is not None:
            try:
                self._persons_tab.invalidate_tree_cache()
            except Exception as e:
                log.debug("persons invalidate_tree_cache: %s", e)

    def _open_xref_review(self):
        """Fenster zum Prüfen grenzwertiger Duplikat-Verknüpfungen (gedcom_person_xref)."""
        try:
            from ancestry.core import bridge
        except Exception as e:
            messagebox.showerror(self._t("dlg.duplicates"), f"bridge nicht ladbar: {e}"); return

        win = tk.Toplevel(self)
        win.title("Duplikate prüfen – Querbezüge")
        win.geometry("900x460")

        bar = ttk.Frame(win); bar.pack(fill="x", padx=8, pady=6)
        ttk.Label(bar, text="Score von").pack(side="left")
        lo_var = tk.StringVar(value="0.72"); hi_var = tk.StringVar(value="0.85")
        ttk.Entry(bar, textvariable=lo_var, width=5).pack(side="left", padx=2)
        ttk.Label(bar, text="bis").pack(side="left")
        ttk.Entry(bar, textvariable=hi_var, width=5).pack(side="left", padx=2)
        only_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text=self._t("dlg.c_unreviewed_only"), variable=only_auto).pack(side="left", padx=8)

        cols = ("score", "status", "a", "b")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=15)
        for c, t, w in [("score","Score",60),("status","Status",80),
                        ("a","A (dein GEDCOM)",360),("b","B (andere Quelle)",360)]:
            tree.heading(c, text=t); tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=8)
        rowmap = {}

        def _fmt(r, pre):
            return (f"{r[pre+'_given'] or ''} {r[pre+'_surname'] or ''} "
                    f"*{r[pre+'_by'] or '?'} †{r[pre+'_dy'] or '?'} "
                    f"[{r[pre+'_bp'] or ''}]").strip()

        def reload():
            tree.delete(*tree.get_children()); rowmap.clear()
            try:
                lo, hi = float(lo_var.get()), float(hi_var.get())
            except ValueError:
                lo, hi = 0.0, 1.0
            pairs = bridge.get_xref_pairs(self._db, lo=lo, hi=hi)
            for r in pairs:
                if only_auto.get() and r["status"] != "auto":
                    continue
                iid = tree.insert("", "end", values=(
                    f"{r['score']:.3f}", r["status"], _fmt(r,"a"), _fmt(r,"b")))
                rowmap[iid] = r
            win.title(f"Duplikate prüfen – {len(rowmap)} Paare")

        def _decide(status):
            for iid in tree.selection():
                r = rowmap.get(iid)
                if not r: continue
                bridge.set_xref_status(self._db, r["ged_id_primary"],
                                       r["ged_id_other"], status)
                tree.set(iid, "status", status)

        btns = ttk.Frame(win); btns.pack(fill="x", padx=8, pady=6)
        ttk.Button(btns, text=self._t("dlg.b_load"), command=reload).pack(side="left")
        ttk.Button(btns, text=self._t("dlg.b_same_person"),
                   command=lambda: _decide("confirmed")).pack(side="left", padx=4)
        ttk.Button(btns, text="✗ Verschiedene (ablehnen)",
                   command=lambda: _decide("rejected")).pack(side="left", padx=4)
        ttk.Label(btns, text=self._t("dlg.l_multiselect"),
                  foreground="#777").pack(side="right")
        reload()

    def _auto_assign_sides(self):
        """Weist Seiten (väterlich/mütterlich) zu — via Mutter-Kit oder GEDCOM-Baum."""
        test_guid = self._current_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return

        dlg = tk.Toplevel(self)
        dlg.title("Seiten automatisch zuweisen")
        dlg.resizable(False, False)
        dlg.grab_set()
        ttk.Label(dlg, text="Methode:", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12,4))

        method_var = tk.StringVar(value="kit")

        # ── Methode A: via Mutter-Kit ─────────────────────────────────────────
        kits = self._db.get_kits()
        other_kits = [k for k in kits if k.guid != test_guid]
        rb_kit = ttk.Radiobutton(dlg, text="Via zweites Ancestry-Kit (Mutter/Vater):",
                                 variable=method_var, value="kit")
        rb_kit.grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(4,2))
        kit_names = [f"{k.name or k.guid[:16]}…" for k in other_kits]
        kit_combo = ttk.Combobox(dlg, values=kit_names, state="readonly", width=34)
        if kit_names:
            kit_combo.current(0)
        else:
            kit_combo.set("(kein zweites Kit vorhanden)")
            kit_combo.configure(state="disabled")
        kit_combo.grid(row=2, column=0, columnspan=2, padx=28, pady=(0,4), sticky="w")
        kit_combo.bind("<Button-1>", lambda _: method_var.set("kit"))
        # Hinweis: ohne zweites Kit ist die Seiten-Zuweisung unzuverlässig
        ttk.Label(dlg,
            text=self._t("dlg.l_side_estimate_note"),
            foreground="#a06000", font=("Segoe UI", 8), justify="left").grid(
            row=2, column=2, padx=(8,14), pady=(0,4), sticky="w")

        # ── Methode B: via GEDCOM-Baum ────────────────────────────────────────
        has_gedcom = bool(getattr(self, "_gedcom", None))
        amap = (self._gedcom.get("amap") or {}) if has_gedcom else {}
        has_amap = bool(amap)
        ged_state = "normal" if (has_gedcom and has_amap) else "disabled"
        rb_ged = ttk.Radiobutton(dlg, text="Via GEDCOM-Baum (Ahnen-Map):",
                                 variable=method_var, value="ged", state=ged_state)
        rb_ged.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(4,2))
        # Show which person is at path 'M' (= the mother) from the amap
        if has_amap:
            mother_gid = next((gid for gid, p in amap.items() if p == "M"), None)
            if mother_gid:
                inds = self._gedcom.get("individuals", {})
                mo_ind = inds.get(mother_gid, {})
                mo_name = (mo_ind.get("NAME") or mother_gid).replace("/","").strip()
                ged_hint = f"Mutter im Baum: {mo_name}"
            else:
                ged_hint = "Keine Mutter im Ahnen-Map gefunden (Wurzelperson prüfen)"
        else:
            ged_hint = "GEDCOM laden + Wurzelperson setzen, um Ahnen-Map zu erstellen"
        ttk.Label(dlg, text=ged_hint, foreground="#555555",
                  font=("Segoe UI", 8)).grid(
            row=4, column=0, columnspan=2, padx=28, pady=(0,12), sticky="w")

        # ── Methode C: Ancestry-Schätzung (Tag 8 / matchClusterCode) ─────────────
        # Vorhandene Daten: tags_json Tag "8" = "M"/"P" und match_cluster_code
        try:
            with self._db._cursor() as _cur:
                _cur.execute(
                    "SELECT COUNT(*) FROM matches WHERE test_guid=? "
                    "AND (tags_json LIKE '%\"8\": \"M\"%' OR tags_json LIKE '%\"8\":\"M\"%' "
                    "OR tags_json LIKE '%\"8\": \"P\"%' OR tags_json LIKE '%\"8\":\"P\"%' "
                    "OR match_cluster_code IN ('maternal','paternal'))",
                    (test_guid,))
                n_ancestry = _cur.fetchone()[0]
        except Exception as e:
            log.debug("auto_assign_sides ancestry count: %s", e)
            n_ancestry = 0

        rb_anc = ttk.Radiobutton(dlg,
            text=self._t("dlg.l_import_anc_est"),
            variable=method_var, value="ancestry")
        rb_anc.grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(4,2))
        ttk.Label(dlg, text=f"{n_ancestry} Matches mit Ancestry-Seitenzuweisung gefunden",
                  foreground="#555555", font=("Segoe UI", 8)).grid(
            row=6, column=0, columnspan=2, padx=28, pady=(0,12), sticky="w")
        if n_ancestry == 0:
            rb_anc.configure(state="disabled")

        # ── Buttons ────────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(dlg); btn_frame.grid(row=7, column=0, columnspan=2,
                                                    padx=14, pady=(4,12))
        result = {"ok": False}

        def _ok():
            result["ok"] = True
            # Auswahl JETZT auslesen – nach dlg.destroy() sind die Widgets weg
            result["method"] = method_var.get()
            try:
                result["kit_index"] = kit_combo.current()
            except tk.TclError:
                result["kit_index"] = -1
            dlg.destroy()

        ttk.Button(btn_frame, text=self._t("dlg.cancel"), command=dlg.destroy).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✓ Zuweisen", command=_ok).pack(side="left", padx=4)
        self.wait_window(dlg)
        if not result["ok"]:
            return

        method = result.get("method", "")
        kit_index = result.get("kit_index", -1)
        if method == "kit":
            # Via Mutter-Kit
            if not other_kits or kit_index < 0:
                messagebox.showinfo(self._t("dlg.no_kit"), self._t("dlg.m_no_second_kit"))
                return
            parent_kit = other_kits[kit_index]
            # min_cm=20: kleine „nur bei mir"-Matches nicht vorschnell der
            # Gegenseite zuordnen (unzuverlässig unterhalb ~20 cM).
            overlap = self._db.get_paternal_maternal_overlap(
                test_guid, parent_kit.guid, min_cm=20.0)
            mat = overlap["shared"]
            pat = overlap["only_a"]
            n_mat = self._db.bulk_set_side(list(mat), "maternal")
            n_pat = self._db.bulk_set_side(list(pat), "paternal")
            self._refresh_match_table()
            messagebox.showinfo(self._t("dlg.result"),
                                f"✅ {n_mat} Matches als mütterlich markiert\n"
                                f"✅ {n_pat} Matches als väterlich markiert\n"
                                f"(nur Matches ≥ 20 cM zuverlässig zuweisbar)\n\n"
                                f"Eltern-Kit: {parent_kit.name or parent_kit.guid[:16]}")
        elif method == "ged":
            # Via GEDCOM-Baum
            if not has_amap:
                messagebox.showwarning(self._t("dlg.no_anc_map"),
                                       self._t("dlg.m_load_gedcom"))
                return
            try:
                from ancestry.core.bridge import infer_side_from_links
            except ImportError:
                messagebox.showerror(self._t("dlg.error"), self._t("dlg.m_bridge_unloadable"))
                return

            with self._db._cursor() as cur:
                match_guids = [r[0] for r in cur.execute(
                    "SELECT DISTINCT match_guid FROM gedcom_links WHERE test_guid=?",
                    (test_guid,)
                ).fetchall()]

            pat_guids, mat_guids, both_guids = [], [], []
            for mguid in match_guids:
                side = infer_side_from_links(self._db, test_guid, mguid, amap)
                if side == "paternal":
                    pat_guids.append(mguid)
                elif side == "maternal":
                    mat_guids.append(mguid)
                elif side == "both":
                    both_guids.append(mguid)

            n_pat = self._db.bulk_set_side(pat_guids, "paternal")
            n_mat = self._db.bulk_set_side(mat_guids, "maternal")
            self._refresh_match_table()
            messagebox.showinfo(self._t("dlg.ged_side"),
                                f"✅ {n_pat} Matches als väterlich markiert\n"
                                f"✅ {n_mat} Matches als mütterlich markiert\n"
                                f"   {len(both_guids)} Matches beidseitig (unverändert)\n\n"
                                f"Basis: {len(amap)} Vorfahren im Ahnen-Map")

        elif method == "ancestry":
            # Via Ancestry-Schätzung (Tag 8 / matchClusterCode)
            try:
                with self._db._cursor() as cur:
                    mat_guids = [r[0] for r in cur.execute(
                        "SELECT match_guid FROM matches WHERE test_guid=? "
                        "AND (tags_json LIKE '%\"8\": \"M\"%' OR tags_json LIKE '%\"8\":\"M\"%' "
                        "OR match_cluster_code = 'maternal')",
                        (test_guid,)).fetchall()]
                    pat_guids = [r[0] for r in cur.execute(
                        "SELECT match_guid FROM matches WHERE test_guid=? "
                        "AND (tags_json LIKE '%\"8\": \"P\"%' OR tags_json LIKE '%\"8\":\"P\"%' "
                        "OR tags_json LIKE '%\"8\": \"F\"%' OR tags_json LIKE '%\"8\":\"F\"%' "
                        "OR match_cluster_code = 'paternal')",
                        (test_guid,)).fetchall()]
            except Exception as e:
                messagebox.showerror(self._t("dlg.error"), str(e))
                return
            n_mat = self._db.bulk_set_side(mat_guids, "maternal")
            n_pat = self._db.bulk_set_side(pat_guids, "paternal")
            self._refresh_match_table()
            messagebox.showinfo(self._t("dlg.anc_estimate"),
                                f"✅ {n_mat} Matches als mütterlich markiert\n"
                                f"✅ {n_pat} Matches als väterlich markiert\n\n"
                                f"Quelle: Ancestry Tag 8 / Cluster-Code")

    def _assign_cluster_side(self):
        """Weist allen Mitgliedern des gewählten Clusters eine Seite zu."""
        sel = self._cluster_tab.get_cluster_list_selection()
        if not sel:
            messagebox.showinfo(self._t("dlg.no_cluster"), self._t("dlg.m_choose_cluster"))
            return
        cid = int(sel[0])
        members = self._cluster_tab.get_clusters().get(cid, [])
        if not members:
            return
        test_guid = self._current_guid()
        if not test_guid:
            return

        dlg = tk.Toplevel(self)
        dlg.title(f"Cluster #{cid} – Seite zuweisen")
        dlg.resizable(False, False)
        dlg.grab_set()
        ttk.Label(dlg, text=f"Seite für alle {len(members)} Mitglieder von Cluster #{cid}:",
                  font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(14, 8), sticky="w")

        side_var = tk.StringVar(value="paternal")
        ttk.Radiobutton(dlg, text=self._t("dlg.r_paternal"),
                        variable=side_var, value="paternal").grid(
            row=1, column=0, columnspan=2, padx=24, pady=2, sticky="w")
        ttk.Radiobutton(dlg, text=self._t("dlg.r_maternal"),
                        variable=side_var, value="maternal").grid(
            row=2, column=0, columnspan=2, padx=24, pady=2, sticky="w")
        ttk.Radiobutton(dlg, text=self._t("dlg.r_remove_side"),
                        variable=side_var, value="").grid(
            row=3, column=0, columnspan=2, padx=24, pady=(2, 10), sticky="w")

        result = {"ok": False}
        def _ok():
            result["ok"] = True
            dlg.destroy()

        bf = ttk.Frame(dlg); bf.grid(row=4, column=0, columnspan=2, padx=14, pady=(0, 12))
        ttk.Button(bf, text="OK", command=_ok, width=10).pack(side="left", padx=4)
        ttk.Button(bf, text=self._t("dlg.cancel"), command=dlg.destroy, width=10).pack(side="left", padx=4)
        dlg.wait_window()

        if not result["ok"]:
            return

        guids = [m["guid"] for m in members]
        side = side_var.get()
        n = self._db.bulk_set_side(guids, side)
        self._refresh_match_table()

        if side:
            side_label = "väterlich" if side == "paternal" else "mütterlich"
            messagebox.showinfo(self._t("dlg.side_assigned"),
                                f"✅ {n} Matches als {side_label} markiert\n"
                                f"Cluster #{cid} ({len(members)} Mitglieder)")
        else:
            messagebox.showinfo(self._t("dlg.side_removed"),
                                f"✅ Seitenzuweisung für {n} Matches entfernt\n"
                                f"Cluster #{cid} ({len(members)} Mitglieder)")
