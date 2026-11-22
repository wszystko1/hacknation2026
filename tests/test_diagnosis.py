"""Diagnosis of the causes: every rule that holds gives a cause with the parcel's number; the split closes."""

from __future__ import annotations

import dataclasses
import re
from datetime import date

import pytest

from app.advice.diagnosis import (
    BOTH_FACTORS,
    LESS_RAIN_SHARE,
    MORE_EVAPORATION_SHARE,
    RULES,
    RUNOFF_MILD_SLOPE_PCT,
    RUNOFF_SLOPE_PCT,
    UsualSeason,
    _rain_cause,
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
from app.models import Diagnosis, PeriodBalance, Report
from app.report import build_context
from app.soil import assess_soil
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, client, html, query, report

PARCELS = [DOBRCZ, GSM_TODAY]
KINDS = ("przepis", "literatura", "kalibracja danych", "propozycja zespołu")
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


@pytest.mark.parametrize(
    ("slope", "level"),
    [(1.4, None), (1.99, None), (2.0, "łagodny"), (2.85, "łagodny"), (4.9, "łagodny"), (5.0, "wyraźny"), (6.0, "wyraźny")],
)
def test_runoff_has_two_levels_mild_from_two_percent_and_clear_from_five(slope: float, level: str | None) -> None:
    causes = {c.code: c for c in diagnose(make_context(DOBRCZ, slope_pct=slope)).causes}
    if level is None:
        assert "splyw" not in causes
        return
    c = causes["splyw"]  # the same code at both levels: the retention actions of the cause stay open
    assert c.evidence["poziom"] == level
    assert c.confidence == ("niska" if level == "łagodny" else "średnia")
    assert c.threshold_source == "literatura"
    assert ("ulewn" in c.words) is (level == "łagodny")


def test_mild_runoff_keeps_the_retention_actions_of_the_cause() -> None:
    from app.models import AXIS_OF_CAUSE

    assert RUNOFF_MILD_SLOPE_PCT == 2.0 and RUNOFF_SLOPE_PCT == 5.0
    mild = diagnose(make_context(DOBRCZ, slope_pct=2.85))
    clear = diagnose(make_context(DOBRCZ, slope_pct=6.0))
    assert need(mild).count("splyw") == need(clear).count("splyw") == 1
    assert AXIS_OF_CAUSE["splyw"] == "miejsce"


def test_gora_swietej_malgorzaty_gets_mild_runoff_and_keeps_retention() -> None:
    r = report(GSM_TODAY)
    runoff = next((c for c in r.diagnosis.causes if c.code == "splyw"), None)
    assert runoff is not None and runoff.evidence["poziom"] == "łagodny" and runoff.confidence == "niska"
    assert any(a.group == "retencja" for a in r.actions)


def _period(precip: float) -> PeriodBalance:
    return PeriodBalance(
        n=4, start=date(2023, 4, 21), end=date(2023, 6, 20), days=61, precip_mm=precip, et0_mm=200.0,
        kbw_mm=round(precip - 200.0, 1), threshold_mm=None, margin_mm=None, complete=True,
    )


@pytest.mark.parametrize(
    ("share", "flag", "klasa"),
    [(0.31, True, "skrajnie suchy"), (0.50, True, "bardzo suchy"), (0.74, True, "bardzo suchy"),
     (0.75, True, "suchy"), (0.88, True, "suchy"), (0.89, True, "suchy"), (0.90, False, None)],
)
def test_less_rain_flag_is_up_to_89_percent_with_the_imgw_class(share: float, flag: bool, klasa: str | None) -> None:
    usual = UsualSeason(n_seasons=9, years=list(range(2014, 2023)), kbw_mm=-90.0, precip_mm=100.0, et0_mm=190.0)
    c = _rain_cause(_period(100.0 * share), usual)
    assert (c is not None) is flag
    if c is not None:
        assert c.evidence["klasa_opadu"] == klasa and c.threshold_source == "literatura"


def test_dobrcz_rain_flag_is_up_and_the_flat_parcel_has_no_runoff() -> None:
    causes = {c.code: c for c in report(DOBRCZ).diagnosis.causes}
    rain = causes["malo_opadu"].evidence  # far below the usual season
    assert rain["opad_do_zwyklego_proc"] <= 89 and rain["klasa_opadu"] in ("suchy", "bardzo suchy", "skrajnie suchy")
    assert "splyw" not in causes  # mean slope 1.4%


def test_parcel_with_little_rain_and_a_slope_gets_both_causes() -> None:
    causes = diagnose(make_context(DOBRCZ, slope_pct=6.1)).causes
    by_code = {c.code: c for c in causes}
    assert {"malo_opadu", "splyw"} <= by_code.keys()
    assert "6,1%" in by_code["splyw"].words and re.search(r"\d+ m\b", by_code["splyw"].words)


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


def test_every_rule_and_every_cause_names_the_kind_of_its_threshold_source() -> None:
    assert {r.code for r in RULES} == {
        "malo_opadu",
        "duze_parowanie",
        "gleba_lekka",
        "splyw",
        "faza_wrazliwa",
    }
    for r in RULES:
        assert r.condition and r.threshold_source in KINDS
        assert r.source or r.threshold_source == "propozycja zespołu"
    assert {r.code: r.threshold_source for r in RULES} == {
        "malo_opadu": "literatura",
        "duze_parowanie": "kalibracja danych",
        "gleba_lekka": "przepis",
        "splyw": "literatura",
        "faza_wrazliwa": "przepis",
    }
    for c in report(DOBRCZ).diagnosis.causes + report(GSM_TODAY).diagnosis.causes:
        assert c.threshold_source in KINDS, c.code


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
def test_adviser_view_shows_rule_thresholds_with_the_kind_of_source(params: dict) -> None:
    r = Report.model_validate(client.get(f"/api/raport?{query(params, widok='doradca')}").json())
    keys = {kv.key: kv.value for kv in r.section("przyczyny").advisor}
    rules = {k: v for k, v in keys.items() if k.startswith("Reguła: ")}
    assert len(rules) == len(RULES)
    assert all("źródło progu: " in v for v in rules.values())
    assert not any("propozycja zespołu" in v for v in rules.values())
    assert any("źródło progu: literatura" in v and "Kaczorowskiej" in v for v in rules.values())
    assert any("źródło progu: kalibracja danych" in v for v in rules.values())
    assert all(any(rule.label.lower() in k for k in keys) for rule in RULES)


def test_thresholds_are_89_and_110_percent() -> None:
    assert (LESS_RAIN_SHARE, MORE_EVAPORATION_SHARE) == (0.89, 1.10)


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
