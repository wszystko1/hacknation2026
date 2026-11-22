"""The report map in a real browser: whole outline in frame, fixed-size pins, slope arrows, zoom overlay, hint."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = {
    "dobrcz": "/raport?dzialka=040303_2.0002.189%2F13&data=20.07.2023&uprawa=zboza_jare",
    "gsm": "/raport?dzialka=100403_2.0011.144&data=20.07.2020&uprawa=zboza_jare",
}


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "GEODATA_OFFLINE": "1"}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
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
def browser() -> Iterator:
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(channel="chrome", headless=True)
        except Exception:  # noqa: BLE001 - fall back to the bundled chromium
            b = pw.chromium.launch(headless=True)
        yield b
        b.close()


def open_report(browser, base_url: str, name: str, width: int, height: int) -> Page:
    page = browser.new_page(viewport={"width": width, "height": height}, locale="pl-PL")
    page.goto(base_url + REPORTS[name])
    page.wait_for_selector(".map svg .mo-outline")
    page.wait_for_timeout(300)
    return page


FRAME_JS = """() => {
  const r = s => { const b = document.querySelector(s).getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
  return {map: r('.map'), outline: r('.mo-outline'), strip: r('.map-strip')};
}"""


@pytest.mark.parametrize("size", [(1440, 900), (1366, 768), (390, 844)])
@pytest.mark.parametrize("name", ["dobrcz", "gsm"])
def test_the_whole_outline_is_in_frame_and_large(browser, base_url: str, name: str, size: tuple[int, int]) -> None:
    page = open_report(browser, base_url, name, *size)
    f = page.evaluate(FRAME_JS)
    page.close()
    m, o, s = f["map"], f["outline"], f["strip"]
    assert o[0] >= m[0] and o[2] <= m[2] and o[1] >= m[1] and o[3] <= s[1] + 1, f
    share = max((o[2] - o[0]) / (m[2] - m[0]), (o[3] - o[1]) / (s[1] - m[1]))
    assert share >= 0.7, f


def test_pins_are_26_px_without_a_tail_and_the_numbers_run_from_one(browser, base_url: str) -> None:
    page = open_report(browser, base_url, "gsm", 1440, 900)
    pins = page.evaluate(
        """() => [...document.querySelectorAll('.mo-pin')].map(p => {
        const b = p.querySelector('circle').getBoundingClientRect(); return [p.textContent.trim(), b.width, b.height]; })"""
    )
    legend = page.locator(".mlegend .lg").count()
    page.close()
    assert [p[0] for p in pins] == [str(i) for i in range(1, len(pins) + 1)] and pins
    assert all(24 <= w <= 28 and 24 <= h <= 28 for _, w, h in pins), pins
    assert legend <= 4


@pytest.mark.parametrize("name", ["dobrcz", "gsm"])
def test_slope_arrows_are_always_drawn_and_nothing_says_too_small(browser, base_url: str, name: str) -> None:
    page = open_report(browser, base_url, name, 1440, 900)
    counts = page.evaluate(
        """() => ({main: document.querySelectorAll('.mo-sa--main').length, small: document.querySelectorAll('.mo-sa--small').length,
        text: document.querySelector('.mapcol').innerText})"""
    )
    page.close()
    assert counts["main"] == 1 and 6 <= counts["small"] <= 12, counts
    assert "za mały" not in counts["text"]
    assert ("Teren płaski" in counts["text"]) == (name == "dobrcz")


def test_zoom_overlay_opens_scales_closes_with_escape_and_returns_focus(browser, base_url: str) -> None:
    page = open_report(browser, base_url, "gsm", 1440, 900)
    button = page.locator("[data-zoom-open]")
    before = page.locator(".map-pan").evaluate("e => getComputedStyle(e).transform")
    button.click()
    assert page.locator(".map.is-zoomed-open").count() == 1
    full = page.locator(".map").evaluate("e => [e.getBoundingClientRect().width, e.getBoundingClientRect().height]")
    assert full == [1440, 900]
    one = page.locator(".map-pan").evaluate("e => getComputedStyle(e).transform")
    page.locator("#map-zoom-range").fill("2")
    two = page.locator(".map-pan").evaluate("e => getComputedStyle(e).transform")
    assert one != two and before != two
    page.keyboard.press("Escape")
    assert page.locator(".map.is-zoomed-open").count() == 0
    assert page.evaluate("document.activeElement.hasAttribute('data-zoom-open')")
    page.close()


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
def test_the_neighbour_hint_is_visible_and_clear_of_the_outline(browser, base_url: str, size) -> None:
    page = open_report(browser, base_url, "gsm", *size)
    hint = page.locator("[data-nb-hint] .hint-mouse")
    assert hint.is_visible() and "sąsiednią działkę" in hint.inner_text()
    hb = page.locator("[data-nb-hint]").bounding_box()
    mb = page.locator(".map").bounding_box()
    page.close()
    assert hb["y"] >= mb["y"] + mb["height"] - 1
