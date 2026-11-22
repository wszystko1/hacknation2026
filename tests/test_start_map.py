"""The map on the start screen in a real browser: zoom, click, outline, the confirmation card, the errors, no other host."""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright  # noqa: E402

from app.main import app  # noqa: E402
from demo.steps import map_pick  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PARCEL = "040303_2.0002.189/13"
BUTTON_ZOOM_IN = "Przybliż mapę"
BUTTON_ZOOM_OUT = "Oddal mapę"


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
        yield browser.new_page(viewport=map_pick.LAPTOP, locale="pl-PL", bypass_csp=True)  # wait_for_function evaluates strings
        browser.close()


@pytest.fixture
def page(browser_page: Page, base_url: str) -> Page:
    browser_page.unroute_all()
    browser_page.set_viewport_size(map_pick.LAPTOP)
    browser_page.goto(base_url + "/")
    map_pick.tiles_loaded(browser_page)
    return browser_page


def point_at_parcel(page: Page) -> None:
    map_pick.zoom_to_parcel(page)
    map_pick.click_parcel(page)
    page.locator(".pm-state .pm-card .pm-title").wait_for(state="visible")


def outline_path(page: Page) -> str:
    return page.locator(".pm-shape .mo-outline").get_attribute("d") or ""


def test_the_start_view_is_the_middle_of_poland_on_the_photo_with_the_empty_caption(page: Page) -> None:
    zoom, lon, lat = map_pick.view(page)
    assert zoom == 9 and 18 < lon < 20 and 51 < lat < 53
    assert page.evaluate("[...document.querySelectorAll('.pm-tile')].every(i => i.src.includes('/orto/9/'))")
    assert page.locator(".pm-state").inner_text() == "Przybliż i kliknij pole albo wpisz numer"
    assert outline_path(page) == ""


@pytest.mark.parametrize("size", [{"width": 1440, "height": 800}, {"width": 390, "height": 844}])
def test_search_card_and_button_are_in_view_and_the_map_fills_the_window(
    browser_page: Page, base_url: str, size: dict
) -> None:
    browser_page.set_viewport_size(size)
    browser_page.goto(base_url + "/")
    map_pick.tiles_loaded(browser_page)
    for locator in (
        browser_page.locator("#start-card"),
        browser_page.get_by_role("button", name="Oceń działkę"),
    ):
        locator.wait_for(state="visible")
        box = locator.bounding_box()
        assert box and box["y"] >= 0 and box["y"] + box["height"] <= size["height"], box
        assert box["x"] >= 0 and box["x"] + box["width"] <= size["width"], box
    box = map_pick.map_box(browser_page)
    assert box["width"] * box["height"] >= 0.85 * size["width"] * size["height"], box
    assert browser_page.evaluate("document.documentElement.scrollHeight <= window.innerHeight")


def test_zoom_buttons_are_large_and_named(page: Page) -> None:
    for name in (BUTTON_ZOOM_IN, BUTTON_ZOOM_OUT):
        box = page.get_by_role("button", name=name).bounding_box()
        assert box and box["width"] >= 44 and box["height"] >= 44, (name, box)


def test_the_photo_from_zoom_9_and_no_zoom_out_beyond_it(page: Page) -> None:
    assert page.evaluate("document.querySelectorAll('.pm-tile').length > 0")
    page.get_by_role("button", name=BUTTON_ZOOM_OUT).click()
    assert map_pick.view(page)[0] == 9  # the photo has empty corners further out, so the map stops here
    map_pick.zoom_to_parcel(page)
    assert map_pick.view(page)[0] == 16
    assert page.evaluate("[...document.querySelectorAll('.pm-tile')].every(i => i.src.includes('/orto/16/'))")
    page.get_by_role("button", name=BUTTON_ZOOM_OUT).click()
    map_pick.tiles_loaded(page)
    assert page.evaluate("document.querySelector('.pm-tile').src.includes('/orto/15/')")
    assert "GUGiK" in page.locator(".map-attr").inner_text()


def test_the_map_centre_cannot_leave_poland(page: Page) -> None:
    for _ in range(12):
        map_pick.drag(page, -300, 0)  # the content follows the pointer: this moves the view east
    _, lon, _ = map_pick.view(page)
    assert lon <= 24.31, lon


def test_this_parcel_fills_the_field_and_moves_focus_to_the_date(page: Page) -> None:
    point_at_parcel(page)
    text = page.locator(".pm-card .pm-title").inner_text()
    assert "189/13" in text and "obręb Dobrcz" in text and "21,53 ha" in text
    assert outline_path(page).startswith("M")
    page.get_by_role("button", name="To ta działka").click()
    assert page.input_value("input[name=dzialka]") == PARCEL
    assert page.evaluate("document.activeElement.id") == "f-data"
    names = page.eval_on_selector_all("form.pick input, form.pick select", "els => els.map(e => e.name)")
    assert names == ["dzialka", "data", "uprawa"]


def test_pick_another_hides_the_card_and_the_outline(page: Page) -> None:
    point_at_parcel(page)
    page.get_by_role("button", name="Wskaż inną").click()
    assert page.locator(".pm-card").count() == 0
    assert outline_path(page) == ""
    assert page.locator(".pm-state").inner_text() == "Przybliż i kliknij pole albo wpisz numer"


def test_a_click_outside_poland_gives_one_sentence_and_the_number_field_still_works(
    page: Page, base_url: str
) -> None:
    for _ in range(14):
        map_pick.drag(page, 300, 0)  # pan west to the edge of the allowed frame
    map_pick.tiles_loaded(page)
    page.mouse.click(
        470, 600
    )  # at the frame edge the left half of the window lies outside Poland, right of the card
    error = page.locator(".pm-state .pm-error")
    error.wait_for(state="visible")
    text = error.inner_text()
    assert "poza Polską" in text and len(re.findall(r"[.!?](?:\s|$)", text)) <= 2, text
    # the form starts with the default parcel; a click outside Poland must not change it
    assert page.input_value("input[name=dzialka]") == PARCEL
    page.locator("#f-dzialka").fill(PARCEL)
    page.locator("#f-data").fill("20.07.2023")
    page.locator("#f-uprawa").select_option("zboza_jare")
    page.get_by_role("button", name="Oceń działkę").first.click()
    page.wait_for_selector(".report-head", timeout=30000)
    assert "21,53 ha" in page.locator(".sub").inner_text()


def test_no_answer_from_the_server_is_a_sentence_next_to_the_map(page: Page) -> None:
    page.route("**/api/dzialka*", lambda route: route.abort())
    page.mouse.click(683, 412)
    page.locator(".pm-state .pm-error").wait_for(state="visible")
    assert page.locator(".pm-state .pm-error").inner_text().startswith("Nie mamy odpowiedzi")
    assert page.locator("#f-dzialka").is_enabled()


def test_the_loading_card_says_what_is_going_on(page: Page) -> None:
    held: list = []
    page.route(
        "**/api/dzialka*", lambda route: held.append(route)
    )  # the answer does not come until we let it
    page.mouse.click(683, 412)
    page.locator(".pm-state .pm-card").wait_for(state="visible")
    assert page.locator(".pm-state .pm-card").inner_text() == "Szukam działki…"
    assert held, "the click did not ask the server"
    held[0].continue_()
    page.locator(".pm-state .pm-card .pm-title, .pm-state .pm-error").wait_for(state="visible")


def test_the_browser_asks_only_our_server(page: Page, base_url: str) -> None:
    hosts: set[str] = set()
    page.on("request", lambda r: hosts.add(r.url.split("/")[2]))
    point_at_parcel(page)
    assert hosts == {base_url.split("//")[1]}, hosts


def test_the_start_html_has_no_external_script_or_stylesheet() -> None:
    html = TestClient(app).get("/").text
    for tag in re.findall(r"<(?:script|link)\b[^>]*>", html, re.I):
        for url in re.findall(r"""(?:src|href)=["']([^"']+)""", tag):
            assert not re.match(r"(https?:)?//", url), tag
    assert "/static/pickmap.js" in html and "/static/pickmap.css" in html


def test_pickmap_script_is_short_and_has_no_libraries() -> None:
    source = (ROOT / "app" / "static" / "pickmap.js").read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 300
    source = source.replace(
        "http://www.w3.org/2000/svg", ""
    )  # the SVG namespace name, not an address we call
    assert not re.search(r"^\s*(import|export)\b|\brequire\(|importScripts|https?://", source, re.M)


_LUMINANCE_JS = """
(rgb) => { const c = rgb.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => { v /= 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }
"""


@pytest.mark.parametrize("size", [{"width": 1440, "height": 800}, {"width": 390, "height": 844}])
def test_search_card_is_a_grey_square_panel_with_a_blue_button_and_readable_text(
    browser_page: Page, base_url: str, size: dict
) -> None:
    browser_page.set_viewport_size(size)
    browser_page.goto(base_url + "/")
    card = browser_page.locator("#start-card")
    card.wait_for(state="visible")
    style = card.evaluate(
        "e => { const s = getComputedStyle(e); return {bg: s.backgroundColor, r: s.borderTopLeftRadius,"
        " r2: s.borderTopRightRadius, w: s.borderTopWidth}; }"
    )
    channels = [float(v) for v in re.findall(r"[\d.]+", style["bg"])[:3]]
    assert max(channels) - min(channels) <= 32 and 15 <= min(channels) < 80, style  # dark slate of the report menu (#1c2633)
    assert style["r"] == "0px" and style["r2"] == "0px" and style["w"] == "1px", style
    button = browser_page.get_by_role("button", name="Oceń działkę")
    bg = [float(v) for v in re.findall(r"[\d.]+", button.evaluate("e => getComputedStyle(e).backgroundColor"))[:3]]
    assert bg[2] > bg[0] + 60 and bg[2] > bg[1] + 40, bg  # blue
    ratios = browser_page.evaluate(
        """(lum => { const L = eval(lum);
          const bg = getComputedStyle(document.getElementById('start-card')).backgroundColor;
          const sel = '#start-card h1, #start-card label, #start-card .start-lead, #start-card .field-hint,'
            + ' #start-card summary, #start-card .ex-go, #start-card .muted';
          return [...document.querySelectorAll(sel)].filter(e => e.offsetParent && e.textContent.trim()).map(e => {
            const a = L(getComputedStyle(e).color), b = L(bg), hi = Math.max(a, b), lo = Math.min(a, b);
            return [e.className || e.tagName, (hi + 0.05) / (lo + 0.05)]; }); })""",
        _LUMINANCE_JS,
    )
    assert ratios and all(r >= 4.5 for _, r in ratios), ratios
