"""Tooltips müssen zweisprachig (de/en) sein und beim Sprachwechsel mitschalten."""
import sys
import types
from unittest.mock import MagicMock

import pytest

# tkinter (mit echten Basisklassen) faken, damit tooltip/theme importierbar sind
_TK = MagicMock()
for _m in ("tkinter", "tkinter.ttk"):
    sys.modules.setdefault(_m, _TK)

from ancestry.gui.widgets.theme import TRANSLATIONS, translate

# alle Tooltip-Keys (Namensraum tt.*)
TT_KEYS = [k for k in TRANSLATIONS if k.startswith("tt.")]


def test_there_are_tooltip_keys():
    assert len(TT_KEYS) >= 25


@pytest.mark.parametrize("key", TT_KEYS)
def test_tooltip_key_has_both_languages(key):
    entry = TRANSLATIONS[key]
    assert entry.get("de"), f"{key}: de fehlt"
    assert entry.get("en"), f"{key}: en fehlt"
    # de und en sollten sich unterscheiden (echte Übersetzung, kein Copy-Paste)
    assert entry["de"] != entry["en"], f"{key}: de == en"


@pytest.mark.parametrize("key", TT_KEYS)
def test_translate_returns_language(key):
    assert translate(key, "de") == TRANSLATIONS[key]["de"]
    assert translate(key, "en") == TRANSLATIONS[key]["en"]


def test_register_tooltip_switches_language():
    """register_tooltip registriert in state.lang_tooltips; das Nachziehen der
    Sprache (wie _apply_lang) ändert den Tooltip-Text."""
    real_tk = types.ModuleType("tkinter")
    real_tk.Toplevel = type("Toplevel", (), {})
    real_tk.Label = type("Label", (), {})
    saved = sys.modules.get("tkinter")
    sys.modules["tkinter"] = real_tk
    try:
        # tooltip-Modul frisch laden, damit es das (harmlose) tkinter sieht
        sys.modules.pop("ancestry.gui.widgets.tooltip", None)
        from ancestry.gui.widgets.tooltip import register_tooltip

        class _Widget:
            def bind(self, *a, **k):
                pass

        class _State:
            lang = "de"
            lang_tooltips = []

        st = _State()
        tip = register_tooltip(_Widget(), "tt.cl_mrca", st)
        assert tip.text == TRANSLATIONS["tt.cl_mrca"]["de"]
        assert st.lang_tooltips == [(tip, "tt.cl_mrca")]

        # Sprachwechsel nachbilden (wie in app._apply_lang)
        for t, key in st.lang_tooltips:
            t.text = translate(key, "en")
        assert tip.text == TRANSLATIONS["tt.cl_mrca"]["en"]
    finally:
        if saved is not None:
            sys.modules["tkinter"] = saved
        sys.modules.pop("ancestry.gui.widgets.tooltip", None)
