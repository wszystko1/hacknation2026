"""Margin grid for D8 accumulation: demo copies, point budget, when it is downloaded."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.geodata import fetch_all, fetch_terrain
from app.geodata import orchestrator as orch
from app.geodata import terrain as terrain_mod
from app.geodata.samples import load_sample

from .conftest import fixture_text  # noqa: F401  (keeps the shared fixtures importable)

DEMO = [("040303_2.0002.189/13", "2023-07-20"), ("100403_2.0011.144", "2026-11-21")]
GUGIK = "services.gugik.gov.pl"
# One round of 4 chunks of 1000 points takes about 6 s (docs/notes/siatka-zlewni-czas.md); 25 s fit 3 rounds.
BUDGET_ROUNDS = 3


@pytest.fixture
def parcel():
    from app.geodata.parcel import parse_uldk

    return parse_uldk(fixture_text("uldk_ok.txt"))


@pytest.mark.parametrize(("pid", "day"), DEMO)
def test_demo_copies_carry_a_margin_grid(pid, day, monkeypatch):
    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    sample = load_sample(pid, day)
    terrain, bbox = sample.terrain.data, sample.parcel.data.bbox_2180
    grid = terrain.catchment_grid
    assert grid is not None and terrain.catchment_note
    assert grid.step_m == pytest.approx(10.0)
    east = grid.x0 + grid.cols * grid.step_m
    south = grid.y_top - grid.rows * grid.step_m
    assert bbox[0] - grid.x0 >= 250 and east - bbox[2] >= 250
    assert bbox[1] - south >= 250 and grid.y_top - bbox[3] >= 250
    assert sum(map(sum, grid.inside)) >= 1
    cells = [v for row in grid.z for v in row if v is not None]
    assert len(cells) > 0.99 * grid.rows * grid.cols
    assert all(round(v, 1) == v for v in cells)


def test_plan_fits_the_budget_for_the_large_parcel_and_the_narrow_strip():
    budget = BUDGET_ROUNDS * 4 * terrain_mod.CHUNK
    assert terrain_mod.CATCHMENT_MAX_POINTS <= budget
    for pid, day in DEMO:
        parcel = load_sample(pid, day).parcel.data
        plan = terrain_mod.catchment_plan(parcel)
        assert plan.points <= budget
        assert plan.margin_m >= 250
        full = math.ceil((parcel.bbox_2180[2] - parcel.bbox_2180[0] + 600) / 10) * math.ceil(
            (parcel.bbox_2180[3] - parcel.bbox_2180[1] + 600) / 10
        )
        # 21.53 ha does not fit at 10 m everywhere, so outside the outline the step is 20-30 m
        assert (plan.coarse_k in (2, 3)) == (full > budget)


def test_plan_shrinks_the_margin_when_even_30_m_does_not_fit(parcel):
    plan = terrain_mod.catchment_plan(parcel, max_points=800)
    assert plan.points <= 800 or plan.margin_m == 150
    assert plan.margin_m < 300


def test_coarse_nodes_are_interpolated_to_one_step(parcel):
    plan = terrain_mod.catchment_plan(parcel, max_points=1500)
    coarse_pts, fine_pts = terrain_mod.catchment_points(plan)
    rows, cols = plan.coarse_nodes
    assert len(coarse_pts) == len(rows) * len(cols)
    # a plane rising to the east is reproduced exactly by bilinear interpolation
    plane = np.array([100 + 0.1 * c * 10 for _ in rows for c in cols], dtype=float)
    fine = [100 + 0.1 * c * 10 for r in range(plan.fine_window[0], plan.fine_window[1])
            for c in range(plan.fine_window[2], plan.fine_window[3])]  # fmt: skip
    z = terrain_mod.assemble_catchment(plan, list(plane), fine)
    assert z.shape == (plan.rows, plan.cols)
    expected = 100 + 0.1 * np.arange(plan.cols) * 10
    assert np.allclose(z, expected[None, :])


def test_fetch_without_the_margin_flag_sends_no_margin_queries(net, parcel):
    result = fetch_terrain(parcel)
    main_queries = net.count(GUGIK)
    assert main_queries > 0
    assert result.data.catchment_grid is None and result.data.catchment_note == ""
    fetch_terrain(parcel)  # cached
    assert net.count(GUGIK) == main_queries
    fetch_terrain(parcel, with_catchment=True)
    assert net.count(GUGIK) > main_queries


def test_margin_grid_from_the_service_has_one_step_and_a_note(net, parcel):
    result = fetch_terrain(parcel, with_catchment=True)
    terrain = result.data
    grid = terrain.catchment_grid
    assert grid is not None and grid.step_m == 10.0
    assert "krok 10 m" in terrain.catchment_note and "GUGiK" in terrain.catchment_note
    assert sum(map(sum, grid.inside)) >= 1
    # second call reads both grids from the cache
    net.calls.clear()
    again = fetch_terrain(parcel, with_catchment=True)
    assert net.count(GUGIK) == 0 and again.data.catchment_grid is not None


def test_margin_failure_keeps_the_main_terrain(net, parcel, monkeypatch):
    def broken(*args, **kwargs):
        raise terrain_mod.UpstreamError("height service HTTP 503")

    fetch_terrain(parcel)
    monkeypatch.setattr(terrain_mod, "fetch_catchment_grid", broken)
    result = fetch_terrain(parcel, with_catchment=True)
    assert result.usable and result.data.catchment_grid is None
    assert "nie pobrano" in result.data.catchment_note


@pytest.mark.parametrize(
    ("outlet", "basin", "expected"),
    [("lowest", "lowest", False), ("d8", "lowest", True), ("lowest", "d8", True), ("ndmi", "ndmi", False)],
)
def test_orchestrator_asks_for_the_margin_only_when_d8_won(outlet, basin, expected, monkeypatch):
    from app.advice import placement

    monkeypatch.setattr(placement, "outlet_method", lambda: outlet)
    monkeypatch.setattr(placement, "basin_method", lambda: basin)
    asked = []
    monkeypatch.setattr(
        orch,
        "fetch_terrain",
        lambda parcel, **kw: asked.append(kw["with_catchment"]) or orch.SourceResult("terrain", "skipped"),
    )
    monkeypatch.setattr(orch, "fetch_parcel", lambda pid, deadline=None: _parcel_result())
    fetch_all("040303_2.0002.189/13", "2023-07-20", sources=("terrain",))
    assert asked == [expected]


def test_orchestrator_without_metrics_does_not_ask(monkeypatch):
    from app.advice import placement

    def no_metrics():
        raise FileNotFoundError("metrics.json")

    monkeypatch.setattr(placement, "outlet_method", no_metrics)
    assert orch.d8_wins() is False


def _parcel_result():
    from app.geodata.models import SourceResult
    from app.geodata.parcel import parse_uldk

    return SourceResult("parcel", "ok", parse_uldk(fixture_text("uldk_ok.txt")))


def test_report_route_for_dobrcz_works_offline_from_the_copy(monkeypatch):
    import time

    from app.main import app

    monkeypatch.setenv("GEODATA_OFFLINE", "1")
    client = TestClient(app)
    started = time.monotonic()
    r = client.get("/api/raport?dzialka=040303_2.0002.189/13&data=2023-07-20&uprawa=zboza_jare")
    assert r.status_code == 200
    assert time.monotonic() - started <= 5
