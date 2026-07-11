@echo off
rem ============================================================
rem  KI-Werkstatt - einmalige Installation
rem  Installiert die Python-Pakete aus requirements.txt.
rem ============================================================
cd /d "%~dp0"

echo.
echo  KI-WERKSTATT - Installation
echo  ===========================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo  FEHLER: Python wurde nicht gefunden.
    echo  Bitte installiere Python 3.9+ von https://www.python.org/downloads/
    echo  und hake dabei "Add python.exe to PATH" an.
    echo.
    pause
    exit /b 1
)

echo  Installiere Python-Pakete (kann 1-2 Minuten dauern) ...
echo.
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  FEHLER bei der Paket-Installation. Meldung oben pruefen.
    echo.
    pause
    exit /b 1
)

echo.
echo  Fertig! Starten mit Doppelklick auf start.bat
echo.
echo  Optional fuer Bild-PDFs (OCR) - einmalig in PowerShell:
echo    winget install -e --id UB-Mannheim.TesseractOCR
echo    winget install -e --id oschwartz10612.Poppler
echo.
pause
