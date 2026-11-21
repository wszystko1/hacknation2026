"""The slope arrow, its label and the lower boundary segment on the photo."""

from __future__ import annotations

import math
import re

from tests.test_mapview import DOBRCZ, GSM, built, centre_2180, page, runoff_set, svg


def test_arrow_points_west_for_270_degrees(monkeypatch) -> None:
    runoff_set(monkeypatch, downhill_deg=270.0, slope_pct=2.0)
    m = built(DOBRCZ).map
    (x0, y0), (x1, y1) = m.slope_arrow_px
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0))  # 180 = left on the photo
    assert abs(abs(angle) - 180) <= 5
    assert m.slope_label == "spadek 2,0%"
    html = page(DOBRCZ)
    assert "spadek 2,0%" in svg(html) and 'class="mo-slope-head"' in svg(html)
    assert "kierunek spadku" in html and "dolny odcinek granicy" not in html


def test_arrow_points_north_for_zero_degrees(monkeypatch) -> None:
    runoff_set(monkeypatch, downhill_deg=0.0, slope_pct=1.0)
    (x0, y0), (x1, y1) = built(DOBRCZ).map.slope_arrow_px
    assert y1 < y0 and abs(x1 - x0) < 1e-6


def test_lower_edge_is_drawn_and_listed(monkeypatch) -> None:
    cx, cy = centre_2180(DOBRCZ)
    runoff_set(monkeypatch, downhill_deg=270.0, slope_pct=2.0, lower_edge_2180=[[cx - 30, cy - 30], [cx - 30, cy + 30]])
    html = page(DOBRCZ)
    assert 'class="mo-lower-edge"' in svg(html)
    assert "dolny odcinek granicy" in html and "kierunek spadku" in html


def test_too_flat_has_no_arrow_and_no_edge_but_a_sentence(monkeypatch) -> None:
    cx, cy = centre_2180(DOBRCZ)
    reason = "spadek 0,3% jest za mały, by wskazać dolny odcinek granicy"
    runoff_set(monkeypatch, downhill_deg=None, slope_pct=0.3, lower_edge_2180=[[cx, cy], [cx, cy + 9]], runoff_reason=reason)
    m = built(DOBRCZ).map
    assert m.slope_arrow_px == [] and m.lower_edge_px == []
    html = page(DOBRCZ)
    assert "mo-slope" not in svg(html) and "mo-lower-edge" not in svg(html)
    assert reason in html
    assert "kierunek spadku" not in html


def test_demo_parcels_show_an_edge_or_a_sentence_and_the_legend_matches_the_svg() -> None:
    for params in (DOBRCZ, GSM):
        html = page(params)
        drawn = svg(html)
        assert "mo-lower-edge" in drawn or "spadek" in html
        legend = re.search(r'class="mlegend".*?</div>\s*</div>', html, flags=re.S)
        text = legend.group(0) if legend else ""
        assert ("kierunek spadku" in text) == ("mo-slope-head" in drawn)
        assert ("dolny odcinek granicy" in text) == ("mo-lower-edge" in drawn)
