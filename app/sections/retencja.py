"""Section 4 "Gdzie zatrzymać wodę na działce": places on the photo, terrain profile, actions with formalities."""

from __future__ import annotations

from app.advice.retention import placement_input
from app.advice.terrain_model import TerrainModel, build_terrain_model
from app.context import ReportContext
from app.models import KeyValue, Section, TextPart
from app.sections import placeholder


def terrain_model(ctx: ReportContext) -> TerrainModel | None:
    """The terrain model of the parcel; None without a parcel outline."""
    inp = placement_input(ctx)
    if inp is None:
        return None
    terrain = ctx.data.terrain.data if ctx.data.terrain.usable else None
    has_margin = bool(terrain and terrain.catchment_grid is not None)
    reason = ""
    if not has_margin:
        reason = (terrain.catchment_note if terrain else "") or "nie pobrano siatki zlewni"
        reason = reason.removeprefix("Siatki zlewni nie pobrano: ")
        reason = "siatki zlewni nie pobrano" + (
            f" ({reason})" if reason != "nie pobrano siatki zlewni" else ""
        )
    return build_terrain_model(inp, margin_grid=has_margin, missing_reason=reason)


def build(ctx: ReportContext) -> Section:
    section = placeholder(
        "retencja",
        "Gdzie zatrzymać wodę na działce",
        "Brak: miejsca działań na zbliżeniu działki i profil terenu, bo tych widoków jeszcze nie rysujemy.",
    )
    section.actions = [a for a in ctx.actions if a.group == "retencja"]
    model = terrain_model(ctx)
    if model is not None:
        section.advisor.append(KeyValue(key="Zlewnia", value=model.line().removeprefix("Zlewnia: ")))
    placed = [a for a in section.actions if a.place]
    if placed:
        section.summary = [
            TextPart(text="Działanie nr 1: "),
            TextPart(text=placed[0].title.lower(), bold=True),
            TextPart(text=f" ({placed[0].place.description})."),
        ]
    return section
