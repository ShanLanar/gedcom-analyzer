@echo off
setlocal EnableExtensions EnableDelayedExpansion
title gedcom-analyzer Updater
cd /d "%~dp0" >nul 2>&1

REM === Konfiguration ============================================================
set "REPO_DIR=C:\gedcom-analyzer"
set "REPO_URL=https://github.com/ShanLanar/gedcom-analyzer.git"
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
if not exist "%REPO_DIR%\.git" (
    if exist "%REPO_DIR%" (
        echo [FEHLER] %REPO_DIR% existiert bereits, ist aber kein Git-Repo.
        echo          Bitte den Ordner umbenennen oder loeschen und erneut starten.
        pause & exit /b 1
    )
    echo Clone Repository (Branch %BRANCH%) nach %REPO_DIR% ...
    git clone --branch "%BRANCH%" "%REPO_URL%" "%REPO_DIR%"
    if errorlevel 1 ( echo [FEHLER] git clone fehlgeschlagen. & pause & exit /b 1 )
) else (
    echo Aktualisiere Repository in %REPO_DIR% ...
    pushd "%REPO_DIR%" >nul
    REM Aktuell ausgecheckten Branch erkennen (statt fest 'main').
    for /f "delims=" %%B in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
    if "!BRANCH!"=="" set "BRANCH=%DEFAULT_BRANCH%"
    if "!BRANCH!"=="HEAD" (
        echo [WARNUNG] Detached HEAD erkannt - wechsle auf %DEFAULT_BRANCH%.
        set "BRANCH=%DEFAULT_BRANCH%"
        git checkout "%DEFAULT_BRANCH%" >nul 2>&1
    )
    echo Branch: !BRANCH!
    git fetch --prune origin "!BRANCH!"
    if errorlevel 1 ( echo [FEHLER] git fetch fehlgeschlagen. & popd >nul & pause & exit /b 1 )
    git checkout "!BRANCH!" >nul 2>&1
    git reset --hard "origin/!BRANCH!"
    if errorlevel 1 (
        echo [FEHLER] git reset fehlgeschlagen.
        popd >nul & pause & exit /b 1
    )
    if exist "__pycache__"        rmdir /s /q "__pycache__"
    if exist "lib\__pycache__"    rmdir /s /q "lib\__pycache__"
    if exist "tasks\__pycache__"  rmdir /s /q "tasks\__pycache__"
    if exist "ancestry\__pycache__" rmdir /s /q "ancestry\__pycache__"
    popd >nul
)

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
%PYTHON% -m pip install -r "%REPO_DIR%\requirements.txt" --quiet --upgrade --disable-pip-version-check
%PYTHON% -m pip install -r "%REPO_DIR%\ancestry\requirements.txt" --quiet --upgrade --disable-pip-version-check
if %errorlevel% neq 0 (
    echo [FEHLER] pip install fehlgeschlagen.
    pause & exit /b 1
)

REM --- Programmauswahl ----------------------------------------------------------
echo Welches Programm starten?
echo   [1] GEDCOM-Analyzer  (Stammbaum-Auswertung)
echo   [2] Ancestry DNA Tool (DNA-Matches ^& Clustering)
echo   [3] Beenden
echo.
set /p CHOICE="Auswahl (1/2/3): "

if "%CHOICE%"=="1" goto start_gedcom
if "%CHOICE%"=="2" goto start_dna
if "%CHOICE%"=="3" goto end
echo Ungueltige Eingabe – starte GEDCOM-Analyzer.

:start_gedcom
echo Starte GEDCOM-Analyzer ...
pushd "%REPO_DIR%" >nul
%PYTHON% main.py
set "RC=%errorlevel%"
popd >nul
goto done

:start_dna
echo Starte Ancestry DNA Tool ...
pushd "%REPO_DIR%\ancestry" >nul
%PYTHON% main.py
set "RC=%errorlevel%"
popd >nul
goto done

:done
if %RC% neq 0 (
    echo.
    echo [HINWEIS] Anwendung wurde mit Fehlercode %RC% beendet.
    pause
)

:end
endlocal
