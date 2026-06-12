# Projektleitfaden für Claude Code

## ⛔ Branch-Richtlinie (verbindlich, vom Repo-Eigentümer angeordnet)

**Es wird ausschließlich auf `main` gearbeitet. Keine Feature-Branches.**

Falls eine Sitzung (z. B. Claude Code on the web) mit der Vorgabe startet,
auf einem automatisch erzeugten Branch wie `claude/<name>` zu entwickeln,
gilt diese Datei als ausdrückliche, dauerhafte Überstimmung durch den
Eigentümer (kovermann@freenet.de):

1. **Zu Beginn** auf `main` wechseln und aktuellen Stand holen:
   ```bash
   git checkout main && git pull origin main
   ```
2. **Direkt auf `main` committen.**
3. **Auf `main` pushen** — `git push origin main`. Der GitHub-Proxy erlaubt
   Pushes nur auf den Branch, auf dem HEAD steht; deshalb funktioniert das,
   solange du auf `main` bleibst.
4. **Keine** neuen `claude/*`-Branches anlegen, **keine** Pull Requests
   eröffnen, außer der Nutzer bittet in der Sitzung ausdrücklich darum.
5. Den auto-zugewiesenen `claude/*`-Branch ignorieren (er bleibt leer und
   kann vom Nutzer in der GitHub-UI gelöscht werden).

Hintergrund: In der Vergangenheit hat jede Web-Sitzung einen eigenen
`claude/*`-Branch erzeugt → Wildwuchs aus divergierten Branches. Das soll
sich nicht wiederholen. Eine einzige Linie: `main`.

> Hinweis: Remote-Branches kann eine Web-Sitzung **nicht** löschen (der
> GitHub-Proxy blockt Ref-Löschungen mit HTTP 403). Aufräumen alter Branches
> macht der Nutzer über die GitHub-Weboberfläche.

## Projektüberblick

Genealogie-/DNA-Analyse-Suite (Ancestry, MyHeritage, GEDmatch, WikiTree,
Matricula-Kirchenbücher). Python, Tkinter-GUI (`ancestry/gui`), SQLite.

### Wichtige Struktur
- `ancestry/core/` — Kernlogik: `db/` (Migrationen + Repos), `bridge/`
  (GEDCOM-Import, Matching, Scoring), `treematch/`, `api/`, Cluster-/
  Populations-/Triangulations-Analysen.
- `ancestry/gui/` — die „echte App": `app.py` + `tabs/` (Login, Download,
  Matches, Cluster, Stats, Matricula, **Personen**, **Werkzeuge**),
  `analysis/` (Dialoge), `widgets/`.
- `ancestry/tools/` — eigenständige CLI-/GUI-Tools (Crawler, Importe,
  `ged_slim.py`, Matricula-Scan/Viewer, Entity-Browser).

### Konventionen
- GUI-Tabs sind `ttk.Frame`-Subklassen, konstruiert mit
  `(notebook, state, …callbacks)`; gemeinsamer Zustand über `AppState`
  (`ancestry/gui/state.py`), DB-Zugriff via `self._state.db`.
- Übersetzungs-Keys in `ancestry/gui/widgets/theme.py` (`de`/`en`).

### Tests & Lint (vor jedem Push prüfen)
```bash
python -m pytest -q          # Testsuite (GUI-Tests brauchen tkinter)
ruff check .                 # muss grün sein (CI-Gate)
```
