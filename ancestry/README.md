# Ancestry DNA Tool

Lädt DNA-Matches von Ancestry herunter, speichert sie in einer lokalen
SQLite-Datenbank und stellt sie in einer übersichtlichen Tkinter-GUI dar.

## Voraussetzungen

- Python 3.11+
- `pip install -r requirements.txt`

## Starten

```bash
python main.py          # GUI
python main.py --help   # CLI-Optionen
```

## Login-Methoden

### Methode 1 – Automatisch (kann durch CAPTCHA/2FA blockiert sein)
E-Mail + Passwort direkt in der GUI eingeben.

### Methode 2 – Cookie-Import (empfohlen, robuster)

1. Browser-Extension **Cookie-Editor** installieren:
   - [Chrome](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
   - [Firefox](https://addons.mozilla.org/de/firefox/addon/cookie-editor/)
2. Auf **ancestry.com** einloggen
3. Cookie-Editor öffnen → **Export** → **JSON** → Datei speichern
4. In der GUI: Tab *Login* → *Methode 2* → Datei auswählen

### Methode 3 – Manuelle GUID
Die Kit-GUID steht in der Ancestry-URL:
```
ancestry.com/dna/tests/<HIER-GUID>/matches
```

## Features

| Feature | Beschreibung |
|---|---|
| Paginierter Download | Alle Matches werden seitenweise abgerufen |
| SQLite-Datenbank | Lokal gespeichert, bleibt erhalten |
| Filter & Suche | Name, Beziehung, cM-Schwellenwert, Markierte |
| Notizen | Lokale Notizen pro Match |
| Export | CSV und XLSX |
| Statistiken | Verteilung nach Beziehungstyp, Kennzahlen |
| Log-Ansicht | Eingebettetes Protokollfenster |
| CLI-Modus | `--cli` für Batch-Downloads ohne GUI |

## Datenbankdatei

`ancestry_dna.db` (SQLite) – liegt im Programmverzeichnis.
Kann mit DB Browser for SQLite geöffnet werden.

## Hinweis

Dieses Tool nutzt die **inoffizielle** Ancestry-API (Browser-Traffic).
Ancestry kann Endpunkte jederzeit ändern. Die Cookie-Methode ist stabiler.
Nutzung auf eigene Verantwortung.
