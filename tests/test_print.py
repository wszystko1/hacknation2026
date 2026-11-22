"""The print view: photo with the outline, verdict, summary, eight sections, the sources table last, no promises."""

from __future__ import annotations

import re

import pytest

from app.models import SECTION_ORDER
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html

PARCELS = [DOBRCZ, GSM_TODAY]
IDS = ["dobrcz", "gora"]


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_print_view_has_photo_verdict_eight_sections_and_sources(params: dict) -> None:
    page = html(params, path="/raport/druk")
    assert re.search(r'id="zdjecie-druk".*?<img src=.*?mo-outline', page, re.S)
    assert 'id="werdykt"' in page and 'id="skrot"' in page
    for section_id, _, _ in SECTION_ORDER:
        assert f'<section id="{section_id}"' in page, section_id
    assert len(SECTION_ORDER) == 8
    assert 'id="tabela-zrodel"' in page
    order = [page.index(f'<section id="{s}"') for s, _, _ in SECTION_ORDER]
    assert order == sorted(order) and page.index('id="tabela-zrodel"') > order[-2]


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_print_view_has_no_promise_of_a_later_result(params: dict) -> None:
    page = html(params, path="/raport/druk")
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    assert "Tu pojawi" not in re.sub(r"<[^>]+>", " ", text)


def test_the_plan_from_the_address_reaches_the_print_view() -> None:
    page = html(DOBRCZ, path="/raport/druk", plan="1,2")
    assert re.search(r"<b data-plan-count>2</b>", page)
    assert 'class="is-planned"' in page


def test_the_report_links_to_the_print_view_with_its_plan() -> None:
    page = html(DOBRCZ, plan="1")
    assert re.search(r'id="pdf"[^>]*href="/raport/druk\?[^"]*plan=1', page)


def test_the_print_view_carries_the_same_plant_row_as_the_screen() -> None:
    screen = html(DOBRCZ, widok="doradca")
    printed = html(DOBRCZ, path="/raport/druk")
    sat = [re.search(r"zdjęcie z \d{2}\.\d{2}\.\d{4}, czystych pikseli \d+%", p) for p in (screen, printed)]
    assert all(sat)
