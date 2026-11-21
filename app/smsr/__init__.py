"""The state's drought assessment (SMSR IUNG) for the parcel's commune: live row and archive parser."""

from __future__ import annotations

from app.context import ReportContext
from app.models import SmsrRow


def smsr_row(ctx: ReportContext) -> SmsrRow:
    """The row for the commune and year; until the parser of susza.iung.pulawy.pl/wykazy exists it says what is missing."""
    year = ctx.request.day.year
    if year < 2020:
        return SmsrRow(
            state="before_2020",
            commune=ctx.parcel.commune,
            year=year,
            reason="Brak: ocena SMSR, bo SMSR publikuje tabele gmin dopiero od 2020 r.",
        )
    return SmsrRow(
        state="missing",
        commune=ctx.parcel.commune,
        year=year,
        reason=f"Brak: ocena SMSR dla gminy {ctx.parcel.commune}, bo tabel SMSR jeszcze nie wczytujemy",
    )
