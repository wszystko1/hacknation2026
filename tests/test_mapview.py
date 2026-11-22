"""The photo overlay: outline, outlet, flow lines, BDOT10k water, markers, legend of the layers that are present."""

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
    from app.mapview import _edge_distance, _inside

    m = built(params).map
    first = next(k for k in m.markers if k.n == 1)
    ring = m.outline_px[0]
    assert _inside(ring, (first.x, first.y))
    assert _edge_distance(ring, (first.x, first.y)) >= 1.5


def test_a_point_on_the_boundary_moves_a_few_pixels_in_and_an_inner_point_stays() -> None:
    assert inside_outline(SQUARE, (50.0, 50.0)) == (50.0, 50.0)
    x, y = inside_outline(SQUARE, (0.0, 50.0))
    assert 1.5 <= x <= 4.0 and y == 50.0
    assert inside_outline(SQUARE, (-30.0, 50.0)) == (-30.0, 50.0)  # too far out: left as it is


# ---------------------------------------------------------------- water from BDOT10k


def test_ditch_at_the_parcel_edge_is_drawn_as_mo_ditch() -> None:
    m = built(GSM).map
    assert len(m.ditches_px) >= 1  # BDOT10k ditch 0.7 m from parcel 144
    html = page(GSM)
    assert 'class="mo-ditch"' in svg(html)
    assert "rów lub ciek (BDOT10k)" in html


def test_water_body_is_a_basin_and_a_missing_layer_is_missing_from_the_legend() -> None:
    html = page(DOBRCZ)
    assert 'class="mo-basin"' in svg(html) and 'class="mo-ditch"' not in svg(html)
    legend = re.search(r'<div class="mlegend">.*?</div>\s*</div>', html, flags=re.S).group(0)
    assert "zbiornik wodny" in legend
    for absent in ("rów lub ciek", "linia spływu"):
        assert absent not in legend


# ---------------------------------------------------------------- outlet and flow lines


def test_outlet_falls_back_to_the_lowest_boundary_point() -> None:
    from app.datasource import frozen_copy

    data = frozen_copy(DOBRCZ["dzialka"], date(2023, 7, 20))
    x, y = data.terrain.data.lowest_outline_point_2180
    o = data.ortho.data
    m = built(DOBRCZ).map
    assert m.outlet_px == (
        round((x - o.bbox_2180[0]) / o.m_per_px, 1),
        round((o.bbox_2180[3] - y) / o.m_per_px, 1),
    )
    assert m.outlet_label == ""


def test_outlet_comes_from_the_runoff_analysis_with_its_catchment(monkeypatch) -> None:
    cx, cy = centre_2180(DOBRCZ)
    runoff_set(monkeypatch, outlet_2180=(cx, cy), outlet_catchment_ha=12.4)
    m = built(DOBRCZ).map
    from app.datasource import frozen_copy

    o = frozen_copy(DOBRCZ["dzialka"], date(2023, 7, 20)).ortho.data
    assert m.outlet_px == (
        round((cx - o.bbox_2180[0]) / o.m_per_px, 1),
        round((o.bbox_2180[3] - cy) / o.m_per_px, 1),
    )
    assert m.outlet_label == "zlewnia 12,4 ha"
    html = page(DOBRCZ)
    assert "zlewnia 12,4 ha" in svg(html)
    assert 'class="mo-outlet"' in svg(html)


def test_flow_lines_come_from_the_runoff_analysis_and_end_in_an_arrow(monkeypatch) -> None:
    cx, cy = centre_2180(DOBRCZ)
    line = [(cx + 40, cy + 60), (cx + 10, cy + 20), (cx - 30, cy - 50)]
    runoff_set(monkeypatch, flow_2180=[line])
    m = built(DOBRCZ).map
    assert len(m.flow_px) == 1 and len(m.flow_px[0]) == 3
    assert m.flow_px[0][0][0] > m.flow_px[0][-1][0]  # drawn from the east end to the west end
    assert len(m.flow_heads_px) == 1
    html = page(DOBRCZ)
    assert 'class="mo-flow"' in svg(html) and 'class="mo-arrowhead"' in svg(html)
    assert "linia spływu wody" in html


def test_without_flow_lines_the_svg_has_no_arrows() -> None:
    m = built(DOBRCZ).map
    assert m.flow_px == [] and m.flow_heads_px == []
    assert "mo-arrowhead" not in svg(page(DOBRCZ)) and "mo-flow" not in svg(page(DOBRCZ))


def test_a_reason_instead_of_arrows(monkeypatch) -> None:
    cx, cy = centre_2180(DOBRCZ)
    reason = "spadek 0,3% jest za mały, by wskazać linię spływu"
    runoff_set(monkeypatch, flow_2180=[[(cx, cy), (cx - 40, cy - 40)]], runoff_reason=reason)
    assert built(DOBRCZ).map.flow_px == []
    html = page(DOBRCZ)
    assert "mo-arrowhead" not in svg(html)
    assert f"Spływ wody: {reason}" in html


def test_arrow_head_points_along_the_last_segment() -> None:
    tip, left, right = arrow_head([(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)])
    assert tip == (100.0, 0.0)
    assert left[0] == right[0] < 100.0 and left[1] == -right[1] != 0
    assert arrow_head([(5.0, 5.0)]) is None
