"""K4: the report is the main content of the report screen.

Three columns: a 56 px icon rail, a 560 px map and the report in all the remaining width
(`grid-template-columns: 56px 560px minmax(0, 1fr)`); below 1180 px the map takes 44%; a phone gets one column.
The rail carries "Nowa ocena", "Raport PDF" and "Zgodność z SMSR", with no avatar and no account.
CSS custom properties are resolved, so the sizes may live in tokens.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.helpers import DOBRCZ, html

GRID = r"grid-template-columns:56px(560px|44%)minmax\(0(px)?,1fr\)"


def _css() -> str:
    text = "".join(p.read_text(encoding="utf-8") for p in sorted(Path("app/static").glob("*.css")))
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    tokens = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+)", text))
    for _ in range(5):  # tokens may refer to tokens
        text = re.sub(
            r"var\(\s*(--[\w-]+)\s*(?:,[^()]*)?\)", lambda m: tokens.get(m.group(1), m.group(0)), text
        )
    return re.sub(r"\s+", "", text)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_report_screen_is_rail_56_map_560_and_the_rest_for_the_report() -> None:
    css = _css()
    assert any(m.group(1) == "560px" for m in re.finditer(GRID, css)), "56px 560px minmax(0,1fr)"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_below_1180_px_the_map_takes_44_percent() -> None:
    css = _css()
    narrow = re.search(r"@media[^{]*max-width:1180px[^{]*\{(.*?)\}\}", css)
    assert narrow, "a media query for screens up to 1180 px"
    assert any(m.group(1) == "44%" for m in re.finditer(GRID, narrow.group(1))), narrow.group(1)[:300]


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_report_page_has_the_icon_rail_without_an_account() -> None:
    page = html(DOBRCZ)
    rail = re.search(r'<nav[^>]*class="[^"]*\brail\b[^"]*"[^>]*>(.*?)</nav>', page, flags=re.S)
    assert rail, "nav.rail on the report page"
    for label in ("Nowa ocena", "Raport PDF", "Zgodność z SMSR"):
        assert label in rail.group(1), label
    assert not re.search(r"konto|wyloguj|awatar", rail.group(1), flags=re.I)
