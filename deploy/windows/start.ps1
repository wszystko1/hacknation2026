# ChronPlon - uruchomienie na Windows (bez make, bez Pythona).
# Zwykle uruchamiane przez start.bat. Reczne uruchomienie:
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy\windows\start.ps1
# Plik ma byc czystym ASCII (Windows PowerShell 5.1 czyta pliki bez BOM jako ANSI).
# Zmienna portu: HN_PORT (tak samo jak w Makefile i w "python -m app"), domyslnie 8000.

$ErrorActionPreference = "Continue"
$here = if ($PSScriptRoot) { $PSScriptRoot } else { $env:CP_DIR }
if (-not $here) { $here = (Get-Location).ProviderPath }

function Write-Info($m) { Write-Host $m }
function Write-Ok($m)   { Write-Host $m -ForegroundColor Green }
function Write-Warn($m) { Write-Host $m -ForegroundColor Yellow }
function Fail($m, $hint) {
    Write-Host ""
    Write-Host "BLAD: $m" -ForegroundColor Red
    if ($hint) { Write-Host $hint -ForegroundColor Yellow }
    Write-Host "Opis krok po kroku i najczestsze problemy: docs\URUCHOMIENIE.md" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "=== ChronPlon: uruchamianie aplikacji ===" -ForegroundColor Cyan

# --- 1. Katalog repozytorium ---
$root = $null
try { $root = (Resolve-Path -LiteralPath (Join-Path $here "..\..")).ProviderPath } catch { }
if (-not $root -or -not (Test-Path -LiteralPath (Join-Path $root "pyproject.toml"))) {
    Fail "Nie znaleziono plikow aplikacji (pyproject.toml) obok folderu deploy." `
         "Najczestsza przyczyna: start.bat uruchomiono z podgladu ZIP. Kliknij ZIP prawym przyciskiem, wybierz 'Wyodrebnij wszystko', potem uruchom start.bat z rozpakowanego folderu."
}
Set-Location -LiteralPath $root
Write-Info "Folder aplikacji: $root"
try { Get-ChildItem -LiteralPath $here -File | Unblock-File -ErrorAction SilentlyContinue } catch { }

# Utf-8 w Pythonie (Windows domyslnie uzywa cp1250: bezpiecznik dla plikow z polskimi znakami).
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
# Bez ostrzezen o hardlinkach, gdy cache uv lezy na innym dysku niz folder aplikacji.
if (-not $env:UV_LINK_MODE) { $env:UV_LINK_MODE = "copy" }

# Zbyt dluga sciezka (limit 260 znakow w Windows): srodowisko Pythona w krotkim miejscu.
if ($root.Length -gt 90 -and -not $env:UV_PROJECT_ENVIRONMENT) {
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $env:LOCALAPPDATA "ChronPlon\venv"
    Write-Warn "Sciezka do folderu jest dluga ($($root.Length) znakow). Srodowisko Pythona trafi do: $env:UV_PROJECT_ENVIRONMENT"
}

# --- 2. uv (menedzer pakietow; sam pobiera tez Pythona) ---
function Update-SessionPath {
    $m = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $u = [Environment]::GetEnvironmentVariable("Path", "User")
    $extra = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:LOCALAPPDATA\Microsoft\WinGet\Links"
    $env:Path = "$extra;$u;$m;$env:Path"
}
function Find-Uv {
    $c = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.Source }
    foreach ($p in @("$here\uv.exe", "$root\uv.exe", "$env:USERPROFILE\.local\bin\uv.exe",
                     "$env:USERPROFILE\.cargo\bin\uv.exe", "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe")) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

$uv = Find-Uv
if (-not $uv) {
    Write-Warn "Brak programu uv. Instalacja (oficjalny instalator Astral, kilkanascie sekund)..."
    try {
        & "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command `
            "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; irm https://astral.sh/uv/install.ps1 | iex"
    } catch { Write-Warn "Instalator uv zglosil blad: $($_.Exception.Message)" }
    Update-SessionPath
    $uv = Find-Uv
}
if (-not $uv -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Warn "Druga proba: winget install astral-sh.uv ..."
    try { & winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements } catch { }
    Update-SessionPath
    $uv = Find-Uv
}
if (-not $uv) {
    Fail "Nie udalo sie zainstalowac programu uv." @"
Co zrobic:
  1. Sprawdz polaczenie z internetem (wymagane: astral.sh, github.com, pypi.org). Na komputerze sluzbowym instalacja moze byc zablokowana.
  2. Reczne pobranie: https://github.com/astral-sh/uv/releases/latest , plik uv-x86_64-pc-windows-msvc.zip.
     Rozpakuj z niego uv.exe do folderu: $root
     i uruchom start.bat jeszcze raz (skrypt znajdzie uv.exe w tym folderze).
"@
}
Write-Info "uv: $uv ($(& $uv --version))"

# --- 3. Zaleznosci (pierwszy raz kilka minut, ok. 450 MB razem z Pythonem) ---
Write-Host ""
Write-Warn "Instalacja skladnikow aplikacji. Pierwszy raz trwa kilka minut i wymaga internetu. Nie zamykaj okna."
& $uv sync --no-dev
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Pierwsza proba nie powiodla sie. Ponawiam raz..."
    & $uv sync --no-dev
}
if ($LASTEXITCODE -ne 0) {
    Fail "Instalacja skladnikow nie powiodla sie." @"
Mozliwe przyczyny: brak internetu, siec firmowa z proxy lub zapora blokujaca pypi.org / github.com / files.pythonhosted.org,
antywirus blokujacy pliki, brak miejsca na dysku (potrzeba ok. 1 GB), zbyt dluga sciezka do folderu.
Sprobuj: przenies folder do C:\ChronPlon (krotka sciezka bez polskich znakow) i uruchom start.bat jeszcze raz.
"@
}

# --- 4. Port ---
function Test-PortFree($p) {
    try {
        $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, [int]$p)
        $l.Start(); $l.Stop(); return $true
    } catch { return $false }
}
function Test-Health($p) {
    try {
        [System.Net.WebRequest]::DefaultWebProxy = $null
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$p/health" -UseBasicParsing -TimeoutSec 2
        return ($r.StatusCode -eq 200 -and $r.Content -match "ok")
    } catch { return $false }
}

$want = 8000
if ($env:HN_PORT -match '^\d{2,5}$' -and [int]$env:HN_PORT -le 65535) { $want = [int]$env:HN_PORT }
elseif ($env:HN_PORT) { Write-Warn "HN_PORT='$($env:HN_PORT)' nie jest poprawnym numerem portu. Uzywam 8000." }

if (Test-Health $want) {
    Write-Ok "Aplikacja juz dziala pod adresem http://127.0.0.1:$want/ . Otwieram przegladarke."
    Start-Process "http://127.0.0.1:$want/"
    exit 0
}
$port = $null
foreach ($p in $want..($want + 20)) {
    if ($p -le 65535 -and (Test-PortFree $p)) { $port = $p; break }
}
if (-not $port) { Fail "Porty $want-$($want + 20) sa zajete." "Zamknij inne programy albo ustaw wolny port: set HN_PORT=9000 (w cmd) i uruchom jeszcze raz." }
if ($port -ne $want) { Write-Warn "Port $want jest zajety przez inny program. Uzywam portu $port." }

# --- 5. Serwer, oczekiwanie na gotowosc, przegladarka ---
$url = "http://127.0.0.1:$port/"
Write-Host ""
Write-Info "Uruchamianie serwera na $url ..."
Write-Info "(Gdy Zapora Windows zapyta o zgode: wybierz Zezwol. Aplikacja nasluchuje tylko na tym komputerze.)"
$proc = Start-Process -FilePath $uv -ArgumentList @("run", "--no-dev", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$port") `
        -WorkingDirectory $root -NoNewWindow -PassThru
$null = $proc.Handle

try {
    $ready = $false
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt 60) {
        if ($proc.HasExited) { break }
        if (Test-Health $port) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if ($proc.HasExited) {
        Fail "Serwer zakonczyl prace od razu (kod $($proc.ExitCode))." "Przeczytaj komunikaty powyzej. Jesli brakuje pliku vcomp140.dll lub msvcp140.dll: zainstaluj 'Microsoft Visual C++ Redistributable x64' (winget install Microsoft.VCRedist.2015+.x64) i uruchom jeszcze raz."
    }
    if ($ready) {
        Write-Ok "Gotowe. Aplikacja dziala pod adresem $url"
    } else {
        Write-Warn "Serwer nie odpowiedzial w ciagu 60 s, ale nadal dziala. Otwieram przegladarke; w razie bialej strony odswiez ja po chwili."
    }
    try { Start-Process $url } catch { Write-Warn "Nie udalo sie otworzyc przegladarki. Wpisz recznie adres: $url" }
    Write-Host ""
    Write-Host "ZATRZYMANIE: nacisnij Ctrl+C w tym oknie albo je zamknij." -ForegroundColor Cyan
    $proc.WaitForExit()
    Write-Info "Serwer zatrzymany."
} finally {
    if ($proc -and -not $proc.HasExited) {
        try { & "$env:SystemRoot\System32\taskkill.exe" /PID $proc.Id /T /F | Out-Null } catch { }
    }
}
exit 0
