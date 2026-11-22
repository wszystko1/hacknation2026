"""The retention section on the two demo parcels, through the route the page uses: the chain's sentences and map fields."""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.advice.placement import outlet_method
from app.advice.retention import placement_input, set_terrain_fields
from app.context import ReportContext
from app.datasource import frozen_copy
from app.models import ReportRequest
from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, report

IMPERATIVES = ("Zrób", "Zamontuj", "Wykonaj", "Zbuduj")


def _retention(params: dict):
    return [a for a in report(params).actions if a.group == "retencja"]


def test_the_two_demo_parcels_get_different_retention() -> None:
    a, b = _retention(DOBRCZ), _retention(GSM_TODAY)
    assert a and b

    def signature(actions):
        return [(x.id, x.place and (x.place.x_2180, x.place.y_2180)) for x in actions]

    assert signature(a) != signature(b)


@pytest.mark.xfail(reason="the catalogue sentences are still being reworded", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_no_retention_sentence_is_a_command_a_gap_or_a_runoff_volume(params: dict) -> None:
    for a in _retention(params):
        assert not a.sentence.startswith(IMPERATIVES), a.sentence
        assert "{" not in a.sentence and "Brak:" not in a.sentence, a.sentence
        assert not re.search(r"mm\s+odpływu", a.sentence, re.I), a.sentence


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_a_sentence_is_the_catalogue_row_with_the_numbers_of_the_parcel(params: dict) -> None:
    from app.advice.catalog import load_catalog

    for a in _retention(params):
        head = load_catalog()[a.id].sentence.split("{")[0]
        assert a.sentence.startswith(head), (a.id, a.sentence)
        assert "{" not in a.sentence and "Brak:" not in a.sentence, a.sentence


@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_a_pin_exists_only_for_an_action_with_a_geometry(params: dict) -> None:
    r = report(params)
    pinned = {m.n for m in r.map.markers} if r.map else set()
    for a in r.actions:
        if a.group == "retencja":
            assert (a.n in pinned) <= (a.candidate.geometry is not None), a.id


def test_grass_strip_sentence_has_a_length_and_tillage_a_direction_in_words() -> None:
    for params in (DOBRCZ, GSM_TODAY):
        for a in _retention(params):
            if a.id == "pas-trawy-przy-wyplywie" and a.place is not None:
                assert re.search(r"\d+\s*m\b", a.sentence), a.sentence
            if a.id == "uprawa-w-poprzek-stoku" and a.place is not None:
                assert " na " in a.sentence and "z " in a.sentence, a.sentence


def _context(parcel: str, day: date) -> ReportContext:
    from app.report import parcel_info

    data = frozen_copy(parcel, day)
    assert data is not None
    req = ReportRequest(parcel_id=parcel, day=day, crop="rosliny_straczkowe")
    return ReportContext(request=req, data=data, parcel=parcel_info(data))


def test_terrain_fields_are_set_and_d8_only_ones_follow_the_variant() -> None:
    ctx = _context("100403_2.0011.144", date(2026, 11, 21))
    inp = placement_input(ctx)
    assert inp is not None
    set_terrain_fields(ctx, inp)
    assert ctx.slope_pct is not None and ctx.slope_pct > 0
    # "lowest" leaves the outlet to the map (it falls back to the lowest boundary point)
    assert (ctx.outlet_2180 is not None) == (outlet_method() != "lowest")
    if outlet_method() == "d8":
        assert ctx.outlet_catchment_ha is not None
    else:
        assert ctx.flow_2180 == [] and ctx.outlet_catchment_ha is None
    if ctx.downhill_deg is not None:
        assert len(ctx.lower_edge_2180) >= 2
    else:
        assert ctx.runoff_reason
