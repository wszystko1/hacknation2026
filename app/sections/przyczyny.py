"""Section 3 "Skąd ten bilans": the balance of the period split into less rain and more evaporation, and the causes."""

from __future__ import annotations

from app.advice.diagnosis import (
    RULES,
    attribution,
    balance_split,
    mean_slope_pct,
    nearest_ditch_m,
    usual_period,
)
from app.charts.causes import waterfall_svg
from app.context import ReportContext
from app.fmt import day_month, dec
from app.models import KeyValue, Section, TextPart
from app.sections import placeholder

TITLE = "Skąd ten bilans"


def _upper_first(text: str) -> str:
    return text[:1].upper() + text[1:]


AXIS_NAMES = {"pogoda": "pogoda", "miejsce": "miejsce", "uprawa": "uprawa"}


def _num(v: object) -> str:
    return dec(float(v)) if isinstance(v, int | float) and not isinstance(v, bool) else str(v)


def _causes_advisor(ctx: ReportContext) -> list[KeyValue]:
    found = {c.code for c in (ctx.diagnosis.causes if ctx.diagnosis else [])}
    rows = [
        KeyValue(
            key=f"Reguła: {r.label.lower()}" + (" (spełniona)" if r.code in found else ""),
            value=f"{r.condition} · pewność: {r.confidence}" + (f" · {r.source}" if r.source else ""),
        )
        for r in RULES
    ]
    causes = ctx.diagnosis.causes if ctx.diagnosis else []
    for c in causes:
        evidence = ", ".join(f"{k.replace('_', ' ')}: {_num(v)}" for k, v in c.evidence.items())
        mm = f", udział w niedoborze {dec(c.strength_mm)} mm" if c.strength_mm is not None else ""
        rows.append(
            KeyValue(
                key=f"Przyczyna: {c.code} · oś: {AXIS_NAMES[c.axis or 'pogoda']}", value=f"{evidence}{mm}"
            )
        )
    usual, attr = usual_period(ctx), attribution(ctx)
    if attr:
        rows.append(
            KeyValue(
                key="Zwykły sezon (a): rok o medianie bilansu",
                value=f"opad {dec(attr.season_rain_mm)} mm, parowanie {dec(attr.season_et0_mm)} mm · {attr.label_season}",
            )
        )
        rows.append(
            KeyValue(
                key="Zwykły sezon (b): mediany osobno",
                value=f"opad {dec(attr.medians_rain_mm)} mm, parowanie {dec(attr.medians_et0_mm)} mm · {attr.label_medians}",
            )
        )
        rows.append(
            KeyValue(
                key="Główny czynnik",
                value=f"{attr.label} (nazwany tylko gdy obie definicje wskazują to samo)",
            )
        )
    if usual:
        rows.append(
            KeyValue(
                key="Zwykły sezon",
                value=f"mediana bilansu {dec(usual.kbw_mm)} mm z lat {usual.years[0]}–{usual.years[-1]} ({usual.n_seasons} sezonów)",
            )
        )
    return rows


def build(ctx: ReportContext) -> Section:
    v, split, usual = ctx.verdict, balance_split(ctx), usual_period(ctx)
    causes = ctx.diagnosis.causes if ctx.diagnosis else []
    if v is None or v.period is None or v.state == "no_data":
        return placeholder(
            "przyczyny", TITLE, "Brak: przyczyn niedoboru, bo nie ma oceny bilansu dla tej działki."
        )
    if split is None or usual is None:
        section = placeholder(
            "przyczyny",
            TITLE,
            "Brak: rozkładu bilansu na opad i parowanie, bo dane o pogodzie obejmują mniej niż "
            "czterech sezonów, a zwykły sezon liczony jest z co najmniej trzech wcześniejszych.",
        )
        section.advisor = _causes_advisor(ctx)
        return section

    p = v.period
    section = placeholder("przyczyny", TITLE, "")
    section.state, section.reason = "ready", ""
    gap = split.result_mm - split.usual_mm
    label = (
        f"Bilans {dec(split.result_mm)} mm: zwykle {dec(split.usual_mm)} mm, "
        f"{dec(split.rain_step_mm)} mm z opadu, {dec(split.evaporation_step_mm)} mm z parowania"
    )
    section.chart_svg = waterfall_svg(split, p.threshold_mm, label)
    section.summary = [
        TextPart(text="bilans "),
        TextPart(text=f"{dec(split.result_mm)} mm", bold=True),
        TextPart(text=f", zwykle {dec(split.usual_mm)} mm"),
        TextPart(
            text=f"; rozpoznane przyczyny: {len(causes)}"
            if causes
            else "; żadna reguła przyczyn nie jest spełniona"
        ),
    ]
    slope, ditch, soil = mean_slope_pct(ctx), nearest_ditch_m(ctx), ctx.soil
    sentences = [
        f"W okresie {p.n} ({day_month(p.start)}–{day_month(p.end)}) bilans wynosi {dec(split.result_mm)} mm, "
        f"zwykle {dec(split.usual_mm)} mm; różnica to {dec(gap)} mm.",
        f"Opad {dec(p.precip_mm)} mm (zwykle {dec(usual.precip_mm)} mm) daje {dec(split.rain_step_mm)} mm tej różnicy, "
        f"parowanie {dec(p.et0_mm)} mm (zwykle {dec(usual.et0_mm)} mm) daje {dec(split.evaporation_step_mm)} mm.",
    ]
    terrain = f"spadek terenu {dec(slope, 1)}% (NMT)" if slope is not None else "spadku terenu nie znamy"
    if ditch is not None:
        terrain += f", najbliższy rów {dec(ditch, 1 if ditch < 10 else 0)} m od działki"
    sentences.append(f"{_upper_first(soil.words if soil else 'gleba nieznana')}; {terrain}.")
    section.sentences = sentences
    section.how = (
        f"Zwykły sezon to wiersz z mediany bilansu okresu {p.n} w {usual.n_seasons} wcześniejszych sezonach "
        f"({usual.years[0]}–{usual.years[-1]}); jego opad i parowanie dają ten bilans co do 0,1 mm. "
        "Składowe: opad − zwykły opad, minus (parowanie − zwykłe parowanie); razem z bilansem zwykłym dają bilans okresu."
    )
    section.advisor = _causes_advisor(ctx)
    return section
