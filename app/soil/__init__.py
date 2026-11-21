"""Soil category I-IV of the drought regulation for the parcel: IUNG map layer first, SoilGrids texture second."""

from __future__ import annotations

from app.context import ReportContext
from app.models import SoilInfo

WORDS = {
    "I": "gleba bardzo podatna na suszę (kat. I)",
    "II": "gleba podatna na suszę (kat. II)",
    "III": "gleba średnio podatna na suszę (kat. III)",
    "IV": "gleba mało podatna na suszę (kat. IV)",
}


def assess_soil(ctx: ReportContext) -> SoilInfo:
    """Skeleton: only the advisor's override; the IUNG layer and the SoilGrids rule come next."""
    override = ctx.request.soil_override
    if override:
        return SoilInfo(
            category=override,
            source="doradca",
            words=WORDS[override],
            note="kategoria ustawiona przez doradcę",
        )
    soil = ctx.data.soil.data if ctx.data.soil.usable else None
    return SoilInfo(
        category=None,
        source="brak",
        words="Tu pojawi się kategoria gleby z mapy IUNG albo z uziarnienia SoilGrids",
        sand_pct=soil.sand_pct if soil else None,
        silt_pct=soil.silt_pct if soil else None,
        clay_pct=soil.clay_pct if soil else None,
    )
