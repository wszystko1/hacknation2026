"""The verdict: sentences with the crop group's genitive, weather gaps, neighbour soil category and the report routes."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

from app.drought.chart import hbar_svg
from app.drought.kbw import CROP_GENITIVE, assess
from app.models import BADGE_ABOVE, BADGE_BELOW, DISCLAIMER, CropGroup
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, html

THRESHOLD_LABEL = re.compile(r'class="lbl-thr"[^>]*>próg −\d+ mm</text>')


def weather(start: date, end: date, rain: float, et0: float) -> tuple[list[str], list[float], list[float]]:
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return days, [rain] * len(days), [et0] * len(days)


def verdict_html(page: str) -> str:
    """The verdict block itself: badge, number, sentence, bar and how-line (without the SMSR and satellite rows)."""
    return re.search(r'<section class="verdict".*?<dl class="facts">', page, flags=re.S).group(0)


def sentence_html(page: str) -> str:
    return re.search(r'id="zdanie-werdyktu"[^>]*>(.*?)</p>', page, flags=re.S).group(1)


@pytest.mark.parametrize("crop", [c for c in CropGroup if c != CropGroup.INNA])
def test_sentence_names_every_crop_group_in_the_genitive(crop: CropGroup) -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 9, 30), rain=0.2, et0=5.0)
    v = assess(d, p, e, date(2023, 9, 30), crop, "IV")
    assert v.state == "below"
    assert v.sentence.endswith(f"poniżej progu suszy dla {CROP_GENITIVE[crop]} na tej glebie.")


def test_genitive_examples_from_the_report() -> None:
    assert CROP_GENITIVE[CropGroup.ZBOZA_JARE] == "zbóż jarych"
    assert CROP_GENITIVE[CropGroup.ROSLINY_STRACZKOWE] == "roślin strączkowych"
    assert len(CROP_GENITIVE) == len(CropGroup)


def test_period_with_more_than_10_percent_missing_days_is_left_out() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    p, e = list(p), list(e)
    # Period 7 is 21.05-20.07 (61 days): remove 10 days of precipitation and 3 of ET0 in July.
    for i, day in enumerate(d):
        if "2023-07-01" <= day <= "2023-07-10":
            p[i] = None
        if "2023-07-11" <= day <= "2023-07-13":
            e[i] = None
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    assert v.period is not None and v.period.n != 7
    assert "Okres 7 pominięty: brak opadu albo parowania w 13 z 61 dni." in v.note
    p7 = next(x for x in v.periods if x.n == 7)
    assert p7.margin_mm is None


def test_gap_of_at_most_10_percent_still_counts() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    p = [None if "2023-07-01" <= day <= "2023-07-06" else x for day, x in zip(d, p, strict=True)]
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    assert "pominięty" not in v.note
    assert any(x.n == 7 and x.margin_mm is not None for x in v.periods)


def test_all_periods_with_gaps_give_no_verdict_with_a_reason() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    p = [None if i % 5 == 0 else x for i, x in enumerate(p)]
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    assert v.state == "no_data"
    assert v.badge == ""
    assert v.sentence.startswith("Brak: ") and " bo " in v.sentence
    assert "brakuje ponad 10% dni" in v.sentence


def test_no_weather_is_one_sentence_brak_bo() -> None:
    v = assess([], [], [], date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    assert v.state == "no_data"
    assert v.sentence.startswith("Brak: bilansu wody, bo ")


def test_running_period_counts_days_and_has_no_badge() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 5, 1), rain=0.0, et0=4.0)
    v = assess(d, p, e, date(2023, 5, 1), CropGroup.ZBOZA_JARE, "I")
    assert v.state == "running" and v.badge == ""
    assert v.note == "okres jeszcze trwa: 42 z 61 dni"
    assert "20.05.2023" in v.sentence


def test_wet_season_sentence_says_rain_exceeded_evaporation() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=5.0, et0=3.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "II")
    assert v.badge == BADGE_ABOVE
    assert v.sentence.startswith("W tych 60 dniach spadło o ")
    assert "powyżej progu suszy dla zbóż jarych" in v.sentence


def test_out_of_season_with_soil_compares_the_last_season() -> None:
    d, p, e = weather(date(2026, 3, 1), date(2026, 11, 21), rain=0.5, et0=4.0)
    v = assess(d, p, e, date(2026, 11, 21), CropGroup.ROSLINY_STRACZKOWE, "II")
    assert v.state == "out_of_season" and v.badge == "Sezon 2026"
    assert v.sentence.startswith("W sezonie 2026, w dniach ")
    assert "poniżej progu suszy dla roślin strączkowych" in v.sentence


@pytest.mark.parametrize(
    ("crop", "soil", "words"),
    [
        (CropGroup.INNA, "I", "„Inna uprawa”"),
        (CropGroup.BURAK_CUKROWY, "I", "nie zaleca uprawy buraka cukrowego"),
        (CropGroup.KUKURYDZA_ZIARNO, "I", "susza nie obniża plonu kukurydzy na ziarno"),
    ],
)
def test_no_threshold_gives_the_balance_and_why(crop: CropGroup, soil: str, words: str) -> None:
    day = date(2023, 5, 31)  # periods 1-2: "x" for maize
    d, p, e = weather(date(2023, 3, 1), day, rain=0.5, et0=4.0)
    v = assess(d, p, e, day, crop, soil)
    assert v.state == "no_threshold" and v.badge == ""
    assert v.kbw_mm is not None
    assert words in v.sentence
    assert "Tu pojawi" not in v.sentence


def test_unknown_soil_gives_the_range_of_thresholds() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, None)
    assert v.badge == ""
    # Constant weather: every period has the same balance, so period 1 is shown.
    assert "od −125 mm (kat. I) do −194 mm (kat. IV)" in v.sentence


def test_neighbour_category_result_is_in_the_note() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I", neighbour="II")
    assert v.note.startswith("Przy sąsiedniej kategorii gleby (kat. II): ")
    assert "mm poniżej progu" in v.note


def test_how_line_has_full_dates() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    assert re.search(
        r"\(okres \d+, \d\d\.\d\d\.2023–\d\d\.\d\d\.2023\) · próg z Dz\.U\. 2019 poz\. 739$", v.how
    )


def test_threshold_bar_labels_the_threshold_in_mm() -> None:
    d, p, e = weather(date(2023, 3, 1), date(2023, 7, 20), rain=0.5, et0=4.0)
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    svg = hbar_svg(v)
    assert THRESHOLD_LABEL.search(svg)
    assert f"próg {v.threshold_mm:.0f} mm".replace("-", "−") in svg


def test_report_route_shows_badge_threshold_tick_and_no_placeholder() -> None:
    section = verdict_html(html(DOBRCZ, gleba="II"))
    assert BADGE_BELOW in section or BADGE_ABOVE in section
    assert 'class="hbar-thr"' in section
    assert THRESHOLD_LABEL.search(section)
    assert "Tu pojawi" not in sentence_html(section)
    assert DISCLAIMER in section
    assert 'id="plakietka"' in section


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY], ids=["dobrcz", "gora-swietej-malgorzaty"])
@pytest.mark.parametrize("path", ["/raport", "/raport/druk"])
def test_demo_parcels_have_no_placeholder_in_the_verdict(params: dict, path: str) -> None:
    section = verdict_html(html(params, path=path))
    assert "Tu pojawi" not in section
    sentence = sentence_html(section)
    assert re.search(r"\d+ mm", sentence)
