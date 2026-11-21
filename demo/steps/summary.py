"""Scene "Cały raport w skrócie": the agreement frame and 8 rows, each leading to its section."""

from demo.steps.common import PAUSE


def scene(page, base_url: str) -> None:
    page.locator("#skrot").scroll_into_view_if_needed()
    assert page.locator("#skrot li").count() == 8
    frame = page.locator("#zgodnosc-ramka")
    assert frame.is_visible()
    import re

    assert re.search(r"w \d+ na 100 przypadków", frame.inner_text())
    page.wait_for_timeout(PAUSE)
