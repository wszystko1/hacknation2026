"""A click on a neighbouring field on the report photo: pixel -> lon/lat, the neighbour's outline and card, the link."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from pyproj import Transformer

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from app.datasource import frozen_copy  # noqa: E402
from app.mapview import map_view, px_to_2180, px_to_lonlat  # noqa: E402
from app.models import ReportRequest  # noqa: E402
from app.picker import frozen  # noqa: E402
from app.report import build_context  # noqa: E402
from demo.steps.parcel_photo import screen_point  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LAPTOP = {"width": 1366, "height": 768}
PARCEL = "040303_2.0002.189/13"
DAY = date(2023, 7, 20)
WEST = (18.1300, 53.2705)  # about 160 m west of the parcel
CORNERS = [(0, 0), (1, 0), (0, 1)]
needs_neighbour = pytest.mark.skipif(
    frozen.find(*WEST) is None,
    reason="the frozen copy in demo/data/map has no parcel west of 189/13; freeze it with scripts/freeze_map.py",
)


def overlay():
    req = ReportRequest(parcel_id=PARCEL, day=DAY, crop="zboza_jare")
    view = map_view(build_context(req))
    assert view is not None
    return view


def polygon_centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return cx / (3 * area), cy / (3 * area)


def metres_apart(a: tuple[float, float], b: tuple[float, float]) -> float:
    to_2180 = Transformer.from_crs(4326, 2180, always_xy=True)
    (ax, ay), (bx, by) = to_2180.transform(*a), to_2180.transform(*b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def test_the_centroid_pixel_maps_to_the_centroid_of_the_parcel_within_2_m() -> None:
    view = overlay()
    col, row = polygon_centroid([(x, y) for x, y in view.outline_px[0]])
    expected = frozen_copy(PARCEL, DAY).parcel.data.centroid_4326
    assert metres_apart(px_to_lonlat(view, col, row), (expected[0], expected[1])) < 2.0


def test_the_corners_of_the_photo_are_the_corners_of_its_frame() -> None:
    view = overlay()
    to_4326 = Transformer.from_crs(2180, 4326, always_xy=True)
    for u, v in CORNERS + [(1, 1)]:
        col, row = u * view.width, v * view.height
        exact = to_4326.transform(*px_to_2180(view, col, row))
        assert metres_apart(px_to_lonlat(view, col, row), exact) < 0.5, (u, v)


def test_the_page_carries_what_the_script_needs() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    html = (
        TestClient(app)
        .get("/raport", params={"dzialka": PARCEL, "data": "2023-07-20", "uprawa": "zboza_jare"})
        .text
    )
    for part in ("data-neighbour", "data-corners-4326=", "data-origin-2180=", 'data-day="2023-07-20"',
                 'data-crop="zboza_jare"', "/static/neighbour.js"):  # fmt: skip
        assert part in html, part


# ---------------------------------------------------------------- in a browser


@pytest.fixture(scope="module")
def base_url(tmp_path_factory) -> Iterator[str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "GEODATA_OFFLINE": "1", "GEODATA_CACHE_DIR": str(tmp_path_factory.mktemp("cache"))}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True,
    )  # fmt: skip
    base = f"http://127.0.0.1:{port}"
    try:
        end = time.time() + 60
        while time.time() < end:
            try:
                with urllib.request.urlopen(base + "/health", timeout=3):
                    break
            except OSError:
                time.sleep(0.4)
        else:
            pytest.fail("the server did not start")
        yield base
    finally:
        os.killpg(server.pid, signal.SIGTERM)


@pytest.fixture(scope="module")
def browser_page() -> Iterator[Page]:
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception:  # noqa: BLE001 - fall back to the bundled chromium
            browser = pw.chromium.launch(headless=True)
        yield browser.new_page(viewport=LAPTOP, locale="pl-PL")
        browser.close()


@pytest.fixture
def report_page(browser_page: Page, base_url: str) -> Page:
    browser_page.set_viewport_size(LAPTOP)
    browser_page.goto(f"{base_url}/raport?dzialka={PARCEL}&data=2023-07-20&uprawa=zboza_jare")
    browser_page.wait_for_selector(".map svg .mo-outline")
    browser_page.locator(".map img").wait_for(state="visible")
    return browser_page


@needs_neighbour
def test_a_click_on_the_field_to_the_west_offers_that_parcel(report_page: Page) -> None:
    report_page.mouse.click(*screen_point(report_page, *WEST))
    card = report_page.locator("[data-nb-card]")
    card.locator(".nb-title").wait_for(state="visible", timeout=15000)
    title = card.locator(".nb-title").inner_text()
    assert title.startswith("Sąsiednia działka ") and "189/13" not in title.split("·")[0], title
    href = card.get_by_role("link", name="Otwórz raport tej działki").get_attribute("href") or ""
    assert "data=2023-07-20" in href and "uprawa=zboza_jare" in href, href
    assert PARCEL not in href.replace("%2F", "/")
    assert (report_page.locator(".mo-neighbour").get_attribute("d") or "").startswith("M")
    assert (
        report_page.locator(".mo-neighbour").evaluate("e => getComputedStyle(e).stroke")
        == "rgb(255, 255, 255)"
    )
    card.get_by_role("button", name="Zamknij").click()
    assert not card.is_visible()
    assert report_page.locator(".mo-neighbour").count() == 0


def test_a_click_on_the_outline_of_the_parcel_does_nothing(report_page: Page) -> None:
    report_page.mouse.click(*screen_point(report_page, 18.1353, 53.2705))
    report_page.wait_for_timeout(500)
    assert not report_page.locator("[data-nb-card]").is_visible()
    assert report_page.locator(".mo-neighbour").count() == 0


def test_a_click_on_an_unknown_place_says_so_in_the_card(report_page: Page) -> None:
    """Far from every frozen parcel the server refuses; the card shows its sentence and can be closed."""
    if frozen.find(18.1353, 53.2705) is None:
        pytest.skip("no frozen sample")
    report_page.route(
        "**/api/dzialka*",
        lambda route: route.fulfill(
            status=422,
            content_type="application/json",
            body='{"bledy":[{"field":"dzialka","message":"W tym punkcie nie ma działki ewidencyjnej."}]}',
        ),
    )
    report_page.mouse.click(*screen_point(report_page, *WEST))
    alert = report_page.locator("[data-nb-card] [role=alert]")
    alert.wait_for(state="visible", timeout=15000)
    assert "nie ma działki ewidencyjnej" in alert.inner_text()
    report_page.get_by_role("button", name="Zamknij").click()
    assert not report_page.locator("[data-nb-card]").is_visible()
    report_page.unroute_all()


def test_the_card_outline_and_link_for_an_answer_of_the_server(report_page: Page) -> None:
    """The script's side with a stubbed answer (a square 30 m wide west of the parcel, number 189/12)."""
    lon, lat = WEST
    ring = [
        [lon - 0.0002, lat - 0.0002],
        [lon + 0.0002, lat - 0.0002],
        [lon + 0.0002, lat + 0.0002],
        [lon - 0.0002, lat + 0.0002],
    ]
    body = {
        "dzialka": "040303_2.0002.189/12", "numer": "189/12", "obreb": "Dobrcz", "gmina": "Dobrcz",
        "pow_ha": 3.5, "obrys_4326": [ring + ring[:1]],
    }  # fmt: skip
    report_page.route("**/api/dzialka*", lambda route: route.fulfill(json=body))
    report_page.mouse.click(*screen_point(report_page, *WEST))
    card = report_page.locator("[data-nb-card]")
    card.locator(".nb-title").wait_for(state="visible", timeout=15000)
    assert card.locator(".nb-title").inner_text() == "Sąsiednia działka 189/12 · obręb Dobrcz · 3,50 ha"
    href = card.get_by_role("link", name="Otwórz raport tej działki").get_attribute("href")
    assert href == "/raport?dzialka=040303_2.0002.189%2F12&data=2023-07-20&uprawa=zboza_jare"
    box = report_page.locator(".mo-neighbour").bounding_box()
    assert box and 10 < box["width"] < 120, (
        box
    )  # 0.0004 deg of longitude is about 27 m, at least 10 px on the framed photo
    centre = screen_point(report_page, lon, lat)
    assert box["x"] < centre[0] < box["x"] + box["width"] and box["y"] < centre[1] < box["y"] + box["height"]
    report_page.keyboard.press("Escape")
    assert not card.is_visible()
    report_page.unroute_all()
