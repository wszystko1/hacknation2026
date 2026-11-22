# ChrońPlon

Aplikacja webowa „Zatrzymaj wodę, chroń plony” dla jednej działki rolnej. Rolnik wpisuje numer działki z ewidencji (albo klika pole na mapie),
datę i uprawę. ChrońPlon liczy bilans wody działki (opad minus parowanie), stawia go obok progu suszy z rozporządzenia i obok oceny SMSR
dla gminy, pokazuje przyczyny i działania „rozważ …” z miejscem na ortofotomapie, a raport zawiera zakładkę Wiarygodność z miarami zgodności.

To nie jest urzędowe stwierdzenie suszy. Urzędową ocenę suszy w gminie publikuje IUNG (SMSR).

## Uruchomienie

| Środowisko | Kroki |
|---|---|
| Windows, bez `make` (potrzebny [uv](https://docs.astral.sh/uv/)) | `uv sync`, potem `uv run python -m app` (równoważnie `uv run uvicorn app.main:app`); adres: http://127.0.0.1:8000. Skrypt `deploy\windows\start.bat` robi to samo i otwiera przeglądarkę (opis: `deploy/windows/README.md`) |
| Linux, macOS | `make setup`, `make serve`; testy: `make test` |
| Serwer (VPS) | `deploy/deploy.sh <IP>`; kroki, logi i koszty: [docs/DEPLOY.md](docs/DEPLOY.md) |
| Inny port | zmienna `HN_PORT`, np. `HN_PORT=8797 make serve` |

Formularz startowy ma wpisaną przykładową działkę, datę i uprawę. Demo bez sieci, na kopii danych dwóch działek z 21.11.2026: `make demo`
(scenariusz: [docs/DEMO.md](docs/DEMO.md)). Na żywo aplikacja pobiera dane dla dowolnej działki, kopia stoi w `demo/data/`.

## Jak to działa

| Krok | Co się dzieje | Gdzie |
|---|---|---|
| Dane | obrys działki (ULDK), pogoda (IMGW, zapas NASA POWER), gleba (mapa IUNG, zapas SoilGrids), teren (NMT GUGiK), rowy (BDOT10k), zdjęcia Sentinel-2 | `app/geodata/` |
| Bilans | opad minus parowanie (FAO-56; drugi wariant: Doroszewski–Górski) w oknie 6 dekad kończącym się na ostatniej pełnej dekadzie | `app/drought/` |
| Próg | próg z Dz.U. 2019 poz. 739: 14 grup upraw, kategorie gleby I–IV, 14 okresów | `app/drought/progi_dz_u_2019_739.csv` |
| Trzy odpowiedzi | werdykt (bilans wobec progu), stan roślin (NDVI działki wobec jej własnych sezonów), podatność (ile z 10 sezonów byłoby pod progiem); bez jednej sklejonej liczby | `app/drought/`, `app/crop_condition/`, `app/vulnerability/` |
| Przyczyny | przyczyna z osią i dowodem liczbowym (pogoda z rankingiem w mm; miejsce i uprawa bez rankingu) | `app/advice/diagnosis.py` |
| Działania | 26 działań z katalogu CSV (źródło, strona, cytat), 9 mechanizmów, formalność z Prawa wodnego; miejsce z modelu terenu: płaszczyzna metodą najmniejszych kwadratów, najniższy punkt granicy, zagłębienia, rów z BDOT10k | `app/advice/` |
| Prognoza | szansa, że do końca okresu krytycznego bilans spadnie pod próg: dopełnianie okna przebiegami z wcześniejszych lat, bez wag | `app/forecast/` |
| Zgodność z SMSR | porównanie z oceną IUNG dla gminy i miary zgodności w zakładce Wiarygodność | `app/validation/` |

Raport ma zakładki Podsumowanie, Przyczyny, Rekomendacje, Wiarygodność i „Jak liczymy”, plan z przełącznikiem „W planie” oraz PDF.
Ocenę bieżącą liczy rachunek i reguły, bez uczenia maszynowego. Raport nie podaje milimetrów wody odpływającej z działki.

## Dowody

Liczba główna: **krzywa kalibracji**. Gdy bilans działki leży co najmniej 25 mm poniżej progu, SMSR potwierdza suszę w 92,3% przypadków
(przedział 95%: 88,5–95,1%; 3799 symboli). Przy marginesie do 10 mm od progu zgodność to 55,2%, czyli rzut monetą, i raport mówi to wprost.
Próba: 149 gmin, 1017 gmino-lat (2020–2026), 566130 symboli „+” lub „-”; susza to 4,5% symboli.

**Czego nie zmierzono:** retencji, czasu raportu na 20 działkach, zgodności upraw z mapą JRC i zgodności na działkach (wiersze „nie zmierzone”).

| Stan | Co | Wartość | Gdzie w repo |
|---|---|---|---|
| zmierzone | krzywa kalibracji: bilans ≥ 25 mm pod progiem | 92,3% potwierdzeń SMSR (88,5–95,1%) | `smsr.confirm_share_margin_le_minus25`, `smsr.calibration` |
| zmierzone | zgodność przy marginesie 0–10 mm | 55,2% | `smsr.agreement_by_distance` |
| zmierzone | CSI wobec linii bazowych | 0,3699 (FAO-56) i 0,4599 (D–G) wobec klimatologii 0,0694 i NASA POWER 0,147 | `smsr.csi_*`, `smsr.baseline_csi_*` |
| zmierzone | trafność zrównoważona | 0,7039 (FAO-56), 0,7555 (D–G), klimatologia 0,5377 | `smsr.balanced_accuracy_*` |
| zmierzone | BSS prognozy przekroczenia progu | 0,2081 wobec częstości historycznej (0,1826–0,2329; 8000 przypadków) | `forecast.brier_skill` |
| zmierzone, słabe | czułość (POD): ile susz SMSR wskazano | 0,4133 (FAO-56), 0,5166 (D–G); precyzja alarmów 0,7789 | `smsr.pod`, `smsr.precision` |
| zmierzone, słabe | kategoria gleby z SoilGrids wobec mapy IUNG | 0,375; w granicach jednej kategorii 0,8958 (96 punktów) | `soil.category_agreement` |
| zmierzone, słabe | zgodność zależy od roku | CSI od 0,1103 (2025) do 0,4758 (2022) | `smsr.by_year` |
| zmierzone, słabe | przesunięcie progu o 53 mm | trafność zrównoważona 2026: 0,7727 → 0,9094; dopasowane do ocen IUNG, w werdykcie nieużyte | `smsr.balanced_accuracy_2026_shifted` |
| nie zmierzone | czas raportu na 20 działkach | pomiar w toku | brak `robustness.*` |
| nie zmierzone | retencja: punkt wypływu wobec rowów, niecka wobec zbiorników | brak; miejsca działań to kandydatury do weryfikacji w terenie, nie projekt | brak `retention.*` |
| nie zmierzone | zgodność upraw z mapą JRC | brak; mapa nie rozróżnia zbóż ozimych i jarych | brak `crop.rotation_agreement_jrc` |
| nie zmierzone | zgodność z SMSR na działkach | brak; pomiar jest na gminach | n/d |

Sama trafność nie jest miarą: susza to 4,5% przypadków, więc odpowiedź „zawsze bez suszy” trafia w 0,955. Dlatego liczą się krzywa
kalibracji, CSI i trafność zrównoważona, każda obok linii bazowej.

**Dwa warianty parowania** (te same gminy testowe; w werdykcie stoi FAO-56, bo wzór D–G pochodzi z postaci miesięcznej w publikacji IUNG 2023):

| Miara | FAO-56 | Doroszewski–Górski |
|---|---|---|
| CSI | 0,3699 | 0,4599 |
| POD (czułość) | 0,4133 | 0,5166 |
| FAR | 0,2211 | 0,1929 |
| Peirce | 0,4077 | 0,511 |
| trafność zrównoważona | 0,7039 | 0,7555 |

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

## Źródła danych i licencje

Pełna tabela z adresami, rozdzielczością i datami pobrania: [docs/DANE.md](docs/DANE.md).

| Źródło | Licencja |
|---|---|
| IMGW-PIB, dane dobowe | dane publiczne, z podaniem źródła |
| Open-Meteo (pogoda, prognoza) | CC BY 4.0, **tylko niekomercyjnie**; dzienny limit zapytań |
| NASA POWER | dane otwarte |
| GUGiK: ULDK, ortofotomapa, NMT, BDOT10k, EGiB WFS | dane publiczne |
| IUNG-PIB: SMSR, mapa kategorii gleby | dane IUNG-PIB, z podaniem źródła; warunków licencji mapy gleby nie ustalono |
| Sentinel-2 (Copernicus) | dane otwarte |
| SoilGrids (ISRIC) | CC BY 4.0 |
| JRC EUCROPMAP 2022 | CC BY 4.0 |

Przepisy i tabele: rozporządzenie Dz.U. 2019 poz. 739, Prawo wodne (Dz.U. 2026 poz. 1335), poradnik CDR 2025, FAO-56.

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
  Progi oznaczone „propozycja zespołu” nie mają źródła w poradniku CDR 2025.
- **Dane:** mapa upraw JRC jest tylko podpowiedzią; Open-Meteo działa bezpłatnie tylko niekomercyjnie; archiwum IMGW ma 1–2 miesiące opóźnienia.

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
