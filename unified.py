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
"""
import os
import sys
import importlib
import pkgutil
import tkinter as tk
from tkinter import ttk

ROOT = os.path.dirname(os.path.abspath(__file__))
ANC  = os.path.join(ROOT, "ancestry")


def _eager_import_analyzer():
    """Analyzer-Seite vollständig laden, solange config==Root gilt."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import config as _root_config          # noqa: F401  (cached als 'config')
    from main import AhnenApp              # main.py importiert config=Root

    # Alle Module unter tasks/ und lib/ eager importieren, damit deren
    # `import config` jetzt (config=Root) gebunden wird – keine späten
    # Lazy-Importe nach dem Umschalten.
    for pkg in ("tasks", "lib"):
        pkg_dir = os.path.join(ROOT, pkg)
        if not os.path.isdir(pkg_dir):
            continue
        for mod in pkgutil.walk_packages([pkg_dir], prefix=f"{pkg}."):
            try:
                importlib.import_module(mod.name)
            except Exception:
                pass  # optionale/kaputte Module ignorieren
    return AhnenApp


def _load_dna_app():
    """Auf Ancestry-config umschalten und die DNA-App laden."""
    sys.modules.pop("config", None)       # Root-config aus dem Cache nehmen
    if ANC not in sys.path:
        sys.path.insert(0, ANC)           # ancestry zuerst auf dem Pfad
    import config as _anc_config          # noqa: F401  (cached jetzt als ancestry)
    from gui.app import AncestryDnaApp
    return AncestryDnaApp


def main():
    AhnenApp        = _eager_import_analyzer()
    AncestryDnaApp  = _load_dna_app()

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

    # Beide Apps eingebettet aufbauen
    _ahnen = AhnenApp(master=tab_ged)
    dna    = AncestryDnaApp(master=tab_dna)

    def _on_close():
        try:
            dna.shutdown()        # Settings speichern + DB schließen
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
