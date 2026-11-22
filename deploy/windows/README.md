# Uruchomienie na Windows (bez `make`, bez Pythona)

Instrukcja dla osób bez doświadczenia: [docs/URUCHOMIENIE.md](../../docs/URUCHOMIENIE.md).

Skrót: rozpakować cały ZIP (najlepiej do `C:\ChronPlon`), kliknąć dwukrotnie `deploy\windows\start.bat`.

Co robi `start.bat` (przez `start.ps1`):

1. Szuka programu `uv` (PATH, `uv.exe` w folderze aplikacji, `%USERPROFILE%\.local\bin`, winget). Gdy brak, instaluje go
   oficjalnym instalatorem Astral, a w razie niepowodzenia przez `winget install astral-sh.uv`.
2. `uv sync --no-dev`: uv sam pobiera Pythona zgodnego z `requires-python` (>=3.12) i składniki. Python nie musi być zainstalowany.
3. Wybiera port: `HN_PORT` (domyślnie 8000, tak samo jak w `Makefile` i `python -m app`); gdy zajęty, kolejny wolny.
4. Uruchamia `uvicorn app.main:app` na 127.0.0.1, czeka do 60 s na `/health`, otwiera przeglądarkę.
5. Ustawia `PYTHONUTF8=1`. Przy długiej ścieżce (ponad 90 znaków) środowisko Pythona trafia do `%LOCALAPPDATA%\ChronPlon\venv`.

Ręcznie, bez skryptu: `uv sync --no-dev`, potem `uv run --no-dev python -m app` (port: `HN_PORT`).
Pliki `start.bat` i `start.ps1` mają być czystym ASCII (`start.bat` z końcami linii CRLF).
Zatrzymanie: Ctrl+C. Wymagany internet. Nie testowano na prawdziwym Windows (tylko analiza statyczna i emulacja na Linuxie).
