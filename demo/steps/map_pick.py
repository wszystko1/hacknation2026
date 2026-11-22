"""Scene "Wskazanie działki na mapie": from the view of Poland to parcel 189/13 with "+" and the wheel, one click, the card.

The helpers also drive the map in tests/test_start_map.py. The map keeps its view in data-zoom, data-lon and data-lat.
"""

from __future__ import annotations

import math
from urllib.parse import urlparse

from app.picker.zoompath import DEMO_CENTRES, FIRST_ZOOM
from demo.steps.common import PAUSE

LAPTOP = {"width": 1366, "height": 768}
PARCEL_ID = "040303_2.0002.189/13"
TARGET = DEMO_CENTRES[PARCEL_ID]  # lon, lat of the parcel centre
FINAL_ZOOM = 16  # the whole parcel (about 460 x 620 m) fits in the frame
BUTTON_PRESSES = 5  # 9 -> 14, the wheel does the rest
TILE = 256


def _world(lon: float, lat: float, z: int) -> tuple[float, float]:
    size = TILE * 2**z
    x = (lon + 180) / 360 * size
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size
    return x, y


def view(page) -> tuple[int, float, float]:
    """(zoom, lon, lat) of the middle of the map."""
    z, lon, lat = page.eval_on_selector(
        "[data-pickmap]", "e => [e.dataset.zoom, e.dataset.lon, e.dataset.lat]"
    )
    return int(z), float(lon), float(lat)


def map_box(page) -> dict:
    return page.locator("[data-pickmap]").bounding_box()


def map_centre(page) -> tuple[float, float]:
    box = map_box(page)
    return box["x"] + box["width"] // 2, box["y"] + box["height"] // 2


def tiles_loaded(page) -> None:
    page.wait_for_function("[...document.querySelectorAll('.pm-tile')].every(i => i.complete)", timeout=20000)


def pixel_of(page, lon: float, lat: float) -> tuple[float, float]:
    """Page coordinates of a point of the earth in the current view."""
    z, mlon, mlat = view(page)
    (cx, cy), (px, py), (sx, sy) = _world(mlon, mlat, z), _world(lon, lat, z), map_centre(page)
    return sx + px - cx, sy + py - cy


def drag(page, dx: int, dy: int) -> None:
    """Pan by (dx, dy) px. The pointer first goes past the click slop, so a short correction is still a drag."""
    sx, sy = map_centre(page)
    sx, sy = sx + 300, sy + 150
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx + 30, sy, steps=3)
    page.mouse.move(sx + dx, sy + dy, steps=3)
    page.mouse.up()


def centre_on(page, lon: float, lat: float) -> None:
    """Drag the map until the point is at its middle (the frozen tiles of the demo lie around that point)."""
    for _ in range(8):
        x, y = pixel_of(page, lon, lat)
        cx, cy = map_centre(page)
        dx, dy = round(cx - x), round(cy - y)
        if abs(dx) < 2 and abs(dy) < 2:
            return
        # one drag stays inside the window: at most 300 px right/left, 150 px up/down
        drag(page, max(-300, min(300, dx)), max(-150, min(150, dy)))
        tiles_loaded(page)


def zoom_to_parcel(page) -> None:
    """Start view of Poland -> drag to Dobrcz -> "+" five times -> wheel up to FINAL_ZOOM, staying centred on the parcel."""
    assert view(page)[0] == FIRST_ZOOM
    centre_on(page, *TARGET)
    plus = page.get_by_role("button", name="Przybliż mapę")
    for _ in range(BUTTON_PRESSES):
        plus.click()
        tiles_loaded(page)
        centre_on(page, *TARGET)
        page.wait_for_timeout(PAUSE // 3)
    while (zoom := view(page)[0]) < FINAL_ZOOM:
        page.mouse.move(*map_centre(page))
        page.mouse.wheel(0, -120)
        assert view(page)[0] == zoom + 1, "one wheel notch is one zoom step"
        tiles_loaded(page)
        centre_on(page, *TARGET)
        page.wait_for_timeout(PAUSE // 3)


def click_parcel(page) -> None:
    page.mouse.click(*pixel_of(page, *TARGET))


def scene(page, base_url: str) -> None:
    previous = page.viewport_size
    page.set_viewport_size(LAPTOP)
    hosts: set[str] = set()
    page.on("request", lambda request: hosts.add(urlparse(request.url).hostname or ""))

    page.goto(base_url + "/")
    assert "Przybliż i kliknij pole albo wpisz numer" in page.locator(".pm-state").inner_text()
    assert view(page)[0] == FIRST_ZOOM
    tiles_loaded(page)
    page.wait_for_timeout(PAUSE)

    zoom_to_parcel(page)
    assert view(page)[0] == FINAL_ZOOM
    page.wait_for_timeout(PAUSE)
    click_parcel(page)

    card = page.locator(".pm-state .pm-card .pm-title")
    card.wait_for(state="visible", timeout=15000)
    text = card.inner_text()
    for part in ("189/13", "obręb Dobrcz", "21,53 ha"):
        assert part in text, f"the card says {text!r}, expected {part!r}"
    assert page.get_by_role("button", name="To ta działka").is_visible()
    assert page.get_by_role("button", name="Wskaż inną").is_visible()
    outline = page.locator(".pm-shape .mo-outline")
    assert (outline.get_attribute("d") or "").startswith("M")
    assert outline.evaluate("e => getComputedStyle(e).stroke") == "rgb(255, 255, 255)"
    box, frame = outline.bounding_box(), map_box(page)
    assert box and box["width"] > 100 and box["height"] > 100, box
    assert frame["x"] <= box["x"] and box["x"] + box["width"] <= frame["x"] + frame["width"], (box, frame)
    assert frame["y"] <= box["y"] and box["y"] + box["height"] <= frame["y"] + frame["height"], (box, frame)
    assert not (hosts - {"127.0.0.1", "localhost"}), f"the browser asked other hosts: {hosts}"
    page.wait_for_timeout(PAUSE)
    if previous:
        page.set_viewport_size(previous)
        page.wait_for_function("document.querySelector('[data-pickmap]').clientWidth > 0")
        tiles_loaded(page)  # the new window may need tiles; the next scene must not cut their requests off
