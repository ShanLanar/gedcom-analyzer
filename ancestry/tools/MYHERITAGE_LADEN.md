# MyHeritage DNA-Matches laden

MyHeritage ist ein React-SPA: die 11.145 Matches werden **nicht** ins HTML
gerendert, sondern per GraphQL nachgeladen und in IndexedDB gecached. Deshalb
funktioniert reines HTML-Parsen (`download_myheritage.py`) nicht.

Der zuverlässige Weg ist die GraphQL-Query **aus der Browser-Console**: dort ist
die Session bereits authentifiziert (Cookies + interner Token), und der Aufruf
geht same-origin an `/web-family-graphql` – kein CORS, keine Token-Bastelei.

## Schritt 1 – Im Browser herunterladen

1. Bei MyHeritage einloggen und die Match-Liste öffnen:
   `https://www.myheritage.com/dna/matches/OYYV65GLYXMJ2JPTF5BJPM3IIQRB5LQ`
2. Warten, bis die ersten Matches **sichtbar** sind (die App muss initialisiert
   sein, damit der Token-Service bereitsteht).
3. `F12` → Reiter **Console** → den **gesamten** Inhalt von `mh_grab_all.js`
   einfügen → Enter.
4. Laufen lassen. Fortschritt erscheint als `[MH] 1234/11145 (11.1%)`.
   Dauer ~3–4 Minuten. Alle 500 Matches wird eine Backup-Datei
   `mh_matches_partial_XXXX.json` heruntergeladen.
5. Am Ende lädt sich `mh_all_matches.json` automatisch herunter
   (Standard-Download-Ordner).

**Tab offen lassen**, nicht wegnavigieren – das Script läuft als Schleife im
Vordergrund der Seite. Bei „Auth abgelaufen" erneuert es den Token selbst.

## Schritt 2 – In die Datenbank importieren

```
mh_all_matches.json  →  nach  ancestry/tools/  kopieren
cd ancestry/tools
python import_mh_matches.py mh_all_matches.json
```

Das legt das Kit `MyHeritage (Shan)` an und importiert alle Matches mit
`source='myheritage'` in `ancestry/ancestry_dna.db` – inklusive
cM, Segmente, Verwandtschafts-Wahrscheinlichkeiten, Land und Stammbaum-Info.

Danach erscheinen die Matches im Tool im Kit-Dropdown des Matches-Reiters.

## Falls etwas klemmt

* **„Kein Token erhalten"** → Seite neu laden (F5), warten bis Matches sichtbar
  sind, Script erneut einfügen.
* **Bricht nach wenigen Seiten ab** → die Backup-Datei
  `mh_matches_partial_XXXX.json` enthält das bisher Geladene und lässt sich
  genauso mit `import_mh_matches.py` importieren.
* **0 Matches / leere Seite sofort** → der interne `KIT_ID` (Variable oben im
  Script) stimmt nicht. Er steht in der App unter
  `console.log(window.dnaKitId)` oder im IndexedDB-Eintrag als
  `dnakit-…`. Dort eintragen und erneut starten.

## Warum nicht die alten Scripts?

| Script | Problem |
|---|---|
| `download_myheritage.py` | SPA rendert kein JSON ins HTML → findet nichts |
| `spy_*.js`, `*_scroll_*` | Infinite-Scroll triggert keine abfangbaren Calls zuverlässig |
| `download_all_matches.js` | rief `familygraphql.myheritage.com` direkt auf (CORS/fetch-Patch-abhängig) |
| **`mh_grab_all.js`** | **same-origin `/web-family-graphql` + Token wie die App → robust** |
