@echo off
REM Ancestry DNA Analyzer – GUI Launcher für Windows

cd /d "%~dp0"

echo ============================================================================
echo  Ancestry DNA Analyzer – Starting GUI...
echo ============================================================================
echo.

python run_gui.py

if errorlevel 1 (
    echo.
    echo [ERROR] App konnte nicht gestartet werden.
    echo.
    echo Troubleshooting:
    echo   1. Stelle sicher, dass Python installiert ist: python --version
    echo   2. Installiere Dependencies: pip install -e .
    echo   3. Starte nochmal mit: python run_gui.py
    echo.
    pause
    exit /b 1
)
