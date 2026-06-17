# Development Guide – GEDCOM Analyzer

## Projektüberblick

- **Technologie**: Python 3.10+, Tkinter GUI, SQLite, Playwright, Anthropic Claude API
- **Struktur**: Genealogie-Suite mit DNA-Matching, GEDCOM-Import, Kirchenbuch-Integration
- **Tests**: 3958 Tests, >95% Core-Code-Abdeckung
- **CI/CD**: GitHub Actions (Lint + Multi-Python-Test)

## Setup für Entwicklung

```bash
# 1. Clone & Install
git clone https://github.com/ShanLanar/gedcom-analyzer.git
cd gedcom-analyzer

# 2. Virtual Environment (empfohlen)
python -m venv venv
source venv/bin/activate  # oder: venv\Scripts\activate (Windows)

# 3. Install mit allen Dev-Tools
pip install -e ".[all]"

# 4. Pre-Commit Hooks installieren
pip install pre-commit
pre-commit install
```

## Entwicklungs-Workflows

### Linting & Code-Quality

```bash
# Ruff Lint (mit Auto-Fix)
ruff check . --fix

# Format (isort + ruff format)
ruff format .

# Alles zusammen
ruff check . --fix && ruff format .
```

### Tests ausführen

```bash
# Alle Tests
python -m pytest tests/ -q

# Nur Unit-Tests (schnell)
python -m pytest tests/ -q -m "not gui"

# Mit Coverage
python -m pytest --cov=ancestry tests/

# Spezifischer Test
python -m pytest tests/test_gedcom.py::test_import_ged -v
```

### Startup-Profiling (GUI-Optimierung)

```bash
# Misst Startup-Zeit und zeigt Bottlenecks
python profile_startup.py
```

## Architektur

### Core (`ancestry/core/`)

- **db/** – SQLite-Schemas, Migrationen, Repos (CQRS-Pattern)
- **bridge/** – GEDCOM-Import, DNA-Matching-Logik, Scoring
- **api/** – Ancestry/MyHeritage/GEDmatch API-Clients
- **cluster.py** – Leeds-Clustering-Algorithmus
- **population_stats.py** – Genealogische Analysen

### GUI (`ancestry/gui/`)

- **app.py** – Hauptfenster (2300 Zeilen — wird schrittweise aufgeteilt)
- **tabs/** – 8 Tab-Widgets (Download, Matches, Cluster, Stats, etc.)
- **analysis/** – Dialog-Module (Pedigree, MRCA, Cluster-Visualisierung)
- **widgets/** – UI-Komponenten, Theme, Lokalisierung

### Tools (`ancestry/tools/`, `tasks/`)

- Eigenständige CLI/GUI-Tools (Importer, Crawler, Analyzers)
- ~100 Analyse-Module für Genealogie-Erkenntnisse

## Performance

### Startup-Optimierungen

1. **Lazy-Tab-Loading** – Heavy Tabs (Stats, Matricula, Persons, Tools) werden asynchron nach GUI-Rendering geladen
2. **Lazy Imports** – Tab-Klassen werden erst beim Bedarf importiert
3. **DB Connection Pooling** – SQLite-Connection wird wiederverwendet

### Messungen

- **Vorher**: ~3–5s (alle Tabs beim Start)
- **Nachher**: ~1–2s (nur essenzielle Tabs beim Start)

## Contribution Workflow

1. **Branch**: Auf `main` entwickeln (keine Feature-Branches)
2. **Commit**: Aussagekräftige Messages auf Deutsch
   ```
   git commit -m "Feature XY: Kurzbeschreibung
   
   - Punkt 1
   - Punkt 2
   "
   ```
3. **Push**: `git push origin main`
4. **CI**: Automatische Lint + Test (GitHub Actions)

## Best Practices

### Code-Qualität

- ✅ Ruff Lint muss bestehen (`ruff check .`)
- ✅ Tests müssen bestehen (`pytest -q`)
- ✅ Type-Hints für neue Code-Teile (schrittweise Verbesserung)
- ❌ Keine Legacy-Hacks (wenn möglich)

### GUI-Entwicklung

- **Tabs sind TTK-Frames** mit standardisiertem Konstruktor:
  ```python
  class MyTab(ttk.Frame):
      def __init__(self, notebook, state, callbacks, ...):
          super().__init__(notebook)
  ```
- **State-Sharing** via `AppState` (ancestry/gui/state.py)
- **Lokalisierung** via `translate(key)` in `widgets/theme.py`

### Core-Entwicklung

- **Repository Pattern** für DB-Zugriff
- **Service Layer** für Geschäftslogik (nicht direkt DB-Query)
- **Migrations** für Schema-Änderungen (SQLite)

## Ressourcen

- **CLAUDE.md** – Repo-Richtlinien (zwingend)
- **pyproject.toml** – Abhängigkeiten, Ruff-Config, Pytest
- **tests/** – 4000+ Tests als Dokumentation und Safeguard
- **.github/workflows/ci.yml** – GitHub Actions CI

## FAQ

**Q: Warum keine Feature-Branches?**  
A: Repo-Richtlinie für Einfachheit und Vermeidung von Branch-Wildwuchs.

**Q: Wie teste ich GUI-Features?**  
A: Unit-Tests für Logik + manuelle Integration (Tkinter braucht Display).

**Q: Wie schnell sollte der Startup sein?**  
A: Ziel <2s (Full-DB-Load + GUI-Render). Profiling: `python profile_startup.py`

**Q: Können wir zu Ruff-Format wechseln?**  
A: Schrittweise möglich (aktuell nur Linting, nicht Formatting). Siehe CLAUDE.md.
