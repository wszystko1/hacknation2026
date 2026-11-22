# Start "Bilans dzialki" on Windows without make. Run: powershell -ExecutionPolicy Bypass -File start.ps1
$ErrorActionPreference = "Stop"
$Port = if ($env:PORT) { $env:PORT } else { "8000" }
Set-Location (Join-Path $PSScriptRoot "..\..")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Brak programu uv. Instaluje go teraz (oficjalny instalator Astral)..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "Nie udalo sie zainstalowac uv. Zainstaluj recznie: https://docs.astral.sh/uv/ i uruchom skrypt ponownie." -ForegroundColor Red
        exit 1
    }
}
Write-Host "Instaluje zaleznosci (pierwszy raz kilka minut)..."
uv sync --no-dev
if ($LASTEXITCODE -ne 0) { Write-Host "Blad instalacji zaleznosci." -ForegroundColor Red; exit 1 }

Start-Job -ScriptBlock { param($p) Start-Sleep -Seconds 5; Start-Process "http://127.0.0.1:$p/" } -ArgumentList $Port | Out-Null
Write-Host "Aplikacja dziala pod adresem http://127.0.0.1:$Port/ . Zatrzymanie: Ctrl+C." -ForegroundColor Green
uv run --no-dev uvicorn app.main:app --host 127.0.0.1 --port $Port
