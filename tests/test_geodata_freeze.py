"""Freezing the demo copies: the 5% rule, the refusal, and the sources that a live request does not wait for."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app import datasource
from app.geodata import config, fetch_all, imgw, satellite
from app.geodata.freeze import FreezeRefused, check_seasons, freeze, season_gaps
from app.geodata.models import Weather

PID = "100403_2.0011.144"


def series(first: date, last: date, missing: set[date]) -> Weather:
    """A hand-made daily series (synthetic, for the test only): 1 mm of rain and 2 mm of ET0 a day."""
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return Weather(
        provider="test", latitude=51.0, longitude=19.0, dates=[d.isoformat() for d in days],
        precipitation_mm=[None if d in missing else 1.0 for d in days],
        et0_mm=[2.0] * len(days),
    )  # fmt: skip


def season_days(year: int, n: int) -> set[date]:
    return {date(year, 3, 21) + timedelta(days=i) for i in range(n)}


def test_season_gaps_count_days_of_21_march_to_30_september_only():
    w = series(date(2013, 1, 1), date(2023, 7, 20), {date(2020, 1, 5), *season_days(2020, 10)})
    gaps = season_gaps(w, date(2023, 7, 20))
    assert sorted(gaps) == list(range(2014, 2024))
    assert gaps[2020] == pytest.approx(10 / 194)  # January does not count, 10 days of the season do
    assert gaps[2023] == 0 and all(g == 0 for y, g in gaps.items() if y != 2020)


def test_last_season_ends_on_the_requested_day():
    w = series(date(2013, 1, 1), date(2023, 7, 20), {date(2023, 7, 21)})
    assert season_gaps(w, date(2023, 7, 20))[2023] == 0


def test_a_season_that_is_not_in_the_series_is_fully_missing():
    w = series(date(2016, 1, 1), date(2023, 7, 20), set())
    assert season_gaps(w, date(2023, 7, 20))[2014] == 1.0


def test_five_percent_of_a_season_is_the_limit():
    ok = series(date(2013, 1, 1), date(2022, 9, 30), season_days(2018, 9))  # 9 of 194 days = 4.6%
    check_seasons(ok, date(2022, 9, 30))
    bad = series(date(2013, 1, 1), date(2022, 9, 30), season_days(2018, 10))  # 10 of 194 days = 5.2%
    with pytest.raises(FreezeRefused, match="2018: 5.2%"):
        check_seasons(bad, date(2022, 9, 30))


def test_freeze_refuses_without_the_station_index_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(imgw, "load_index", lambda: None)
    with pytest.raises(FreezeRefused, match="imgw-sync"):
        freeze(directory=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_imgw_only_weather_does_not_ask_open_meteo_for_the_archive(net, monkeypatch):
    monkeypatch.setenv("GEODATA_WEATHER", "imgw")
    result = fetch_all(PID, "2016-12-31", sources=("weather",))
    assert net.count("archive-api") == 0
    assert any("GEODATA_WEATHER=imgw" in n for n in result.weather.notes)


def test_a_live_request_does_not_wait_for_the_satellite(net, monkeypatch):
    monkeypatch.setattr(config, "BACKGROUND_GRACE_S", 0.3)
    net.delay["earth-search"] = 2.0
    result = fetch_all(
        PID, "2016-12-31", budget_s=20, sources=("weather", "satellite"), background=("satellite",)
    )
    assert result.weather.usable and result.core_ok
    assert result.satellite.status == "timeout" and "w tle" in result.satellite.error
    assert result.total_ms < 1500


def test_seasonal_outlook_and_crop_hint_are_not_part_of_a_default_fetch(net):
    result = fetch_all(PID, "2016-12-31")
    assert result.seasonal.status == "skipped" and result.crop_hint.status == "skipped"
    assert net.count("seasonal-api") == 0


def test_live_load_has_a_25_s_limit_and_the_satellite_in_the_background(monkeypatch):
    seen = {}

    def spy(parcel_id, day, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(datasource, "fetch_all", spy)
    monkeypatch.setattr(datasource, "frozen_copy", lambda *_: None)
    with pytest.raises(RuntimeError):
        datasource.load("100403_2.0011.77", date(2022, 7, 1))
    assert seen["budget_s"] == 25.0
    assert seen["background"] == ("satellite",) and seen["history_years"] == 5


def test_one_scene_per_acquisition_is_tried():
    items = [
        {"id": "S2B_MSIL2A_20230721T094549_R079_T33UYV_20241019T210836", "date": "2023-07-21"},
        {"id": "S2B_MSIL2A_20230721T094549_R079_T33UYV_20230721T130000", "date": "2023-07-21"},
        {"id": "S2B_MSIL2A_20230714T094549_R079_T33UYV_20230714T130000", "date": "2023-07-14"},
    ]
    kept = satellite._one_per_acquisition(items)
    assert [i["date"] for i in kept] == ["2023-07-21", "2023-07-14"]
