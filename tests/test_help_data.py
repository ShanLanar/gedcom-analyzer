"""Tests für das In-App-Hilfemodul: Konsistenz mit Task-Registry."""
import pytest


def test_help_entries_loadable():
    from tasks.help_data import HELP_ENTRIES, CLI_HELP, CONCEPTS
    assert isinstance(HELP_ENTRIES, dict)
    assert isinstance(CLI_HELP, dict)
    assert isinstance(CONCEPTS, dict)
    assert len(HELP_ENTRIES) >= 30
    assert len(CLI_HELP) >= 4
    assert len(CONCEPTS) >= 3


def test_help_entries_cover_all_tasks():
    """Jeder Task in der Registry MUSS einen Hilfe-Eintrag haben."""
    import sys, types
    for n in ['tkinter', 'tkinter.ttk', 'tkinter.filedialog',
              'tkinter.scrolledtext']:
        sys.modules.setdefault(n, types.ModuleType(n))
    sys.modules['tkinter'].Tk = type
    sys.modules['tkinter'].BooleanVar = lambda **kw: None
    sys.modules['tkinter'].StringVar = lambda **kw: None
    sys.modules['tkinter'].Toplevel = type
    sys.modules['tkinter'].Listbox = type
    sys.modules['tkinter'].Frame = type
    sys.modules['tkinter'].Label = type
    sys.modules['tkinter'].Entry = type
    sys.modules['tkinter'].Button = type
    sys.modules['tkinter'].Canvas = type
    sys.modules['tkinter'].Checkbutton = type
    sys.modules['tkinter.ttk'].Combobox = type
    sys.modules['tkinter.ttk'].Scrollbar = type
    sys.modules['tkinter.ttk'].Progressbar = type
    sys.modules['tkinter.scrolledtext'].ScrolledText = type

    import main
    from tasks.help_data import HELP_ENTRIES
    task_ids = {t["id"] for t in main.TASKS}
    help_ids = set(HELP_ENTRIES.keys())
    missing = task_ids - help_ids
    extras  = help_ids - task_ids
    assert not missing, f"Tasks ohne Hilfe-Eintrag: {missing}"
    assert not extras,  f"Hilfe-Einträge ohne Task:   {extras}"


@pytest.mark.parametrize("required_field", ["title", "group", "purpose"])
def test_help_entries_have_required_fields(required_field):
    from tasks.help_data import HELP_ENTRIES
    for key, entry in HELP_ENTRIES.items():
        assert required_field in entry, \
            f"Task '{key}' fehlt das Feld '{required_field}'"
        assert entry[required_field], \
            f"Task '{key}': Feld '{required_field}' ist leer"


@pytest.mark.parametrize("required_field", ["title", "syntax", "purpose"])
def test_cli_entries_have_required_fields(required_field):
    from tasks.help_data import CLI_HELP
    for key, entry in CLI_HELP.items():
        assert required_field in entry, \
            f"CLI-Befehl '{key}' fehlt das Feld '{required_field}'"


@pytest.mark.parametrize("required_field", ["definition", "formula", "examples"])
def test_concept_entries_have_required_fields(required_field):
    from tasks.help_data import CONCEPTS
    for key, entry in CONCEPTS.items():
        assert required_field in entry, \
            f"Konzept '{key}' fehlt das Feld '{required_field}'"


def test_help_groups_are_valid():
    """Gruppe muss eine der bekannten Kategorien sein."""
    from tasks.help_data import HELP_ENTRIES
    valid_groups = {"Vorbereitung", "Analysen", "Extras", "Export"}
    for key, entry in HELP_ENTRIES.items():
        assert entry["group"] in valid_groups, \
            f"Task '{key}': unbekannte Gruppe '{entry['group']}'"


def test_help_purpose_length_reasonable():
    """Zweck-Text sollte mindestens 20 Zeichen lang sein."""
    from tasks.help_data import HELP_ENTRIES
    for key, entry in HELP_ENTRIES.items():
        assert len(entry["purpose"]) >= 20, \
            f"Task '{key}': Zweck zu kurz ({len(entry['purpose'])} Zeichen)"


def test_concepts_include_kinship_and_inbreeding():
    """Die zentralen mathematischen Konzepte müssen dokumentiert sein."""
    from tasks.help_data import CONCEPTS
    keys_lower = " ".join(CONCEPTS.keys()).lower()
    assert "kinship" in keys_lower or "Φ" in str(CONCEPTS.keys())
    assert "inzucht" in keys_lower or "wright" in keys_lower
    assert "sosa" in keys_lower
