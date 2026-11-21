"""Climatic water balance (KBW) in the 14 periods of the drought regulation (Dz.U. 2019 poz. 739).

KBW = sum of precipitation - sum of reference evapotranspiration (ET0, FAO-56) over one period of six dekads.
The verdict compares the KBW of each finished period with the threshold for the crop group and soil category.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from app.drought.thresholds import threshold_mm
from app.models import (
    BADGE_ABOVE,
    BADGE_BELOW,
    CROP_LABELS,
    LAW_THRESHOLDS,
    CropGroup,
    PeriodBalance,
    SoilCategory,
    Verdict,
)

# (period number, (start month, day), (end month, day)) as published by SMSR IUNG.
PERIODS: list[tuple[int, tuple[int, int], tuple[int, int]]] = [
    (1, (3, 21), (5, 20)),
    (2, (4, 1), (5, 31)),
    (3, (4, 11), (6, 10)),
    (4, (4, 21), (6, 20)),
    (5, (5, 1), (6, 30)),
    (6, (5, 11), (7, 10)),
    (7, (5, 21), (7, 20)),
    (8, (6, 1), (7, 31)),
    (9, (6, 11), (8, 10)),
    (10, (6, 21), (8, 20)),
    (11, (7, 1), (8, 31)),
    (12, (7, 11), (9, 10)),
    (13, (7, 21), (9, 20)),
    (14, (8, 1), (9, 30)),
]


def period_dates(year: int, n: int) -> tuple[date, date]:
    _, (sm, sd), (em, ed) = PERIODS[n - 1]
    return date(year, sm, sd), date(year, em, ed)


def season_of(day: date) -> tuple[int, bool]:
    """(season year, in_monitoring) for a day: 21.III-30.IX is in the monitoring period."""
    if date(day.year, 3, 21) <= day <= date(day.year, 9, 30):
        return day.year, True
    return (day.year if day.month >= 10 else day.year - 1), False


def period_balance(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    year: int,
    n: int,
    until: date,
    crop: CropGroup,
    soil: SoilCategory | None,
) -> PeriodBalance | None:
    """KBW of period n in `year`, summed up to min(period end, until). None when the period has not started."""
    start, end = period_dates(year, n)
    stop = min(end, until)
    if stop < start:
        return None
    by_day = {d: (p, e) for d, p, e in zip(dates, precip, et0, strict=True)}
    p_sum = e_sum = 0.0
    days = 0
    d = start
    while d <= stop:
        p, e = by_day.get(d.isoformat(), (None, None))
        if p is not None and e is not None:
            p_sum += p
            e_sum += e
            days += 1
        d += timedelta(days=1)
    kbw = round(p_sum - e_sum, 1)
    thr = threshold_mm(crop, soil, n) if soil else None
    return PeriodBalance(
        n=n,
        start=start,
        end=end,
        precip_mm=round(p_sum, 1),
        et0_mm=round(e_sum, 1),
        kbw_mm=kbw,
        threshold_mm=thr,
        margin_mm=round(kbw - thr, 1) if thr is not None else None,
        complete=end <= until,
        days=days,
    )


def season_balances(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    year: int,
    until: date,
    crop: CropGroup,
    soil: SoilCategory | None,
) -> list[PeriodBalance]:
    out = []
    for n, _, _ in PERIODS:
        pb = period_balance(dates, precip, et0, year, n, until, crop, soil)
        if pb is not None:
            out.append(pb)
    return out


def _mm(x: float) -> str:
    return f"{x:.0f}".replace("-", "−")


def _dm(d: date) -> str:
    return d.strftime("%d.%m")


def assess(
    dates: Sequence[str],
    precip: Sequence[float | None],
    et0: Sequence[float | None],
    day: date,
    crop: CropGroup,
    soil: SoilCategory | None,
) -> Verdict:
    """The verdict for the analysis day. Skeleton: states and numbers are computed, texts are minimal."""
    if not dates:
        return Verdict(
            state="no_data",
            badge="",
            kbw_mm=None,
            threshold_mm=None,
            margin_mm=None,
            period=None,
            sentence="Brak danych o pogodzie dla tej działki; bez bilansu nie dajemy zaleceń.",
            how="",
        )
    year, in_season = season_of(day)
    until = day if in_season else date(year, 9, 30)
    periods = season_balances(dates, precip, et0, year, until, crop, soil)
    complete = [p for p in periods if p.complete]
    if not complete:
        running = periods[0] if periods else None
        return Verdict(
            state="running",
            badge="",
            kbw_mm=running.kbw_mm if running else None,
            threshold_mm=None,
            margin_mm=None,
            period=running,
            periods=periods,
            sentence="Pierwszy okres 60 dni jeszcze trwa; wynik wobec progu pojawi się po 20.05.",
            how="",
            note=f"okres jeszcze trwa: {running.days} z 61 dni" if running else "",
        )
    with_thr = [p for p in complete if p.margin_mm is not None]
    top = min(with_thr, key=lambda p: p.margin_mm) if with_thr else min(complete, key=lambda p: p.kbw_mm)
    how = (
        f"opad {_mm(top.precip_mm)} − parowanie {_mm(top.et0_mm)} = {_mm(top.kbw_mm)} mm "
        f"(okres {top.n}, {_dm(top.start)}–{_dm(top.end)}.{top.start.year}) · próg z {LAW_THRESHOLDS}"
    )
    crop_label = CROP_LABELS[crop].lower()
    if not in_season:
        state, badge = "out_of_season", f"Sezon {year}"
    elif top.margin_mm is None:
        state, badge = "no_threshold", ""
    elif top.margin_mm < 0:
        state, badge = "below", BADGE_BELOW
    else:
        state, badge = "above", BADGE_ABOVE
    if top.margin_mm is None:
        sentence = (
            f"W tych 60 dniach bilans wody wyniósł {_mm(top.kbw_mm)} mm. "
            f"Tu pojawi się porównanie z progiem z {LAW_THRESHOLDS} dla upraw: {crop_label}."
        )
    elif top.margin_mm < 0:
        sentence = (
            f"W tych 60 dniach wyparowało o {_mm(-top.kbw_mm)} mm więcej wody, niż spadło. "
            f"To {_mm(-top.margin_mm)} mm poniżej progu suszy dla upraw: {crop_label} na tej glebie."
        )
    else:
        sentence = (
            f"W tych 60 dniach bilans wody wyniósł {_mm(top.kbw_mm)} mm. "
            f"To {_mm(top.margin_mm)} mm powyżej progu suszy dla upraw: {crop_label} na tej glebie."
        )
    return Verdict(
        state=state,
        badge=badge,
        kbw_mm=top.kbw_mm,
        threshold_mm=top.threshold_mm,
        margin_mm=top.margin_mm,
        period=top,
        periods=periods,
        sentence=sentence,
        how=how,
        season_year=year if not in_season else None,
    )
