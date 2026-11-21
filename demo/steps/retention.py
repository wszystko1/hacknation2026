"""Scene "Gdzie zatrzymać wodę na działce": section 4 with the place on the photo and the formality."""

from demo.steps.common import PAUSE, open_section


def scene(page, base_url: str) -> None:
    page.locator("#skrot").scroll_into_view_if_needed()
    open_section(page, "Zatrzymanie wody", "retencja")
    section = page.locator("#retencja")
    assert section.is_visible()
    assert "Wodach Polskich" in section.inner_text() or "Prawo wodne" in section.inner_text()
    page.wait_for_timeout(PAUSE)
