"""The 14 periods of the regulation and the balance on the demo parcel's frozen weather."""

from datetime import date

from app.datasource import frozen_copy
from app.drought.kbw import PERIODS, assess, period_dates, season_of
from app.drought.thresholds import threshold_mm
from app.models import CropGroup


def test_fourteen_periods_of_six_dekads() -> None:
    assert len(PERIODS) == 14
    assert period_dates(2023, 1) == (date(2023, 3, 21), date(2023, 5, 20))
    assert period_dates(2023, 14) == (date(2023, 8, 1), date(2023, 9, 30))


def test_season_of_november_is_out_of_monitoring() -> None:
    assert season_of(date(2026, 11, 21)) == (2026, False)
    assert season_of(date(2026, 2, 1)) == (2025, False)
    assert season_of(date(2026, 7, 1)) == (2026, True)


def test_threshold_table_spot_values() -> None:
    assert threshold_mm(CropGroup.ZBOZA_JARE, "I", 1) == -125
    assert threshold_mm(CropGroup.ZBOZA_JARE, "IV", 1) == -194
    assert threshold_mm(CropGroup.ZBOZA_JARE, "I", 10) is None  # "x"
    assert threshold_mm(CropGroup.INNA, "I", 5) is None


def test_balance_on_frozen_copy_is_rain_minus_evaporation() -> None:
    data = frozen_copy("040303_2.0002.189/13", date(2023, 7, 20))
    assert data is not None
    w = data.weather.data
    v = assess(w.dates, w.precipitation_mm, w.et0_mm, date(2023, 7, 20), CropGroup.ZBOZA_JARE, "I")
    assert v.period is not None
    assert v.period.kbw_mm == round(v.period.precip_mm - v.period.et0_mm, 1)
    assert [p.n for p in v.periods if p.complete] == list(range(1, 8))
    assert v.state in {"below", "above"}
