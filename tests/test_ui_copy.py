"""The farmer screen never speaks in the first person plural: no "nasz szacunek", "naszej metody", "propozycja zespołu"."""

from __future__ import annotations

import re

import pytest

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html

FIRST_PERSON = re.compile(r"\bnasz\w*|zespołu|\bnaszych?\b|uważamy|według nas|w naszej ocenie", re.I)


def farmer_text(page: str) -> str:
    """All text of the farmer report column, hidden tabs and closed rows included; scripts and styles are dropped."""
    main = page[page.index('<main id="tresc"') :]
    main = re.sub(r"<(script|style)\b.*?</\1>", " ", main, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main))


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz", "out_of_season"])
def test_farmer_screen_has_no_first_person_plural(params: dict) -> None:
    text = farmer_text(html(params))
    assert not FIRST_PERSON.findall(text), FIRST_PERSON.findall(text)


def test_farmer_screen_has_no_pin_sentence() -> None:
    assert "inezk" not in farmer_text(html(DOBRCZ))


def test_farmer_screen_does_not_mention_applications_or_subsidies() -> None:
    # decision of the owner 22.11.2026: the app helps farmers cope by themselves, it is not about aid
    for params in (DOBRCZ, GSM_TODAY):
        assert not re.search(r"wniosk|dopłat", farmer_text(html(params)), re.I)
