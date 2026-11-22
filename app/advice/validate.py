"""Validation of a candidate against the terrain model: what could make the place wrong, written as risks.

Five checks; each one that fires appends a risk (Polish, read by the farmer and the adviser) and the candidate's
confidence drops one step in total (wysoka -> średnia -> niska), however many risks fire:

* the catchment is cut by the edge of the grid, so its size is a lower bound;
* the external catchment exceeds `EXTERNAL_CATCHMENT_RATIO` times the parcel (only for a runoff cause: other
  causes do not depend on water from upstream);
* the place is closer than `MIN_BOUNDARY_DISTANCE_M` to the boundary;
* nothing is known about drainage (we do not ask the farmer, so it stays "unknown"): only for the drain regulator;
* the slope is below the resolution of the heights (0.1 m).

The thresholds (2 times the parcel, 20 m) are the team's proposal: no source gives them. They are shown in the
adviser view. A candidate that triggers none comes back unchanged. The function does not modify its argument.

Inputs are read from the candidate's `evidence` (`zlewnia_ucieta`, `zlewnia_ha`, `dzialka_ha`,
`odleglosc_od_granicy_m`, `spadek_ponizej_rozdzielczosci`) and, where the evidence lacks a value, from the
terrain model.
"""

from __future__ import annotations

from app.advice.terrain_model import FLAT_FLAG, TerrainModel
from app.models import Candidate, Confidence

# Team proposals, see the module docstring.
EXTERNAL_CATCHMENT_RATIO = 2.0
MIN_BOUNDARY_DISTANCE_M = 20.0

DRAIN_ACTION = "dreny-regulowany-odplyw"
RUNOFF_CAUSE = "splyw"

RISK_CUT = "zlewnia ucięta przez siatkę: jej wielkość jest dolnym oszacowaniem"
RISK_DRAINS = "brak danych o drenażu: nie wiemy, czy grunt jest zdrenowany"
RISK_FLAT = "spadek poniżej rozdzielczości modelu: kierunek spływu jest niepewny"

_STEPS: list[Confidence] = ["niska", "średnia", "wysoka"]


def _risk_external(ratio: float) -> str:
    return (
        f"zlewnia zewnętrzna jest {ratio:.1f} razy większa niż działka "
        f"(próg {EXTERNAL_CATCHMENT_RATIO:g}; wartość orientacyjna): duży dopływ z cudzych gruntów"
    )


def _risk_boundary(distance: float) -> str:
    return (
        f"miejsce {distance:.0f} m od granicy (próg {MIN_BOUNDARY_DISTANCE_M:g} m; wartość orientacyjna): "
        "skutek może wyjść na sąsiednią działkę"
    )


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _lower(confidence: Confidence) -> Confidence:
    return _STEPS[max(0, _STEPS.index(confidence) - 1)]


def _risks(candidate: Candidate, terrain: TerrainModel | None) -> list[str]:
    ev = candidate.evidence
    found: list[str] = []

    cut = ev.get("zlewnia_ucieta")
    if cut is None and terrain is not None:
        cut = terrain.catchment_truncated
    if cut:
        found.append(RISK_CUT)

    catchment = _number(ev.get("zlewnia_ha"))
    if catchment is None and terrain is not None:
        catchment = terrain.catchment_ha
    parcel = _number(ev.get("dzialka_ha"))
    if RUNOFF_CAUSE in candidate.cause_codes and catchment is not None and parcel:
        ratio = (catchment - parcel) / parcel
        if ratio > EXTERNAL_CATCHMENT_RATIO:
            found.append(_risk_external(ratio))

    distance = _number(ev.get("odleglosc_od_granicy_m"))
    if distance is not None and distance < MIN_BOUNDARY_DISTANCE_M:
        found.append(_risk_boundary(distance))

    if candidate.action_id == DRAIN_ACTION:
        found.append(RISK_DRAINS)

    flat = ev.get("spadek_ponizej_rozdzielczosci")
    if flat is None and terrain is not None:
        flat = FLAT_FLAG in terrain.flags
    if flat:
        found.append(RISK_FLAT)
    return found


def validate(candidate: Candidate, terrain_model: TerrainModel | None) -> Candidate:
    """The candidate with the risks that apply appended and its confidence lowered by one step; a copy."""
    new = [r for r in _risks(candidate, terrain_model) if r not in candidate.risks]
    out = candidate.model_copy(deep=True)
    if new:
        out.risks.extend(new)
        out.confidence = _lower(out.confidence)
    return out
