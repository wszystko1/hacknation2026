"""Off-season summary: the norm is the median of the same calendar days in earlier years."""

from __future__ import annotations

from datetime import date, timedelta

from app.off_season import autumn_start_year, norm_from, rain_since_october
from tests.acceptance.helpers import GSM_TODAY, report


def _series(first: date, last: date, per_day: dict[int, float]) -> tuple[list[str], list[float]]:
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return [d.isoformat() for d in days], [per_day.get(autumn_start_year(d), 0.0) for d in days]


def test_norm_is_the_median_of_earlier_years_and_excludes_the_assessed_one() -> None:
    # 1.X-21.XI is 52 days; 2021: 1 mm a day, 2022: 2, 2023: 3, 2024: 10, 2026 (assessed): 100.
    dates, rain = _series(
        date(2021, 10, 1), date(2026, 11, 21), {2021: 1, 2022: 2, 2023: 3, 2024: 10, 2026: 100}
    )
    per_year = rain_since_october(dates, rain, date(2026, 11, 21))
    assert per_year[2021] == 52 and per_year[2022] == 104 and per_year[2023] == 156 and per_year[2024] == 520
    assert per_year[2026] == 5200
    norm, n = norm_from(per_year, 2026)
    assert n == 5  # 2025 has no rain days at 0 -> still a full window of zeros
    assert norm == 104  # median of 52, 104, 156, 520 and 0 (2025)


def test_too_few_earlier_years_give_no_norm() -> None:
    assert norm_from({2025: 50.0, 2026: 40.0}, 2026) == (None, 1)


def test_window_with_missing_days_is_skipped() -> None:
    dates, rain = _series(date(2024, 10, 1), date(2024, 11, 21), {2024: 1})
    keep = [i for i in range(len(dates)) if i % 2 == 0]
    per_year = rain_since_october([dates[i] for i in keep], [rain[i] for i in keep], date(2025, 11, 21))
    assert 2024 not in per_year


def test_report_sentence_matches_the_numbers() -> None:
    o = report(GSM_TODAY).off_season
    assert o is not None and o.rain_mm is not None and o.norm_mm is not None
    assert f"{round(o.rain_mm)} mm" in o.sentence and f"{round(o.norm_mm)} mm" in o.sentence
    assert f"z {o.n_years} lat" in o.sentence
