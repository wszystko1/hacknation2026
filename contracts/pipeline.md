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
| 7 | `retention_actions(ctx)` | `app/advice/retention.py` | `diagnosis`, `find_places(...)`, `legal_note(...)` | `list[Action]` grupy `retencja` |
| 8 | `field_actions(ctx)` | `app/advice/rules.py` | `diagnosis`, `verdict`, `soil`, `data` | `list[Action]` grup `uprawa`, `nawadnianie` |
| — | `number_actions(...)` | `app/report.py` | — | numery 1..M (retencja pierwsza), `in_plan` z `request.plan` |
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
- `app/advice/placement.find_places(PlacementInput) -> list[PlaceCandidate]` (rodzaje: „punkt wypływu”, „rów”,
  „linia spływu”, „zbiornik”; bez miejsca: `place=None` i `reason`);
- `app/advice/legal.legal_note(action_id) -> LegalNote` z `app/advice/prawo_wodne.csv`
  (`action_id,formality,article,quote,pdf_page,checked_on,extra`);
- `app/validation/agreement.confusion(pairs)`, `scores(table)`, `bucket_of(margin_mm)`.

Identyfikatory działań (`Action.id`) z formalnością w Prawie wodnym: `zastawka-istniejaca`, `zastawka-nowa`,
`dreny-regulowany-odplyw`, `przebudowa-rowu`, `niecka-przy-wyplywie`, `pobor-wody-nawadnianie`; pozostałe działania
z katalogu mają własne stałe identyfikatory (małe litery, myślniki).

Metryki (`make eval` → `metrics.json`, zagnieżdżone po kropkach): `smsr.*` (`scripts/eval_smsr.py`), `soil.*`
(`scripts/eval_soil.py`), `forecast.*` (`scripts/eval_forecast.py`), `retention.*` i `robustness.*` (`scripts/eval_parcels.py`).
Każdy skrypt ma `run() -> dict[str, float | int]` z płaskimi kluczami; `scripts/evaluate.py` je scala.
Zgodność według odległości od progu: `smsr.agreement_by_distance.<koszyk>` z koszykami `0–10 mm`, `10–25 mm`, `25–50 mm`, `>50 mm`.
