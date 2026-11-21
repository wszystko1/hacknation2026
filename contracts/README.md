# Kontrakty

Wspólne interfejsy modułów raportu. Zmiana w tych plikach dotyka wszystkich modułów, więc robimy ją osobno,
przed zmianą modułów.

| Plik | Co ustala |
|---|---|
| `app/models.py` | modele danych (Pydantic): `ReportRequest`, `Report` i jego części, stałe teksty (plakietki, zastrzeżenie) |
| `contracts/api.md` | trasy HTTP, parametry, odpowiedzi i błędy |
| `contracts/pipeline.md` | kroki raportu: która funkcja, w którym module, co dostaje i co zwraca |
| `contracts/ui.md` | identyfikatory elementów strony, na których opierają się sceny demo i testy |
| `contracts/examples/` | przykładowe odpowiedzi `/api/raport` dla działek demo (wygenerowane z aplikacji) |

Zasady:
- moduł wypełnia tylko swoją część `ReportContext` i zwraca typ z `app/models.py`; nie zmienia cudzych części;
- funkcje z `contracts/pipeline.md` zachowują nazwę i sygnaturę; ciało wymienia właściciel modułu;
- liczby w odpowiedzi to liczby policzone przez aplikację albo odczytane z `metrics.json`; brak danych to stan
  `missing` z powodem, nigdy wymyślona wartość.
