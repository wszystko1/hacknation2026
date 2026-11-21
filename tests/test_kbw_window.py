"""The running window ends on the last full dekad."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.drought.kbw import assess, last_full_dekad_end
from app.models import CropGroup


def _series(start: date, end: date, rain: float, et0: float):
    days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return days, [rain] * len(days), [et0] * len(days)


@pytest.mark.parametrize(
    ("day", "end"),
    [
        (date(2023, 5, 15), date(2023, 5, 10)),
        (date(2023, 5, 10), date(2023, 5, 10)),
        (date(2023, 5, 9), date(2023, 4, 30)),
        (date(2023, 5, 25), date(2023, 5, 20)),
        (date(2023, 5, 31), date(2023, 5, 31)),
        (date(2024, 2, 29), date(2024, 2, 29)),
    ],
)
def test_last_full_dekad(day: date, end: date) -> None:
    assert last_full_dekad_end(day) == end


def test_window_on_15_may_has_51_days() -> None:
    d, p, e = _series(date(2023, 3, 1), date(2023, 5, 15), 0.0, 4.0)
    v = assess(d, p, e, date(2023, 5, 15), CropGroup.ZBOZA_JARE, "I")
    assert v.period is not None and v.period.days == 51
    assert v.kbw_mm == pytest.approx(-204.0)
    assert v.et_method == "fao56"


def test_first_days_of_the_season_have_no_balance_yet() -> None:
    d, p, e = _series(date(2023, 3, 1), date(2023, 3, 25), 1.0, 1.0)
    v = assess(d, p, e, date(2023, 3, 25), CropGroup.ZBOZA_JARE, "I")
    assert v.state == "no_data"
    assert v.sentence.startswith("Brak:")


def test_a_finished_period_does_not_depend_on_the_dekad_rule() -> None:
    d, p, e = _series(date(2023, 3, 1), date(2023, 7, 20), 1.0, 3.0)
    on_the_day = assess(d, p, e, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    later = assess(d + ["2023-07-21"], p + [1.0], e + [3.0], date(2023, 7, 21), CropGroup.ZBOZA_JARE, "I")
    assert on_the_day.kbw_mm == later.kbw_mm
