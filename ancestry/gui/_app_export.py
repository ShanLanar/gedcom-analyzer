"""Export-/Import-Mixin für AncestryDnaApp (Menü 'Datei': CSV-/XLSX-Export,
Namens-Import aus Browser-DOM-Export).

Achter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für die
Begründung). Die Export-Methoden lesen nur Daten aus self._db und melden
Ergebnisse über self._set_status()/messagebox — keine eigenen
Zustandsattribute. _import_names schreibt direkt in die matches-Tabelle und
stößt danach self._refresh_match_table() an.

Erwartet von der Host-Klasse (AncestryDnaApp): self._db, self._t(),
self._set_status(), self._get_kit_guid(), self._state.current_test_guid,
self._refresh_match_table().
"""
from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox

log = logging.getLogger(__name__)


class ExportMixin:
    """CSV-/XLSX-Export (einzeln, Shared, Komplett) und Namens-Import."""

    def _export_csv(self):
        from ancestry.core.export import export_csv
        matches = self._db.get_matches()
        if not matches:
            messagebox.showinfo(self._t("dlg.no_data"), self._t("dlg.m_no_matches"))
            return
        p = filedialog.asksaveasfilename(title="Matches als CSV",
            defaultextension=".csv", filetypes=[("CSV","*.csv"),("Alle","*.*")],
            initialfile="ancestry_dna_matches.csv")
        if p:
            try:
                export_csv(matches, p)
                self._show_export_done(p, f"{len(matches)} Matches")
            except Exception as e:
                log.debug("export_csv: %s", e)
                self._set_status(f"⚠ CSV-Export: {e}", "warn")

    def _export_shared_csv(self):
        from ancestry.core.export import export_shared_csv
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        if not test_guid:
            messagebox.showwarning(self._t("dlg.no_kit"), self._t("dlg.m_choose_kit"))
            return
        with self._db._cursor() as cur:
            cur.execute("SELECT * FROM shared_matches WHERE test_guid=? ORDER BY shared_cm_b DESC",
                        (test_guid,))
            rows = cur.fetchall()
        if not rows:
            messagebox.showinfo(self._t("dlg.no_data"), self._t("dlg.m_no_shared_db"))
            return
        from ancestry.models import SharedMatch
        shared = [SharedMatch.from_db_row(dict(r)) for r in rows]
        matches = {m.match_guid: m.display_name for m in self._db.get_matches(test_guid=test_guid)}

        p = filedialog.asksaveasfilename(title="Shared Matches als CSV",
            defaultextension=".csv", filetypes=[("CSV","*.csv"),("Alle","*.*")],
            initialfile="ancestry_shared_matches.csv")
        if p:
            try:
                export_shared_csv(shared, p, matches)
                self._show_export_done(p, f"{len(shared)} Shared Matches")
            except Exception as e:
                log.debug("export_shared_csv: %s", e)
                self._set_status(f"⚠ Shared-CSV-Export: {e}", "warn")

    def _export_xlsx(self):
        from ancestry.core.export import export_xlsx
        matches = self._db.get_matches()
        if not matches:
            messagebox.showinfo(self._t("dlg.no_data"), self._t("dlg.m_no_matches"))
            return
        p = filedialog.asksaveasfilename(title="Matches als XLSX",
            defaultextension=".xlsx", filetypes=[("XLSX","*.xlsx"),("Alle","*.*")],
            initialfile="ancestry_dna_matches.xlsx")
        if p:
            self._set_status("Export läuft…")
            try:
                export_xlsx(matches, p)
                self._set_status(f"Export fertig: {len(matches)} Matches", "ok")
                self._show_export_done(p, f"{len(matches)} Matches")
            except Exception as e:
                log.debug("export_xlsx: %s", e)
                self._set_status(f"⚠ XLSX-Export: {e}", "warn")

    def _export_all_xlsx(self):
        from ancestry.core.export import export_xlsx
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        matches = self._db.get_matches(test_guid=test_guid)
        if not matches:
            messagebox.showinfo(self._t("dlg.no_data"), self._t("dlg.m_no_matches"))
            return
        shared, name_map = [], {}
        if test_guid:
            with self._db._cursor() as cur:
                cur.execute("SELECT * FROM shared_matches WHERE test_guid=? ORDER BY shared_cm_b DESC",
                            (test_guid,))
                from ancestry.models import SharedMatch
                shared = [SharedMatch.from_db_row(dict(r)) for r in cur.fetchall()]
            name_map = {m.match_guid: m.display_name for m in matches}

        # Statistik-Kennzahlen
        try:
            stats = self._db.get_statistics(test_guid)
        except Exception as e:
            log.debug("export_all get_statistics: %s", e)
            self._set_status(f"⚠ Statistik-Abfrage beim Export: {e}", "warn")
            stats = None

        # Analyse-Blatt: Herkunft (Regel + ML) und Seite je Match
        import json as _json
        analysis = []
        try:
            with self._db._cursor() as cur:
                rows = cur.execute(
                    "SELECT display_name, shared_cm, paternal_maternal, "
                    "probable_origin, ml_origin FROM matches WHERE test_guid=? "
                    "ORDER BY shared_cm DESC", (test_guid,)).fetchall()
            def _reg(j):
                try:
                    d = _json.loads(j) if j else {}
                    r = d.get("region", "")
                    pr = d.get("score", d.get("prob"))
                    return f"{r} ({pr})" if r and pr is not None else r
                except (ValueError, KeyError):
                    return ""
            for r in rows:
                analysis.append({
                    "name":   r["display_name"],
                    "cm":     r["shared_cm"],
                    "side":   {"paternal":"väterlich","maternal":"mütterlich",
                               "both":"beidseitig"}.get(r["paternal_maternal"] or "", ""),
                    "origin_rule": _reg(r["probable_origin"]),
                    "origin_ml":   _reg(r["ml_origin"]),
                })
        except Exception as e:
            log.warning("export_all analysis rows: %s", e)
            analysis = []

        p = filedialog.asksaveasfilename(title=self._t("dlg.b_export_xlsx"),
            defaultextension=".xlsx", filetypes=[("XLSX","*.xlsx"),("Alle","*.*")],
            initialfile="ancestry_dna_komplett.xlsx")
        if p:
            self._set_status("Komplett-Export läuft…")
            try:
                export_xlsx(matches, p, shared if shared else None, name_map,
                            stats=stats, analysis=analysis)
                self._set_status(
                    f"Komplett-Export fertig: {len(matches)} Matches", "ok")
                self._show_export_done(
                    p,
                    f"{len(matches)} Matches + {len(shared)} Shared Matches"
                    " + Statistik + Herkunft/Seiten",
                )
            except Exception as e:
                log.debug("export_all_xlsx: %s", e)
                self._set_status(f"⚠ Komplett-XLSX-Export: {e}", "warn")

    # ─────────────────────────────────────────────────────────────────────
    # Hilfsmethoden
    # ─────────────────────────────────────────────────────────────────────

    def _show_export_done(self, path: str, msg: str):
        """Dialog nach erfolgreichem Export mit '📂 Öffnen'-Button."""
        dlg = tk.Toplevel(self)
        dlg.title(self._t("dlg.done"))
        dlg.resizable(False, False)
        tk.Label(
            dlg,
            text=f"{msg}\n→ {path}",
            justify="left",
            wraplength=480,
            pady=8, padx=14,
        ).pack()
        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=(0, 10))
        tk.Button(
            btn_frame, text="📂 Öffnen",
            command=lambda p=path: self._open_exported_file(p),
        ).pack(side="left", padx=6)
        tk.Button(btn_frame, text="OK", command=dlg.destroy).pack(side="left", padx=6)
        dlg.grab_set()

    @staticmethod
    def _open_exported_file(path: str):
        import subprocess
        import sys as _sys
        try:
            if _sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif _sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _import_names(self):
        """
        Importiert Namen aus JSON (Browser-DOM-Export).
        Filtert Rausch-Eintraege wie "This match is connected..." heraus.
        Dedupliziert pro sampleId: bester Name gewinnt.
        """
        path = filedialog.askopenfilename(
            title=self._t("dlg.t_import_names"),
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv"), ("Alle", "*.*")],
        )
        if not path:
            return

        import csv
        import json
        import re

        # Muster die KEIN echter Name sind
        NOISE_PATTERNS = [
            "this match is connected",
            "public linked tree",
            "unlinked tree",
            "private tree",
            "no tree",
        ]

        def is_noise(name: str) -> bool:
            n = name.lower().strip()
            return any(n.startswith(p) for p in NOISE_PATTERNS)

        def name_quality(name: str) -> int:
            """Hoehere Zahl = besserer Name. Echter Name > Benutzername > Initialen."""
            if is_noise(name):
                return -1
            # Initialen wie "J. M." = niedrige Qualitaet
            if re.match(r'^[A-Z]\.\s+[A-Z]\.$', name.strip()):
                return 1
            # Echter Name (Vor- + Nachname) = hohe Qualitaet
            if ' ' in name and not name.startswith('@'):
                return 3
            return 2  # Benutzername

        # Einlesen
        raw: list[tuple[str, str]] = []
        try:
            if path.lower().endswith(".json"):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    # Listen-Format: [{"sampleId": "...", "name": "..."}, ...]
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        sid  = (item.get("sampleId") or item.get("sample_id")
                                or item.get("guid", "")).strip()
                        name = (item.get("name") or item.get("displayName")
                                or item.get("matchName") or item.get("managedName")
                                or "").strip()
                        if sid and name:
                            raw.append((sid, name))
                elif isinstance(data, dict):
                    # Dict-Format (profileData-Antwort):
                    #   {"<sid>": {"matchName": "...", "managedName": "..."}, ...}
                    #   oder {"<sid>": "Name", ...}
                    for sid, info in data.items():
                        sid = (sid or "").strip()
                        if isinstance(info, dict):
                            name = (info.get("matchName") or info.get("managedName")
                                    or info.get("name") or info.get("displayName")
                                    or "").strip()
                        else:
                            name = str(info or "").strip()
                        if sid and name:
                            raw.append((sid, name))
            else:
                with open(path, encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        sid  = (row.get("sampleId") or row.get("match_guid", "")).strip()
                        name = (row.get("name") or row.get("display_name", "")).strip()
                        if sid and name:
                            raw.append((sid, name))
        except Exception as e:
            messagebox.showerror(self._t("dlg.import_error"), str(e))
            return

        # Deduplizieren: bester Name pro sampleId
        best: dict[str, tuple[str, int]] = {}
        for sid, name in raw:
            q = name_quality(name)
            if q < 0:
                continue
            if sid not in best or q > best[sid][1]:
                best[sid] = (name, q)

        if not best:
            messagebox.showinfo(self._t("dlg.no_result"),
                                self._t("dlg.m_no_valid_names"))
            return

        # In DB schreiben. Ueberschrieben werden nur Platzhalter:
        # leer/Anonym/NULL, Gender-Suffixe und das 8-stellige GUID-Kuerzel
        # (z.B. "BEC4AE66"), das matchList ohne echten Namen speichert.
        # Manuell eingetragene echte Namen bleiben unangetastet.
        HEX8 = "[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]" \
               "[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]"
        updated = skipped = 0
        with self._db._cursor() as cur:
            for sid, (name, _) in best.items():
                cur.execute(
                    "UPDATE matches SET display_name=? "
                    "WHERE match_guid=? "
                    "AND (display_name='' OR display_name='Anonym' "
                    "     OR display_name IS NULL "
                    "     OR display_name LIKE '% (m.)' "
                    "     OR display_name LIKE '% (w.)' "
                    f"     OR display_name GLOB '{HEX8}')",
                    (name, sid)
                )
                if cur.rowcount:
                    updated += 1
                else:
                    skipped += 1

        self._refresh_match_table()
        msg = (str(len(raw)) + " Roheintraege, "
               + str(len(best)) + " eindeutige Matches, "
               + str(updated) + " aktualisiert"
               + (" (" + str(skipped) + " uebersprungen)" if skipped else ""))
        messagebox.showinfo(self._t("dlg.import_done"), msg)
        self._set_status("Namen: " + str(updated) + " importiert")
