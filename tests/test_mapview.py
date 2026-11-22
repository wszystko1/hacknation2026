"""The photo overlay: outline, BDOT10k water, candidate shapes, pins, legend of the layers that are present."""

from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.report
from app.main import app as web_app
from app.mapview import arrow_head, inside_outline
from app.models import ReportRequest
from app.report import build_report

client = TestClient(web_app)
DOBRCZ = {"dzialka": "040303_2.0002.189/13", "data": "2023-07-20", "uprawa": "zboza_jare"}
GSM = {"dzialka": "100403_2.0011.144", "data": "2026-11-21", "uprawa": "rosliny_straczkowe"}
SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]


def built(params: dict):
    return build_report(
        ReportRequest(
            parcel_id=params["dzialka"], day=date.fromisoformat(params["data"]), crop=params["uprawa"]
        )
    )


def page(params: dict) -> str:
    r = client.get("/raport", params=params)
    assert r.status_code == 200
    return r.text


def svg(html: str) -> str:
    return re.search(r"<svg viewBox=\"[^\"]*\" preserveAspectRatio.*?</svg>", html, flags=re.S).group(0)


def runoff_set(monkeypatch, **fields) -> None:
    """What the runoff analysis would leave in the context, set just before the map is built."""
    real = app.report.map_view

    def patched(ctx):
        for name, value in fields.items():
            setattr(ctx, name, value)
        return real(ctx)

    monkeypatch.setattr(app.report, "map_view", patched)


def centre_2180(params: dict) -> tuple[float, float]:
    from app.datasource import frozen_copy

    cx, cy = frozen_copy(params["dzialka"], date.fromisoformat(params["data"])).parcel.data.centroid_2180
    return cx, cy


# ---------------------------------------------------------------- markers


@pytest.mark.parametrize("params", [DOBRCZ, GSM])
def test_marker_of_action_1_lies_inside_the_outline(params: dict) -> None:
    """A marker exists exactly when the first action has a place; a flat parcel gets the reason instead."""
    from app.mapview import _edge_distance, _inside

    report = built(params)
    m = report.map
    action = next(a for a in report.actions if a.n == 1)
    has_place = action.candidate is not None and action.candidate.geometry is not None
    markers = [k for k in m.markers if k.n == 1]
    if not has_place:
        assert markers == []
        assert action.place is None
        assert action.no_place_reason.startswith("brak miejsca na działce, bo ")
        body = client.get("/api/raport", params=params).json()
        served = body["action_1"]
        assert served["place"] is None
        assert served["no_place_reason"] == action.no_place_reason  # the reason travels with the action
        return
    assert len(markers) == 1
    first = markers[0]
    ring = m.outline_px[0]
    assert _inside(ring, (first.x, first.y))
    if action.candidate.geometry.type != "line":  # a strip lies on the lower boundary: its pin stands on it
        assert _edge_distance(ring, (first.x, first.y)) >= 1.5


def test_at_least_one_demo_parcel_shows_a_numbered_marker_inside_the_outline() -> None:
    from app.mapview import _inside

    placed = 0
    for params in (DOBRCZ, GSM):
        m = built(params).map
        for k in m.markers:
            assert _inside(m.outline_px[0], (k.x, k.y))
            placed += 1
    assert placed >= 1


def test_a_point_on_the_boundary_moves_a_few_pixels_in_and_an_inner_point_stays() -> None:
    assert inside_outline(SQUARE, (50.0, 50.0)) == (50.0, 50.0)
    x, y = inside_outline(SQUARE, (0.0, 50.0))
    assert 1.5 <= x <= 4.0 and y == 50.0
    assert inside_outline(SQUARE, (-30.0, 50.0)) == (-30.0, 50.0)  # too far out: left as it is


# ---------------------------------------------------------------- water from BDOT10k


def test_ditch_and_water_body_are_drawn_as_blue_mo_water_and_listed_once() -> None:
    m = built(GSM).map
    assert len(m.ditches_px) >= 1  # BDOT10k ditch 0.7 m from parcel 144
    html = page(GSM)
    assert 'class="mo-water"' in svg(html)
    assert "rów, ciek lub zbiornik" in html
    assert 'class="mo-basin"' not in svg(html) and "mo-ditch" not in svg(html)


def test_the_legend_has_at_most_four_rows_with_four_different_symbols_and_no_checkboxes() -> None:
    for params in (DOBRCZ, GSM):
        m = built(params).map
        assert len(m.legend) <= 4
        assert len({r.symbol for r in m.legend}) == len(m.legend)
        assert 'type="checkbox"' not in page(params).split('class="mlegend"')[1].split("</div>")[0]


# ---------------------------------------------------------------- candidate shapes, pins, no other arrows


def test_a_strip_is_a_line_with_a_casing_and_the_pin_stands_in_the_middle() -> None:
    m = built(GSM).map
    lines = [sh for sh in m.shapes if sh.kind == "line"]
    assert lines and all(len(sh.points) >= 2 for sh in lines)
    html = svg(page(GSM))
    assert "mo-cand-casing" in html and "mo-cand-line" in html
    for sh in lines:
        pin = next(k for k in m.markers if k.n == sh.n)
        xs, ys = [p[0] for p in sh.points], [p[1] for p in sh.points]
        assert min(xs) - 1 <= pin.x <= max(xs) + 1 and min(ys) - 1 <= pin.y <= max(ys) + 1


def test_a_polygon_candidate_is_filled_and_a_pin_numbers_run_from_one() -> None:
    from app.mapview import _candidate_shape
    from app.models import Action, Candidate, Geometry

    ctx = app.report.build_context(
        ReportRequest(parcel_id=GSM["dzialka"], day=date.fromisoformat(GSM["data"]), crop=GSM["uprawa"])
    )
    cx, cy = centre_2180(GSM)
    ring = [(cx - 5, cy - 5), (cx + 5, cy - 5), (cx + 5, cy + 5), (cx - 5, cy + 5)]
    action = Action.model_construct(
        n=1, candidate=Candidate(geometry=Geometry(type="polygon", coordinates=ring)), place=None
    )
    shape, pin = _candidate_shape(ctx, action)
    assert shape.kind == "polygon" and pin is not None
    for params in (DOBRCZ, GSM):
        numbers = [k.n for k in built(params).map.markers]
        assert numbers == list(range(1, len(numbers) + 1))


def test_there_is_exactly_one_main_slope_arrow_and_no_flow_or_outlet_arrows() -> None:
    for params in (DOBRCZ, GSM):
        html = svg(page(params))
        assert html.count("mo-sa--main") == 1
        assert "mo-flow" not in html and "mo-arrowhead" not in html and "mo-outlet" not in html


def test_arrow_head_points_along_the_last_segment() -> None:
    tip, left, right = arrow_head([(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)])
    assert tip == (100.0, 0.0)
    assert left[0] == right[0] < 100.0 and left[1] == -right[1] != 0
    assert arrow_head([(5.0, 5.0)]) is None
