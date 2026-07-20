@echo off
setlocal
cd /d "%~dp0"

set "APP_FILE=app_v12.py"
if not exist "%APP_FILE%" set "APP_FILE=app.py"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%APP_FILE%"
    exit /b 0
)

where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%APP_FILE%"
    exit /b 0
)

echo Python nerastas. Paleiskite setup arba sukurkite .venv aplinka.
pause
exit /b 1
