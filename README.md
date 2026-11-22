# ChrońPlon

**Zespół:** Freesolo · **Tytuł rozwiązania:** ChrońPlon, aplikacja do zadania „Zatrzymaj wodę, chroń plony” (KOWR, HackNation 2026)
· **Wersja online:** https://70-34-247-151.sslip.io/

Aplikacja webowa dla jednej działki rolnej. Rolnik wpisuje numer działki z ewidencji (albo klika pole na mapie),
datę i uprawę. ChrońPlon liczy bilans wody działki (opad minus parowanie), stawia go obok progu suszy z rozporządzenia i obok oceny SMSR
dla gminy, pokazuje przyczyny i działania „rozważ …” z miejscem na ortofotomapie, a raport zawiera zakładkę Wiarygodność z miarami zgodności.

To nie jest urzędowe stwierdzenie suszy. Urzędową ocenę suszy w gminie publikuje IUNG (SMSR).

| | |
|---|---|
| Problem | dane o suszy są rozproszone i wymagają wiedzy GIS; rolnik nie dostaje odpowiedzi dla swojej działki, uprawy i dnia |
| Główne funkcje | wskazanie działki, ocena sytuacji wodnej na tle progu, przyczyny, miejsca i sposoby retencji, plan działań, raport do druku lub PDF |
| Sposób użycia danych | obrys, pogoda z 10 lat, gleba, teren, rowy i zdjęcia Sentinel-2 pobiera aplikacja przy zapytaniu; wynik liczy rachunek na tych danych (sekcja „Wynik liczy aplikacja”) |
| Korzyść dla rolnika | jedna strona zamiast kilku serwisów: czy jest niedobór, dlaczego, co zrobić i ile jest to pewne |

## Uruchomienie

Instrukcja krok po kroku dla osoby bez doświadczenia (Windows: dwa kliknięcia na `deploy\windows\start.bat`; Linux i macOS: `./start.sh`): [docs/URUCHOMIENIE.md](docs/URUCHOMIENIE.md).

Wymagany jest [uv](https://docs.astral.sh/uv/) (sam pobiera Python 3.12 i zależności z `uv.lock`) oraz przeglądarka (Chrome, Firefox, Edge, Safari, Opera).
Adres po starcie: http://127.0.0.1:8000. Dane działki aplikacja pobiera z internetu; bez sieci działają dwie działki z kopii (niżej).

**Linux i macOS**

```bash
git clone <adres repozytorium> && cd <katalog>
uv sync --no-dev                           # zależności produkcyjne (make setup robi to samo; bez Playwrighta)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   # albo: make serve
```

**Windows (PowerShell lub cmd, bez `make`)**

```powershell
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   # równoważnie: uv run python -m app
```

Skrypt `deploy\windows\start.bat` robi to samo i otwiera przeglądarkę (opis: `deploy/windows/README.md`; skryptów Windows nie testowano).

**Zmienne środowiskowe** (żadna nie jest wymagana; brak kluczy API i kont)

| Zmienna | Znaczenie |
|---|---|
| `HN_PORT` | port dla `python -m app` i `make serve` (domyślnie 8000); Linux/macOS: `HN_PORT=<port> make serve`, PowerShell: `$env:HN_PORT="<port>"` |
| `HN_LIVE_ONLY=1` | wersja online: kopia z `demo/data/` nigdy nie jest używana, także dla dwóch działek demo; dane z pamięci podręcznej na dysku lub z zapytań na żywo (ustawiana w `deploy/`; w `start.*` domyślnie nie) |
| `GEODATA_OFFLINE=1` | tryb offline: dane tylko z dysku (kopia demo i pamięć podręczna), bez zapytań do sieci |
| `GEODATA_CACHE_DIR` | katalog pamięci podręcznej (domyślnie `data/raw/geodata_cache`) |
| `GEODATA_WEATHER=imgw` | pogoda z archiwum IMGW zamiast Open-Meteo (wymaga indeksu `imgw-sync`) |
| `GEODATA_IMGW_DIR`, `GEODATA_STAC` | katalog archiwum IMGW; katalog Sentinel-2 (`planetary-computer` lub `earth-search`) |
| `CHRONPLON_VERDICT_PERIOD`, `CHRONPLON_VERDICT_ET` | wariant okresu (`current`, `worst`) i wzoru parowania (`fao56`, `dg`) w werdykcie; domyślnie `current` i `fao56` |

**Tryb offline z kopią danych.** Repozytorium zawiera kopię danych dwóch działek z 21.11.2026 (`demo/data/`: 040303_2.0002.189/13 na dzień 20.07.2023
i 100403_2.0011.144 na dzień 21.11.2026, wraz z kafelkami mapy). Dla tych działek i dat objętych kopią aplikacja używa kopii, a raport podaje etykietę
„kopia danych z <data>”. Bez sieci: `GEODATA_OFFLINE=1 uv run python -m app` (PowerShell: `$env:GEODATA_OFFLINE="1"; uv run python -m app`) albo `make demo`
(scenariusz: [docs/DEMO.md](docs/DEMO.md)). Dla każdej innej działki w trybie offline raport pokaże braki danych wprost. Opcjonalnie, dla zapasu
pogody z IMGW: `uv run python -m app.geodata imgw-sync` (jednorazowo, ok. 22 MB, poza repozytorium).

Pozostałe: `make test` (pytest), `make lint`, serwer VPS: `deploy/deploy.sh <IP>` ([docs/DEPLOY.md](docs/DEPLOY.md)). Formularz startowy ma wpisaną
przykładową działkę, datę i uprawę.

## Dane na żywo a kopia

Wersja online działa z `HN_LIVE_ONLY=1`: każda działka, także dwie działki demo, jest liczona z zapytań na żywo (lub z pamięci podręcznej na dysku po wcześniejszym zapytaniu), a kopia z `demo/data/` nie jest używana. Kopia służy tylko trybowi offline (`GEODATA_OFFLINE=1`, `make demo`) i testom; bez `HN_LIVE_ONLY` zachowanie jest takie jak dotąd. Po wdrożeniu `deploy/warm.sh` rozgrzewa dwie działki demo na żywo.

## Wersja demonstracyjna online

Adres działającej wersji: https://70-34-247-151.sslip.io/ (kroki, logi i koszty serwera: [docs/DEPLOY.md](docs/DEPLOY.md)).
Wersja online działa na żywo dla dowolnej działki w Polsce, bez logowania.

## Dostęp dla jury do repozytorium

Repozytorium jest prywatne, a dostęp dla jury zapewnia się według instrukcji opublikowanej na platformie konkursowej.

## Funkcje

Kolejność odpowiada zadaniu: najpierw ocena sytuacji wodnej działki, potem z niej wynikające rekomendacje; bez rozpoznania warunków działki raport nie podaje działań.

| Etap zadania | Co robi aplikacja | Gdzie |
|---|---|---|
| Wejście | numer działki ewidencyjnej (pełny albo „obręb numer”) lub klik na mapie; data analizy (dziś albo dzień z ostatnich 10 lat); uprawa z 14 grup rozporządzenia | `app/inputs.py`, `app/picker/` |
| 1. Ocena stanu wilgotności | bilans wody wobec progu suszy, stan roślin z NDVI Sentinel-2 wobec własnych sezonów działki, podatność w 10 sezonach pogody, prognoza przekroczenia progu | `app/drought/`, `app/crop_condition/`, `app/vulnerability/`, `app/forecast/` |
| 2. Retencja i agrotechnika | przyczyna niedoboru z dowodem liczbowym; działania z katalogu (źródło, strona, cytat); miejsce na działce z modelu terenu (spadek, najniższy punkt granicy, zagłębienia, rów z BDOT10k); formalność z Prawa wodnego | `app/advice/` |
| 3. Nawadnianie (opcjonalnie) | decyzja „teraz tak/nie” z bilansu wobec progu oraz dawka w mm i m³ (poradnik CDR 2025); precyzyjnego terminu z bilansu w strefie korzeni aplikacja nie liczy | `app/advice/rules.py`, `app/sections/nawadnianie.py` |
| Raport | zakładki Podsumowanie, Przyczyny, Rekomendacje, Wiarygodność, „Jak liczymy”; data i źródła danych z czasem pobrania; braki danych wprost; plan z przełącznikiem „W planie”; widok do druku (3 strony A4) i zapis do PDF z okna drukowania przeglądarki | `app/report.py`, `app/templates/` |

Przykładowe raporty: `docs/raporty/` (PDF, stan z chwili wygenerowania; raport przeliczony po zmianie metody może się różnić), zrzuty ekranu: `docs/img/readme/`.

## Architektura

```
przeglądarka (HTML, własny JS bez frameworka, htmx)  <->  FastAPI (app/main.py, szablony Jinja2, wykresy SVG po stronie serwera)
                                                              |
        orkiestrator danych app/geodata/  (równoległe zapytania z limitem czasu na źródło, pamięć podręczna na dysku, kopia demo)
              |             |              |             |              |              |
         ULDK/EGiB    Open-Meteo/IMGW   IUNG/SoilGrids  NMT GUGiK    BDOT10k       Sentinel-2
        (obrys)       /NASA POWER       (gleba)         (teren)      (rowy)        (NDVI, NDMI)
              \_____________________________ rachunek bez uczenia maszynowego ____________________________/
                 bilans i próg (drought) -> stan roślin, podatność, prognoza -> przyczyny -> działania i miejsca (advice) -> raport
```

Aplikacja nie ma bazy danych ani kont użytkowników: stan to pamięć podręczna plików (`GEODATA_CACHE_DIR`). Kafle mapy podaje serwer aplikacji
(przeglądarka nie łączy się z GUGiK). Opis metod i kodu: [docs/PYTANIA_JURY.md](docs/PYTANIA_JURY.md).

## Jak to działa

| Krok | Co się dzieje | Gdzie |
|---|---|---|
| Dane | obrys działki (ULDK), pogoda 10 lat (Open-Meteo, zapas IMGW i NASA POWER), gleba (mapa IUNG, zapas SoilGrids), teren (NMT GUGiK), rowy (BDOT10k), zdjęcia Sentinel-2 | `app/geodata/` |
| Bilans | opad minus parowanie (wzór Doroszewskiego–Górskiego jak w IUNG; FAO-56 do nawadniania i jako zapas bez temperatury lub usłonecznienia) w oknie 6 dekad kończącym się na ostatniej pełnej dekadzie | `app/drought/` |
| Próg | próg z Dz.U. 2019 poz. 739: 14 grup upraw, kategorie gleby I–IV, 14 okresów | `app/drought/progi_dz_u_2019_739.csv` |
| Trzy odpowiedzi | werdykt (bilans wobec progu), stan roślin (NDVI działki wobec jej własnych sezonów), podatność (ile z 10 sezonów byłoby pod progiem); bez jednej sklejonej liczby | `app/drought/`, `app/crop_condition/`, `app/vulnerability/` |
| Przyczyny | przyczyna z osią i dowodem liczbowym (pogoda z rankingiem w mm; miejsce i uprawa bez rankingu) | `app/advice/diagnosis.py` |
| Działania | 26 działań z katalogu CSV (źródło, strona, cytat), 9 mechanizmów, formalność z Prawa wodnego; miejsce z modelu terenu: płaszczyzna metodą najmniejszych kwadratów, najniższy punkt granicy, zagłębienia, rów z BDOT10k | `app/advice/` |
| Prognoza | szansa, że do końca okresu krytycznego bilans spadnie pod próg: dopełnianie okna przebiegami z wcześniejszych lat, bez wag | `app/forecast/` |
| Zgodność z SMSR | porównanie z oceną IUNG dla gminy i miary zgodności w zakładce Wiarygodność | `app/validation/` |

Raport ma zakładki Podsumowanie, Przyczyny, Rekomendacje, Wiarygodność i „Jak liczymy”, plan z przełącznikiem „W planie” oraz PDF.
Ocenę bieżącą liczy rachunek i reguły, bez uczenia maszynowego. Raport nie podaje milimetrów wody odpływającej z działki.

## Dowody

**Jakość jedną komendą.** `make jakosc` (albo `uv run python scripts/jakosc.py`) wypisuje na jednej stronie zmierzone liczby (zgodność z SMSR, CSI, czułość i precyzja, prognoza, gleba, retencja, czas raportu) wraz z tym, czego nie dowodzą, i uruchamia ręcznie dobrane „złote lokalizacje” (15 działek z oczekiwaniami eksperckimi; znane wady oznaczone XFAIL z powodem). Na działającej aplikacji: `uv run python scripts/jakosc.py --online https://ADRES`; przeliczenie pomiarów (sieć): `--przelicz`. Wszystkie pomiary, skrypty i ich ograniczenia w jednej tabeli: [docs/POMIARY.md](docs/POMIARY.md).


Liczba główna: **krzywa kalibracji**. Gdy bilans działki leży co najmniej 25 mm poniżej progu, SMSR potwierdza suszę w 92,3% przypadków
(przedział 95%: 88,5–95,1%; 3799 symboli). Przy marginesie do 10 mm od progu zgodność to 55,2%, czyli rzut monetą, i raport mówi to wprost.
Próba: 149 gmin, 1017 gmino-lat (2020–2026), 566130 symboli „+” lub „-”; susza to 4,5% symboli.

**Czego nie zmierzono:** zgodności miejsc zastawek z rzeczywistymi budowlami (brak otwartych danych), zgodności upraw z mapą JRC i zgodności na działkach (wiersze „nie zmierzone”).

| Stan | Co | Wartość | Gdzie w repo |
|---|---|---|---|
| zmierzone | krzywa kalibracji: bilans ≥ 25 mm pod progiem | 92,3% potwierdzeń SMSR (88,5–95,1%) | `smsr.confirm_share_margin_le_minus25`, `smsr.calibration` |
| zmierzone | zgodność przy marginesie 0–10 mm | 55,2% | `smsr.agreement_by_distance` |
| zmierzone | CSI wobec linii bazowych | 0,4599 (D–G, werdykt) i 0,3699 (FAO-56) wobec klimatologii 0,0694 i NASA POWER 0,147 | `smsr.csi_*`, `smsr.baseline_csi_*` |
| zmierzone | trafność zrównoważona | 0,7555 (D–G, werdykt), 0,7039 (FAO-56), klimatologia 0,5377 | `smsr.balanced_accuracy_*` |
| zmierzone | BSS prognozy przekroczenia progu | 0,2081 wobec częstości historycznej (0,1826–0,2329; 8000 przypadków) | `forecast.brier_skill` |
| zmierzone, słabe | czułość (POD): ile susz SMSR wskazano | 0,5166 (D–G), 0,4133 (FAO-56); precyzja alarmów 0,7789 | `smsr.pod`, `smsr.precision` |
| zmierzone, słabe | kategoria gleby z SoilGrids wobec mapy IUNG | 0,375; w granicach jednej kategorii 0,8958 (96 punktów) | `soil.category_agreement` |
| zmierzone, słabe | zgodność zależy od roku | CSI od 0,1103 (2025) do 0,4758 (2022) | `smsr.by_year` |
| zmierzone, słabe | przesunięcie progu o 53 mm | trafność zrównoważona 2026: 0,7727 → 0,9094; dopasowane do ocen IUNG, w werdykcie nieużyte | `smsr.balanced_accuracy_2026_shifted` |
| zmierzone | czas raportu na 20 działkach z 15 województw (zimny start, dane na żywo) | mediana 10,3 s, 95. percentyl 25,9 s; 18 z 20 poniżej 30 s (0,9); 2 działki bez pogody | `robustness.*` |
| zmierzone, słabe | retencja: najniższy punkt granicy leży do 30 m od rowu | 0,50 wobec 0,2456 dla losowego punktu granicy (50 działek z rowem; rów jest zagłębieniem w modelu terenu, więc wynik jest optymistyczny) | `retention.outlet_hit_lowest`, `retention.outlet_hit_random` |
| zmierzone, słabe | stawy z BDOT10k jako zastępnik niecek (mapy niecek na polach nie ma): prosta miara „o ile miejsce leży niżej niż teren w oknie 100 m” odróżnia stawy z BDOT10k od losowych miejsc poza nimi (to nie jest dokładnie reguła, którą aplikacja wskazuje nieckę; test jest łatwy, bo staw jest zagłębieniem w modelu terenu) | AUC 0,902 (124 zbiorniki); po dopasowaniu tła do położenia (ta sama wysokość ±2 m, 30–150 m od brzegu) 0,858 (przedział 0,826–0,886; `retention.pond_auc_matched`); reguła „dołka” użyta w aplikacji odróżnia stawy słabo (AUC 0,538; `retention.pond_auc_pit_rule`); optymistyczne | `retention.pond_auc_lowest` |
| nie zmierzone | zgodność miejsc zastawek z rzeczywistymi budowlami | pilot na BDOT10k (97 działek) nierozstrzygający: dane nie zawierają zastawek rolniczych; miejsca działań to kandydatury do weryfikacji w terenie | n/d |
| nie zmierzone | zgodność upraw z mapą JRC | brak; mapa nie rozróżnia zbóż ozimych i jarych | brak `crop.rotation_agreement_jrc` |
| nie zmierzone | zgodność z SMSR na działkach | brak; pomiar jest na gminach | n/d |

Sama trafność nie jest miarą: susza to 4,5% przypadków, więc odpowiedź „zawsze bez suszy” trafia w 0,955. Dlatego liczą się krzywa
kalibracji, CSI i trafność zrównoważona, każda obok linii bazowej.

**Dwa warianty parowania** (te same gminy testowe; w werdykcie stoi wzór D–G, bo daje wyższe CSI i niższy odsetek fałszywych alarmów; FAO-56 liczy dawki i terminy nawadniania):

| Miara | Doroszewski–Górski (werdykt) | FAO-56 |
|---|---|---|
| CSI | 0,4599 | 0,3699 |
| POD (czułość) | 0,5166 | 0,4133 |
| FAR | 0,1929 | 0,2211 |
| Peirce | 0,511 | 0,4077 |
| trafność zrównoważona | 0,7555 | 0,7039 |

**Miary jednym zdaniem**

| Miara | Znaczenie |
|---|---|
| trafność zrównoważona | średnia z odsetka trafionych susz i trafionych „bez suszy”; nie wygrywa jej odpowiedź „zawsze nie” |
| czułość (POD) | z ilu susz według SMSR wskazano suszę |
| precyzja | ile alarmów SMSR potwierdził |
| CSI | trafienia podzielone przez trafienia, chybienia i fałszywe alarmy; pomija zgodne „bez suszy” |
| FAR | odsetek alarmów, których SMSR nie potwierdził |
| Peirce | czułość minus odsetek fałszywych alarmów; 0 to brak umiejętności |
| Brier, BSS | średni kwadrat błędu prognozowanego prawdopodobieństwa; BSS = 1 − Brier / Brier częstości historycznej |

**Prognoza** (walidacja krocząca, 200 gmin, lata testowe 2016–2025): Brier 0,0558 dla dopełniania przebiegami (w aplikacji), 0,0705 dla
częstości historycznej, 0,0583 dla LightGBM; LightGBM nie wygrał, więc go w aplikacji nie ma. Kalibracja: `forecast.calibration`.

## Źródła i zakresy danych

Pełna tabela z adresami, rozdzielczością i ograniczeniami: [docs/DANE.md](docs/DANE.md). Stan na 22.11.2026.

| Kategoria zadania | Źródło | Zakres przestrzenny i czasowy |
|---|---|---|
| Przestrzenne (działka, użytkowanie, teren) | ULDK GUGiK (obrys, numer), EGiB WFS (zapas), ortofotomapa GUGiK, NMT GUGiK (wysokości), BDOT10k (rowy, cieki, zbiorniki), JRC EUCROPMAP 2022 (podpowiedź uprawy) | cała Polska; stan bieżący ewidencji; NMT próbkowany co 10 m w obrysie i w marginesie ok. 300 m; mapa upraw: jeden sezon, 10 m |
| Meteorologiczne | Open-Meteo (archiwum ERA5-Land, opad i ET0 FAO-56), IMGW-PIB (dane dobowe, zapas), NASA POWER (luki), Open-Meteo Forecast (16 dni) | 10 sezonów wstecz od daty analizy; siatka ok. 9 km (Open-Meteo), stacje IMGW, siatka ok. 50 km (NASA POWER) |
| Satelitarne | Sentinel-2 L2A (katalog STAC Planetary Computer; zapas: Earth Search): NDVI, NDMI z maską chmur | od 2.11.2016; 10 i 20 m; scena najbliższa dacie (okno 20 dni) i ta sama pora roku w 5 poprzednich sezonach |
| Glebowe | IUNG-PIB: kategoria gleby I–IV (warstwa `katgl_landuse2024`); zapas: SoilGrids (ISRIC) | cała Polska; mapa IUNG w punktach wewnątrz obrysu, SoilGrids 250 m |
| Hydrologiczne | BDOT10k (rowy, cieki, zbiorniki, oczka wodne), model terenu (zlewnia, spływ D8) | cała Polska, skala 1:10 000; nie wszystkie rowy polowe są w bazie |
| Odniesienie (ocena państwa) | SMSR IUNG, tabele gmin | gminy, lata 2020–2026; do porównania z wynikiem aplikacji |

## Dane na bieżąco a pobrane wcześniej

Wynik i rekomendacje liczy aplikacja na danych, które pobiera przy zapytaniu o działkę i datę. Przy powtórnym zapytaniu aplikacja korzysta z pamięci
podręcznej na dysku (ważność: obrys i ortofotomapa 30 dni, pogoda z ostatnich dni 6 godzin, scena satelitarna z ostatnich dni 12 godzin; dane archiwalne bez wygasania).
Raport podaje dla każdego źródła adres, godzinę i czas pobrania (zakładka „Jak liczymy”).

| Dane | Kiedy pobrane | Data |
|---|---|---|
| Obrys i numer działki, ortofotomapa, pogoda (10 lat, prognoza 16 dni), gleba, teren, rowy, sceny Sentinel-2 | na żywo przy zapytaniu o działkę (lub z pamięci podręcznej w podanych terminach) | dzień zapytania, widoczny w raporcie |
| Dwie działki demo (040303_2.0002.189/13, 100403_2.0011.144) | wcześniej, kopia w `demo/data/` używana zamiast zapytań (raport pisze „kopia danych z <data>”) | 21.11.2026 |
| Kafle mapy startowej i raportu | na żywo z GUGiK przez serwer aplikacji; dla obszaru demo kopia | dzień zapytania; kopia z 21.11.2026 |
| Indeks stacji i archiwum IMGW (zapas pogody) | wcześniej, jednorazowo komendą `imgw-sync`, poza repozytorium | indeks zbudowany 21.11.2026 |
| Progi suszy (Dz.U. 2019 poz. 739), katalog działań, formalności Prawa wodnego, współrzędne stacji IMGW | wcześniej, przepisane do plików w repozytorium (`app/drought/*.csv`, `app/advice/*.csv`, `app/geodata/data/`) | 21.11.2026 (Prawo wodne sprawdzone z tekstem tego dnia) |
| Tabele SMSR i pogoda 200 gmin do pomiaru zgodności (`make eval`) | wcześniej, `scripts/fetch_smsr.py`, `scripts/fetch_commune_weather.py`, poza repozytorium; nie biorą udziału w liczeniu raportu | 21.11.2026 |
| Wiersz SMSR dla gminy działki (porównanie w raporcie) | na żywo ze strony SMSR dla gminy i roku, z pamięcią podręczną; dla dwóch gmin demo kopia w `demo/data/smsr/` | dzień zapytania; kopia 21.11.2026 |

**Wynik liczy aplikacja, nie ma zaszytych wyników.** Werdykt jest bilansem (opad minus ET0 w oknie 6 dekad) z pobranych szeregów, porównanym z progiem z tabeli
rozporządzenia dla uprawy i kategorii gleby (`app/drought/kbw.py`, `thresholds.py`); stan roślin liczy NDVI z pikseli sceny w obrysie (`app/crop_condition/`);
podatność powtarza ten sam bilans na 10 sezonach pogody działki (`app/vulnerability/`); miejsca działań wynikają z wysokości terenu w obrysie
(`app/advice/placement.py`, `terrain_model.py`). W `app/` nie ma gotowych raportów ani wyników dla numerów działek; jedyne dane „na sztywno” to tabele przepisów
i katalog działań z cytatem źródła oraz kopia danych wejściowych dwóch działek demo, na której rachunek jest uruchamiany tak samo jak na danych z sieci.
Granica: w aplikacji historia satelitarna to 5 poprzednich sezonów (pogoda: 10).

## Biblioteki, komponenty, modele i usługi zewnętrzne

**Sztuczna inteligencja.** Aplikacja w działaniu nie wywołuje żadnego modelu językowego ani usługi AI i nie zawiera wytrenowanych modeli. Ocenę bieżącą liczy rachunek
i reguły. Jedyne uczenie maszynowe to LightGBM w skrypcie pomiarowym (`scripts/eval_forecast.py`), użyte do porównania z prognozą aplikacji; nie wygrało, więc w aplikacji go nie ma.
Kod i dokumentacja powstały z udziałem asystenta LLM jako narzędzia programistycznego; wyniki dla działek nie pochodzą od niego.

| Komponent | Rola | Licencja |
|---|---|---|
| FastAPI, Starlette, Uvicorn | serwer WWW | MIT, MIT, BSD-3-Clause |
| Jinja2, python-multipart | szablony, formularze | BSD-3-Clause, Apache-2.0 |
| httpx | zapytania do źródeł danych | BSD-3-Clause |
| NumPy | obliczenia na szeregach i rastrach | BSD-3-Clause (z komponentami 0BSD, MIT, Zlib, CC0) |
| pyproj, rasterio | układy współrzędnych (EPSG:2180), odczyt rastrów (NMT, Sentinel-2, JRC) | MIT, BSD-3-Clause |
| LightGBM | tylko pomiar prognozy (`make eval`) | MIT |
| htmx 2.0.4 (`app/static/htmx.min.js`) | doczytywanie sekcji raportu | 0BSD |
| Mapa (`app/static/pickmap.js`) | własny kod, bez biblioteki mapowej | MIT (licencja repozytorium) |
| Czcionki Inter, Geist, IBM Plex (`app/static/fonts/`) | interfejs, wbudowane w repozytorium | SIL OFL 1.1 |
| pytest, ruff, Playwright, pypdf (grupa dev) | testy, lint, scenariusz demo | MIT, MIT, Apache-2.0, BSD-3-Clause |
| uv | menedżer środowiska | Apache-2.0 lub MIT |

Wersje zależności są w `uv.lock`. Usługi zewnętrzne są wymienione w tabelach danych (nie wymagają kluczy ani kont).

## Licencje i warunki korzystania z danych

| Źródło | Licencja lub warunki |
|---|---|
| IMGW-PIB, dane dobowe | dane publiczne, z podaniem źródła |
| Open-Meteo (archiwum, prognoza) | CC BY 4.0, **tylko niekomercyjnie**; dzienny limit zapytań |
| NASA POWER | dane otwarte |
| GUGiK: ULDK, ortofotomapa, NMT, BDOT10k, EGiB WFS | dane publiczne, bezpłatne |
| IUNG-PIB: SMSR, mapa kategorii gleby | dane IUNG-PIB, z podaniem źródła; warunków licencji mapy gleby nie ustalono |
| Sentinel-2 (Copernicus), katalog STAC Planetary Computer | dane otwarte; dostęp przez anonimowy token SAS pobierany w locie, bez konta |
| SoilGrids (ISRIC) | CC BY 4.0 |
| JRC EUCROPMAP 2022 | CC BY 4.0, © Unia Europejska |

Przepisy i tabele: rozporządzenie Dz.U. 2019 poz. 739, Prawo wodne (Dz.U. 2026 poz. 1335), poradnik CDR 2025, FAO-56, katalog NWRM (szczegóły: docs/DANE.md).
Kod aplikacji: MIT (`LICENSE`). Źródła z licencją niekomercyjną (Open-Meteo) wymagają zmiany dostawcy lub planu przy użyciu komercyjnym (sekcja o kosztach).

## Uczciwe ograniczenia

- **Gleba:** zgodność reguły SoilGrids z mapą IUNG to 37,5% (89,6% w granicach jednej kategorii); kategorię bierze się z mapy IUNG, a regułę tylko jako zapas.
- **Czułość:** 41–52% susz z SMSR zostaje wskazanych (FAO-56 i D–G); większość susz jest pominięta, a alarmy potwierdzają się w 78–81%.
- **Zgodność** liczona na gminach, nie na działkach; wynik zależy od roku (CSI 0,1103–0,4758).
- **Czas raportu:** pomiar na 20 działkach w toku; do czasu wyniku nie podaje się czasu z sali.
- **Retencja:** miejsca działań to kandydatury do weryfikacji w terenie, nie projekt techniczny. Sprawdzenia trafności (punkt wypływu wobec rowów,
  niecka wobec zbiorników) brak: usługa ULDK zwracała błędne odpowiedzi i nie zebrano 50 działek z rowem. W aplikacji stoi podstawa
  (najniższy punkt granicy), a warianty D8 i NDMI do porównania (O'Callaghan i Mark 1984; patentu na te metody nie znaleziono,
  wyszukiwanie 21.11.2026) nie są w niej użyte. Przyszły wynik będzie optymistyczny: rów jest w modelu terenu zagłębieniem.
- **Lokalizacja i zgody** (Prawo wodne) trzeba zweryfikować na miejscu; nowelizacje poz. 1358 i 1156 nie były otwierane.
- **Obrys działki:** zapas EGiB WFS (gdy ULDK nie odpowiada) nie był sprawdzony z sieci sali; jego testy idą na atrapach HTTP. Kopia lokalna obejmuje 50 działek.
- **Parowanie:** wzór, którym IUNG liczy parowanie w SMSR, jest nieznany; zgodność mierzy się symbolami „+” i „-”, nie w mm.
- **Zlewnia** bywa ucięta przez siatkę (margines ok. 300 m); drenaż jest „nieznany”, więc regulator drenów to potencjał o niskiej pewności.
  Progi oznaczone „wartość orientacyjna” nie mają źródła w poradniku CDR 2025.
- **Przeglądarki i systemy:** scenariusz demo i testy przeglądarkowe biegną w Chrome (Playwright); Firefoxa, Edge, Safari i Opery nie sprawdzono. Skryptów Windows nie testowano.
- **Historia satelitarna:** 5 poprzednich sezonów (pogoda: 10 sezonów); zdjęcia z chmurami i działki bez czystej sceny w oknie dają raport bez oceny stanu roślin, z jawnym komunikatem.
- **Obciążenie:** brak ograniczeń szybkości i jednoczesnych raportów oraz rozmiaru pamięci podręcznej (sekcja Skalowanie, koszty i bezpieczeństwo).
- **Zapas pogody:** indeks IMGW leży poza repozytorium (`imgw-sync`); bez niego zapasem jest tylko NASA POWER (ok. 50 km).
- **Dane:** mapa upraw JRC jest tylko podpowiedzią; Open-Meteo działa bezpłatnie tylko niekomercyjnie; archiwum IMGW ma 1–2 miesiące opóźnienia.

## Skalowanie, koszty i bezpieczeństwo

**Stan prototypu (22.11.2026).** Każde źródło ma własny limit czasu (łącznie do 25 s na działkę), wyniki trafiają do pamięci podręcznej na dysku (terminy wyżej),
a gdy Open-Meteo odpowie limitem zapytań, pogodę przejmują IMGW i NASA POWER. Brak: ograniczenia szybkości zapytań, limitu jednoczesnych raportów i limitu rozmiaru pamięci podręcznej
(przegląd z 22.11.2026: `docs/notes/bezpieczenstwo-przeglad.md`; zimny raport zajmuje ok. 65 MB pamięci, więc ruch trzeba ograniczać). Czas raportu: test
`test_demo_parcel_report_in_under_30_s` (kopia danych); pomiar na 20 działkach z różnych województw w toku, do jego wyniku nie podaje się czasu dla działek spoza kopii.

| Co potrzeba dla wielu rolników | Rozwiązanie |
|---|---|
| Limity i dostępność źródeł | wspólna pamięć podręczna dla procesów, kolejkowanie żądań i limit jednoczesnych raportów, wyłącznik dla wolnych usług, wstępne grzanie pamięci dla gmin (`deploy/warm.sh`) |
| Aktualizacja danych | pogoda i prognoza odświeżane co kilka godzin, indeks IMGW co dzień, tabele SMSR co dekadę; dane archiwalne nie wygasają |
| Szybkość przy większym ruchu | wiele procesów za Caddy (`deploy/`), własny serwer kafli lub CDN zamiast przekazywania do GUGiK |
| Koszty | serwer VPS 2 vCPU / 4 GB: kilka euro miesięcznie ([docs/DEPLOY.md](docs/DEPLOY.md)); przy użyciu komercyjnym płatny plan Open-Meteo albo własne archiwum ERA5 (cena nieustalona); alternatywa bez opłat: IMGW i NASA POWER (`GEODATA_WEATHER=imgw`) |

Prototyp nie korzysta z żadnych płatnych usług ani warstw; rolnik nie instaluje oprogramowania i nie zakłada konta.

**Bezpieczeństwo.** Aplikacja nie ma kont ani sesji i nie zbiera danych osobowych (numer działki i data są tylko w nazwach plików pamięci podręcznej). Szablony Jinja2 mają
automatyczne unikanie znaków HTML, adresy źródeł są stałe w konfiguracji (wejście użytkownika trafia tylko do parametrów zapytań), odpowiedź ULDK jest sprawdzana (`app/geodata/uldk_guard.py`),
błędy źródeł nie ujawniają śladu stosu, a `make check-secrets` szuka kluczy w repozytorium; na serwerze Caddy wystawia HTTPS i nagłówki bezpieczeństwa.
Otwarte uwagi z przeglądu (limity zasobów, brak CSP) są opisane w notatce wyżej.

## Weryfikacja wyników i rekomendacji

| Co sprawdzono | Jak | Gdzie |
|---|---|---|
| Progi suszy | porównanie 784 komórek tabeli z tekstem rozporządzenia (wymaga `pdftotext`) | `uv run python -m app.drought.regulation_pdf`, `tests/test_thresholds.py` |
| Werdykt wobec oceny państwa | zgodność z SMSR na 149 gminach i 1017 gmino-latach, z krzywą kalibracji, przedziałami i liniami bazowymi; w raporcie zakładka Wiarygodność i etykieta pewności | `make eval ONLY=smsr`, `metrics.json`, sekcja Dowody |
| Przypadek wzorcowy | działka 040303_2.0002.189/13, 20.07.2023, zboża jare: bilans policzony z kopii danych i porównany z symbolem SMSR | `tests/acceptance/test_drought_assessment.py` |
| Działania | każde z cytatem i stroną źródła; test sprawdza cytat na wskazanej stronie PDF (po pobraniu źródeł) | `app/advice/catalog.csv`, `tests/test_catalog_quotes.py` |
| Prognoza | walidacja krocząca na 200 gminach, Brier i BSS wobec częstości historycznej | `forecast.*` w `metrics.json` |
| Liczby w dokumentacji | skrypt zgłasza liczbę w README, której nie ma w `metrics.json` lub `docs/DANE.md` | `make check-claims` |
| Samodzielnie przez jury | ten sam dzień i gmina w serwisie SMSR IUNG (https://susza.iung.pulawy.pl/), porównanie z werdyktem w raporcie | zakładka Wiarygodność |

Czego nie zweryfikowano: retencji (miejsca działań są kandydaturami do sprawdzenia w terenie), zgodności na działkach (pomiar jest na gminach), czasu na 20 działkach.
Liczby zgodności zależą od okresu werdyktu i wzoru parowania: wartości w README dotyczą okresu bieżącego (kończącego się w ostatniej pełnej dekadzie) i FAO-56 w werdykcie,
a D–G jest podany obok; bieżące liczby są w `metrics.json` (klucze `smsr.*_fao56` i `smsr.*_dg`).

## Odpowiedź na kryteria oceny

| Kryterium (waga) | Gdzie jest dowód |
|---|---|
| Wartość praktyczna (25%) | raport z działaniami „rozważ …”, miejscem na ortofotomapie i planem „W planie” (`docs/img/readme/`, `tests/acceptance/test_action_catalog.py`, `tests/acceptance/test_recommendations.py`) |
| Wykorzystanie danych i wiarygodność (25%) | pięć kategorii danych z licencjami (`docs/DANE.md`), próg z rozporządzenia sprawdzony z tekstem (`tests/test_thresholds.py`), zgodność z SMSR i ograniczenia w zakładce Wiarygodność (`metrics.json`, sekcje Dowody i Uczciwe ograniczenia) |
| Innowacyjność i potencjał (20%) | trzy osobne odpowiedzi zamiast jednej liczby, krzywa kalibracji i prognoza przekroczenia progu (`app/validation/`, `app/forecast/`), miejsce retencji z modelu terenu (`app/advice/terrain_model.py`), plan rozwoju w sekcji Skalowanie |
| Prostota obsługi (15%) | ekran startowy z mapą i jednym formularzem, wpisany przykład (`tests/acceptance/test_start_defaults.py`, `tests/acceptance/test_map_pick.py`), język bez żargonu (`tests/acceptance/test_plain_language.py`), układ na telefonie (`make ui-audit`) |
| Działający prototyp i jakość (15%) | uruchomienie z README i adresu https://70-34-247-151.sslip.io/, raport z kopii danych poniżej 30 s (`tests/acceptance/test_report_flow.py`), `make gate-fast`, `make demo`, wdrożenie (`docs/DEPLOY.md`), zgodność licencji (sekcja Licencje) |

## Struktura repozytorium i testy

| Ścieżka | Zawartość |
|---|---|
| `app/` | aplikacja FastAPI: `drought/` (bilans, próg), `advice/` (przyczyny, działania, teren), `forecast/`, `validation/`, `geodata/`, `templates/`, `static/` |
| `scripts/` | pobieranie danych i pomiar (`eval_*.py`, `evaluate.py` zapisuje `metrics.json`) |
| `tests/` | testy pytest (`tests/acceptance/` to testy kryteriów) |
| `demo/` | scenariusz demo (Playwright) i kopia danych dwóch działek |
| `deploy/` | wdrożenie na VPS i start na Windows |
| `docs/` | `DANE.md`, `DEMO.md`, `DEPLOY.md`, `PYTANIA_JURY.md` |

| Komenda | Co robi |
|---|---|
| `make test` | pytest |
| `make lint` | ruff |
| `make eval` | pomiar na danych z `data/raw/`, zapis `metrics.json` |
| `make demo` | scenariusz demo w przeglądarce bez interfejsu |
| `make gate-fast` | lint, testy, sprawdzenie tekstów i liczb w README, reguły interfejsu, demo |

Kod, o który jury może zapytać: [docs/PYTANIA_JURY.md](docs/PYTANIA_JURY.md).

## Licencja

MIT, plik `LICENSE`.
