"""The chain models: Cause axis, Geometry, Range, Candidate."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import Action, Candidate, Cause, Geometry, Range


def test_range_validates() -> None:
    Range(low=5, high=10, unit="m", source="propozycja zespołu")
    with pytest.raises(ValidationError):
        Range(low=10, high=5, unit="m", source="x")
    with pytest.raises(ValidationError):
        Range(low=1, high=2, unit="", source="x")
    with pytest.raises(ValidationError):
        Range(low=1, high=2, unit="m", source=" ")


def test_geometry_vertices() -> None:
    Geometry(type="point", coordinates=[(1.0, 2.0)])
    Geometry(type="line", coordinates=[(0, 0), (1, 1)], azimuth_deg=45, length_m=1.4)
    with pytest.raises(ValidationError):
        Geometry(type="polygon", coordinates=[(0, 0), (1, 1)])
    with pytest.raises(ValidationError):
        Geometry(type="point", coordinates=[(0, 0), (1, 1)])


def test_candidate_without_geometry_needs_reason_and_low_confidence() -> None:
    with pytest.raises(ValidationError):
        Candidate(action_id="a")
    with pytest.raises(ValidationError):
        Candidate(action_id="a", no_place_reason="teren płaski")
    with pytest.raises(ValidationError):
        Candidate(
            action_id="a", no_place_reason="brak miejsca na działce, bo teren płaski", confidence="wysoka"
        )
    c = Candidate(action_id="a", no_place_reason="brak miejsca na działce, bo teren płaski")
    assert c.confidence == "niska"


def test_candidate_json_round_trip() -> None:
    c = Candidate(
        action_id="pas-trawy",
        mechanism_id="m1",
        cause_codes=["splyw"],
        geometry=Geometry(type="line", coordinates=[(0, 0), (10, 0)], length_m=10),
        parameters={"szerokosc": Range(low=3, high=6, unit="m", source="propozycja zespołu")},
        evidence={"slope_pct": 4.2},
        confidence="średnia",
        risks=["erozja"],
    )
    assert Candidate.model_validate_json(c.model_dump_json()) == c


def test_cause_axis_defaults_and_strength() -> None:
    c = Cause(code="splyw", words="w")
    assert c.axis == "miejsce"
    assert Cause(code="malo_opadu", words="w", strength_mm=3.0).axis == "pogoda"
    with pytest.raises(ValidationError):
        Cause(code="splyw", words="w", strength_mm=3.0)


def test_action_new_fields_default_empty() -> None:
    a = Action(id="x", n=1, group="retencja", title="t", sentence="s", cause="c", when="w", source="s")
    assert a.cause_codes == [] and a.candidate is None
