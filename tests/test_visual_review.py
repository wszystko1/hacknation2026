"""Visual review of the report and start screens in a real browser (Chrome via Playwright).

The sticky report header is opaque, the first screen at 1280x800 holds the answer (badge, number, sentence, threshold bar),
no framed dashed placeholders, the parcel field shows the whole identifier, the date field is Polish.
"""

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
REPORT = "/raport?dzialka=040303_2.0002.189%2F13&data=20.07.2023&uprawa=zboza_jare"


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env={**os.environ, "GEODATA_OFFLINE": "1"},
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
        yield browser.new_page(viewport={"width": 1280, "height": 800}, locale="pl-PL")
        browser.close()


def open_report(page: Page, base_url: str, view: str = "doradca") -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + REPORT + f"&widok={view}")
    page.wait_for_selector("main.report")


def test_header_is_opaque_over_scrolled_content(page: Page, base_url: str) -> None:
    open_report(page, base_url)
    page.evaluate("window.scrollTo(0, 1500)")
    page.wait_for_timeout(200)
    inside = page.evaluate("() => !!document.elementFromPoint(1000, 40).closest('.report-head')")
    assert inside
    alpha = page.evaluate(
        """() => { const c = getComputedStyle(document.querySelector('.report-head')).backgroundColor;
        const m = c.match(/rgba?\\(([^)]+)\\)/)[1].split(',').map(Number); return m.length === 4 ? m[3] : 1; }"""
    )
    assert alpha == 1


def test_header_stays_on_top_at_section_6(page: Page, base_url: str) -> None:
    open_report(page, base_url)
    page.locator("#skrot li").nth(5).locator("a").click()
    page.wait_for_timeout(500)
    box = page.locator(".report-head").bounding_box()
    assert box
    owner = page.evaluate(
        "([x, y]) => !!document.elementFromPoint(x, y).closest('.report-head')",
        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2],
    )
    assert owner


def test_no_dashed_border_in_the_report(page: Page, base_url: str) -> None:
    open_report(page, base_url)
    dashed = page.evaluate(
        """() => [...document.querySelectorAll('.report *')].filter(e => {
        const s = getComputedStyle(e); const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && ['Top', 'Right', 'Bottom', 'Left'].some(d => s['border' + d + 'Style'] === 'dashed' && parseFloat(s['border' + d + 'Width']) > 0);
        }).map(e => e.className)"""
    )
    assert dashed == []


def test_first_screen_of_the_farmer_view_holds_the_verdict_and_what_to_do(page: Page, base_url: str) -> None:
    open_report(page, base_url, "rolnik")
    for selector in ("#plakietka", "#zdanie-werdyktu", "#dzialanie-1"):
        box = page.locator(selector).first.bounding_box()
        assert box, selector
        assert box["y"] >= 0 and box["y"] + box["height"] <= 800, (selector, box)


def test_first_screen_holds_the_answer(page: Page, base_url: str) -> None:
    open_report(page, base_url)
    for selector in (".big-number b", "#plakietka", "#zdanie-werdyktu", "svg.hbar .lbl-thr"):
        box = page.locator(selector).first.bounding_box()
        assert box, selector
        assert box["y"] >= 0 and box["y"] + box["height"] <= 800, (selector, box)
    assert "próg −" in page.locator("svg.hbar .lbl-thr").text_content()


def test_parcel_field_shows_the_whole_identifier(page: Page, base_url: str) -> None:
    for width in (1280, 1366):
        page.set_viewport_size({"width": width, "height": 800})
        for url in (REPORT, "/"):
            page.goto(base_url + url)
            page.wait_for_selector("#f-dzialka")
            page.locator("#f-dzialka").fill(PARCEL)
            fits = page.evaluate(
                "() => { const e = document.getElementById('f-dzialka'); return [e.value, e.scrollWidth <= e.clientWidth]; }"
            )
            assert fits == [PARCEL, True], (width, url, fits)


def test_date_field_is_polish(page: Page, base_url: str) -> None:
    open_report(page, base_url)
    field = page.locator("#f-data")
    assert field.get_attribute("lang") == "pl"
    assert field.input_value() == "20.07.2023"
    assert field.get_attribute("placeholder") == "dd.mm.rrrr"
