"""Mechanisms: why an action helps, between the cause and the action.

A mechanism ("spowolnić spływ", "zatrzymać wodę w obniżeniu") is addressed by causes and finds its place with one
detector. It enters the report by one rule: in the season it needs the need (at least one of `need_required` in the
diagnosis) AND the opportunity (the terrain offers what `terrain_input` asks for); off season the opportunity is
enough. Mechanisms with detector `no_place` have no spot on the map and say why in `no_place_reason`.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.advice.catalog import load_catalog
from app.models import CauseCode

DETECTORS = ("strip", "balk", "contour", "basin", "no_place")
TERRAIN_INPUTS = ("spadek", "zlewnia", "zagłębienie", "rów", "gleba", "brak")


@dataclass(frozen=True)
class Mechanism:
    id: str
    title: str
    causes_addressed: tuple[CauseCode, ...]
    terrain_input: str
    need_required: tuple[CauseCode, ...]
    opportunity_required: str  # the terrain condition in words
    detector: str
    no_place_reason: str
    threshold_source: str


def _split(text: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in text.split(";") if p.strip())


@lru_cache(maxsize=1)
def _load(path: Path) -> dict[str, Mechanism]:
    out: dict[str, Mechanism] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            m = Mechanism(
                id=raw["id"].strip(),
                title=raw["title"].strip(),
                causes_addressed=_split(raw["causes_addressed"]),  # type: ignore[arg-type]
                terrain_input=raw["terrain_input"].strip(),
                need_required=_split(raw["need_required"]),  # type: ignore[arg-type]
                opportunity_required=raw["opportunity_required"].strip(),
                detector=raw["detector"].strip(),
                no_place_reason=raw["no_place_reason"].strip(),
                threshold_source=raw["threshold_source"].strip(),
            )
            if m.detector not in DETECTORS:
                raise ValueError(f"mechanism {m.id}: unknown detector {m.detector!r}")
            if m.detector == "no_place" and not m.no_place_reason:
                raise ValueError(f"mechanism {m.id}: no_place needs a reason")
            out[m.id] = m
    return out


def load_mechanisms() -> dict[str, Mechanism]:
    """Every mechanism by id, in file order."""
    return dict(_load(Path(__file__).parent / "mechanisms.csv"))


def mechanism_for(action_id: str) -> Mechanism:
    """The mechanism of a catalogue action."""
    return load_mechanisms()[load_catalog()[action_id].mechanism]


def is_needed(mechanism: Mechanism, cause_codes: set[str] | frozenset[str] | tuple[str, ...], in_season: bool) -> bool:
    """In the season the need is required: one of `need_required` among the diagnosed causes. Off season it is not."""
    if not in_season:
        return True
    return any(code in cause_codes for code in mechanism.need_required)


def has_opportunity(mechanism: Mechanism, terrain_inputs: Mapping[str, bool]) -> bool:
    """The terrain offers the input of the mechanism; `brak` needs nothing from the terrain."""
    if mechanism.terrain_input == "brak":
        return True
    return bool(terrain_inputs.get(mechanism.terrain_input, False))
