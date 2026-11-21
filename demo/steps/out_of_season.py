"""Scene "Raport na dziś: poza okresem monitoringu suszy": parcel 2, today's date, legumes."""

import re
from urllib.parse import urlencode

from app.models import OUT_OF_SEASON
from demo.steps.common import PARCEL_2, PAUSE, evaluate


def scene(page, base_url: str) -> None:
    evaluate(page, base_url, PARCEL_2)
    # The number the viewer reads must be the one the report computed for the 2026 season.
    verdict = page.request.get(f"{base_url}/api/raport?{urlencode(PARCEL_2)}").json()["verdict"]
    assert verdict["state"] == "out_of_season" and verdict["season_year"] == 2026
    expected = round(abs(verdict["kbw_mm"]))

    banner = page.locator("#poza-sezonem")
    assert OUT_OF_SEASON in banner.inner_text()
    shown = page.locator("#werdykt .big-number b").inner_text()
    assert str(expected) in shown.replace("−", "-").lstrip("-"), (shown, expected)
    assert "2026" in page.locator("#werdykt .big-number .cap").inner_text()
    assert re.search(r"Sezon 2026", page.locator("#werdykt").inner_text())
    # The data are a frozen copy and say how long the original download took.
    assert (
        "kopia danych z 21.11.2026; pobranie trwało" in page.locator(".report-head .demo-data").inner_text()
    )

    # The summary of the season just ended and the rain since 1 October against the norm.
    off = page.request.get(f"{base_url}/api/raport?{urlencode(PARCEL_2)}").json()["off_season"]
    assert off["season_year"] == 2026 and off["norm_mm"] and off["n_years"] >= 5
    assert page.locator("#wiersz-werdyktu-dzis").inner_text().count("nie dotyczy") == 1
    sentence = page.locator("#opad-od-1x")
    assert f"{round(off['rain_mm'])} mm" in sentence.inner_text()
    assert f"{round(off['norm_mm'])} mm" in sentence.inner_text()
    sentence.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
