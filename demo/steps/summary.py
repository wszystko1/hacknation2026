"""Scene "Cały raport w skrócie": level A on top, the rows of level B below it; the "gmina" row opens on the
agreement of the method with the state's assessment, then the scene returns to level A."""

import re

from demo.steps.common import PAUSE
from demo.steps.tabs import open_row, show_tab


def scene(page, base_url: str) -> None:
    rows = page.locator("#poziom-b .b-group")
    assert rows.count() >= 6, rows.count()
    show_tab(page, "wiarygodnosc")
    page.locator("#poziom-b").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    open_row(page, "gmina")
    frame = page.locator("#pasek-pewnosci")
    assert frame.is_visible()
    assert re.search(r"\d+ na 100 przypadków", frame.inner_text())
    frame.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    show_tab(page, "podsumowanie")
    page.locator("#poziom-a").scroll_into_view_if_needed()
    assert page.locator("#zdanie-werdyktu").is_visible()
    page.wait_for_timeout(PAUSE)
