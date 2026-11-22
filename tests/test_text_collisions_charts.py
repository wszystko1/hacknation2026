"""Text collisions in the new charts: no text outside the viewBox, over a bar or over another text."""

from __future__ import annotations

import pytest

from app.charts.calendar import calendar_svg
from app.charts.cause_cards import cause_cards_html
from app.charts.schema import schema_svg
from tests.acceptance.helpers import DOBRCZ, report

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

JS = """() => [...document.querySelectorAll('svg')].map(svg => {
  const vb = svg.viewBox.baseVal;
  const boxes = [...svg.querySelectorAll('text')].map(t => { const b = t.getBBox(); return {s: t.textContent, x: b.x, y: b.y, w: b.width, h: b.height}; }).filter(b => b.w > 0);
  const rects = [...svg.querySelectorAll('rect')].map(t => { const b = t.getBBox(); return {x: b.x, y: b.y, w: b.width, h: b.height}; });
  return {vb: [vb.x, vb.y, vb.width, vb.height], boxes, rects, height: svg.getBoundingClientRect().height};
})"""


def _overlap(a: dict, b: dict) -> bool:
    ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return ox > 2 and oy > 2


@pytest.mark.parametrize("width", [1440, 390])
def test_new_charts_have_no_colliding_text(width: int) -> None:
    css = open("app/static/app.css", encoding="utf-8").read()
    pages = [calendar_svg(report(DOBRCZ)), calendar_svg(report(DOBRCZ, uprawa="ziemniak")), schema_svg()]
    pages.append(cause_cards_html(report(DOBRCZ)))
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception:  # noqa: BLE001 - fall back to the bundled chromium
            browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
        checked = 0
        for markup in pages:
            page.set_content(f"<style>{css}</style><div style='max-width:{width - 40}px'>{markup}</div>")
            for chart in page.evaluate(JS):
                checked += 1
                vx, vy, vw, vh = chart["vb"]
                assert chart["height"] <= 260
                for b in chart["boxes"]:
                    assert b["x"] >= vx - 1 and b["x"] + b["w"] <= vx + vw + 1, b["s"]
                    assert b["y"] >= vy - 1 and b["y"] + b["h"] <= vy + vh + 1, b["s"]
                    for r in chart["rects"]:
                        assert not (_overlap(b, r) and r["w"] > 3 and r["h"] > 3), (b["s"], "over a bar")
                for i, a in enumerate(chart["boxes"]):
                    for b in chart["boxes"][i + 1 :]:
                        assert not _overlap(a, b), (a["s"], b["s"])
        browser.close()
    assert checked >= 6
