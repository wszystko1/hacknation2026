"""Diagnosis of the causes: every rule that holds gives a cause with the parcel's number; the split closes."""

from __future__ import annotations

import dataclasses
import re

import pytest

from app.advice.diagnosis import (
    BOTH_FACTORS,
    LESS_RAIN_SHARE,
    MORE_EVAPORATION_SHARE,
    RULES,
    attribution,
    balance_split,
    diagnose,
    need,
    season_history,
    usual_period,
)
from app.context import ReportContext
from app.drought.kbw import assess
from app.inputs import parse_request
from app.models import Diagnosis, Report
from app.report import build_context
from app.soil import assess_soil
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, client, html, query, report

PARCELS = [DOBRCZ, GSM_TODAY]
BALANCE_SENTENCE = re.compile(r"spadło \d+ mm, parowanie zabrało \d+ mm")


def make_context(
    params: dict, *, slope_pct: float | None = None, drop_weather: bool = False
) -> ReportContext:
    """The context up to the verdict, as the report builds it; the slope can be set for a rule test."""
    req, errors = parse_request(params)
    assert req is not None, errors
    ctx = build_context(req)
    if slope_pct is not None:
        terrain = dataclasses.replace(ctx.data.terrain.data, slope_mean_pct=slope_pct)
        ctx.data = dataclasses.replace(ctx.data, terrain=dataclasses.replace(ctx.data.terrain, data=terrain))
    ctx.soil = assess_soil(ctx)
    w = ctx.data.weather.data
    if drop_weather:
        ctx.data = dataclasses.replace(ctx.data, weather=dataclasses.replace(ctx.data.weather, data=None))
    dates, rain, et0 = ([], [], []) if drop_weather else (w.dates, w.precipitation_mm, w.et0_mm)
    ctx.verdict = assess(dates, rain, et0, req.day, req.crop, ctx.soil.category)
    return ctx


@pytest.mark.parametrize("params", PARCELS)
def test_no_action_repeats_the_balance_sentence_and_every_cause_has_a_number(params: dict) -> None:
    r = report(params)
    assert r.diagnosis.causes
    for c in r.diagnosis.causes:
        assert re.search(r"\d", c.words), c.words
        assert not BALANCE_SENTENCE.search(c.words)
    for a in r.actions:
        assert a.cause != r.verdict.sentence
        assert not BALANCE_SENTENCE.search(a.cause), a.cause


def test_causes_are_all_rules_that_hold_strongest_first() -> None:
    causes = report(DOBRCZ).diagnosis.causes
    assert {c.code for c in causes} >= {"malo_opadu", "duze_parowanie", "gleba_lekka"}
    measured = [c.strength_mm for c in causes if c.strength_mm is not None]
    assert measured == sorted(measured, reverse=True)
    assert [c.code for c in causes][: len(measured)] == [c.code for c in causes if c.strength_mm is not None]


def test_without_an_assessment_the_diagnosis_is_empty() -> None:
    ctx = make_context(DOBRCZ, drop_weather=True)
    assert ctx.verdict is not None and ctx.verdict.state == "no_data"
    assert diagnose(ctx) == Diagnosis()


@pytest.mark.parametrize(("slope", "runoff"), [(2.5, True), (2.0, False), (1.4, False)])
def test_runoff_cause_needs_a_mean_slope_above_two_percent(slope: float, runoff: bool) -> None:
    codes = {c.code for c in diagnose(make_context(DOBRCZ, slope_pct=slope)).causes}
    assert ("splyw" in codes) is runoff


def test_parcel_with_little_rain_and_a_slope_gets_both_causes() -> None:
    causes = diagnose(make_context(DOBRCZ, slope_pct=3.1)).causes
    by_code = {c.code: c for c in causes}
    assert {"malo_opadu", "splyw"} <= by_code.keys()
    assert "3,1%" in by_code["splyw"].words and re.search(r"\d+ m\b", by_code["splyw"].words)


def test_usual_balance_is_the_median_of_the_earlier_seasons() -> None:
    ctx = make_context(DOBRCZ)
    usual = usual_period(ctx)
    assert usual is not None and usual.n_seasons == 9
    assert diagnose(ctx).usual_kbw_mm == usual.kbw_mm
    assert abs((usual.precip_mm - usual.et0_mm) - usual.kbw_mm) <= 0.1


@pytest.mark.parametrize("params", PARCELS)
def test_waterfall_parts_add_up_to_the_balance_of_the_period(params: dict) -> None:
    ctx = make_context(params)
    split = balance_split(ctx)
    assert split is not None and ctx.verdict is not None and ctx.verdict.period is not None
    assert abs(split.usual_mm + split.rain_step_mm + split.evaporation_step_mm - split.result_mm) <= 1.0
    assert split.result_mm == ctx.verdict.period.kbw_mm


def test_history_has_ten_seasons_ending_with_the_verdicts_own() -> None:
    ctx = make_context(DOBRCZ)
    seasons = season_history(ctx)
    assert [s.year for s in seasons] == list(range(2014, 2024))
    assert seasons[-1].period.n == ctx.verdict.period.n
    assert seasons[-1].period.margin_mm == ctx.verdict.margin_mm


def test_every_rule_names_its_threshold_and_confidence() -> None:
    assert {r.code for r in RULES} == {
        "malo_opadu",
        "duze_parowanie",
        "gleba_lekka",
        "splyw",
        "faza_wrazliwa",
    }
    for r in RULES:
        assert r.condition and r.confidence
        assert r.source or r.confidence == "propozycja zespołu"


@pytest.mark.parametrize("params", PARCELS)
def test_causes_stand_above_the_retention_section_in_both_views(params: dict) -> None:
    from markupsafe import escape

    r = report(params)
    for path in ("/raport", "/raport/druk"):
        page = html(params, path, **({"widok": "doradca"} if path == "/raport" else {}))
        end = page.index('id="retencja"')
        for c in r.diagnosis.causes:
            assert 0 <= page.find(str(escape(c.words))) < end, (path, c.words)


@pytest.mark.parametrize("params", PARCELS)
def test_adviser_view_shows_rule_thresholds_with_confidence(params: dict) -> None:
    r = Report.model_validate(client.get(f"/api/raport?{query(params, widok='doradca')}").json())
    keys = {kv.key: kv.value for kv in r.section("przyczyny").advisor}
    assert any("propozycja zespołu" in v for v in keys.values())
    assert all(any(rule.label.lower() in k for k in keys) for rule in RULES)


def test_thresholds_are_85_and_110_percent() -> None:
    assert (LESS_RAIN_SHARE, MORE_EVAPORATION_SHARE) == (0.85, 1.10)


@pytest.mark.parametrize("params", PARCELS)
def test_two_definitions_of_usual_and_a_label_only_when_they_agree(params: dict) -> None:
    attr = attribution(make_context(params))
    assert attr is not None
    assert attr.label == (attr.label_season if attr.label_season == attr.label_medians else BOTH_FACTORS)
    assert abs((attr.season_rain_mm - attr.season_et0_mm) - usual_period(make_context(params)).kbw_mm) <= 0.1


@pytest.mark.parametrize("params", PARCELS)
def test_label_is_stable_when_any_earlier_season_is_dropped(params: dict) -> None:
    ctx = make_context(params)
    full = attribution(ctx)
    assert full is not None
    years = usual_period(ctx).years
    assert len(years) == 9
    for year in years:
        dropped = attribution(ctx, without_year=year)
        assert dropped is not None
        assert dropped.label in {full.label, BOTH_FACTORS}, (year, dropped.label, full.label)


def test_label_is_both_factors_when_the_definitions_disagree() -> None:
    from app.advice.diagnosis import MAINLY_EVAPORATION, MAINLY_RAIN, _factor

    # same period, two different "usual" values: one says rain, the other evaporation
    assert _factor(100, 200, 150, 200) == MAINLY_RAIN
    assert _factor(100, 200, 100, 150) == MAINLY_EVAPORATION
    assert _factor(100, 200, 100, 200) == BOTH_FACTORS


@pytest.mark.parametrize("params", PARCELS)
def test_place_and_crop_causes_are_not_ranked_and_the_need_lists_every_cause(params: dict) -> None:
    d = report(params).diagnosis
    assert need(d) == [c.code for c in d.causes]
    for c in d.causes:
        assert c.evidence, c.code
        if c.axis != "pogoda":
            assert c.strength_mm is None
    axes = [c.axis for c in d.causes]
    assert axes == sorted(axes, key=lambda a: a != "pogoda")


def test_adviser_route_shows_axis_and_evidence_of_every_cause_and_both_definitions() -> None:
    page = html(DOBRCZ, widok="doradca")
    r = report(DOBRCZ, widok="doradca")
    rows = {kv.key: kv.value for kv in r.section("przyczyny").advisor}
    for c in r.diagnosis.causes:
        key = next(k for k in rows if k.startswith(f"Przyczyna: {c.code} · oś: "))
        assert re.search(r"\d", rows[key]), key
    assert any(k.startswith("Zwykły sezon (a)") for k in rows)
    assert any(k.startswith("Zwykły sezon (b)") for k in rows)
    assert "Zwykły sezon (b)" in page
    farmer = html(DOBRCZ)
    assert "Zwykły sezon (b)" not in farmer and "oś: " not in farmer
