"""The verdict is about the period that ends on the last full dekad; the worst period of the season stays beside it."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.drought.kbw import VERDICT_PERIOD_ENV, assess, main_verdict
from app.main import app
from app.models import CropGroup, ReportRequest
from app.report import build_report

PARCEL = "040303_2.0002.189/13"
JARE = CropGroup.ZBOZA_JARE
client = TestClient(app)


def season(start: date, end: date, rain_until: date, dry: tuple[float, float], wet: tuple[float, float]):
    """Daily series: `dry` (rain, et0) up to `rain_until`, `wet` after it."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    pick = [dry if d <= rain_until else wet for d in days]
    return [d.isoformat() for d in days], [p[0] for p in pick], [p[1] for p in pick]


def dobrcz(period: str | None = None):
    r = build_report(ReportRequest(parcel_id=PARCEL, day=date(2023, 7, 20), crop=JARE))
    return r


def test_dobrcz_verdict_is_period_7_and_the_worst_period_is_4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VERDICT_PERIOD_ENV, raising=False)
    v = dobrcz().verdict
    assert v.period is not None and v.period.n == 7
    assert (v.period.start, v.period.end) == (date(2023, 5, 21), date(2023, 7, 20))
    assert v.margin_mm is not None and v.margin_mm == pytest.approx(-16, abs=1.5)  # FAO-56: −15.0
    assert v.state == "below"
    assert v.worst is not None and v.worst.n == 4
    assert v.context.startswith("Najgorszy okres sezonu do tej pory: 21.04.2023–20.06.2023")


def test_switch_worst_restores_the_earlier_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VERDICT_PERIOD_ENV, "worst")
    v = dobrcz().verdict
    assert v.period is not None and v.period.n == 4
    assert v.margin_mm == -46.7 and v.kbw_mm == -200.7 and v.threshold_mm == -154.0
    assert v.context == ""


def test_report_page_follows_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    query = f"dzialka={PARCEL}&data=2023-07-20&uprawa=zboza_jare"
    monkeypatch.delenv(VERDICT_PERIOD_ENV, raising=False)
    assert "od 21 maja 2023 do 20 lipca 2023" in client.get(f"/raport?{query}").text
    monkeypatch.setenv(VERDICT_PERIOD_ENV, "worst")
    assert "od 21 kwietnia 2023 do 20 czerwca 2023" in client.get(f"/raport?{query}").text


def test_main_verdict_is_assess_with_the_period_of_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    d, p, e = season(date(2023, 3, 1), date(2023, 7, 20), date(2023, 6, 20), (0.5, 4.0), (3.0, 3.0))
    monkeypatch.delenv(VERDICT_PERIOD_ENV, raising=False)
    now = main_verdict(d, p, e, date(2023, 7, 20), JARE, "I")
    assert now.model_dump() == assess(d, p, e, date(2023, 7, 20), JARE, "I", period="current").model_dump()
    assert now.period is not None and now.period.n == 7
    monkeypatch.setenv(VERDICT_PERIOD_ENV, "worst")
    old = main_verdict(d, p, e, date(2023, 7, 20), JARE, "I")
    assert old.model_dump() == assess(d, p, e, date(2023, 7, 20), JARE, "I").model_dump()
    assert old.period is not None and old.period.n < 7


def test_current_period_ends_on_the_last_full_dekad_of_the_analysis_day() -> None:
    d, p, e = season(date(2023, 3, 1), date(2023, 7, 27), date(2023, 6, 20), (0.5, 4.0), (3.0, 3.0))
    v = assess(d, p, e, date(2023, 7, 27), JARE, "I", period="current")
    assert v.period is not None and v.period.end == date(2023, 7, 20)  # 27.VII is inside the dekad 21-31.VII


def test_worst_period_is_kept_and_named_when_it_differs() -> None:
    d, p, e = season(date(2023, 3, 1), date(2023, 7, 20), date(2023, 6, 20), (0.5, 4.0), (3.0, 3.0))
    v = assess(d, p, e, date(2023, 7, 20), JARE, "I", period="current")
    assert v.worst is not None and v.period is not None
    assert v.worst.margin_mm is not None and v.period.margin_mm is not None
    assert v.worst.margin_mm <= v.period.margin_mm
    assert v.worst.n != v.period.n and "Najgorszy okres sezonu do tej pory" in v.context


def test_no_context_line_when_the_current_period_is_the_worst() -> None:
    d, p, e = season(date(2023, 3, 1), date(2023, 7, 20), date(2023, 7, 20), (0.5, 4.0), (0.5, 4.0))
    v = assess(d, p, e, date(2023, 7, 20), CropGroup.ZIEMNIAK, "I", period="current")
    assert v.period is not None and v.worst is not None and v.worst.n == v.period.n
    assert v.context == ""


def test_crop_without_a_threshold_in_the_current_period_keeps_the_last_period_with_one() -> None:
    # spring cereals have thresholds in periods 1-9; on 15.IX the period ending 10.IX is period 12
    d, p, e = season(date(2023, 3, 1), date(2023, 9, 15), date(2023, 9, 15), (0.5, 4.0), (0.5, 4.0))
    v = assess(d, p, e, date(2023, 9, 15), JARE, "I", period="current")
    assert v.period is not None and v.period.n == 9
    assert v.state in {"below", "above"}
    assert "nie ma progu suszy dla zbóż jarych" in v.context


def test_late_crop_before_its_first_threshold_period_shows_the_balance_without_a_threshold() -> None:
    # maize has thresholds from period 4 (ends 20.VI); on 31.V only periods 1-2 are finished
    d, p, e = season(date(2023, 3, 1), date(2023, 5, 31), date(2023, 5, 31), (0.5, 4.0), (0.5, 4.0))
    v = assess(d, p, e, date(2023, 5, 31), CropGroup.KUKURYDZA_ZIARNO, "I", period="current")
    assert v.state == "no_threshold" and v.period is not None and v.period.n == 2


def test_out_of_season_is_the_same_in_both_modes() -> None:
    d, p, e = season(date(2023, 3, 1), date(2023, 11, 21), date(2023, 6, 20), (0.5, 4.0), (3.0, 3.0))
    a = assess(d, p, e, date(2023, 11, 21), JARE, "I", period="current")
    b = assess(d, p, e, date(2023, 11, 21), JARE, "I", period="worst")
    assert a.model_dump() == b.model_dump()
    assert a.state == "out_of_season" and a.context == "" and a.worst is None


def test_farmer_screen_names_the_window_when_the_day_is_inside_a_dekad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.farmer_view import balance_caption

    monkeypatch.delenv(VERDICT_PERIOD_ENV, raising=False)
    r = dobrcz()
    assert "ostatniej pełnej dekadzie" not in balance_caption(r)  # 20.VII ends the dekad itself
    later = r.model_copy(update={"request": r.request.model_copy(update={"day": date(2023, 7, 23)})})
    assert "okno kończy się na ostatniej pełnej dekadzie przed 23 lipca 2023" in balance_caption(later)
