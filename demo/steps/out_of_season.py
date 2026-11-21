"""Scene "Raport na dziś: poza okresem monitoringu suszy": parcel 2, today's date, legumes."""

from app.models import OUT_OF_SEASON
from demo.steps.common import PARCEL_2, PAUSE, evaluate


def scene(page, base_url: str) -> None:
    evaluate(page, base_url, PARCEL_2)
    banner = page.locator("#poza-sezonem")
    banner.scroll_into_view_if_needed()
    assert OUT_OF_SEASON in banner.inner_text()
    page.wait_for_timeout(PAUSE)
