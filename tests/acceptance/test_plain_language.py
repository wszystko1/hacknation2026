"""K4: three fields, an alphabetical crop list, errors next to the field in Polish, text at least 16 px,
the farmer view without jargon (KBW, ewapotranspiracja, NDVI, NDMI, BSS only in the advisor view)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models import CROP_CHOICES, CROP_LABELS, CropGroup
from tests.acceptance.helpers import DOBRCZ, client, html

JARGON = ("KBW", "ewapotranspiracja", "NDVI", "NDMI", "BSS")


def farmer_text(page: str) -> str:
    """Visible text of the farmer view: without advisor blocks, "Jak to policzono", scripts and tags."""
    page = re.sub(r'<div class="advisor".*?</div>', " ", page, flags=re.S)
    page = re.sub(r'<details class="calc".*?</details>', " ", page, flags=re.S)
    page = re.sub(r"<(script|style|title|desc)\b.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r"<[^>]+>", " ", page)
    return page


def test_start_screen_has_three_fields() -> None:
    page = client.get("/").text
    assert len(re.findall(r'<(input|select)\b[^>]*name="(dzialka|data|uprawa)"', page)) == 3


def test_crop_list_is_alphabetical_with_other_last() -> None:
    labels = [CROP_LABELS[c] for c in CROP_CHOICES]
    assert len(labels) == 15
    assert labels[-1] == "Inna uprawa"
    assert labels[:-1] == sorted(labels[:-1], key=lambda s: s.replace("ś", "s~").replace("ż", "z~"))
    assert CROP_CHOICES[-1] == CropGroup.INNA


@pytest.mark.parametrize(
    ("params", "field", "message"),
    [
        ({"dzialka": "abc", "data": "2023-07-20", "uprawa": "zboza_jare"}, "dzialka", "Numer ma postać"),
        (
            {"dzialka": DOBRCZ["dzialka"], "data": "2009-07-20", "uprawa": "zboza_jare"},
            "data",
            "Data musi być",
        ),
        ({"dzialka": DOBRCZ["dzialka"], "data": "2023-07-20", "uprawa": ""}, "uprawa", "Wybierz uprawę"),
    ],
)
def test_input_errors_are_next_to_the_field_in_polish(params: dict, field: str, message: str) -> None:
    from urllib.parse import urlencode

    r = client.get(f"/raport?{urlencode(params)}")
    assert r.status_code == 422
    assert re.search(rf'name="{field}"[^>]*aria-invalid="true"', r.text)
    assert re.search(rf'class="field-error" id="e-{field}">{message}', r.text)


def test_no_text_below_16_px_in_the_stylesheet() -> None:
    css = Path("app/static/app.css").read_text(encoding="utf-8")
    css = re.sub(r"@media print\s*\{.*", "", css, flags=re.S)  # print sizes are in pt
    sizes = [float(m) for m in re.findall(r"(?:font-size\s*:|font\s*:[^;]*?)\s*(\d+(?:\.\d+)?)px", css)]
    assert sizes and min(sizes) >= 16


def test_report_body_is_18_px() -> None:
    css = Path("app/static/app.css").read_text(encoding="utf-8")
    assert re.search(r"--fs-base:\s*18px", css)


def test_farmer_view_has_no_jargon() -> None:
    text = farmer_text(html(DOBRCZ))
    for word in JARGON:
        assert not re.search(rf"\b{word}\b", text), word


def test_verdict_is_one_sentence_with_a_number() -> None:
    page = html(DOBRCZ)
    sentence = re.search(r'class="verdict-sentence[^"]*">(.*?)</p>', page, flags=re.S).group(1)
    assert re.search(r"\d+ mm", sentence)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_advisor_view_shows_the_technical_terms() -> None:
    page = html(DOBRCZ, widok="doradca")
    advisor = " ".join(re.findall(r'<div class="advisor".*?</div>', page, flags=re.S))
    for word in ("KBW", "ET0"):
        assert word in advisor
