@echo off
REM ===================================================================
REM  Startet eine SEPARATE Chrome-Instanz mit Remote-Debugging (Port 9222)
REM  in einem eigenen Profil-Verzeichnis. Dein normales Chrome bleibt
REM  offen und unangetastet (anderes --user-data-dir = eigene Instanz).
REM
REM  EINMALIG in diesem Fenster-Chrome einrichten:
REM    1. Genealogy Assistant installieren (Chrome Web Store) + verifizieren
REM    2. Auf MyHeritage einloggen
REM  Danach bleibt beides in diesem Profil gespeichert.
REM
REM  Dann das Scraper-Skript mit  --cdp  starten.
REM ===================================================================

set "DEBUG_PROFILE=%LOCALAPPDATA%\mh_chrome_debug"

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
    echo Chrome nicht gefunden. Bitte Pfad in dieser .bat anpassen.
    pause
    exit /b 1
)

echo Starte Debug-Chrome (Port 9222), Profil: %DEBUG_PROFILE%
"%CHROME%" --remote-debugging-port=9222 --user-data-dir="%DEBUG_PROFILE%" https://www.myheritage.com/dna/matches
