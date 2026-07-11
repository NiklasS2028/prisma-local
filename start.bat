@echo off
rem ============================================================
rem  Prisma - Start
rem  Startet den lokalen Server und oeffnet den Browser.
rem  Beenden: dieses Fenster schliessen oder Strg+C druecken.
rem ============================================================
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo  FEHLER: Python wurde nicht gefunden.
    echo  Bitte erst install.bat ausfuehren (bzw. Python installieren).
    pause
    exit /b 1
)

echo.
echo  PRISMA startet ...
echo  Browser oeffnet sich gleich auf http://localhost:8770
echo  Beenden: dieses Fenster schliessen oder Strg+C
echo.

rem Browser mit kurzer Verzoegerung oeffnen, damit der Server schon laeuft
start "" /b cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8770"

python app.py

pause
