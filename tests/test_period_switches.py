"""The two switches that choose the verdict's period and evaporation formula."""

import pytest

from app.drought.kbw import VERDICT_ET_ENV, VERDICT_PERIOD_ENV, verdict_et_method, verdict_period_mode


def test_defaults_are_the_current_period_and_dg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VERDICT_PERIOD_ENV, raising=False)
    monkeypatch.delenv(VERDICT_ET_ENV, raising=False)
    assert verdict_period_mode() == "current"
    assert verdict_et_method() == "dg"


@pytest.mark.parametrize(
    ("value", "expected"), [("worst", "worst"), (" Worst ", "worst"), ("x", "current"), ("", "current")]
)
def test_period_switch_reads_the_variable_at_every_call(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    monkeypatch.setenv(VERDICT_PERIOD_ENV, value)
    assert verdict_period_mode() == expected


@pytest.mark.parametrize(
    ("value", "expected"), [("dg", "dg"), ("DG", "dg"), ("fao56", "fao56"), ("x", "dg")]
)
def test_formula_switch_falls_back_to_dg(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    monkeypatch.setenv(VERDICT_ET_ENV, value)
    assert verdict_et_method() == expected
