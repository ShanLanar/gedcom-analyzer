@echo off
REM Git Ref Lock Problem Fixer für Windows
REM
REM Nutze: fix_git_refs.bat [REPO_PATH]
REM Beispiel: fix_git_refs.bat C:\Test\gedcom-analyzer

setlocal enabledelayedexpansion

if "%~1"=="" (
    set REPO_PATH=%CD%
) else (
    set REPO_PATH=%~1
)

echo ============================================================================
echo  GIT REF LOCK FIXER - Windows Version
echo ============================================================================
echo.
echo Repository: %REPO_PATH%
echo.

cd /d "%REPO_PATH%" || (
    echo FEHLER: Konnte nicht zu %REPO_PATH% wechseln
    pause
    exit /b 1
)

if not exist ".git" (
    echo FEHLER: Kein Git Repository in %REPO_PATH%
    pause
    exit /b 1
)

echo Starte Reparatur...
echo.

REM Option 1: Git garbage collection
echo [1/5] Git Garbage Collection...
git gc --aggressive 2>nul

REM Option 2: Prune
echo [2/5] Git Prune...
git prune 2>nul

REM Option 3: Force fetch
echo [3/5] Force Fetch...
git fetch --force origin main 2>nul
if !errorlevel! neq 0 (
    echo [3b/5] Force Fetch fehlgeschlagen, versuche alternative Methode...
    git update-ref -d refs/remotes/origin/main 2>nul
    git fetch origin main 2>nul
)

REM Option 4: Status check
echo.
echo [4/5] Status Check...
git status

echo.
echo [5/5] Branches...
git branch -a

echo.
echo ============================================================================
echo REPAIR ABGESCHLOSSEN
echo ============================================================================
echo.
echo Nächste Schritte:
echo   1. git pull origin main
echo   2. python -m pip install -e .
echo.

pause
