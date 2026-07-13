@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo Nerastas .env failas.
    echo Nukopijuokite .env.example i .env ir irasykite API rakta.
    echo.
    pause
    exit /b 1
)

"C:\Users\Vartotojas\AppData\Local\Programs\Python\Python313\python.exe" main.py

echo.
pause