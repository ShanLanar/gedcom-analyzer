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

### Methode 2: Kanonischer Einstiegspunkt (empfohlen)
```bash
python -m ancestry.main
```
Dies ist der „echte" Entry-Point mit Logging-Setup und tkinter-Check.

### Methode 3: Weitere gültige Varianten
```bash
python run_gui.py            # delegiert an ancestry.main
python -m ancestry.gui       # delegiert an ancestry.main
python -m ancestry.gui.app   # delegiert an ancestry.main
```

> ⚠️ Hinweis: `python -m ancestry.gui.app` startete früher nichts, weil
> `app.py` keinen `__main__`-Block hatte. Das ist jetzt behoben.

---

## ⚡ Performance

Nach unseren Optimierungen sollte die App:
- **GUI laden:** <1 Sekunde
- **Match-Tabelle:** Asynchron im Hintergrund
- **Responsive:** Sofort nutzbar

---

## 🐛 Troubleshooting

### Problem: `Fatal Python error: ... No module named 'encodings'`
**Ursache:** Kaputte Python-Umgebung — `PYTHONHOME` zeigt auf eine andere
Installation (z. B. miniconda3) als die genutzte `python.exe` (z. B. Python310).

Erkennbar in der Fehlerausgabe:
```
sys.executable = ...Python310\python.exe   ← genutztes python
sys.prefix     = ...miniconda3             ← PYTHONHOME zeigt woanders hin
```

**Diagnose (Windows):**
```cmd
echo %PYTHONHOME%
echo %PYTHONPATH%
where python
```

**Lösung A — PYTHONHOME temporär leeren (in dieser Sitzung):**
```cmd
set PYTHONHOME=
set PYTHONPATH=
python -m ancestry.main
```

**Lösung B — PYTHONHOME dauerhaft entfernen:**
```cmd
setx PYTHONHOME ""
REM Danach CMD-Fenster NEU öffnen
```

**Lösung C — eine Installation konsequent nutzen** (z. B. conda direkt):
```cmd
C:\Users\<USER>\miniconda3\python.exe -m ancestry.main
```

> Tipp: `run_gui.bat` neutralisiert `PYTHONHOME`/`PYTHONPATH` automatisch
> für die Sitzung — am einfachsten also einfach `run_gui.bat` nutzen.

### Problem: `ModuleNotFoundError: No module named 'tkinter'`
**Lösung:** tkinter ist nicht installiert
```bash
# Windows: Normalerweise im Python-Installer enthalten
#          (bei conda: conda install tk)
# Linux: sudo apt-get install python3-tk
# macOS: Teil von Python.org Installation
```

### Problem: `No module named 'ancestry'`
**Lösung:** Installation fehlgeschlagen
```bash
pip install -e .
```

### Problem: Git Ref Lock Error
```
error: cannot lock ref 'refs/remotes/origin/main'
```
**Lösung:**
```bash
git fetch --force origin main
git reset --hard origin/main
```

### Problem: Sehr langsamer Startup
Die Match-Tabelle wird seit den Startup-Optimierungen asynchron im
Hintergrund geladen, damit das Fenster sofort reagiert. Wenn der Start
trotzdem lange dauert:
- [ ] Check: `python -c "import ancestry"` (sollte sofort zurückkehren)
- [ ] Prüfe, ob ein Antivirus Python/SQLite blockiert
- [ ] Sehr große Datenbank? Der erste Tabellenaufbau kann dauern.

---

## 🛠️ Development Setup

### Mit Pre-Commit Hooks
```bash
pip install pre-commit
pre-commit install

# Tests ausführen
pytest tests/ -q
```

Details zu Architektur und Workflows: siehe **DEVELOPMENT.md**.

---

## 📚 Weitere Ressourcen

- **DEVELOPMENT.md** — Development Guide
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
