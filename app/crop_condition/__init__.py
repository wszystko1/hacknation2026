"""Plants on the parcel from Sentinel-2, read against earlier seasons of the same rotation group.

The satellite stands beside the verdict and never changes it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.context import ReportContext
from app.geodata import SceneIndex
from app.models import CropCondition

from . import background
from .compare import compare
from .reading import read_together
from .rotation import classify_season

__all__ = ["assess_crop_condition", "classify_season", "compare", "read_together"]


def _by_year(readings: list[SceneIndex], before: int) -> dict[int, list[SceneIndex]]:
    years: dict[int, list[SceneIndex]] = defaultdict(list)
    for r in readings:
        year = date.fromisoformat(r.date).year
        if year < before:
            years[year].append(r)
    return dict(years)


def _gap(reason: str, ctx: ReportContext) -> CropCondition:
    return compare([], {}, ctx.request.crop, ctx.request.day).model_copy(
        update={"reason": reason, "words": f"Brak: stanu roślin ze zdjęć satelitarnych, bo {reason}"}
    )


def assess_crop_condition(ctx: ReportContext) -> CropCondition:
    """Seasons from the satellite data, the frozen copy or the cache; otherwise they are computed in the
    background and the report says "ocena roślin w toku". Without any of them: the readings grouped by year."""
    day, year = ctx.request.day, ctx.request.day.year
    result = ctx.data.satellite
    sat = result.data if result.usable else None
    seasons = sat.seasons if sat is not None else {}
    if not seasons and ctx.data.parcel.usable:
        status, seasons, reason = background.seasons_for(ctx.data.parcel.data, day)
        if status == "waiting":
            return CropCondition(state="waiting", words="ocena roślin w toku")
        if status == "missing" and sat is None:
            return _gap(reason, ctx)
    if sat is None and not seasons:
        return compare([], {}, ctx.request.crop, day)
    current = seasons.get(year) or ([sat.current] if sat is not None and sat.current else [])
    history = {y: r for y, r in seasons.items() if y < year} or (_by_year(sat.history, year) if sat else {})
    return compare(current, history, ctx.request.crop, day)
