"""Section 6 "Plan działań i termin": timeline to the next drought window, "W planie" switches, forecast."""

from __future__ import annotations

import logging
from datetime import date

from app.charts import timeline
from app.context import ReportContext
from app.drought.kbw import period_dates
from app.fmt import day
from app.models import CROP_LABELS, Section, TextPart
from app.sections import empty_sentence, placeholder
from app.smsr.pages import PageUnavailable, load_page
from app.smsr.parser import SmsrPageError, parse_commune_page

log = logging.getLogger(__name__)
HEADING = "Plan działań i termin"


def _archive(ctx: ReportContext, year: int, today: date) -> tuple[list[timeline.Entry], str]:
    """Periods of `year` that ended after the assessment date, with the SMSR symbol of the commune.

    Returns the timeline entries and one sentence for the section; an empty sentence when the date is not in
    the past (no period ended between the assessment date and today).
    """
    first = ctx.request.day
    crop, soil = ctx.request.crop, ctx.soil.category if ctx.soil else None
    ended = [
        n
        for n in range(1, 15)
        if first < period_dates(year, n)[1] <= today and period_dates(year, n)[0] <= today
    ]
    if not ended or first.year != year:
        return [], ""
    where = f"{first.strftime('%d.%m.%Y')}"
    if soil is None or crop.value == "inna":
        why = "nie znamy kategorii gleby" if soil is None else "SMSR ocenia tylko 14 grup upraw"
        return [], empty_sentence(f"oceny okresów, które skończyły się po {where}, bo {why}")
    try:
        table = parse_commune_page(load_page(year, ctx.parcel.teryt_commune).html)
    except (PageUnavailable, SmsrPageError) as exc:
        why = getattr(exc, "reason", "strona IUNG ma inny układ, niż umiemy czytać")
        return [], empty_sentence(f"oceny okresów, które skończyły się po {where}, bo {why}")
    label = CROP_LABELS[crop]
    entries, drought = [], 0
    for n in ended:
        symbol = table.symbol(label, soil, n)
        if symbol not in {"+", "-"}:
            continue
        end = period_dates(year, n)[1]
        verdict = "susza" if symbol == "+" else "brak suszy"
        drought += symbol == "+"
        entries.append(
            timeline.Entry("past", end, day(end), f"okres {n}: SMSR dla gminy {table.commune}: {verdict}")
        )
    if not entries:
        return [], empty_sentence(
            f"oceny SMSR okresów po {where}, bo tabela gminy nie ocenia tej uprawy na tej glebie"
        )
    sentence = f"Okresy kończące się po {where}: SMSR ocenił w gminie {table.commune} suszę w {drought} z {len(entries)}."
    return entries, sentence


def build(ctx: ReportContext) -> Section:
    if not ctx.actions:
        return placeholder(
            "plan",
            HEADING,
            "Brak: planu działań, bo bez oceny bilansu nie ma przyczyn, na które odpowiadają działania.",
        )
    end = timeline.window_end(ctx.request.day, ctx.request.crop, ctx.soil.category if ctx.soil else None)
    year = timeline.next_window_year(ctx.request.day)
    past, past_sentence = _archive(ctx, year, date.today())
    entries = timeline.build_entries(ctx.actions, end, past)
    planned = sum(1 for a in ctx.actions if a.in_plan)
    if end is None:
        window = "Brak: końca okna suszy, bo rozporządzenie nie podaje progów dla tej uprawy."
    else:
        window = (
            f"Oś czasu kończy się {day(end[0])}, czyli w ostatnim okresie z progiem suszy dla tej uprawy."
        )
    section = Section(
        id="plan",
        n=6,
        title="Plan i termin",
        heading=HEADING,
        state="ready",
        chart_svg=timeline.render(entries),
        sentences=[s for s in (window, past_sentence) if s],
        summary=[
            TextPart(text=f"{planned} z {len(ctx.actions)}", bold=True),
            TextPart(text=" działań w planie"),
            TextPart(text="" if end is None else f"; oś czasu do {day(end[0])}."),
        ],
    )
    return section
