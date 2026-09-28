"""GEDCOM-Treffer-Panel-Mixin für MatchesTab: Ahnentafel-Abgleich im
Detail-Panel anzeigen (Bulk-Match-Ergebnisse pro Match), manuelle
GEDCOM-Verknüpfung suchen/anwenden.

Elfter Baustein der Mixin-Aufteilung (siehe MatchesTab-Docstring in
matches.py für die Übersicht). `load_gedcom_link_panel` ist public und
wird von außen aufgerufen (AncestryDnaApp._load_gedcom_link_panel →
self._matches_tab.load_gedcom_link_panel(match)) — das bleibt
unverändert, da der Aufruf nur den Methodennamen auf der Instanz kennt,
nicht die definierende Basisklasse. Die UI-Widgets des Panels
(`_ged_link_tree`, `_ged_rerun_btn`, `_ged_link_var`, `_ged_link_result`,
`_ged_link_status`) werden weiterhin in `_build_gedcom_link_panel`
(bleibt in matches.py) angelegt; diese Methoden lesen/befüllen sie nur.

Erwartet von der Host-Klasse (MatchesTab): self._state, self._get_gedcom(),
self._get_test_guid(), self._selected_match, self._on_gedcom_header_update(),
self._on_match_select(), self._ged_link_tree, self._ged_rerun_btn,
self._ged_link_var, self._ged_link_result, self._ged_link_status.
"""
from __future__ import annotations

import logging
import threading
import webbrowser
from urllib.parse import quote

from ancestry.models import DnaMatch

log = logging.getLogger(__name__)


class GedcomLinkPanelMixin:
    """GEDCOM-Ahnentafel-Abgleich im Detail-Panel + manuelle Verknüpfung."""

    def load_gedcom_link_panel(self, match: "DnaMatch"):
        """Füllt den GEDCOM-Treffer-Tab für den ausgewählten Match."""
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        self._ged_rerun_btn.configure(state="normal")
        ged = self._get_gedcom()
        if not ged:
            self._ged_link_status.set(self._state.t("md.ged_none"))
            return

        test_guid = self._get_test_guid()
        if not test_guid:
            return

        self._ged_link_status.set(self._state.t("md.ged_searching"))

        self.after(0, lambda: self._on_gedcom_header_update(ged))

        def _worker():
            try:
                from ancestry.core import bridge
                bridge.ensure_tables(self._state.db)
                # GEDCOM-Personen importieren, falls leer
                if bridge.get_gedcom_person_count(self._state.db) == 0:
                    n = bridge.import_gedcom_persons(
                        self._state.db, ged["individuals"], ged.get("path", ""),
                        families=ged.get("families") or {})
                    log.info("bridge: %d Personen importiert", n)
                rows = bridge.run_match_for_match(self._state.db, test_guid, match.match_guid)
                self.after(0, lambda: self._fill_ged_link_tree(rows, match))
            except Exception as exc:
                log.warning("bridge: %s", exc)
                msg = str(exc).lower()
                if "no such table" in msg or "no table" in msg:
                    hint = "Bitte zuerst GEDCOM-Datei laden (Werkzeuge → GEDCOM-Import)"
                elif "no column" in msg or "no such column" in msg:
                    hint = "DB-Schema veraltet — bitte Anwendung neu starten"
                else:
                    hint = f"Fehler: {exc}"
                self.after(0, lambda h=hint: self._ged_link_status.set(h))

        threading.Thread(target=_worker, daemon=True, name="bridge").start()

    def _fill_ged_link_tree(self, rows: list, match: "DnaMatch"):
        # Stale-Guard: Auswahl könnte während des Worker-Laufs gewechselt haben
        if not self._selected_match or self._selected_match.match_guid != match.match_guid:
            return
        self._ged_link_tree.delete(*self._ged_link_tree.get_children())
        if not rows:
            self._ged_link_status.set(self._state.t("md.ged_no_ped"))
            return
        hits = sum(1 for r in rows if r["icon"])
        self._ged_link_status.set(
            f"{hits} Treffer von {len(rows)} Vorfahren  ·  {match.display_name}")
        try:
            from ancestry.core.bridge import path_to_sosa
        except ImportError:
            path_to_sosa = lambda p: ""  # noqa: E731
        for r in rows:
            tag = "strong" if r["icon"] == "✓" else ("weak" if not r["icon"] else "")
            ap = r["ahnen_path"] or ""
            sosa = path_to_sosa(ap) if ap else ""
            self._ged_link_tree.insert("", "end", values=(
                r["generation"], sosa, ap,
                r["ped_name"],   r["ped_year"],
                r["icon"],
                r["ged_name"],   r["ged_year"],
                r["score"],      r["method"],
            ), tags=(tag,) if tag else ())

    def _on_ged_link_dblclick(self, _event):
        """Doppelklick auf eine GEDCOM-Treffer-Zeile → FamilySearch-Suche nach Name."""
        sel = self._ged_link_tree.selection()
        if not sel:
            return
        vals = self._ged_link_tree.item(sel[0], "values")
        # cols: gen(0) sosa(1) path(2) ped_name(3) ped_year(4) icon(5) ged_name(6) ged_year(7)
        if not vals or len(vals) < 8 or vals[6] == "—" or not vals[6]:
            return
        ged_name = vals[6]
        ged_year = vals[7] or ""
        parts = ged_name.split()
        if parts:
            q = quote(parts[-1])
            url = (f"https://www.familysearch.org/search/record/results"
                   f"?q.surname={q}" + (f"&q.birthLikeDate.from={ged_year}&q.birthLikeDate.to={ged_year}"
                                        if ged_year else ""))
            webbrowser.open(url)

    def _rerun_gedcom_for_selected(self):
        """Re-runs GEDCOM matching for the currently selected match on demand."""
        if self._selected_match:
            self.load_gedcom_link_panel(self._selected_match)

    def _ged_link_search(self):
        """Sucht GEDCOM-Personen nach GED-ID oder Name."""
        q = self._ged_link_var.get().strip()
        if not q:
            return
        try:
            with self._state.db._cursor() as cur:
                rows = cur.execute(
                    "SELECT ged_id, given_name, surname, birth_year FROM gedcom_persons "
                    "WHERE ged_id=? OR (given_name LIKE ? OR surname LIKE ?) LIMIT 5",
                    (q, f"%{q}%", f"%{q}%"),
                ).fetchall()
            if rows:
                lines = [
                    f"{r['ged_id']}: {r['given_name'] or ''} {r['surname'] or ''} "
                    f"({'*' + str(r['birth_year']) if r['birth_year'] else ''})"
                    for r in rows
                ]
                self._ged_link_result.set("\n".join(lines))
            else:
                self._ged_link_result.set("Keine Ergebnisse.")
        except Exception as e:
            self._ged_link_result.set(f"Fehler: {e}")

    def _ged_link_apply(self):
        """Speichert die manuelle GEDCOM-Verknüpfung für den ausgewählten Match."""
        m = self._selected_match
        if not m:
            return
        q = self._ged_link_var.get().strip()
        if not q:
            return
        try:
            test_guid = self._get_test_guid()
            with self._state.db._cursor() as cur:
                r = cur.execute(
                    "SELECT ged_id FROM gedcom_persons WHERE ged_id=? LIMIT 1", (q,)
                ).fetchone()
                if not r:
                    r = cur.execute(
                        "SELECT ged_id FROM gedcom_persons "
                        "WHERE given_name LIKE ? OR surname LIKE ? LIMIT 1",
                        (f"%{q}%", f"%{q}%"),
                    ).fetchone()
                if r:
                    ged_id = r["ged_id"]
                    cur.execute(
                        """INSERT OR REPLACE INTO gedcom_links
                           (test_guid, match_guid, ged_id, match_method, total_score)
                           VALUES (?, ?, ?, 'manual', 0.0)""",
                        (test_guid or "", m.match_guid, ged_id),
                    )
                    self._ged_link_result.set(f"✓ Verknüpft: {ged_id}")
                    self._on_match_select(None)
                else:
                    self._ged_link_result.set("GED-ID nicht gefunden.")
        except Exception as e:
            self._ged_link_result.set(f"Fehler: {e}")
