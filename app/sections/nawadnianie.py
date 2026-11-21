"""Section 7 "Czy nawadniać": now yes or no with the reason, the dose in mm and m³, water source, deficit by decade."""

from __future__ import annotations

from app.advice.catalog import load_catalog
from app.advice.rules import (
    NOT_USED,
    PERMIT_M3_PER_YEAR,
    PROPOSALS,
    decade_deficits,
    irrigation,
    water_source_sentence,
)
from app.charts.agro import deficit_svg
from app.context import ReportContext
from app.fmt import dec
from app.models import KeyValue, Section, TextPart
from app.sections import placeholder

TITLE = "Czy nawadniać"


def _range(pair: tuple[int, int]) -> str:
    return f"{dec(pair[0])}–{dec(pair[1])}"


def _advisor() -> list[KeyValue]:
    rows = [
        KeyValue(key=f"Reguła: {r.title.lower()}", value=f"pewność: {r.confidence}")
        for r in load_catalog().values()
        if r.group == "nawadnianie" and r.action_id not in NOT_USED
    ]
    rows += [
        KeyValue(key=f"Próg: {what.lower()}", value=f"{value} · propozycja zespołu")
        for what, value in PROPOSALS[3:]
    ]
    rows.append(
        KeyValue(
            key="Bilans wody w strefie korzeni",
            value="nie liczymy; decyzja z bilansu KBW okresu i progu z rozporządzenia",
        )
    )
    return rows


def build(ctx: ReportContext) -> Section:
    v = ctx.verdict
    if v is None or v.state == "no_data":
        section = placeholder(
            "nawadnianie",
            TITLE,
            "Brak: decyzji o nawadnianiu i dawki w mm i m³, bo nie ma oceny bilansu dla tej działki.",
        )
        section.advisor = _advisor()
        return section

    ir = irrigation(ctx)
    section = placeholder("nawadnianie", TITLE, "")
    section.state, section.reason = "ready", ""
    section.actions = [a for a in ctx.actions if a.group == "nawadnianie"]
    deficits = decade_deficits(ctx)
    section.chart_svg = deficit_svg(
        deficits, "Niedobór wody w dekadach IV–IX na tle faz uprawy z progiem w rozporządzeniu"
    )
    head, _, tail = ir.reason.partition(": ")
    section.summary = (
        [TextPart(text=head, bold=True), TextPart(text=f": {tail}")] if tail else [TextPart(text=ir.reason)]
    )
    area = ctx.parcel.area_ha
    sentences = [ir.reason]
    if ir.dose_mm and ir.dose_m3:
        sentences.append(
            f"Dawka według poradnika CDR 2025: {_range(ir.dose_mm)} mm na polew, czyli {_range(ir.dose_m3)} m³ "
            f"na działkę {dec(area, 2)} ha (1 mm na 1 ha to 10 m³)."
        )
        top = ir.dose_m3[1]
        reach = (
            f"już jedna dawka ({dec(top)} m³) jest większa od tego odpowiednika"
            if top > PERMIT_M3_PER_YEAR
            else f"przy dawce {dec(top)} m³ próg przekroczy {PERMIT_M3_PER_YEAR // top + 1}. dawka w roku"
        )
        sentences.append(
            f"Pobór ponad 5 m³ na dobę średniorocznie, czyli {dec(PERMIT_M3_PER_YEAR)} m³ rocznie, wymaga pozwolenia wodnoprawnego; {reach}."
        )
    sentences.append(water_source_sentence(ctx))
    section.sentences = sentences
    section.how = (
        "Decyzję liczymy z bilansu KBW (opad − parowanie FAO-56) okresu z werdyktu i progu z Dz.U. 2019 poz. 739; "
        "bilansu wody w strefie korzeni nie liczymy. Parowanie w werdykcie może mieć drugi wariant (Doroszewski–Górski, widok doradcy); "
        "nawadnianie zostaje przy FAO-56. Kolumny pod wykresem: niedobór to parowanie minus opad w 10 dniach."
    )
    section.advisor = _advisor()
    return section
