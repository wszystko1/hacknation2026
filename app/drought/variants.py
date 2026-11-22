"""The verdict with evaporation by the Doroszewski-Górski formula (the formula of the Polish SMSR IUNG).

`main_verdict` picks the verdict of the report: Doroszewski-Górski by default, FAO-56 when the point has no
temperature or sunshine or when `CHRONPLON_VERDICT_ET=fao56`. Irrigation doses and dates stay on FAO-56."""

from __future__ import annotations

import json
from pathlib import Path

from app.context import ReportContext
from app.drought.evaporation import etp_dg_daily
from app.drought.kbw import assess, verdict_et_method, verdict_period_mode
from app.drought.kbw import main_verdict as fao56_verdict
from app.geodata.samples import sample_stem
from app.models import Verdict

WEATHER_INPUTS = Path(__file__).resolve().parents[2] / "demo" / "data" / "weather_inputs"


def inputs_file(parcel_id: str, day: str) -> Path:
    """Where the temperature and sunshine of an offline demo copy are kept."""
    return WEATHER_INPUTS / f"{sample_stem(parcel_id, day)}.json"


def _frozen_inputs(
    parcel_id: str, day: str, dates: list[str]
) -> tuple[list[float | None], list[float | None]]:
    path = inputs_file(parcel_id, day)
    if not path.is_file():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    by_day = dict(zip(data["dates"], zip(data["tmean_c"], data["sunshine_h"], strict=True), strict=True))
    return [by_day.get(d, (None, None))[0] for d in dates], [by_day.get(d, (None, None))[1] for d in dates]


def verdict_dg(ctx: ReportContext) -> Verdict | None:
    """The verdict recomputed with `et_method="dg"`; None when there is no temperature and sunshine for the point."""
    if not ctx.data.weather.usable:
        return None
    w = ctx.data.weather.data
    tmean, sun = w.tmean_c, w.sunshine_h
    if not tmean or not sun:
        tmean, sun = _frozen_inputs(ctx.request.parcel_id, ctx.request.day.isoformat(), w.dates)
    if not tmean or not sun:
        return None
    et = etp_dg_daily(w.dates, tmean, sun, w.latitude)
    verdict = assess(
        w.dates,
        w.precipitation_mm,
        et,
        ctx.request.day,
        ctx.request.crop,
        ctx.soil.category,
        et_method="dg",
        period=verdict_period_mode(),
    )
    return None if verdict.state == "no_data" else verdict


FALLBACK_NOTE = "Parowanie liczone wzorem FAO-56, bo brak temperatury lub usłonecznienia do wzoru Doroszewskiego–Górskiego."


def main_verdict(ctx: ReportContext) -> tuple[Verdict, Verdict | None]:
    """The verdict of the report and the other formula's verdict (None when it cannot be computed).

    Needs `ctx.soil` and the weather in `ctx.data`. Doroszewski-Górski is the verdict unless the switch asks for
    FAO-56; without temperature or sunshine the verdict falls back to FAO-56 and says so in `how`.
    """
    w = ctx.data.weather.data if ctx.data.weather.usable else None
    fao = fao56_verdict(
        w.dates if w else [],
        w.precipitation_mm if w else [],
        w.et0_mm if w else [],
        ctx.request.day,
        ctx.request.crop,
        ctx.soil.category,
    )
    if verdict_et_method() == "fao56" or fao.state == "no_data":
        return fao, verdict_dg(ctx) if fao.state != "no_data" else None
    dg = verdict_dg(ctx)
    if dg is not None:
        return dg, fao
    how = f"{fao.how} · {FALLBACK_NOTE}" if fao.how else FALLBACK_NOTE
    return fao.model_copy(update={"how": how}), None
