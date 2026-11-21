"""The Doroszewski-Górski formula (Żyłowska, Kozyra 2023, s. 67) and its daily use."""

from __future__ import annotations

import pytest

from app.drought.evaporation import day_length_h, etp_dg, etp_dg_daily


def test_formula_matches_a_hand_calculation_of_the_printed_form() -> None:
    # t = 15 deg C, h = 250 h, f = 14.5 h:
    # -89.6 + 0.0621*225 + 0.00448*250^1.66 + 9.1*14.5 = -89.6 + 13.9725 + 42.84 + 131.95 = 99.16 mm
    # The source prints the formula without a worked example, so the value was calculated by hand.
    assert etp_dg(15.0, 250.0, 14.5) == pytest.approx(99.16, abs=0.05)


def test_day_length_in_june_and_december_at_52_north() -> None:
    assert day_length_h(2023, 6, 52.0) == pytest.approx(16.5, abs=0.3)
    assert day_length_h(2023, 12, 52.0) == pytest.approx(7.6, abs=0.3)


def test_daily_values_are_the_month_divided_by_its_days() -> None:
    dates = [f"2023-06-{d:02d}" for d in range(1, 31)]
    daily = etp_dg_daily(dates, [15.0] * 30, [250 / 30] * 30, 52.0)
    monthly = etp_dg(15.0, 250.0, day_length_h(2023, 6, 52.0))
    assert sum(v for v in daily if v is not None) == pytest.approx(monthly, abs=0.1)


def test_a_month_with_too_few_days_gives_no_value() -> None:
    dates = [f"2023-06-{d:02d}" for d in range(1, 31)]
    temp: list[float | None] = [None] * 25 + [15.0] * 5
    daily = etp_dg_daily(dates, temp, [8.0] * 30, 52.0)
    assert daily == [None] * 30
