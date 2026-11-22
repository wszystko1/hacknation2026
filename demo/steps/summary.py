"""Scene "Cały raport w skrócie": level A on top, the rows of level B below it; the "gmina" row opens on the
agreement of the method with the state's assessment, then the scene returns to level A."""

import re

from demo.steps.common import PAUSE


def scene(page, base_url: str) -> None:
    rows = page.locator("#poziom-b details")
    assert rows.count() >= 8, rows.count()
    assert page.locator("#poziom-b details summary").count() == rows.count()  # one arrow per row
    page.locator("#poziom-b").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    page.locator("#wiersz-gmina summary").click()
    frame = page.locator("#zgodnosc-ramka")
    assert frame.is_visible()
    assert re.search(r"w \d+ na 100 przypadków", frame.inner_text())
    frame.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    page.locator("#wiersz-gmina summary").click()
    page.locator("#poziom-a").scroll_into_view_if_needed()
    assert page.locator("#zdanie-werdyktu").is_visible()
    page.wait_for_timeout(PAUSE)
