from datetime import date

import numpy as np
import pytest

from app.geodata import config, fetch_weather
from app.geodata.errors import CacheMiss
from app.geodata.et0 import et0_penman_monteith

TODAY = date(2026, 11, 21)


def test_penman_monteith_matches_the_fao56_worked_example():
    # FAO-56 example 18 (Uccle, 6 July): 3.9 mm/day with RH min/max; mean RH gives a slightly lower value.
    et0 = et0_penman_monteith(
        np.array([21.5]), np.array([12.3]), np.array([73.5]), np.array([2.078]), np.array([22.07]),
        np.array([187.0]), 50.8, 100.0,
    )  # fmt: skip
    assert et0[0] == pytest.approx(3.8, abs=0.25)


def test_archive_series_is_sliced_to_the_requested_day(net):
    result = fetch_weather(52.2, 21.0, date(2016, 12, 31), today=date(2017, 12, 5))
    data = result.data
    assert result.status == "ok" and data.provider == "open-meteo-archive"
    assert data.precipitation_provider == data.et0_provider == "open-meteo-archive"
    assert set(data.precipitation_sources) == {
        "open-meteo-archive",
        "missing",
    }  # the recording starts in Nov 2016
    assert data.dates[-1] == "2016-12-31"
    assert len(data.dates) == len(data.precipitation_mm) == len(data.et0_mm)
    assert data.precipitation_mm[data.dates.index("2016-11-01")] == 13.2
    assert "9 km" in result.resolution and result.source_url.startswith("https://archive-api.open-meteo.com")


def test_rate_limited_archive_falls_back_to_nasa_power(net):
    net.fail["archive-api"] = 429
    result = fetch_weather(52.1, 19.35, date(2026, 6, 20), today=TODAY)
    assert result.status == "fallback" and result.data.provider == "nasa-power"
    assert any("429" in note for note in result.notes)
    i = result.data.dates.index("2026-06-15")
    assert result.data.precipitation_mm[i] is not None
    assert 1.0 < result.data.et0_mm[i] < 8.0  # June day in central Poland
    assert net.count("archive-api") == 1  # no retries against a daily limit


def test_newest_days_are_filled_from_the_forecast_model(net):
    net.fail["archive-api"] = 429
    result = fetch_weather(52.1, 19.35, TODAY, today=TODAY)
    assert result.data.dates[-1] == TODAY.isoformat()
    assert result.data.precipitation_mm[-1] is not None and result.data.et0_mm[-1] is not None
    assert result.data.recent_filled_from != ""


def test_other_dates_of_the_same_place_come_from_the_cache(net):
    fetch_weather(52.2, 21.0, date(2017, 6, 1), today=date(2017, 12, 5))
    net.down = True
    again = fetch_weather(52.2004, 21.0003, date(2017, 3, 1), today=date(2017, 12, 5))
    assert again.from_cache and again.data.dates[-1] == "2017-03-01"


def test_stale_copy_is_served_when_refresh_fails(net):
    first = fetch_weather(52.2, 21.0, date(2017, 12, 5), today=date(2017, 12, 5))
    assert not first.from_cache
    net.down = True
    later = fetch_weather(52.2, 21.0, date(2017, 12, 5), today=date(2017, 12, 5))
    assert later.from_cache


def test_offline_without_cache_raises(net):
    config.set_offline(True)
    with pytest.raises(CacheMiss):
        fetch_weather(52.2, 21.0, date(2017, 6, 1), today=TODAY)
