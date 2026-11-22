"""Scene "Gdzie zatrzymać wodę na działce": the row with the places on the parcel and the row with the formality."""

from demo.steps.common import PAUSE, open_row
from demo.steps.tabs import show_tab


def scene(page, base_url: str) -> None:
    show_tab(page, "rekomendacje")
    open_row(page, "formalnosci")
    formalities = page.locator("#wiersz-formalnosci")
    assert "Wodach Polskich" in formalities.inner_text() or "Prawo wodne" in formalities.inner_text()
    open_row(page, "spadek")
    assert page.locator("#wiersz-spadek .b-body").inner_text().strip()
    page.locator("#wiersz-spadek").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    show_tab(page, "podsumowanie")
