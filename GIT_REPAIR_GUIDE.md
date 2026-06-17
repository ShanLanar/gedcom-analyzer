# Git Ref Lock Problem – Reparaturanleitung

## Problem

```
error: cannot lock ref 'refs/remotes/origin/main':
is at 84d5b77... but expected 72859d0...
[FEHLER] git fetch fehlgeschlagen.
```

**Was ist das?**  
Git kann die lokale Remote-Referenz nicht aktualisieren, weil sie in einem inkonsistenten Zustand ist.

---

## ✅ Lösung (Einfach)

### Option A: Automatisches Reparatur-Skript (Empfohlen)

#### Windows:
```cmd
cd C:\Test\gedcom-analyzer
fix_git_refs.bat
```

#### Linux/macOS:
```bash
cd ~/gedcom-analyzer
python fix_git_refs.py
```

---

### Option B: Manuell (wenn Skript nicht funktioniert)

**Windows (PowerShell oder CMD):**
```cmd
cd C:\Test\gedcom-analyzer

REM 1. Git aufräumen
git gc --aggressive
git prune

REM 2. Force Fetch
git fetch --force origin main

REM 3. Lokale Ref zurücksetzen
git reset --hard origin/main

REM 4. Status prüfen
git status
```

**Linux/macOS:**
```bash
cd ~/gedcom-analyzer

# 1. Git aufräumen
git gc --aggressive
git prune

# 2. Force Fetch
git fetch --force origin main

# 3. Lokale Ref zurücksetzen
git reset --hard origin/main

# 4. Status prüfen
git status
```

---

### Option C: Wenn alles andere fehlschlägt

**Kompletter Reset (warnt: lokale Änderungen gehen verloren!):**

```cmd
REM Windows
cd C:\Test\gedcom-analyzer
rmdir /s /q .git
git clone https://github.com/ShanLanar/gedcom-analyzer.git .
```

```bash
# Linux/macOS
cd ~/gedcom-analyzer
rm -rf .git
git clone https://github.com/ShanLanar/gedcom-analyzer.git .
```

---

## 🔍 Was ist schiefgelaufen?

Der Fehler ist typischerweise:

1. **Netzwerk-Unterbrechung** während des Fetch
2. **Git-Prozess** wurde unterbrochen oder war noch aktiv
3. **Mehrere Git-Operationen** gleichzeitig
4. **Ref-Lock-Dateien** nicht gelöscht (`refs/remotes/origin/main.lock`)

---

## ✅ Danach

Nach der Reparatur:

```cmd
REM 1. Aktuellen Stand abrufen
git pull origin main

REM 2. Installation prüfen
pip install -e .

REM 3. Tests laufen
pytest tests/ -q --tb=no
```

---

## 📞 Wenn immer noch Probleme

1. Prüfe deine **Netzwerk-Verbindung** (VPN, Firewall)
2. Prüfe dein **Git-Konfiguration**:
   ```bash
   git config --list
   ```
3. Prüfe ob **git.exe läuft** (Windows Task Manager)
4. Prüfe ob die **`.git` Dateien locked** sind (Windows Antivirus?)

---

## 📚 Weitere Hilfe

- GitHub Help: https://docs.github.com/en/get-started/using-git
- Git Reference: https://git-scm.com/docs/git-fetch
- Unser CLAUDE.md: Branch-Richtlinien und Setup

---

**Status:** Nach Reparatur sollte `git status` grün sein ✅
