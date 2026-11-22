"""Retention actions of a parcel: the terrain fields the map reads, then the chain from cause to action.

`set_terrain_fields` fills the slope, the direction of the fall, the lower boundary segment and the outlet on the
report context. Flow lines and the catchment of the outlet are set only when the D8 variant won the check
(`outlet_method() == "d8"`): the other variants have no such number.
"""

from __future__ import annotations

from app.advice import placement as pl
from app.advice.chain import build_chain, plane_of
from app.advice.diagnosis import _cached
from app.advice.placement import PlacementInput, find_places
from app.advice.terrain_model import TerrainModel, build_terrain_model
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


def terrain_model_of(ctx: ReportContext, inp: PlacementInput) -> TerrainModel:
    """The terrain model of the parcel, computed once per report."""

    def compute() -> TerrainModel:
        terrain = ctx.data.terrain.data if ctx.data.terrain.usable else None
        has_margin = bool(terrain and terrain.catchment_grid is not None)
        reason = ""
        if not has_margin:
            note = (terrain.catchment_note if terrain else "") or "nie pobrano siatki zlewni"
            note = note.removeprefix("Siatki zlewni nie pobrano: ")
            reason = "siatki zlewni nie pobrano" + (f" ({note})" if note != "nie pobrano siatki zlewni" else "")
        return build_terrain_model(inp, margin_grid=has_margin, missing_reason=reason)

    return _cached(ctx, "terrain_model", compute)


def set_terrain_fields(ctx: ReportContext, inp: PlacementInput) -> None:
    """slope_pct, downhill_deg, lower_edge_2180, outlet_2180 where the terrain model has them; flow_2180 and
    outlet_catchment_ha only for the D8 variant; runoff_reason when the slope is too small for a direction."""
    plane = plane_of(inp)
    if plane is None:
        ctx.runoff_reason = "brak siatki wysokości dla działki"
        return
    ctx.slope_pct = round(plane.slope_pct, 2)
    ctx.downhill_deg = round(plane.downhill_deg, 1)  # the map draws the fall of a flat parcel too
    if pl._too_flat(plane):
        ctx.runoff_reason = f"spadek {pl._slope_text(plane.slope_pct)}% jest za mały, by wskazać dolny odcinek granicy"
    else:
        edge = pl.lower_edge(inp)
        ctx.lower_edge_2180 = [list(p) for p in edge.points_2180] if edge else []
    outlet = next((c for c in find_places(inp) if c.kind == "punkt wypływu"), None)
    # the map falls back to the lowest boundary point itself; an outlet is set only when another variant won
    if pl.outlet_method() != "lowest" and outlet is not None and outlet.place is not None:
        ctx.outlet_2180 = (outlet.place.x_2180, outlet.place.y_2180)
    if pl.outlet_method() == "d8":
        run = pl.runoff(inp)
        ctx.flow_2180 = [[(x, y) for x, y in line] for line in run.flow_lines]
        if outlet is not None:
            ctx.outlet_catchment_ha = outlet.catchment_ha
        if run.reason and not ctx.runoff_reason:
            ctx.runoff_reason = run.reason


def retention_actions(ctx: ReportContext) -> list[Action]:
    """Where to hold water on this parcel: up to three actions, each with a candidate, risks and a formality."""
    inp = placement_input(ctx)
    if inp is None:
        return []
    set_terrain_fields(ctx, inp)
    if ctx.diagnosis is None or not ctx.diagnosis.causes:
        return []
    model = terrain_model_of(ctx, inp)
    in_season = bool(ctx.verdict and ctx.verdict.state != "out_of_season")
    return build_chain(ctx.diagnosis.causes, ctx.request.day, in_season, model, inp, ctx.parcel.area_ha)
