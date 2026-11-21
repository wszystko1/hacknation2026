"""Runoff analysis and place rules: the thresholds come from the catalogue, the method is chosen by the ditch test.

The synthetic terrains are planes and valleys on a 10 m grid with heights rounded to 0.1 m, the precision of the
public height model.
"""

from __future__ import annotations

import ast
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import pytest

from app.advice import catalog, placement
from app.advice.placement import (
    FILL_DEPTH_M,
    PlacementInput,
    find_places,
    outlet_method,
    runoff,
    stream_power_index,
    weir_count,
)
from app.geodata import ElevationGrid, WaterFeature

X0, Y0, SIDE, MARGIN, STEP = 500_000.0, 600_000.0, 100.0, 300.0, 10.0
OUTLINE = [[X0, Y0], [X0 + SIDE, Y0], [X0 + SIDE, Y0 + SIDE], [X0, Y0 + SIDE], [X0, Y0]]
VALLEY_Y = Y0 + 55.0


def make_grid(
    *, slope_pct: float = 2.0, valley: bool = False, pits=(), cells: int | None = None
) -> ElevationGrid:
    """A plane falling `slope_pct` to the west; `valley` adds a 5% valley along y = VALLEY_Y; pits are (x, y, depth)."""
    n = cells or int((SIDE + 2 * MARGIN) / STEP)
    gx0, y_top = X0 - MARGIN, Y0 + SIDE + MARGIN

    def centre(r: int, c: int) -> tuple[float, float]:
        return gx0 + (c + 0.5) * STEP, y_top - (r + 0.5) * STEP

    def height(x: float, y: float) -> float:
        h = 100.0 + slope_pct / 100.0 * (x - X0)
        return h + 0.05 * abs(y - VALLEY_Y) if valley else h

    z = [[round(height(*centre(r, c)), 1) for c in range(n)] for r in range(n)]
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


def make_input(grid, water=(), slope: float | None = 3.0) -> PlacementInput:
    return PlacementInput(
        outline_2180=OUTLINE,
        grid=grid,
        lowest_outline_point_2180=None,
        water=list(water),
        slope_mean_pct=slope,
    )


def ditch_west_of_the_parcel() -> WaterFeature:
    ring = [
        [X0 - 8, Y0 - 250],
        [X0 - 4, Y0 - 250],
        [X0 - 4, Y0 + 350],
        [X0 - 8, Y0 + 350],
        [X0 - 8, Y0 - 250],
    ]
    return WaterFeature(kind="ditch", distance_m=4.0, area_m2=2400.0, rings_2180=[ring])


def edge_water_ha(surface: placement._Surface, method: str) -> float:
    """Water that reaches the cells on the grid edge, in ha."""
    flow = placement._flow(surface, method)
    rows, cols = surface.rows, surface.cols
    edge = np.zeros((rows, cols), dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    return float(flow.acc_ha[edge.ravel()].sum())


# ---------------------------------------------------------------- outlet method from the ditch test


def write_metrics(path: Path, retention: dict | None) -> None:
    path.write_text(json.dumps({} if retention is None else {"retention": retention}), encoding="utf-8")


@pytest.mark.parametrize(
    ("retention", "expected"),
    [
        (None, "lowest"),
        ({"outlet_hit_share": 0.5}, "lowest"),
        ({"outlet_hit_d8": 0.6, "outlet_hit_dinf": 0.7, "outlet_hit_lowest": 0.5}, "dinf"),
        ({"outlet_hit_d8": 0.7, "outlet_hit_dinf": 0.7, "outlet_hit_lowest": 0.5}, "d8"),
        ({"outlet_hit_d8": 0.7, "outlet_hit_dinf": 0.6, "outlet_hit_lowest": 0.7}, "lowest"),
        ({"outlet_hit_d8": 0.5, "outlet_hit_dinf": 0.5, "outlet_hit_lowest": 0.5}, "lowest"),
        ({"outlet_hit_d8": 0.4, "outlet_hit_dinf": 0.4, "outlet_hit_lowest": 0.6}, "lowest"),
    ],
)
def test_outlet_method_follows_the_best_hit_rate(tmp_path, monkeypatch, retention, expected) -> None:
    write_metrics(tmp_path / "metrics.json", retention)
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")
    assert outlet_method() == expected


def test_outlet_method_without_a_metrics_file_is_the_lowest_point(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "missing.json")
    assert outlet_method() == "lowest"


def test_outlet_method_reads_the_metrics_file_of_the_working_directory(tmp_path, monkeypatch) -> None:
    write_metrics(
        tmp_path / "metrics.json", {"outlet_hit_d8": 0.5, "outlet_hit_dinf": 0.8, "outlet_hit_lowest": 0.4}
    )
    monkeypatch.chdir(tmp_path)
    assert outlet_method() == "dinf"


# ---------------------------------------------------------------- filling and conservation of water


def test_a_pit_of_one_rounding_step_vanishes_and_a_deep_one_stays() -> None:
    cell = (int((VALLEY_Y - (Y0 + SIDE + MARGIN)) // -STEP), int((X0 + 55 - (X0 - MARGIN)) // STEP))
    shallow = placement._build_surface(make_grid(pits=((X0 + 55, VALLEY_Y, 0.1),)))
    deep = placement._build_surface(make_grid(pits=((X0 + 55, VALLEY_Y, 0.5),)))
    assert shallow.kept_depressions == 0
    assert shallow.filled[cell] > shallow.z[cell]
    assert deep.kept_depressions == 1
    assert deep.filled[cell] == deep.z[cell]


@pytest.mark.parametrize("method", ["d8", "dinf"])
def test_water_from_a_deep_pit_catchment_does_not_reach_the_grid_edge(method: str) -> None:
    pit = ((X0 + 55, VALLEY_Y, 0.5),)
    plain = placement._build_surface(make_grid())
    shallow = placement._build_surface(make_grid(pits=((X0 + 55, VALLEY_Y, 0.1),)))
    deep = placement._build_surface(make_grid(pits=pit))
    total_ha = plain.rows * plain.cols * STEP * STEP / 10_000.0
    assert edge_water_ha(shallow, method) == pytest.approx(total_ha, rel=0.01)
    assert edge_water_ha(deep, method) < total_ha * 0.99


@pytest.mark.parametrize("method", ["d8", "dinf"])
def test_on_a_plane_falling_west_all_water_leaves_through_the_grid_edge(method: str) -> None:
    surface = placement._build_surface(make_grid(slope_pct=2.0))
    total_ha = surface.rows * surface.cols * STEP * STEP / 10_000.0
    assert edge_water_ha(surface, method) == pytest.approx(total_ha, rel=0.01)


def test_a_flat_parcel_gets_a_sentence_with_the_slope_and_no_lines() -> None:
    r = runoff(make_input(make_grid(slope_pct=0.0), slope=0.3))
    assert r.flow_lines == [] and r.outlets == []
    assert r.reason.startswith("spadek 0,3%")


def test_without_a_grid_the_reason_is_the_missing_grid() -> None:
    inp = PlacementInput(OUTLINE, None, None)
    assert runoff(inp).reason == "brak siatki wysokości dla działki"
    candidates = find_places(inp)
    assert [c.kind for c in candidates] == ["punkt wypływu"]
    assert candidates[0].place is None
    assert candidates[0].no_place_reason == "brak miejsca na działce, bo brak siatki wysokości dla działki"


def test_without_a_grid_the_lowest_outline_point_is_still_the_outlet() -> None:
    inp = PlacementInput(OUTLINE, None, [X0 + 3, Y0 + 40])
    candidates = find_places(inp)
    assert candidates[0].place is not None and candidates[0].place.x_2180 == X0 + 3


@pytest.mark.parametrize("method", ["d8", "dinf"])
def test_runoff_is_deterministic(method: str) -> None:
    grid = make_grid(valley=True)
    a, b = runoff(make_input(grid), method), runoff(make_input(grid), method)
    assert a == b


# ---------------------------------------------------------------- thresholds come from the catalogue


# The catalogue has no grassed-waterway or contour-strip row; the placement code still honours such a row when a
# catalogue holds one. These thresholds stand in for that row so the reading of each column stays tested.
ROWS_NOT_IN_THE_CATALOGUE = {
    "row-zadarniony": {"spi_min": "2", "length_min_m": "50"},
    "pas-konturowy": {"slope_min_pct": "4", "slope_max_pct": "15"},
}


def catalogue_with_extra_rows() -> dict[str, catalog.CatalogRow]:
    """The catalogue plus the rows above, built from an existing retention row with only id and thresholds changed."""
    rows = catalog.load_catalog()
    base = rows["uprawa-w-poprzek-stoku"]
    extra = {
        action_id: base.model_copy(update={"action_id": action_id, "conditions": {**base.conditions, **cond}})
        for action_id, cond in ROWS_NOT_IN_THE_CATALOGUE.items()
        if action_id not in rows
    }
    return {**rows, **extra}


def with_condition(monkeypatch, action_id: str, **conditions: str) -> None:
    """Replace the condition columns of one catalogue row, as a changed CSV would."""
    rows = catalogue_with_extra_rows()
    changed = rows[action_id].model_copy(update={"conditions": {**rows[action_id].conditions, **conditions}})
    monkeypatch.setattr(catalog, "load_catalog", lambda: {**rows, action_id: changed})


def kinds(inp: PlacementInput) -> set[str]:
    return {c.kind for c in find_places(inp) if c.place}


def test_grassed_waterway_follows_the_spi_and_length_thresholds_of_the_catalogue(monkeypatch) -> None:
    inp = make_input(make_grid(valley=True))
    assert "rów zadarniony" not in kinds(inp)  # the catalogue has no such row
    with_condition(monkeypatch, "row-zadarniony")
    assert "rów zadarniony" in kinds(inp)
    with_condition(monkeypatch, "row-zadarniony", spi_min="50")
    assert "rów zadarniony" not in kinds(inp)
    monkeypatch.undo()
    with_condition(monkeypatch, "row-zadarniony", length_min_m="500")
    assert "rów zadarniony" not in kinds(inp)
    monkeypatch.undo()
    with_condition(monkeypatch, "row-zadarniony", length_min_m="5", spi_min="-1")
    assert "rów zadarniony" in kinds(inp)


def test_contour_strip_follows_the_slope_band_of_the_catalogue(monkeypatch) -> None:
    inp = make_input(make_grid(slope_pct=8.0), slope=8.0)
    found = kinds(inp)
    assert "pas konturowy" not in found and "uprawa w poprzek stoku" in found  # the catalogue has no strip row
    with_condition(monkeypatch, "pas-konturowy")
    assert "pas konturowy" in kinds(inp) and "uprawa w poprzek stoku" in kinds(inp)
    with_condition(monkeypatch, "pas-konturowy", slope_min_pct="9", slope_max_pct="20")
    found = kinds(inp)
    assert "pas konturowy" not in found
    assert "uprawa w poprzek stoku" in found  # its own row is unchanged
    monkeypatch.undo()
    with_condition(monkeypatch, "pas-konturowy", slope_min_pct="1", slope_max_pct="2")
    assert "pas konturowy" not in kinds(inp)


def test_a_replaced_reader_in_the_module_is_honoured_too(monkeypatch) -> None:
    rows = catalogue_with_extra_rows()
    monkeypatch.setattr(placement, "load_catalog", lambda: rows)
    assert "pas konturowy" in kinds(make_input(make_grid(slope_pct=8.0), slope=8.0))
    changed = rows["pas-konturowy"].model_copy(
        update={"conditions": {**rows["pas-konturowy"].conditions, "slope_min_pct": "9"}}
    )
    monkeypatch.setattr(placement, "load_catalog", lambda: {**rows, "pas-konturowy": changed})
    assert "pas konturowy" not in kinds(make_input(make_grid(slope_pct=8.0), slope=8.0))


def test_weir_distance_to_the_ditch_comes_from_the_catalogue(monkeypatch) -> None:
    inp = make_input(make_grid(valley=True), water=[ditch_west_of_the_parcel()])
    assert "zastawka" in kinds(inp)
    with_condition(monkeypatch, "zastawka-nowa", ditch_max_m="1")
    assert "zastawka" not in kinds(inp)


# ---------------------------------------------------------------- places


def test_contour_strip_is_across_the_slope_and_carries_its_bearing(monkeypatch) -> None:
    with_condition(monkeypatch, "pas-konturowy")
    candidates = find_places(make_input(make_grid(slope_pct=8.0), slope=8.0))
    strip = next(c for c in candidates if c.kind == "pas konturowy")
    assert strip.bearing_deg == pytest.approx(
        0.0, abs=1.0
    )  # a plane falling west: the contour runs north-south
    assert strip.length_m is not None and strip.length_m >= SIDE
    assert strip.slope_pct == 8.0


def test_waterway_reaches_are_at_least_the_catalogue_length(monkeypatch) -> None:
    with_condition(monkeypatch, "row-zadarniony")
    min_m = catalog.load_catalog()["row-zadarniony"].cond("length_min_m")
    assert min_m == 50.0
    ways = [c for c in find_places(make_input(make_grid(valley=True))) if c.kind == "rów zadarniony"]
    assert ways and all(c.length_m >= min_m for c in ways)


def test_weir_count_for_the_ditch_beside_the_parcel_and_its_slope() -> None:
    inp = make_input(make_grid(valley=True), water=[ditch_west_of_the_parcel()])
    weir = next(c for c in find_places(inp) if c.kind == "zastawka")
    assert weir.n_weirs is not None and weir.n_weirs >= 1
    assert weir.distance_m == pytest.approx(4.0, abs=1.0)
    assert (
        weir.place is not None and weir.place.x_2180 < X0
    )  # the weir stands in the ditch, outside the outline


def test_flat_parcel_has_no_flow_places_but_says_why_for_the_outlet(monkeypatch, tmp_path) -> None:
    write_metrics(
        tmp_path / "metrics.json", {"outlet_hit_d8": 0.9, "outlet_hit_dinf": 0.5, "outlet_hit_lowest": 0.5}
    )
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")
    candidates = find_places(make_input(make_grid(slope_pct=0.0), slope=0.2))
    outlet = next(c for c in candidates if c.kind == "punkt wypływu")
    assert outlet.place is None
    assert "teren płaski" in outlet.reason and "0,2%" in outlet.reason
    assert {c.kind for c in candidates if c.place} <= {"rów", "zbiornik"}


def test_places_have_descriptions_a_clerk_can_read() -> None:
    places = [c.place for c in find_places(make_input(make_grid(valley=True))) if c.place]
    assert places and all(p.description for p in places)
    assert all(re.search(r"[a-ząęółśżźćń]", p.description) for p in places)


# ---------------------------------------------------------------- helpers and limits


def test_stream_power_index_and_weir_count() -> None:
    assert stream_power_index(100.0, 5.0) == pytest.approx(math.log(5.0))
    assert stream_power_index(100.0, 0.0) == -math.inf
    assert weir_count(400.0, 0.5, 0.4) == 5
    assert weir_count(10.0, 0.1, 0.5) == 1


@pytest.mark.parametrize("method", ["d8", "dinf"])
def test_runoff_on_a_200_by_200_grid_takes_at_most_3_seconds(method: str) -> None:
    n = 200
    rng = np.random.default_rng(7)
    x, y = np.arange(n)[None, :] * STEP, np.arange(n)[:, None] * STEP
    z = np.round(100 + 0.03 * x + 2 * np.sin(x / 200) * np.cos(y / 150) + rng.normal(0, 0.2, (n, n)), 1)
    inside = np.zeros((n, n), dtype=int)
    inside[90:110, 90:110] = 1
    grid = ElevationGrid("EPSG:2180", X0, Y0 + n * STEP, STEP, n, n, z.tolist(), inside.tolist())
    ring = [[X0 + 900, Y0 + 900], [X0 + 1100, Y0 + 900], [X0 + 1100, Y0 + 1100], [X0 + 900, Y0 + 1100]] * 1
    ring.append(ring[0])
    started = time.perf_counter()
    result = runoff(PlacementInput(ring, grid, None, [], None), method=method)
    assert time.perf_counter() - started <= 3.0
    assert result.outlets


def test_every_threshold_constant_names_its_source() -> None:
    """A numeric constant in the module is either from the ACPF manual with its PDF page or a team proposal."""
    path = Path(placement.__file__)
    lines = path.read_text(encoding="utf-8").splitlines()
    source = re.compile(r"ACPF.*(PDF page|page|p\.)\s*\d+|Team proposal", re.S)
    checked = []
    for node in ast.parse("\n".join(lines)).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (
            isinstance(target, ast.Name) and target.id.isupper() and isinstance(node.value, ast.Constant)
        ):
            continue
        if not isinstance(node.value.value, int | float):
            continue
        above = []
        i = node.lineno - 2
        while i >= 0 and lines[i].lstrip().startswith("#"):
            above.insert(0, lines[i])
            i -= 1
        text = " ".join(above) + " " + lines[node.lineno - 1]
        assert source.search(text), f"{target.id}: no ACPF page or team-proposal comment"
        checked.append(target.id)
    assert {"FILL_DEPTH_M", "FLOW_LINE_MIN_HA"} <= set(checked)
    assert FILL_DEPTH_M == 0.2
