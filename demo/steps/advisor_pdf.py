"""Scene "Raport PDF": the print view of the same report, with the photo, the verdict and the sources table."""

from demo.steps.common import PAUSE
from demo.steps.tabs import show_tab


def scene(page, base_url: str) -> None:
    show_tab(page, "podsumowanie")
    page.locator("#pdf").click()
    page.wait_for_selector("#druk-info")
    assert page.locator("#werdykt").is_visible()
    assert "Działka 189/13" in page.locator("h1").first.inner_text()
    assert page.locator("#zdjecie-druk img").is_visible()
    assert page.locator("#tabela-zrodel").count() == 1
    page.locator("#zdjecie-druk").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
