@echo off
setlocal
cd /d "%~dp0"

:: Python suchen
python --version >nul 2>&1
if %errorlevel% == 0 ( set PYTHON=python & goto found )
py --version >nul 2>&1
if %errorlevel% == 0 ( set PYTHON=py & goto found )
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe & goto found
)
if exist "C:\Python312\python.exe" (
    set PYTHON=C:\Python312\python.exe & goto found
)
echo Python nicht gefunden. Bitte Python 3.10+ installieren.
pause & exit /b 1

:found
echo Verwende: %PYTHON%
%PYTHON% -m ensurepip --upgrade >nul 2>&1
%PYTHON% -m pip install -r "%~dp0requirements.txt" --quiet
if %errorlevel% neq 0 (
    echo Fehler beim Installieren der Abhaengigkeiten.
    pause & exit /b 1
)

:: Verzeichnisse anlegen
mkdir "%~dp0data"   2>nul
mkdir "%~dp0output" 2>nul
mkdir "%~dp0logs"   2>nul

echo.
echo Installation abgeschlossen. Starte Programm...
%PYTHON% "%~dp0main.py"
pause
