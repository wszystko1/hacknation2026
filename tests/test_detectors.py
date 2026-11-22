"""Detectors with geometry: grass strip, balk, tillage across the slope, basin; flat land gives a reason."""

from __future__ import annotations

import pytest

from app.advice import detectors as dt
from app.advice.mechanisms import load_mechanisms
from app.advice.placement import fit_plane
from app.advice.terrain_model import build_terrain_model
from app.models import NO_PLACE_PREFIX, Candidate
from tests.test_placement import X0, Y0, ditch, make_grid, make_input

MECH = load_mechanisms()


def _run(detector: str, mech_id: str, grid, water=(), roads=()):
    inp = make_input(grid, water)
    model = build_terrain_model(inp, margin_grid=True)
    return getattr(dt, detector)(
        model, MECH[mech_id], inp, *([roads] if detector == "detect_basin" else [])
    ), inp


def _angle_gap(a: float, b: float) -> float:
    return abs((a - b + 90.0) % 180.0 - 90.0)


def test_strip_is_a_line_along_the_outflow_segment() -> None:
    c, _ = _run("detect_strip", "slow_runoff_strip", make_grid(slope_pct=3.0))
    assert c.geometry is not None and c.geometry.type == "line"
    assert all(abs(x - X0) < 1e-6 for x, _ in c.geometry.coordinates)  # the west side falls
    assert c.geometry.length_m and c.geometry.length_m > 0
    assert c.evidence["along_ditch"] is False


def test_strip_along_a_ditch_says_so() -> None:
    c, _ = _run("detect_strip", "slow_runoff_strip", make_grid(slope_pct=3.0), [ditch(X0 - 10, X0 - 6)])
    assert c.evidence["along_ditch"] is True
    assert "rowu" in c.next_step


def test_balk_is_a_line_across_the_slope_inside_the_outline() -> None:
    grid = make_grid(slope_pct=3.0)  # falls to the west: the balk runs north-south
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    assert c.geometry is not None and c.geometry.type == "line"
    (x1, y1), (x2, y2) = c.geometry.coordinates
    assert abs(x1 - x2) < 0.5 and abs(abs(y1 - y2) - 100.0) < 0.5
    assert X0 <= x1 <= X0 + 100 and Y0 - 1e-6 <= min(y1, y2)


def test_contour_polygon_with_rows_across_the_fall() -> None:
    for slope in (5.0, 8.0):
        grid = make_grid(slope_pct=slope)
        c, _ = _run("detect_contour", "contour_tillage", grid)
        assert c.geometry is not None and c.geometry.type == "polygon"
        assert c.geometry.azimuth_deg is not None
        downhill = fit_plane(grid).downhill_deg
        assert _angle_gap(c.geometry.azimuth_deg, downhill) == pytest.approx(90.0, abs=1.0)
        assert c.evidence["rows_words"] == "z północy na południe"
        assert "z północy na południe" in c.next_step


def test_contour_is_refused_outside_the_slope_band() -> None:
    c, _ = _run("detect_contour", "contour_tillage", make_grid(slope_pct=2.0))
    assert c.geometry is None
    assert c.no_place_reason.startswith(NO_PLACE_PREFIX) and c.confidence == "niska"


def test_row_direction_words() -> None:
    assert dt.row_direction_words(0) == "z północy na południe"
    assert dt.row_direction_words(90) == "ze wschodu na zachód"
    assert dt.row_direction_words(179) == "z północy na południe"


def test_basin_polygon_in_a_depression() -> None:
    grid = make_grid(slope_pct=0.0, pits=[(X0 + 55.0, Y0 + 55.0, 0.5)])
    c, _ = _run("detect_basin", "hold_in_depression", grid)
    assert c.geometry is not None and c.geometry.type == "polygon"
    assert c.evidence["depth_m"] >= 0.2


def test_basin_point_at_the_lowest_interior_point_without_a_depression() -> None:
    c, _ = _run("detect_basin", "hold_in_depression", make_grid(slope_pct=3.0))
    assert c.geometry is not None and c.geometry.type == "point"
    assert c.confidence == "niska"


def test_basin_near_a_road_is_refused() -> None:
    grid = make_grid(slope_pct=0.0, pits=[(X0 + 55.0, Y0 + 55.0, 0.5)])
    road = [[X0 + 20.0, Y0 + 58.0], [X0 + 90.0, Y0 + 58.0]]
    c, _ = _run("detect_basin", "hold_in_depression", grid, roads=[road])
    assert c.geometry is None
    assert "od drogi" in c.no_place_reason and c.confidence == "niska"
    far = [[X0 - 200.0, Y0 - 200.0], [X0 - 150.0, Y0 - 200.0]]
    ok, _ = _run("detect_basin", "hold_in_depression", grid, roads=[far])
    assert ok.geometry is not None


@pytest.mark.parametrize("mech", ["slow_runoff_strip", "slow_runoff_balk", "contour_tillage"])
def test_flat_land_has_no_place_and_a_reason(mech: str) -> None:
    grid = make_grid(slope_pct=0.3)
    inp = make_input(grid)
    model = build_terrain_model(inp, margin_grid=True)
    c = dt.detect(MECH[mech], model, inp)
    assert c.geometry is None
    assert c.no_place_reason.startswith("brak miejsca na działce, bo ")
    assert "0,3%" in c.no_place_reason
    assert c.confidence == "niska"


def test_mechanisms_without_a_place_are_potential_with_a_reason() -> None:
    inp = make_input(make_grid(slope_pct=3.0))
    model = build_terrain_model(inp, margin_grid=True)
    for mid in (
        "dam_in_ditch",
        "drain_outflow",
        "reduce_evaporation",
        "raise_soil_capacity",
        "supply_missing_rain",
    ):
        c = dt.detect(MECH[mid], model, inp)
        assert c.geometry is None and c.confidence == "niska"
        assert c.no_place_reason.startswith(NO_PLACE_PREFIX) and len(c.no_place_reason) > len(NO_PLACE_PREFIX)
        assert c.next_step.startswith(dt.POTENTIAL)


def test_every_parameter_is_a_range_with_unit_and_source() -> None:
    inp = make_input(make_grid(slope_pct=5.0))
    model = build_terrain_model(inp, margin_grid=True)
    seen = 0
    for mech in MECH.values():
        c: Candidate = dt.detect(mech, model, inp)
        for name, rng in c.parameters.items():
            seen += 1
            assert rng.unit.strip() and rng.source.strip(), name
            assert rng.source == dt.PROPOSAL or "s." in rng.source
            assert rng.low <= rng.high
    assert seen >= 6


def test_no_grid_gives_a_reason_not_an_error() -> None:
    inp = make_input(None)
    model = build_terrain_model(inp, margin_grid=True)
    for mid in ("slow_runoff_strip", "slow_runoff_balk", "contour_tillage"):
        c = dt.detect(MECH[mid], model, inp)
        assert c.geometry is None and "siatki" in c.no_place_reason
