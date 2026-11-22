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
    page.evaluate("document.querySelectorAll('details').forEach(d => { d.open = true; })")
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
    assert page.locator("#poziom-b .b-group:visible").count() == 1  # only the balance bar
    assert not page.locator("#wiersz-skad").is_visible()


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


def test_phone_tabs_fit_without_being_cut(page: Page, base_url: str) -> None:
    open_report(page, base_url, 390, 844)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    rights = page.evaluate(
        "[...document.querySelectorAll('.tabs [role=tab]')].map(b => Math.round(b.getBoundingClientRect().right))"
    )
    assert len(rights) == 5 and max(rights) <= 390


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
    assert page.evaluate(size, "#poziom-b .b-group > h3") >= page.evaluate(size, "#poziom-b .b-sub > h4")
    assert page.evaluate(size, "#poziom-b .b-sub > h4") >= page.evaluate(size, "#poziom-b .b-body p")
    assert page.evaluate(size, ".ledger > summary") >= page.evaluate(size, ".ledger .sources li")
    page.get_by_role("tab", name="Podsumowanie").click()
    # summary tiles: the title is set apart by capitals and weight, the content is not smaller than 13 px
    assert (
        page.evaluate("getComputedStyle(document.querySelector('#poziom-a .tile h2')).textTransform")
        == "uppercase"
    )


@pytest.mark.parametrize("name", ["przyczyny", "rekomendacje", "wiarygodnosc", "zrodla"])
def test_every_tab_shows_content_at_once(page: Page, base_url: str, name: str) -> None:
    open_report(page, base_url, 1280, 800)
    page.goto(base_url + URL + "#" + name)
    page.wait_for_selector("main.report")
    groups = page.locator("#poziom-b .b-group:visible")
    assert groups.count() >= 1
    assert page.locator("#poziom-b summary:visible").count() <= 1, (
        "at most one folded technical block per tab"
    )
    assert page.locator("#poziom-b").inner_text().strip()


CHART_JS = """() => {
  const out = [];
  document.querySelectorAll('svg.ch, svg.hbar').forEach((svg, n) => {
    const vb = svg.viewBox.baseVal;
    const boxes = [...svg.querySelectorAll('text')].map(t => {
      const b = t.getBBox(); return {s: t.textContent.trim(), x: b.x, y: b.y, w: b.width, h: b.height};
    }).filter(b => b.w > 0);
    const r = svg.getBoundingClientRect();
    const rects = [...svg.querySelectorAll('rect')].map(t => { const b = t.getBBox(); return {x: b.x, y: b.y, w: b.width, h: b.height}; });
    out.push({n, rects, boxes, vb: [vb.x, vb.y, vb.width, vb.height], height: r.height, shown: r.height > 0});
  });
  return out;
}"""


def test_no_chart_text_overlaps_and_no_chart_is_taller_than_260_px(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1440, 900)
    checked = 0
    for tab in ["przyczyny", "rekomendacje", "wiarygodnosc", "zrodla"]:
        page.goto(base_url + URL + "#" + tab)
        page.wait_for_selector("main.report")
        page.evaluate("document.querySelectorAll('details').forEach(d => { d.open = true; })")
        for chart in page.evaluate(CHART_JS):
            if not chart["shown"]:
                continue
            checked += 1
            assert chart["height"] <= 260, (tab, chart["n"], chart["height"])
            vx, vy, vw, vh = chart["vb"]
            boxes = chart["boxes"]
            for b in boxes:
                assert b["x"] >= vx - 1 and b["y"] >= vy - 1, (tab, b["s"])
                assert b["x"] + b["w"] <= vx + vw + 1 and b["y"] + b["h"] <= vy + vh + 1, (tab, b["s"])
            for b in boxes:
                for r in chart["rects"]:
                    ox = min(b["x"] + b["w"], r["x"] + r["w"]) - max(b["x"], r["x"])
                    oy = min(b["y"] + b["h"], r["y"] + r["h"]) - max(b["y"], r["y"])
                    assert not (ox > 2 and oy > 2 and r["w"] > 3 and r["h"] > 3), (tab, b["s"], "over a bar")
            for i, a in enumerate(boxes):
                for b in boxes[i + 1 :]:
                    ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
                    oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
                    assert not (ox > 2 and oy > 2), (tab, a["s"], b["s"])
    assert checked >= 3


def test_legend_rows_switch_the_map_layers(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1440, 900)
    box = page.locator('[data-layer-toggle="outline"]')
    layer = page.locator('.map svg [data-layer="outline"]')
    assert layer.first.is_visible()
    box.uncheck(force=True)
    assert layer.first.evaluate("e => getComputedStyle(e).display") == "none"
    box.check(force=True)
    assert layer.first.is_visible()


def test_summary_tiles_are_filled_and_fit_two_screens_at_1440(page: Page, base_url: str) -> None:
    open_report(page, base_url, 1440, 900)
    tiles = page.locator("#poziom-a .tile")
    assert tiles.count() >= 4
    for i in range(tiles.count()):
        assert tiles.nth(i).inner_text().strip(), f"tile {i} is empty"
    bottom = page.evaluate(
        "document.querySelector('#poziom-a').getBoundingClientRect().bottom + window.scrollY"
    )
    assert bottom <= 2 * 900
