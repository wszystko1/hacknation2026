"""Terrain model: catchment with a truncation flag, outflow segment, depression regions, and the adviser's line."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.advice import terrain_model as tm
from app.advice.terrain_model import build_terrain_model
from app.geodata import ElevationGrid
from tests.test_placement import MARGIN, OUTLINE, SIDE, STEP, VALLEY_Y, X0, Y0, make_grid, make_input


def _model(grid: ElevationGrid, **kw):
    return build_terrain_model(make_input(grid, **kw), margin_grid=True)


def test_plane_of_three_percent_drains_through_the_downhill_side() -> None:
    m = _model(make_grid(slope_pct=3.0))
    assert m.slope_pct == pytest.approx(3.0, abs=0.2)
    assert m.outflow is not None
    assert all(abs(x - X0) < 1e-6 for x, _ in m.outflow.points_2180)  # the west side falls
    assert m.outflow.share >= tm.OUTFLOW_SHARE
    assert m.catchment_ha is not None and m.catchment_ha >= 1.0
    assert "Zlewnia:" in m.line() and "ha" in m.line() and "≥80%" in m.line()


def test_plane_catchment_reaches_the_edge_of_the_grid() -> None:
    m = _model(make_grid(slope_pct=3.0))
    assert m.catchment_truncated is True
    assert "ucięta przez siatkę: tak" in m.line()


def _hill() -> ElevationGrid:
    """A cone with its top inside the grid: water of the parcel comes only from the cone."""
    n = int((SIDE + 2 * MARGIN) / STEP)
    gx0, y_top = X0 - MARGIN, Y0 + SIDE + MARGIN
    cx, cy = X0 + 150.0, Y0 + SIDE / 2
    z, inside = [], []
    for r in range(n):
        zr, ir = [], []
        for c in range(n):
            x, y = gx0 + (c + 0.5) * STEP, y_top - (r + 0.5) * STEP
            zr.append(round(100.0 - 0.03 * ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 * 10, 1))
            ir.append(int(X0 < x < X0 + SIDE and Y0 < y < Y0 + SIDE))
        z.append(zr)
        inside.append(ir)
    return ElevationGrid(
        crs="EPSG:2180", x0=gx0, y_top=y_top, step_m=STEP, rows=n, cols=n, z=z, inside=inside
    )


def test_catchment_inside_the_grid_is_not_truncated() -> None:
    m = _model(_hill())
    assert m.catchment_ha is not None
    assert m.catchment_truncated is False
    assert "ucięta przez siatkę: nie" in m.line()


def test_flat_parcel_is_flagged_below_resolution() -> None:
    m = _model(make_grid(slope_pct=0.3))
    assert tm.FLAT_FLAG in m.flags
    assert m.outflow is None and m.catchment_ha is None
    assert "poniżej rozdzielczości" in m.reason


def test_valley_with_a_pit_gives_a_depression_with_depth_and_volume() -> None:
    m = _model(make_grid(slope_pct=2.0, valley=True, pits=[(X0 + 52.0, VALLEY_Y, 0.8)]))
    assert m.depressions
    d = m.depressions[0]
    assert d.depth_m >= 0.5 and d.volume_m3 > 0 and d.area_m2 >= STEP * STEP
    assert d.outline_2180[0] == d.outline_2180[-1]
    assert X0 < d.lowest_point_2180[0] < X0 + SIDE


def test_outflow_segment_is_short_for_a_valley() -> None:
    m = _model(make_grid(slope_pct=2.0, valley=True))
    assert m.outflow is not None
    assert m.outflow.length_m < SIDE and m.outflow.share >= tm.OUTFLOW_SHARE


def test_distance_to_a_ditch() -> None:
    from tests.test_placement import ditch

    m = _model(make_grid(slope_pct=3.0), water=[ditch(X0 - 30.0, X0 - 20.0)])
    assert m.ditch_distance_m == pytest.approx(20.0, abs=5.0)


def test_large_grid_is_fast() -> None:
    from app.geodata import ElevationGrid as G

    n = 200
    z = [[round(100 + 0.03 * (c * STEP), 1) for c in range(n)] for _ in range(n)]
    x0, y_top = X0 - 950.0, Y0 + SIDE + 950.0
    inside = [
        [
            int(X0 < x0 + (c + 0.5) * STEP < X0 + SIDE and Y0 < y_top - (r + 0.5) * STEP < Y0 + SIDE)
            for c in range(n)
        ]
        for r in range(n)
    ]
    grid = G(crs="EPSG:2180", x0=x0, y_top=y_top, step_m=STEP, rows=n, cols=n, z=z, inside=inside)
    started = time.monotonic()
    m = _model(grid)
    assert time.monotonic() - started <= 3.0
    assert m.catchment_ha is not None


def test_without_the_margin_grid_the_model_falls_back_with_a_reason() -> None:
    inp = make_input(make_grid(slope_pct=3.0))
    m = build_terrain_model(
        inp, margin_grid=False, missing_reason="siatki zlewni nie pobrano (usługa nie odpowiada)"
    )
    assert m.catchment_ha is None and m.lowest_boundary_2180 is not None
    assert "usługa nie odpowiada" in m.line()
    none = build_terrain_model(make_input(None), margin_grid=False)
    assert none.catchment_ha is None and none.reason and none.line().startswith("Zlewnia: brak")


def test_outline_is_the_one_of_the_tests() -> None:
    assert OUTLINE[0] == [X0, Y0]


# ---- orchestrator and route ----------------------------------------------------------------------------------


def test_orchestrator_takes_the_margin_grid_without_metrics(monkeypatch, tmp_path) -> None:
    from app.advice import placement
    from app.geodata import orchestrator as orch
    from tests.test_catchment_grid import _parcel_result

    monkeypatch.chdir(tmp_path)  # no metrics.json here
    monkeypatch.setattr(placement, "METRICS_PATH", tmp_path / "metrics.json")
    asked = []
    monkeypatch.setattr(
        orch,
        "fetch_terrain",
        lambda parcel, **kw: asked.append(kw["with_catchment"]) or orch.SourceResult("terrain", "skipped"),
    )
    monkeypatch.setattr(orch, "fetch_parcel", lambda pid, deadline=None: _parcel_result())
    orch.fetch_all("040303_2.0002.189/13", "2023-07-20", sources=None, budget_s=5, offline=True)
    assert asked == [True]


@pytest.mark.parametrize(
    "query",
    [
        "dzialka=040303_2.0002.189/13&data=2023-07-20&uprawa=zboza_jare",
        "dzialka=100403_2.0011.144&data=2026-11-21&uprawa=zboza_jare",
    ],
)
def test_adviser_view_has_the_catchment_line(monkeypatch, query: str) -> None:
    from app.main import app

    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    html = TestClient(app).get(f"/raport?{query}&widok=doradca").text
    start = html.index('id="retencja"')
    block = html[start : html.index("</section>", start)]
    assert "Zlewnia" in block
    assert ("ucięta przez siatkę" in block and " ha" in block) or "brak, bo" in block
