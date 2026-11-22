"""Scene "Gdzie zatrzymać wodę na działce": the row with the places on the parcel and the row with the formality."""

from demo.steps.common import PAUSE
from demo.steps.tabs import open_row, show_tab


def scene(page, base_url: str) -> None:
    show_tab(page, "rekomendacje")
    open_row(page, "zatrzymaj")
    formalities = page.locator("#wiersz-formalnosci")
    assert "Wodach Polskich" in formalities.inner_text() or "Prawo wodne" in formalities.inner_text()
    assert page.locator("#wiersz-spadek").inner_text().strip()
    page.locator("#wiersz-spadek").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    show_tab(page, "podsumowanie")
