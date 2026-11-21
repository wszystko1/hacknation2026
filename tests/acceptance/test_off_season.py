"""K5: from 1 October to 20 March (the final's date included) the verdict and the plants do not apply; the report
gives the last season, the rain since 1 October against the norm and the actions whose time is now."""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

import pytest
from markupsafe import escape

from app.drought.kbw import assess
from app.models import CropGroup
from tests.acceptance.helpers import GSM_TODAY, html, report

TODAY = date(2026, 11, 21)
NEXT_SEASON = date(2027, 3, 21)


def weather(start: date, end: date, rain: float, et0: float) -> tuple[list[str], list[float], list[float]]:
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return days, [rain] * len(days), [et0] * len(days)


def test_first_of_october_and_twentieth_of_march_are_out_of_season() -> None:
    for day in (date(2025, 10, 1), date(2026, 3, 20)):
        d, p, e = weather(date(2025, 3, 1), day, rain=1.0, et0=2.0)
        v = assess(d, p, e, day, CropGroup.ROSLINY_STRACZKOWE, "II")
        assert v.state == "out_of_season", day
        assert v.season_year == 2025, day


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_verdict_and_plants_do_not_apply_today() -> None:
    r = report(GSM_TODAY)
    assert r.verdict.state == "out_of_season"
    assert r.crop_condition.state == "not_applicable"
    assert "nie dotyczy" in r.crop_condition.words
    page = html(GSM_TODAY)
    top = page[page.index('id="werdykt"') :]
    top = top[: top.index("</section>")]
    assert top.count("nie dotyczy") >= 2


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_last_season_and_rain_since_october_against_the_norm() -> None:
    o = report(GSM_TODAY).off_season
    assert o.season_year == 2026
    assert o.rain_mm is not None and o.rain_mm >= 0
    assert o.norm_mm is not None and o.norm_mm > 0
    assert o.n_years >= 5
    assert re.search(r"od 1\.X|od 1 października", o.sentence)
    assert any(str(n) in o.sentence for n in (math.floor(o.rain_mm), round(o.rain_mm)))
    assert str(escape(o.sentence)) in html(GSM_TODAY)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_actions_whose_time_is_now_come_before_the_next_season() -> None:
    r = report(GSM_TODAY)
    due_now = [a for a in r.actions if a.due and TODAY <= a.due < NEXT_SEASON]
    assert due_now
    titles = " ".join(a.title.lower() for a in due_now)
    assert any(word in titles for word in ("międzyplon", "resztk", "mulcz", "zastawk"))
