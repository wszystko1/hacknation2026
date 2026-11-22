"""The exceedance forecast: completion with runs, the historical frequency, the states and the sentences."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from app.forecast import exceedance
from app.forecast.exceedance import (
    completed_run,
    in_season_chances,
    next_season_chance,
    own_weather_run,
    periods_after,
    skill_sentence,
)
from app.models import CropGroup
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, report

ROOT = Path(__file__).resolve().parents[1]
CROP, SOIL = CropGroup.ZBOZA_JARE, "III"


def season(years: range, rain: dict[int, float], et0: float = 5.0) -> dict[date, tuple[float, float]]:
    """Every day of the given years with a constant ET0 and a constant rain per year (mm/day)."""
    out = {}
    for y in years:
        d = date(y, 1, 1)
        while d.year == y:
            out[d] = (rain[y], et0)
            d += timedelta(days=1)
    return out


def test_dry_years_exceed_and_wet_years_do_not() -> None:
    rain = {y: (0.0 if y % 2 == 0 else 9.0) for y in range(2010, 2024)}
    daily = season(range(2010, 2024), rain)
    periods = periods_after(date(2023, 7, 1), CROP, SOIL)
    assert periods
    assert own_weather_run(daily, 2012, periods, CROP, SOIL) is True
    assert own_weather_run(daily, 2013, periods, CROP, SOIL) is False


def test_completion_uses_the_known_balance_and_the_weather_of_the_source_year() -> None:
    # The analysis year is dry until 1 July; a wet source year cannot rescue the periods that started dry,
    # a dry source year makes the run exceed. The run of source year 2013 sees the analysis year only up to the date.
    rain = {y: 9.0 for y in range(2010, 2024)} | {2023: 0.0, 2012: 0.0}
    daily = season(range(2010, 2024), rain)
    asof = date(2023, 7, 1)
    periods = periods_after(asof, CROP, SOIL)
    assert completed_run(daily, asof, 2012, periods, CROP, SOIL) is True
    wet = completed_run(daily, asof, 2013, periods, CROP, SOIL)
    dry_all_year = {d: v for d, v in daily.items()}
    assert wet is not None
    assert completed_run(dry_all_year, asof, 2013, periods, CROP, SOIL) == wet


def test_chances_count_only_earlier_years_and_ignore_the_rest_of_the_analysis_year() -> None:
    rain = {y: (0.0 if y % 3 == 0 else 6.0) for y in range(2005, 2024)}
    daily = season(range(2005, 2024), rain)
    asof = date(2023, 7, 1)
    years = list(range(2005, 2023))
    analog, own = in_season_chances(daily, asof, CROP, SOIL, years)
    assert own.years == tuple(years) and own.k == sum(1 for y in years if y % 3 == 0)
    poisoned = daily | {d: (500.0, 0.0) for d in daily if d > asof and d.year == 2023}
    poisoned |= {d: (0.0, 50.0) for d in daily if d.year > 2023}
    assert in_season_chances(poisoned, asof, CROP, SOIL, years) == (analog, own)


def test_the_forecast_overlay_replaces_the_analog_days() -> None:
    daily = season(range(2005, 2024), dict.fromkeys(range(2005, 2024), 6.0))
    asof = date(2023, 7, 1)
    periods = periods_after(asof, CROP, SOIL)
    overlay = {asof + timedelta(i): (0.0, 40.0) for i in range(1, 17)}
    plain = completed_run(daily, asof, 2010, periods, CROP, SOIL)
    forced = completed_run(daily, asof, 2010, periods, CROP, SOIL, overlay)
    assert plain is False
    assert forced is True


def test_next_season_chance_counts_seasons() -> None:
    rain = {y: (0.0 if y < 2012 else 8.0) for y in range(2005, 2020)}
    chance = next_season_chance(season(range(2005, 2020), rain), CROP, SOIL, list(range(2005, 2020)))
    assert (chance.k, chance.n) == (7, 15)


def test_skill_sentence_gives_accuracy_beside_the_majority_answer_and_no_jargon() -> None:
    metrics = {
        "forecast.accuracy": 0.93, "forecast.accuracy_majority": 0.91, "forecast.recall": 0.32,
        "forecast.precision": 0.72, "forecast.n_cases": 8000, "forecast.test_year_first": 2016,
        "forecast.test_year_last": 2025,
    }  # fmt: skip
    text = skill_sentence(metrics, "analog")
    assert "93%" in text and "91%" in text and "zawsze częstsza odpowiedź" in text
    assert "Brier" not in text and "BSS" not in text
    assert skill_sentence({}, "analog").startswith("Brak:")


def test_when_the_runs_lose_to_the_frequency_the_report_gives_the_frequency_and_says_so(monkeypatch) -> None:
    monkeypatch.setattr(exceedance, "_analog_loses", lambda metrics: True)
    f = report(DOBRCZ).forecast
    assert f.method == "historical"
    assert "częstość" in f.sentence and f"{f.k} z {f.n}" in f.sentence


def test_dobrcz_forecast_uses_only_earlier_years_and_shows_what_happened() -> None:
    f = report(DOBRCZ).forecast
    assert f.years_used and max(f.years_used) < 2023
    assert "okres 9" in f.what_happened and "10.08.2023" in f.what_happened


def test_next_season_frequency_has_earlier_years_only() -> None:
    f = report(GSM_TODAY).forecast
    assert f.method == "historical" and max(f.years_used) <= 2026
    assert f.n == len(f.years_used)


def test_the_app_keeps_no_model_and_reads_no_weights() -> None:
    metrics = json.loads((ROOT / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["forecast"]["gbdt_in_app"] is False
    for path in (ROOT / "app" / "forecast").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in ("lightgbm", "pickle", "joblib", "load_model", "open("):
            assert word not in text, f"{path.name} mentions {word}"
    report(DOBRCZ)
    assert "lightgbm" not in sys.modules


def test_a_validation_case_of_year_y_sees_nothing_from_years_y_or_later() -> None:
    spec = importlib.util.spec_from_file_location("eval_forecast", ROOT / "scripts" / "eval_forecast.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_forecast"] = module
    spec.loader.exec_module(module)
    rain = {y: (0.0 if y % 2 == 0 else 7.0) for y in range(2001, 2026)}
    daily = season(range(2001, 2026), rain)
    case = module.Case("0000000", 2016, date(2016, 7, 1), CROP, SOIL, 51.0, 17.0)
    clean = module.evaluate_case(daily, case)
    future = {d: (999.0, 0.0) if d.year >= 2016 and d > case.asof else v for d, v in daily.items()}
    future |= {d: (0.0, 80.0) for d in daily if d.year > 2016}
    seen = module.evaluate_case(future, case)
    assert clean[:2] == seen[:2]  # chances ignore the case year after the date and every later year
    assert clean[0] is not None
