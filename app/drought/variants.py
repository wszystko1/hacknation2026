"""The second variant of the verdict: evaporation by the Doroszewski-Górski formula, shown in the advisor view."""

from __future__ import annotations

import json
from pathlib import Path

from app.context import ReportContext
from app.drought.evaporation import etp_dg_daily
from app.drought.kbw import assess
from app.geodata.samples import sample_stem
from app.models import Verdict

WEATHER_INPUTS = Path(__file__).resolve().parents[2] / "demo" / "data" / "weather_inputs"


def inputs_file(parcel_id: str, day: str) -> Path:
    """Where the temperature and sunshine of an offline demo copy are kept."""
    return WEATHER_INPUTS / f"{sample_stem(parcel_id, day)}.json"


def _frozen_inputs(parcel_id: str, day: str, dates: list[str]) -> tuple[list[float | None], list[float | None]]:
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
        w.dates, w.precipitation_mm, et, ctx.request.day, ctx.request.crop, ctx.soil.category, et_method="dg"
    )
    return None if verdict.state == "no_data" else verdict
