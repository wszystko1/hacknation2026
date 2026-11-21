"""The state's drought assessment (SMSR IUNG) for the parcel's commune: the row next to our verdict."""

from __future__ import annotations

from app.context import ReportContext
from app.fmt import dec
from app.models import CROP_LABELS, CropGroup, SmsrRow, SourceRow
from app.smsr.pages import Page, PageUnavailable, load_page, page_url
from app.smsr.parser import SmsrPageError, parse_commune_page

FIRST_YEAR = 2020
LABEL, PROVIDER = "Ocena suszy w gminie (SMSR)", "IUNG-PIB, SMSR"

WORDS = {
    "+": "susza",
    "-": "brak suszy",
    "x": "SMSR nie ocenia tej uprawy w tym okresie",
    "#": "uprawa niewskazana na tej kategorii gleby",
    "*": "w gminie nie ma gleb tej kategorii",
    "n": "SMSR nie podaje oceny dla tej komórki",
}


def symbol_words(symbol: str, share_pct: float | None) -> str:
    """What the symbol says, with the share of the commune's area at risk where it adds something."""
    words = WORDS.get(symbol, "SMSR nie podaje oceny dla tej komórki")
    if share_pct is None:
        return words
    if symbol == "+":
        return f"{words}, zagrożone {dec(share_pct)}% powierzchni gminy"
    if symbol == "-" and share_pct > 0:
        return f"{words}, choć na części gleb gminy zagrożone jest {dec(share_pct)}% powierzchni"
    return words


def _missing(commune: str, year: int | None, reason: str, **fields: object) -> SmsrRow:
    where = f"dla gminy {commune}" if commune else ""
    return SmsrRow(
        state="missing",
        commune=commune,
        year=year,
        reason=f"Brak: ocena SMSR {where}, bo {reason}".replace("  ", " "),
        **fields,  # type: ignore[arg-type]
    )


def _source(row: SmsrRow, page: Page | None, year: int, teryt: str) -> SourceRow:
    if row.state != "ok" or page is None:
        status = "missing"
    else:
        status = "copy" if page.origin == "demo" else "ok"
    gave = f"gmina {row.commune}, okres {row.period_n} z {year} r." if row.state == "ok" else ""
    return SourceRow(
        key="smsr",
        label=LABEL,
        provider=PROVIDER,
        gave=gave,
        status=status,
        elapsed_s=round(page.elapsed_s, 1) if page else None,
        retrieved_at=page.retrieved_at if page else "",
        resolution="gmina",
        reason=row.reason if status == "missing" else "",
        url=page_url(year, teryt) if year >= FIRST_YEAR else "",
    )


def smsr_row(ctx: ReportContext) -> SmsrRow:
    """SMSR's symbol for the commune, the year, the period of our verdict, the crop and the soil category.

    The row also goes to `ctx.extra_sources`, with the time of the download.
    """
    commune, teryt = ctx.parcel.commune, ctx.parcel.teryt_commune
    year = ctx.request.day.year
    if year < FIRST_YEAR:
        row, page = _before_2020(commune, year), None
    else:
        if ctx.verdict is not None and ctx.verdict.season_year:
            year = ctx.verdict.season_year  # out of season: the last season is shown
        row, page = _compute(ctx, commune, teryt, year)
    ctx.extra_sources = [s for s in ctx.extra_sources if s.key != "smsr"]
    ctx.extra_sources.append(_source(row, page, year, teryt))
    return row


def _before_2020(commune: str, year: int) -> SmsrRow:
    return SmsrRow(
        state="before_2020",
        commune=commune,
        year=year,
        reason="Brak: ocena SMSR, bo SMSR publikuje tabele gmin dopiero od 2020 r.",
    )


def _compute(ctx: ReportContext, commune: str, teryt: str, year: int) -> tuple[SmsrRow, Page | None]:
    crop, verdict, soil = ctx.request.crop, ctx.verdict, ctx.soil
    if crop == CropGroup.INNA:
        return _missing(commune, year, "SMSR ocenia tylko 14 grup upraw, a wybrano „Inna uprawa”"), None
    if verdict is None or verdict.period is None:
        return _missing(commune, year, "nie ma okresu bilansu, do którego można ją odnieść"), None
    period = verdict.period.n
    if soil is None or soil.category is None:
        reason = "nie znamy kategorii gleby działki, a SMSR podaje wynik osobno dla każdej"
        return _missing(commune, year, reason, period_n=period), None
    try:
        page = load_page(year, teryt)
        table = parse_commune_page(page.html)
    except PageUnavailable as exc:
        return _missing(commune, year, exc.reason, period_n=period), None
    except SmsrPageError:
        return _missing(commune, year, "strona IUNG ma inny układ, niż umiemy czytać", period_n=period), None
    label = CROP_LABELS[crop]
    symbol = table.symbol(label, soil.category, period)
    if symbol is None:
        return _missing(commune, year, f"tabela SMSR nie ma wiersza „{label}”", period_n=period), page
    share = table.area_share_pct(label, period)
    row = SmsrRow(
        state="ok",
        commune=table.commune,
        year=year,
        period_n=period,
        crop_label=label,
        soil_category=soil.category,
        symbol=symbol,
        words=symbol_words(symbol, share),
        area_share_pct=share,
        url=page_url(year, teryt),
    )
    return row, page
