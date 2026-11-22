"""Scene "Werdykt: bilans wobec progu z rozporządzenia": level A states the verdict in one sentence with a colour and
a word; the balance and the threshold of Dz.U. 2019 poz. 739 appear when the "bilans" row is opened."""

import re
from urllib.parse import urlencode

from demo.steps.common import PARCEL_1, PAUSE


def scene(page, base_url: str) -> None:
    verdict = page.request.get(f"{base_url}/api/raport?{urlencode(PARCEL_1)}").json()["verdict"]
    assert verdict["state"] == "below", verdict["state"]
    top = page.locator("#poziom-a")
    top.scroll_into_view_if_needed()
    sentence = page.locator("#zdanie-werdyktu").inner_text()
    assert "próg suszy dla zbóż jarych" in sentence, sentence
    assert page.locator("#plakietka").inner_text() == "Susza: tak"
    assert "badge--dry" in page.locator("#plakietka").get_attribute("class")
    assert page.locator("#poziom-a [data-a-item]").count() <= 7
    assert "Przy wniosku liczy się ocena IUNG" in page.locator("#pewnosc").inner_text()
    page.wait_for_timeout(PAUSE)
    # The number is not on the first level: it appears when the row is opened.
    row = page.locator("#wiersz-bilans")
    assert not re.search(r"−\d+\s*mm", top.inner_text())
    row.locator("summary").click()
    number = row.locator(".big-number b").inner_text()
    assert str(round(abs(verdict["kbw_mm"]))) in number.replace("−", ""), number
    label = row.locator("svg.hbar .lbl-thr").text_content()
    assert re.fullmatch(r"próg −\d+ mm", label), label
    row.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    row.locator("summary").click()  # closed again: the scene ends on level A
    top.scroll_into_view_if_needed()
    assert page.locator("#zdanie-werdyktu").is_visible()
    page.wait_for_timeout(PAUSE)
