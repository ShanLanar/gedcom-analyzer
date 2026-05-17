@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% == 0 ( set PYTHON=python & goto found )
py --version >nul 2>&1
if %errorlevel% == 0 ( set PYTHON=py & goto found )
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe & goto found
)
echo Python nicht gefunden.
pause & exit /b 1

:found
%PYTHON% "%~dp0main.py"
if %errorlevel% neq 0 pause
