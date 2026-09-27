"""Anreicherungs-Läufe-Mixin für AncestryDnaApp: ML-Herkunftsmodell,
WikiTree-Linienverlängerung, Herkunfts-Inferenz aus Pedigree-Nachnamen,
GEDmatch-Brücken-Verknüpfung, GEDCOM-Endogamie-Transfer.

Vierzehnter Baustein der Mixin-Aufteilung (siehe _app_recent_files.py für
die Begründung). Sechs voneinander unabhängige Hintergrund-Läufe, die alle
demselben Muster folgen: Vorbedingung prüfen, Status auf
`self._ged_link_status` setzen, in einem Daemon-Thread arbeiten und über
`self.after(0, ...)` ins UI zurückmelden. Keine eigenen Zustandsattribute.

Erwartet von der Host-Klasse (AncestryDnaApp): self._db, self._state,
self._t(), self._get_kit_guid(), self._refresh_match_table(),
self._ged_link_status, self._selected_match, self._gedcom (optional,
per getattr).
"""
from __future__ import annotations

import logging
import threading
from tkinter import messagebox

log = logging.getLogger(__name__)


class EnrichmentRunsMixin:
    """ML-Herkunft, WikiTree-Verlängerung, Herkunfts-Inferenz, GEDmatch-Brücke,
    GEDCOM-Endogamie-Transfer."""

    def _run_endogamy_transfer(self):
        """Überträgt GEDCOM-Endogamie-Scores via Geburtsort-Abgleich auf Matches."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo(self._t("dlg.gedcom"), self._t("md.ged_none"))
            return
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Endogamie-Transfer läuft …")

        def _worker():
            try:
                import importlib.util as _ilu
                import os as _os

                from ancestry.core import bridge as _bridge
                # GEDCOM-Endogamie aus dem Haupt-Analyzer (tasks ist installiert)
                _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
                from lib.places import load_location_data
                from tasks.endogamy import compute_endogamy_with_detailed_places
                # Root-config direkt laden (nicht über sys.modules["config"],
                # der auf ancestry/config.py zeigt)
                _cfg_spec = _ilu.spec_from_file_location(
                    "_root_config", _os.path.join(_root, "config.py"))
                _cfg_root = _ilu.module_from_spec(_cfg_spec)
                _cfg_spec.loader.exec_module(_cfg_root)
                loc = load_location_data(
                    _cfg_root.DEFAULT_CONFIG.get("location_data_json", ""))
                endo_results = compute_endogamy_with_detailed_places(
                    ged["individuals"], ged["families"],
                    root_id="", location_data=loc)
                n = _bridge.apply_gedcom_endogamy_to_matches(
                    self._db, test_guid, endo_results,
                    progress_cb=lambda m, **kw: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)))
                self.after(0, lambda: self._ged_link_status.set(
                    f"Endogamie-Transfer fertig: {n} Matches markiert"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("endogamy-transfer: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        threading.Thread(target=_worker, daemon=True, name="endo-transfer").start()

    def _run_ml_origin(self):
        """Trainiert (falls nötig) das ML-Herkunftsmodell auf dem GEDCOM und
        wendet es als 'zweite Meinung' auf alle Matches an (ml_origin-Spalte)."""
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        if not test_guid:
            return
        self._ged_link_status.set("ML-Herkunft: starte …")

        def _worker():
            try:
                from ancestry.core import ml_origin as _ml
                cb = lambda m: self.after(0, lambda mm=m: self._ged_link_status.set(mm))
                if not _ml.load():
                    cb("ML: trainiere Modell auf GEDCOM …")
                    metrics = _ml.train(self._db, progress_cb=cb)
                    cb(f"ML: trainiert ({metrics['n_train']} Personen, "
                       f"{metrics['n_regions']} Regionen, "
                       f"{metrics['train_acc']:.0%})")
                n = _ml.apply_to_matches(self._db, test_guid, progress_cb=cb)
                self.after(0, lambda: self._ged_link_status.set(
                    f"ML-Herkunft fertig: {n} Matches gelabelt"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("ml-origin: %s", exc)
                msg = str(exc).split("\n")[0]
                self.after(0, lambda: self._ged_link_status.set(f"ML-Fehler: {msg}"))
                self.after(0, lambda exc=exc: messagebox.showwarning(self._t("dlg.ml_origin"), str(exc)))

        threading.Thread(target=_worker, daemon=True, name="ml-origin").start()

    def _run_wikitree_extend(self):
        """Verlängert die Ahnenlinie des gewählten Matches über die WikiTree-API."""
        match = getattr(self, "_selected_match", None)
        if not match:
            messagebox.showinfo(self._t("dlg.wikitree"), self._t("dlg.m_choose_match"))
            return
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("WikiTree-Abgleich läuft …")

        def _worker(mguid=match.match_guid, mname=match.display_name):
            try:
                from ancestry.core import bridge as _bridge
                results = _bridge.wikitree_extend_match(
                    self._db, test_guid, mguid,
                    progress_cb=lambda m: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)),
                )
                found = sum(1 for r in results if r.get("best"))
                self.after(0, lambda: self._ged_link_status.set(
                    f"WikiTree: {found} Linie(n) gefunden"))
                self.after(0, lambda: self._show_wikitree_results(mname, results))
            except Exception as exc:
                log.warning("wikitree-extend: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        threading.Thread(target=_worker, daemon=True, name="wikitree").start()

    def _show_wikitree_results(self, match_name: str, results: list):
        from ancestry.gui.analysis.gedcom_results import show_wikitree_results
        show_wikitree_results(self, match_name, results)

    def _run_origin_inference(self):
        """Leitet wahrscheinliche Herkunftsregionen aus Pedigree-Nachnamen × GEDCOM-Orten ab."""
        ged = getattr(self, "_gedcom", None)
        if not ged:
            messagebox.showinfo(self._t("dlg.gedcom"), self._t("md.ged_none"))
            return
        test_guid = self._state.current_test_guid or self._get_kit_guid()
        if not test_guid:
            return

        self._ged_link_status.set("Herkunfts-Analyse läuft …")

        def _worker():
            try:
                from ancestry.core import bridge as _bridge
                results = _bridge.infer_match_origins(
                    self._db, test_guid,
                    progress_cb=lambda m, **kw: self.after(
                        0, lambda mm=m: self._ged_link_status.set(mm)),
                )
                n = len(results)
                self.after(0, lambda: self._ged_link_status.set(
                    f"Herkunfts-Analyse fertig: {n} Matches zugeordnet"))
                self.after(0, self._refresh_match_table)
            except Exception as exc:
                log.warning("origin-inference: %s", exc)
                self.after(0, lambda exc=exc: self._ged_link_status.set(f"Fehler: {exc}"))

        threading.Thread(target=_worker, daemon=True, name="origin-infer").start()

    def _run_gedmatch_bridge(self):
        """Verknüpft GEDmatch-Matches mit Ancestry/MH-Matches (Name+cM-Ähnlichkeit)."""
        def _do():
            try:
                n = self._db.link_gedmatch_bridges()
                msg = (f"{n} GEDmatch-Match/es mit Ancestry/MH-Matches verknüpft.\n"
                       "⚡-Badge erscheint in der Match-Liste wenn Brücke bekannt.")
                self.after(0, lambda m=msg: messagebox.showinfo(self._t("dlg.gedmatch_bridge"), m))
                self.after(50, self._refresh_match_table)
            except Exception as e:
                self.after(0, lambda e=e: messagebox.showerror(self._t("dlg.error"), str(e)))
        threading.Thread(target=_do, daemon=True).start()
