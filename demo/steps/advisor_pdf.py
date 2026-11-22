"""Scene "Widok doradcy i raport PDF": the same report with advisor blocks, then the print view."""

from demo.steps.common import PAUSE


def scene(page, base_url: str) -> None:
    if "view-doradca" not in (page.locator("body").get_attribute("class") or ""):
        page.locator("#pokaz-doradcy").click()
        page.wait_for_selector("body.view-doradca")
    block = page.locator("#zrodla .advisor")
    block.scroll_into_view_if_needed()
    assert block.is_visible()
    assert "Rozdzielczość" in block.inner_text() or "rozdzielczość" in block.inner_text()
    page.wait_for_timeout(PAUSE)
    page.locator("#pdf").click()
    page.wait_for_selector("#druk-info")
    assert page.locator("#werdykt").is_visible()
    assert "Działka 189/13" in page.locator("h1").first.inner_text()
    assert page.locator("#zdjecie-druk img").is_visible()
    assert page.locator("#tabela-zrodel").count() == 1
    page.locator("#zdjecie-druk").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
