@echo off
rem ChronPlon - uruchomienie na Windows (dwuklik). Plik tylko ASCII, konce linii CRLF.
rem Uruchamia start.ps1 bez wzgledu na polityke wykonywania skryptow (skrypt jest czytany jako tekst).
chcp 65001 >nul
title ChronPlon - uruchamianie
set "CP_DIR=%~dp0"
set "CP_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%CP_PS%" set "CP_PS=powershell"
echo.
echo ChronPlon - uruchamianie aplikacji. Nie zamykaj tego okna.
echo Pierwsze uruchomienie trwa kilka minut (pobieranie skladnikow, potrzebny internet).
"%CP_PS%" -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create([System.IO.File]::ReadAllText((Join-Path $env:CP_DIR 'start.ps1'))))"
set "CP_CODE=%errorlevel%"
echo.
if not "%CP_CODE%"=="0" echo Uruchomienie nie powiodlo sie ^(kod %CP_CODE%^). Przeczytaj komunikaty powyzej.
if not "%CP_CODE%"=="0" echo Pomoc: docs\URUCHOMIENIE.md ^(tabela "Najczestsze problemy"^).
if "%CP_CODE%"=="0" echo Aplikacja zostala zatrzymana. Mozna zamknac to okno.
pause
