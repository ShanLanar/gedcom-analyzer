@echo off
REM Holt alle Shared Matches via CDP (laufendes Chrome mit Port 9222)
REM Vorher: start_chrome_debug.bat ausfuehren und bei MyHeritage einloggen

set "CSV=%USERPROFILE%\Documents\Andreas Kovermann D-44D71405-0D71-4D2B-91F7-337F3344BD17 - MyHeritage Match List.csv"
if not exist "%CSV%" set "CSV=C:\gedcom-analyzer\data\Andreas Kovermann D-44D71405-0D71-4D2B-91F7-337F3344BD17 - MyHeritage Match List.csv"

cd /d "%~dp0"
python ancestry\tools\fetch_mh_shared_matches.py --csv "%CSV%" --debug --min-cm 15 --no-skip --cdp http://127.0.0.1:9222 --pause 3
pause
