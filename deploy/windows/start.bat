@echo off
rem Start "Bilans dzialki" on Windows (double-click). Calls start.ps1.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 (
  echo.
  echo Uruchomienie nie powiodlo sie. Przeczytaj komunikaty powyzej.
)
pause
