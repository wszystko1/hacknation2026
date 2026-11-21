"""The state's drought assessment (SMSR IUNG) for the parcel's commune: live row and archive parser."""

from __future__ import annotations

from app.context import ReportContext
from app.models import SmsrRow


def smsr_row(ctx: ReportContext) -> SmsrRow:
    """Skeleton: the row is a placeholder; the parser of susza.iung.pulawy.pl/wykazy comes next."""
    year = ctx.request.day.year
    if year < 2020:
        return SmsrRow(
            state="before_2020",
            commune=ctx.parcel.commune,
            year=year,
            reason="SMSR publikuje tabele gmin od 2020 r.",
        )
    return SmsrRow(
        state="missing",
        commune=ctx.parcel.commune,
        year=year,
        reason=f"Tu pojawi się ocena SMSR IUNG dla gminy {ctx.parcel.commune} w tym okresie",
    )
