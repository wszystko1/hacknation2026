"""Diagnosis of the causes of the water deficit from the parcel's own data. No assessment, no causes.

Every rule that holds gives a cause, each with the parcel's number in its words; the strongest (the largest
shortfall in mm) stands first. The "usual" season is read from the earlier seasons of the same weather series
that the verdict uses, over the same days of the year, so the comparison needs no other source.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from app.context import ReportContext
from app.drought.kbw import period_balance as _period_balance
from app.drought.kbw import season_balances, season_of
from app.fmt import dec
from app.models import (
    LAW_THRESHOLDS,
    Cause,
    CauseCode,
    CropGroup,
    Diagnosis,
    PeriodBalance,
)

T = TypeVar("T")

SEASONS = 10  # seasons in the history: the verdict's season and the nine before it
MIN_EARLIER_SEASONS = 3  # fewer earlier seasons give no "usual" season
MIN_DATA_SHARE = 0.9  # a period needs at least this share of days with rain and evaporation data

# Thresholds of the rules. `source` empty means the number is the team's proposal and says so in the adviser view.
LESS_RAIN_SHARE = 0.85  # rain at most this share of the usual
MORE_EVAPORATION_SHARE = 1.10  # evaporation at least this share of the usual
LIGHT_SOIL_CATEGORIES = ("I", "II")
RUNOFF_SLOPE_PCT = 2.0  # mean slope above this makes water run off


@dataclass(frozen=True)
class Rule:
    code: CauseCode
    label: str  # farmer-facing name of the cause
    condition: str  # the threshold in words, for the adviser view
    confidence: str  # "propozycja zespołu" unless a source stands behind the number
    source: str = ""


RULES: tuple[Rule, ...] = (
    Rule(
        "malo_opadu",
        "Za mało opadu",
        f"opad w okresie co najwyżej {dec(LESS_RAIN_SHARE * 100)}% opadu zwykłego sezonu",
        "propozycja zespołu",
    ),
    Rule(
        "duze_parowanie",
        "Duże parowanie",
        f"parowanie w okresie co najmniej {dec(MORE_EVAPORATION_SHARE * 100)}% parowania zwykłego sezonu",
        "propozycja zespołu",
    ),
    Rule(
        "gleba_lekka",
        "Gleba słabo trzyma wodę",
        "kategoria gleby I albo II (gleba bardzo podatna albo podatna na suszę)",
        "przepis",
        f"podział na kategorie gleb: {LAW_THRESHOLDS}",
    ),
    Rule(
        "splyw",
        "Woda spływa z pola",
        f"średni spadek terenu z NMT powyżej {dec(RUNOFF_SLOPE_PCT, 1)}%",
        "propozycja zespołu",
    ),
    Rule(
        "faza_wrazliwa",
        "Uprawa w wrażliwej fazie",
        "rozporządzenie podaje dla tej uprawy próg w tym okresie (w okresach z „x” susza nie obniża plonu)",
        "przepis",
        f"tabela progów: {LAW_THRESHOLDS}",
    ),
)
RULE_BY_CODE: dict[CauseCode, Rule] = {r.code: r for r in RULES}


# ---------------------------------------------------------------- the same weather series as the verdict


def _cached(ctx: ReportContext, key: str, compute: Callable[[], T]) -> T:
    """Both sections and the diagnosis read the same history; compute it once per report."""
    store: dict[str, object] = ctx.__dict__.setdefault("_advice_cache", {})
    if key not in store:
        store[key] = compute()
    return store[key]  # type: ignore[return-value]


def _series(ctx: ReportContext) -> tuple[list[str], list[float | None], list[float | None]] | None:
    w = ctx.data.weather.data if ctx.data.weather.usable else None
    if w is None or not w.dates:
        return None
    return w.dates, w.precipitation_mm, w.et0_mm


def _enough_data(p: PeriodBalance, until: date) -> bool:
    window = (min(p.end, until) - p.start).days + 1
    return window > 0 and p.days >= MIN_DATA_SHARE * window


@dataclass
class SeasonWorst:
    """One season of the history: its worst finished period up to the same day of the year."""

    year: int
    period: PeriodBalance
    below: bool | None  # None: the regulation gives no threshold for this period


def season_year(ctx: ReportContext) -> int:
    return season_of(ctx.request.day)[0]


def _cutoff(ctx: ReportContext, year: int) -> date:
    """The last day counted in `year`: the analysis day's calendar date, or 30.IX out of season."""
    day = ctx.request.day
    _, in_season = season_of(day)
    return date(year, day.month, day.day) if in_season else date(year, 9, 30)


def season_history(ctx: ReportContext) -> list[SeasonWorst]:
    """Up to ten seasons ending with the verdict's own, oldest first; a season without data is left out."""

    def compute() -> list[SeasonWorst]:
        series = _series(ctx)
        soil = ctx.soil.category if ctx.soil else None
        if series is None:
            return []
        dates, rain, et0 = series
        out: list[SeasonWorst] = []
        last = season_year(ctx)
        for year in range(last - SEASONS + 1, last + 1):
            until = _cutoff(ctx, year)
            usable = [
                p
                for p in season_balances(dates, rain, et0, year, until, ctx.request.crop, soil)
                if p.complete and _enough_data(p, until)
            ]
            if not usable:
                continue
            with_threshold = [p for p in usable if p.margin_mm is not None]
            worst = (
                min(with_threshold, key=lambda p: p.margin_mm or 0.0)
                if with_threshold
                else min(usable, key=lambda p: p.kbw_mm)
            )
            out.append(SeasonWorst(year, worst, None if worst.margin_mm is None else worst.margin_mm < 0))
        return out

    return _cached(ctx, "history", compute)


@dataclass
class UsualSeason:
    """The period of the verdict in the earlier seasons: the median balance and a season that closes the sum."""

    n_seasons: int
    years: list[int]
    kbw_mm: float  # median balance of the same period
    precip_mm: float  # rain of the season(s) with the median balance
    et0_mm: float  # evaporation of the same season(s); precip - et0 = kbw_mm exactly


def usual_period(ctx: ReportContext) -> UsualSeason | None:
    """The same days of the year in the earlier seasons of the history, or None with fewer than three."""

    def compute() -> UsualSeason | None:
        v, series = ctx.verdict, _series(ctx)
        if v is None or v.period is None or series is None:
            return None
        dates, rain, et0 = series
        soil = ctx.soil.category if ctx.soil else None
        n, stop = v.period.n, min(v.period.end, ctx.request.day)
        last = season_year(ctx)
        rows: list[tuple[int, PeriodBalance]] = []
        for year in range(last - SEASONS + 1, last):
            until = date(year, stop.month, stop.day)
            p = _period_balance(dates, rain, et0, year, n, until, ctx.request.crop, soil)
            if p is not None and _enough_data(p, until):
                rows.append((year, p))
        if len(rows) < MIN_EARLIER_SEASONS:
            return None
        ranked = sorted(rows, key=lambda r: r[1].kbw_mm)
        mid = len(ranked) // 2
        middle = [ranked[mid]] if len(ranked) % 2 else ranked[mid - 1 : mid + 1]
        return UsualSeason(
            n_seasons=len(rows),
            years=sorted(y for y, _ in rows),
            kbw_mm=round(statistics.median(p.kbw_mm for _, p in rows), 1),
            precip_mm=round(statistics.fmean(p.precip_mm for _, p in middle), 1),
            et0_mm=round(statistics.fmean(p.et0_mm for _, p in middle), 1),
        )

    return _cached(ctx, "usual", compute)


# ---------------------------------------------------------------- the rules


def _rain_cause(p: PeriodBalance, usual: UsualSeason) -> Cause | None:
    if p.precip_mm > LESS_RAIN_SHARE * usual.precip_mm:
        return None
    gap = usual.precip_mm - p.precip_mm
    return Cause(
        code="malo_opadu",
        words=f"spadło {dec(p.precip_mm)} mm, o {dec(gap)} mm mniej niż zwykle ({dec(usual.precip_mm)} mm)",
        strength_mm=round(gap, 1),
    )


def _evaporation_cause(p: PeriodBalance, usual: UsualSeason) -> Cause | None:
    if p.et0_mm < MORE_EVAPORATION_SHARE * usual.et0_mm:
        return None
    gap = p.et0_mm - usual.et0_mm
    return Cause(
        code="duze_parowanie",
        words=f"wyparowało {dec(p.et0_mm)} mm, o {dec(gap)} mm więcej niż zwykle ({dec(usual.et0_mm)} mm)",
        strength_mm=round(gap, 1),
    )


def _soil_cause(ctx: ReportContext, p: PeriodBalance) -> Cause | None:
    soil = ctx.soil
    if soil is None or soil.category not in LIGHT_SOIL_CATEGORIES:
        return None
    if soil.sand_pct is not None:
        number = f"piasku {dec(soil.sand_pct)}% w warstwie 0–30 cm"
    elif p.threshold_mm is not None:
        number = f"próg suszy w okresie {p.n} to {dec(p.threshold_mm)} mm"
    else:
        number = f"kategoria {soil.category} z czterech"
    return Cause(code="gleba_lekka", words=f"{soil.words}; {number}")


def mean_slope_pct(ctx: ReportContext) -> float | None:
    terrain = ctx.data.terrain.data if ctx.data.terrain.usable else None
    return terrain.slope_mean_pct if terrain else None


def nearest_ditch_m(ctx: ReportContext) -> float | None:
    water = ctx.data.water.data if ctx.data.water.usable else None
    return water.nearest_ditch_m if water else None


def _runoff_cause(ctx: ReportContext) -> Cause | None:
    slope = mean_slope_pct(ctx)
    if slope is None or slope <= RUNOFF_SLOPE_PCT:
        return None
    words = f"spadek terenu {dec(slope, 1)}% (NMT)"
    ditch = nearest_ditch_m(ctx)
    if ditch is not None:
        words += f", najbliższy rów w odległości {dec(ditch, 1 if ditch < 10 else 0)} m (BDOT10k)"
    return Cause(code="splyw", words=words)


def _phase_cause(ctx: ReportContext, p: PeriodBalance) -> Cause | None:
    soil = ctx.soil.category if ctx.soil else None
    if ctx.request.crop == CropGroup.INNA or soil is None or p.threshold_mm is None:
        return None  # a threshold in the table means drought lowers the yield in this period
    return Cause(
        code="faza_wrazliwa",
        words=f"w okresie {p.n} ({dec(p.threshold_mm)} mm progu) susza obniża plon tej uprawy",
    )


def diagnose(ctx: ReportContext) -> Diagnosis:
    """All causes whose rule holds, strongest first; empty without an assessment."""
    v = ctx.verdict
    if v is None or v.period is None or v.state == "no_data":
        return Diagnosis()
    p = v.period
    usual = usual_period(ctx)
    found: list[Cause | None] = []
    if usual is not None:
        found += [_rain_cause(p, usual), _evaporation_cause(p, usual)]
    found += [_soil_cause(ctx, p), _runoff_cause(ctx), _phase_cause(ctx, p)]
    causes = [c for c in found if c is not None]
    causes.sort(key=lambda c: -(c.strength_mm if c.strength_mm is not None else -1.0))  # stable: rule order
    return Diagnosis(causes=causes, usual_kbw_mm=usual.kbw_mm if usual else None)


# ---------------------------------------------------------------- the split of the balance, for section 3


@dataclass
class BalanceSplit:
    """usual balance + rain step + evaporation step = this period's balance (exactly, in tenths of mm)."""

    usual_mm: float
    rain_step_mm: float  # negative: less rain than usual
    evaporation_step_mm: float  # negative: more evaporation than usual
    result_mm: float

    def parts(self) -> list[float]:
        return [self.usual_mm, self.rain_step_mm, self.evaporation_step_mm, self.result_mm]


def balance_split(ctx: ReportContext) -> BalanceSplit | None:
    v, usual = ctx.verdict, usual_period(ctx)
    if v is None or v.period is None or usual is None:
        return None
    p = v.period
    return BalanceSplit(
        usual_mm=usual.kbw_mm,
        rain_step_mm=round(p.precip_mm - usual.precip_mm, 1),
        evaporation_step_mm=round(-(p.et0_mm - usual.et0_mm), 1),
        result_mm=p.kbw_mm,
    )
