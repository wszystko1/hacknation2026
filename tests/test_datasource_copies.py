"""The committed copies of the two demo parcels: complete weather, both outlook sources, no network needed."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import datasource
from app.geodata import list_samples, load_sample
from app.geodata.freeze import DEMO_TARGETS, MAX_MISSING_SHARE, season_gaps
from app.main import app
from app.models import Report
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, query

client = TestClient(app)
FIRST_SEASON = {"040303_2.0002.189/13": 2014, "100403_2.0011.144": 2017}


def _copy(target):
    return load_sample(target.parcel_id, target.day.isoformat())


@pytest.mark.parametrize("target", DEMO_TARGETS, ids=lambda t: t.parcel_id)
def test_copy_has_ten_seasons_with_under_5_percent_of_days_missing(target):
    copy = _copy(target)
    assert copy is not None, "the copy of the golden-path date is committed"
    gaps = season_gaps(copy.weather.data, target.day)
    assert sorted(gaps) == list(range(FIRST_SEASON[target.parcel_id], target.day.year + 1))
    assert max(gaps.values()) < MAX_MISSING_SHARE


@pytest.mark.parametrize("target", DEMO_TARGETS, ids=lambda t: t.parcel_id)
def test_copy_weather_comes_from_station_measurements(target):
    weather = _copy(target).weather.data
    assert weather.precipitation_sources.get("imgw", 0) > 0.95
    assert (
        weather.et0_sources.get("imgw", 0) > 0.7
    )  # the rest is the NASA POWER grid, named in the sources table


@pytest.mark.parametrize("target", DEMO_TARGETS, ids=lambda t: t.parcel_id)
def test_copy_has_the_forecast_and_the_satellite(target):
    copy = _copy(target)
    assert copy.forecast.usable and copy.forecast.data.days == 16
    assert copy.satellite.usable and copy.satellite.data.current is not None
    assert copy.seasonal.status == "skipped"  # the 183-day outlook is not part of the report


def test_every_golden_path_date_has_its_own_copy_and_nothing_else_is_committed():
    assert sorted(list_samples()) == sorted((t.parcel_id, t.day.isoformat()) for t in DEMO_TARGETS)


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz-2023-07-20", "gora-2026-11-21"])
def test_offline_report_from_the_copy_without_any_request(params, net, monkeypatch):
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    r = client.get(f"/api/raport?{query(params)}")
    assert r.status_code == 200
    report = Report.model_validate(r.json())
    assert report.data_copy.startswith("kopia danych z 21.11.2026")
    assert net.calls == []


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz-2023-07-20", "gora-2026-11-21"])
def test_offline_copies_give_a_forecast_that_is_not_missing_for_lack_of_a_file(params, monkeypatch):
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    data, label = datasource.load(params["dzialka"], date.fromisoformat(params["data"]))
    assert label is not None and data.forecast.usable
    assert "not in this sample" not in " ".join(data.forecast.notes)


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz-2023-07-20", "gora-2026-11-21"])
def test_copy_label_states_the_original_download_time_of_the_rows(params, monkeypatch):
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    report = Report.model_validate(client.get(f"/api/raport?{query(params)}").json())
    rows = [s.elapsed_s for s in report.sources if s.key in datasource.LISTED_SOURCES]
    assert len(rows) == len(datasource.LISTED_SOURCES)
    assert report.data_copy == "kopia danych z 21.11.2026"
    stated = report.data_copy_took_s
    assert stated is not None
    assert stated == pytest.approx(sum(rows), abs=0.1)
    assert stated > 1.0  # the original downloads took seconds; a copy read in milliseconds must not show that


def test_a_date_before_the_copy_is_served_by_cutting_the_weather(monkeypatch):
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    data, label = datasource.load("040303_2.0002.189/13", date(2016, 8, 10))
    assert label is not None and data.weather.data.dates[-1] == "2016-08-10"
