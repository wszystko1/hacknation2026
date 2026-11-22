"""Entering the report through #hash opens the tab from its top; the "not covered" sentence stands once."""

from __future__ import annotations

import pytest

from tests.test_report_layout_browser import URL, base_url, page  # noqa: F401

pytest.importorskip("playwright.sync_api")

SENTENCE = "Raport nie uwzględnia drenowania"


@pytest.mark.parametrize(
    ("anchor", "label"),
    [
        ("zrodla", "Jak liczymy"),
        ("zrodla-danych", "Jak liczymy"),
        ("przyczyny", "Przyczyny"),
        ("rekomendacje", "Rekomendacje"),
        ("wiarygodnosc", "Wiarygodność"),
    ],
)
def test_hash_opens_tab_from_the_top(page, base_url, anchor, label) -> None:  # noqa: F811
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + URL + "#" + anchor)
    page.wait_for_selector("main.report")
    page.wait_for_timeout(500)
    assert page.get_by_role("tab", name=label).get_attribute("aria-selected") == "true"
    head = page.evaluate(
        "(() => { const p = [...document.querySelectorAll('.report [data-tab]')].find(e => !e.hidden && e.getClientRects().length);"
        " const h = p.matches('h1,h2,h3') ? p : p.querySelector('h1,h2,h3'); const r = h.getBoundingClientRect();"
        " return {top: r.top, focused: document.activeElement === h}; })()"
    )
    assert 0 <= head["top"] < 300
    assert head["focused"]


def test_not_covered_sentence_once_in_how_we_count(page, base_url) -> None:  # noqa: F811
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + URL + "#zrodla")
    page.wait_for_selector("main.report")
    html = page.evaluate(
        "[...document.querySelectorAll('.report [data-tab=zrodla]')].map(e => e.textContent).join(' ')"
    )
    assert html.count(SENTENCE) == 1
