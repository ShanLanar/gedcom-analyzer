@echo off
REM Ancestry DNA Analyzer – GUI Launcher für Windows
setlocal

cd /d "%~dp0"

echo ============================================================================
echo  Ancestry DNA Analyzer – Starting GUI...
echo ============================================================================
echo.

REM Defekte PYTHONHOME/PYTHONPATH neutralisieren (haeufige Ursache fuer
REM "Fatal Python error: No module named 'encodings'" bei conda+Standalone-Mix).
REM Wirkt nur in dieser Sitzung dank setlocal.
set "PYTHONHOME="
set "PYTHONPATH="

python -m ancestry.main %*

if errorlevel 1 (
    echo.
    echo [ERROR] App konnte nicht gestartet werden.
    echo.
    echo Troubleshooting:
    echo   1. Python pruefen:        python --version
    echo   2. Umgebung pruefen:      python -c "import sys; print(sys.prefix)"
    echo      ^(sys.prefix muss zum genutzten python.exe passen^)
    echo   3. Dependencies:          pip install -e .
    echo   4. Manuell starten:       python -m ancestry.main
    echo.
    pause
    exit /b 1
)
