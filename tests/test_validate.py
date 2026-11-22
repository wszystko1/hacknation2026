"""Validation of a candidate: each check adds a risk and lowers confidence one step; a clean candidate is unchanged."""

from __future__ import annotations

import pytest

from app.advice.terrain_model import FLAT_FLAG, TerrainModel
from app.advice.validate import (
    DRAIN_ACTION,
    MIN_BOUNDARY_DISTANCE_M,
    RISK_CUT,
    RISK_DRAINS,
    RISK_FLAT,
    validate,
)
from app.models import Candidate, Geometry


def _candidate(
    *,
    action_id: str = "pas-trawy",
    causes: list | None = None,
    confidence: str = "wysoka",
    **evidence: object,
) -> Candidate:
    return Candidate(
        action_id=action_id,
        cause_codes=causes or ["splyw"],
        geometry=Geometry(type="point", coordinates=[(500000.0, 500000.0)]),
        confidence=confidence,  # type: ignore[arg-type]
        evidence=evidence,  # type: ignore[arg-type]
    )


def _terrain(**kw: object) -> TerrainModel:
    return TerrainModel(**kw)  # type: ignore[arg-type]


def test_candidate_without_risks_is_unchanged() -> None:
    c = _candidate(zlewnia_ucieta=False, zlewnia_ha=3.0, dzialka_ha=2.0, odleglosc_od_granicy_m=45.0)
    out = validate(c, _terrain(catchment_ha=3.0, catchment_truncated=False))
    assert out == c and out is not c


def test_cut_catchment_is_a_risk_and_lowers_confidence() -> None:
    out = validate(_candidate(), _terrain(catchment_ha=5.0, catchment_truncated=True))
    assert RISK_CUT in out.risks and out.confidence == "średnia"


def test_cut_flag_in_evidence_is_enough_without_a_terrain_model() -> None:
    out = validate(_candidate(zlewnia_ucieta=True), None)
    assert out.risks == [RISK_CUT]


def test_large_external_catchment_matters_only_for_a_runoff_cause() -> None:
    evidence = {"zlewnia_ha": 12.0, "dzialka_ha": 2.0}
    runoff = validate(_candidate(**evidence), None)
    assert any("zlewnia zewnętrzna" in r for r in runoff.risks) and runoff.confidence == "średnia"
    weather = validate(_candidate(causes=["malo_opadu"], **evidence), None)
    assert weather.risks == [] and weather.confidence == "wysoka"


def test_external_catchment_at_the_threshold_is_not_a_risk() -> None:
    assert validate(_candidate(zlewnia_ha=6.0, dzialka_ha=2.0), None).risks == []


def test_place_closer_than_20_m_to_the_boundary() -> None:
    near = validate(_candidate(odleglosc_od_granicy_m=MIN_BOUNDARY_DISTANCE_M - 1), None)
    assert any("od granicy" in r for r in near.risks) and near.confidence == "średnia"
    assert validate(_candidate(odleglosc_od_granicy_m=MIN_BOUNDARY_DISTANCE_M), None).risks == []


def test_drain_regulator_always_carries_the_unknown_drainage_risk() -> None:
    out = validate(_candidate(action_id=DRAIN_ACTION, confidence="średnia"), None)
    assert out.risks == [RISK_DRAINS] and out.confidence == "niska"
    assert RISK_DRAINS not in validate(_candidate(), None).risks


def test_slope_below_resolution_from_the_terrain_flags() -> None:
    out = validate(_candidate(), _terrain(flags=[FLAT_FLAG]))
    assert out.risks == [RISK_FLAT] and out.confidence == "średnia"


def test_several_risks_lower_confidence_only_one_step() -> None:
    out = validate(_candidate(zlewnia_ucieta=True, odleglosc_od_granicy_m=5.0), _terrain(flags=[FLAT_FLAG]))
    assert len(out.risks) == 3 and out.confidence == "średnia"


def test_confidence_does_not_go_below_niska() -> None:
    out = validate(_candidate(confidence="niska", zlewnia_ucieta=True), None)
    assert out.confidence == "niska" and out.risks


def test_validating_twice_does_not_repeat_risks_or_lower_again() -> None:
    once = validate(_candidate(zlewnia_ucieta=True), None)
    twice = validate(once, None)
    assert twice.risks == once.risks and twice.confidence == once.confidence


@pytest.mark.parametrize("confidence", ["wysoka", "średnia", "niska"])
def test_argument_is_not_modified(confidence: str) -> None:
    c = _candidate(confidence=confidence, zlewnia_ucieta=True)
    validate(c, None)
    assert c.risks == [] and c.confidence == confidence
