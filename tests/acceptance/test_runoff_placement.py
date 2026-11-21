"""K1, K3: retention places come from a runoff analysis on an elevation grid with a ~300 m margin around the parcel.

Depressions shallower than ~0.2 m are filled (a 10 m grid with heights rounded to 0.1 m is full of them); deeper
ones are kept, as in the ACPF manual v7.0. Accumulation is computed both with one direction per cell (D8) and with
D-infinity; the ditch test picks which of D8, D-infinity or the lowest boundary point the app uses. Accumulation is
the catchment area in ha, and concentrated flow lines are cells above a threshold. Outlets and inlets on the parcel
boundary carry their catchment; candidate places are sorted by the catchment they intercept. Placement thresholds
follow the ACPF manual in metric units: a grassed waterway where the stream power index ln(SCA * tan(slope)) is
above its threshold, at least 50 m long; contour buffer strips on slopes of 4-15%. A parcel too flat for a reliable
flow line gets a sentence instead of arrows.

The synthetic terrain: a 100 m x 100 m parcel on a plane falling 2% to the west, with a valley (5% side slopes)
crossing it from east to west, inside a 700 m x 700 m grid (300 m margin, 10 m cells, heights rounded to 0.1 m).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

X0, Y0 = 500_000.0, 600_000.0  # south-west corner of the parcel, EPSG:2180
SIDE, MARGIN, STEP = 100.0, 300.0, 10.0
VALLEY_Y = Y0 + 55.0  # a row of cell centres
VALLEY_MID = (X0 + 55.0, VALLEY_Y)  # a cell centre on the valley floor, inside the parcel
OUTLINE = [[X0, Y0], [X0 + SIDE, Y0], [X0 + SIDE, Y0 + SIDE], [X0, Y0 + SIDE], [X0, Y0]]
SE_CORNER = [X0 + SIDE - 5.0, Y0 + 5.0]
FLOW_METHODS = ("d8", "dinf")


def _grid(
    *,
    flat: bool = False,
    valley: bool = True,
    slope_pct: float = 2.0,
    pits: tuple[tuple[float, float, float], ...] = (),
):
    """Pits are (x, y, depth): the cell is set `depth` metres below its lowest neighbour, so `depth` is the depth
    of the depression that filling would remove."""
    from app.geodata import ElevationGrid

    n = int((SIDE + 2 * MARGIN) / STEP)
    gx0, y_top = X0 - MARGIN, Y0 + SIDE + MARGIN

    def centre(row: int, col: int) -> tuple[float, float]:
        return gx0 + (col + 0.5) * STEP, y_top - (row + 0.5) * STEP

    def base(x: float, y: float) -> float:
        if flat:
            return 100.0
        h = 100.0 + slope_pct / 100.0 * (x - X0)
        return h + 0.05 * abs(y - VALLEY_Y) if valley else h

    z = [[round(base(*centre(r, c)), 1) for c in range(n)] for r in range(n)]
    for px, py, depth in pits:
        col, row = int((px - gx0) // STEP), int((y_top - py) // STEP)
        lowest = min(z[row + dr][col + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0))
        z[row][col] = round(lowest - depth, 1)
    inside = [
        [int(X0 < centre(r, c)[0] < X0 + SIDE and Y0 < centre(r, c)[1] < Y0 + SIDE) for c in range(n)]
        for r in range(n)
    ]
    return ElevationGrid(
        crs="EPSG:2180", x0=gx0, y_top=y_top, step_m=STEP, rows=n, cols=n, z=z, inside=inside
    )


def _ditch_along_the_west_edge():
    from app.geodata import WaterFeature

    ring = [
        [X0 - 8, Y0 - 250],
        [X0 - 4, Y0 - 250],
        [X0 - 4, Y0 + 350],
        [X0 - 8, Y0 + 350],
        [X0 - 8, Y0 - 250],
    ]
    return WaterFeature(kind="ditch", distance_m=4.0, area_m2=2400.0, rings_2180=[ring])


def _input(grid, water=(), lowest=None, slope=3.0):
    from app.advice.placement import PlacementInput

    return PlacementInput(
        outline_2180=OUTLINE,
        grid=grid,
        lowest_outline_point_2180=lowest,
        water=list(water),
        slope_mean_pct=slope,
    )


def _near(p, x: float, y: float, tol: float = 20.0) -> bool:
    return abs(p.x_2180 - x) <= tol and abs(p.y_2180 - y) <= tol


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("method", FLOW_METHODS)
def test_outlet_is_where_the_valley_leaves_the_parcel_and_collects_the_neighbours_water(
    method: str,
) -> None:
    from app.advice.placement import runoff

    r = runoff(_input(_grid()), method=method)
    assert r.outlets, "no outlet on the boundary"
    top = r.outlets[0]
    assert _near(top, X0, VALLEY_Y), (top.x_2180, top.y_2180)
    # the parcel has 1 ha; the valley drains the land east of it, so only a grid with a margin sees > 5 ha
    assert top.catchment_ha > 5.0
    assert [o.catchment_ha for o in r.outlets] == sorted((o.catchment_ha for o in r.outlets), reverse=True)
    assert any(_near(p, X0 + SIDE, VALLEY_Y) and p.catchment_ha > 5.0 for p in r.inlets)
    assert r.flow_lines, "the valley is a concentrated flow line"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_shallow_pits_are_filled_and_a_deep_corner_hole_is_not_the_outlet() -> None:
    from app.advice.placement import runoff

    # 0.1 m is one rounding step of the heights: filled. The 8 m hole is the lowest boundary point, yet no water
    # leaves the parcel through it.
    pits = ((*VALLEY_MID, 0.1), (SE_CORNER[0], SE_CORNER[1], 8.0))
    r = runoff(_input(_grid(pits=pits), lowest=SE_CORNER))
    top = r.outlets[0]
    assert _near(top, X0, VALLEY_Y), (top.x_2180, top.y_2180)
    assert top.catchment_ha > 5.0


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_depression_deeper_than_20_cm_is_kept_and_holds_the_valley_water() -> None:
    from app.advice.placement import runoff

    r = runoff(_input(_grid(pits=((*VALLEY_MID, 1.0),))))
    # the water still enters the parcel along the valley ...
    assert any(_near(p, X0 + SIDE, VALLEY_Y) and p.catchment_ha > 5.0 for p in r.inlets)
    # ... but stays in the 1 m deep depression instead of reaching the western edge
    assert r.outlets
    assert not any(_near(o, X0, VALLEY_Y) and o.catchment_ha > 5.0 for o in r.outlets)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_flat_parcel_gets_a_sentence_instead_of_flow_lines() -> None:
    from app.advice.placement import runoff

    r = runoff(_input(_grid(flat=True), slope=0.0))
    assert r.flow_lines == []
    assert "spad" in r.reason.lower()


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_stream_power_index_is_log_of_specific_catchment_times_slope() -> None:
    from app.advice.placement import stream_power_index

    assert stream_power_index(sca_m=100.0, slope_pct=5.0) == pytest.approx(math.log(100.0 * 0.05))
    assert stream_power_index(sca_m=400.0, slope_pct=5.0) > stream_power_index(sca_m=100.0, slope_pct=5.0)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_grassed_waterway_lies_on_the_valley_and_is_at_least_50_m_long() -> None:
    from app.advice.placement import find_places

    waterways = [c for c in find_places(_input(_grid())) if c.kind == "rów zadarniony" and c.place]
    assert waterways, "the valley carries > 5 ha through the parcel: its SPI is above the threshold"
    for c in waterways:
        assert abs(c.place.y_2180 - VALLEY_Y) <= 20.0, c.place
        assert c.length_m >= 50.0, c.length_m


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_contour_buffer_strips_only_on_slopes_from_4_to_15_percent() -> None:
    from app.advice.placement import find_places

    def has_strip(slope: float) -> bool:
        grid = _grid(valley=False, slope_pct=slope)
        return any(c.kind == "pas konturowy" and c.place for c in find_places(_input(grid, slope=slope)))

    assert has_strip(8.0)
    assert not has_strip(2.0)
    assert not has_strip(20.0)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_weir_only_where_the_flow_line_reaches_a_ditch() -> None:
    from app.advice.placement import find_places

    with_ditch = {
        c.kind for c in find_places(_input(_grid(), water=[_ditch_along_the_west_edge()])) if c.place
    }
    assert "zastawka" in with_ditch
    assert "rów zadarniony" in with_ditch
    without = {c.kind for c in find_places(_input(_grid())) if c.place}
    assert "zastawka" not in without


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_outflow_onto_a_neighbours_field_gets_a_strip_and_a_basin_inside() -> None:
    from app.advice.placement import find_places

    places = [c for c in find_places(_input(_grid())) if c.place]
    kinds = {c.kind for c in places}
    assert {"pas trawy", "niecka"} <= kinds
    basin = next(c.place for c in places if c.kind == "niecka")
    assert X0 < basin.x_2180 < X0 + SIDE and Y0 < basin.y_2180 < Y0 + SIDE


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_places_are_sorted_by_intercepted_catchment() -> None:
    from app.advice.placement import find_places

    sites = {"rów zadarniony", "pas trawy", "zastawka", "niecka"}
    places = [
        c
        for c in find_places(_input(_grid(), water=[_ditch_along_the_west_edge()]))
        if c.place and c.kind in sites
    ]
    assert places
    catchments = [c.catchment_ha for c in places]
    assert all(v is not None and v > 0 for v in catchments)
    assert catchments == sorted(catchments, reverse=True)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_number_of_weirs_follows_ditch_length_slope_and_head() -> None:
    from app.advice.placement import weir_count

    assert weir_count(length_m=400.0, slope_pct=0.5, head_m=0.4) == 5  # 400 m x 0.005 / 0.4 m
    assert weir_count(length_m=100.0, slope_pct=0.2, head_m=0.3) >= 1


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_app_uses_the_outlet_method_that_wins_the_ditch_test() -> None:
    from app.advice.placement import outlet_method

    m = json.loads(Path("metrics.json").read_text(encoding="utf-8")).get("retention", {})
    keys = {"outlet_hit_d8", "outlet_hit_dinf", "outlet_hit_lowest", "outlet_hit_random", "outlet_hit_share"}
    assert keys <= set(m), keys - set(m)
    # a tie goes to the simpler method: the lowest boundary point, then D8
    scores = [("lowest", m["outlet_hit_lowest"]), ("d8", m["outlet_hit_d8"]), ("dinf", m["outlet_hit_dinf"])]
    best = max(scores, key=lambda s: s[1])
    assert outlet_method() == best[0]
    assert m["outlet_hit_share"] == pytest.approx(best[1])  # the share of the method the app uses


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_readme_cites_the_runoff_method_and_compares_the_outlet_methods() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    for ref in ("ACPF", "Tomer", "2013", "2015", "Porter", "7.0"):
        assert ref in readme, ref
    for method in ("D8", "D-nieskończoność", "najniższy punkt granicy"):
        assert method in readme, method
