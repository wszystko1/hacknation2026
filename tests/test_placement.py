"""Placement base and extension: plane fit, lower boundary segment, lowest points, depressions, D8, variant choice.

The synthetic terrains are planes and valleys on a 10 m grid with heights rounded to 0.1 m, the precision of the
public height model. Thresholds come from the catalogue; a test that changes a row replaces `load_catalog`.
"""

from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.advice import catalog, placement
from app.advice.placement import (
    PlacementInput,
    basin_method,
    depressions,
    find_places,
    fit_plane,
    lower_edge,
    lowest_boundary_point,
    lowest_interior_point,
    outlet_method,
    runoff,
)
from app.geodata import ElevationGrid, WaterFeature

X0, Y0, SIDE, MARGIN, STEP = 500_000.0, 600_000.0, 100.0, 300.0, 10.0
OUTLINE = [[X0, Y0], [X0 + SIDE, Y0], [X0 + SIDE, Y0 + SIDE], [X0, Y0 + SIDE], [X0, Y0]]
VALLEY_Y = Y0 + 55.0


def make_grid(*, slope_pct: float = 2.0, valley: bool = False, pits=()) -> ElevationGrid:
    """A plane falling `slope_pct` to the west; `valley` adds a 5% valley along y = VALLEY_Y; pits (x, y, depth)."""
    n = int((SIDE + 2 * MARGIN) / STEP)
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


def make_input(grid, water=(), **extra) -> PlacementInput:
    return PlacementInput(OUTLINE, grid, None, list(water), 3.0, **extra)


def ditch(x_from: float, x_to: float) -> WaterFeature:
    ring = [[x_from, Y0 - 250], [x_to, Y0 - 250], [x_to, Y0 + 350], [x_from, Y0 + 350], [x_from, Y0 - 250]]
    return WaterFeature(kind="ditch", distance_m=4.0, area_m2=2400.0, rings_2180=[ring])


def kinds(inp: PlacementInput) -> set[str]:
    return {c.kind for c in find_places(inp) if c.place}


def write_metrics(path: Path, retention: dict | None) -> None:
    path.write_text(json.dumps({} if retention is None else {"retention": retention}), encoding="utf-8")


def with_condition(monkeypatch, action_id: str, **conditions: str) -> None:
    """Replace condition columns of one catalogue row, as a changed CSV would."""
    rows = catalog.load_catalog()
    changed = rows[action_id].model_copy(update={"conditions": {**rows[action_id].conditions, **conditions}})
    monkeypatch.setattr(catalog, "load_catalog", lambda: {**rows, action_id: changed})


# ---------------------------------------------------------------- the variant comes from metrics.json


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        (None, "lowest"),
        ({"outlet_hit_share": 0.5}, "lowest"),
        ({"outlet_hit_lowest": 0.5, "outlet_hit_d8": 0.6, "outlet_hit_ndmi": 0.4}, "d8"),
        ({"outlet_hit_lowest": 0.5, "outlet_hit_d8": 0.6, "outlet_hit_ndmi": 0.7}, "ndmi"),
        ({"outlet_hit_lowest": 0.6, "outlet_hit_d8": 0.6, "outlet_hit_ndmi": 0.5}, "lowest"),
        ({"outlet_hit_lowest": 0.5, "outlet_hit_d8": 0.7, "outlet_hit_ndmi": 0.7}, "d8"),
        ({"outlet_hit_lowest": 0.5, "outlet_hit_d8": 0.5, "outlet_hit_ndmi": 0.5}, "lowest"),
        ({"outlet_hit_d8": 0.9, "outlet_hit_ndmi": 0.8}, "lowest"),  # no score of the base to beat
    ],
)
def test_outlet_method_follows_the_best_score_and_keeps_the_base_on_a_tie(
    tmp_path, monkeypatch, scores, expected
) -> None:
    write_metrics(tmp_path / "metrics.json", scores)
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")
    assert outlet_method() == expected


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        (None, "lowest"),
        ({"pond_auc_lowest": 0.55, "pond_auc_d8": 0.62, "pond_auc_ndmi": 0.58}, "d8"),
        ({"pond_auc_lowest": 0.55, "pond_auc_d8": 0.62, "pond_auc_ndmi": 0.71}, "ndmi"),
        ({"pond_auc_lowest": 0.62, "pond_auc_d8": 0.62, "pond_auc_ndmi": 0.5}, "lowest"),
    ],
)
def test_basin_method_follows_the_best_pond_auc(tmp_path, monkeypatch, scores, expected) -> None:
    write_metrics(tmp_path / "metrics.json", scores)
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")
    assert basin_method() == expected


def test_a_missing_or_broken_metrics_file_means_the_base(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "missing.json")
    assert (outlet_method(), basin_method()) == ("lowest", "lowest")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "broken.json")
    assert (outlet_method(), basin_method()) == ("lowest", "lowest")


def test_the_d8_outlet_carries_its_catchment_when_d8_wins(tmp_path, monkeypatch) -> None:
    write_metrics(tmp_path / "metrics.json", {"outlet_hit_lowest": 0.4, "outlet_hit_d8": 0.8})
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")
    outlet = next(c for c in find_places(make_input(make_grid(valley=True))) if c.kind == "punkt wypływu")
    assert outlet.place is not None and outlet.catchment_ha is not None and outlet.catchment_ha > 5.0
    assert abs(outlet.place.y_2180 - VALLEY_Y) <= 20.0
    base = next(c for c in find_places(make_input(make_grid(valley=True))) if c.kind == "punkt wypływu")
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "missing.json")
    again = next(c for c in find_places(make_input(make_grid(valley=True))) if c.kind == "punkt wypływu")
    assert again.catchment_ha is None and base.catchment_ha is not None


def test_the_ndmi_outlet_and_basin_come_from_the_wet_zones_and_fall_back_without_them(
    tmp_path, monkeypatch
) -> None:
    write_metrics(
        tmp_path / "metrics.json",
        {"outlet_hit_lowest": 0.3, "outlet_hit_ndmi": 0.9, "pond_auc_lowest": 0.5, "pond_auc_ndmi": 0.8},
    )
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")
    wet = SimpleNamespace(
        wettest_boundary_2180=[X0 + 50.0, Y0 + SIDE], wettest_interior_2180=[X0 + 55.0, Y0 + 85.0]
    )
    monkeypatch.setattr(placement.importlib, "import_module", lambda name: None)  # the module is "there"
    found = {c.kind: c.place for c in find_places(make_input(make_grid(), wet=wet)) if c.place}
    assert (found["punkt wypływu"].x_2180, found["punkt wypływu"].y_2180) == (X0 + 50.0, Y0 + SIDE)
    assert (found["niecka"].x_2180, found["niecka"].y_2180) == (X0 + 55.0, Y0 + 85.0)
    without = {c.kind: c.place for c in find_places(make_input(make_grid())) if c.place}
    assert without["punkt wypływu"].x_2180 <= X0 + 1.0  # the lowest boundary point, on the west edge


def test_without_the_wet_zones_module_the_base_is_used(tmp_path, monkeypatch) -> None:
    write_metrics(tmp_path / "metrics.json", {"outlet_hit_lowest": 0.3, "outlet_hit_ndmi": 0.9})
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")

    def missing(name: str):
        raise ImportError(name)

    monkeypatch.setattr(placement.importlib, "import_module", missing)
    wet = SimpleNamespace(wettest_boundary_2180=[X0 + 50.0, Y0 + SIDE], wettest_interior_2180=None)
    outlet = next(c for c in find_places(make_input(make_grid(), wet=wet)) if c.kind == "punkt wypływu")
    assert outlet.place is not None and outlet.place.x_2180 <= X0 + 1.0


# ---------------------------------------------------------------- the base


def test_plane_ignores_the_cells_outside_the_parcel() -> None:
    grid = make_grid()
    grid.z[0][0] = 9999.0  # a corner of the margin
    assert fit_plane(grid).slope_pct == pytest.approx(2.0, abs=0.1)


def test_plane_needs_three_cells_with_heights() -> None:
    grid = make_grid()
    grid.inside = [[0] * grid.cols for _ in range(grid.rows)]
    with pytest.raises(ValueError):
        fit_plane(grid)
    assert lower_edge(make_input(grid)) is None


def test_lower_edge_is_a_continuous_part_of_the_outline_on_the_downhill_side() -> None:
    edge = lower_edge(make_input(make_grid()))
    assert edge is not None
    assert 100.0 <= edge.length_m < 2 * SIDE
    assert edge.middle_2180[0] == pytest.approx(X0, abs=1.0)
    steps = np.hypot(*np.diff(np.array(edge.points_2180), axis=0).T)
    assert steps.max() <= STEP * 1.5, "the points follow the outline step by step"


def test_lower_edge_wraps_nothing_when_the_low_part_straddles_the_start_of_the_ring() -> None:
    """The ring starts at the south-west corner, the middle of the lower (west) side lies before its end."""
    shifted = [[X0, Y0 + SIDE], [X0, Y0], [X0 + SIDE, Y0], [X0 + SIDE, Y0 + SIDE], [X0, Y0 + SIDE]]
    inp = PlacementInput(shifted, make_grid(), None)
    edge = lower_edge(inp)
    assert edge is not None and edge.length_m >= 100.0
    assert edge.middle_2180[0] == pytest.approx(X0, abs=1.0)


def test_lowest_points_come_from_the_grid_not_from_the_given_outline_point() -> None:
    inp = PlacementInput(OUTLINE, make_grid(), [X0 + 99.0, Y0 + 1.0])
    x, y = lowest_boundary_point(inp)
    assert x == pytest.approx(X0, abs=1.0) and Y0 <= y <= Y0 + SIDE
    ix, iy = lowest_interior_point(inp)
    assert X0 < ix < X0 + 10.0 and Y0 < iy < Y0 + SIDE
    assert lowest_boundary_point(PlacementInput(OUTLINE, None, None)) is None
    assert lowest_interior_point(PlacementInput(OUTLINE, None, None)) is None


def test_a_depression_needs_all_eight_neighbours_higher_and_known() -> None:
    grid = make_grid(pits=((X0 + 55.0, Y0 + 45.0, 0.5),))
    assert len(depressions(grid)) == 1
    row, col = int((grid.y_top - (Y0 + 45.0)) // STEP), int((X0 + 55.0 - grid.x0) // STEP)
    grid.z[row + 1][col] = None
    assert depressions(grid) == []


def test_a_pit_shallower_than_the_catalogue_depth_is_not_a_basin_place(monkeypatch) -> None:
    pit = ((X0 + 75.0, Y0 + 45.0, 0.1),)
    shallow = next(c for c in find_places(make_input(make_grid(pits=pit))) if c.kind == "niecka")
    assert shallow.place is not None and shallow.place.x_2180 < X0 + 20.0  # the lowest interior column
    deep = next(
        c for c in find_places(make_input(make_grid(pits=((*pit[0][:2], 0.5),)))) if c.kind == "niecka"
    )
    assert deep.place is not None and deep.place.x_2180 == pytest.approx(X0 + 75.0, abs=6.0)
    with_condition(monkeypatch, "niecka-przy-wyplywie", depression_min_m="1")
    again = next(
        c for c in find_places(make_input(make_grid(pits=((*pit[0][:2], 0.5),)))) if c.kind == "niecka"
    )
    assert again.place is not None and again.place.x_2180 < X0 + 20.0


# ---------------------------------------------------------------- thresholds come from the catalogue


def test_the_smallest_slope_of_the_strip_row_decides_on_a_one_percent_plane(monkeypatch) -> None:
    inp = make_input(make_grid(slope_pct=1.0))
    assert "pas trawy" in kinds(inp)  # the catalogue's 0.5% is below 1%
    with_condition(monkeypatch, "pas-trawy-przy-wyplywie", slope_min_pct="1.5")
    assert "pas trawy" not in kinds(inp)
    strip = next(c for c in find_places(inp) if c.kind == "pas trawy")
    assert strip.place is None and strip.reason.startswith("spadek 1,")
    with_condition(monkeypatch, "pas-trawy-przy-wyplywie", slope_min_pct="0.8")
    assert "pas trawy" in kinds(inp)


def test_the_slope_band_of_the_tillage_row_comes_from_the_catalogue(monkeypatch) -> None:
    inp = make_input(make_grid(slope_pct=8.0))
    assert "uprawa w poprzek stoku" in kinds(inp)
    with_condition(monkeypatch, "uprawa-w-poprzek-stoku", slope_min_pct="9")
    assert "uprawa w poprzek stoku" not in kinds(inp)
    with_condition(monkeypatch, "uprawa-w-poprzek-stoku", slope_min_pct="1", slope_max_pct="5")
    assert "uprawa w poprzek stoku" not in kinds(inp)


def test_ditch_distances_of_the_weir_and_the_strip_come_from_the_catalogue(monkeypatch) -> None:
    far = make_input(make_grid(), water=[ditch(X0 - 45, X0 - 40)])  # 40 m from the lower edge
    assert "zastawka" not in kinds(far)
    with_condition(monkeypatch, "zastawka-nowa", ditch_max_m="50")
    assert "zastawka" in kinds(far)
    strip = next(c for c in find_places(far) if c.kind == "pas trawy")
    assert "rowu" not in strip.place.description  # the strip row keeps its own 30 m
    with_condition(monkeypatch, "pas-trawy-przy-wyplywie", ditch_max_m="50")
    strip = next(c for c in find_places(far) if c.kind == "pas trawy")
    assert "rowu" in strip.place.description


# ---------------------------------------------------------------- places


def test_strip_and_weir_carry_length_distance_and_slope() -> None:
    inp = make_input(make_grid(), water=[ditch(X0 - 8, X0 - 4)])
    found = {c.kind: c for c in find_places(inp)}
    strip = found["pas trawy"]
    assert strip.length_m == strip.place.length_m and strip.length_m >= 100.0
    assert strip.place.description == "wzdłuż rowu na zachodniej granicy"
    assert strip.slope_pct == pytest.approx(2.0, abs=0.1)
    assert found["zastawka"].distance_m == pytest.approx(4.0, abs=1.0)
    assert found["rów"].place is not None


def test_without_a_ditch_the_strip_description_names_only_the_side() -> None:
    strip = next(c for c in find_places(make_input(make_grid())) if c.kind == "pas trawy")
    assert strip.place.description == "na zachodniej granicy"


def test_tillage_direction_is_stored_on_the_place_too() -> None:
    rows = next(
        c for c in find_places(make_input(make_grid(slope_pct=6.0))) if c.kind == "uprawa w poprzek stoku"
    )
    assert (
        rows.direction_deg == pytest.approx(0.0, abs=1.0) and rows.place.direction_deg == rows.direction_deg
    )


def test_a_flat_parcel_gets_sentences_with_the_slope_and_no_place_for_the_slope_rules() -> None:
    candidates = find_places(make_input(make_grid(slope_pct=0.0)))
    by_kind = {c.kind: c for c in candidates}
    assert by_kind["pas trawy"].reason == "spadek 0,0% jest za mały, by wskazać dolny odcinek granicy"
    assert by_kind["punkt wypływu"].place is None and "spadek" in by_kind["punkt wypływu"].reason
    assert by_kind["niecka"].place is None and "spadek" in by_kind["niecka"].reason
    assert "uprawa w poprzek stoku" not in by_kind
    assert by_kind["pas trawy"].no_place_reason.startswith("brak miejsca na działce, bo spadek")


def test_a_gently_tilted_parcel_keeps_its_lowest_points_but_has_no_lower_edge() -> None:
    by_kind = {c.kind: c for c in find_places(make_input(make_grid(slope_pct=0.3)))}
    assert by_kind["pas trawy"].place is None and by_kind["pas trawy"].reason.startswith("spadek 0,3%")
    assert by_kind["punkt wypływu"].place is not None and by_kind["punkt wypływu"].place.x_2180 <= X0 + 11.0
    assert by_kind["niecka"].place is not None


def test_a_slope_just_below_the_minimum_is_not_written_as_the_minimum() -> None:
    tilt = 0.47  # reads "0,5%" with one decimal, the catalogue minimum is 0.5%
    strip = next(c for c in find_places(make_input(make_grid(slope_pct=tilt))) if c.kind == "pas trawy")
    assert strip.place is None and strip.reason.startswith("spadek 0,4")


def test_a_flat_parcel_with_a_real_depression_still_gets_a_basin() -> None:
    inp = make_input(make_grid(slope_pct=0.0, pits=((X0 + 55.0, Y0 + 45.0, 0.5),)))
    basin = next(c for c in find_places(inp) if c.kind == "niecka")
    assert basin.place is not None and basin.place.description.startswith("zagłębieniu")


def test_without_a_grid_the_reason_is_the_missing_grid_and_a_given_lowest_point_is_kept() -> None:
    candidates = find_places(PlacementInput(OUTLINE, None, None))
    assert [c.kind for c in candidates] == ["punkt wypływu"] and candidates[0].place is None
    assert candidates[0].no_place_reason == "brak miejsca na działce, bo brak siatki wysokości dla działki"
    kept = find_places(PlacementInput(OUTLINE, None, [X0 + 3, Y0 + 40]))
    assert kept[0].place is not None and kept[0].place.x_2180 == X0 + 3


def test_places_have_descriptions_a_clerk_can_read() -> None:
    inp = make_input(make_grid(slope_pct=6.0, valley=True), water=[ditch(X0 - 8, X0 - 4)])
    places = [c.place for c in find_places(inp) if c.place]
    assert {p.kind for p in places} >= {
        "punkt wypływu",
        "pas trawy",
        "niecka",
        "uprawa w poprzek stoku",
        "zastawka",
    }
    assert all(re.search(r"[a-ząęółśżźćń]{4}", p.description) for p in places)


# ---------------------------------------------------------------- D8, the extension


def test_a_flat_parcel_gets_a_sentence_instead_of_flow_lines() -> None:
    r = runoff(make_input(make_grid(slope_pct=0.3)))
    assert r.flow_lines == [] and r.outlets == []
    assert r.reason == "spadek 0,3% jest za mały, by wskazać linię spływu"
    assert runoff(PlacementInput(OUTLINE, None, None)).reason == "brak siatki wysokości dla działki"


def test_on_a_plane_all_the_water_of_the_grid_leaves_through_its_west_edge() -> None:
    surface = placement._build_surface(make_grid())
    edge = np.zeros((surface.rows, surface.cols), dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    total_ha = surface.rows * surface.cols * STEP * STEP / 10_000.0
    assert surface.flow.acc_ha[edge.ravel()].sum() == pytest.approx(total_ha, rel=0.01)


def test_a_pit_is_filled_so_its_water_still_leaves_the_grid() -> None:
    surface = placement._build_surface(make_grid(pits=((X0 + 55.0, VALLEY_Y, 0.5),)))
    edge = np.zeros((surface.rows, surface.cols), dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    total_ha = surface.rows * surface.cols * STEP * STEP / 10_000.0
    assert surface.flow.acc_ha[edge.ravel()].sum() == pytest.approx(total_ha, rel=0.01)


def test_runoff_is_deterministic_and_has_flow_lines_in_the_valley() -> None:
    grid = make_grid(valley=True)
    a, b = runoff(make_input(grid)), runoff(make_input(grid))
    assert a == b and a.flow_lines


# ---------------------------------------------------------------- limits and wording of the module


def test_fit_plane_and_find_places_on_a_200_by_200_grid_take_at_most_a_second() -> None:
    n = 200
    rng = np.random.default_rng(7)
    x, y = np.arange(n)[None, :] * STEP, np.arange(n)[:, None] * STEP
    z = np.round(100 + 0.03 * x + 2 * np.sin(x / 200) * np.cos(y / 150) + rng.normal(0, 0.2, (n, n)), 1)
    inside = np.zeros((n, n), dtype=int)
    inside[90:110, 90:110] = 1
    grid = ElevationGrid("EPSG:2180", X0, Y0 + n * STEP, STEP, n, n, z.tolist(), inside.tolist())
    ring = [[X0 + 900, Y0 + 900], [X0 + 1100, Y0 + 900], [X0 + 1100, Y0 + 1100], [X0 + 900, Y0 + 1100]]
    ring.append(ring[0])
    started = time.perf_counter()
    plane = fit_plane(grid)
    candidates = find_places(PlacementInput(ring, grid, None, [], None))
    assert time.perf_counter() - started <= 1.0
    assert plane.slope_pct > 0 and any(c.kind == "pas trawy" for c in candidates)


def test_the_module_does_not_rest_on_the_removed_methods() -> None:
    text = Path(placement.__file__).read_text(encoding="utf-8").lower()
    for word in ("acpf", "dinf", "stream_power", "weir_count", "d-infinity", "contour strip"):
        assert word not in text, word


def test_every_numeric_constant_of_the_module_is_marked_as_a_team_proposal_or_a_step() -> None:
    lines = Path(placement.__file__).read_text(encoding="utf-8").splitlines()
    checked = []
    for node in ast.parse("\n".join(lines)).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not (
            isinstance(target, ast.Name) and target.id.isupper() and isinstance(node.value, ast.Constant)
        ):
            continue
        if not isinstance(node.value.value, int | float):
            continue
        above, i = [], node.lineno - 2
        while i >= 0 and lines[i].lstrip().startswith("#"):
            above.insert(0, lines[i])
            i -= 1
        assert re.search(r"Team proposal|A sampling step", " ".join(above)), target.id
        checked.append(target.id)
    assert {"LOWER_EDGE_FRACTION", "FLAT_GRADIENT_M", "FLOW_LINE_MIN_HA", "POINT_SPACING_M"} <= set(checked)


# ---------------------------------------------------------------- the report's route


def test_the_report_action_for_the_outlet_uses_the_base_and_states_a_missing_slope() -> None:
    from tests.acceptance.helpers import GSM_TODAY, report

    r = report(GSM_TODAY)
    retention = [a for a in r.actions if a.group == "retencja"]
    assert retention
    for a in retention:
        assert a.place is not None or "spadek" in a.no_place_reason or "brak" in a.no_place_reason
        text = f"{a.title} {a.sentence} {a.no_place_reason}".lower()
        assert "acpf" not in text and "rów zadarniony" not in text and "pas konturowy" not in text
