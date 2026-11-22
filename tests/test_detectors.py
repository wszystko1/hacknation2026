"""Detectors with geometry: grass strip, balk, tillage across the slope, basin; flat land gives a reason."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.advice import detectors as dt
from app.advice import placement as pl
from app.advice.mechanisms import load_mechanisms
from app.advice.placement import fit_plane
from app.advice.terrain_model import build_terrain_model
from app.geodata.models import ElevationGrid
from app.geodata.samples import load_sample
from app.models import NO_PLACE_PREFIX, Candidate
from tests.test_placement import MARGIN, SIDE, STEP, X0, Y0, ditch, make_grid, make_input

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


# ---------------------------------------------------------------- balk on the contour, tillage across the fall


def terrain(height, *, gaps=None, step: float = 10.0) -> ElevationGrid:
    """A grid over the test parcel (+300 m margin) with heights from `height(x, y)`; `gaps(r, c)` drops a cell."""
    base = make_grid(slope_pct=0.0)
    z = []
    for r in range(base.rows):
        row = []
        for c in range(base.cols):
            x, y = base.x0 + (c + 0.5) * step, base.y_top - (r + 0.5) * step
            row.append(None if gaps and gaps(r, c) else round(height(x, y), 1))
        z.append(row)
    return ElevationGrid(
        crs=base.crs,
        x0=base.x0,
        y_top=base.y_top,
        step_m=step,
        rows=base.rows,
        cols=base.cols,
        z=z,
        inside=base.inside,
    )


def _heights_on(line, grid: ElevationGrid) -> np.ndarray:
    xs, ys = np.array([p[0] for p in line]), np.array([p[1] for p in line])
    return pl._sample(grid, pl._heights(grid), xs, ys)


def _along(line, spacing: float = 2.0):
    pts = []
    for (x1, y1), (x2, y2) in zip(line, line[1:], strict=False):
        n = max(1, int(math.hypot(x2 - x1, y2 - y1) / spacing))
        pts += [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n)]
    return [*pts, line[-1]]


def _in_outline(point, tol: float = 0.2) -> bool:
    return X0 - tol <= point[0] <= X0 + SIDE + tol and Y0 - tol <= point[1] <= Y0 + SIDE + tol


def _on_contour(c: Candidate, grid: ElevationGrid, slope_pct: float) -> None:
    assert c.geometry is not None and c.geometry.type == "line"
    level = c.evidence["level_m"]
    # half a cell sideways is a height of slope * 5 m; the heights themselves are rounded to 0.1 m
    tol = 0.5 * grid.step_m * slope_pct / 100.0 + 0.05
    for h in _heights_on(_along(c.geometry.coordinates), grid):
        assert abs(h - level) <= tol
    assert all(_in_outline(p) for p in c.geometry.coordinates)
    assert c.geometry.length_m and c.geometry.length_m > 0


def test_balk_lies_on_the_contour_of_a_tilted_slope() -> None:
    # falls to the north-east at about 4.2%: the contour runs north-west to south-east
    grid = terrain(lambda x, y: 100.0 - 0.03 * (x - X0) - 0.03 * (y - Y0))
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    _on_contour(c, grid, 4.25)
    assert _angle_gap(c.geometry.azimuth_deg, 135.0) < 3.0
    assert c.parameters["szerokosc"].source == dt.PROPOSAL


def test_balk_follows_the_curve_of_a_convex_hill() -> None:
    cx, cy = X0 + 40.0, Y0 + 50.0
    grid = terrain(lambda x, y: 110.0 - 0.0004 * ((x - cx) ** 2 + (y - cy) ** 2))
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    assert c.geometry is not None and len(c.geometry.coordinates) > 2  # a curve, not a straight chord
    _on_contour(c, grid, 5.0)
    radii = {round(math.hypot(x - cx, y - cy)) for x, y in _along(c.geometry.coordinates)}
    assert max(radii) - min(radii) <= 6  # on one circle around the top, within the grid's resolution


def test_balk_is_clipped_to_the_outline_and_cuts_no_corner() -> None:
    grid = terrain(lambda x, y: 100.0 - 0.02 * (x - X0) - 0.04 * (y - Y0))
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    assert c.geometry is not None
    first, last = c.geometry.coordinates[0], c.geometry.coordinates[-1]
    on_edge = [
        abs(p[0] - X0) < 0.2
        or abs(p[0] - X0 - SIDE) < 0.2
        or abs(p[1] - Y0) < 0.2
        or abs(p[1] - Y0 - SIDE) < 0.2
        for p in (first, last)
    ]
    assert all(on_edge)  # both ends sit on the outline
    assert c.geometry.length_m <= SIDE * math.sqrt(2) + 0.5


def test_balk_has_no_place_on_flat_ground_with_a_reason() -> None:
    grid = terrain(lambda x, y: 100.0 + 0.0001 * (x - X0))
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    assert c.geometry is None and c.confidence == "niska"
    assert c.no_place_reason.startswith(NO_PLACE_PREFIX) and "za mały" in c.no_place_reason


def test_balk_has_no_place_when_the_grid_has_heights_in_a_few_percent_of_cells() -> None:
    keep = lambda r, c: (r * 31 + c * 17) % 25 != 0  # noqa: E731  # about 4% of the cells keep a height
    grid = terrain(lambda x, y: 100.0 - 0.03 * (x - X0), gaps=lambda r, c: keep(r, c))
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    assert c.geometry is None
    assert "komórek działki" in c.no_place_reason and c.confidence == "niska"


def test_a_gap_cuts_the_balk_instead_of_bridging_it() -> None:
    def hole(
        r: int, c: int
    ) -> bool:  # a band of missing heights across the middle of the parcel, 3 rows wide
        return abs(r - 30) <= 1 and 25 <= c <= 45

    grid = terrain(lambda x, y: 100.0 - 0.03 * (x - X0) + 0.0 * y, gaps=hole)
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    assert c.geometry is not None
    ys = [p[1] for p in c.geometry.coordinates]
    gap_y = (Y0 + SIDE + MARGIN) - 31 * STEP  # northing of the middle of the missing rows
    assert max(ys) < gap_y - 5 or min(ys) > gap_y + 5  # the line stays on one side of the gap


def test_balk_has_no_place_when_the_contour_is_shorter_than_the_minimum(monkeypatch) -> None:
    grid = make_grid(slope_pct=3.0)  # the contour crosses the parcel over 100 m
    monkeypatch.setattr(dt, "MIN_BALK_M", 150.0)
    c, _ = _run("detect_balk", "slow_runoff_balk", grid)
    assert c.geometry is None and "mniej niż 150 m" in c.no_place_reason


@pytest.mark.parametrize("slope_dir_deg", [270.0, 200.0, 45.0, 123.0])
def test_tillage_rows_are_at_right_angles_to_the_fall(slope_dir_deg: float) -> None:
    slope = 0.07
    gx, gy = -slope * math.sin(math.radians(slope_dir_deg)), -slope * math.cos(math.radians(slope_dir_deg))
    grid = terrain(lambda x, y: 100.0 + gx * (x - X0) + gy * (y - Y0))
    c, _ = _run("detect_contour", "contour_tillage", grid)
    assert c.geometry is not None and c.geometry.type == "polygon"
    assert _angle_gap(c.geometry.azimuth_deg, slope_dir_deg) == pytest.approx(90.0, abs=1.0)
    assert 0.0 <= c.geometry.azimuth_deg < 180.0
    assert all(_in_outline(p, 0.2) for p in c.geometry.coordinates)  # clipped to the outline


@pytest.mark.parametrize(("slope", "placed"), [(3.0, False), (4.5, True), (12.0, True), (16.0, False)])
def test_tillage_only_inside_the_threshold_band(slope: float, placed: bool) -> None:
    c, _ = _run("detect_contour", "contour_tillage", make_grid(slope_pct=slope))
    assert (c.geometry is not None) is placed
    if not placed:
        assert "przedziałem 4–15%" in c.no_place_reason and c.confidence == "niska"


def test_tillage_above_the_nrcs_limit_says_so() -> None:
    low, _ = _run("detect_contour", "contour_tillage", make_grid(slope_pct=8.0))
    high, _ = _run("detect_contour", "contour_tillage", make_grid(slope_pct=12.0))
    assert not any("NRCS" in r for r in low.risks) and any("NRCS" in r for r in high.risks)


def test_tillage_polygon_is_the_whole_band_on_a_plane() -> None:
    c, inp = _run("detect_contour", "contour_tillage", make_grid(slope_pct=6.0))
    ring = [(x, y) for x, y in c.geometry.coordinates]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, [*ring[1:], ring[0]], strict=True))) / 2.0
    assert area > 0.8 * SIDE * SIDE


# ---------------------------------------------------------------- the frozen demo parcel


def test_the_demo_parcel_gets_a_balk_on_a_contour_or_a_reason(monkeypatch) -> None:
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    sample = load_sample("100403_2.0011.144", "2026-11-21")
    parcel, t = sample.parcel.data, sample.terrain.data
    inp = pl.PlacementInput(
        parcel.rings_2180[0], t.catchment_grid or t.grid, t.lowest_outline_point_2180, [], t.slope_mean_pct
    )
    model = build_terrain_model(inp, margin_grid=True)
    balk = dt.detect(MECH["slow_runoff_balk"], model, inp)
    assert (
        balk.geometry is not None and balk.geometry.type == "line" and balk.geometry.length_m > dt.MIN_BALK_M
    )
    ring = parcel.rings_2180[0]
    assert all(
        dt._inside_ring(x, y, ring) or dt._distance_to_polyline(x, y, ring) < 0.2
        for x, y in _along(balk.geometry.coordinates)
    )
    grid = inp.grid
    heights = _heights_on(_along(balk.geometry.coordinates), grid)
    assert float(np.nanmax(np.abs(heights - balk.evidence["level_m"]))) <= 0.5 * grid.step_m * 0.11 + 0.05
    # the mean slope of the parcel is 2.85%, below the 4% band: tillage across the slope has a reason, not a polygon
    tillage = dt.detect(MECH["contour_tillage"], model, inp)
    assert tillage.geometry is None and "przedziałem 4–15%" in tillage.no_place_reason


def test_balk_and_tillage_fit_the_candidate_model() -> None:
    grid = make_grid(slope_pct=6.0)
    for det, mid in (("detect_balk", "slow_runoff_balk"), ("detect_contour", "contour_tillage")):
        c, _ = _run(det, mid, grid)
        assert Candidate.model_validate(c.model_dump()) == c
