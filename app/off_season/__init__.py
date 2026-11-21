"""From 1 October to 20 March the verdict and the plants do not apply; the report gives the season and the rain."""

from __future__ import annotations

from app.context import ReportContext
from app.models import CropCondition, OffSeason

NOT_APPLICABLE_WORDS = "Stan roślin: nie dotyczy poza sezonem (1.X–20.III)"


def off_season_summary(ctx: ReportContext) -> OffSeason | None:
    """The last season, the rain since 1 October against the norm; None while the summary is not built."""
    return None


def not_applicable() -> CropCondition:
    """The plants row outside the season: nothing is read from the satellite."""
    return CropCondition(state="not_applicable", words=NOT_APPLICABLE_WORDS)
