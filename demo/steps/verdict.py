"""Scene "Werdykt: bilans wobec progu z rozporządzenia": the balance in mm against the threshold of Dz.U. 2019
poz. 739, the badge, the threshold tick on the bar, the fixed disclaimer and the SMSR row."""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.models import BADGE_ABOVE, BADGE_BELOW, DISCLAIMER
from demo.steps.common import PAUSE


def scene(page, base_url: str) -> None:
    verdict = page.locator("#werdykt")
    verdict.scroll_into_view_if_needed()
    assert re.search(r"−?\d+\s*mm", verdict.locator(".big-number").inner_text())
    sentence = page.locator("#zdanie-werdyktu").inner_text()
    assert "Tu pojawi" not in sentence, sentence
    if not page.locator("#plakietka").count():
        # Soil category unknown: the balance and the range of thresholds for categories I-IV, no badge.
        assert "Bez kategorii gleby" in sentence, sentence
        assert not verdict.locator("svg.hbar .lbl-thr").count()
        page.wait_for_timeout(PAUSE)
        # The advisor sets the category (gleba=II in the address): the threshold, the badge and the tick appear.
        url = urlsplit(page.url)
        query = [(k, v) for k, v in parse_qsl(url.query) if k != "gleba"] + [("gleba", "II")]
        page.goto(urlunsplit(url._replace(query=urlencode(query))))
        verdict.scroll_into_view_if_needed()
        sentence = page.locator("#zdanie-werdyktu").inner_text()
        assert "Tu pojawi" not in sentence, sentence
    # Soil category known: the badge from the regulation and the threshold tick "próg −N mm" on the bar.
    badge = page.locator("#plakietka").inner_text()
    assert badge in {BADGE_BELOW, BADGE_ABOVE}, badge
    label = verdict.locator("svg.hbar .lbl-thr").text_content()
    assert re.fullmatch(r"próg −\d+ mm", label), label
    assert "progu suszy dla zbóż jarych" in sentence, sentence
    assert DISCLAIMER in page.locator("#zastrzezenie").inner_text()
    assert "Ocena SMSR dla gminy Dobrcz" in page.locator("#wiersz-smsr").inner_text()
    page.locator("#zdanie-werdyktu").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
    # Three separate answers under the badge: plants, the reading of verdict and plants together, vulnerability.
    plants = page.locator("#wiersz-satelita").inner_text()
    assert "Stan roślin" in plants and ("zdjęcie z" in plants or "brak" in plants.lower() or "w toku" in plants), plants
    reading = page.locator("#wiersz-odczyt")
    if reading.count():
        text = reading.inner_text()
        expected = ("Susza potwierdzona", "satelita jeszcze nie pokazuje stresu", "Spadek niewyjaśniony",
                    "Brak oznak problemu z wodą", "Sam bilans")  # fmt: skip
        assert any(e in text for e in expected), text
    assert "gdyby rosły" in page.locator("#wiersz-podatnosc").inner_text().lower()
    page.locator("#wiersz-satelita").scroll_into_view_if_needed()
    page.wait_for_timeout(PAUSE)
