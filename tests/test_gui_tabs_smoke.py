"""Headless Smoke-Tests für alle GUI-Tab-Builder (EPIC 5).

Tkinter ist in CI/Container oft nicht (mit Display) verfügbar. Statt eines
echten Tk-Roots wird hier ein leichtgewichtiges Fake-tkinter in sys.modules
injiziert: alle Widgets sind echte Klassen (damit `class XTab(ttk.Frame)`
subklassbar bleibt) mit permissiven No-Op-Methoden, Variablen mit get/set.

Damit lässt sich jeder Tab IMPORTIEREN und KONSTRUIEREN — das fängt die
häufigsten Bruchstellen ab: Importfehler, fehlende Namen, Tippfehler in
_build(), falsche Widget-Aufrufe. Echte Pixel werden nicht geprüft.

Die Tab-Konstruktor-Argumente werden per inspect.signature dynamisch mit
generischen Callbacks belegt, damit der Test nicht bei jeder Signaturänderung
bricht.
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
import tempfile
import types

import pytest

# ── Fake-tkinter aufbauen und in sys.modules injizieren ───────────────────────


class _FakeWidget:
    """Permissives Basis-Widget: jeder Methodenaufruf ist ein No-Op."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        # unbekannte Attribute → aufrufbarer No-Op, der ein Widget zurückgibt
        return lambda *a, **k: _FakeWidget()

    def __setitem__(self, key, value):
        pass

    def __getitem__(self, key):
        return ""

    def __iter__(self):
        return iter(())


class _FakeVar:
    def __init__(self, master=None, value=None, name=None):
        self._v = "" if value is None else value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v

    def trace_add(self, *a, **k):
        return "trace"

    def trace(self, *a, **k):
        return "trace"


_WIDGET_NAMES = [
    "Tk", "Toplevel", "Frame", "Widget", "Canvas", "Label", "Button", "Entry",
    "Text", "Menu", "Menubutton", "Listbox", "Scrollbar", "PanedWindow",
    "Spinbox", "Message", "PhotoImage", "Image",
]
_TTK_NAMES = [
    "Frame", "Label", "Button", "Entry", "Combobox", "Treeview", "Notebook",
    "Style", "Scrollbar", "Progressbar", "LabelFrame", "Checkbutton",
    "Radiobutton", "Separator", "Panedwindow", "Spinbox", "Sizegrip",
]


def _mod_getattr(attr):
    # Großgeschriebene Namen (PanedWindow, Sizegrip, …) → Widget-Klasse,
    # alles andere (END, LEFT, BOTH, …) → Name als String-Konstante.
    if attr[:1].isupper():
        return type(attr, (_FakeWidget,), {})
    return attr.lower()


def _make_module(name, widget_names):
    mod = types.ModuleType(name)
    for wn in widget_names:
        # jede Widget-Klasse ist eine echte Subklasse → subklassbar & konstruierbar
        setattr(mod, wn, type(wn, (_FakeWidget,), {}))
    # Variablen
    for vn in ("StringVar", "BooleanVar", "IntVar", "DoubleVar", "Variable"):
        setattr(mod, vn, _FakeVar)
    mod.__getattr__ = _mod_getattr  # type: ignore[attr-defined]
    return mod


def _install_fake_tk():
    tk = _make_module("tkinter", _WIDGET_NAMES)
    ttk = _make_module("tkinter.ttk", _TTK_NAMES)
    tk.ttk = ttk

    scrolled = types.ModuleType("tkinter.scrolledtext")
    scrolled.ScrolledText = type("ScrolledText", (_FakeWidget,), {})

    def _passive(name):
        m = types.ModuleType(name)
        m.__getattr__ = lambda attr: (lambda *a, **k: None)  # type: ignore[attr-defined]
        return m

    submods = {
        "scrolledtext": scrolled,
        "messagebox": _passive("tkinter.messagebox"),
        "filedialog": _passive("tkinter.filedialog"),
        "simpledialog": _passive("tkinter.simpledialog"),
        "font": _passive("tkinter.font"),
        "colorchooser": _passive("tkinter.colorchooser"),
    }
    sys.modules["tkinter"] = tk
    sys.modules["tkinter.ttk"] = ttk
    for short, m in submods.items():
        sys.modules[f"tkinter.{short}"] = m
        setattr(tk, short, m)  # auch als Attribut: tk.scrolledtext.ScrolledText


@pytest.fixture(autouse=True)
def fake_tk():
    """Installiert das Fake-tkinter NUR während dieses Tests und stellt danach
    den vorherigen sys.modules-Zustand wieder her (sonst Cross-Contamination
    mit anderen Tests, die tkinter mocken)."""
    def _snapshot():
        return {k: v for k, v in sys.modules.items()
                if k == "tkinter" or k.startswith("tkinter.")
                or k.startswith("ancestry.gui")}

    saved = _snapshot()
    # alles tkinter*/ancestry.gui* entfernen → sauberer Import unter Fake
    for k in list(saved):
        del sys.modules[k]
    _install_fake_tk()
    try:
        yield
    finally:
        # unter Fake importierte Module entfernen, Original-Snapshot zurück
        for k in [k for k in list(sys.modules)
                  if k == "tkinter" or k.startswith("tkinter.")
                  or k.startswith("ancestry.gui")]:
            del sys.modules[k]
        sys.modules.update(saved)


TAB_MODULES = [
    ("ancestry.gui.tabs.login", "LoginTab"),
    ("ancestry.gui.tabs.download", "DownloadTab"),
    ("ancestry.gui.tabs.matches", "MatchesTab"),
    ("ancestry.gui.tabs.cluster", "ClusterTab"),
    ("ancestry.gui.tabs.stats", "StatsTab"),
    ("ancestry.gui.tabs.matricula", "MatriculaTab"),
    ("ancestry.gui.tabs.persons", "PersonsTab"),
    ("ancestry.gui.tabs.tools", "ToolsTab"),
]


@pytest.fixture
def app_state(fake_tk):
    from ancestry.core.database import Database
    from ancestry.gui.state import AppState

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    db = Database(path)
    state = AppState(db=db)
    yield state
    db.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


def _build_kwargs(cls, parent, state):
    """Belegt die Tab-Konstruktorparameter generisch."""
    sig = inspect.signature(cls.__init__)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name in ("self", "parent", "state"):
            continue
        if param.default is not inspect.Parameter.empty:
            # optionale Parameter (cookie_var, guid_var, auto_login) auslassen,
            # aber auto_login sicher auf False ziehen (kein Login-Seiteneffekt)
            if name == "auto_login":
                kwargs[name] = False
            continue
        if name == "cm_ranges":
            kwargs[name] = []
        elif name.startswith("load_ui_settings"):
            kwargs[name] = lambda *a, **k: {}
        elif name.startswith("get_") or name.endswith("_gedcom"):
            kwargs[name] = lambda *a, **k: None
        else:
            kwargs[name] = lambda *a, **k: None
    return kwargs


@pytest.mark.parametrize("module_name,cls_name", TAB_MODULES)
def test_tab_imports(module_name, cls_name):
    mod = importlib.import_module(module_name)
    cls = getattr(mod, cls_name)
    assert isinstance(cls, type)


@pytest.mark.parametrize("module_name,cls_name", TAB_MODULES)
def test_tab_constructs(module_name, cls_name, app_state):
    from tkinter import ttk

    mod = importlib.import_module(module_name)
    cls = getattr(mod, cls_name)
    assert issubclass(cls, ttk.Frame), f"{cls_name} ist kein ttk.Frame"

    parent = ttk.Frame()
    kwargs = _build_kwargs(cls, parent, app_state)
    tab = cls(parent, app_state, **kwargs)  # darf nicht werfen
    assert tab is not None
