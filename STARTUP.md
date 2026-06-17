# Ancestry Analyzer – Startup Guide

## 🚀 Quick Start

### Windows
```cmd
cd C:\Test\gedcom-analyzer
run_gui.bat
```

### Linux / macOS
```bash
cd ~/gedcom-analyzer
./run_gui.sh
# oder
python3 run_gui.py
```

---

## 📋 Installation (Einmalig)

### 1. Repository clonen
```bash
git clone https://github.com/ShanLanar/gedcom-analyzer.git
cd gedcom-analyzer
```

### 2. Python Dependencies installieren
```bash
# Windows
pip install -e .

# Linux/macOS
pip3 install -e .
```

### 3. (Optional) Alle Features
```bash
# Mit allen Optional-Features (Viewer, Scraping, AI)
pip install -e ".[all]"
```

---

## 🎯 Startup Methods

Wähle **eine** dieser Methoden:

### Methode 1: Launcher-Skript (Empfohlen)
```cmd
# Windows
run_gui.bat

# Linux/macOS
./run_gui.sh
```

### Methode 2: Python Script
```bash
python run_gui.py
```

### Methode 3: Python Module (Advanced)
```bash
python -m ancestry.gui
```

---

## ⚡ Performance

Nach unseren Optimierungen sollte die App:
- **GUI laden:** <1 Sekunde
- **Match-Tabelle:** Asynchron im Hintergrund
- **Responsive:** Sofort nutzbar

---

## 🐛 Troubleshooting

### Problem: `ModuleNotFoundError: No module named 'tkinter'`
**Lösung:** tkinter ist nicht installiert
```bash
# Windows: Normalerweise im Python-Installer enthalten
# Linux: sudo apt-get install python3-tk
# macOS: Teil von Python.org Installation
```

### Problem: `No module named 'ancestry'`
**Lösung:** Installation fehlgeschlagen
```bash
pip install -e .
```

### Problem: Git Ref Lock Error
**Lösung:** Siehe GIT_REPAIR_GUIDE.md
```bash
# Schnelle Reparatur:
git fetch --force origin main
git reset --hard origin/main
```

### Problem: Sehr langsamer Startup
**Diagnose:**
```bash
python measure_startup.py
```

Sollte <1 Sekunde für Core sein. Wenn länger:
- [ ] Check: `python -c "import ancestry"`
- [ ] Check: `python measure_startup.py`
- [ ] Prüfe: Antivirus blockiert Python?

---

## 📊 Performance-Metriken (nach Optimierung)

```
Core Startup:       211ms  ✓
GUI Rendering:      500-800ms  ✓
Match-Table (async): Im Hintergrund  ✓
─────────────────
TOTAL:             ~1-2 Sekunden  ✓
```

---

## 🛠️ Development Setup

### Mit Pre-Commit Hooks
```bash
pip install pre-commit
pre-commit install

# Tests ausführen
pytest tests/ -q
```

### Performance Testing
```bash
# Quick diagnostics
python measure_startup.py

# Database analysis
python audit_performance.py

# Full benchmark
pytest tests/test_performance.py -v --benchmark-only
```

---

## 📚 Weitere Ressourcen

- **DEVELOPMENT.md** — Development Guide
- **OPTIMIZATIONS.md** — Performance Details
- **GIT_REPAIR_GUIDE.md** — Git Problem Solving
- **CLAUDE.md** — Project Guidelines

---

## ✅ Success Criteria

App ist erfolgreich gestartet wenn:
- [ ] GUI-Fenster öffnet sich
- [ ] Keine Fehler in der Konsole
- [ ] Tabs sind sichtbar (Download, Matches, Cluster, Stats)
- [ ] Match-Tabelle lädt im Hintergrund

---

**Status: Ready to Use!** 🎉

Bei Problemen: Siehe Troubleshooting oben oder check DEVELOPMENT.md
