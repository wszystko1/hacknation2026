# Uruchomienie na Windows (bez `make`)

1. Rozpakuj repozytorium (cały folder, nie sam `deploy`).
2. Kliknij dwukrotnie `deploy\windows\start.bat` (albo `powershell -ExecutionPolicy Bypass -File deploy\windows\start.ps1`).
3. Skrypt sprawdza `uv` (w razie braku instaluje go oficjalnym instalatorem), robi `uv sync --no-dev`,
   uruchamia serwer na `http://127.0.0.1:8000/` i otwiera przeglądarkę. Inny port: `set PORT=8785` przed startem.
4. Zatrzymanie: Ctrl+C w oknie. Wymagany dostęp do internetu (ULDK GUGiK, dane pogodowe). Nie testowane na Windows.
