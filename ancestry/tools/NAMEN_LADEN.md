# DNA-Match-Namen laden

Die Match-Liste lädt zuerst **ohne Namen** (du siehst nur ein 8-Zeichen-Kürzel
wie `BEC4AE66`). So bekommst du die echten Namen.

## Weg 1 – automatisch im Tool (zuerst probieren)

1. Tool starten → Reiter **Herunterladen**
2. Bei **A2: Namen nachladen** auf **▶ Namen nachladen** klicken
3. Das Tool probiert automatisch mehrere Verfahren durch.
   - **Klappt es** → die Namen erscheinen in der Matches-Tabelle. Fertig. ✅
   - **Steht im Log** „keine CSRF-Form erfolgreich" → weiter mit Weg 2.

## Weg 2 – über den Browser (klappt immer)

Der Namen-Endpunkt von Ancestry akzeptiert Anfragen nur aus dem Browser.
Dieses kleine Skript holt die Namen dort ab und speichert sie als Datei.

1. Im Browser bei **ancestry.com einloggen** und die Match-Liste öffnen:
   `https://www.ancestry.com/discoveryui-matches/list/DEINE-KIT-GUID`
2. **F12** drücken → oben den Reiter **Console** wählen
3. Den **kompletten** Inhalt der Datei
   [`fetch_names_browser.js`](fetch_names_browser.js) hineinkopieren → **Enter**
4. Unten rechts läuft ein Fortschrittsbalken. Nach ein paar Minuten lädt sich
   automatisch die Datei **`ancestry_names_<GUID>.json`** herunter
   (üblicherweise im Ordner *Downloads*).
5. Zurück im Tool: Menü **Datei → Namen importieren (JSON/CSV) …** → die eben
   heruntergeladene Datei auswählen.

Die Namen erscheinen in der Matches-Tabelle. ✅

### Hinweise
- Das Skript **liest nur** – es ändert nichts an deinem Ancestry-Konto.
- Falls die Meldung **„profileData lehnt ab (303)"** erscheint: Seite mit **F5**
  neu laden und das Skript **als Allererstes** wieder einfügen.
- Der Import überschreibt nur Platzhalter (leer / `Anonym` / GUID-Kürzel).
  **Manuell eingetragene Namen bleiben erhalten.**
