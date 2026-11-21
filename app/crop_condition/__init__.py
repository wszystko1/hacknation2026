"""Plants on the parcel from Sentinel-2: NDMI of the last clear scene vs the median of the same dekad."""

from __future__ import annotations

from datetime import date

from app.context import ReportContext
from app.geodata import SceneIndex
from app.models import CropCondition, CropGroup


def compare(
    current: SceneIndex | None, history: list[SceneIndex], crop: CropGroup, day: date
) -> CropCondition:
    """NDMI of `current` vs the median NDMI of `history` (same dekads, earlier seasons), read with the crop phase.

    The comparison is not built yet: the result states what is missing and why.
    """
    return CropCondition(
        state="missing",
        words="Brak: kondycja roślin ze zdjęć satelitarnych, bo porównania z poprzednimi sezonami jeszcze nie liczymy",
        reason="porównanie z poprzednimi sezonami jeszcze nie działa",
    )


def assess_crop_condition(ctx: ReportContext) -> CropCondition:
    sat = ctx.data.satellite.data if ctx.data.satellite.usable else None
    return compare(
        sat.current if sat else None, sat.history if sat else [], ctx.request.crop, ctx.request.day
    )
