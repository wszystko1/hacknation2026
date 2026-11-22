"""Scene "Werdykt: bilans wobec progu z rozporządzenia": level A states the verdict in one sentence with a colour and
a word; the balance and the threshold of Dz.U. 2019 poz. 739 appear when the "bilans" row is opened."""

import re
from urllib.parse import urlencode

from demo.steps.common import PARCEL_1, PAUSE
from demo.steps.tabs import open_row, show_tab


def scene(page, base_url: str) -> None:
    verdict = page.request.get(f"{base_url}/api/raport?{urlencode(PARCEL_1)}").json()["verdict"]
    assert verdict["state"] == "below", verdict["state"]
    top = page.locator("#poziom-a")
    top.scroll_into_view_if_needed()
    sentence = page.locator("#zdanie-werdyktu").inner_text()
    assert "próg suszy dla zbóż jarych" in sentence, sentence
    assert page.locator("#plakietka").inner_text() == "Bilans poniżej progu suszy (szacunek dla działki)"
    assert "badge--dry" in page.locator("#plakietka").get_attribute("class")
    assert page.locator("#poziom-a [data-a-item]").count() <= 7
    assert "IUNG dla gminy" in page.locator("#pewnosc").inner_text()  # decision of the owner 22.11.2026
    page.wait_for_timeout(PAUSE)
    # The balance row below the tiles carries the number and its caption.
    show_tab(page, "podsumowanie")
    row = page.locator("#wiersz-bilans")
    open_row(page, "bilans")
    number = row.locator(".big-number b").inner_text()
    assert str(round(abs(verdict["kbw_mm"]))) in number.replace("−", ""), number
    label = row.locator("svg.hbar .lbl-thr").text_content()
    assert re.fullmatch(r"próg −\d+ mm", label), label
    row.scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    show_tab(page, "podsumowanie")
    top.scroll_into_view_if_needed()
    assert page.locator("#zdanie-werdyktu").is_visible()
    page.wait_for_timeout(PAUSE)
