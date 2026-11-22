"""Forest, built-up land and roads get no irrigation advice; farmland and unknown use are unchanged."""

from __future__ import annotations

import pytest

from app.drought.variants import main_verdict
from app.geodata import parcel_use
from app.geodata.parcel_use import LandUse, classify, land_use_from_properties
from app.models import ReportRequest
from app.report import build_context
from app.sections import nawadnianie
from app.soil import assess_soil


@pytest.mark.parametrize(
    ("code", "kind"),
    [("Ls", "forest"), ("Lzr", "forest"), ("Bi", "built"), ("B", "built"), ("dr", "road"),
     ("R", "farm"), ("Ps", "farm"), ("Ł", "farm"), ("Ws", "water"), ("xyz", "other")],
)  # fmt: skip
def test_classify(code: str, kind: str) -> None:
    assert classify(code).kind == kind


def test_properties_without_a_land_use_field_give_none() -> None:
    assert land_use_from_properties({"ID_DZIALKI": "x"}) is None
    assert land_use_from_properties({"OZU": "Ls"}) == LandUse("Ls", "forest")


def _ctx():
    from datetime import date

    ctx = build_context(
        ReportRequest.model_validate(
            {"parcel_id": "040303_2.0002.189/13", "day": date(2023, 7, 20), "crop": "zboza_jare"}
        )
    )
    ctx.soil = assess_soil(ctx)
    ctx.verdict, _ = main_verdict(ctx)
    ctx.data_copy = None  # as for a parcel without a committed copy
    return ctx


@pytest.mark.parametrize("code", ["Ls", "Bi", "dr"])
def test_not_farmland_gets_a_message_without_recommendation(monkeypatch, code: str) -> None:
    monkeypatch.setattr(parcel_use, "fetch_land_use", lambda pid, **kw: classify(code))
    section = nawadnianie.build(_ctx())
    text = section.reason
    assert "nie jest użytkiem rolnym" in text and "nie ma zastosowania" in text
    assert not section.actions and not section.sentences and not section.chart_svg


def test_farmland_keeps_the_assessment(monkeypatch) -> None:
    monkeypatch.setattr(parcel_use, "fetch_land_use", lambda pid, **kw: classify("R"))
    section = nawadnianie.build(_ctx())
    assert section.state == "ready"
