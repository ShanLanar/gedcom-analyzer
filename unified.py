#!/usr/bin/env python3
"""
Vereinte Genealogie-Suite – EIN Fenster, zwei Reiter:

  🌳 Stammbaum-Auswertung   (der bisherige GEDCOM-Analyzer / main.py)
  🧬 DNA-Matches             (das bisherige Ancestry-DNA-Tool / ancestry)

Beide Programme bleiben weiterhin auch einzeln startbar (main.py bzw.
ancestry/main.py) – dieser Launcher bettet sie nur gemeinsam ein.

Technischer Knackpunkt: beide Codebasen haben ein eigenes Top-Level-Modul
namens `config` mit UNTERSCHIEDLICHEM Inhalt. tkinter erlaubt zudem nur EINEN
Tk-Root. Daher:
  1. Erst die GESAMTE Analyzer-Seite laden, solange `config` == Root-config
     (alle tasks.*/lib.*-Module eager importieren, damit ihr `import config`
     dauerhaft an die Root-config bindet).
  2. Dann `config` aus dem Cache nehmen, ancestry/ auf den Pfad legen und die
     DNA-App laden – deren `import config` trifft jetzt die Ancestry-config.
Bereits importierte Module behalten ihre jeweils richtige config-Referenz.

ACHTUNG: Alle Unter-Module MÜSSEN `import config` verwenden (nie
`from config import X`), damit die Modul-Identität nach dem Swap stimmt.
"""
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
ANC  = os.path.join(ROOT, "ancestry")


def _eager_import_analyzer():
    """Analyzer-Seite vollständig laden, solange config==Root gilt."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import config as _root_config          # noqa: F401  (cached als 'config')
    from main import AhnenApp              # main.py importiert config=Root

    # Alle Module unter tasks/ und lib/ eager importieren, damit deren
    # `import config` jetzt (config=Root) gebunden wird.
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
    """Auf Ancestry-config umschalten und die DNA-App laden."""
    sys.modules.pop("config", None)       # Root-config aus dem Cache nehmen
    if ANC not in sys.path:
        sys.path.insert(0, ANC)           # ancestry zuerst auf dem Pfad
    import config as _anc_config          # noqa: F401  (cached jetzt als ancestry)
    from gui.app import AncestryDnaApp
    return AncestryDnaApp


def _error_tab(parent: tk.Frame, title: str, exc: Exception) -> None:
    """Zeigt einen Fehler-Platzhalter statt einer nicht ladbaren App."""
    msg = f"⚠ {title}\n\n{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
    lbl = tk.Label(parent, text=msg, justify="left", fg="#cc0000",
                   font=("Consolas", 9), wraplength=900, anchor="nw")
    lbl.pack(fill="both", expand=True, padx=20, pady=20)


def main():
    try:
        AhnenApp = _eager_import_analyzer()
    except Exception as exc:
        log.exception("Analyzer-Import fehlgeschlagen")
        AhnenApp = None
        _ahnen_exc = exc
    else:
        _ahnen_exc = None

    try:
        AncestryDnaApp = _load_dna_app()
    except Exception as exc:
        log.exception("DNA-App-Import fehlgeschlagen")
        AncestryDnaApp = None
        _dna_exc = exc
    else:
        _dna_exc = None

    root = tk.Tk()
    root.title("Genealogie-Suite – Stammbaum & DNA")
    root.geometry("1300x840")
    root.minsize(1000, 680)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    tab_ged = ttk.Frame(nb)
    tab_dna = ttk.Frame(nb)
    nb.add(tab_ged, text="   🌳 Stammbaum-Auswertung   ")
    nb.add(tab_dna, text="   🧬 DNA-Matches   ")

    # GEDCOM-Analyzer einbetten
    dna_obj = None
    if AhnenApp is None:
        _error_tab(tab_ged, "GEDCOM-Analyzer konnte nicht geladen werden", _ahnen_exc)
    else:
        try:
            AhnenApp(master=tab_ged)
        except Exception as exc:
            log.exception("AhnenApp-Initialisierung fehlgeschlagen")
            _error_tab(tab_ged, "GEDCOM-Analyzer-Fehler beim Start", exc)

    # DNA-Tool einbetten
    if AncestryDnaApp is None:
        _error_tab(tab_dna, "DNA-Tool konnte nicht geladen werden", _dna_exc)
    else:
        try:
            dna_obj = AncestryDnaApp(master=tab_dna)
        except Exception as exc:
            log.exception("AncestryDnaApp-Initialisierung fehlgeschlagen")
            _error_tab(tab_dna, "DNA-Tool-Fehler beim Start", exc)
            dna_obj = None

    def _on_close():
        if dna_obj is not None:
            try:
                dna_obj.shutdown()
            except Exception:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("\nFehler – Eingabetaste zum Beenden ...")
