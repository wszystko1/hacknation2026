"""Scene "Raport na dziś: poza okresem monitoringu suszy": parcel 2, today's date, legumes."""

from urllib.parse import urlencode

from demo.steps.common import PARCEL_2, PAUSE, evaluate


def scene(page, base_url: str) -> None:
    evaluate(page, base_url, PARCEL_2)
    # The number the viewer reads must be the one the report computed for the 2026 season.
    verdict = page.request.get(f"{base_url}/api/raport?{urlencode(PARCEL_2)}").json()["verdict"]
    assert verdict["state"] == "out_of_season" and verdict["season_year"] == 2026
    expected = round(abs(verdict["kbw_mm"]))

    # Level A: grey word, the season sentence, no drought call for today.
    assert page.locator("#plakietka").inner_text() == "Poza sezonem"
    assert "badge--neutral" in page.locator("#plakietka").get_attribute("class")
    assert (
        "Susza rolnicza jest oceniana od 21 marca do 30 września"
        in page.locator("#zdanie-werdyktu").inner_text()
    )
    assert page.locator("#poziom-a [data-a-item]").count() <= 7
    # The balance of the season just ended opens in its row.
    page.locator("#wiersz-bilans summary").click()
    shown = page.locator("#wiersz-bilans .big-number b").inner_text()
    assert str(expected) in shown.replace("−", "-").lstrip("-"), (shown, expected)
    assert "2026" in page.locator("#wiersz-bilans .big-number .cap").inner_text()

    # The summary of the season just ended and the rain since 1 October against the norm.
    off = page.request.get(f"{base_url}/api/raport?{urlencode(PARCEL_2)}").json()["off_season"]
    assert off["season_year"] == 2026 and off["norm_mm"] and off["n_years"] >= 5
    sentence = page.locator("#wiersz-bilans #opad-od-1x")
    assert f"{round(off['rain_mm'])} mm" in sentence.inner_text()
    assert f"{round(off['norm_mm'])} mm" in sentence.inner_text()
    sentence.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
