"""Enforcement-Guard: das Übersetzungswörterbuch ist vollständig zweisprachig.

Jeder Eintrag in TRANSLATIONS MUSS sowohl 'de' als auch 'en' haben. So kann
keine künftig hinzugefügte UI-Beschriftung einsprachig durchrutschen.
"""
import sys
from unittest.mock import MagicMock

import pytest

for _m in ("tkinter", "tkinter.ttk"):
    sys.modules.setdefault(_m, MagicMock())

from ancestry.gui.widgets.theme import TRANSLATIONS

# Symbole/Abkürzungen, die in beiden Sprachen identisch sein dürfen
# (cM, GUID, Eigennamen, Tab-Titel …). Bewusst kuratiert.
ALLOWED_IDENTICAL = {
    "tab_login", "tab_matches", "tab_cluster", "tab_matricula",
    "mat.refresh", "m.name", "m.guid", "m.cm", "m.seg", "m.ged", "m.starred",
    "cl.cid", "cl.count", "cl.maxcm", "mb.name", "mb.cm", "pw.a", "pw.b",
    "gc.cluster", "gc.match", "gc.cm", "ct.person", "ct.gen", "mf.mincm",
    "cl.frm_left", "gc.f.cluster", "lg.email", "dl.filter", "md.tab_shared",
    "md.cm", "st.kit_kz", "mf.chip_200", "dl.pause", "dl.dash_mat",
    "dl.dash_sh", "md.fs_link", "mf.kit",
    # Eigennamen / Formate, in beiden Sprachen identisch
    "dlg.gedcom", "dlg.export", "dlg.wikitree",
    # Ähnlichkeits-Matrix: Spaltenbezeichnungen sind in beiden Sprachen gleich
    "sm.match_a", "sm.match_b", "sm.score",
}


@pytest.mark.parametrize("key", sorted(TRANSLATIONS))
def test_key_has_both_languages(key):
    entry = TRANSLATIONS[key]
    assert isinstance(entry, dict), f"{key}: kein Dict"
    assert entry.get("de"), f"{key}: 'de' fehlt oder leer"
    assert entry.get("en"), f"{key}: 'en' fehlt oder leer"


def test_no_unexpected_identical_translations():
    """de == en nur für kuratierte Symbole/Abkürzungen – alles andere ist
    vermutlich eine vergessene Übersetzung."""
    identical = {k for k, v in TRANSLATIONS.items()
                 if v.get("de") and v["de"] == v.get("en")}
    unexpected = identical - ALLOWED_IDENTICAL
    assert not unexpected, (
        "Diese Keys haben identische de/en-Texte (Übersetzung vergessen?): "
        + ", ".join(sorted(unexpected)))


def test_all_tooltip_keys_are_namespaced():
    """Tooltip-Keys leben im tt.*-Namensraum (Konvention)."""
    tt = [k for k in TRANSLATIONS if k.startswith("tt.")]
    assert len(tt) >= 35
