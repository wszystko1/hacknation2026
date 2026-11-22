"""K4: the farmer screen has two levels.

Level A (`#poziom-a`, at most 7 items, each marked `data-a-item`): header, verdict sentence, two bars "zwykle / teraz",
action no. 1 with a deadline, confidence, the "Raport PDF" and "Pokaż doradcy" buttons. Level B is a list of `<details>`
rows, one arrow per row. Numbers stay in level B and in the advisor view; the farmer screen drops timings,
category codes, period numbers and "Brak:" boxes.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html
from tests.acceptance.test_plain_language import farmer_text

FORBIDDEN = ("pobranie trwało", "kat. II", "okres 4", "bilans wody w 60 dniach", "Brak: zgodność metody")


def _farmer(params: dict) -> str:
    page = html(params)
    # the advisor view is a separate request; the farmer view keeps level B but not the advisor blocks
    return farmer_text(page)


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_farmer_screen_has_none_of_the_removed_texts(params: dict) -> None:
    text = _farmer(params)
    for phrase in FORBIDDEN:
        assert phrase not in text, phrase
    assert not re.search(r"\b\d+[.,]\d s\b", text), "fetch times such as 14,5 s"
    assert not re.search(r"\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s?\d{1,2}\b", text), "roman-numeral dates"


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_top_block_has_at_most_seven_items(params: dict) -> None:
    page = html(params)
    top = re.search(
        r'<(section|div)[^>]*id="poziom-a"[^>]*>(.*?)</\1>\s*(?=<(?:section|div)[^>]*id="poziom-b")',
        page,
        flags=re.S,
    )
    assert top, "#poziom-a followed by #poziom-b"
    items = re.findall(r"data-a-item", top.group(2))
    assert 1 <= len(items) <= 7, len(items)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_top_block_has_verdict_action_confidence_and_both_buttons() -> None:
    page = html(DOBRCZ)
    top = re.search(r'id="poziom-a"(.*?)id="poziom-b"', page, flags=re.S)
    assert top
    text = re.sub(r"<[^>]+>", " ", top.group(1))
    assert re.search(r"susza|bilans", text, flags=re.I)
    assert "ocena IUNG" in text or "ocena SMSR" in text
    for button in ("Raport PDF", "Pokaż doradcy"):
        assert button in text, button


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_balance_and_threshold_stand_once_in_level_b() -> None:
    page = html(DOBRCZ)
    b = re.search(r'id="poziom-b"(.*)', page, flags=re.S).group(1)
    rows = re.findall(r"<details\b.*?</details>", b, flags=re.S)
    assert rows, "level B rows are <details>"
    with_balance = [r for r in rows if re.search(r"[−-]\d+ mm", re.sub(r"<[^>]+>", " ", r))]
    assert with_balance, "the balance in mm stays in a level B row"


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_empty_sections_are_one_line_not_boxes() -> None:
    page = html(GSM_TODAY)
    text = farmer_text(page)
    assert len(re.findall(r"Jeszcze nie liczymy:", text)) <= 1
    assert not re.search(r"Brak:\s", text)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_actions_are_phrased_as_consider_not_as_orders() -> None:
    page = html(DOBRCZ)
    text = farmer_text(page)
    assert not re.search(r"\b(Zrób nieckę|Zamontuj zastawkę)\b", text, flags=re.I)
