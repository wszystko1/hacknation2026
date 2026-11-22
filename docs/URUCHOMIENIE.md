# Uruchomienie ChrońPlon krok po kroku

Aplikacja działa na własnym komputerze, w przeglądarce. Nie potrzeba Pythona, `make` ani wiedzy technicznej.
Wymagany jest internet (pierwszy start pobiera ok. 450 MB składników, a raport pobiera dane o działce) i ok. 1 GB wolnego miejsca.

## Windows 10 i 11

1. Na stronie repozytorium w GitHubie kliknąć zielony przycisk **Code**, potem **Download ZIP**.
2. **Odblokowanie (zalecane, unika ostrzeżeń):** w Pobranych kliknąć plik ZIP prawym przyciskiem, **Właściwości**, na dole zaznaczyć **Odblokuj**, **OK**.
3. Kliknąć ZIP prawym przyciskiem, **Wyodrębnij wszystko…**, najlepiej do krótkiej ścieżki, np. `C:\ChronPlon`
   (ścieżka bez spacji i polskich znaków oraz krótka: Windows ma limit 260 znaków). Nie uruchamiać plików z podglądu wewnątrz ZIP.
4. Wejść do rozpakowanego folderu, potem do `deploy\windows` i dwukrotnie kliknąć **`start.bat`**.
5. Jeśli pojawi się niebieskie okno **„Windows zabezpieczył ten komputer”**: kliknąć **Więcej informacji**, potem **Uruchom mimo to**.
   (Okno „Otwórz plik – ostrzeżenie zabezpieczeń”: **Uruchom**.)
6. Otworzy się czarne okno z komunikatami. Przy pierwszym starcie trwa kilka minut (instalacja programu `uv`, Pythona i składników).
   Okna nie zamykać. Jeśli Zapora Windows zapyta o zgodę: **Zezwól** (aplikacja nasłuchuje tylko na tym komputerze).
7. Gdy w oknie pojawi się zielony napis **„Gotowe. Aplikacja działa pod adresem http://127.0.0.1:8000/”**, sama otworzy się przeglądarka
   z formularzem (przykładowa działka jest już wpisana). Gdyby się nie otworzyła, wpisać ten adres w przeglądarce ręcznie.
8. **Zatrzymanie:** w czarnym oknie nacisnąć **Ctrl+C** (przy pytaniu o zakończenie zadania wsadowego wpisać `T` albo `Y`) lub zamknąć okno.
   Kolejne uruchomienia trwają kilka sekund.

### Najczęstsze problemy (Windows)

| Objaw | Przyczyna i rozwiązanie |
|---|---|
| „Windows zabezpieczył ten komputer” | Plik z internetu. **Więcej informacji → Uruchom mimo to**; albo odblokować ZIP (krok 2) i rozpakować ponownie |
| „Nie znaleziono plików aplikacji (pyproject.toml)” | `start.bat` uruchomiono z podglądu ZIP. Rozpakować cały ZIP (**Wyodrębnij wszystko**) |
| „Nie udało się zainstalować programu uv” | Brak internetu lub komputer firmowy blokuje instalator. Pobrać `uv-x86_64-pc-windows-msvc.zip` z https://github.com/astral-sh/uv/releases/latest, wypakować `uv.exe` do głównego folderu aplikacji (obok `pyproject.toml`) i uruchomić `start.bat` jeszcze raz. Alternatywa: w wierszu poleceń `winget install astral-sh.uv` |
| „Instalacja składników nie powiodła się” | Brak internetu, proxy firmowe, antywirus albo mało miejsca. Sprawdzić internet (potrzebne: pypi.org, github.com, astral.sh), przenieść folder do `C:\ChronPlon`, uruchomić ponownie (skrypt wznawia od miejsca przerwania) |
| „Port 8000 jest zajęty” | Skrypt sam wybiera kolejny wolny port i wypisuje go w oknie. Własny port: w wierszu poleceń `set HN_PORT=9000`, potem `start.bat` |
| Okno zamyka się od razu | Uruchomić `start.bat` z wiersza poleceń (Windows+R, `cmd`, przeciągnąć plik do okna, Enter) i przeczytać komunikat |
| Brak `vcomp140.dll` lub `msvcp140.dll` | Zainstalować „Microsoft Visual C++ Redistributable x64”: `winget install Microsoft.VCRedist.2015+.x64` lub ze strony Microsoftu, potem uruchomić ponownie |
| Strona się nie otwiera po „Gotowe” | Wpisać ręcznie adres z okna. Jeśli przeglądarka pokazuje błąd połączenia, sprawdzić, czy czarne okno nadal jest otwarte |
| Raport nie pobiera danych | Brak internetu lub chwilowa awaria usług publicznych (ULDK GUGiK, IMGW). Spróbować za kilka minut; demo na zapisanych danych dwóch działek działa bez sieci |
| Skrypty PowerShell zablokowane przez administratora | `start.bat` czyta skrypt jako tekst i omija blokadę zwykłej polityki. Gdy administrator blokuje także to, potrzebna zgoda działu IT |

## Linux i macOS

1. Pobrać repozytorium (**Code → Download ZIP** i rozpakować, albo `git clone`).
2. W terminalu wejść do folderu aplikacji i uruchomić: `./start.sh`
   (gdy brak prawa wykonywania: `bash start.sh`).
3. Skrypt instaluje `uv` (jeśli brak), składniki i Pythona, uruchamia serwer, czeka na gotowość i otwiera przeglądarkę.
   Adres: http://127.0.0.1:8000/ . Inny port: `HN_PORT=8797 ./start.sh`.
4. Zatrzymanie: **Ctrl+C** w terminalu.

Szczegóły techniczne (bez `make` na Windows, wersja serwerowa): `deploy/windows/README.md`, `docs/DEPLOY.md`.
