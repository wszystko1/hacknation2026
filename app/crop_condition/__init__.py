"""Plants on the parcel from Sentinel-2, read against earlier seasons of the same rotation group.

The satellite stands beside the verdict and never changes it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.context import ReportContext
from app.geodata import SceneIndex
from app.models import CropCondition

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


def assess_crop_condition(ctx: ReportContext) -> CropCondition:
    """History from the whole seasons of the satellite data; without them, the readings grouped by year."""
    day, year = ctx.request.day, ctx.request.day.year
    result = ctx.data.satellite
    if not result.usable or result.data is None:
        return compare([], {}, ctx.request.crop, day)
    sat = result.data
    current = sat.seasons.get(year) or ([sat.current] if sat.current else [])
    history = {y: r for y, r in sat.seasons.items() if y < year} or _by_year(sat.history, year)
    return compare(current, history, ctx.request.crop, day)
