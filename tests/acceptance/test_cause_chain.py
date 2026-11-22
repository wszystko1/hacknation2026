"""K1, K2: the chain cause -> mechanism -> candidate with geometry -> validation -> action.

A cause has an axis: weather (the period is drier than usual: the only axis ranked in mm), place (runoff, soil: why
this parcel holds water badly, no ranking) and crop. A mechanism is addressed by causes and enters the report when
the need (from the diagnosis) AND the opportunity (from the terrain) hold in the season; off season the opportunity
is enough. A candidate carries the geometry, ranges with a source, evidence, confidence, risks, formality and the
next step; the action's text, the map and the PDF all read it. Without a place the action stays, with the line
"brak miejsca na działce, bo …" and low confidence.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tests.acceptance.helpers import DOBRCZ, GSM_TODAY, report

AXES = {"pogoda", "miejsce", "uprawa"}
AXIS_OF = {
    "malo_opadu": "pogoda",
    "duze_parowanie": "pogoda",
    "splyw": "miejsce",
    "gleba_lekka": "miejsce",
    "faza_wrazliwa": "uprawa",
}
CATALOGUES = (Path("app/advice/catalog.csv"), Path("app/advice/catalog_retencja.csv"))
MECHANISMS = Path("app/advice/mechanisms.csv")


def _retention(params: dict):
    return [a for a in report(params).actions if a.group == "retencja"]


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_every_cause_has_an_axis_and_evidence(params: dict) -> None:
    for c in report(params).diagnosis.causes:
        assert c.axis == AXIS_OF[c.code], c
        assert c.evidence, c.code


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_only_weather_causes_are_ranked_in_mm() -> None:
    causes = report(DOBRCZ).diagnosis.causes
    for c in causes:
        if c.axis != "pogoda":
            assert c.strength_mm is None, c.code
    weather = [c.strength_mm for c in causes if c.axis == "pogoda" and c.strength_mm is not None]
    assert weather == sorted(weather, reverse=True)


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_actions_carry_cause_codes_that_the_diagnosis_recognised(params: dict) -> None:
    r = report(params)
    codes = {c.code for c in r.diagnosis.causes}
    assert r.actions
    for a in r.actions:
        assert a.cause_codes and set(a.cause_codes) <= codes, (a.id, a.cause_codes)


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_mechanisms_csv_has_nine_mechanisms() -> None:
    rows = list(csv.DictReader(MECHANISMS.open(encoding="utf-8")))
    assert len(rows) == 9
    assert len({r["id"] for r in rows}) == 9


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_every_catalogue_action_has_a_mechanism() -> None:
    known = {r["id"] for r in csv.DictReader(MECHANISMS.open(encoding="utf-8"))}
    for path in CATALOGUES:
        for row in csv.DictReader(path.open(encoding="utf-8")):
            assert row["mechanism"] in known, (path.name, row["action_id"], row["mechanism"])


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_the_action_is_the_view_of_its_candidate(params: dict) -> None:
    r = report(params)
    actions = [a for a in r.actions if a.group == "retencja"]
    assert actions
    marked = {m.n for m in r.map.markers} if r.map else set()
    for a in actions:
        cand = a.candidate
        assert cand is not None and cand.mechanism_id and cand.action_id == a.id, a.id
        assert set(cand.cause_codes) == set(a.cause_codes), a.id
        assert (a.place is None) == (cand.geometry is None), a.id
        if cand.geometry is None:
            assert cand.no_place_reason.startswith("brak miejsca na działce, bo "), a.id
            assert cand.confidence == "niska", a.id
            assert a.n not in marked, a.id
        else:
            assert cand.geometry.type in {"point", "line", "polygon"}, a.id


@pytest.mark.xfail(reason="not built yet", strict=False)
def test_candidate_parameters_are_ranges_with_a_source() -> None:
    for a in _retention(DOBRCZ):
        for name, rng in (a.candidate.parameters if a.candidate else {}).items():
            assert rng.low <= rng.high and rng.unit and rng.source, (a.id, name)


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_retention_sentences_say_consider_if_and_the_next_step(params: dict) -> None:
    for a in _retention(params):
        low = a.sentence.lower()
        assert low.startswith("rozważ"), a.sentence
        assert "jeśli" in low and "następny krok" in low, a.sentence
        assert "{" not in a.sentence, a.sentence


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_new_weir_speaks_of_distance_not_of_a_flow_line(params: dict) -> None:
    for a in _retention(params):
        if a.id == "zastawka-nowa":
            assert "odległości" in a.sentence and "linii spływu" not in a.sentence, a.sentence


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_drain_regulation_is_a_conditional_potential_with_low_confidence(params: dict) -> None:
    # nobody is asked about drainage: it is "nieznane", so the action is a potential to verify
    for a in _retention(params):
        if a.id == "dreny-regulowany-odplyw":
            assert a.candidate.confidence == "niska", a.candidate.confidence
            assert "jeśli" in a.sentence.lower() and "drena" in a.sentence.lower(), a.sentence
            assert "brak danych o drenażu" in " ".join(a.candidate.risks), a.candidate.risks


@pytest.mark.xfail(reason="not built yet", strict=False)
@pytest.mark.parametrize("params", [DOBRCZ, GSM_TODAY])
def test_a_catchment_cut_by_the_grid_is_a_stated_risk(params: dict) -> None:
    for a in _retention(params):
        if a.candidate and a.candidate.evidence.get("zlewnia_ucieta"):
            assert any("ucięt" in risk for risk in a.candidate.risks), (a.id, a.candidate.risks)
