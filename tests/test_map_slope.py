"""The slope arrows and their label on the photo: always drawn when the fall is determined."""

from __future__ import annotations

import math

from app.mapview import GRID_MAX, GRID_MIN
from tests.test_mapview import DOBRCZ, GSM, built, page, runoff_set, svg


def test_main_arrow_points_west_for_270_degrees(monkeypatch) -> None:
    runoff_set(monkeypatch, downhill_deg=270.0, slope_pct=2.0)
    m = built(DOBRCZ).map
    assert abs(abs(m.slope_main.angle) - 180) <= 5  # 180 = left on the photo
    assert m.slope_label == "spadek 2,0%" and not m.slope_flat
    html = page(DOBRCZ)
    assert "mo-sa--main" in svg(html) and "kierunek spadku" in html


def test_main_arrow_points_north_for_zero_degrees(monkeypatch) -> None:
    runoff_set(monkeypatch, downhill_deg=0.0, slope_pct=1.5)
    m = built(DOBRCZ).map
    assert math.isclose(m.slope_main.angle % 360, 270.0, abs_tol=0.1)  # up on the photo


def test_a_flat_parcel_still_gets_arrows_and_a_label_without_too_small() -> None:
    m = built(DOBRCZ).map  # 0,5%
    assert m.slope_flat and m.slope_main is not None
    assert GRID_MIN <= len(m.slope_grid) <= GRID_MAX
    assert m.slope_label.startswith("Teren płaski · spadek")
    html = page(DOBRCZ)
    assert "za mały" not in html and "jest za mały" not in m.runoff_reason
    assert "Teren płaski" in html


def test_the_small_arrows_lie_inside_the_outline_and_have_a_length_of_10_to_28_px() -> None:
    from app.mapview import _inside

    for params in (DOBRCZ, GSM):
        m = built(params).map
        assert GRID_MIN <= len(m.slope_grid) <= GRID_MAX
        for k in m.slope_grid:
            assert _inside(m.outline_px[0], (k.x, k.y))
            assert 10 <= k.length <= 28


def test_below_the_height_resolution_there_are_no_arrows_but_a_label(monkeypatch) -> None:
    runoff_set(monkeypatch, downhill_deg=10.0, slope_pct=0.05)
    m = built(DOBRCZ).map
    assert m.slope_main is None and m.slope_grid == []
    assert m.slope_label == "teren płaski, kierunek spadku nieznaczący"
    assert "kierunek spadku" not in [r.text for r in m.legend]


def test_the_legend_lists_the_slope_direction_only_when_arrows_are_drawn() -> None:
    for params in (DOBRCZ, GSM):
        m = built(params).map
        assert ("kierunek spadku" in [r.text for r in m.legend]) == (m.slope_main is not None)
