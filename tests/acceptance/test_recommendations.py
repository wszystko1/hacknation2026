"""K1: recommendations follow from a diagnosed cause; action no. 1 has a place on the photo or a stated reason;
irrigation gives mm and m³; soil and crop actions have a term; the plan goes to the link and the PDF."""

from __future__ import annotations

import dataclasses
import re

import pytest

from app import datasource
from tests.acceptance.helpers import DOBRCZ, client, html, query, report

PLACEHOLDER = "Tu pojawi się"


def test_no_recommendations_without_an_assessment(monkeypatch) -> None:
    real_load = datasource.load

    def without_weather(parcel_id, day, **kw):
        data, copy = real_load(parcel_id, day, **kw)
        gone = dataclasses.replace(data.weather, status="error", data=None, error="test: no weather")
        return dataclasses.replace(data, weather=gone), copy

    monkeypatch.setattr(datasource, "load", without_weather)
    r = report()
    assert r.verdict.state == "no_data"
    assert r.diagnosis.causes == []
    assert r.actions == []
    assert r.action_1 is None


def test_every_action_answers_a_diagnosed_cause() -> None:
    r = report()
    causes = {c.words for c in r.diagnosis.causes}
    assert causes
    assert r.actions
    for a in r.actions:
        assert a.cause in causes, (a.id, a.cause)


def test_action_1_has_a_numbered_place_on_the_photo_or_a_stated_reason() -> None:
    r = report()
    a1 = r.action_1
    assert a1 is not None and a1.n == 1 and a1.group == "retencja"
    if a1.place is not None:
        assert r.map is not None
        assert any(m.n == 1 for m in r.map.markers)
    else:
        assert a1.no_place_reason.startswith("brak miejsca na działce, bo ")


def test_action_numbers_are_1_to_m_in_report_order() -> None:
    r = report()
    assert [a.n for a in r.actions] == list(range(1, len(r.actions) + 1))
    order = {"retencja": 0, "uprawa": 1, "nawadnianie": 2}
    assert [order[a.group] for a in r.actions] == sorted(order[a.group] for a in r.actions)


def test_no_runoff_volume_is_reported() -> None:
    r = report()
    for a in r.section("retencja").actions:
        assert "m³" not in a.sentence
        assert not re.search(r"\d+\s*mm\s+(wody\s+)?odpływ", a.sentence)


def test_plan_state_goes_to_the_link_and_the_print_view() -> None:
    page = html(DOBRCZ, plan="1")
    assert "data-plan-count>1<" in page
    switches = re.findall(r"<input[^>]*data-plan-switch[^>]*>", page)
    assert any('value="1"' in tag and "checked" in tag for tag in switches)
    printed = client.get(f"/raport/druk?{query(DOBRCZ, plan='1')}").text
    assert "data-plan-count>1<" in printed


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_actions_have_parcel_numbers_terms_and_sources_not_placeholders() -> None:
    r = report()
    assert len(r.actions) >= 3
    for a in r.actions:
        for text in (a.title, a.sentence, a.when, a.source):
            assert text and PLACEHOLDER not in text, (a.id, text)
        assert re.search(r"\d", a.sentence), a.sentence


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_each_group_has_an_action_and_soil_actions_have_a_date() -> None:
    r = report()
    groups = {a.group for a in r.actions}
    assert groups == {"retencja", "uprawa", "nawadnianie"}
    for a in r.actions:
        if a.group == "uprawa":
            assert re.search(r"\d{1,2}\.\d{2}(\.\d{4})?|[IVX]+ \d{4}", a.when), a.when


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_irrigation_says_now_yes_or_no_with_dose_in_mm_and_m3_for_the_parcel() -> None:
    r = report()
    irrigation = [a for a in r.actions if a.group == "nawadnianie"]
    assert irrigation
    text = irrigation[0].title + " " + irrigation[0].sentence
    assert re.search(r"\bTeraz (tak|nie)\b", text, re.I)
    assert re.search(r"\d+\s*mm", text)
    assert re.search(r"\d[\d  ]*\s*m³", text)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_retention_places_come_from_geometry_with_ditch_and_outlet() -> None:
    from datetime import date

    from app.advice.placement import PlacementInput, find_places
    from app.datasource import frozen_copy

    data = frozen_copy("100403_2.0011.144", date(2024, 6, 20))
    terrain, water, parcel = data.terrain.data, data.water.data, data.parcel.data
    inp = PlacementInput(
        outline_2180=parcel.rings_2180[0], grid=terrain.grid,
        lowest_outline_point_2180=terrain.lowest_outline_point_2180, water=water.features,
        slope_mean_pct=terrain.slope_mean_pct,
    )  # fmt: skip
    kinds = {c.kind for c in find_places(inp) if c.place is not None}
    assert "punkt wypływu" in kinds
    assert "rów" in kinds  # the ditch runs along the parcel's edge (BDOT10k, 0.7 m)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_flat_parcel_without_ditch_gets_brak_miejsca_with_reason() -> None:
    from app.advice.placement import PlacementInput, find_places

    flat = PlacementInput(
        outline_2180=[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]], grid=None,
        lowest_outline_point_2180=None, water=[], slope_mean_pct=0.1,
    )  # fmt: skip
    candidates = find_places(flat)
    assert candidates
    assert all(c.place is None and c.reason for c in candidates)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_advisor_view_calls_rule_thresholds_team_proposals() -> None:
    page = html(DOBRCZ, widok="doradca")
    assert "propozycja zespołu" in page or "propozycje zespołu" in page
