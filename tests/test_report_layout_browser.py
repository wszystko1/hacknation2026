"""The report screen in a real browser: rail 168 px, map 560 px, the report in the rest; 44% below 1180 px; one column on a phone."""

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
    assert width_of(page, "nav.rail") == 168
    assert width_of(page, ".mapcol") == 560
    assert width_of(page, "main.report") == 1280 - 168 - 560


def test_below_1180_px_the_map_takes_44_percent(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1100, 800)
    assert width_of(page, "nav.rail") == 168
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
    page.get_by_role("tab", name="Rekomendacje").click()
    page.evaluate("document.querySelectorAll('details.b-row').forEach(d => { d.open = true; })")
    page.mouse.wheel(0, 1500)
    page.wait_for_timeout(200)
    assert page.evaluate("window.scrollY") > 0
    assert abs(page.evaluate("document.querySelector('.mapcol').getBoundingClientRect().top")) < 1
    assert abs(page.evaluate("document.querySelector('nav.rail').getBoundingClientRect().top")) < 1


def test_report_fills_the_rest_of_the_width_at_1920(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1920, 1080)
    rest = 1920 - 168 - 560
    assert width_of(page, "main.report") >= 0.8 * rest
    # the last content block reaches the right edge of the report: no empty column on its right
    right = page.evaluate(
        "(() => { const r = document.querySelector('main.report'); const kids = [...r.children].filter(e => e.getBoundingClientRect().width);"
        " return Math.max(...kids.map(e => e.getBoundingClientRect().right)) - r.getBoundingClientRect().right; })()"
    )
    assert abs(right) <= 1


def test_sources_panel_is_collapsed_and_does_not_cover_the_parcel(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    assert page.evaluate("document.querySelector('details.ledger').open") is False
    stage = page.evaluate(
        "(() => { const r = document.querySelector('.mapstage').getBoundingClientRect(); return [r.top, r.bottom]; })()"
    )
    dock = page.evaluate("document.querySelector('.mapdock').getBoundingClientRect().top")
    assert dock >= stage[1] - 1, "the dock sits under the map, not over it"
    assert stage[1] - stage[0] > 0.6 * 800
    assert not page.locator(".ledger-body").is_visible()
    page.locator(".ledger > summary").click()
    assert page.locator(".ledger-body").is_visible()
    assert page.evaluate("document.querySelector('.mapdock').getBoundingClientRect().top") >= stage[1] - 400


TABS = ["podsumowanie", "przyczyny", "rekomendacje", "wiarygodnosc", "zrodla"]


def visible_tabs(page: Page) -> list[str]:
    """Names of the tabs whose blocks are on screen (blocks of the summary count as 'podsumowanie')."""
    return page.evaluate(
        "(() => { const out = new Set(); document.querySelectorAll('.report [data-tab]').forEach(e => {"
        " const t = e.getAttribute('data-tab'); if (t !== 'all-details' && e.getClientRects().length) out.add(t); });"
        " return [...out]; })()"
    )


def test_summary_tab_is_active_by_default(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    assert page.get_by_role("tab", name="Podsumowanie").get_attribute("aria-selected") == "true"
    assert page.locator('[role=tab][aria-selected="true"]:visible').count() == 1
    assert visible_tabs(page) == ["podsumowanie"]
    assert page.locator("#zdanie-werdyktu").is_visible()
    assert not page.locator("#poziom-b").is_visible()


@pytest.mark.parametrize(
    "name,label",
    [
        ("przyczyny", "Przyczyny"),
        ("rekomendacje", "Rekomendacje"),
        ("wiarygodnosc", "Wiarygodność"),
        ("zrodla", "Jak liczymy"),
    ],
)
def test_click_opens_only_its_section(page: Page, base_url: str, name: str, label: str) -> None:
    open_report(page, base_url, 1280, 800)
    page.get_by_role("tab", name=label).click()
    assert page.url.endswith("#" + name)
    assert visible_tabs(page) == [name]
    assert page.get_by_role("tab", name=label).get_attribute("aria-selected") == "true"
    assert not page.locator("#zdanie-werdyktu").is_visible()
    assert page.locator(".report-head").is_visible(), "the parcel header stays"


def test_hash_opens_the_section_and_back_returns(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    page.goto(base_url + URL + "#rekomendacje")
    page.wait_for_selector("main.report")
    assert visible_tabs(page) == ["rekomendacje"]
    page.get_by_role("tab", name="Wiarygodność").click()
    assert visible_tabs(page) == ["wiarygodnosc"]
    page.go_back()
    assert visible_tabs(page) == ["rekomendacje"]


def test_keyboard_arrows_move_between_tabs(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    page.get_by_role("tab", name="Podsumowanie").focus()
    page.keyboard.press("ArrowRight")
    assert visible_tabs(page) == ["przyczyny"]
    assert page.evaluate("document.activeElement.getAttribute('data-tab-button')") == "przyczyny"


def test_credibility_tab_has_the_collapsed_jury_tables(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    page.get_by_role("tab", name="Wiarygodność").click()
    row = page.locator("#wiersz-dla-doradcy")
    assert row.get_attribute("open") is None
    row.locator("summary").click()
    assert page.locator("#tabela-2x2").is_visible()


def test_advisor_view_shows_everything_without_tabs(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + URL + "&widok=doradca")
    page.wait_for_selector("main.report")
    assert page.locator("[role=tab]").count() == 0
    assert page.locator("#gmina").is_visible() and page.locator("#zrodla").is_visible()


def test_phone_tabs_sit_in_one_scrolling_row(page: Page, base_url: str) -> None:
    open_report(page, base_url, 390, 844)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    tops = page.evaluate(
        "[...document.querySelectorAll('.tabs [role=tab]')].map(b => Math.round(b.getBoundingClientRect().top))"
    )
    assert len(set(tops)) == 1


def test_desktop_menu_has_labels_and_replaces_the_top_tabs(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    assert not page.locator(".tabs").is_visible()
    rail = page.locator("nav.rail")
    for label in [
        "Nowa ocena",
        "Podsumowanie",
        "Przyczyny",
        "Rekomendacje",
        "Wiarygodność",
        "Jak liczymy",
        "Raport PDF",
    ]:
        assert rail.get_by_text(label, exact=True).is_visible(), label
    rail.get_by_role("tab", name="Jak liczymy").click()
    assert visible_tabs(page) == ["zrodla"]
    assert rail.get_by_role("tab", name="Jak liczymy").get_attribute("aria-selected") == "true"
    assert page.evaluate("document.querySelector('main.report').getBoundingClientRect().right") == 1280


def test_section_headings_are_not_smaller_than_what_they_contain(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1280, 800)
    page.get_by_role("tab", name="Rekomendacje").click()
    page.evaluate("document.querySelectorAll('details').forEach(d => { d.open = true; })")
    size = "s => parseFloat(getComputedStyle(document.querySelector(s)).fontSize)"
    assert page.evaluate(size, "#poziom-b > h2") >= page.evaluate(size, "#poziom-b .b-row > summary")
    assert page.evaluate(size, "#poziom-b .b-row > summary") >= page.evaluate(size, "#poziom-b .b-body p")
    assert page.evaluate(size, ".ledger > summary") >= page.evaluate(size, ".ledger .sources li")
    page.get_by_role("tab", name="Podsumowanie").click()
    assert page.evaluate(size, "#poziom-a h2") >= page.evaluate(size, "#poziom-a .a-do p")
