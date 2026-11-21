"""The report pipeline: data -> soil -> verdict -> SMSR row -> plants -> diagnosis -> actions -> forecast ->
agreement -> sections. Each step is one function in its own module; a failing step leaves its part of the
report empty with a reason instead of breaking the whole report."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import TypeVar

from app import datasource
from app.advice.diagnosis import diagnose
from app.advice.retention import retention_actions
from app.advice.rules import field_actions
from app.context import ReportContext
from app.crop_condition import assess_crop_condition
from app.crop_condition.reading import read_together
from app.drought.kbw import assess, season_of
from app.drought.variants import verdict_dg
from app.forecast.exceedance import forecast_exceedance
from app.geodata import FetchResult
from app.mapview import map_view
from app.models import (
    Action,
    Agreement,
    CropCondition,
    Diagnosis,
    ExceedanceForecast,
    ParcelInfo,
    Report,
    ReportRequest,
    Section,
    SmsrRow,
    SoilInfo,
    SourceRow,
    Verdict,
    Vulnerability,
)
from app.off_season import not_applicable, off_season_summary
from app.sections import gmina as gmina_section
from app.sections import historia, nawadnianie, placeholder, plan, przyczyny, retencja, uprawa, zrodla
from app.smsr import smsr_row
from app.soil import assess_soil
from app.sources_table import source_rows
from app.validation.agreement import agreement_frame
from app.vulnerability import assess_vulnerability

log = logging.getLogger(__name__)
T = TypeVar("T")

SECTION_BUILDERS: list[tuple[str, Callable[[ReportContext], Section]]] = [
    ("historia", historia.build),
    ("gmina", gmina_section.build),
    ("przyczyny", przyczyny.build),
    ("retencja", retencja.build),
    ("uprawa", uprawa.build),
    ("plan", plan.build),
    ("nawadnianie", nawadnianie.build),
    ("zrodla", zrodla.build),
]


class ParcelUnavailable(Exception):
    """The parcel could not be found or downloaded; the message is for the user, in Polish."""


def _safe(step: str, fn: Callable[[], T], fallback: T) -> T:
    try:
        return fn()
    except Exception:  # a broken step must not take the report down
        log.exception("report step %s failed", step)
        return fallback


def parcel_info(data: FetchResult) -> ParcelInfo:
    p = data.parcel.data
    teryt = p.id.split(".")[0].replace("_", "")
    return ParcelInfo(
        id=p.id,
        number=p.number,
        precinct=p.precinct,
        commune=p.commune,
        county=p.county,
        voivodeship=p.voivodeship,
        teryt_commune=teryt,
        area_ha=p.area_ha,
        centroid_lonlat=(p.centroid_4326[0], p.centroid_4326[1]),
    )


def number_actions(actions: list[Action], plan_numbers: list[int], day: date | None = None) -> list[Action]:
    """Numbers 1..M in report order: retention, soil and crop, irrigation; inside a group the order stays as
    `rank_actions` left it. Out of season, actions due before the season starts (21.III) come first."""
    order = {"retencja": 0, "uprawa": 1, "nawadnianie": 2}
    season_start = None
    if day is not None and not season_of(day)[1]:
        season_start = date(day.year + 1 if day.month >= 10 else day.year, 3, 21)

    def early(a: Action) -> int:
        return 0 if season_start and a.due is not None and a.due < season_start else 1

    ranked = sorted(actions, key=lambda a: (early(a), order[a.group]))
    return [
        a.model_copy(update={"n": i, "in_plan": i in plan_numbers}) for i, a in enumerate(ranked, start=1)
    ]


def build_context(req: ReportRequest) -> ReportContext:
    data, copy = datasource.load(req.parcel_id, req.day)
    if not data.parcel.usable:
        raise ParcelUnavailable(
            f"ULDK nie zna działki {req.parcel_id}. Sprawdź numer obrębu i działki."
            if data.parcel.status == "error"
            else "Nie udało się pobrać obrysu działki z ULDK. Spróbuj za minutę."
        )
    return ReportContext(request=req, data=data, parcel=parcel_info(data), data_copy=copy)


def total_time_s(sources: list[SourceRow]) -> float:
    """The one total of the report: the sum of the source rows, the same number on the map card and in section 8."""
    return round(sum(row.elapsed_s or 0 for row in sources), 1)


def build_report(req: ReportRequest) -> Report:
    ctx = build_context(req)
    ctx.soil = _safe(
        "soil", lambda: assess_soil(ctx), SoilInfo(category=None, source="brak", words="brak danych o glebie")
    )
    w = ctx.data.weather.data if ctx.data.weather.usable else None
    ctx.verdict = _safe(
        "verdict",
        lambda: assess(
            w.dates if w else [],
            w.precipitation_mm if w else [],
            w.et0_mm if w else [],
            req.day,
            req.crop,
            ctx.soil.category,
        ),
        Verdict(state="no_data", badge="", kbw_mm=None, threshold_mm=None, margin_mm=None, period=None,
                sentence="Nie udało się policzyć bilansu.", how=""),
    )  # fmt: skip
    ctx.verdict_dg = _safe("verdict_dg", lambda: verdict_dg(ctx), None)
    ctx.smsr = _safe("smsr", lambda: smsr_row(ctx), SmsrRow(state="missing", commune=ctx.parcel.commune))
    if ctx.verdict.state == "out_of_season":
        ctx.crop_condition = not_applicable()
    else:
        ctx.crop_condition = _safe(
            "crop_condition",
            lambda: assess_crop_condition(ctx),
            CropCondition(state="missing", words="Brak: stanu roślin, bo obliczenie nie powiodło się"),
        )
    ctx.reading = _safe("reading", lambda: read_together(ctx.verdict.state, ctx.crop_condition), "")
    ctx.vulnerability = _safe(
        "vulnerability",
        lambda: assess_vulnerability(ctx),
        Vulnerability(reason="Brak: podatności działki, bo obliczenie nie powiodło się"),
    )
    ctx.off_season = _safe("off_season", lambda: off_season_summary(ctx), None)
    ctx.diagnosis = _safe("diagnosis", lambda: diagnose(ctx), Diagnosis())
    actions = _safe("retention", lambda: retention_actions(ctx), []) + _safe(
        "rules", lambda: field_actions(ctx), []
    )
    ctx.actions = number_actions(actions, req.plan, req.day)
    ctx.forecast = _safe("forecast", lambda: forecast_exceedance(ctx), ExceedanceForecast(state="missing"))
    ctx.agreement = _safe(
        "agreement",
        lambda: agreement_frame(ctx.metrics, ctx.verdict.margin_mm),
        Agreement(available=False, sentence=""),
    )
    sections = [
        _safe(
            sid, lambda b=builder: b(ctx), placeholder(sid, sid, "Tej części raportu nie udało się policzyć.")
        )
        for sid, builder in SECTION_BUILDERS
    ]
    retention = [a for a in ctx.actions if a.group == "retencja"]
    sources = _safe("sources", lambda: source_rows(ctx), [])
    return Report(
        request=req,
        parcel=ctx.parcel,
        data_copy=ctx.data_copy,
        data_copy_took_s=datasource.original_download_s(ctx.data) if ctx.data_copy else None,
        map=_safe("map", lambda: map_view(ctx), None),
        soil=ctx.soil,
        verdict=ctx.verdict,
        verdict_dg=ctx.verdict_dg,
        smsr=ctx.smsr,
        crop_condition=ctx.crop_condition,
        reading=ctx.reading,
        vulnerability=ctx.vulnerability,
        off_season=ctx.off_season,
        diagnosis=ctx.diagnosis,
        action_1=retention[0] if retention else None,
        action_1_reason="" if retention else "brak działań retencyjnych, bo nie ma oceny bilansu",
        agreement=ctx.agreement,
        forecast=ctx.forecast,
        sections=sections,
        sources=sources,
        total_s=total_time_s(sources),
    )
