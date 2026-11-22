"""The report in a real browser: colours, four text sizes, readable charts,
lists, links, duplicates, the map frame and the phone layout. Dobrcz and the narrow parcel in Góra Świętej Małgorzaty."""

from __future__ import annotations

import colorsys
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

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REPORTS = {
    "dobrcz": "/raport?dzialka=040303_2.0002.189%2F13&data=20.07.2023&uprawa=zboza_jare",
    "gsm": "/raport?dzialka=100403_2.0011.144&data=20.07.2020&uprawa=zboza_jare",
}
TABS = ["podsumowanie", "przyczyny", "rekomendacje", "wiarygodnosc", "zrodla"]


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


def open_report(browser, base_url: str, name: str, width: int = 1440, height: int = 900) -> Page:
    page = browser.new_page(viewport={"width": width, "height": height}, locale="pl-PL")
    page.goto(base_url + REPORTS[name])
    page.wait_for_selector("main.report")
    return page


def show_tab(page: Page, tab: str) -> None:
    page.locator(f'[data-tab-button="{tab}"]:visible').first.click()
    page.wait_for_selector(f'[data-tab-button="{tab}"][aria-selected="true"]:visible')


def css_text() -> str:
    return (ROOT / "app/static/app.css").read_text(encoding="utf-8")


def token(name: str) -> str:
    m = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", css_text())
    assert m, name
    return m.group(1)


def luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def hue(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


# ---------- colours ----------


def test_shortfall_is_orange_and_the_accent_is_blue_with_readable_contrast() -> None:
    assert 15 <= hue(token("danger")) <= 30
    assert 205 <= hue(token("accent")) <= 230
    assert 205 <= hue(token("accent-ink")) <= 230
    for text, ground in (
        ("danger", "surface"),
        ("danger", "danger-soft"),
        ("warn", "surface"),
        ("accent-ink", "surface"),
    ):
        assert contrast(token(text), token(ground)) >= 4.5, (text, ground)
    assert contrast(token("accent-text"), token("danger")) >= 4.5  # the white word on the orange badge
    assert contrast(token("accent-text"), token("accent")) >= 4.5


# ---------- four text sizes, readable chart text ----------

SIZES_JS = """() => {
  const sizes = new Set();
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('svg')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    sizes.add(cs.fontSize);
  }
  return [...sizes];
}"""

SVG_TEXT_JS = """() => [...document.querySelectorAll('main.report svg')].filter(s => s.getBoundingClientRect().width > 0)
  .flatMap(svg => [...svg.querySelectorAll('text')].map(t => ({s: t.textContent, h: t.getBoundingClientRect().height / 1.15}))
  .filter(t => t.h > 0))"""


@pytest.mark.parametrize("name", ["dobrcz", "gsm"])
def test_the_whole_report_uses_at_most_four_text_sizes(browser, base_url: str, name: str) -> None:
    page = open_report(browser, base_url, name)
    sizes: set[str] = set()
    for tab in TABS:
        show_tab(page, tab)
        sizes |= set(page.evaluate(SIZES_JS))
    page.close()
    assert len(sizes) <= 4, sorted(sizes)
    assert "28px" in sizes  # the verdict number


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("name", ["dobrcz", "gsm"])
def test_text_inside_charts_is_at_least_10_px_after_scaling(
    browser, base_url: str, name: str, width: int
) -> None:
    page = open_report(browser, base_url, name, width)
    seen = 0
    for tab in TABS:
        show_tab(page, tab)
        for t in page.evaluate(SVG_TEXT_JS):
            seen += 1
            assert t["h"] >= 10, (tab, t["s"], round(t["h"], 1))
    page.close()
    assert seen > 20


COLLISION_JS = """() => [...document.querySelectorAll('svg.ch')].filter(s => s.getBoundingClientRect().width > 0).map(svg => ({
  title: (svg.querySelector('title') || {}).textContent,
  boxes: [...svg.querySelectorAll('text')].map(t => { const b = t.getBBox(); return {s: t.textContent, x: b.x, y: b.y, w: b.width, h: b.height}; })
    .filter(b => b.w > 0),
}))"""


def collisions(boxes: list[dict]) -> list[tuple[str, str]]:
    found = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ox > 0.01 and oy > 0.01:
                found.append((a["s"], b["s"]))
    return found


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("name", ["dobrcz", "gsm"])
def test_no_two_texts_of_a_chart_touch(browser, base_url: str, name: str, width: int) -> None:
    page = open_report(browser, base_url, name, width)
    charts = 0
    for tab in ["podsumowanie", "przyczyny", "wiarygodnosc"]:
        show_tab(page, tab)
        for chart in page.evaluate(COLLISION_JS):
            charts += 1
            assert not collisions(chart["boxes"]), (tab, chart["title"], collisions(chart["boxes"]))
    page.close()
    assert charts >= 3


def test_the_history_chart_marks_the_smsr_years_without_overlapping_words(browser, base_url: str) -> None:
    page = open_report(browser, base_url, "dobrcz")
    show_tab(page, "przyczyny")
    svg = page.locator("#wiersz-czesto svg.ch")
    assert svg.count() == 1
    dots = svg.locator("circle.s-dry").count()
    assert dots == 3  # 2022 and 2023 in the chart plus the legend entry
    texts = svg.locator("text").evaluate_all("els => els.map(e => e.textContent)")
    assert texts.count("SMSR") == 1 and "susza" in texts
    page.close()


def test_the_calibration_label_does_not_lie_on_the_parcel_line(browser, base_url: str) -> None:
    page = open_report(browser, base_url, "dobrcz")
    show_tab(page, "wiarygodnosc")
    r = page.evaluate(
        """() => {
      const svg = document.querySelector('svg.ch:has(line[data-marker])');
      const line = svg.querySelector('line[data-marker]').getBBox();
      const own = [...svg.querySelectorAll('text.lbl')].map(t => ({s: t.textContent, b: t.getBBox()}))
        .filter(t => t.b.x < line.x + 12 && t.b.x + t.b.width > line.x - 1);
      return own.map(t => [t.s, t.b.x, t.b.width, line.x]);
    }"""
    )
    for s, x, w, line_x in r:
        assert not (x < line_x < x + w), (s, x, w, line_x)
    page.close()


# ---------- headings, duplicates ----------

HEADINGS_JS = """() => [...document.querySelectorAll('main.report h2, main.report h3, main.report h4')]
  .filter(h => h.getBoundingClientRect().height > 0).map(h => h.textContent.trim())"""


def test_every_heading_stands_once_per_tab_and_the_balance_section_is_not_repeated(
    browser, base_url: str
) -> None:
    page = open_report(browser, base_url, "dobrcz")
    chart_title = "Niedobór wody w najgorszym okresie sezonu"
    tabs_with_chart = 0
    for tab in TABS:
        show_tab(page, tab)
        headings = page.evaluate(HEADINGS_JS)
        assert len(headings) == len(set(headings)), (tab, headings)
        assert "Bilans wody i próg suszy" not in headings
        if chart_title in page.locator("main.report").inner_text():
            tabs_with_chart += 1
    assert tabs_with_chart == 1
    show_tab(page, "podsumowanie")
    after_button = page.evaluate(
        "() => { const t = document.querySelector('main.report').innerText; return t.slice(t.indexOf('Raport PDF')); }"
    )
    assert "Bilans wody i próg suszy" not in after_button
    page.close()


# ---------- links ----------


def test_only_anchors_look_like_links(browser, base_url: str) -> None:
    page = open_report(browser, base_url, "dobrcz")
    show_tab(page, "zrodla")
    page.locator("#wiersz-zrodla summary").click()
    copy = page.locator("#tabela-zrodel td.st-copy")
    assert copy.count() >= 5
    assert copy.first.inner_text().startswith("kopia z dnia")
    accent = {token("accent"), token("accent-ink")}
    for tab in TABS:
        show_tab(page, tab)
        bad = page.evaluate(
            """() => [...document.querySelectorAll('main.report *')].filter(el => {
          if (el.closest('svg') || el.tagName === 'A' || el.tagName === 'SUMMARY' || !el.getBoundingClientRect().width) return false;
          if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return false;
          const cs = getComputedStyle(el);
          return cs.textDecorationLine.includes('underline');
        }).map(el => el.tagName + '.' + el.className + ':' + el.textContent.trim().slice(0, 30))"""
        )
        assert not bad, (tab, bad)
    show_tab(page, "zrodla")
    colours = page.evaluate(
        "() => [...document.querySelectorAll('#tabela-zrodel td.st-copy')].map(e => [getComputedStyle(e).color, getComputedStyle(e).fontWeight])"
    )
    for colour, weight in colours:
        rgb = tuple(int(x) for x in re.findall(r"\d+", colour)[:3])
        assert "#%02x%02x%02x" % rgb not in accent
        assert int(weight) < 600
    page.close()


# ---------- lists ----------


def test_list_like_sections_are_bulleted_lists(browser, base_url: str) -> None:
    page = open_report(browser, base_url, "dobrcz")
    show_tab(page, "przyczyny")
    causes = page.locator("#wiersz-dlaczego ul.b-lines")
    assert causes.count() == 1
    assert causes.evaluate("e => getComputedStyle(e.querySelector('li')).display") == "list-item"
    assert causes.evaluate("e => getComputedStyle(e.querySelector('li')).listStyleType") != "none"
    months = page.locator("#wiersz-czesto ul.b-list li")
    assert months.count() >= 3
    assert months.first.evaluate("e => getComputedStyle(e).listStyleType") != "none"
    assert "Według miesięcy" in page.locator("#wiersz-czesto").inner_text()
    assert ";" not in page.locator("#wiersz-czesto ul.b-list").inner_text()
    show_tab(page, "rekomendacje")
    formalities = page.locator("#wiersz-formalnosci ul.b-lines li")
    assert formalities.count() >= 1
    assert formalities.first.evaluate("e => getComputedStyle(e).listStyleType") != "none"
    assert "Formalność:" not in page.locator("#wiersz-zatrzymaj").inner_text().replace("Formalności", "")
    show_tab(page, "zrodla")
    method = page.locator("#wiersz-jak ul.b-list li")
    assert any("Raport nie uwzględnia" in t for t in method.all_inner_texts())
    page.close()


# ---------- grammar ----------


@pytest.mark.parametrize("name", ["dobrcz", "gsm"])
def test_the_sensitive_phase_is_written_with_we(browser, base_url: str, name: str) -> None:
    page = open_report(browser, base_url, name)
    for tab in TABS:
        show_tab(page, tab)
        assert not re.search(r"\bw wrażliwej fazie", page.locator("main.report").inner_text(), flags=re.I), (
            tab
        )
    page.close()


# ---------- the map ----------

RECTS_JS = """() => {
  const g = s => { const b = document.querySelector(s).getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
  return {form: g('.map-form'), stage: g('.mapstage'), outline: g('.mo-outline'), marker: g('.mo-marker')};
}"""


def inside(inner: list[float], outer: list[float]) -> bool:
    return (
        inner[0] >= outer[0] - 1
        and inner[1] >= outer[1] - 1
        and inner[2] <= outer[2] + 1
        and inner[3] <= outer[3] + 1
    )


def apart(a: list[float], b: list[float]) -> bool:
    return a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


@pytest.mark.xfail(reason="p56: kadr mapy raportu (obrys pod formularzem); zdejmij xfail po scaleniu p56", strict=False)
@pytest.mark.parametrize("size", [(1440, 900), (1366, 768)])
@pytest.mark.parametrize("name", ["dobrcz", "gsm"])
def test_the_selection_form_does_not_cover_the_parcel_outline(
    browser, base_url: str, name: str, size: tuple[int, int]
) -> None:
    page = open_report(browser, base_url, name, *size)
    r = page.evaluate(RECTS_JS)
    page.close()
    assert apart(r["form"], r["outline"]), r
    assert inside(r["outline"], r["stage"]), r
    assert inside(r["marker"], r["stage"]), r


# ---------- phone ----------


def test_phone_layout_has_no_orphan_unit_or_detached_time_column(browser, base_url: str) -> None:
    page = open_report(browser, base_url, "dobrcz", 390, 844)
    assert page.evaluate("[document.documentElement.scrollWidth, innerWidth]") == [390, 390]
    for row in page.locator(".a-bar").all():
        height = row.evaluate("e => e.querySelector('span').getBoundingClientRect().height")
        assert height < 20, row.inner_text()  # one line: the number and "mm" stay together
    show_tab(page, "zrodla")
    page.locator("#wiersz-zrodla summary").click()
    cells = page.evaluate(
        """() => [...document.querySelectorAll('#tabela-zrodel td.num')].map(e => {
        const cs = getComputedStyle(e); return [cs.textAlign, e.textContent.trim(), e.getAttribute('data-label')]; })"""
    )
    assert cells
    for align, text, label in cells:
        assert align != "right", text
        assert label == "Czas"
    assert page.evaluate("[document.documentElement.scrollWidth, innerWidth]") == [390, 390]
    page.close()
