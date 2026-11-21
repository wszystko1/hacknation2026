"""Scene "Działka z ewidencji na zdjęciu": number, date, crop typed in; the photo with the outline comes first."""

from demo.steps.common import PARCEL_1, PAUSE, evaluate


def scene(page, base_url: str) -> None:
    evaluate(page, base_url, PARCEL_1)
    crumb = page.locator(".crumb").inner_text()
    assert "gm. Dobrcz › obręb Dobrcz" in crumb, crumb
    assert "21,53 ha" in page.locator(".sub").inner_text()
    assert page.locator(".map img").first.is_visible()
    page.wait_for_timeout(PAUSE)
