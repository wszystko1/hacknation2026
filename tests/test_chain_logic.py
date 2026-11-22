"""The chain from cause to action on synthetic terrain: need, opportunity, candidate, validation, action."""

from __future__ import annotations

from datetime import date

import pytest

from app.advice.chain import MAX_ACTIONS, build_chain
from app.advice.terrain_model import build_terrain_model
from app.models import NO_PLACE_PREFIX, Cause
from tests.test_placement import X0, ditch, make_grid, make_input

SEASON = date(2026, 7, 10)
DORMANT = date(2026, 11, 21)
AREA_HA = 1.0


def cause(code: str) -> Cause:
    return Cause(code=code, words=f"przyczyna {code}", evidence={"x": 1})  # type: ignore[arg-type]


def chain(codes: list[str], *, in_season: bool, slope: float = 3.0, water=(), pits=()):
    inp = make_input(make_grid(slope_pct=slope, pits=pits), water)
    model = build_terrain_model(inp, margin_grid=True)
    day = SEASON if in_season else DORMANT
    return build_chain([cause(c) for c in codes], day, in_season, model, inp, AREA_HA)


def ids(actions) -> set[str]:
    return {a.id for a in actions}


def test_in_season_a_mechanism_without_need_does_not_enter() -> None:
    # only little rain is diagnosed: the runoff mechanisms (strip, balk, tillage) need the cause "splyw"
    actions = chain(["malo_opadu"], in_season=True)
    assert not ids(actions) & {"pas-trawy-przy-wyplywie", "pas-buforowy-wzdluz-rowu", "miedza-w-poprzek-stoku"}


def test_in_season_a_mechanism_without_opportunity_does_not_enter() -> None:
    actions = chain(["splyw"], in_season=True, slope=0.0)
    assert not ids(actions) & {"pas-trawy-przy-wyplywie", "pas-buforowy-wzdluz-rowu", "miedza-w-poprzek-stoku"}


def test_off_season_the_opportunity_alone_is_enough() -> None:
    # light soil is answered by the strip along a ditch, but the strip's need is runoff
    ditches = [ditch(X0 - 8, X0 - 4)]
    assert "pas-buforowy-wzdluz-rowu" not in ids(chain(["gleba_lekka"], in_season=True, water=ditches))
    assert "pas-buforowy-wzdluz-rowu" in ids(chain(["gleba_lekka"], in_season=False, water=ditches))


def test_a_flat_parcel_has_no_place_and_no_runoff_actions_in_the_season() -> None:
    actions = chain(["splyw", "malo_opadu"], in_season=True, slope=0.0)
    assert all(a.place is None for a in actions)


@pytest.mark.parametrize("in_season", [True, False])
def test_every_action_is_the_view_of_its_candidate(in_season: bool) -> None:
    codes = ["splyw", "malo_opadu", "gleba_lekka"]
    actions = chain(codes, in_season=in_season, water=[ditch(X0 - 12, X0 - 8)])
    assert actions
    for a in actions:
        c = a.candidate
        assert c is not None and c.mechanism_id and c.action_id == a.id
        assert a.cause_codes and set(a.cause_codes) <= set(codes)
        assert set(c.cause_codes) == set(a.cause_codes)
        assert (a.place is None) == (c.geometry is None)
        if c.geometry is None:
            assert c.no_place_reason.startswith(NO_PLACE_PREFIX) and c.confidence == "niska"
            assert a.no_place_reason == c.no_place_reason


def test_at_most_three_actions_by_falling_number_of_causes() -> None:
    codes = ["splyw", "malo_opadu", "gleba_lekka", "duze_parowanie", "faza_wrazliwa"]
    actions = chain(codes, in_season=False, water=[ditch(X0 - 12, X0 - 8)])
    assert 0 < len(actions) <= MAX_ACTIONS
    counts = [len(a.cause_codes) for a in actions]
    assert counts == sorted(counts, reverse=True)


def test_sentences_have_no_open_field_and_no_runoff_volume() -> None:
    actions = chain(["splyw", "malo_opadu"], in_season=False, water=[ditch(X0 - 12, X0 - 8)])
    for a in actions:
        assert "{" not in a.sentence and "Brak:" not in a.sentence, a.sentence
        assert "mm odpływu" not in a.sentence.lower()


def test_drain_regulator_is_a_low_confidence_potential_with_the_drainage_risk() -> None:
    actions = chain(["malo_opadu"], in_season=True, slope=0.8)
    drain = next((a for a in actions if a.id == "dreny-regulowany-odplyw"), None)
    assert drain is not None and drain.place is None
    assert drain.candidate.confidence == "niska"
    assert any("brak danych o drenażu" in r for r in drain.candidate.risks)


def test_a_new_weir_is_a_candidate_without_a_pin() -> None:
    actions = chain(["malo_opadu", "splyw"], in_season=True, water=[ditch(X0 - 12, X0 - 8)])
    weir = next((a for a in actions if a.id == "zastawka-nowa"), None)
    assert weir is not None and weir.place is None
    assert weir.candidate.geometry is None


def test_no_actions_without_a_diagnosed_cause() -> None:
    assert chain([], in_season=False) == []
