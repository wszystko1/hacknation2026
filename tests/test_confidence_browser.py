"""p77 in a real browser: no text collisions in the confidence block and <= 24 px above "Ocena sytuacji w gminie"."""

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
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
URL = "/raport?dzialka=040303_2.0002.189%2F13&data=20.07.2023&uprawa=zboza_jare"

GAP_JS = """() => {
  const h = [...document.querySelectorAll('.a-conf h2')].find(e => e.textContent.includes('Ocena sytuacji w gminie'));
  const tile = h.closest('.tile'), top = tile.getBoundingClientRect().top;
  const above = [...document.querySelectorAll('.level-a > [data-tab=podsumowanie]')]
    .filter(e => e !== tile && e.getBoundingClientRect().height > 0 && e.getBoundingClientRect().bottom <= top + 1)
    .map(e => e.getBoundingClientRect().bottom);
  return h.getBoundingClientRect().top - Math.max(...above);
}"""
BOXES_JS = """() => [...document.querySelectorAll('#pasek-pewnosci .conf-pin span, #pasek-pewnosci .conf-names > div, #pasek-pewnosci .conf-label, #pasek-pewnosci .conf-cap, #pasek-pewnosci .conf-sentence')]
  .map(e => { const r = e.getBoundingClientRect(); return {s: e.textContent.trim(), x: r.x, y: r.y, w: r.width, h: r.height}; })"""


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


@pytest.mark.parametrize("width", [1440, 390])
def test_gap_above_the_commune_frame_and_no_colliding_text(base_url: str, width: int) -> None:
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception:  # noqa: BLE001 - fall back to the bundled chromium
            browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(base_url + URL)
        page.wait_for_selector("main.report")
        assert page.evaluate(GAP_JS) <= 24
        page.evaluate("document.querySelector('[data-tab-button=wiarygodnosc]')?.click()")
        page.evaluate("document.querySelectorAll('[data-tab=wiarygodnosc]').forEach(e => e.hidden = false)")
        boxes = [b for b in page.evaluate(BOXES_JS) if b["w"] > 0]
        browser.close()
    assert len(boxes) >= 6
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            ox = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            oy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            assert not (ox > 2 and oy > 2), (a["s"], b["s"])
