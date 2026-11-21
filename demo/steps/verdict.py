"""Scene "Werdykt: bilans wobec progu z rozporządzenia": the balance in mm, the badge, the fixed disclaimer, SMSR row."""

from app.models import DISCLAIMER
from demo.steps.common import PAUSE


def scene(page, base_url: str) -> None:
    page.locator("#werdykt").scroll_into_view_if_needed()
    assert "mm" in page.locator("#werdykt .big-number").inner_text()
    assert DISCLAIMER in page.locator("#zastrzezenie").inner_text()
    assert "Ocena SMSR dla gminy Dobrcz" in page.locator("#wiersz-smsr").inner_text()
    page.wait_for_timeout(PAUSE)
