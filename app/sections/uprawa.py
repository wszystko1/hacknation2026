"""Section 5 "Uprawa gleby, która trzyma wodę": decades under the threshold and the soil and crop actions."""

from __future__ import annotations

from app.advice.catalog import load_catalog
from app.advice.rules import (
    NOT_USED,
    PROPOSALS,
    crop_comparison,
    crop_label,
    decade_counts,
)
from app.charts.agro import counts_svg
from app.context import ReportContext
from app.drought.kbw import CROP_GENITIVE
from app.models import KeyValue, Section, TextPart
from app.sections import placeholder

TITLE = "Uprawa gleby, która trzyma wodę"
ROMAN = ("IV", "V", "VI", "VII", "VIII", "IX")


def _decade_name(index: int, locative: bool = False) -> str:
    return f"{index % 3 + 1}. {'dekadzie' if locative else 'dekada'} {ROMAN[index // 3]}"


def _advisor(ctx: ReportContext) -> list[KeyValue]:
    rows = [
        KeyValue(
            key=f"Reguła: {r.title.lower()}",
            value=(
                (f"gleba {', '.join(r.cond_set('soil'))}" if r.cond_set("soil") else "bez warunku na glebę")
                + f" · pewność: {r.confidence}"
            ),
        )
        for r in load_catalog().values()
        if r.group == "uprawa" and r.action_id not in NOT_USED
    ]
    rows += [
        KeyValue(key=f"Próg: {what.lower()}", value=f"{value} · propozycja zespołu")
        for what, value in PROPOSALS[:3]
    ]
    return rows


def build(ctx: ReportContext) -> Section:
    v, diagnosis = ctx.verdict, ctx.diagnosis
    if v is None or v.state == "no_data" or diagnosis is None or not diagnosis.causes:
        section = placeholder(
            "uprawa",
            TITLE,
            "Brak: zabiegów w uprawie, bo nie ma oceny bilansu ani rozpoznanej przyczyny niedoboru dla tej działki.",
        )
        section.advisor = _advisor(ctx)
        return section

    section = placeholder("uprawa", TITLE, "")
    section.state, section.reason = "ready", ""
    section.actions = [a for a in ctx.actions if a.group == "uprawa"]
    counts = decade_counts(ctx)
    judged = [c for c in counts if c.judged]
    genitive = CROP_GENITIVE[ctx.request.crop]
    sentences: list[str] = []
    if judged:
        worst = max(judged, key=lambda c: (c.below, c.decade.index))
        section.chart_svg = counts_svg(
            counts, f"Okna 60 dni pod progiem dla {genitive} w {worst.judged} sezonach, według dekad IV–IX"
        )
        section.summary = [
            TextPart(text="najczęściej pod progiem: "),
            TextPart(text=f"{worst.below} z {worst.judged}", bold=True),
            TextPart(text=f" sezonów ({_decade_name(worst.decade.index)})"),
        ]
        sentences.append(
            f"Okno 60 dni kończące się w {_decade_name(worst.decade.index, True)} było pod progiem dla {genitive} "
            f"w {worst.below} z {worst.judged} sezonów; w pozostałych dekadach rzadziej."
            if worst.below
            else f"Dla {genitive} żadne okno 60 dni z IV–IX nie było pod progiem w {worst.judged} sezonach."
        )
    else:
        sentences.append(
            f"Brak: wykresu dekad pod progiem, bo rozporządzenie nie podaje progu dla {genitive} na tej glebie "
            "albo nie znamy kategorii gleby."
        )
    comparison = crop_comparison(ctx)
    if len(comparison) > 1:
        soil = ctx.soil.category if ctx.soil else "?"
        parts = [f"{crop_label(c)} w {k} z {n}" for c, k, n in comparison]
        sentences.append(
            f"Te same dane pogodowe, inne progi, gleba kategorii {soil}: w ilu sezonach okno było pod progiem: "
            + ", ".join(parts)
            + "."
        )
    if not section.actions:
        sentences.append(
            "Brak: zabiegów w uprawie, bo żaden z działań katalogu nie pasuje do tej gleby i uprawy przy rozpoznanych przyczynach."
        )
    section.sentences = sentences
    section.how = (
        "Dla każdej z 14 dekad, w których kończy się okres z rozporządzenia (Dz.U. 2019 poz. 739), liczymy bilans okna 60 dni "
        f"(opad − parowanie FAO-56) w ostatnich {max((c.judged for c in counts), default=0)} sezonach i porównujemy z progiem dla uprawy i gleby. "
        "Działanie wchodzi, gdy odpowiada na rozpoznaną przyczynę i spełnia warunki wiersza katalogu; wyżej stoi to, które odpowiada na więcej przyczyn."
    )
    section.advisor = _advisor(ctx)
    return section
