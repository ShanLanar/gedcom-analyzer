"""Regressionstest: Kirchenbuch-Export (MatriculaTab._export_entries)
ignorierte den Pfarrei-Filter — parish_id steht in source_matrikula_books,
nicht direkt in source_matrikula_entries, daher griff die alte
`if "parish_id" in existing_cols` -Prüfung nie und es wurde immer die
GESAMTE Entries-Tabelle über alle Pfarreien exportiert.

tkinter ist in diesem Container nicht installiert (nicht nur kein
Display) — wie in test_gui_tabs_smoke.py wird ein leichtgewichtiges
Fake-tkinter in sys.modules injiziert, nur damit der Import von
ancestry.gui.tabs.matricula gelingt. _export_entries wird danach auf
einem schlanken Duck-Typing-Stub aufgerufen (statt einer echten
MatriculaTab-Instanz) — die Methode greift nur auf self._parish_var,
self._label_to_id und self._state.db zu.
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import types
from types import SimpleNamespace

import pytest

from ancestry.core.database import Database


# ── Fake-tkinter aufbauen und in sys.modules injizieren (wie test_gui_tabs_smoke.py) ──

class _FakeWidget:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
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


def _make_module(name, widget_names):
    mod = types.ModuleType(name)
    for wn in widget_names:
        setattr(mod, wn, type(wn, (_FakeWidget,), {}))
    for vn in ("StringVar", "BooleanVar", "IntVar", "DoubleVar", "Variable"):
        setattr(mod, vn, _FakeVar)
    mod.__getattr__ = (lambda attr: type(attr, (_FakeWidget,), {})
                       if attr[:1].isupper() else attr.lower())
    return mod


def _install_fake_tk():
    tk = _make_module("tkinter", ["Tk", "Toplevel", "Frame", "Canvas", "Label",
                                  "Button", "Entry", "Text", "Menu", "Listbox",
                                  "Scrollbar", "PhotoImage"])
    ttk = _make_module("tkinter.ttk", ["Frame", "Label", "Button", "Entry",
                                       "Combobox", "Treeview", "Notebook",
                                       "Style", "Scrollbar", "Progressbar",
                                       "LabelFrame", "Checkbutton", "Separator"])
    tk.ttk = ttk

    def _passive(name):
        m = types.ModuleType(name)
        m.__getattr__ = lambda attr: (lambda *a, **k: None)
        return m

    submods = {
        "scrolledtext": _passive("tkinter.scrolledtext"),
        "messagebox": _passive("tkinter.messagebox"),
        "filedialog": _passive("tkinter.filedialog"),
        "simpledialog": _passive("tkinter.simpledialog"),
        "font": _passive("tkinter.font"),
    }
    sys.modules["tkinter"] = tk
    sys.modules["tkinter.ttk"] = ttk
    for short, m in submods.items():
        sys.modules[f"tkinter.{short}"] = m
        setattr(tk, short, m)


@pytest.fixture(autouse=True)
def fake_tk():
    saved = {k: v for k, v in sys.modules.items()
             if k == "tkinter" or k.startswith("tkinter.")
             or k.startswith("ancestry.gui")}
    for k in list(saved):
        del sys.modules[k]
    _install_fake_tk()
    try:
        yield
    finally:
        for k in [k for k in list(sys.modules)
                  if k == "tkinter" or k.startswith("tkinter.")
                  or k.startswith("ancestry.gui")]:
            del sys.modules[k]
        sys.modules.update(saved)


def _matricula_tab_cls():
    from ancestry.gui.tabs.matricula import MatriculaTab
    return MatriculaTab


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    database = Database(path)
    yield database
    database.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


@pytest.fixture
def csv_out_path():
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def _seed(db):
    with db._cursor() as cur:
        cur.executemany(
            "INSERT INTO source_matrikula_books (book_id, parish_id, book_type) "
            "VALUES (?, ?, 'tauf')",
            [("book-A1", "parish-A"), ("book-A2", "parish-A"), ("book-B1", "parish-B")],
        )
        cur.executemany(
            "INSERT INTO source_matrikula_entries (book_id, entry_type, person_name) "
            "VALUES (?, 'tauf', ?)",
            [("book-A1", "Anna aus A1"), ("book-A2", "Bert aus A2"),
             ("book-B1", "Clara aus B1")],
        )


def _make_stub(db, parish_label="", label_to_id=None):
    """Duck-typing-Stub für self: _export_entries liest nur diese Attribute."""
    return SimpleNamespace(
        _parish_var=SimpleNamespace(get=lambda: parish_label),
        _label_to_id=label_to_id or {},
        _state=SimpleNamespace(db=db),
        _set_status=lambda *a, **k: None,
        _log_line=lambda *a, **k: None,
    )


def _read_csv_names(path):
    with open(path, encoding="utf-8") as f:
        return [row["person_name"] for row in csv.DictReader(f)]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_export_with_parish_selected_filters_to_that_parish(
        db, csv_out_path, monkeypatch):
    """Bug: mit ausgewählter Pfarrei 'A' landeten bisher auch Einträge aus
    Pfarrei B im Export."""
    _seed(db)
    MatriculaTab = _matricula_tab_cls()
    monkeypatch.setattr(
        "ancestry.gui.tabs.matricula.filedialog.asksaveasfilename",
        lambda **kw: csv_out_path)

    stub = _make_stub(db, parish_label="Pfarrei A",
                      label_to_id={"Pfarrei A": "parish-A", "Pfarrei B": "parish-B"})
    MatriculaTab._export_entries(stub)

    names = _read_csv_names(csv_out_path)
    assert set(names) == {"Anna aus A1", "Bert aus A2"}
    assert "Clara aus B1" not in names


def test_export_without_parish_selected_exports_all(db, csv_out_path, monkeypatch):
    """Ohne Pfarrei-Auswahl (z. B. 'Alle') bleibt der volle Export korrekt."""
    _seed(db)
    MatriculaTab = _matricula_tab_cls()
    monkeypatch.setattr(
        "ancestry.gui.tabs.matricula.filedialog.asksaveasfilename",
        lambda **kw: csv_out_path)

    stub = _make_stub(db, parish_label="", label_to_id={"Pfarrei A": "parish-A"})
    MatriculaTab._export_entries(stub)

    names = _read_csv_names(csv_out_path)
    assert set(names) == {"Anna aus A1", "Bert aus A2", "Clara aus B1"}
