@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_auralis.ps1"
if errorlevel 1 (
  echo.
  echo Auralis did not start. See the message above.
  pause
)
