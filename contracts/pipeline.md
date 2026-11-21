# Kroki raportu (`app/report.py`)

`build_report(req)` woła kroki po kolei; każdy dostaje `ReportContext` (`app/context.py`) z wynikami kroków wcześniejszych.
Wyjątek w kroku nie przerywa raportu: jego część dostaje stan braku z powodem. Nazw i sygnatur nie zmieniamy.

| # | Funkcja | Moduł | Czyta z kontekstu | Zwraca |
|---|---|---|---|---|
| 1 | `datasource.load(parcel_id, day)` | `app/datasource.py` | — | `(FetchResult, etykieta kopii albo None)` |
| 2 | `assess_soil(ctx)` | `app/soil/__init__.py` | `data.soil`, `parcel`, `request.soil_override` | `SoilInfo` |
| 3 | `assess(dates, precip, et0, day, crop, soil)` | `app/drought/kbw.py` | `data.weather`, `soil.category` | `Verdict` |
| 4 | `smsr_row(ctx)` | `app/smsr/__init__.py` | `parcel.teryt_commune`, `verdict.period`, `soil` | `SmsrRow` (+ wiersz w `ctx.extra_sources`) |
| 5 | `assess_crop_condition(ctx)` → `compare(current, history, crop, day)` | `app/crop_condition/__init__.py` | `data.satellite` | `CropCondition` |
| 6 | `diagnose(ctx)` | `app/advice/diagnosis.py` | `verdict`, `soil`, `data.weather`, `data.terrain` | `Diagnosis` (pusta, gdy nie ma oceny) |
| 7 | `retention_actions(ctx)` | `app/advice/retention.py` | `diagnosis`, `runoff(...)`, `find_places(...)`, `legal_note(...)` | `list[Action]` grupy `retencja` (najwyżej 3); ustawia `ctx.flow_2180`, `ctx.outlet_2180`, `ctx.outlet_catchment_ha`, `ctx.runoff_reason` |
| 8 | `field_actions(ctx)` | `app/advice/rules.py` | `diagnosis`, `verdict`, `soil`, `data` | `list[Action]` grup `uprawa`, `nawadnianie` (najwyżej 3 na grupę) |
| — | `number_actions(...)` | `app/report.py` | — | numery 1..M (retencja pierwsza, w grupie kolejność z `rank_actions`), `in_plan` z `request.plan` |
| 9 | `forecast_exceedance(ctx)` | `app/forecast/exceedance.py` | `verdict`, `data.weather`, `data.forecast`, pliki modeli | `ExceedanceForecast` |
| 10 | `agreement_frame(metrics, margin_mm)` | `app/validation/agreement.py` | `metrics` (z `metrics.json`) | `Agreement` |
| 11 | `build(ctx)` w `app/sections/<id>.py` | po jednym module na sekcję 1–8 | wszystko wyżej | `Section` |
| 12 | `map_view(ctx)` | `app/mapview.py` | `data.ortho`, `data.terrain`, `actions` | `MapView` |
| 13 | `source_rows(ctx)` | `app/sources_table.py` | `data`, `extra_sources` | `list[SourceRow]` |

Funkcje pomocnicze z ustalonym wejściem i wyjściem (używają ich testy akceptacyjne):
- `app/drought/thresholds.threshold_mm(crop, soil, period) -> float | None`, tabela `app/drought/progi_dz_u_2019_739.csv`
  (`crop,soil_category,period,threshold_mm`; `-` i `x` jak w rozporządzeniu);
- `app/soil/texture.category_from_texture(sand_pct, silt_pct, clay_pct) -> (SoilCategory, SoilCategory | None)`:
  kategoria i sąsiednia kategoria, gdy uziarnienie leży blisko granicy klas;
- `app/smsr/parser.parse_commune_page(html) -> CommuneTable` z `.commune`, `.year`, `.symbol(crop_label, soil, period)`,
  `.area_share_pct(crop_label, period)`;
- `app/advice/placement.py` (analiza spływu, jeden wymienny moduł, numpy):
  - `PlacementInput(outline_2180, grid, lowest_outline_point_2180, water, slope_mean_pct)`; `grid` to siatka z marginesem
    ok. 300 m (`Terrain.catchment_grid`, gdy jest; inaczej `Terrain.grid`), `ElevationGrid.inside` = 1 w obrysie;
  - `runoff(PlacementInput, method: "d8" | "dinf" = "d8") -> Runoff`: zagłębienia płytsze niż ok. 0,2 m wypełnione, głębsze
    zostają; akumulacja D8 albo D-nieskończonością; `outlets` i `inlets` (`list[BoundaryPoint]`: `x_2180`, `y_2180`,
    `catchment_ha`, malejąco po `catchment_ha`), `flow_lines` (`list[list[[x, y]]]` w EPSG:2180, akumulacja powyżej progu)
    i `reason` (gdy spadek za mały: zdanie ze słowem „spadek”, `flow_lines == []`);
  - `stream_power_index(sca_m, slope_pct) -> float` = ln(sca_m × slope_pct / 100) (SPI jak w ACPF; SCA z D-nieskończoności,
    zlewnia na metr szerokości oczka);
  - `find_places(PlacementInput) -> list[PlaceCandidate]` (`kind`, `place: Place | None`, `reason`, `catchment_ha`,
    `length_m: float | None` = długość odcinka dla „rów zadarniony”); rodzaje miejsc: „rów zadarniony” (SPI powyżej progu
    z katalogu, odcinek ≥ `cond_length_min_m`), „pas konturowy” (nachylenie w `cond_slope_min_pct`–`cond_slope_max_pct`),
    „pas trawy”, „zastawka”, „niecka”, „uprawa w poprzek stoku”, oraz „punkt wypływu”, „rów”, „zbiornik”; progi rozmieszczania
    czytane z `app/advice/catalog_retencja.csv` (`load_catalog()`), nie z kodu; miejsca malejąco po `catchment_ha`; bez
    miejsca: `place=None` i `reason`;
  - `weir_count(length_m, slope_pct, head_m) -> int` = max(1, round(length_m × slope_pct / 100 / head_m));
  - `outlet_method() -> "d8" | "dinf" | "lowest"`: metoda z najwyższym `retention.outlet_hit_d8` /
    `retention.outlet_hit_dinf` / `retention.outlet_hit_lowest` w `metrics.json` (remis: „lowest”, potem „d8”; bez kluczy:
    „lowest”, punkt wypływu = najniższy punkt granicy); `retention.outlet_hit_share` = wynik tej metody;
- `app/advice/legal.legal_note(action_id) -> LegalNote` z `app/advice/prawo_wodne.csv`
  (`action_id,formality,article,quote,pdf_page,checked_on,extra`);
- `app/validation/agreement.confusion(pairs)`, `scores(table)`, `bucket_of(margin_mm)`; `scores` zwraca `accuracy`,
  `balanced_accuracy`, `recall`, `precision`, `accuracy_majority` (odpowiedź „zawsze częstsza odpowiedź”), `csi`, `pod`,
  `far`, `peirce`;
- katalog działań `app/advice/catalog*.csv` (`catalog_retencja.csv`, `catalog.csv`): `action_id, group, causes, cond_*,
  effect_low, effect_high, effect_unit, source_doc, source_page, source_quote, source_url, confidence, legal_article, term`;
  `causes` to kody `CauseCode` rozdzielone „;”, `confidence` ∈ {badanie, opinia ekspercka, propozycja zespołu}; wspólny
  czytnik `app/advice/catalog.py` (`load_catalog() -> dict[str, CatalogRow]`, `effect_text(row) -> str`: zakres z dopiskiem
  „literatura” tylko przy pełnym źródle, inaczej „”), `rank_actions(actions) -> list[Action]` (w grupie: liczba przyczyn,
  wykonalność od daty oceny, rolnik zrobi sam; najwyżej 3 na grupę).

Siatka wysokości do analizy spływu: `Terrain.catchment_grid: ElevationGrid | None` (`app/geodata/models.py`): obrys
działki plus ok. 300 m, jeden krok dla całej siatki: 5 m, gdy punkty w obrysie co 5 m i poza nim co 10 m mieszczą się
w limicie punktów i czasu (oczka poza pobranymi punktami interpolowane z siatki 10 m), inaczej 10 m, a gdy i to się nie mieści,
20–30 m; `inside` = 1 w obrysie; `Terrain.catchment_step_inside_m` i `Terrain.catchment_note` mówią, co pobrano;
`Terrain.grid` (gęsta, wokół działki) zostaje dla statystyk i profilu terenu.

Identyfikatory działań (`Action.id`) z formalnością w Prawie wodnym: `zastawka-istniejaca`, `zastawka-nowa`,
`dreny-regulowany-odplyw`, `przebudowa-rowu`, `niecka-przy-wyplywie`, `pobor-wody-nawadnianie`; pozostałe działania
z katalogu mają własne stałe identyfikatory (małe litery, myślniki).

Metryki (`make eval` → `metrics.json`, zagnieżdżone po kropkach): `smsr.*` (`scripts/eval_smsr.py`), `soil.*`
(`scripts/eval_soil.py`), `forecast.*` (`scripts/eval_forecast.py`), `robustness.*` (`scripts/eval_parcels.py`), `retention.*`
(`scripts/eval_retention.py`: `place_or_reason_share`, `outlet_hit_share`, `outlet_hit_lowest`, `outlet_hit_random`, `pond_auc`).
Każdy skrypt ma `run() -> dict[str, float | int]` z płaskimi kluczami; `scripts/evaluate.py` je scala.
Zgodność według odległości od progu: `smsr.agreement_by_distance.<koszyk>` z koszykami `0–10 mm`, `10–25 mm`, `25–50 mm`, `>50 mm`.
