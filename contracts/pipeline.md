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
- `app/advice/placement.py` (rozmieszczanie działań retencji, jeden wymienny moduł, numpy):
  - `PlacementInput(outline_2180, grid, lowest_outline_point_2180, water, slope_mean_pct)`; `grid` to siatka wysokości
    (`Terrain.grid`; do akumulacji `Terrain.catchment_grid` z marginesem ok. 300 m, gdy jest), `ElevationGrid.inside` = 1
    w obrysie;
  - podstawa: `fit_plane(grid) -> Plane` (`a`, `b`, `c`, `slope_pct` = 100 · √(a² + b²), `downhill_deg` = azymut wektora
    (−a, −b): 0 płn., 90 wsch., 180 płd., 270 zach.) z płaszczyzny z = ax + by + c dopasowanej metodą najmniejszych
    kwadratów do oczek w obrysie; `lower_edge(inp) -> LowerEdge` (`points_2180`: ciągły fragment obrysu z najniższymi
    wysokościami, punkty co krok siatki; `length_m`; `None`, gdy spadek płaszczyzny poniżej progu z katalogu);
    `lowest_boundary_point(inp)` i `lowest_interior_point(inp) -> [x, y] | None` liczone z siatki;
    `depressions(grid) -> list[[x, y]]` (oczka w obrysie niższe od wszystkich 8 sąsiadów);
  - `find_places(PlacementInput) -> list[PlaceCandidate]` (`kind`, `place: Place | None`, `reason`, `catchment_ha`,
    `length_m: float | None` dla „pas trawy”, `direction_deg: float | None` dla „uprawa w poprzek stoku”: kierunek orki
    i siewu jako azymut w [0, 180), prostopadły do kierunku spadku); rodzaje: „pas trawy” (dolny odcinek granicy;
    `place.description` ze słowem „rów”, gdy rów z BDOT10k biegnie przy tym odcinku), „uprawa w poprzek stoku”, „niecka”
    (najniższy punkt wnętrza albo zagłębienie), „zastawka” (tylko rów przy dolnym odcinku), oraz „punkt wypływu”, „rów”,
    „zbiornik”; progi (najmniejszy spadek dolnego odcinka, odległość rowu od odcinka, spadek dla uprawy w poprzek stoku)
    czytane z `app/advice/catalog_retencja.csv` (`load_catalog()`), nie z kodu; za mały spadek: brak „pas trawy” i `reason`
    ze słowem „spadek”; bez miejsca: `place=None` i `reason`;
  - rozszerzenie (zastępuje podstawę tylko po wygranej w sprawdzeniu miejsc): `runoff(PlacementInput) -> Runoff`: akumulacja
    D8 (O'Callaghan i Mark 1984) po wypełnieniu zagłębień; `outlets` i `inlets` (`list[BoundaryPoint]`: `x_2180`, `y_2180`,
    `catchment_ha`, malejąco po `catchment_ha`), `flow_lines` (`list[list[[x, y]]]` w EPSG:2180) i `reason`;
    `app/advice/wet_zones.py`: `wet_zones(satellite, weather, outline_2180) -> WetZones | None` (mediana NDMI w każdym pikselu
    działki ze scen bez chmur z suchych okresów; `wettest_boundary_2180`, `wettest_interior_2180`, `n_scenes`, `reason`);
  - `outlet_method() -> "lowest" | "d8" | "ndmi"`: wariant z najwyższym `retention.outlet_hit_lowest` / `_d8` / `_ndmi`
    w `metrics.json`; `basin_method() -> "lowest" | "d8" | "ndmi"`: to samo dla `retention.pond_auc_lowest` / `_d8` /
    `_ndmi`; remis: „lowest”, potem „d8”; bez kluczy: „lowest”; `retention.outlet_hit_share` i `retention.pond_auc` = wynik
    wybranego wariantu;
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

Siatka wysokości z marginesem (tylko do akumulacji D8 i jej sprawdzenia): `Terrain.catchment_grid: ElevationGrid | None`
(`app/geodata/models.py`): obrys działki plus ok. 300 m, jeden krok dla całej siatki (10 m; poza działką 20–30 m przy limicie
punktów i czasu); `inside` = 1 w obrysie; `Terrain.catchment_note` mówi, co pobrano; pobierana na żywo tylko, gdy
`outlet_method()` albo `basin_method()` zwraca „d8”, zawsze w `make eval`. `Terrain.grid` (w obrysie) wystarcza podstawie.

Kontekst dla mapy i sekcji (ustawia `retention_actions`): `ctx.slope_pct`, `ctx.downhill_deg` (strzałka kierunku spadku,
`None` przy za małym spadku), `ctx.lower_edge_2180` (dolny odcinek granicy), `ctx.outlet_2180`, `ctx.outlet_catchment_ha`
(tylko wariant „d8”), `ctx.flow_2180` (tylko wariant „d8”), `ctx.runoff_reason` (zdanie o za małym spadku).

Identyfikatory działań (`Action.id`) z formalnością w Prawie wodnym: `zastawka-istniejaca`, `zastawka-nowa`,
`dreny-regulowany-odplyw`, `przebudowa-rowu`, `niecka-przy-wyplywie`, `pobor-wody-nawadnianie`; pozostałe działania
z katalogu mają własne stałe identyfikatory (małe litery, myślniki).

Metryki (`make eval` → `metrics.json`, zagnieżdżone po kropkach): `smsr.*` (`scripts/eval_smsr.py`), `soil.*`
(`scripts/eval_soil.py`), `forecast.*` (`scripts/eval_forecast.py`), `robustness.*` (`scripts/eval_parcels.py`), `retention.*`
(`scripts/eval_retention.py`: `place_or_reason_share`, `with_place_share`, `n_parcels`, `outlet_hit_lowest`, `outlet_hit_d8`,
`outlet_hit_ndmi`, `outlet_hit_random`, `outlet_hit_share`, `n_ditch_parcels`; `scripts/eval_ponds.py`: `pond_auc_lowest`,
`pond_auc_d8`, `pond_auc_ndmi`, `pond_auc`, `n_ponds`).
Każdy skrypt ma `run() -> dict[str, float | int]` z płaskimi kluczami; `scripts/evaluate.py` je scala.
Zgodność według odległości od progu: `smsr.agreement_by_distance.<koszyk>` z koszykami `0–10 mm`, `10–25 mm`, `25–50 mm`, `>50 mm`.
