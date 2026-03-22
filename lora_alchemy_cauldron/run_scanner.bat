@echo off
setlocal
echo ===================================================
echo LoRA Alchemy Cauldron - Database Scanner
echo ===================================================
echo.
echo Please select a scan mode (defaults to Quick Update in 5 seconds):
echo   [1] Quick Update (Scan only new or modified LoRAs)
echo   [2] Full Rebuild (Delete existing database and scan everything from scratch)
echo.

choice /C 12 /N /T 5 /D 1 /M "Enter your choice [1 or 2]: "
if errorlevel 2 goto Rebuild
if errorlevel 1 goto Quick

:Rebuild
echo.
echo Starting Full Rebuild. This will clear lora_db.json...
cd /d "%~dp0"
python scan_loras.py --rebuild
goto Done

:Quick
echo.
echo Starting Quick Update...
cd /d "%~dp0"
python scan_loras.py
goto Done

:Done
echo.
echo Scan complete! You can close this window.
pause
