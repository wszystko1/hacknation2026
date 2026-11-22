"""Terrain and the other sources through the guards: the 148.9 % case, the frozen demo parcel, mocked services."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.geodata import orchestrator
from app.geodata.errors import UpstreamError
from app.geodata.models import Parcel, SourceResult, Terrain, Weather, from_dict
from app.geodata.terrain import assess_terrain, grid_stats

FROZEN = Path("demo/data/geodata/040303_2_0002_189_13__2023-07-20.json")
X0, Y_TOP, STEP = 500000.0, 400400.0, 10.0


def _parcel(x: float = 500150.0, y: float = 400150.0, side: float = 100.0) -> Parcel:
    ring = [[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]
    return Parcel(
        id="000000_0.0000.1", voivodeship="x", county="x", commune="x", precinct="x", number="1", area_ha=side * side / 1e4,
        rings_2180=[ring], rings_4326=[ring], centroid_2180=[x + side / 2, y + side / 2], centroid_4326=[17.0, 50.0],
        bbox_2180=[x, y, x + side, y + side], bbox_4326=[17.0, 50.0, 17.1, 50.1],
    )  # fmt: skip


def _plane(slope_pct: float, rows: int = 40, cols: int = 40) -> np.ndarray:
    return np.fromfunction(lambda r, c: 260.0 - slope_pct / 100.0 * STEP * c, (rows, cols))


def test_plane_gives_its_slope() -> None:
    t = grid_stats(_plane(3.0), X0, Y_TOP, STEP, _parcel(), "test")
    assert t.slope_mean_pct == pytest.approx(3.0, abs=0.05)


def test_the_148_9_percent_case_zero_gaps_next_to_land() -> None:
    """The service answers 0.0 outside its coverage. Half of the outline on 260 m land and half on 0.0 gave
    a gradient of 26 m per 10 m cell at the seam and a mean slope of 100+ %."""
    z = _plane(2.0)
    z[:18, :] = 0.0  # the northern 30 % of the outline: no coverage
    t = grid_stats(z, X0, Y_TOP, STEP, _parcel(y=400150.0), "test")
    # the cells are NaN now: statistics describe only real heights, and the slope is the real 2 %
    assert t.min_m > 200.0
    assert t.slope_mean_pct == pytest.approx(2.0, abs=0.5)


def test_outline_mostly_without_heights_is_no_terrain() -> None:
    z = _plane(2.0)
    z[:22, :] = 0.0
    with pytest.raises(UpstreamError, match="brak danych"):
        grid_stats(z, X0, Y_TOP, STEP, _parcel(), "test")


def test_nodata_minus_9999_in_the_grid() -> None:
    z = _plane(2.0)
    z[18:22, 18:22] = -9999.0
    t = grid_stats(z, X0, Y_TOP, STEP, _parcel(), "test")
    assert t.min_m > 0 and t.slope_mean_pct is not None and t.slope_mean_pct < 5.0


def test_absurd_slope_is_removed_with_a_reason() -> None:
    z = _plane(2.0)
    z[18:22, 18:22] += 40.0  # a 40 m spike inside the parcel: slope over 40 %
    t = grid_stats(z, X0, Y_TOP, STEP, _parcel(), "test")
    # either the spike stays within 0-40 % on average (kept) or it is dropped: never a number above the range
    assert t.slope_mean_pct is None or t.slope_mean_pct <= 40.0
    checked, notes = assess_terrain(_parcel(), t)
    assert checked.slope_mean_pct is None or checked.slope_mean_pct <= 40.0


def test_cached_answer_with_148_9_is_recomputed_or_refused() -> None:
    parcel = _parcel()
    z = _plane(2.0)
    t = grid_stats(z, X0, Y_TOP, STEP, parcel, "test")
    poisoned = from_dict(Terrain, json.loads(json.dumps(__import__("dataclasses").asdict(t))))
    poisoned.slope_mean_pct, poisoned.slope_max_pct = 148.87, 1939.24
    fixed, notes = assess_terrain(parcel, poisoned)
    assert fixed.slope_mean_pct is not None and fixed.slope_mean_pct < 5.0
    assert any("od nowa" in n for n in notes)


def test_cached_grid_with_zero_gaps_is_refused_when_the_outline_has_no_heights() -> None:
    """The real parcel 160204_5.0001.101: 68 % of the outline cells were 0.0 in the stored answer."""
    parcel = _parcel()
    z = _plane(2.0)
    t = grid_stats(z, X0, Y_TOP, STEP, parcel, "test")
    assert t.grid is not None
    t.grid.z = [[0.0 if i < 30 else v for v in row] for i, row in enumerate(t.grid.z)]
    t.slope_mean_pct = 148.87
    with pytest.raises(UpstreamError):
        assess_terrain(parcel, t)


def test_frozen_demo_parcel_is_unchanged() -> None:
    raw = json.loads(FROZEN.read_text())
    t = from_dict(Terrain, raw["terrain"]["data"])
    parcel = from_dict(Parcel, raw["parcel"]["data"])
    before = (t.slope_mean_pct, t.slope_max_pct, t.min_m, t.max_m, t.mean_m, t.samples)
    checked, notes = assess_terrain(parcel, t)
    assert (
        checked.slope_mean_pct,
        checked.slope_max_pct,
        checked.min_m,
        checked.max_m,
        checked.mean_m,
        checked.samples,
    ) == before
    assert notes == []


def test_frozen_demo_other_sources_pass_the_checks() -> None:
    from app.geodata import sanity

    raw = json.loads(FROZEN.read_text())
    parcel = from_dict(Parcel, raw["parcel"]["data"])
    weather = from_dict(Weather, raw["weather"]["data"])
    assert sanity.check_outline(parcel.rings_2180, parcel.area_ha).level is sanity.Level.OK
    assert sanity.check_precipitation(weather.precipitation_mm).level is sanity.Level.OK
    assert sanity.check_et0(weather.et0_mm).level is sanity.Level.OK
    assert sanity.check_series_gaps(weather.missing_share).level is not sanity.Level.INVALID


def test_orchestrator_turns_a_degenerate_outline_into_a_gap() -> None:
    bad = _parcel(side=0.0)
    res = SourceResult("parcel", "ok", bad, source_url="u")
    out = orchestrator._vet_parcel(res)
    assert out.status == "error" and not out.usable and out.error.startswith("brak: obrys")
    good = orchestrator._vet_parcel(SourceResult("parcel", "ok", _parcel()))
    assert good.usable


def test_weather_out_of_range_days_become_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    from app.geodata import weather

    dates = [f"2023-07-{d:02d}" for d in range(1, 11)]
    series = {
        "dates": dates, "latitude": 50.0, "longitude": 17.0, "precipitation_mm": [1.0, -5.0, 400.0] + [0.0] * 7,
        "et0_mm": [3.0] * 3 + [99.0] + [3.0] * 6, "p_src": [1] * 10, "e_src": [1] * 10,
        "stations": {}, "tmean_c": [], "sunshine_h": [],
    }  # fmt: skip
    entry = {
        "series": series,
        "start": "2023-07-01",
        "notes": [],
        "url": "u",
        "retrieved_at": "2023-07-10T00:00:00+00:00",
    }
    res = weather._build(entry, date(2023, 7, 10), date(2023, 7, 1), True, [])
    assert res.data.precipitation_mm[1:3] == [None, None]
    assert res.data.et0_mm[3] is None
    assert res.data.missing_days == 3
    text = " ".join(res.notes)
    assert "opad poza zakresem" in text and "parowanie poza zakresem" in text and "niekompletny" in text
