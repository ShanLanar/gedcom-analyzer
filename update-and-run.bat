@echo off
setlocal EnableExtensions
title gedcom-analyzer Updater
cd /d "%~dp0" >nul 2>&1

REM === Konfiguration ============================================================
set "REPO_DIR=C:\gedcom-analyzer"
set "REPO_URL=https://github.com/ShanLanar/gedcom-analyzer.git"
set "BRANCH=main"
REM ==============================================================================

echo === gedcom-analyzer Updater ===
echo Repo:   %REPO_URL%
echo Branch: %BRANCH%
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
    echo Clone Repository nach %REPO_DIR% ...
    git clone --branch "%BRANCH%" "%REPO_URL%" "%REPO_DIR%"
    if errorlevel 1 ( echo [FEHLER] git clone fehlgeschlagen. & pause & exit /b 1 )
) else (
    echo Aktualisiere Repository in %REPO_DIR% ...
    pushd "%REPO_DIR%" >nul
    git fetch --prune origin "%BRANCH%"
    if errorlevel 1 ( echo [FEHLER] git fetch fehlgeschlagen. & popd >nul & pause & exit /b 1 )
    git checkout "%BRANCH%" >nul 2>&1
    git pull --ff-only origin "%BRANCH%"
    if errorlevel 1 (
        echo [FEHLER] git pull fehlgeschlagen ^(lokale Aenderungen oder Konflikte?^).
        echo          Tipp: git status im Repo-Ordner pruefen.
        popd >nul & pause & exit /b 1
    )
    popd >nul
)
echo.

REM --- Verzeichnisse anlegen ----------------------------------------------------
if not exist "%REPO_DIR%\data"   mkdir "%REPO_DIR%\data"
if not exist "%REPO_DIR%\output" mkdir "%REPO_DIR%\output"
if not exist "%REPO_DIR%\logs"   mkdir "%REPO_DIR%\logs"

REM --- Dependencies installieren ------------------------------------------------
echo Installiere/aktualisiere Abhaengigkeiten ...
%PYTHON% -m pip install -r "%REPO_DIR%\requirements.txt" --quiet --upgrade --disable-pip-version-check
if %errorlevel% neq 0 (
    echo [FEHLER] pip install fehlgeschlagen.
    pause & exit /b 1
)
echo.

REM --- Anwendung starten --------------------------------------------------------
echo Starte Anwendung ...
pushd "%REPO_DIR%" >nul
%PYTHON% main.py
set "RC=%errorlevel%"
popd >nul

if %RC% neq 0 (
    echo.
    echo [HINWEIS] Anwendung wurde mit Fehlercode %RC% beendet.
    pause
)
endlocal
