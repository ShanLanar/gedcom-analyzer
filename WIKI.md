# 📖 Genealogie-Suite — Anleitung & Wiki

Diese Suite vereint **DNA-Match-Analyse** (Ancestry, MyHeritage, GEDmatch),
**Stammbaum-Auswertung** (GEDCOM, WikiTree, Webtrees) und **Kirchenbuch-Erschließung**
(Matricula) in **einem Fenster** mit Reitern.

> **Schnellstart:** `update-and-run.bat` ausführen → die App aktualisiert sich,
> installiert Abhängigkeiten und startet direkt. Alle Daten liegen lokal in
> `ancestry/ancestry_dna.db` (wird **nie** ins Internet geladen).

---

## Inhalt
1. [Die Reiter im Überblick](#1-die-reiter-im-überblick)
2. [Empfohlener Arbeitsablauf](#2-empfohlener-arbeitsablauf)
3. [Datenquellen — woher bekomme ich was?](#3-datenquellen--woher-bekomme-ich-was)
4. [Der Werkzeuge-Tab Schritt für Schritt](#4-der-werkzeuge-tab-schritt-für-schritt)
5. [Wo liegen meine Daten?](#5-wo-liegen-meine-daten)
6. [Problemlösung](#6-problemlösung)

---

## 1. Die Reiter im Überblick

| Reiter | Wozu |
|---|---|
| 🏠 **Start** | GEDCOM-Datei + Wurzelperson und optionale CSV-Pfade festlegen. |
| 🔑 **Login** | Bei Ancestry anmelden (Cookie-Datei empfohlen) oder Kit-GUID manuell setzen. |
| ⬇ **Herunterladen** | DNA-Matches und deren Ahnentafeln von Ancestry laden. |
| 🧬 **Matches** | Matches durchsuchen, filtern, mit dem GEDCOM abgleichen, Herkunft/Endogamie. |
| 🌳 **Cluster** | Automatische Cluster (Leeds-Methode), Seiten (väterlich/mütterlich) zuweisen. |
| 📊 **Statistiken** | Kennzahlen, Verwandtschaftsverteilung, Fortschritt. |
| ⛪ **Matricula** | Kirchenbuch-Seiten pro Pfarrei scannen (läuft als Hintergrund-Prozess). |
| 👪 **Personen** | Durchsuchbarer Personen-Browser mit navigierbarem Stammbaum + DNA-Treffern. |
| 🔧 **Werkzeuge** | Externe Sammel-/Import-Tools (Webtrees, MyHeritage, GEDmatch, WikiTree, GED Slim). |

---

## 2. Empfohlener Arbeitsablauf

```
①  Start-Tab:    GEDCOM-Datei + Wurzelperson wählen
        │
②  Login-Tab:    Ancestry-Cookie-Datei laden  (oder Kit-GUID setzen)
        │
③  Herunterladen: „Matches herunterladen"  →  danach „Ahnentafeln laden"
        │
④  Matches-Tab:  „🌳 GEDCOM abgleichen"  →  gemeinsame Vorfahren finden
        │            „🗺 Herkunft ableiten" / „🧬 Endogamie übertragen"
        │
⑤  Cluster-Tab:  „Cluster bilden"  →  „Cluster-Seite zuweisen"
        │
⑥  Werkzeuge:    weitere Quellen ergänzen (Webtrees-Crawl, MyHeritage, WikiTree …)
```

Die Schritte ①–③ sind die Grundlage. ④–⑥ kannst du beliebig oft wiederholen,
wenn neue Daten dazukommen.

---

## 3. Datenquellen — woher bekomme ich was?

| Quelle | Was | So bekommst du es |
|---|---|---|
| **Ancestry** | DNA-Matches + Ahnentafeln | Im **Login-Tab** mit Cookie-Datei anmelden, dann im **Herunterladen-Tab** laden. |
| **GEDCOM** | Dein eigener Stammbaum | Aus deinem Genealogie-Programm exportieren, im **Start-Tab** wählen. |
| **MyHeritage** | DNA-Matches | „Genealogy Assistant"-Browser-Export → CSV, dann **Werkzeuge → MyHeritage**. |
| **GEDmatch** | Cross-Plattform-Matches | One-to-many als TSV speichern, dann **Werkzeuge → GEDmatch-TSV → DB**. |
| **WikiTree** | Stammbaum-Personen | WikiTree-ID (z. B. `Kovermann-123`), dann **Werkzeuge → WikiTree → DB**. |
| **Webtrees** (anverwandte.info) | Öffentlicher Stammbaum | **Werkzeuge → Webtrees** crawlen, dann „Crawl → Datenbank importieren". |
| **Matricula** | Kirchenbuch-Scans | **Matricula-Tab** oder **Werkzeuge → Matricula**. |

### Cookie-Datei für Ancestry (empfohlene Login-Methode)
1. Browser-Erweiterung **„Cookie-Editor"** (Chrome/Firefox) installieren.
2. Auf **ancestry.com** einloggen.
3. Cookie-Editor → **Export → JSON** → Datei speichern.
4. Im **Login-Tab** unter „Cookie-Datei" diese Datei wählen → „Mit Cookies einloggen".

---

## 4. Der Werkzeuge-Tab Schritt für Schritt

Alle Werkzeuge laufen **im Hintergrund** (eigener Prozess), sind **fortsetzbar**
und jederzeit per **■** stoppbar. Der Live-Log rechts zeigt den Fortschritt.

### ⬇ Webtrees-Stammbaum (anverwandte.info)
1. **Profil** eingeben (Standard `anverwandte`).
2. **„Öffentlichen Baum crawlen"** — mit `--discover` wird der ganze erreichbare
   Baum erschlossen (sonst nur die Startpersonen).
3. **„Crawl → Datenbank importieren"** — übernimmt die gecrawlten Personen in die
   Hauptdatenbank (Quelle `anverwandte`).
4. Optional **„💾 Als GEDCOM-Datei exportieren"**.

### ⛪ Matricula-Kirchenbücher
1. **„0 · Pfarrei-Katalog"** (einmalig) — lädt die Liste der Pfarreien.
2. **„1 · Bücherverzeichnis holen"** — die Bücher der (optional) gewählten Pfarrei.
3. **„2 · Seiten scannen"** — transkribiert Seiten (Claude Vision).

> **Voraussetzungen für das Seiten-Scannen:**
> - **Playwright-Browser** einmalig installieren:
>   `pip install playwright` und dann `playwright install chromium`.
> - **`ANTHROPIC_API_KEY`** als Umgebungsvariable setzen — sonst läuft der Scan
>   nur als Bilder-Download **ohne** Transkription (Hinweis „ANTHROPIC_API_KEY
>   nicht gesetzt — Scan ohne Transkription").

### 🧬 MyHeritage-DNA
1. **„1 · Matchliste herunterladen"** *(Login im Browser nötig)*.
2. Match-CSV wählen → **„2 · Gemeinsame Matches laden"**.
   > Hast du die Daten schon, überspringe Schritt 1.

### 📥 Weitere Importe
- **MyHeritage-CSV → DB**, **GEDmatch-TSV → DB**, **WikiTree → DB** — jeweils
  Datei/ID wählen und Knopf drücken.

### 🧰 Extras
- **GED Slim** — große GEDCOM-Dateien verkleinern (eigenes Fenster).
- **Matricula-Web-Viewer** (Port 5000) und **Entity-Browser** (Port 5001).

---

## 5. Wo liegen meine Daten?

| Datei / Ordner | Inhalt |
|---|---|
| `ancestry/ancestry_dna.db` | **Alle** Matches, GEDCOM-Personen, Cluster, Links — die Hauptdatenbank. |
| `ancestry/tools/webtrees_crawl.db` | Roh-Crawl von anverwandte.info. |
| `ancestry/data/` | Zwischenstände, Snapshots. |
| `output/` | Excel-/HTML-Exporte. |

> ⚠️ Diese Dateien sind **gitignored** und werden von Updates (`git reset --hard`)
> **nicht** angetastet. Deine heruntergeladenen Daten bleiben bei jedem Update erhalten.
> Für ein echtes Backup die `*.db`-Dateien kopieren.

---

## 6. Problemlösung

| Symptom | Ursache / Lösung |
|---|---|
| `No module named 'core'` | Veraltete Version — `update-and-run.bat` neu laufen lassen (zieht den Fix). |
| `UnicodeEncodeError … charmap` | Windows-Konsole ohne UTF-8 — behoben; per `update-and-run.bat` starten (setzt `PYTHONUTF8=1`). |
| `unrecognized arguments: --discover` | Veralteter Crawler — Update ziehen. |
| Reiter fehlen / „Init fehlgeschlagen" | Update ziehen; der Startfehler ist behoben. |
| Tool „lädt nicht" trotz grünem Log | Viele Tools brauchen vorher einen **Login im Browser** (Ancestry/MyHeritage) bzw. eine zuvor gewählte **CSV/Datei**. |
| `Failed to launch chromium … executable doesn't exist` | Playwright-Browser fehlt: `pip install playwright` + `playwright install chromium`. |
| `ANTHROPIC_API_KEY nicht gesetzt` | Für die Kirchenbuch-Transkription den API-Key als Umgebungsvariable setzen. |
| Ein Reiter zeigt „konnte nicht geladen werden" | Sicherheitsnetz — die übrigen Reiter laufen normal; den Fehlertext im Reiter/Log melden. |
| Update überschreibt meinen Pfad | `update-and-run.bat` folgt jetzt automatisch ihrem eigenen Ordner — kein fester Pfad mehr. |

---

*Bei einem Startfehler hilft fast immer: `update-and-run.bat` erneut ausführen
(holt die neueste Version) — und beim Hängenbleiben den genauen Fehlertext notieren.*
