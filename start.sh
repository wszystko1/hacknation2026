#!/usr/bin/env bash
# ChronPlon: uruchomienie na Linux i macOS bez make i bez Pythona (uv pobierze Pythona sam).
# Uzycie:  ./start.sh        (gdy brak prawa wykonywania:  bash start.sh)
# Inny port: HN_PORT=8797 ./start.sh   (domyslnie 8000; gdy zajety, skrypt wybierze kolejny wolny)
set -u
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
export PYTHONUTF8=1
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

say()  { printf '%s\n' "$*"; }
fail() {
    printf '\nBLAD: %s\n' "$1" >&2
    [ -n "${2:-}" ] && printf '%s\n' "$2" >&2
    printf 'Opis krok po kroku: docs/URUCHOMIENIE.md\n' >&2
    exit 1
}

say ""
say "=== ChronPlon: uruchamianie aplikacji ==="
[ -f pyproject.toml ] || fail "Nie znaleziono pyproject.toml. Uruchom skrypt z folderu aplikacji (po rozpakowaniu calego ZIP-a)."

# --- uv ---
if ! command -v uv >/dev/null 2>&1; then
    say "Brak programu uv. Instalacja (oficjalny instalator Astral)..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        fail "Brak curl i wget, nie mozna pobrac uv." "Zainstaluj curl (np. sudo apt install curl) albo uv recznie: https://docs.astral.sh/uv/"
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv >/dev/null 2>&1 || fail "Nie udalo sie zainstalowac uv." "Sprawdz internet (astral.sh) albo zainstaluj recznie: https://docs.astral.sh/uv/"
fi
say "uv: $(command -v uv) ($(uv --version))"

# --- zaleznosci ---
say ""
say "Instalacja skladnikow aplikacji (pierwszy raz kilka minut, potrzebny internet, ok. 450 MB)..."
if ! uv sync --no-dev; then
    say "Pierwsza proba nie powiodla sie. Ponawiam raz..."
    uv sync --no-dev || fail "Instalacja skladnikow nie powiodla sie." "Sprawdz internet (pypi.org, github.com), proxy firmowy i miejsce na dysku (ok. 1 GB)."
fi

# --- port ---
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
health_ok() {
    if command -v curl >/dev/null 2>&1; then
        curl -fs -m 2 "http://127.0.0.1:$1/health" 2>/dev/null | grep -q ok
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- -T 2 "http://127.0.0.1:$1/health" 2>/dev/null | grep -q ok
    else
        port_busy "$1"
    fi
}
open_url() {
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 &
    elif command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 &
    else say "Otworz w przegladarce adres: $1"; fi
}

WANT="${HN_PORT:-8000}"
case "$WANT" in ''|*[!0-9]*) say "HN_PORT='$WANT' nie jest numerem portu. Uzywam 8000."; WANT=8000;; esac
if health_ok "$WANT"; then
    say "Aplikacja juz dziala pod adresem http://127.0.0.1:$WANT/ . Otwieram przegladarke."
    open_url "http://127.0.0.1:$WANT/"
    exit 0
fi
PORT=""
for p in $(seq "$WANT" $((WANT + 20))); do
    if ! port_busy "$p"; then PORT="$p"; break; fi
done
[ -n "$PORT" ] || fail "Porty $WANT-$((WANT + 20)) sa zajete." "Ustaw wolny port: HN_PORT=9000 ./start.sh"
[ "$PORT" = "$WANT" ] || say "Port $WANT jest zajety przez inny program. Uzywam portu $PORT."

# --- serwer ---
URL="http://127.0.0.1:$PORT/"
say ""
say "Uruchamianie serwera na $URL ..."
uv run --no-dev uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
SERVER=$!
cleanup() {
    trap - INT TERM EXIT
    if kill -0 "$SERVER" 2>/dev/null; then
        pkill -P "$SERVER" 2>/dev/null
        kill "$SERVER" 2>/dev/null
        wait "$SERVER" 2>/dev/null
    fi
    say "Serwer zatrzymany."
}
trap 'cleanup; exit 0' INT TERM
trap cleanup EXIT

READY=0
for _ in $(seq 1 120); do
    kill -0 "$SERVER" 2>/dev/null || break
    if health_ok "$PORT"; then READY=1; break; fi
    sleep 0.5
done
kill -0 "$SERVER" 2>/dev/null || fail "Serwer zakonczyl prace od razu." "Przeczytaj komunikaty powyzej."
if [ "$READY" = 1 ]; then say "Gotowe. Aplikacja dziala pod adresem $URL"
else say "Serwer nie odpowiedzial w ciagu 60 s, ale nadal dziala. Odswiez strone po chwili."; fi
open_url "$URL"
say "ZATRZYMANIE: Ctrl+C w tym oknie."
wait "$SERVER"
