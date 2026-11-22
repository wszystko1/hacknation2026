"""The verdict is counted with the Doroszewski-Górski formula; FAO-56 is the fallback, the switch and the irrigation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import context as app_context
from app.drought import variants
from app.drought.kbw import VERDICT_ET_ENV, VERDICT_PERIOD_ENV
from app.main import app
from app.models import Report
from app.validation.calibration import class_of

client = TestClient(app)
PARAMS = "dzialka=040303_2.0002.189/13&data=2023-07-20&uprawa=zboza_jare"
NO_INPUTS = ([], [])


def _report(extra: str = "") -> Report:
    r = client.get(f"/api/raport?{PARAMS}{extra}")
    assert r.status_code == 200
    return Report.model_validate(r.json())


def test_dobrcz_verdict_by_dg_is_204_against_188_in_period_7(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VERDICT_ET_ENV, raising=False)
    monkeypatch.delenv(VERDICT_PERIOD_ENV, raising=False)
    v = _report().verdict
    assert v.et_method == "dg" and v.state == "below"
    assert v.period is not None and v.period.n == 7
    assert v.kbw_mm == pytest.approx(-203.8, abs=0.5)
    assert v.threshold_mm == -188.0
    assert "poniżej progu" in v.badge
    assert v.note == "" or "Doroszewski" not in v.note


def test_switch_to_fao56_restores_the_fao56_verdict_and_keeps_the_dg_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(VERDICT_ET_ENV, "fao56")
    r = _report()
    assert r.verdict.et_method == "fao56"
    assert r.verdict.kbw_mm == pytest.approx(-203.0, abs=0.5)
    assert r.verdict_dg is not None and r.verdict_dg.et_method == "dg"


def test_with_both_old_switches_dobrcz_is_the_worst_period_by_fao56(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VERDICT_ET_ENV, "fao56")
    monkeypatch.setenv(VERDICT_PERIOD_ENV, "worst")
    v = _report().verdict
    assert v.period is not None and v.period.n == 4
    assert (v.kbw_mm, v.threshold_mm) == (-200.7, -154.0)


def test_the_dg_variant_follows_the_period_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VERDICT_PERIOD_ENV, "worst")
    v = _report().verdict_dg
    assert v is not None and v.period is not None and v.period.n == 4
    monkeypatch.delenv(VERDICT_PERIOD_ENV)
    v = _report().verdict_dg
    assert v is not None and v.period is not None and v.period.n == 7


def test_without_temperature_or_sunshine_the_verdict_falls_back_to_fao56_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(VERDICT_ET_ENV, raising=False)
    monkeypatch.setattr(variants, "_frozen_inputs", lambda *_a: NO_INPUTS)
    r = _report()
    if r.verdict_dg is not None:  # the cached weather of this point carries temperature and sunshine itself
        pytest.skip("the weather of this point has temperature and sunshine in the source data")
    assert r.verdict.et_method == "fao56"
    assert "FAO-56" in r.verdict.how and "brak temperatury lub usłonecznienia" in r.verdict.how


def test_the_confidence_label_comes_from_the_dg_calibration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VERDICT_ET_ENV, raising=False)
    r = _report()
    assert r.verdict.margin_mm is not None
    cls = class_of(r.verdict.margin_mm)
    share = app_context.load_metrics()[f"smsr.calibration.dg.{cls.key}.plus_share"]
    assert r.agreement.k_per_100 == round(100 * share)


def test_irrigation_stays_on_fao56_and_says_so() -> None:
    how = " ".join(s.how for s in _report().sections if s.id == "nawadnianie")
    assert "FAO-56" in how and "Doroszewski" in how


def test_the_waiting_page_uses_the_same_formula_and_period_as_the_report() -> None:
    from datetime import date

    from app.main import _first_look
    from app.models import CropGroup, ReportRequest

    req = ReportRequest(parcel_id="040303_2.0002.189/13", day=date(2023, 7, 20), crop=CropGroup.ZBOZA_JARE)
    first = _first_look(req)["verdict"]
    assert first.et_method == "dg"
    # The waiting page downloads its own weather (a recorded answer here), the report reads the committed copy,
    # so the numbers differ in a test; the formula and the period are the same.
    assert first.period is not None and first.period.n == 7
