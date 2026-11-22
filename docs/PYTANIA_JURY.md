# Pytania jury: kod, który warto otworzyć

Pięć modułów, z których wynika to, co raport mówi rolnikowi. Każdy jest mały, typowany i ma testy w `tests/`.

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

**Dlaczego FAO-56, skoro wzór Doroszewskiego–Górskiego wypada lepiej?** Mierzymy oba (`smsr.*_fao56`, `smsr.*_dg` w `metrics.json`,
tabela w README). Wzór D–G mamy z postaci miesięcznej w publikacji IUNG 2023, nie z tekstu oryginału, więc werdykt zostaje przy FAO-56,
a wariant D–G stoi w widoku doradcy. Zmiana to jedna decyzja, kod jest za jednym parametrem.

**Skąd kategoria gleby?** Z mapy IUNG, gdy odpowiada dla punktu; inaczej reguła z uziarnienia SoilGrids (`app/soil/`). Zgodność reguły
z mapą mierzymy (96 punktów, 0,375; w granicach jednej kategorii 0,8958) i podajemy w README.

**Dlaczego CSI, a nie sama trafność?** Susza to ok. 4,5% przypadków, więc odpowiedź „zawsze nie” trafia w 0,955. CSI i trafność
zrównoważona pomijają zgodne „bez suszy”. Obok stoją linie odniesienia (klimatologia, „zawsze susza”). Kod: `app/validation/agreement.py`.

**Jak liczymy miejsce na działce?** `app/advice/placement.py`: płaszczyzna z = ax + by + c metodą najmniejszych kwadratów do wysokości
w obrysie, spadek = 100·√(a² + b²) %, kierunek = (−a, −b). Dolny odcinek granicy to ciągły fragment obrysu o najniższych wysokościach.
`app/advice/terrain_model.py` liczy z siatki z marginesem ok. 300 m zlewnię, odcinek wypływu i zagłębienia.

**Rozmieszczanie: podstawa, rozszerzenie, wybór pomiarem.** Podstawa to powyższa geometria. Rozszerzenia to akumulacja D8
(O'Callaghan i Mark 1984) i mediana NDMI z suchych okresów. Rozszerzenie zastępuje podstawę tylko po wygranej w sprawdzeniu miejsc
(`basin_method()` w `app/advice/placement.py` czyta `retention.*` z `metrics.json`). Sprawdzenia jeszcze nie zmierzyliśmy, więc
w aplikacji stoi podstawa. Rów jest w modelu terenu zagłębieniem, więc taki wynik będzie optymistyczny.

## Prognoza przekroczenia progu

**Co liczy `forecast_exceedance`?** Znamy bilans do dnia oceny. Resztę okresu dopełniamy pogodą z tych samych dni kalendarza w każdym
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
w PDF). Progi bez źródła mają poziom „propozycja zespołu” i widok doradcy tak je opisuje. Efekt działania podajemy tylko jako zakres
z literatury.

**Skąd formalność?** `app/advice/prawo_wodne.csv`: artykuł, cytat, strona PDF, data sprawdzenia. Gdzie ustawa nie rozstrzyga
(nowa zastawka w istniejącym rowie), raport pisze „sprawdź w Wodach Polskich”.

**Co z łańcuchem przyczyna → mechanizm → miejsce?** 9 mechanizmów w `app/advice/mechanisms.csv`: w sezonie trzeba potrzeby (z przyczyn)
ORAZ możliwości (z terenu), poza sezonem wystarcza możliwość. Miejsce liczy `placement.py`. Osobnych detektorów kandydatów
i walidacji (zlewnia ucięta, zlewnia zewnętrzna, blisko granicy) jeszcze nie ma; zlewnia ucięta przez siatkę jest tylko flagą
w modelu terenu.

**Czy raport obiecuje efekt w mm?** Nie. Nie podaje też milimetrów wody odpływającej z działki; współczynnika spływu dla pól uprawnych
ze źródłem nie mamy.
