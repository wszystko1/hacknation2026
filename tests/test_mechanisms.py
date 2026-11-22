"""The mechanism layer: every catalogue action has a mechanism, and the need/opportunity rule."""

from __future__ import annotations

import typing

from app.advice.catalog import load_catalog
from app.advice.mechanisms import (
    DETECTORS,
    TERRAIN_INPUTS,
    has_opportunity,
    is_needed,
    load_mechanisms,
    mechanism_for,
)
from app.models import CauseCode


def test_nine_mechanisms() -> None:
    assert len(load_mechanisms()) == 9


def test_every_action_has_a_mechanism_with_detector_or_reason() -> None:
    catalog = load_catalog()
    assert catalog
    for action_id in catalog:
        m = mechanism_for(action_id)
        assert m.detector in DETECTORS, action_id
        if m.detector == "no_place":
            assert m.no_place_reason, action_id


def test_causes_are_known_codes() -> None:
    known = set(typing.get_args(CauseCode))
    for m in load_mechanisms().values():
        assert set(m.causes_addressed) <= known, m.id
        assert set(m.need_required) <= known, m.id
        assert m.terrain_input in TERRAIN_INPUTS, m.id


def test_action_causes_are_addressed_by_its_mechanism_or_declared() -> None:
    for action_id, row in load_catalog().items():
        assert set(row.causes) & set(mechanism_for(action_id).causes_addressed), action_id


def test_need_is_required_in_season_only() -> None:
    m = load_mechanisms()["slow_runoff_strip"]
    assert is_needed(m, {"splyw"}, in_season=True)
    assert not is_needed(m, {"malo_opadu"}, in_season=True)
    assert is_needed(m, {"malo_opadu"}, in_season=False)


def test_opportunity_reads_terrain_inputs() -> None:
    m = load_mechanisms()["hold_in_depression"]
    assert has_opportunity(m, {"zagłębienie": True})
    assert not has_opportunity(m, {"spadek": True})
    assert has_opportunity(load_mechanisms()["supply_missing_rain"], {})
