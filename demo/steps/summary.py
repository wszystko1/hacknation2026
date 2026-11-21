"""Scene "Cały raport w skrócie": the agreement frame and 8 rows, each leading to its section."""

from demo.steps.common import PAUSE


def scene(page, base_url: str) -> None:
    page.locator("#skrot").scroll_into_view_if_needed()
    assert page.locator("#skrot li").count() == 8
    assert page.locator("#zgodnosc-ramka").is_visible()
    page.wait_for_timeout(PAUSE)
