# Pomiary jakości w jednym miejscu

Wszystkie liczby jakości są w `metrics.json`, a ich przeliczenie i objaśnienie uruchamia jedna komenda:

```
make jakosc                                     # tabela liczb + złote lokalizacje offline (ok. 30 s)
uv run python scripts/jakosc.py --online ADRES  # te same lokalizacje na działającej aplikacji
uv run python scripts/jakosc.py --przelicz      # przelicza pomiary od nowa (sieć, kilka minut)
make eval ONLY=<nazwa>                          # jeden pomiar, np. make eval ONLY=smsr
```

| Co sprawdza | Pomiar (`ONLY=`) | Skrypt | Klucze w `metrics.json` | Wynik | Czego nie dowodzi |
|---|---|---|---|---|---|
| Zgodność werdyktu z oceną państwa (SMSR) na gminach, krzywa kalibracji, CSI, czułość, precyzja | `smsr`, `period_variants` | `scripts/eval_smsr.py`, `scripts/eval_period_variants.py` | `smsr.*`, `smsr_variants.*` | 92,3% przy ≥ 25 mm pod progiem; 55,2% przy 0–10 mm; CSI 0,46 (D–G) i 0,37 (FAO-56); czułość 0,52 i 0,41, precyzja 0,81 | porównanie na gminach (149 gmin, 1017 gmino-lat), nie pomiar w polu |
| Przyczyny „mało opadu” i „duże parowanie” wobec suchych okresów SMSR i SPI-3 | `causes` | `scripts/eval_causes.py` | `causes.*` | zgodność flag z okresami suchymi | kontrola poczytalności, nie dowód przyczynowy |
| Prognoza przekroczenia progu (analogi wobec LightGBM) | `forecast` | `scripts/eval_forecast.py` | `forecast.*` | BSS 0,208 (analogi), 0,172 (LightGBM, nie użyty w aplikacji) | prognoza na historii, nie na przyszłości |
| Kategoria gleby z SoilGrids (zapas) wobec mapy IUNG | `soil`, `soil_sensitivity` | `scripts/eval_soil.py`, `scripts/eval_soil_sensitivity.py` | `soil.*`, `soil_sensitivity.*` | 37,5% dokładnie, 89,6% w granicach jednej kategorii (96 punktów) | dokładności mapy IUNG nie mierzono |
| Retencja: punkt odpływu przy rowie | `retention` | `scripts/eval_retention.py` | `retention.outlet_hit_*` | 50% wobec 25% losowo (50 działek) | rów jest zagłębieniem w tym samym modelu terenu (optymistyczne) |
| Retencja: niecka wobec rzeczywistych miejsc, w których zbiera się woda | (nie zmierzono) | — | — | brak mapy niecek na polach; miejsca w raporcie to kandydatury do sprawdzenia w terenie | — |
| Zastawki wobec rzeczywistych budowli | (nie zmierzono) | — | — | pilot BDOT10k nierozstrzygający (brak otwartych danych o zastawkach rolniczych) | — |
| Czas raportu na 20 działkach z 15 województw | `robustness` | `scripts/eval_robustness.py` | `robustness.*` | mediana 10,3 s, p95 25,9 s, 18 z 20 poniżej 30 s | zimny start, dane na żywo, zależne od usług zewnętrznych |
| Odmiana uprawy z Sentinel-2 wobec mapy JRC | `rotation` | `scripts/eval_rotation.py` | `crop.*` | nie zmierzono (mapa nie rozróżnia zbóż ozimych i jarych) | — |
| Ręcznie dobrane lokalizacje z oczekiwaniami eksperckimi | (testy) | `tests/golden/`, `scripts/golden_check.sh ADRES` | `docs/notes/golden-wynik-*.md` | 15 lokalizacji, znane wady oznaczone XFAIL z powodem | oczekiwania ekspertów, nie obserwacje w polu |

Skrypty `eval_*.py` zapisują do `metrics.json` tylko pod własnymi kluczami; jeśli brakuje pobranych danych, nic nie zmieniają. Dokładny opis każdej miary jest w nagłówku skryptu.
