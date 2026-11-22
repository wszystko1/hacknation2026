# ChrońPlon: pytania jury i kod, który warto otworzyć

Sześć modułów, z których wynika to, co raport mówi rolnikowi. Każdy jest mały, typowany i ma testy w `tests/`.

| # | Moduł | Co robi | Testy |
|---|---|---|---|
| 1 | `app/drought/kbw.py`, `app/drought/progi_dz_u_2019_739.csv` | 14 okresów, klimatyczny bilans wody (KBW), próg, wynik; stany „poza okresem” i „brak progu”; okno do ostatniej pełnej dekady; parowanie FAO-56 albo Doroszewskiego–Górskiego (`app/drought/evaporation.py`, `variants.py`) | `tests/test_kbw_*.py`, `tests/test_thresholds.py`, `tests/test_evaporation.py` |
| 2 | `app/advice/rules.py`, `app/advice/catalog*.csv`, `app/advice/prawo_wodne.csv` | reguła = przyczyny i warunek → zdanie, liczby, termin, źródło, formalność; kolejność działań | `tests/test_rules.py`, `tests/test_catalog*.py`, `tests/test_legal.py` |
| 3 | `app/advice/diagnosis.py`, `app/advice/mechanisms.py`, `app/advice/terrain_model.py` | przyczyna z osią i dowodem → mechanizm → model terenu (zlewnia, odcinek wypływu, zagłębienia) | `tests/test_diagnosis.py`, `tests/test_mechanisms.py`, `tests/test_terrain_model.py` |
| 3a | `app/advice/placement.py` | płaszczyzna najmniejszych kwadratów, dolny odcinek granicy, najniższe punkty, zagłębienia, rów; miejsce działania albo „brak miejsca, bo …” | `tests/test_placement.py` |
| 4 | `app/validation/agreement.py` | tabela 2×2, trafność, trafność zrównoważona, czułość, precyzja, CSI, POD, FAR, Peirce, linie odniesienia | `tests/test_agreement.py` |
| 5 | `app/forecast/exceedance.py` | szansa przekroczenia progu do końca okresu krytycznego, dopełnianie przebiegami | `tests/test_forecast.py` |

## Modele i metody obliczeń

**Skąd liczba w werdykcie?** Z rachunku, bez uczenia maszynowego: opad minus parowanie w oknie 6 dekad (`app/drought/kbw.py`)
porównany z progiem z Dz.U. 2019 poz. 739 (`progi_dz_u_2019_739.csv`: 14 grup upraw × 4 kategorie gleby × 14 okresów). Test porównuje
CSV z rozporządzeniem. Nie ma wag do uczenia, więc nie ma wycieku danych.

**Dlaczego FAO-56, skoro wzór Doroszewskiego–Górskiego wypada lepiej?** Zmierzone są oba (`smsr.*_fao56`, `smsr.*_dg` w `metrics.json`,
tabela w README): CSI 0,3699 wobec 0,4599. Wzór D–G pochodzi z postaci miesięcznej w publikacji IUNG 2023, nie z tekstu oryginału, więc werdykt zostaje przy FAO-56.
Zmiana to jedna decyzja, kod jest za jednym parametrem.

**Skąd kategoria gleby?** Z mapy IUNG, gdy odpowiada dla punktu; inaczej reguła z uziarnienia SoilGrids (`app/soil/`). Zgodność reguły
z mapą jest zmierzona (96 punktów, 0,375; w granicach jednej kategorii 0,8958) i podana w README jako słaba.

**Dlaczego CSI, a nie sama trafność?** Susza to 4,5% przypadków, więc odpowiedź „zawsze nie” trafia w 0,955, a trafność samej metody różni się od niej o ok. 1,3 punktu.
CSI i trafność zrównoważona pomijają zgodne „bez suszy”. Obok stoją linie odniesienia (klimatologia, „zawsze susza”, siatka NASA POWER). Kod: `app/validation/agreement.py`.

**Jak liczone jest miejsce na działce?** `app/advice/placement.py`: płaszczyzna z = ax + by + c metodą najmniejszych kwadratów do wysokości
w obrysie, spadek = 100·√(a² + b²) %, kierunek = (−a, −b). Dolny odcinek granicy to ciągły fragment obrysu o najniższych wysokościach.
`app/advice/terrain_model.py` liczy z siatki z marginesem ok. 300 m zlewnię, odcinek wypływu i zagłębienia.

**Rozmieszczanie: podstawa, rozszerzenie, wybór pomiarem.** Podstawa to powyższa geometria. Rozszerzenia to akumulacja D8
(O'Callaghan i Mark 1984) i mediana NDMI z suchych okresów. Rozszerzenie zastępuje podstawę tylko po wygranej w sprawdzeniu miejsc
(`basin_method()` w `app/advice/placement.py` czyta `retention.*` z `metrics.json`). Sprawdzenia nie zmierzono, więc
w aplikacji stoi podstawa, a miejsca działań to kandydatury do weryfikacji w terenie, nie projekt. Rów jest w modelu terenu zagłębieniem,
więc przyszły wynik będzie optymistyczny.

## Prognoza przekroczenia progu

**Co liczy `forecast_exceedance`?** Bilans jest znany do dnia oceny. Resztę okresu dopełnia pogoda z tych samych dni kalendarza w każdym
wcześniejszym roku (pierwsze 16 dni prognozą Open-Meteo). Wynik to odsetek przebiegów z przekroczeniem progu. Zapisanych wag nie ma.
Dla daty z przeszłości rok analizy nie wchodzi do danych.

**Czy działa?** Walidacja krocząca na 200 gminach, 8000 przypadków, lata testowe 2016–2025, rok Y liczony z lat wcześniejszych:
BSS 0,2081 wobec częstości historycznej (przedział 95%: 0,1826–0,2329). Trzy podejścia: częstość historyczna (Brier 0,0705),
dopełnianie (0,0558), LightGBM (0,0583). LightGBM nie wygrał, więc nie ma go w aplikacji. Kod oceny: `scripts/eval_forecast.py`.

**Czego prognoza nie umie?** Czułość dla szansy od 50% to 0,3232: większość przekroczeń ma niższą szansę. Precyzja to 0,7187.

## Skąd biorą się rekomendacje

**Skąd działanie w raporcie?** Z jednego wiersza katalogu CSV (`app/advice/catalog.csv`, `catalog_retencja.csv`): 26 działań ze źródłem,
stroną, cytatem i poziomem pewności. Działanie pojawia się, gdy zachodzi jedna z jego przyczyn (`diagnosis.py`) i pasują warunki
(`rules.py`, `retention.py`). Bez przyczyny nie ma zalecenia.

**Skąd liczby w warunkach?** Progi z poradnika CDR 2025 mają numer strony i cytat (test `tests/test_catalog_quotes.py` sprawdza cytat
w PDF). Progi bez źródła mają poziom „propozycja zespołu” i raport tak je opisuje. Efekt działania jest podany tylko jako zakres
z literatury.

**Skąd formalność?** `app/advice/prawo_wodne.csv`: artykuł, cytat, strona PDF, data sprawdzenia. Gdzie ustawa nie rozstrzyga
(nowa zastawka w istniejącym rowie), raport pisze „sprawdź w Wodach Polskich”.

**Co z łańcuchem przyczyna → mechanizm → miejsce?** 9 mechanizmów w `app/advice/mechanisms.csv`: w sezonie trzeba potrzeby (z przyczyn)
ORAZ możliwości (z terenu), poza sezonem wystarcza możliwość. Miejsce liczy `placement.py`. Osobnych detektorów kandydatów
i walidacji (zlewnia ucięta, zlewnia zewnętrzna, blisko granicy) jeszcze nie ma; zlewnia ucięta przez siatkę jest tylko flagą
w modelu terenu.

**Czy raport obiecuje efekt w mm?** Nie. Nie podaje też milimetrów wody odpływającej z działki; współczynnika spływu dla pól uprawnych
ze źródłem brak.

## Jak czytać krzywą kalibracji

**Co pokazuje krzywa?** Dla klas odległości bilansu od progu (np. 25 mm i więcej pod progiem) odsetek symboli „+” w SMSR IUNG
(`smsr.calibration` w `metrics.json`, tabela w README). Krzywa powinna rosnąć w stronę bilansu pod progiem: w klasie −25 mm i niżej
SMSR potwierdza suszę w 92,3% przypadków (`smsr.confirm_share_margin_le_minus25`, przedział 88,5–95,1%, 3799 symboli), a blisko progu
(margines do 10 mm) zgodność to 55,2% (`smsr.agreement_by_distance`), czyli rzut monetą. Płaska krzywa znaczyłaby, że bilans nie niesie informacji. Przedziały pochodzą z bootstrapu po gminach.
Kod: `scripts/eval_smsr.py`, `app/validation/agreement.py`.

**Dlaczego baza to najmocniejsza linia?** CSI jest porównywane z najwyższym wynikiem z trzech prostych linii: „zawsze susza”, klimatologia gminy
i siatka NASA POWER (`smsr.baseline_csi_*`). CSI 0,3699 (FAO-56) i 0,4599 (D–G) stoją wobec klimatologii 0,0694 i siatki NASA POWER 0,147; przewaga `smsr.csi_gain_vs_baseline` to 0,2229 wobec siatki, która dziś wygrywa.
Słabsza linia zawyżałaby przewagę; wybór najmocniejszej jest uczciwszy i kod robi go sam (`strongest_baseline` w `scripts/eval_smsr.py`).

## Obrys działki: `uldk_guard.py` i kolejność źródeł

**Po co strażnik?** W sali ULDK może przekierować na atrapę (`integracja01.gugik.gov.pl/resp/uldk.php`) z nagłówkiem 4 GiB i nieskończonym
strumieniem. `app/geodata/uldk_guard.py` nie idzie za przekierowaniem, przyjmuje tylko host `uldk.gugik.gov.pl`, czyta strumień z limitem
rozmiaru i czasu, sprawdza kształt odpowiedzi, a po pierwszej atrapie omija ULDK na 5 minut. Testy: `tests/test_uldk_guard.py`.

**W jakiej kolejności szukamy obrysu?** `app/geodata/parcel.py`: kopia lokalna (50 działek i działki demo), ULDK przez strażnika,
EGiB WFS (`app/geodata/parcel_wfs.py`), a gdy nic nie odpowie, uczciwy komunikat. Zapas EGiB WFS nie był sprawdzony z sieci sali;
testy używają atrap HTTP.

## Najsłabsze miejsca (pytania, które warto zadać samemu)

| Pytanie | Odpowiedź |
|---|---|
| Ile susz z SMSR wskazuje metoda? | 41% (FAO-56) do 52% (D–G) (`smsr.pod`, `smsr.pod_dg`); gdy wskazuje, SMSR potwierdza w 78–81% (`smsr.precision`) |
| Czy gleba jest dobrze rozpoznana? | Reguła SoilGrids zgadza się z mapą IUNG w 37,5% przypadków (89,6% w granicach jednej kategorii); pierwszeństwo ma mapa IUNG |
| Jak długo trwa raport? | Pomiar na 20 działkach w toku; do czasu wyniku nie ma tu liczby |
| Czy miejsca działań są sprawdzone? | Nie: to kandydatury do weryfikacji w terenie, nie projekt; sprawdzenia trafności (`retention.*`) brak |
| Czy to jest urzędowa ocena suszy? | Nie. Urzędową ocenę suszy w gminie publikuje IUNG (SMSR); to zdanie stoi w raporcie |
