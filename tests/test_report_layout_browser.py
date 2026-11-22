"""The report screen in a real browser: rail 56 px, map 560 px, the report in the rest; 44% below 1180 px; one column on a phone."""

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
PARCEL = "040303_2.0002.189/13"
URL = "/raport?dzialka=040303_2.0002.189%2F13&data=20.07.2023&uprawa=zboza_jare"


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
def page() -> Iterator[Page]:
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception:  # noqa: BLE001 - fall back to the bundled chromium
            browser = pw.chromium.launch(headless=True)
        yield browser.new_page(locale="pl-PL")
        browser.close()


def open_report(page: Page, base_url: str, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(base_url + URL)
    page.wait_for_selector("main.report")


def width_of(page: Page, selector: str) -> float:
    return page.evaluate("s => document.querySelector(s).getBoundingClientRect().width", selector)


def test_desktop_rail_56_map_560_report_wider_than_the_map(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    assert width_of(page, "nav.rail") == 56
    assert width_of(page, ".mapcol") == 560
    assert width_of(page, "main.report") == 1280 - 56 - 560
    assert width_of(page, "main.report") > width_of(page, ".mapcol")


def test_below_1180_px_the_map_takes_44_percent(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1100, 800)
    assert width_of(page, "nav.rail") == 56
    assert abs(width_of(page, ".mapcol") - 0.44 * 1100) <= 2
    assert width_of(page, "main.report") > 400


def test_phone_is_one_column_without_horizontal_scroll(page: Page, base_url: str) -> None:
    open_report(page, base_url, 390, 844)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    mapcol = page.evaluate(
        "(() => { const r = document.querySelector('.mapcol').getBoundingClientRect(); return [r.left, r.width]; })()"
    )
    report = page.evaluate(
        "(() => { const r = document.querySelector('main.report').getBoundingClientRect(); return [r.left, r.top]; })()"
    )
    assert mapcol[0] == 0 and mapcol[1] <= 390
    assert report[0] == 0 and report[1] >= mapcol[1] - 1, "the report sits under the map"


def test_parcel_field_shows_the_whole_number_at_1366(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1366, 768)
    field = page.locator("input[name=dzialka]")
    assert field.input_value() == PARCEL
    assert page.evaluate("e => e.scrollWidth <= e.clientWidth", field.element_handle())


def test_map_stays_while_the_report_scrolls(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(200)
    assert page.evaluate("window.scrollY") > 0
    assert abs(page.evaluate("document.querySelector('.mapcol').getBoundingClientRect().top")) < 1
    assert abs(page.evaluate("document.querySelector('nav.rail').getBoundingClientRect().top")) < 1
