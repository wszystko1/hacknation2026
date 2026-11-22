"""Retention actions (where to hold water on the parcel), each with a place or a reason and a formality."""

from __future__ import annotations

from datetime import date

from app.advice.legal import legal_note
from app.advice.placement import PlacementInput, find_places
from app.context import ReportContext
from app.models import Action


def placement_input(ctx: ReportContext) -> PlacementInput | None:
    parcel = ctx.data.parcel.data
    if parcel is None:
        return None
    terrain = ctx.data.terrain.data if ctx.data.terrain.usable else None
    water = ctx.data.water.data if ctx.data.water.usable else None
    return PlacementInput(
        outline_2180=parcel.rings_2180[0],
        grid=(terrain.catchment_grid or terrain.grid) if terrain else None,
        lowest_outline_point_2180=terrain.lowest_outline_point_2180 if terrain else None,
        water=water.features if water else [],
        slope_mean_pct=terrain.slope_mean_pct if terrain else None,
    )


def retention_actions(ctx: ReportContext) -> list[Action]:
    """One action at the outlet point; its sentence and term say what is missing until the action catalogue exists."""
    if ctx.diagnosis is None or not ctx.diagnosis.causes:
        return []
    inp = placement_input(ctx)
    candidates = find_places(inp) if inp else []
    outlet = next((c for c in candidates if c.kind == "punkt wypływu"), None)
    day = ctx.request.day
    in_season = bool(ctx.verdict and ctx.verdict.state != "out_of_season")
    # Earthworks are done in the dormant season: out of season the deadline is the day before 21.III.
    due = None if in_season else date(day.year + 1 if day.month >= 10 else day.year, 3, 20)
    return [
        Action(
            id="niecka-przy-wyplywie",
            n=0,
            group="retencja",
            title="Niecka lub oczko przy punkcie wypływu",
            sentence="Brak: opis działania z liczbami tej działki, bo katalog działań jeszcze nie jest wczytany.",
            cause=ctx.diagnosis.causes[0].words,
            when="Brak: termin, bo terminów działań jeszcze nie wyliczamy",
            source="katalog NWRM N01 · CDR 2025",
            legal=legal_note("niecka-przy-wyplywie"),
            due=due,
            place=outlet.place if outlet else None,
            no_place_reason=""
            if outlet and outlet.place
            else f"brak miejsca na działce, bo {outlet.reason if outlet else 'brak obrysu'}",
        )
    ]
