"""The print view: a short report of at most three A4 pages, no folds, no tabs, no promises."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html

PARCELS = [DOBRCZ, GSM_TODAY]
IDS = ["dobrcz", "gora"]
FORBIDDEN = ("<details", 'role="tab"', "data-tab", "hx-get", "Tu pojawi", "Liczę…", "Brak: zgodność metody", "data-neighbour")


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_print_view_has_three_pages_of_content(params: dict) -> None:
    page = html(params, path="/raport/druk")
    for marker in ("strona-1", "strona-2", "strona-3", "k-werdykt", "k-plakietka", "k-dzialanie-1", "k-zastrzezenie", "k-tabela-zrodel"):
        assert f'id="{marker}"' in page, marker
    assert re.search(r'id="k-zdjecie".*?<img src=.*?mo-outline', page, re.S)
    assert page.count("<svg") >= 3  # balance bar, at least one chart


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_print_view_has_no_forbidden_patterns(params: dict) -> None:
    page = html(params, path="/raport/druk")
    page = page[: page.index('id="pelny-raport"')]  # the part that is printed
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    for pattern in FORBIDDEN:
        assert pattern not in text, pattern


@pytest.mark.parametrize("params", PARCELS, ids=IDS)
def test_print_view_prints_on_at_most_three_pages(params: dict, tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    pypdf = pytest.importorskip("pypdf")
    from scripts.export_reports import export_one

    pdf = export_one(params, tmp_path / "r.pdf")
    reader = pypdf.PdfReader(str(pdf))
    assert 1 <= len(reader.pages) <= 3
    text = "".join(p.extract_text() for p in reader.pages).replace(" ", "")  # glyph spacing varies
    assert "Zastrzeżenie" in text and "Źródładanych" in text


def test_the_plan_from_the_address_reaches_the_print_view() -> None:
    page = html(DOBRCZ, path="/raport/druk", plan="1,2")
    assert "Działka 189/13" in page


def test_the_report_links_to_the_print_view_with_its_plan() -> None:
    page = html(DOBRCZ, plan="1")
    assert re.search(r'id="pdf"[^>]*href="/raport/druk\?[^"]*plan=1', page)
