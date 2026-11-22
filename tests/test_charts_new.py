"""Phase calendar, cause cards and the "Jak liczymy" schema: content tests on the markup."""

from __future__ import annotations

import re

import pytest

from app.charts.calendar import calendar_svg, covered_days
from app.charts.cause_cards import cause_cards_html
from app.charts.schema import schema_svg
from app.models import CropGroup
from tests.acceptance.helpers import DOBRCZ, report

CROPS = ["zboza_jare", "ziemniak"]


def _rects(markup: str, cls: str) -> list[float]:
    return [float(w) for w in re.findall(rf'<rect class="{cls}" x="[\d.]+" y="[\d.]+" width="([\d.]+)"', markup)]


@pytest.mark.parametrize("crop", CROPS)
def test_calendar_draws_the_periods_with_a_threshold_and_the_assessment_date(crop: str) -> None:
    r = report(DOBRCZ, uprawa=crop)
    markup = calendar_svg(r)
    assert markup.count("<svg") == 1
    assert "data oceny 20.07" in markup
    assert 'class="s-date"' in markup
    assert "okno bilansu" in markup
    # the blue spans are exactly the days of the periods that have a threshold in the table
    with_thr, _ = covered_days(CropGroup(crop), r.soil.category)  # type: ignore[arg-type]
    assert with_thr
    drawn = sum(_rects(markup, "s-ok")[:-1])  # the last s-ok is the legend swatch
    assert drawn == pytest.approx(len(with_thr) * 560 / 214, abs=len(with_thr) * 0.01 + 2)


def test_two_crops_have_different_threshold_periods() -> None:
    soil = report(DOBRCZ).soil.category
    spans = {crop: covered_days(CropGroup(crop), soil)[0] for crop in CROPS}  # type: ignore[arg-type]
    assert spans["zboza_jare"] != spans["ziemniak"]


def test_calendar_is_empty_for_a_crop_without_a_table() -> None:
    assert calendar_svg(report(DOBRCZ, uprawa="inna")) == ""


def test_cause_cards_carry_one_number_per_cause() -> None:
    r = report(DOBRCZ)
    html = cause_cards_html(r)
    cards = re.findall(r'<li class="cause-card" data-cause="(\w+)">(.*?)</li>', html, flags=re.S)
    assert cards, "the Dobrcz parcel has diagnosed causes"
    assert len(cards) <= len(r.diagnosis.causes)
    for code, card in cards:
        assert card.count('class="num"') == 1, code
        assert "<title>" in card and 'role="img"' in card


def test_schema_has_four_steps_with_alt_text() -> None:
    markup = schema_svg()
    for step in ("Dane", "Bilans", "Próg", "Werdykt"):
        assert f">{step}<" in markup
    assert 'role="img"' in markup and "<desc>" in markup
