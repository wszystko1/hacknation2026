"""Scene "Widok doradcy i raport PDF": the same report with advisor blocks, then the print view."""

from demo.steps.common import PAUSE


def scene(page, base_url: str) -> None:
    page.locator(".seg a", has_text="Doradca").click()
    page.wait_for_selector("body.view-doradca")
    page.wait_for_timeout(PAUSE)
    page.locator("#pdf").click()
    page.wait_for_selector("#druk-info")
    assert page.locator("#werdykt").is_visible()
    assert "Działka 189/13" in page.locator("h1").first.inner_text()
    page.wait_for_timeout(PAUSE)
