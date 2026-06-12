@echo off
setlocal EnableExtensions
title gedcom-analyzer Updater

REM === Selbst-Schutz gegen Selbst-Modifikation =================================
REM Das git-Update überschreibt diese .bat. Würde sie sich selbst ausführen,
REM stürzt cmd.exe ab (liest ab altem Byte-Offset in der neuen Datei weiter).
REM Lösung: beim Start einmal nach %TEMP% kopieren und von DORT laufen – das
REM git-Update trifft dann nur die Repo-Datei, nicht die laufende Kopie.
if "%~1"=="__fromtemp" goto :main_start
set "SELFCOPY=%TEMP%\gedcom-updater"
if not exist "%SELFCOPY%" mkdir "%SELFCOPY%" >nul 2>&1
copy /y "%~f0" "%SELFCOPY%\update-and-run.bat" >nul
REM Ursprungsordner (wo diese .bat liegt) an die Temp-Kopie weiterreichen,
REM damit REPO_DIR dem tatsaechlichen Speicherort folgt (kein fester Pfad).
call "%SELFCOPY%\update-and-run.bat" __fromtemp "%~dp0"
exit /b %errorlevel%

:main_start
cd /d "%~dp0" >nul 2>&1

REM === Konfiguration ============================================================
REM REPO_DIR folgt dem Ordner, aus dem die .bat gestartet wurde (via %~2 von der
REM Selbstkopie). Ist das bereits ein Git-Repo, wird DORT aktualisiert – egal wo
REM es liegt (z. B. C:\Test\gedcom-analyzer). Nur fuer den ERST-Clone (Ordner ist
REM noch kein Repo) gilt das Standardziel C:\gedcom-analyzer.
set "REPO_DIR=%~2"
if defined REPO_DIR if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"
if not defined REPO_DIR set "REPO_DIR=C:\gedcom-analyzer"
if not exist "%REPO_DIR%\.git" set "REPO_DIR=C:\gedcom-analyzer"
set "REPO_URL=https://github.com/ShanLanar/gedcom-analyzer.git"
REM UTF-8 erzwingen: Tools/App geben Emojis aus; Windows-Konsole ist sonst
REM cp1252 -> UnicodeEncodeError. Wird an alle Kindprozesse vererbt.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
REM Branch beim ERST-Clone. Bei vorhandenem Repo wird der aktuell ausgecheckte
REM Branch automatisch erkannt (siehe unten).
set "DEFAULT_BRANCH=main"
set "BRANCH=%DEFAULT_BRANCH%"
REM ==============================================================================

echo === gedcom-analyzer Updater ===
echo Repo:   %REPO_URL%
echo Ziel:   %REPO_DIR%
echo.

REM --- Git pruefen --------------------------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Git nicht gefunden. Bitte installieren: https://git-scm.com/download/win
    pause & exit /b 1
)

REM --- Python finden ------------------------------------------------------------
set "PYTHON="
where python >nul 2>&1
if %errorlevel% == 0 ( set "PYTHON=python" & goto python_ok )
where py >nul 2>&1
if %errorlevel% == 0 ( set "PYTHON=py" & goto python_ok )
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe" & goto python_ok
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe" & goto python_ok
)
if exist "C:\Python312\python.exe" ( set "PYTHON=C:\Python312\python.exe" & goto python_ok )
if exist "C:\Python311\python.exe" ( set "PYTHON=C:\Python311\python.exe" & goto python_ok )
echo [FEHLER] Python 3.10+ nicht gefunden. Bitte installieren: https://www.python.org/downloads/
pause & exit /b 1

:python_ok
echo Python: %PYTHON%
echo.

REM --- Clone oder Update --------------------------------------------------------
REM Update-Logik bewusst in einer Subroutine (CALL) statt im if/else-Block:
REM so funktioniert normales %BRANCH% zeilenweise – KEIN Delayed Expansion nötig,
REM was den selbst-modifizierenden Batch robust macht.
if not exist "%REPO_DIR%\.git" goto do_clone
call :do_update
if errorlevel 1 ( pause & exit /b 1 )
goto after_repo

:do_clone
if exist "%REPO_DIR%" (
    echo [FEHLER] %REPO_DIR% existiert bereits, ist aber kein Git-Repo.
    echo          Bitte den Ordner umbenennen oder loeschen und erneut starten.
    pause & exit /b 1
)
echo Clone Repository (Branch %DEFAULT_BRANCH%) nach %REPO_DIR% ...
git clone --branch "%DEFAULT_BRANCH%" "%REPO_URL%" "%REPO_DIR%"
if errorlevel 1 ( echo [FEHLER] git clone fehlgeschlagen. & pause & exit /b 1 )
goto after_repo

REM --- Subroutine: vorhandenes Repo aktualisieren ------------------------------
:do_update
echo Aktualisiere Repository in %REPO_DIR% ...
pushd "%REPO_DIR%" >nul
set "BRANCH=%DEFAULT_BRANCH%"
for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
if "%BRANCH%"=="" set "BRANCH=%DEFAULT_BRANCH%"
if /i "%BRANCH%"=="HEAD" (
    echo [WARNUNG] Detached HEAD erkannt - wechsle auf %DEFAULT_BRANCH%.
    set "BRANCH=%DEFAULT_BRANCH%"
    git checkout "%DEFAULT_BRANCH%" >nul 2>&1
)
echo Branch: %BRANCH%
git fetch --prune origin "%BRANCH%"
if errorlevel 1 ( echo [FEHLER] git fetch fehlgeschlagen. & popd >nul & exit /b 1 )
git checkout "%BRANCH%" >nul 2>&1
git reset --hard "origin/%BRANCH%"
if errorlevel 1 ( echo [FEHLER] git reset fehlgeschlagen. & popd >nul & exit /b 1 )
if exist "__pycache__"          rmdir /s /q "__pycache__"
if exist "lib\__pycache__"      rmdir /s /q "lib\__pycache__"
if exist "tasks\__pycache__"    rmdir /s /q "tasks\__pycache__"
if exist "ancestry\__pycache__" rmdir /s /q "ancestry\__pycache__"
popd >nul
exit /b 0

:after_repo

REM --- Aktuelle Version anzeigen ------------------------------------------------
pushd "%REPO_DIR%" >nul
echo Aktuelle Version:
git log -1 --format="  Commit:  %%h" 2>nul
git log -1 --format="  Datum:   %%ad" --date=format:"%%d.%%m.%%Y %%H:%%M" 2>nul
git log -1 --format="  Aenderung: %%s" 2>nul
popd >nul
echo.

REM --- Verzeichnisse anlegen ----------------------------------------------------
if not exist "%REPO_DIR%\data"         mkdir "%REPO_DIR%\data"
if not exist "%REPO_DIR%\output"       mkdir "%REPO_DIR%\output"
if not exist "%REPO_DIR%\logs"         mkdir "%REPO_DIR%\logs"
if not exist "%REPO_DIR%\ancestry\data" mkdir "%REPO_DIR%\ancestry\data"

REM --- Dependencies installieren ------------------------------------------------
echo Installiere/aktualisiere Abhaengigkeiten ...
pushd "%REPO_DIR%" >nul
%PYTHON% -m pip install -e ".[viewer,scraping,vision,dev]" --quiet --upgrade --disable-pip-version-check --no-warn-script-location
set "PIP_RC=%errorlevel%"
REM Optionale ML-Abhaengigkeiten (scikit-learn fuer Herkunfts-Inferenz).
REM Kein Abbruch bei Fehler – ancestry/core/ml_origin.py ist ohne sklearn deaktiviert.
if exist "%REPO_DIR%\ancestry\requirements.txt" (
    %PYTHON% -m pip install -r "%REPO_DIR%\ancestry\requirements.txt" --quiet --upgrade --disable-pip-version-check >nul 2>&1
)
popd >nul
if %PIP_RC% neq 0 (
    echo [FEHLER] pip install fehlgeschlagen.
    pause & exit /b 1
)

REM --- Programm starten ---------------------------------------------------------
REM Die Genealogie-Suite (unified.py) vereint Stammbaum, DNA-Matches, den
REM durchsuchbaren Personen-/Stammbaum-Browser und die Werkzeuge (Crawler,
REM Importe, Matricula-/Entity-Viewer) in EINEM Fenster. Das fruehere Auswahl-
REM menue mit Einzelstarts entfaellt – alles ist ueber die Reiter erreichbar.
echo Starte Genealogie-Suite ...
pushd "%REPO_DIR%" >nul
%PYTHON% unified.py
set "RC=%errorlevel%"
popd >nul

:done
if %RC% neq 0 (
    echo.
    echo [HINWEIS] Anwendung wurde mit Fehlercode %RC% beendet.
    pause
)

:end
endlocal
