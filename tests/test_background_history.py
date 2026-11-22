"""Season history in the background: the report does not wait, the demo copy answers at once."""

from __future__ import annotations

import dataclasses
import threading
import time
from datetime import date

import pytest

from app.crop_condition import background
from app.geodata import SceneIndex, config
from app.geodata.parcel import parse_uldk
from tests.acceptance.helpers import DOBRCZ, html, report
from tests.conftest import fixture_text

DAY = date(2023, 7, 20)


@pytest.fixture
def parcel():
    # a parcel without a demo copy
    return dataclasses.replace(parse_uldk(fixture_text("uldk_ok.txt")), id="141201_1.0001.77")


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(background, "_running", {})
    monkeypatch.setattr(background, "_failed", {})


def _reading(year: int) -> SceneIndex:
    return SceneIndex(f"S2_{year}", f"{year}-06-01", 0, 1.0, 0.7, 0.3, 0.9, 300, ndvi_spread=0.08)


def test_first_report_waits_for_nothing_and_the_next_one_has_the_seasons(monkeypatch, parcel) -> None:
    release = threading.Event()
    calls: list[int] = []

    def slow_season(p, year, until=None, deadline=None):
        calls.append(year)
        release.wait(5)
        return [_reading(year)]

    monkeypatch.setattr(background, "fetch_season", slow_season)
    started = time.monotonic()
    status, seasons, _ = background.seasons_for(parcel, DAY)
    assert status == "waiting" and seasons == {}
    assert time.monotonic() - started < 0.5  # the history is not waited for
    assert background.seasons_for(parcel, DAY)[0] == "waiting"
    release.set()
    for thread in list(background._running.values()):
        thread.join(5)
    status, seasons, _ = background.seasons_for(parcel, DAY)
    assert status == "ready"
    assert sorted(seasons) == list(range(DAY.year - background.SEASONS_BACK, DAY.year + 1))
    assert len(calls) == background.SEASONS_BACK + 1  # one thread, one pass


def test_failed_history_is_a_stated_gap_not_an_endless_wait(monkeypatch, parcel) -> None:
    def broken(*a, **k):
        raise RuntimeError("usługa nie odpowiada")

    monkeypatch.setattr(background, "fetch_season", broken)
    background.seasons_for(parcel, DAY)
    for thread in list(background._running.values()):
        thread.join(5)
    status, _, reason = background.seasons_for(parcel, DAY)
    assert status == "missing" and "usługa nie odpowiada" in reason


def test_without_copy_and_without_network_the_gap_names_the_reason(parcel) -> None:
    config.set_offline(True)
    status, seasons, reason = background.seasons_for(parcel, DAY)
    assert status == "missing" and seasons == {}
    assert "brak kopii" in reason and not background._running


def test_the_result_is_cached_outside_tracked_files(monkeypatch, parcel, tmp_path) -> None:
    monkeypatch.setattr(background, "fetch_season", lambda p, y, until=None, deadline=None: [_reading(y)])
    background.seasons_for(parcel, DAY)
    for thread in list(background._running.values()):
        thread.join(5)
    assert any((tmp_path / "cache" / background.NAMESPACE).glob("*.json"))


def test_demo_copy_holds_comparable_seasons_with_spread() -> None:
    seasons = background.load_frozen(DOBRCZ["dzialka"], DAY)
    assert seasons is not None and DAY.year in seasons
    assert sum(1 for y, r in seasons.items() if y < DAY.year and len(r) >= 8) >= 3
    assert all(r.ndvi_spread is None or r.ndvi_spread >= 0 for rs in seasons.values() for r in rs)
    assert any(isinstance(r.ndvi_spread, float) for rs in seasons.values() for r in rs)


def test_route_shows_the_scene_date_from_the_demo_copy() -> None:
    condition = report().crop_condition
    assert condition.state in {"ok", "missing"} and condition.state != "waiting"
    assert condition.scene_date is not None
    page = html(widok="doradca")
    row = page.split('id="wiersz-satelita"')[1].split("</div>")[0]
    assert condition.scene_date.strftime("%d.%m.%Y") in row
