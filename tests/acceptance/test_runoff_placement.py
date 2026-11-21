"""K1, K3: retention places come from the parcel's geometry; flow accumulation and wet zones only where they win.

The base: a plane z = ax + by + c fitted by least squares to the heights inside the parcel gives the mean slope in %
and the downhill direction; the lower edge is the part of the outline with the lowest heights; the lowest boundary and
interior points, depressions (a cell lower than all eight neighbours) and the nearest BDOT10k ditch complete it. The
rules: a grass strip on the lower edge (along the ditch when the ditch runs by that edge), tillage across the slope
(perpendicular to the downhill direction), a basin at the lowest interior point or in a depression, a weir only on a
ditch by the lower edge. A plane too flat to show a lower edge gets a sentence instead. The module finds the lowest
points from the grid itself.

The extension: D8 flow accumulation (O'Callaghan and Mark 1984) on a grid with a ~300 m margin, and wet zones from
the per-pixel median NDMI of dry periods. It replaces the base only where it scores higher in the ditch test (outlet
within 30 m of a ditch) or in the pond test (AUC at ponds); a tie keeps the base.

The synthetic terrain: a 100 m x 100 m parcel on a plane inside a 700 m x 700 m grid (300 m margin, 10 m cells,
heights rounded to 0.1 m). By default the plane falls 2% to the west.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pytest

X0, Y0 = 500_000.0, 600_000.0  # south-west corner of the parcel, EPSG:2180
SIDE, MARGIN, STEP = 100.0, 300.0, 10.0
VALLEY_Y = Y0 + 55.0  # a row of cell centres
OUTLINE = [[X0, Y0], [X0 + SIDE, Y0], [X0 + SIDE, Y0 + SIDE], [X0, Y0 + SIDE], [X0, Y0]]
PIT = (X0 + 75.0, Y0 + 45.0)  # a cell centre inside the parcel, away from its lowest (west) column


def _grid(
    *,
    fall_west_pct: float = 2.0,
    fall_south_pct: float = 0.0,
    flat: bool = False,
    valley: bool = False,
    pits: tuple[tuple[float, float, float], ...] = (),
):
    """The plane rises to the east by `fall_west_pct` and to the north by `fall_south_pct` (negative: the other way).
    Pits are (x, y, depth): the cell is set `depth` metres below its lowest neighbour."""
    from app.geodata import ElevationGrid

    n = int((SIDE + 2 * MARGIN) / STEP)
    gx0, y_top = X0 - MARGIN, Y0 + SIDE + MARGIN

    def centre(row: int, col: int) -> tuple[float, float]:
        return gx0 + (col + 0.5) * STEP, y_top - (row + 0.5) * STEP

    def base(x: float, y: float) -> float:
        if flat:
            return 100.0
        h = 100.0 + fall_west_pct / 100.0 * (x - X0) + fall_south_pct / 100.0 * (y - Y0)
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


def _ditch(side: str):
    """A ditch 4-8 m outside the west or the east edge, longer than the parcel."""
    from app.geodata import WaterFeature

    a, b = (X0 - 8, X0 - 4) if side == "west" else (X0 + SIDE + 4, X0 + SIDE + 8)
    ring = [[a, Y0 - 250], [b, Y0 - 250], [b, Y0 + 350], [a, Y0 + 350], [a, Y0 - 250]]
    return WaterFeature(kind="ditch", distance_m=4.0, area_m2=2400.0, rings_2180=[ring])


def _input(grid, water=(), slope: float = 2.0):
    from app.advice.placement import PlacementInput

    return PlacementInput(
        outline_2180=OUTLINE,
        grid=grid,
        lowest_outline_point_2180=None,
        water=list(water),
        slope_mean_pct=slope,
    )


def _places(inp, kind: str) -> list:
    from app.advice.placement import find_places

    return [c for c in find_places(inp) if c.kind == kind and c.place is not None]


def _plain(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(ch))


def _near(p, x: float, y: float, tol: float = 20.0) -> bool:
    return abs(p.x_2180 - x) <= tol and abs(p.y_2180 - y) <= tol


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize(
    ("fall_west", "fall_south", "slope_pct", "downhill_deg"),
    [(2.0, 0.0, 2.0, 270.0), (0.0, 3.0, 3.0, 180.0), (-3.0, -4.0, 5.0, 36.87)],
    ids=["west", "south", "north-east"],
)
def test_plane_fit_gives_the_mean_slope_and_the_downhill_direction(
    fall_west: float, fall_south: float, slope_pct: float, downhill_deg: float
) -> None:
    from app.advice.placement import fit_plane

    plane = fit_plane(_grid(fall_west_pct=fall_west, fall_south_pct=fall_south))
    assert plane.slope_pct == pytest.approx(slope_pct, abs=0.2)
    # azimuth of the downhill direction: 0 north, 90 east, 180 south, 270 west
    off = (plane.downhill_deg - downhill_deg + 180.0) % 360.0 - 180.0
    assert abs(off) <= 3.0, plane.downhill_deg


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize(
    ("fall_west", "fall_south", "edge_x", "edge_y"),
    [(2.0, 0.0, X0, None), (0.0, -2.0, None, Y0 + SIDE)],
    ids=["falls-west", "falls-north"],
)
def test_grass_strip_lies_on_the_lower_edge_of_the_outline(
    fall_west: float, fall_south: float, edge_x: float | None, edge_y: float | None
) -> None:
    strips = _places(_input(_grid(fall_west_pct=fall_west, fall_south_pct=fall_south)), "pas trawy")
    assert strips, "a plane falling 2% has a lower edge"
    s = strips[0]
    if edge_x is not None:
        assert abs(s.place.x_2180 - edge_x) <= 15.0, s.place
    if edge_y is not None:
        assert abs(s.place.y_2180 - edge_y) <= 15.0, s.place
    # the lower edge is one side of the square, perhaps with the low ends of its neighbours, never the whole outline
    assert s.length_m is not None and 50.0 <= s.length_m < 2 * SIDE, s.length_m


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_weir_only_on_a_ditch_by_the_lower_edge_and_the_strip_runs_along_it() -> None:
    grid = _grid()  # falls to the west
    by_lower_edge = _input(grid, water=[_ditch("west")])
    weirs = _places(by_lower_edge, "zastawka")
    assert weirs, "the ditch runs along the lower (west) edge"
    for w in weirs:
        assert X0 - 30.0 <= w.place.x_2180 <= X0 + 5.0, w.place
        assert Y0 - 30.0 <= w.place.y_2180 <= Y0 + SIDE + 30.0, w.place
    strips = _places(by_lower_edge, "pas trawy")
    assert strips and re.search(r"\brow(u|em|ie)?\b", _plain(strips[0].place.description)), strips
    assert not _places(_input(grid, water=[_ditch("east")]), "zastawka"), "a ditch by the upper edge"
    assert not _places(_input(grid), "zastawka"), "no ditch"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_depressions_are_cells_inside_the_parcel_lower_than_all_eight_neighbours() -> None:
    from app.advice.placement import depressions

    assert list(depressions(_grid())) == [], "a plane has no depression"
    outside = (X0 - 95.0, Y0 + 45.0)
    found = list(depressions(_grid(pits=((*PIT, 0.3), (*outside, 0.3)))))
    assert any(abs(x - PIT[0]) <= 5.0 and abs(y - PIT[1]) <= 5.0 for x, y in found), found
    assert not any(x < X0 for x, _ in found), "only cells inside the parcel"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_basin_is_at_the_lowest_interior_point_or_in_a_depression() -> None:
    basins = _places(_input(_grid()), "niecka")
    assert basins
    b = basins[0].place
    assert X0 < b.x_2180 < X0 + 20.0 and Y0 < b.y_2180 < Y0 + SIDE, b  # the lowest interior column
    # a 3 m deep pit is both a depression and the lowest interior point
    deep = _places(_input(_grid(pits=((*PIT, 3.0),))), "niecka")
    assert deep and _near(deep[0].place, *PIT, tol=10.0), deep


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize(
    ("fall_west", "fall_south", "rows_deg"),
    [(6.0, 0.0, 0.0), (0.0, 6.0, 90.0)],
    ids=["falls-west", "falls-south"],
)
def test_tillage_runs_across_the_slope(fall_west: float, fall_south: float, rows_deg: float) -> None:
    grid = _grid(fall_west_pct=fall_west, fall_south_pct=fall_south)
    rows = _places(_input(grid, slope=6.0), "uprawa w poprzek stoku")
    assert rows
    # direction of ploughing and sowing as an azimuth in [0, 180): 0 north-south, 90 east-west
    off = abs(rows[0].direction_deg % 180.0 - rows_deg)
    assert min(off, 180.0 - off) <= 5.0, rows[0].direction_deg
    assert not _places(_input(_grid(flat=True), slope=0.0), "uprawa w poprzek stoku")


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_too_flat_plane_gets_a_sentence_instead_of_a_lower_edge() -> None:
    from app.advice.placement import find_places

    candidates = find_places(_input(_grid(flat=True), slope=0.0))
    assert not any(c.kind == "pas trawy" and c.place is not None for c in candidates)
    assert any("spad" in (c.reason or "").lower() for c in candidates), [c.reason for c in candidates]


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_accumulation_outlet_is_where_the_valley_leaves_the_parcel_with_the_neighbours_water() -> None:
    from app.advice.placement import runoff

    r = runoff(_input(_grid(valley=True)))
    assert r.outlets, "no outlet on the boundary"
    top = r.outlets[0]
    assert _near(top, X0, VALLEY_Y), (top.x_2180, top.y_2180)
    # the parcel has 1 ha; the valley drains the land east of it, so only a grid with a margin sees > 5 ha
    assert top.catchment_ha > 5.0
    assert [o.catchment_ha for o in r.outlets] == sorted((o.catchment_ha for o in r.outlets), reverse=True)
    assert any(_near(p, X0 + SIDE, VALLEY_Y) and p.catchment_ha > 5.0 for p in r.inlets)


def _retention_metrics() -> dict:
    return json.loads(Path("metrics.json").read_text(encoding="utf-8")).get("retention", {})


def _winner(m: dict, prefix: str) -> str:
    """The highest score wins; a tie keeps the base ("lowest"), then the simpler D8."""
    order = ("lowest", "d8", "ndmi")
    return max(order, key=lambda k: (m[f"{prefix}_{k}"], -order.index(k)))


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_outlet_comes_from_the_variant_that_wins_the_ditch_test() -> None:
    from app.advice.placement import outlet_method

    m = _retention_metrics()
    keys = {"outlet_hit_lowest", "outlet_hit_d8", "outlet_hit_ndmi", "outlet_hit_random", "outlet_hit_share"}
    assert keys <= set(m), keys - set(m)
    best = _winner(m, "outlet_hit")
    assert outlet_method() == best
    assert m["outlet_hit_share"] == pytest.approx(m[f"outlet_hit_{best}"])


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_basin_comes_from_the_variant_that_wins_the_pond_test() -> None:
    from app.advice.placement import basin_method

    m = _retention_metrics()
    keys = {"pond_auc_lowest", "pond_auc_d8", "pond_auc_ndmi", "pond_auc"}
    assert keys <= set(m), keys - set(m)
    best = _winner(m, "pond_auc")
    assert basin_method() == best
    assert m["pond_auc"] == pytest.approx(m[f"pond_auc_{best}"])


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_readme_cites_classic_methods_compares_the_variants_and_does_not_rest_on_acpf() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert re.search(r"O[’']Callaghan", readme)
    for ref in (
        "1984",
        "najmniejszych kwadratów",
        "NDMI",
        "najniższy punkt granicy",
        "patentu",
        "21.11.2026",
    ):
        assert ref in readme, ref
    assert "ACPF" not in readme
