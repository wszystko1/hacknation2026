"""From 1 October to 20 March the verdict and the plants do not apply; the report gives the season and the rain."""

from __future__ import annotations

import statistics
from datetime import date

from app.context import ReportContext
from app.fmt import day as ddmmyyyy
from app.fmt import dec
from app.models import CropCondition, OffSeason

NOT_APPLICABLE_WORDS = "Stan roślin: nie dotyczy poza sezonem (1.X–20.III)"
MIN_YEARS = 3  # fewer earlier years do not make a norm
MAX_MISSING_SHARE = 0.10  # a window with more days without rain data is skipped


def _clamp(year: int, month: int, dom: int) -> date:
    try:
        return date(year, month, dom)
    except ValueError:  # 29 February in a year that has none
        return date(year, month, 28)


def autumn_start_year(day: date) -> int:
    """The year of the 1 October that opened the winter half-year `day` belongs to."""
    return day.year if day.month >= 10 else day.year - 1


def rain_since_october(dates: list[str], rain: list[float | None], day: date) -> dict[int, float]:
    """Rain from 1 October to the same calendar day, per start year; only windows with enough data."""
    by_day = dict(zip(dates, rain, strict=False))
    out: dict[int, float] = {}
    for y in range(min(int(d[:4]) for d in dates) if dates else day.year, autumn_start_year(day) + 1):
        start = date(y, 10, 1)
        end = _clamp(y + (day.year - autumn_start_year(day)), day.month, day.day)
        n = (end - start).days + 1
        vals = [by_day.get((start.fromordinal(start.toordinal() + i)).isoformat()) for i in range(n)]
        have = [v for v in vals if v is not None]
        if n > 0 and len(have) >= n * (1 - MAX_MISSING_SHARE) and vals[0] is not None:
            out[y] = round(sum(have), 1)
    return out


def norm_from(per_year: dict[int, float], current_year: int) -> tuple[float | None, int]:
    """Median of earlier years only: the assessed year never enters its own norm."""
    earlier = [v for y, v in per_year.items() if y < current_year]
    if len(earlier) < MIN_YEARS:
        return None, len(earlier)
    return round(statistics.median(earlier), 1), len(earlier)


def _last_season(ctx: ReportContext) -> str:
    v = ctx.verdict
    if v is None or v.period is None:
        return "Brak: oceny minionego sezonu, bo nie ma bilansu z tego roku"
    p = v.period
    text = (
        f"Najgorszy okres sezonu {v.season_year}: {ddmmyyyy(p.start)}–{ddmmyyyy(p.end)}, bilans {dec(p.kbw_mm)} mm"
    )
    if p.threshold_mm is not None and p.margin_mm is not None:
        side = "poniżej" if p.margin_mm < 0 else "powyżej"
        text += f", {dec(abs(p.margin_mm))} mm {side} progu {dec(p.threshold_mm)} mm"
    s = ctx.smsr
    if s is not None and s.state == "ok":
        text += f"; ocena SMSR dla gminy {s.commune}: {s.words}"
    return text


def off_season_summary(ctx: ReportContext) -> OffSeason | None:
    """The last season, the rain since 1 October against the norm; None inside the season."""
    v = ctx.verdict
    if v is None or v.state != "out_of_season" or v.season_year is None:
        return None
    day = ctx.request.day
    last = _last_season(ctx)
    w = ctx.data.weather.data if ctx.data.weather.usable else None
    if w is None:
        return OffSeason(season_year=v.season_year, last_season=last,
                         sentence="Brak: opadu od 1.X, bo nie ma danych pogodowych")  # fmt: skip
    per_year = rain_since_october(list(w.dates), list(w.precipitation_mm), day)
    current = autumn_start_year(day)
    rain = per_year.get(current)
    norm, n = norm_from(per_year, current)
    if rain is None or norm is None:
        return OffSeason(season_year=v.season_year, rain_mm=rain, n_years=n, last_season=last,
                         sentence="Brak: porównania opadu od 1.X z normą, bo w danych jest za mało lat")  # fmt: skip
    diff = rain - norm
    if diff < -0.1 * norm:
        verdict = "zapas wody przed zimą jest mniejszy niż zwykle"
    elif diff > 0.1 * norm:
        verdict = "zapas wody przed zimą jest większy niż zwykle"
    else:
        verdict = "zapas wody przed zimą jest zbliżony do zwykłego"
    sentence = f"Opad od 1.X to {round(rain)} mm, norma z {n} lat to {round(norm)} mm: {verdict}."
    return OffSeason(season_year=v.season_year, rain_mm=rain, norm_mm=norm, n_years=n,
                     sentence=sentence, last_season=last)  # fmt: skip


def not_applicable() -> CropCondition:
    """The plants row outside the season: nothing is read from the satellite."""
    return CropCondition(state="not_applicable", words=NOT_APPLICABLE_WORDS)
